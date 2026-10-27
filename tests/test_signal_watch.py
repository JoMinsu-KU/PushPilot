"""Finite signal-watch tests with generated frames and offline model fixtures."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.core import CommandError, WorkspaceStore
from backend.live_intelligence import LiveIntelligenceService
from backend.scene import SceneError
from backend.signal_watch import SignalWatchService
from test_live_intelligence import FakeCamera, FakePlanner, FakeReviewer, NeverTextProvider, signal_result, test_map


class SignalWatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = WorkspaceStore(":memory:", provider=NeverTextProvider(), map_definition=test_map())
        self.addCleanup(self.store.close)
        self.camera = FakeCamera(self.store.map_definition)
        self.planner, self.reviewer = FakePlanner(), FakeReviewer()
        self.intelligence = LiveIntelligenceService(self.store, self.camera,
            planning_provider=self.planner, review_provider=self.reviewer)
        self.now = [100.0]

        async def finite_sleep(seconds):
            self.now[0] += seconds
            await asyncio.sleep(0)

        self.watch = SignalWatchService(self.store, self.intelligence, clock=lambda: self.now[0], sleep=finite_sleep)
        self.addAsyncCleanup(self.watch.close)

    def payload(self, **extra):
        return {"request_id": str(uuid4()), "expected_revision": self.store.snapshot()["revision"], **extra}

    async def stopped(self):
        state, status = await self.intelligence.plan(self.payload(text="School via the left map road.", source="typed"))
        self.assertEqual(status, 200)
        state, status = self.store.execute("approve", self.payload(plan_id=state["plan"]["id"], plan_revision=state["plan"]["revision"]))
        self.assertEqual(status, 200)
        for _kind in ("PUSH", "STOP"):
            state, status = self.intelligence.advance(self.payload())
            self.assertEqual(status, 200)
            state, status = await self.intelligence.review_action(self.payload(review_id=state["review"]["id"], expected_visual="Synthetic placement expectation."))
            self.assertEqual(status, 200)
        self.assertEqual(state["state"], "WAITING_SIGNAL")
        return state

    async def finished(self):
        for _index in range(200):
            state = self.store.snapshot()
            if state["signal_watch"]["status"] != "running":
                return state
            await asyncio.sleep(0.005)
        self.fail("The finite fixture watch did not finish.")

    async def test_no_watch_starts_at_initialization_and_defaults_are_finite(self):
        self.assertNotIn("signal_watch", self.store.snapshot())
        self.assertEqual(self.reviewer.signal_calls, [])
        await self.stopped()
        state, status = await self.watch.start(self.payload())
        self.assertEqual(status, 200)
        self.assertEqual((state["signal_watch"]["max_attempts"], state["signal_watch"]["interval_seconds"], state["signal_watch"]["max_duration_seconds"]), (30, 2.0, 300.0))
        self.assertEqual(self.reviewer.signal_calls, [])
        stopped, status = await self.watch.stop(self.payload())
        self.assertEqual((status, stopped["signal_watch"]["status"]), (200, "cancelled"))

    async def test_red_unknown_green_uses_new_frames_and_leaves_crossing_for_review(self):
        await self.stopped()
        colors = ["RED", "UNKNOWN", "GREEN"]

        async def judgment():
            self.assertFalse(self.store._lock._is_owned(), "Inference cannot hold the store lock.")
            self.reviewer.signal_output = signal_result(colors[len(self.reviewer.signal_calls) - 1])

        self.reviewer.signal_callback = judgment
        response, status = await self.watch.start(self.payload(max_attempts=5, interval_seconds=0.5, max_duration_seconds=20))
        self.assertEqual(status, 200)
        state = await self.finished()
        self.assertEqual(state["signal_watch"]["status"], "green_admitted")
        self.assertEqual(state["signal_watch"]["attempts"], 3)
        self.assertEqual(state["state"], "REVIEW_REQUIRED")
        self.assertEqual(state["plan"]["steps"][state["current_step"]]["kind"], "CROSS")
        self.assertEqual(state["review"]["verdict"], "PENDING")
        self.assertEqual(state["action_receipt"]["source"], "simulation")
        self.assertFalse(state["action_receipt"]["physical_stop_verified"])
        frames = [inputs["frame"]["metadata"]["id"] for inputs in self.reviewer.signal_calls]
        self.assertEqual(len(frames), len(set(frames)))
        self.assertGreater(state["revision"], response["revision"])
        operations = self.intelligence.operations()["operations"]
        self.assertEqual(len([operation for operation in operations if operation["kind"] == "live-signal-reviews"]), 3)
        for event in state["events"]:
            if event["kind"].startswith("SIGNAL_WATCH_"):
                self.assertNotIn("record", event)

    async def test_attempt_budget_exhaustion_keeps_red_stopped(self):
        await self.stopped()
        await self.watch.start(self.payload(max_attempts=3, interval_seconds=0.5))
        state = await self.finished()
        self.assertEqual((state["signal_watch"]["status"], state["signal_watch"]["attempts"]), ("exhausted", 3))
        self.assertEqual(state["state"], "WAITING_SIGNAL")
        self.assertTrue(state["stopped"])
        self.assertEqual(len(self.reviewer.signal_calls), 3)

    async def test_elapsed_time_budget_prevents_further_queries(self):
        await self.stopped()
        await self.watch.start(self.payload(max_attempts=60, interval_seconds=2, max_duration_seconds=1))
        state = await self.finished()
        self.assertEqual(state["signal_watch"]["status"], "exhausted")
        self.assertEqual(state["signal_watch"]["attempts"], 1)
        self.assertEqual(len(self.reviewer.signal_calls), 1)
        self.assertEqual(state["state"], "WAITING_SIGNAL")

    async def test_provider_failure_holds_without_fallback_or_retry(self):
        await self.stopped()
        self.reviewer.signal_error = SceneError(502, "Synthetic upstream failure.", "MUSE_FAILED")
        await self.watch.start(self.payload())
        state = await self.finished()
        self.assertEqual(state["signal_watch"]["status"], "held")
        self.assertEqual(len(self.reviewer.signal_calls), 1)
        self.assertEqual(state["state"], "WAITING_SIGNAL")

    async def test_stop_cancels_pending_inference_and_is_idempotent(self):
        await self.stopped()
        entered, release = asyncio.Event(), asyncio.Event()

        async def pending_green():
            entered.set()
            await release.wait()
            self.reviewer.signal_output = signal_result("GREEN")

        self.reviewer.signal_callback = pending_green
        await self.watch.start(self.payload())
        await asyncio.wait_for(entered.wait(), 1)
        command = self.payload()
        first = await self.watch.stop(command)
        self.assertEqual(await self.watch.stop(command), first)
        release.set()
        await asyncio.sleep(0)
        state = self.store.snapshot()
        self.assertEqual(state["signal_watch"]["status"], "cancelled")
        self.assertEqual(state["state"], "WAITING_SIGNAL")
        self.assertEqual(len(self.reviewer.signal_calls), 1)

    async def test_mission_cancel_during_red_interval_prevents_the_next_query(self):
        await self.stopped()
        sleeping, release = asyncio.Event(), asyncio.Event()

        async def paused_sleep(_seconds):
            sleeping.set()
            await release.wait()

        self.watch._sleep = paused_sleep
        await self.watch.start(self.payload())
        await asyncio.wait_for(sleeping.wait(), 1)
        self.store.execute("cancel", self.payload())
        release.set()
        state = await self.finished()
        self.assertEqual(state["signal_watch"]["status"], "cancelled")
        self.assertEqual(state["state"], "CANCELLED")
        self.assertEqual(len(self.reviewer.signal_calls), 1)

    async def test_start_idempotency_conflicts_and_stale_commands(self):
        await self.stopped()
        payload = self.payload(max_attempts=2)
        first = await self.watch.start(payload)
        self.assertEqual(await self.watch.start(payload), first)
        with self.assertRaises(CommandError):
            await self.watch.start({**payload, "max_attempts": 3})
        with self.assertRaises(CommandError):
            await self.watch.start(self.payload())
        with self.assertRaises(CommandError):
            await self.watch.stop({"request_id": str(uuid4()), "expected_revision": 0})
        await self.watch.stop(self.payload())
        self.assertEqual(self.reviewer.signal_calls, [])

    async def test_start_requires_stop_review_target_and_current_camera_view(self):
        with self.assertRaises(CommandError):
            await self.watch.start(self.payload())
        await self.stopped()
        with patch.object(self.store.map_definition, "signal_target", return_value=None):
            with self.assertRaises(CommandError) as raised:
                await self.watch.start(self.payload())
            self.assertEqual(raised.exception.status, 422)
        self.camera.locked = False
        with self.assertRaises(SceneError):
            await self.watch.start(self.payload())
        self.assertEqual(self.reviewer.signal_calls, [])

    async def test_invalid_budgets_fail_before_a_watch_or_provider_call(self):
        await self.stopped()
        for field, value in (("max_attempts", 0), ("max_attempts", 61), ("max_attempts", True),
                             ("interval_seconds", 0.1), ("interval_seconds", 11), ("interval_seconds", True),
                             ("max_duration_seconds", 0), ("max_duration_seconds", 901),
                             ("max_duration_seconds", float("nan"))):
            with self.subTest(field=field, value=value), self.assertRaises(CommandError):
                await self.watch.start(self.payload(**{field: value}))
        self.assertNotIn("signal_watch", self.store.snapshot())
        self.assertEqual(self.reviewer.signal_calls, [])

    async def test_startup_and_close_interrupt_without_auto_resume(self):
        await self.stopped()
        saved = {"id": str(uuid4()), "status": "running", "attempts": 2, "max_attempts": 30,
                 "interval_seconds": 2, "max_duration_seconds": 300, "started_at": self.store._at(), "detail": "Persisted fixture."}
        with self.store._lock, self.store._db:
            state = self.store._load()
            state["signal_watch"] = deepcopy(saved)
            self.store._save(state)
        resumed = SignalWatchService(self.store, self.intelligence)
        self.assertEqual(self.store.snapshot()["signal_watch"]["status"], "interrupted")
        self.assertEqual(self.reviewer.signal_calls, [])
        await resumed.close()
        await self.watch.start(self.payload())
        await self.watch.close()
        self.assertEqual(self.store.snapshot()["signal_watch"]["status"], "interrupted")
        self.assertEqual(self.reviewer.signal_calls, [])
        with self.assertRaises(CommandError):
            await self.watch.start(self.payload())


if __name__ == "__main__":
    unittest.main()
