"""No-equipment service checks for explicit continuation after completed C4.

The fake reviewer calls the real narrow state/receipt candidate validator. No
robot, camera, model provider, background mission or network is constructed.
"""
from dataclasses import asdict, replace
import json
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from backend.core import CommandError
from backend.physical_mission import PhysicalMissionService
from backend.robot_control.completed_native_resume import candidate
from backend.robot_control.mission_policy import MissionState, Phase, RouteStep, TaughtPrimitive
from tests import test_mission_policy as policy_fixtures
from tests import test_physical_mission as service_fixtures


def c4_plan():
    original = policy_fixtures.plan()
    contexts = ("START", "C1", "C2", "C3", "C4", "GOAL_PARK")
    steps = tuple(RouteStep(f"C-step-{i}", TaughtPrimitive(f"c{i}-unit", contexts[i-1], contexts[i],
        "b"*64, False, False, release_mode="site_trial", current_site_review_sha256="c"*64),
        "GOAL" if i == 5 else "FRONTAGE", 0., at_goal=i == 5,
        review_mode="expected_outcome" if i == 5 else "intermediate_progress") for i in range(1, 6))
    return replace(original, destination="VILLA", release_mode="site_trial", steps=steps,
        parking=replace(original.parking, mode="delivery_only"),
        empty_return=tuple(replace(p, qualified=False, release_mode="site_trial",
            current_site_review_sha256="c"*64) for p in original.empty_return))


class NativeResumeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.plan = c4_plan()
        self.store = service_fixtures.FakeWorkspace()
        self.store.state["goal"]["destination"] = "VILLA"
        self.store.state["plan"]["route"].update(destination="VILLA", node_ids=["START", "VILLA"])
        self.driver = service_fixtures.FakeMeasuredDriver(self.plan)
        self.now = 100.
        self.service = PhysicalMissionService(self.store, self.temp.name, driver=self.driver,
            clock=lambda: self.now)
        self.workspace = service_fixtures.command_for(self.service, self.store)
        self.completed = MissionState(self.plan.id, "session", phase=Phase.OBSERVE, step_index=3,
            action_command_id="completed-c4", last_motion_completed_at_s=140., start_verified=True,
            issued_command_ids=("completed-c1", "completed-c2", "completed-c3", "completed-c4"), reason="ROUTE")
        self.receipt = {"command_id": "completed-c4", "primitive_id": "c4-unit", "session_id": "session",
            "target_context_id": "C4", "completed_at_s": 140., "native_verified": True, "outcome": "COMPLETED"}
        self.service.status.update(state="HOLD", mission_id=self.plan.id, error="PHYSICAL_STATUS_REQUIRED")
        self.service._persist("MISSION_ACCEPTED", {"workspace": self.workspace, "policy": asdict(self.plan)})
        self.now = 110.
        self.service._persist("PRIMITIVE_DISPATCH_INTENT", {"primitive": "c4-unit", "command_id": "completed-c4"})
        self.now = 140.
        self.service._persist("PRIMITIVE_RECEIPT", {"receipt": self.receipt, "state": asdict(self.completed)})
        self.now = 150.
        self.service._persist("MISSION_INTERRUPTED", {"exception_type": "ExecutionBlocked", "state": asdict(self.completed)})
        self.preparations, self.started = [], []
        def prepare(workspace, old, interrupted, completed, receipt, **kwargs):
            self.preparations.append((workspace, old, interrupted, completed, receipt, kwargs))
            plan, state = candidate(old, self.plan, interrupted, completed, receipt)
            return plan, state, {"summary": "Synthetic fresh C4 progress review."}, {
                "motion_issued": False, "command_replayed": False, "native_interruption": True,
                "next_step": "C-step-5"}
        self.driver.resume_review = prepare
        async def worker(policy, state, workspace, **kwargs):
            self.started.append((policy.plan, state, workspace, kwargs))
        self.service._run = worker

    async def asyncTearDown(self):
        await self.service.close()
        self.temp.cleanup()

    def command(self, **changes):
        return {"request_id": str(uuid4()), "expected_revision": self.service.status["revision"],
            "mission_id": self.plan.id, "reason": "Explicitly continue after completed C4.", **changes}

    def rewrite_receipt(self, **changes):
        row = self.service.db.execute("SELECT seq,value FROM events WHERE kind='PRIMITIVE_RECEIPT'").fetchone()
        value = json.loads(row[1])
        value["receipt"].update(changes)
        with self.service.db:
            self.service.db.execute("UPDATE events SET value=? WHERE seq=?", (json.dumps(value), row[0]))

    async def test_explicit_resume_selects_interruption_receipt_and_original_capture_lower_bound(self):
        # A separate review-hold event must not replace the interrupted C4 state.
        self.service._persist("MISSION_HELD", {"state": asdict(replace(self.completed,
            phase=Phase.FAILED, reason="unrelated historical visual review"))})
        self.assertIsNone(self.service.task)
        self.assertEqual(self.started, [])
        request = self.command()
        result = await self.service.resume(request)
        await self.service.task
        self.assertEqual(result["state"], "OBSERVING")
        self.assertEqual(len(self.preparations), 1)
        _, old, interrupted, completed, receipt, kwargs = self.preparations[0]
        self.assertEqual(old, self.plan)
        self.assertEqual(interrupted, self.completed)
        self.assertEqual(completed, self.completed)
        self.assertEqual(receipt, self.receipt)
        self.assertEqual(kwargs, {"native_interruption": True, "capture_after_s": 110.})
        self.assertEqual(self.started[0][1].phase, Phase.OBSERVE)
        self.assertEqual(self.started[0][1].step_index, 3)  # C4 review, never replay C4.
        self.assertEqual(self.started[0][1].issued_command_ids, self.completed.issued_command_ids)
        self.assertEqual(self.driver.commands, [])
        self.assertEqual(await self.service.resume(request), result)
        self.assertEqual(len(self.started), 1)
        original = json.loads(self.service.db.execute(
            "SELECT value FROM events WHERE kind='MISSION_INTERRUPTED'").fetchone()[0])
        self.assertEqual(original["state"], json.loads(json.dumps(asdict(self.completed))))

    async def test_any_dispatch_after_completed_receipt_prevents_native_resume(self):
        self.service._persist("PRIMITIVE_DISPATCH_INTENT", {"primitive": "later", "command_id": "later-command"})
        with self.assertRaises(CommandError):
            await self.service.resume(self.command())
        self.assertEqual(self.preparations, [])
        self.assertIsNone(self.service.task)
        self.assertEqual(self.driver.commands, [])

    async def test_missing_matching_original_dispatch_rejects_capture_interval(self):
        with self.service.db:
            self.service.db.execute("UPDATE events SET value=? WHERE kind='PRIMITIVE_DISPATCH_INTENT'",
                (json.dumps({"primitive": "c4-unit", "command_id": "foreign-command"}),))
        with self.assertRaises(CommandError):
            await self.service.resume(self.command())
        self.assertEqual(self.preparations, [])
        self.assertIsNone(self.service.task)

    async def test_unknown_completed_receipt_is_preserved_and_does_not_launch_worker(self):
        self.rewrite_receipt(outcome="UNKNOWN")
        with self.assertRaises(CommandError):
            await self.service.resume(self.command())
        self.assertIsNone(self.service.task)
        self.assertEqual(self.service.status["state"], "HOLD")
        self.assertEqual(self.service.status["error"], "PHYSICAL_STATUS_REQUIRED")
        saved = json.loads(self.service.db.execute("SELECT value FROM events WHERE kind='PRIMITIVE_RECEIPT'").fetchone()[0])
        self.assertEqual(saved["receipt"]["outcome"], "UNKNOWN")
        self.assertEqual(self.driver.commands, [])

    async def test_wrong_error_or_review_omission_cannot_use_native_recovery(self):
        for error, changes in (("ROBOT_NOT_COMPLETE", {}), ("OPERATOR_STOP", {}),
                               ("PHYSICAL_STATUS_REQUIRED", {"omit_c19_review": True})):
            self.service.status["error"] = error
            with self.subTest(error=error), self.assertRaises(CommandError):
                await self.service.resume(self.command(**changes))
        self.assertEqual(self.preparations, [])
        self.assertIsNone(self.service.task)

    async def test_stop_during_native_preparation_keeps_original_failure_and_no_worker(self):
        prepare = self.driver.resume_review
        def stopped(*args, **kwargs):
            result = prepare(*args, **kwargs)
            self.service.stop_generation += 1
            return result
        self.driver.resume_review = stopped
        with self.assertRaises(CommandError):
            await self.service.resume(self.command())
        self.assertIsNone(self.service.task)
        self.assertEqual(self.service.status["state"], "HOLD")
        self.assertEqual(self.service.status["error"], "PHYSICAL_STATUS_REQUIRED")
        self.assertEqual(self.started, [])
        self.assertEqual(self.driver.commands, [])


if __name__ == "__main__":
    unittest.main()
