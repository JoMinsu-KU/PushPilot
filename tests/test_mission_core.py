"""Offline mission gates: no credentials, provider calls, or hardware required."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from backend.core import CommandError, WorkspaceStore
from backend.meta import ProviderError


class FakeProvider:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def interpret(self, text):
        self.calls += 1
        if self.fail:
            raise ProviderError("The provider is unavailable.")
        return {"destination": "BAKERY", "requires_clarification": False, "summary": "Push to symbolic BAKERY."}


class MissionCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "state.sqlite3")
        self.now = 1_800_000_000.0
        self.provider = FakeProvider()
        self.store = self.open_store()

    def open_store(self):
        return WorkspaceStore(self.path, provider=self.provider, clock=lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def command(self, action, **extra):
        payload = {"request_id": str(uuid4()), "expected_revision": self.store.snapshot()["revision"], **extra}
        result, status = self.store.execute(action, payload)
        self.assertEqual(status, 200)
        return result

    def prepare(self):
        state = self.command("goals", text="Take the car to the bakery.", provider="demo", source="typed")
        return self.command("approve", plan_id=state["plan"]["id"], plan_revision=state["plan"]["revision"])

    def pass_review(self):
        return self.command("reviews", review_id=self.store.snapshot()["review"]["id"], verdict="PASS")

    def stop_review(self):
        self.prepare()
        self.command("advance")
        self.pass_review()
        return self.command("advance")

    def test_approval_requires_current_plan_identity_and_version(self):
        state = self.command("goals", text="bakery", provider="demo")
        with self.assertRaises(CommandError):
            self.command("approve", plan_id=str(uuid4()), plan_revision=state["plan"]["revision"])
        with self.assertRaises(CommandError):
            self.command("approve", plan_id=state["plan"]["id"], plan_revision=999)
        self.assertEqual(self.store.snapshot()["state"], "PLAN_READY")

    def test_action_cannot_skip_pending_review(self):
        self.prepare()
        state = self.command("advance")
        self.assertEqual(state["state"], "REVIEW_REQUIRED")
        with self.assertRaises(CommandError):
            self.command("advance")
        self.assertEqual(self.store.snapshot()["current_step"], 0)

    def test_fresh_green_still_requires_mandatory_stop_and_accepted_review(self):
        self.prepare()
        self.command("signal", color="GREEN")
        self.command("advance")
        self.pass_review()
        state = self.command("advance")
        self.assertTrue(state["stopped"])
        self.assertEqual(state["current_step"], 1)
        self.assertFalse(any(e["kind"] == "CROSSING_ADMITTED" for e in state["events"]))
        state = self.pass_review()
        self.assertEqual(state["current_step"], 2)
        self.assertEqual(state["state"], "REVIEW_REQUIRED")
        stops = [e["sequence"] for e in state["events"] if e["title"] == "Simulated stop completed"]
        admitted = [e["sequence"] for e in state["events"] if e["kind"] == "CROSSING_ADMITTED"]
        self.assertLess(stops[0], admitted[0])

    def test_red_wait_and_fresh_green_automatically_admit_one_crossing(self):
        self.stop_review()
        self.command("signal", color="RED")
        state = self.pass_review()
        self.assertEqual(state["state"], "WAITING_SIGNAL")
        state = self.command("signal", color="GREEN")
        self.assertEqual(state["state"], "REVIEW_REQUIRED")
        self.assertEqual(state["current_step"], 2)
        self.assertEqual(sum(e["kind"] == "CROSSING_ADMITTED" for e in state["events"]), 1)
        self.command("signal", color="GREEN")
        self.assertEqual(sum(e["kind"] == "CROSSING_ADMITTED" for e in self.store.snapshot()["events"]), 1)

    def test_unknown_signal_inhibits_crossing(self):
        self.stop_review()
        self.command("signal", color="UNKNOWN")
        state = self.pass_review()
        self.assertEqual(state["state"], "WAITING_SIGNAL")
        self.assertEqual(state["current_step"], 1)

    def test_stale_green_does_not_authorize_entry(self):
        self.stop_review()
        self.command("signal", color="GREEN")
        self.now += 31
        state = self.pass_review()
        self.assertEqual(state["state"], "WAITING_SIGNAL")
        self.assertIn("SIGNAL_STALE", [e["kind"] for e in state["events"]])

    def test_clock_rollback_cannot_freshen_a_future_observation(self):
        self.stop_review()
        self.command("signal", color="GREEN")
        self.now -= 1
        self.assertEqual(self.pass_review()["state"], "WAITING_SIGNAL")

    def test_later_red_does_not_revoke_admitted_crossing(self):
        self.stop_review()
        self.pass_review()
        self.command("signal", color="GREEN")
        state = self.command("signal", color="RED")
        self.assertEqual(state["state"], "REVIEW_REQUIRED")
        self.assertEqual(state["current_step"], 2)
        self.assertEqual(self.pass_review()["state"], "READY")

    def test_complete_mission_with_all_route_action_reviews(self):
        self.stop_review()
        self.pass_review()
        self.command("signal", color="GREEN")
        for _ in range(30):
            state = self.store.snapshot()
            if state["state"] == "COMPLETED":
                break
            if state["state"] == "REVIEW_REQUIRED":
                self.pass_review()
            elif state["state"] == "READY":
                self.command("advance")
            elif state["state"] == "WAITING_SIGNAL":
                self.command("signal", color="GREEN")
            else:
                self.fail(f"Unexpected mission state: {state['state']}")
        self.assertEqual(state["state"], "COMPLETED")
        self.assertFalse(state["approved"])
        self.assertTrue(all(step["status"] == "complete" for step in state["plan"]["steps"]))
        self.assertEqual(len([e for e in state["events"] if e["kind"] == "DEMO_REVIEW_RECORDED"]), 8)

    def test_uncertainty_requires_new_review_binding_without_rerunning_motion(self):
        self.prepare()
        first = self.command("advance")
        state = self.command("reviews", review_id=first["review"]["id"], verdict="UNKNOWN")
        self.assertEqual(state["state"], "REOBSERVE")
        state = self.command("reobserve")
        self.assertNotEqual(first["review"]["id"], state["review"]["id"])
        self.assertEqual(sum(e["kind"] == "SIMULATED_ACTION_COMPLETED" for e in state["events"]), 1)
        with self.assertRaises(CommandError):
            self.command("reviews", review_id=first["review"]["id"], verdict="PASS")

    def test_failure_faults_and_prevents_advance(self):
        self.prepare()
        state = self.command("advance")
        state = self.command("reviews", review_id=state["review"]["id"], verdict="FAIL")
        self.assertEqual(state["state"], "FAULT")
        self.assertFalse(state["approved"])
        with self.assertRaises(CommandError):
            self.command("advance")

    def test_request_replay_returns_original_receipt_and_reuse_rejects_changed_payload(self):
        payload = {"request_id": str(uuid4()), "expected_revision": 0, "text": "bakery", "provider": "demo"}
        first, _ = self.store.execute("goals", payload)
        second, _ = self.store.execute("goals", payload)
        self.assertEqual(first, second)
        self.assertEqual(self.store.snapshot()["revision"], 1)
        with self.assertRaises(CommandError):
            self.store.execute("goals", {**payload, "text": "different bakery"})

    def test_stale_revision_rejects_without_changing_state(self):
        self.command("goals", text="bakery", provider="demo")
        with self.assertRaises(CommandError):
            self.store.execute("reset", {"request_id": str(uuid4()), "expected_revision": 0})
        self.assertEqual(self.store.snapshot()["state"], "PLAN_READY")

    def test_restart_clears_authority_and_never_replays_a_pending_action(self):
        self.stop_review()
        self.pass_review()
        self.command("signal", color="GREEN")
        old = self.store.snapshot()
        self.store.close()
        self.store = self.open_store()
        state = self.store.snapshot()
        self.assertEqual(state["state"], "RECOVERY_REQUIRED")
        self.assertFalse(state["approved"])
        self.assertFalse(state["stopped"])
        self.assertIsNone(state["review"])
        self.assertEqual(state["signal"]["color"], "UNKNOWN")
        self.assertEqual(sum(e["kind"] == "SIMULATED_ACTION_COMPLETED" for e in old["events"]),
                         sum(e["kind"] == "SIMULATED_ACTION_COMPLETED" for e in state["events"]))
        with self.assertRaises(CommandError):
            self.command("advance")
        self.assertEqual(self.command("reset")["state"], "IDLE")

    def test_new_goal_and_reset_cannot_replace_active_or_waiting_mission(self):
        self.stop_review()
        self.pass_review()
        for source in ("typed", "voice"):
            with self.assertRaises(CommandError):
                self.command("goals", text="bakery", provider="demo", source=source)
        with self.assertRaises(CommandError):
            self.command("reset")
        self.command("cancel")
        with self.assertRaises(CommandError):
            self.command("goals", text="bakery", provider="demo")
        self.assertEqual(self.command("reset")["state"], "IDLE")

    def test_provider_failure_is_recorded_without_demo_fallback(self):
        self.provider.fail = True
        payload = {"request_id": str(uuid4()), "expected_revision": 0, "text": "bakery", "provider": "meta"}
        response, status = self.store.execute("goals", payload)
        self.assertEqual(status, 502)
        self.assertIn("No plan", response["detail"])
        state = self.store.snapshot()
        self.assertIsNone(state["plan"])
        self.assertEqual(state["state"], "IDLE")
        self.assertEqual(state["events"][-1]["source"], "meta")
        self.store.execute("goals", payload)
        self.assertEqual(self.provider.calls, 1)

    def test_failed_goal_replacement_invalidates_the_old_plan(self):
        old = self.command("goals", text="bakery", provider="demo")
        self.provider.fail = True
        payload = {"request_id": str(uuid4()), "expected_revision": old["revision"], "text": "bakery", "provider": "meta"}
        self.assertEqual(self.store.execute("goals", payload)[1], 502)
        self.assertIsNone(self.store.snapshot()["plan"])
        with self.assertRaises(CommandError):
            self.command("approve", plan_id=old["plan"]["id"], plan_revision=old["plan"]["revision"])

    def test_evidence_retained_across_reset_and_sources_are_explicit(self):
        self.prepare()
        self.command("advance")
        self.pass_review()
        self.command("cancel")
        before = self.store.snapshot()["events"]
        state = self.command("reset")
        self.assertEqual(state["events"][:-1], before)
        self.assertEqual([e["sequence"] for e in state["events"]], list(range(1, len(state["events"]) + 1)))
        self.assertTrue(any(e["source"] == "demo" for e in state["events"]))
        self.assertFalse(state["capabilities"]["robot"])
        self.assertTrue(state["capabilities"]["recorded_action_review"])
        self.assertTrue(state["capabilities"]["image_review"])


if __name__ == "__main__":
    unittest.main()
