"""Offline product coordinator tests with a synchronous fake measured driver."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx

from backend.core import CommandError
from backend.physical_api import router
from backend.physical_mission import PhysicalMissionService
from backend.robot_control.mission_policy import MotionReceipt, ParkingTarget, Phase
from tests.test_mission_policy import BINDING, car, context, plan, signal, start


class FakeWorkspace:
    def __init__(self):
        self.map_definition = SimpleNamespace(id="synthetic-map", version="1", geometry_hash="a" * 64)
        self.state = {"state": "PLAN_READY", "session_id": "workspace-session",
            "goal": {"destination": "HANOK", "provider": "meta"},
            "plan": {"id": "workspace-plan", "revision": 1, "route": {"node_ids": ["START", "HANOK"],
                     "destination": "HANOK", "map_id": "synthetic-map", "map_version": "1", "map_hash": "a" * 64},
                     "planning": {"source": "synthetic-live-meta"}}}

    def snapshot(self):
        return deepcopy(self.state)


class FakeMeasuredDriver:
    """There is no network, robot, camera, or real provider behind this driver."""
    def __init__(self, configuration=None):
        self.plan = configuration or plan()
        self.now = 10.
        self.where, self.seq = "START", 1
        self.commands, self.holds = [], []
        self.observations, self.context_calls, self.prepare_calls = 0, 0, 0
        self.closed = False
        self.context_error_at = None
        self.execute_error = None
        self.observe_error = None
        self.prepare_hook = None
        self.observe_hook = None
        self.execute_hook = None
        self.signal_colors = []
        self.status_available = True
        self.primitives = {s.primitive.id: s.primitive for s in self.plan.steps}
        self.primitives.update({p.id: p for p in self.plan.empty_return})
        for step in self.plan.steps:
            if step.signal_gate:
                for p in (step.signal_gate.recontact, step.signal_gate.release_to_wait):
                    self.primitives[p.id] = p

    def readiness(self):
        return {"available": self.status_available, "connected": True, "stationary": True,
                "at_start": self.where == "START", "blockers": [], "destinations": [self.plan.destination],
                "capabilities": {"synthetic_only": True}}

    def prepare(self, _binding):
        self.prepare_calls += 1
        if self.prepare_hook:
            self.prepare_hook()
        return self.plan

    def context(self):
        self.context_calls += 1
        if self.context_error_at == self.context_calls:
            raise ConnectionError("synthetic context failure")
        self.now += .1
        return context(self.where, self.now, self.seq)

    def observe(self, state):
        self.observations += 1
        if self.observe_hook:
            self.observe_hook(state)
        if self.observe_error:
            raise self.observe_error
        self.now += .2
        at = context(self.where, self.now, self.seq)
        if state.phase == Phase.READY:
            return {"start": start(at), "summary": "Synthetic fixed start."}
        step = self.plan.steps[state.step_index]
        digest = hashlib.sha256(f"frame-{self.observations}".encode()).hexdigest()
        observed_car = replace(car(at, state, step=step.id, zone=step.car_zone_id,
            arrived=step.at_goal, heading_deg=step.expected_heading_deg), image_sha256=digest)
        result = {"car": observed_car, "summary": "Synthetic outcome."}
        if state.phase in {Phase.WAIT_SIGNAL, Phase.ENTRY_SIGNAL}:
            color = self.signal_colors.pop(0) if self.signal_colors else "GREEN"
            result["signal"] = replace(signal(at, color=color), image_sha256=digest)
        return result

    def execute(self, primitive_id, command_id):
        self.commands.append((primitive_id, command_id))
        if self.execute_hook:
            self.execute_hook(primitive_id, command_id)
        if self.execute_error:
            raise self.execute_error
        primitive = self.primitives[primitive_id]
        self.now += 1.
        self.where, self.seq = primitive.target_context_id, self.seq + 1
        return MotionReceipt(command_id, primitive_id, "session", self.where, self.now, True, "COMPLETED")

    def hold(self, reason):
        self.holds.append(reason)

    def close(self):
        self.closed = True


def command_for(service, store, **changes):
    value = {"request_id": str(uuid4()), "expected_revision": service.snapshot()["revision"],
        "workspace_session_id": store.state["session_id"], "plan_id": store.state["plan"]["id"],
        "plan_revision": store.state["plan"]["revision"], "destination": store.state["goal"]["destination"],
        "route_nodes": store.state["plan"]["route"]["node_ids"], "map_id": store.map_definition.id,
        "map_version": store.map_definition.version, "map_hash": store.map_definition.geometry_hash}
    value.update(changes)
    return value


async def event_seen(event):
    if not await asyncio.to_thread(event.wait, 2.):
        raise AssertionError("Synthetic driver did not reach the expected synchronization point.")


class PhysicalMissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.store, self.driver = FakeWorkspace(), FakeMeasuredDriver()
        self.service = PhysicalMissionService(self.store, self.temp.name, driver=self.driver,
                                             poll_interval_s=.001, clock=lambda: self.driver.now)

    async def asyncTearDown(self):
        if self.service is not None:
            await self.service.close()
        self.temp.cleanup()

    async def finish(self):
        await asyncio.wait_for(self.service.task, 3.)
        return self.service.snapshot()

    async def test_full_product_loop_qualifies_delivery_then_empty_return(self):
        response = await self.service.start(command_for(self.service, self.store))
        self.assertEqual(response["state"], "STARTING")
        result = await self.finish()
        self.assertEqual(result["state"], "COMPLETE")
        self.assertTrue(result["car"]["arrived"])
        self.assertTrue(result["car"]["aligned"])
        self.assertTrue(result["robot"]["at_start"])
        self.assertEqual([row[0] for row in self.driver.commands], ["delivery-unit", "return"])
        self.assertEqual(len({row[1] for row in self.driver.commands}), 2)
        events = self.service.db.execute("SELECT kind,value FROM events ORDER BY seq").fetchall()
        intents = [i for i, row in enumerate(events) if row[0] == "PRIMITIVE_DISPATCH_INTENT"]
        receipts = [i for i, row in enumerate(events) if row[0] == "PRIMITIVE_RECEIPT"]
        self.assertEqual(len(intents), 2)
        self.assertTrue(all(i < r for i, r in zip(intents, receipts)))

    async def test_available_driver_does_not_release_another_destination(self):
        self.store.state["goal"]["destination"] = "VILLA"
        self.store.state["plan"]["route"].update(destination="VILLA", node_ids=["START", "VILLA"])
        with self.assertRaises(CommandError):
            await self.service.start(command_for(self.service, self.store))
        self.assertEqual(self.driver.prepare_calls, 0)
        self.assertEqual(self.driver.commands, [])
        self.assertEqual(self.service.snapshot()["capabilities"]["destinations"], ["HANOK"])

    async def test_identical_start_request_is_idempotent_before_and_after_finish(self):
        command = command_for(self.service, self.store)
        first = await self.service.start(command)
        self.assertEqual(await self.service.start(command), first)
        await self.finish()
        self.assertEqual(await self.service.start(command), first)
        self.assertEqual(self.driver.prepare_calls, 1)
        self.assertEqual(len(self.driver.commands), 2)

    async def test_request_id_cannot_be_rebound_to_different_payload(self):
        command = command_for(self.service, self.store)
        await self.service.start(command)
        with self.assertRaises(CommandError) as raised:
            await self.service.start({**command, "destination": "VILLA"})
        self.assertEqual(raised.exception.status, 409)
        await self.finish()

    async def test_revision_stale_plan_and_non_muse_goal_cannot_start(self):
        cases = ({"expected_revision": 0}, {"plan_revision": 999}, {"map_hash": "f" * 64})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(CommandError):
                await self.service.start(command_for(self.service, self.store, **changes))
        self.store.state["goal"]["provider"] = "symbolic"
        with self.assertRaises(CommandError):
            await self.service.start(command_for(self.service, self.store))
        self.assertEqual(self.driver.commands, [])

    async def test_workspace_changes_during_prepare_abort_before_task_or_motion(self):
        self.driver.prepare_hook = lambda: self.store.state["plan"].update(revision=2)
        with self.assertRaises(CommandError):
            await self.service.start(command_for(self.service, self.store))
        self.assertIsNone(self.service.task)
        self.assertEqual(self.driver.commands, [])

    async def test_stop_while_prepare_is_blocked_cancels_before_start_task(self):
        entered, release = threading.Event(), threading.Event()
        def blocking_prepare():
            entered.set()
            release.wait(3.)
        self.driver.prepare_hook = blocking_prepare
        preparing = asyncio.create_task(self.service.start(command_for(self.service, self.store)))
        await event_seen(entered)
        stopping = asyncio.create_task(self.service.stop({"request_id": str(uuid4()), "expected_revision": 0}))
        await asyncio.sleep(0)
        release.set()
        with self.assertRaises(CommandError):
            await asyncio.wait_for(preparing, 2.)
        stopped = await asyncio.wait_for(stopping, 2.)
        self.assertEqual(stopped["state"], "HOLD")
        self.assertIsNone(self.service.task)
        self.assertEqual(self.driver.commands, [])
        self.assertIn("STOP_DURING_PREPARATION", self.driver.holds)

    async def test_map_change_during_model_inference_holds_without_dispatch(self):
        def change(_state):
            self.store.map_definition.geometry_hash = "b" * 64
        self.driver.observe_hook = change
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(self.driver.commands, [])
        self.assertTrue(self.driver.holds)

    async def test_stop_during_model_inference_admits_no_next_motion(self):
        entered, release = threading.Event(), threading.Event()
        def blocking(_state):
            entered.set()
            release.wait(3.)
        self.driver.observe_hook = blocking
        await self.service.start(command_for(self.service, self.store))
        await event_seen(entered)
        stopped = await self.service.stop({"request_id": str(uuid4()), "expected_revision": 0})
        self.assertEqual(stopped["state"], "HOLD")
        release.set()
        result = await self.finish()
        self.assertEqual(self.driver.commands, [])
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(result["error"], "OPERATOR_STOP")

    async def test_stop_during_motion_never_dispatches_return_or_second_motion(self):
        entered, release = threading.Event(), threading.Event()
        def blocking(_primitive, _command):
            entered.set()
            release.wait(3.)
        self.driver.execute_hook = blocking
        await self.service.start(command_for(self.service, self.store))
        await event_seen(entered)
        await self.service.stop({"request_id": str(uuid4()), "expected_revision": 0})
        release.set()
        result = await self.finish()
        self.assertEqual([p for p, _ in self.driver.commands], ["delivery-unit"])
        self.assertEqual(result["state"], "HOLD")
        self.assertIn("OPERATOR_STOP", self.driver.holds)

    async def test_execute_connection_failure_has_no_retry(self):
        self.driver.execute_error = ConnectionError("Synthetic lost receipt after dispatch")
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(len(self.driver.commands), 1)
        self.assertEqual(result["error"], "PHYSICAL_MISSION_INTERRUPTED")

    async def test_readonly_provider_failures_are_finite_without_motion_retry(self):
        self.driver.observe_error = TimeoutError("Synthetic model unavailable")
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(self.driver.observations, 3)
        self.assertEqual(self.driver.commands, [])

    async def test_context_connection_failure_before_first_action_holds(self):
        self.driver.context_error_at = 2
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(self.driver.commands, [])

    async def test_crash_record_reopens_held_without_replay_or_poll_reset(self):
        self.service.status.update(state="MOVING", mission_id="old-mission")
        self.service._persist("SYNTHETIC_CRASH_INTENT", {"command_id": "never-replay"})
        await self.service.close()
        self.service = PhysicalMissionService(self.store, self.temp.name, driver=self.driver, poll_interval_s=.001)
        snapshot = await self.service.refresh_readiness()
        self.assertEqual(snapshot["state"], "HOLD")
        self.assertEqual(snapshot["error"], "RESTART_REQUIRES_RECONCILIATION")
        self.assertIsNone(self.service.task)
        self.assertEqual(self.driver.commands, [])
        with self.assertRaises(CommandError):
            await self.service.start(command_for(self.service, self.store))

    async def test_second_owner_cannot_open_same_physical_state(self):
        with self.assertRaises(Exception) as raised:
            PhysicalMissionService(self.store, self.temp.name, driver=self.driver)
        self.assertEqual(getattr(raised.exception, "code", None), "SERVICE_OWNED")

    async def test_removed_release_clears_persisted_runtime_readiness(self):
        ready = await self.service.refresh_readiness()
        self.assertTrue(ready["available"])
        self.service._persist("SYNTHETIC_READY")
        await self.service.close()
        self.service = PhysicalMissionService(self.store, self.temp.name)
        for status in (self.service.snapshot(), await self.service.refresh_readiness()):
            self.assertEqual(status["state"], "DISABLED")
            self.assertFalse(status["enabled"])
            self.assertFalse(status["available"])
            self.assertEqual(status["capabilities"], {})
            self.assertEqual(status["robot"], {"connected": False, "stationary": False, "at_start": False})
            self.assertTrue(status["blockers"])
        with self.assertRaises(CommandError):
            await self.service.start(command_for(self.service, self.store))
        self.assertEqual(self.driver.commands, [])

    async def test_removed_release_preserves_completed_delivery_history(self):
        await self.service.start(command_for(self.service, self.store))
        completed = await self.finish()
        await self.service.refresh_readiness()
        self.service._persist("SYNTHETIC_COMPLETE_READY")
        await self.service.close()
        self.service = PhysicalMissionService(self.store, self.temp.name)
        status = await self.service.refresh_readiness()
        self.assertEqual(status["state"], "COMPLETE")
        self.assertEqual(status["mission_id"], completed["mission_id"])
        self.assertEqual(status["car"], completed["car"])
        self.assertFalse(status["enabled"])
        self.assertFalse(status["available"])
        self.assertEqual(status["capabilities"], {})
        self.assertFalse(status["robot"]["connected"])
        self.assertFalse(status["robot"]["at_start"])
        self.assertIsNone(self.service.task)

    async def test_removed_release_preserves_crash_reconciliation_hold(self):
        await self.service.refresh_readiness()
        self.service.status.update(state="RETURNING_HOME", mission_id="interrupted-mission", returning_home=True)
        self.service._persist("SYNTHETIC_CRASH_INTENT")
        await self.service.close()
        self.service = PhysicalMissionService(self.store, self.temp.name)
        status = await self.service.refresh_readiness()
        self.assertEqual(status["state"], "HOLD")
        self.assertEqual(status["error"], "RESTART_REQUIRES_RECONCILIATION")
        self.assertEqual(status["mission_id"], "interrupted-mission")
        self.assertFalse(status["enabled"])
        self.assertFalse(status["available"])
        self.assertFalse(status["returning_home"])
        self.assertEqual(status["capabilities"], {})
        self.assertEqual(self.driver.commands, [])

    async def test_signal_red_wait_then_recontact_entry_recheck_and_return(self):
        await self.service.close()
        self.driver = FakeMeasuredDriver(plan(signal=True))
        self.driver.signal_colors = ["RED", "UNKNOWN", "GREEN", "GREEN", "GREEN", "GREEN"]
        self.service = PhysicalMissionService(self.store, self.temp.name, driver=self.driver,
                                             poll_interval_s=.001, clock=lambda: self.driver.now)
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual([p for p, _ in self.driver.commands], ["approach-unit", "recontact", "crossing-unit", "return"])
        self.assertGreaterEqual(self.driver.observations, 8)
        reasons = [json.loads(row[0])["decision"]["reason"] for row in self.service.db.execute(
            "SELECT value FROM events WHERE kind='POLICY_DECISION' ORDER BY seq")]
        self.assertIn("WAIT_RED", reasons)
        self.assertIn("WAIT_UNKNOWN", reasons)
        self.assertIn("WAIT_SECOND_EXCLUSIVE_GREEN_FRAME", reasons)
        self.assertIn("ENTRY_WAIT_SECOND_EXCLUSIVE_GREEN_FRAME", reasons)

    async def test_telemetry_waits_for_native_receipts_and_counts_empty_return(self):
        entered, release = threading.Event(), threading.Event()
        def blocking(_primitive, _command):
            if len(self.driver.commands) == 1:
                entered.set()
                release.wait(3.)
        self.driver.execute_hook = blocking
        accepted = await self.service.start(command_for(self.service, self.store))
        self.assertEqual(accepted["progress"], {"completed": 0, "total": 2})
        await event_seen(entered)
        current = self.service.snapshot()
        self.assertEqual(current["progress"], {"completed": 0, "total": 2})
        self.assertEqual([row["status"] for row in current["telemetry"]["sequence"]], ["current", "pending"])
        self.assertFalse(current["car"]["arrived"])
        self.assertFalse(any(row["source"] == "native" for row in current["telemetry"]["history"]))
        release.set()
        result = await self.finish()
        self.assertEqual(result["progress"], {"completed": 2, "total": 2})
        self.assertEqual([row["status"] for row in result["telemetry"]["sequence"]], ["complete", "complete"])
        self.assertEqual([row["detail"] for row in result["telemetry"]["history"] if row["source"] == "native"],
                         ["delivery-unit", "return"])
        self.assertIsNone(result["telemetry"]["distance_mm"])
        self.assertIsNone(result["telemetry"]["distance_source"])

    async def test_unverified_receipt_holds_row_without_fabricating_completion(self):
        execute = self.driver.execute
        def unverified(primitive, command):
            return replace(execute(primitive, command), native_verified=False)
        self.driver.execute = unverified
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(result["progress"], {"completed": 0, "total": 2})
        self.assertEqual([row["status"] for row in result["telemetry"]["sequence"]], ["held", "pending"])
        self.assertEqual(result["telemetry"]["current_step_id"], "delivery-unit")
        self.assertFalse(any(row["source"] == "native" for row in result["telemetry"]["history"]))
        self.assertEqual(len(self.driver.commands), 1)

    async def test_delivery_only_arrival_does_not_claim_alignment(self):
        self.driver.plan = replace(self.driver.plan, parking=ParkingTarget(0., mode="delivery_only"))
        observe = self.driver.observe
        def skewed(state):
            result = observe(state)
            if result.get("car"):
                result["car"] = replace(result["car"], heading_deg=35., heading_matches_expected=False)
            return result
        self.driver.observe = skewed
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "COMPLETE")
        self.assertTrue(result["car"]["arrived"])
        self.assertFalse(result["car"]["aligned"])
        self.assertIsNone(result["car"]["heading_error_deg"])
        self.assertEqual(result["progress"], {"completed": 2, "total": 2})
        self.assertEqual([primitive for primitive, _ in self.driver.commands], ["delivery-unit", "return"])

    async def test_simulator_completion_signal_and_review_never_fill_physical_telemetry(self):
        self.store.state.update(current_step=99, progress={"completed": 99, "total": 99},
            events=[{"source": "simulation", "title": "Fake arrival"}],
            signal={"source": "simulation", "color": "GREEN"},
            review={"source": "demo", "verdict": "PASS", "summary": "Fake arrival"})
        self.driver.observe_error = TimeoutError("No actual observation")
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(result["progress"], {"completed": 0, "total": 2})
        self.assertEqual(result["signal"]["color"], "UNKNOWN")
        self.assertIsNone(result["telemetry"]["review"])
        self.assertIsNone(result["telemetry"]["signal_observed_at"])
        self.assertFalse(any(row["source"] in {"simulation", "demo", "meta", "native"}
                             for row in result["telemetry"]["history"]))
        self.assertNotIn("Fake arrival", json.dumps(result))

    async def test_failed_car_review_preserves_endpoint_but_does_not_complete_delivery(self):
        observe = self.driver.observe
        def failed(state):
            result = observe(state)
            if result.get("car"):
                result["car"] = replace(result["car"], verdict="FAIL", arrived=False)
                result["summary"] = "Actual review reports the car outside its target."
            return result
        self.driver.observe = failed
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "HOLD")
        self.assertEqual(result["progress"], {"completed": 1, "total": 2})
        self.assertEqual([row["status"] for row in result["telemetry"]["sequence"]], ["complete", "pending"])
        self.assertFalse(result["car"]["arrived"])
        self.assertEqual(result["telemetry"]["review"]["verdict"], "FAIL")
        self.assertEqual(result["telemetry"]["review"]["source"], "meta")
        self.assertEqual([p for p, _ in self.driver.commands], ["delivery-unit"])

    async def test_post_stop_inference_does_not_publish_late_arrival_or_review(self):
        entered, release = threading.Event(), threading.Event()
        def blocking(state):
            if state.phase == Phase.OBSERVE:
                entered.set()
                release.wait(3.)
        self.driver.observe_hook = blocking
        await self.service.start(command_for(self.service, self.store))
        await event_seen(entered)
        self.assertTrue(self.service.snapshot()["vision"]["in_flight"])
        await self.service.stop({"request_id": str(uuid4()), "expected_revision": 0})
        release.set()
        result = await self.finish()
        self.assertEqual(result["state"], "HOLD")
        self.assertFalse(result["vision"]["in_flight"])
        self.assertIsNone(result["telemetry"]["review"])
        self.assertFalse(result["car"]["arrived"])
        self.assertEqual([p for p, _ in self.driver.commands], ["delivery-unit"])

    async def test_queued_signal_frames_update_actual_telemetry_without_extra_inference(self):
        await self.service.close()
        self.driver = FakeMeasuredDriver(plan(signal=True))
        self.service = PhysicalMissionService(self.store, self.temp.name, driver=self.driver,
            poll_interval_s=.001, clock=lambda: self.driver.now)
        observe = self.driver.observe
        pairs, captures, snapshots = [], [], []
        def paired(state):
            if state.phase not in {Phase.WAIT_SIGNAL, Phase.ENTRY_SIGNAL}:
                return observe(state)
            pairs.append(state.phase)
            samples = []
            for index in range(2):
                self.driver.now += .3
                at = context(self.driver.where, self.driver.now, self.driver.seq)
                step = self.driver.plan.steps[state.step_index]
                digest = hashlib.sha256(f"{len(pairs)}-{index}".encode()).hexdigest()
                samples.append({"car": replace(car(at, state, step=step.id, zone=step.car_zone_id,
                    heading_deg=step.expected_heading_deg), image_sha256=digest),
                    "signal": replace(signal(at), image_sha256=digest), "summary": "Actual paired signal review"})
                captures.append(at.now_s)
            return {**samples[-1], "samples": samples}
        self.driver.observe = paired
        persist = self.service._persist
        def record(kind, evidence=None):
            persist(kind, evidence)
            if kind == "QUEUED_OBSERVATION_SELECTED":
                snapshots.append(self.service.snapshot())
        self.service._persist = record
        await self.service.start(command_for(self.service, self.store))
        result = await self.finish()
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual(pairs, [Phase.WAIT_SIGNAL, Phase.ENTRY_SIGNAL])
        self.assertEqual([s["telemetry"]["signal_observed_at"] for s in snapshots], captures)
        self.assertTrue(all(s["signal"]["color"] == "GREEN" and not s["vision"]["in_flight"] for s in snapshots))
        self.assertTrue(all(s["telemetry"]["review"]["observed_at"] == s["telemetry"]["signal_observed_at"] for s in snapshots))
        rows = result["telemetry"]["sequence"]
        self.assertEqual([row["id"] for row in rows], ["approach-unit", "recontact", "crossing-unit", "return"])
        self.assertTrue(all(row["status"] == "complete" for row in rows))
        self.assertEqual(result["progress"], {"completed": 4, "total": 4})
        self.assertEqual(len([row for row in result["telemetry"]["history"] if row["kind"] == "signal"]), 4)

    async def test_status_copy_cannot_mutate_service(self):
        snapshot = self.service.snapshot()
        snapshot["car"]["arrived"] = True
        snapshot["state"] = "COMPLETE"
        self.assertFalse(self.service.snapshot()["car"]["arrived"])
        self.assertEqual(self.service.snapshot()["state"], "READY")


class PhysicalApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.store, self.driver = FakeWorkspace(), FakeMeasuredDriver()
        self.service = PhysicalMissionService(self.store, self.temp.name, driver=self.driver, poll_interval_s=.001)
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.physical = self.service
        @self.app.exception_handler(CommandError)
        async def command_error(_request, error):
            return JSONResponse({"detail": error.message}, status_code=error.status)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.service.close()
        self.temp.cleanup()

    async def test_same_origin_start_runs_and_status_is_read_only(self):
        initial = await self.client.get("/api/v1/physical/status")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(self.driver.commands, [])
        response = await self.client.post("/api/v1/physical/start", headers={"origin": "http://testserver"},
                                          json=command_for(self.service, self.store))
        self.assertEqual(response.status_code, 200)
        await asyncio.wait_for(self.service.task, 3.)

    async def test_cross_origin_and_missing_origin_cannot_start_or_stop(self):
        command = command_for(self.service, self.store)
        for headers in ({}, {"origin": "http://attacker"}, {"origin": "https://testserver"},
                        {"origin": "http://testserver:9999"},
                        {"origin": "http://testserver", "sec-fetch-site": "cross-site"}):
            for route, payload in (("start", command), ("stop", {"request_id": str(uuid4()), "expected_revision": 0})):
                with self.subTest(headers=headers, route=route):
                    response = await self.client.post("/api/v1/physical/" + route, headers=headers, json=payload)
                    self.assertEqual(response.status_code, 403)
        self.assertEqual(self.driver.commands, [])

    async def test_raw_coordinate_or_extra_hardware_fields_rejected(self):
        command = command_for(self.service, self.store, tcp=[1, 2, 3, 4, 5, 6])
        response = await self.client.post("/api/v1/physical/start", headers={"origin": "http://testserver"}, json=command)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.driver.commands, [])


if __name__ == "__main__":
    unittest.main()
