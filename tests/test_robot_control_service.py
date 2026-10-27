"""Equipment-free commissioning API, crash recovery and dispatch failure tests.

All dimensions, identities and image hashes below are synthetic. The mock's
internal motion flag exercises admission policy, never a hardware capability.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.robot_control.api import create_app
from backend.robot_control.gates import admit
from backend.robot_control.legacy import OutcomeUnknown
from backend.robot_control.mock import MockReceiver
from backend.robot_control.service import RobotService
from backend.robot_control.store import ControlError, Journal


TOKEN = "synthetic-test-token-not-a-production-secret"
HEADERS = {"X-PushPilot-Control-Token": TOKEN}


class TestClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds=1):
        self.value += seconds


class BeforePublicationReceiver(MockReceiver):
    """Suspend immediately before the service's final publication admission."""
    def __init__(self):
        super().__init__()
        self.reached = threading.Event()
        self.release = threading.Event()

    def execute(self, command, on_event):
        self.reached.set()
        if not self.release.wait(3):
            raise RuntimeError("Test publication gate timed out.")
        return super().execute(command, on_event)


class AfterPublicationReceiver(MockReceiver):
    """Suspend a published command until the test releases its completion."""
    def __init__(self):
        super().__init__()
        self.reached = threading.Event()
        self.release = threading.Event()

    def execute(self, command, on_event):
        def gate(kind, data):
            on_event(kind, data)
            if kind == "published":
                self.reached.set()
                if not self.release.wait(3):
                    raise RuntimeError("Test completion gate timed out.")
        return super().execute(command, gate)


class AfterCommitReceiver(MockReceiver):
    """Pause after durable admission but before the simulated mailbox publish."""
    def __init__(self):
        super().__init__()
        self.reached = threading.Event()
        self.release = threading.Event()

    def execute(self, command, on_event):
        def gate(kind, data):
            on_event(kind, data)
            if kind == "publication_intent":
                self.reached.set()
                if not self.release.wait(3):
                    raise RuntimeError("Test committed-publication gate timed out.")
        return super().execute(command, gate)


class RobotControlServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "control.sqlite3"
        self.clock = TestClock()
        self.receiver = MockReceiver()
        self.journal = Journal(self.path, clock=self.clock)
        self.service = RobotService(self.journal, self.receiver, clock=self.clock)
        self.client = None
        self.installation = {
            "installation_id": "synthetic-installation", "map_id": "synthetic-map",
            "map_hash": "1" * 64, "calibration_id": "synthetic-calibration",
            "tcp_id": "mock-tcp", "tool_id": "mock-tool",
            "review_reference": "Synthetic test fixture; no physical qualification.",
            "qualified": True, "workspace_min_mm": [-500, -500, 0],
            "workspace_max_mm": [500, 500, 500], "min_tcp_z_mm": 10,
            "raised_tcp_z_mm": 120, "max_step_mm": 30, "max_speed_mm_s": 15,
            "max_accel_mm_s2": 30, "observation_max_age_seconds": 10,
            "camera_epoch": "synthetic-epoch", "registration_id": "synthetic-registration",
        }
        self.addCleanup(self.close)

    def close(self):
        release = getattr(self.receiver, "release", None)
        if release:
            release.set()
        if self.client:
            self.client.__exit__(None, None, None)
            self.client = None
        self.journal.close()

    def start(self, receiver=None):
        if receiver is not None:
            self.receiver = receiver
            self.service = RobotService(self.journal, receiver, clock=self.clock)
        self.client = TestClient(create_app(self.service, TOKEN))
        self.client.__enter__()
        return self.client

    def binding(self):
        state = self.receiver.snapshot()
        return {key: state[key] for key in ("session_id", "seq", "profile_id")}

    def post(self, path, value):
        return self.client.post(path, headers=HEADERS, json=value)

    def get(self, path):
        return self.client.get(path, headers=HEADERS)

    def configure(self):
        response = self.post("/v1/installation", self.installation)
        self.assertEqual(response.status_code, 200, response.text)
        response = self.post("/v1/arm", {"installation_id": self.installation["installation_id"],
                             "expected_receiver": self.binding(), "reason": "Synthetic fixture explicitly armed."})
        self.assertEqual(response.status_code, 200, response.text)

    def command(self, **overrides):
        return {"request_id": str(uuid4()), "kind": "translate", "purpose": "commissioning",
                "installation_id": self.installation["installation_id"], "expected_receiver": self.binding(),
                "target": [5, 0, 100, 180, 0, 0], "timeout_seconds": 3,
                "admission_timeout_seconds": 30, **overrides}

    def observation(self, **overrides):
        key = uuid4().hex
        return {**{key: self.installation[key] for key in (
            "installation_id", "map_id", "map_hash", "calibration_id", "camera_epoch", "registration_id")},
                "observation_id": str(uuid4()), "source": "operator", "frame_id": "synthetic-" + key,
                "frame_sha256": key * 2, "captured_at": self.clock(), "view_status": "fixed",
                "marker_count": 4, "car_visible": True, "car_pose": [0, 0, 0], **overrides}

    def observe(self, **overrides):
        value = self.observation(**overrides)
        response = self.post("/v1/observations", value)
        self.assertEqual(response.status_code, 200, response.text)
        return value

    def submit(self, value):
        response = self.post("/v1/commands", value)
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def wait_state(self, request_id, state):
        deadline = time.monotonic() + 4
        last = None
        while time.monotonic() < deadline:
            response = self.get("/v1/commands/" + request_id)
            self.assertEqual(response.status_code, 200, response.text)
            last = response.json()
            if last["state"] == state:
                return last
            time.sleep(.01)
        self.fail(f"Command did not reach {state}: {last}")

    def review(self, command, observation, verdict="PASS", **overrides):
        return self.post(f"/v1/commands/{command['request_id']}/review", {
            "review_id": str(uuid4()), "observation_id": observation["observation_id"],
            "source": "operator", "verdict": verdict,
            "summary": "Synthetic post-action review.", **overrides})

    def test_app_factory_has_no_startup_or_receiver_io(self):
        with patch.object(self.service, "start") as start, patch.object(self.receiver, "open") as opened, \
                patch.object(self.receiver, "snapshot") as snapshot, patch.object(self.journal, "recover") as recover:
            app = create_app(self.service, TOKEN)
        self.assertEqual(app.title, "PushPilot Robot Commissioning")
        for operation in (start, opened, snapshot, recover):
            operation.assert_not_called()
        self.assertFalse(self.path.with_suffix(".owner.lock").exists())
        self.assertEqual(self.receiver.calls, [])
        with self.assertRaises(ValueError):
            create_app(self.service, "short")

    def test_auth_origin_and_bounded_payload_are_enforced(self):
        self.start()
        self.assertEqual(self.client.get("/health").status_code, 200)
        for headers in ({}, {"X-PushPilot-Control-Token": "incorrect"},
                        {**HEADERS, "origin": "http://untrusted.invalid"}):
            response = self.client.get("/v1/status", headers=headers)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["code"], "CONTROL_AUTH_REQUIRED")
        response = self.client.post("/v1/hold", headers={**HEADERS, "content-type": "text/plain"}, content="hold")
        self.assertEqual(response.status_code, 413)
        response = self.post("/v1/hold", {"reason": "x" * 65536})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.receiver.calls, [])

    def test_schema_rejects_invalid_commands_without_dispatch(self):
        self.start()
        valid = self.command()
        invalid = [
            {**valid, "unexpected": True}, {**valid, "target": [1, 2, 3]},
            {**valid, "target": ["Infinity", 0, 100, 180, 0, 0]},
            {**valid, "expected_receiver": {**valid["expected_receiver"], "seq": True}},
            {**valid, "kind": "rotate"}, {**valid, "purpose": "push", "expected_visual": ""},
            {**valid, "kind": "profile_update", "target": None},
            {**valid, "profile": {"allow_motion": True}}, {**valid, "timeout_seconds": 0},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.post("/v1/commands", payload).status_code, 422)
        self.assertEqual(self.get("/v1/events").json()["events"][-1]["kind"], "service_started_disarmed")
        self.assertEqual(self.receiver.calls, [])

    def test_numeric_and_capability_inputs_cannot_be_coerced_into_motion_authority(self):
        self.start()
        for value in (True, "5"):
            with self.subTest(value=value):
                command = self.command(target=[value, 0, 100, 180, 0, 0])
                self.assertEqual(self.post("/v1/commands", command).status_code, 422)
                command = self.command(timeout_seconds=value)
                self.assertEqual(self.post("/v1/commands", command).status_code, 422)
                installation = {**self.installation, "max_step_mm": value}
                self.assertEqual(self.post("/v1/installation", installation).status_code, 422)
                observation = self.observation(car_pose=[value, 0, 0])
                self.assertEqual(self.post("/v1/observations", observation).status_code, 422)
        for value in (1, "true"):
            with self.subTest(capability=value):
                installation = {**self.installation, "qualified": value}
                self.assertEqual(self.post("/v1/installation", installation).status_code, 422)
                observation = self.observation(car_visible=value)
                self.assertEqual(self.post("/v1/observations", observation).status_code, 422)
        self.assertIsNone(self.journal.get_meta("installation"))
        self.assertIsNone(self.journal.get_observation())
        self.assertEqual(self.receiver.calls, [])

    def test_mock_status_never_claims_external_physical_capability(self):
        self.start()
        status = self.get("/v1/status").json()
        self.assertEqual(status["mode"], "mock")
        self.assertFalse(status["armed"])
        self.assertFalse(status["hardware_connected"])
        self.assertFalse(status["receiver"]["physical_execution"])
        self.assertFalse(status["automatic_replay"])
        self.assertFalse(status["hold_is_emergency_stop"])
        self.assertEqual(self.receiver.snapshot()["profile"]["tcp_id"], "mock-tcp")

    def test_readonly_inspection_works_disarmed_without_installation(self):
        self.start()
        command = self.command(kind="inspect_current", installation_id=None, target=None)
        self.submit(command)
        done = self.wait_state(command["request_id"], "complete")
        self.assertEqual(len(self.receiver.calls), 1)
        self.assertEqual(done["result"]["source"], "mock")
        self.assertFalse(done["result"]["physical_execution"])
        self.assertFalse(done["result"]["robot_receipt"]["physical_execution"])
        self.assertFalse(self.get("/v1/status").json()["armed"])

    def test_concurrent_duplicate_id_dispatches_only_once_and_returns_original(self):
        self.receiver.delay = .08
        self.start()
        command = self.command(kind="inspect_current", installation_id=None, target=None)
        with ThreadPoolExecutor(max_workers=8) as executor:
            responses = list(executor.map(lambda _: self.post("/v1/commands", deepcopy(command)), range(8)))
        for response in responses:
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()["id"], command["request_id"])
        done = self.wait_state(command["request_id"], "complete")
        repeated = self.post("/v1/commands", command)
        self.assertEqual(repeated.status_code, 202)
        self.assertEqual(repeated.json(), done)
        self.assertEqual(len(self.receiver.calls), 1)
        created = [event for event in self.journal.events() if event["kind"] == "command_created"]
        self.assertEqual(len(created), 1)

    def test_same_id_different_payload_is_conflict(self):
        self.start()
        command = self.command(kind="inspect_current", installation_id=None, target=None)
        self.submit(command)
        self.wait_state(command["request_id"], "complete")
        response = self.post("/v1/commands", {**command, "expected_visual": "Different semantic request."})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(len(self.receiver.calls), 1)

    def test_missing_stale_and_covered_car_wait_then_zero_markers_resume_once(self):
        self.start()
        self.configure()
        command = self.command(purpose="push", expected_visual="Car moves along the synthetic edge.")
        self.submit(command)
        self.wait_state(command["request_id"], "waiting_observation")
        self.assertEqual(self.receiver.calls, [])
        for overrides in ({"captured_at": self.clock() - 11}, {"car_visible": False, "car_pose": None}):
            with patch("backend.robot_control.service.admit", wraps=admit) as admission:
                observation = self.observe(**overrides)
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and not any(
                        len(call.args) > 3 and call.args[3]
                        and call.args[3]["observation_id"] == observation["observation_id"]
                        for call in admission.call_args_list):
                    time.sleep(.005)
                self.assertTrue(any(
                    len(call.args) > 3 and call.args[3]
                    and call.args[3]["observation_id"] == observation["observation_id"]
                    for call in admission.call_args_list), "Worker did not inspect this observation.")
            self.wait_state(command["request_id"], "waiting_observation")
            self.assertEqual(self.receiver.calls, [])
        self.observe(view_status="marker_occluded", marker_count=0)
        done = self.wait_state(command["request_id"], "awaiting_review")
        self.assertEqual(done["result"]["before_observation"]["marker_count"], 0)
        self.assertFalse(done["result"]["vehicle_completion_verified"])
        self.assertTrue(self.get("/v1/status").json()["worker_alive"])
        for _ in range(3):
            self.observe(view_status="marker_occluded", marker_count=0)
        self.assertEqual(len(self.receiver.calls), 1)

    def test_push_requires_new_review_before_next_command_and_reobserve_retains_wait(self):
        self.start()
        self.configure()
        before = self.observe()
        self.clock.advance()
        command = self.command(purpose="push", expected_visual="Car advances without leaving the road.")
        self.submit(command)
        self.wait_state(command["request_id"], "awaiting_review")
        blocked = self.post("/v1/commands", self.command())
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["code"], "COMMAND_ACTIVE")
        old = self.review(command, before)
        self.assertEqual(old.status_code, 409)
        self.assertEqual(old.json()["code"], "REOBSERVE")
        self.clock.advance()
        repeated_pixels = self.observe(frame_sha256=before["frame_sha256"])
        self.assertEqual(self.review(command, repeated_pixels).json()["code"], "REOBSERVE")
        covered = self.observe(car_visible=False, car_pose=None, marker_count=0, view_status="marker_occluded")
        self.assertEqual(self.review(command, covered).json()["code"], "CAR_OCCLUDED")
        response = self.review(command, covered, "REOBSERVE")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "awaiting_review")
        self.clock.advance()
        unmeasured = self.observe(car_visible=True, car_pose=None)
        response = self.review(command, unmeasured)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "CAR_OCCLUDED")
        self.assertEqual(self.get(f"/v1/commands/{command['request_id']}").json()["state"], "awaiting_review")
        after = self.observe(marker_count=0, view_status="marker_occluded")
        passed = self.review(command, after)
        self.assertEqual(passed.status_code, 200, passed.text)
        self.assertEqual(passed.json()["state"], "complete")
        self.assertFalse(passed.json()["result"]["physical_execution"])
        self.assertEqual(len(self.receiver.calls), 1)
        next_command = self.command(kind="inspect_current", target=None)
        self.submit(next_command)
        self.wait_state(next_command["request_id"], "complete")
        self.assertEqual(len(self.receiver.calls), 2)

    def test_unbound_external_meta_review_cannot_approve_a_push(self):
        self.start()
        self.configure()
        self.observe()
        command = self.command(purpose="push", expected_visual="Synthetic car advancement.")
        self.submit(command)
        self.wait_state(command["request_id"], "awaiting_review")
        self.clock.advance()
        after = self.observe()
        response = self.review(command, after, source="external_meta_bridge", provider_receipt_id="self-reported")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "PHYSICAL_META_BRIDGE_NOT_CONNECTED")
        self.assertEqual(self.get(f"/v1/commands/{command['request_id']}").json()["state"], "awaiting_review")

    def test_waiting_command_can_be_cancelled_without_publication(self):
        self.start()
        self.configure()
        command = self.command(purpose="push", expected_visual="Synthetic car advancement.")
        self.submit(command)
        self.wait_state(command["request_id"], "waiting_observation")
        cancelled = self.post(f"/v1/commands/{command['request_id']}/cancel", {})
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["state"], "cancelled")
        self.observe()
        self.assertEqual(self.receiver.calls, [])

    def test_cancel_at_final_prewire_check_prevents_publication(self):
        receiver = BeforePublicationReceiver()
        self.start(receiver)
        self.configure()
        command = self.command()
        self.submit(command)
        self.assertTrue(receiver.reached.wait(2))
        response = self.post(f"/v1/commands/{command['request_id']}/cancel", {})
        self.assertEqual(response.status_code, 200)
        receiver.release.set()
        self.wait_state(command["request_id"], "rejected")
        self.assertEqual(receiver.calls, [])
        self.assertFalse(self.get("/v1/status").json()["armed"])
        self.assertNotIn("published", [event["kind"] for event in self.journal.events()])

    def test_retryable_observation_loss_at_publication_waits_then_dispatches_once(self):
        receiver = BeforePublicationReceiver()
        self.start(receiver)
        self.configure()
        self.observe()
        command = self.command(purpose="push", expected_visual="Car advances along the synthetic edge.")
        self.submit(command)
        self.assertTrue(receiver.reached.wait(2))
        self.assertEqual(self.get(f"/v1/commands/{command['request_id']}").json()["state"], "dispatching")
        self.observe(car_visible=False, car_pose=None)
        receiver.release.set()
        waiting = self.wait_state(command["request_id"], "waiting_observation")
        self.assertEqual(waiting["error"], "WAIT_OBSERVATION")
        self.assertEqual(receiver.calls, [])
        self.assertNotIn("publication_intent", [event["kind"] for event in self.journal.events()])
        fresh = self.observe(view_status="marker_occluded", marker_count=0)
        done = self.wait_state(command["request_id"], "awaiting_review")
        self.assertEqual(done["result"]["before_observation"]["observation_id"], fresh["observation_id"])
        self.assertEqual(len(receiver.calls), 1)
        publications = [event for event in self.journal.events() if event["kind"] == "publication_intent"]
        self.assertEqual(len(publications), 1)
        self.assertTrue(publications[0]["data"]["admission_committed"])

    def test_hold_after_durable_commit_truthfully_allows_committed_publication(self):
        receiver = AfterCommitReceiver()
        self.start(receiver)
        self.configure()
        command = self.command()
        self.submit(command)
        self.assertTrue(receiver.reached.wait(2))
        self.assertEqual(receiver.calls, [])
        self.assertEqual(self.get(f"/v1/commands/{command['request_id']}").json()["state"], "committed")
        held = self.post("/v1/hold", {"reason": "Synthetic operator hold after durable admission."})
        self.assertEqual(held.status_code, 200, held.text)
        self.assertEqual(held.json()["effect"], "inhibit_uncommitted_commands_only")
        self.assertFalse(held.json()["robot_stop_issued"])
        self.assertTrue(held.json()["committed_command_may_still_publish_or_execute"])
        cancel = self.post(f"/v1/commands/{command['request_id']}/cancel", {})
        self.assertEqual(cancel.status_code, 200, cancel.text)
        self.assertEqual(cancel.json()["state"], "committed")
        event = next(event for event in self.journal.events() if event["kind"] == "cancel_requested")
        self.assertFalse(event["data"]["robot_stop_issued"])
        self.assertTrue(event["data"]["committed_command_may_still_publish_or_execute"])
        receiver.release.set()
        self.assertTrue(self.wait_state(command["request_id"], "complete")["cancel_requested"])
        self.assertEqual(len(receiver.calls), 1)
        status = self.get("/v1/status").json()
        self.assertTrue(status["hold"])
        self.assertFalse(status["armed"])
        next_command = self.command(target=[10, 0, 100, 180, 0, 0])
        self.submit(next_command)
        self.assertEqual(self.wait_state(next_command["request_id"], "rejected")["error"], "NOT_ARMED")
        self.assertEqual(len(receiver.calls), 1)

    def test_inflight_cancel_inhibits_next_command_without_claiming_robot_stop(self):
        receiver = AfterPublicationReceiver()
        self.start(receiver)
        self.configure()
        command = self.command()
        self.submit(command)
        self.assertTrue(receiver.reached.wait(2))
        response = self.post(f"/v1/commands/{command['request_id']}/cancel", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "running")
        self.assertTrue(response.json()["cancel_requested"])
        status = self.get("/v1/status").json()
        self.assertTrue(status["hold"])
        self.assertFalse(status["armed"])
        self.assertFalse(status["hold_is_emergency_stop"])
        event = next(event for event in self.journal.events() if event["kind"] == "cancel_requested")
        self.assertFalse(event["data"]["robot_stop_issued"])
        receiver.release.set()
        done = self.wait_state(command["request_id"], "complete")
        self.assertTrue(done["cancel_requested"])
        next_command = self.command(target=[10, 0, 100, 180, 0, 0])
        self.submit(next_command)
        self.assertEqual(self.wait_state(next_command["request_id"], "rejected")["error"], "NOT_ARMED")
        self.assertEqual(len(receiver.calls), 1)

    def assert_unknown_without_retry(self, failure):
        self.start()
        self.configure()
        self.receiver.failure = failure
        command = self.command()
        self.submit(command)
        unknown = self.wait_state(command["request_id"], "outcome_unknown")
        self.assertFalse(self.get("/v1/status").json()["armed"])
        self.receiver.failure = None
        repeated = self.post("/v1/commands", command)
        self.assertEqual(repeated.status_code, 202)
        self.assertEqual(repeated.json(), unknown)
        self.assertEqual(self.post("/v1/commands", self.command()).status_code, 409)
        self.assertEqual(len(self.receiver.calls), 1)
        self.assertTrue(self.get("/v1/status").json()["worker_alive"])

    def test_completion_loss_is_unknown_and_duplicate_id_never_retries(self):
        self.assert_unknown_without_retry(OutcomeUnknown("Synthetic DONE loss."))

    def test_unexpected_backend_exception_is_unknown_and_never_retries(self):
        self.assert_unknown_without_retry(RuntimeError("Synthetic backend exception."))

    def test_operator_reconciliation_resets_bound_transport_without_replay_or_rearming(self):
        self.start()
        self.configure()
        self.receiver.failure = OutcomeUnknown("Synthetic lost completion receipt.")
        command = self.command()
        self.submit(command)
        self.wait_state(command["request_id"], "outcome_unknown")
        with self.receiver.lock:
            self.receiver.state.update(idle=True, stage="idle")
        value = {"installation_id": self.installation["installation_id"],
                 "expected_receiver": self.binding(), "reason": "Synthetic operator inspected the endpoint.",
                 "measured_outcome": "confirmed_not_executed"}
        with patch.object(self.receiver, "reconcile", wraps=self.receiver.reconcile) as reset:
            wrong = {**value, "expected_receiver": {**value["expected_receiver"], "seq": 999}}
            self.assertEqual(self.post(f"/v1/commands/{command['request_id']}/reconcile", wrong).status_code, 409)
            reset.assert_not_called()
            response = self.post(f"/v1/commands/{command['request_id']}/reconcile", value)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["state"], "reconciled")
            reset.assert_called_once_with(value["expected_receiver"])
        self.assertFalse(self.get("/v1/status").json()["armed"])
        self.assertEqual(len(self.receiver.calls), 1)
        self.assertEqual(self.post("/v1/commands", command).json()["state"], "reconciled")
        event = next(event for event in self.journal.events() if event["kind"] == "operator_reconciled_no_replay")
        self.assertEqual(event["data"]["receiver_receipt"]["seq"], value["expected_receiver"]["seq"])
        self.assertFalse(event["data"]["receiver_receipt"]["physical_execution"])
        next_command = self.command()
        self.submit(next_command)
        self.assertEqual(self.wait_state(next_command["request_id"], "rejected")["error"], "NOT_ARMED")
        self.assertEqual(len(self.receiver.calls), 1)

    def assert_installation_free_inspection_can_be_reconciled(self, kind):
        self.start()
        self.assertIsNone(self.journal.get_meta("installation"))
        self.receiver.failure = OutcomeUnknown("Synthetic inspection completion loss.")
        command = self.command(kind=kind, installation_id=None,
                               target=None if kind == "inspect_current" else [5, 0, 100, 180, 0, 0])
        self.submit(command)
        self.wait_state(command["request_id"], "outcome_unknown")
        blocked = self.post("/v1/installation", self.installation)
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["code"], "COMMAND_ACTIVE")
        value = {"installation_id": "inspection-before-installation",
                 "expected_receiver": self.binding(), "reason": "Synthetic operator inspected the idle receiver.",
                 "measured_outcome": "confirmed_completed"}
        with patch.object(self.receiver, "reconcile", wraps=self.receiver.reconcile) as reset:
            not_idle = self.post(f"/v1/commands/{command['request_id']}/reconcile", value)
            self.assertEqual(not_idle.status_code, 409)
            self.assertEqual(not_idle.json()["code"], "RECEIVER_NOT_READY")
            reset.assert_not_called()
            with self.receiver.lock:
                self.receiver.state.update(idle=True, stage="idle", seq=self.receiver.state["seq"] + 1)
            stale = self.post(f"/v1/commands/{command['request_id']}/reconcile", value)
            self.assertEqual(stale.status_code, 409)
            self.assertEqual(stale.json()["code"], "RECEIVER_BINDING")
            reset.assert_not_called()
            value["expected_receiver"] = self.binding()
            response = self.post(f"/v1/commands/{command['request_id']}/reconcile", value)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["state"], "reconciled")
            reset.assert_called_once_with(value["expected_receiver"])
        self.assertFalse(self.get("/v1/status").json()["armed"])
        self.assertIsNone(self.journal.get_meta("installation"))
        self.assertEqual(self.post("/v1/commands", command).json()["state"], "reconciled")
        self.assertEqual(len(self.receiver.calls), 1)
        installed = self.post("/v1/installation", self.installation)
        self.assertEqual(installed.status_code, 200, installed.text)
        self.assertEqual(installed.json()["installation_id"], self.installation["installation_id"])
        self.assertFalse(self.get("/v1/status").json()["armed"])
        self.assertEqual(len(self.receiver.calls), 1)

    def test_unknown_current_inspection_without_installation_can_be_reconciled_then_installed(self):
        self.assert_installation_free_inspection_can_be_reconciled("inspect_current")

    def test_unknown_ik_inspection_without_installation_can_be_reconciled_then_installed(self):
        self.assert_installation_free_inspection_can_be_reconciled("inspect_ik")

    def test_unbound_detector_and_meta_observations_cannot_enter_control_ledger(self):
        self.start()
        for source in ("detector", "external_meta_bridge"):
            with self.subTest(source=source):
                response = self.post("/v1/observations", self.observation(source=source))
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["code"], "PHYSICAL_OBSERVATION_BRIDGE_NOT_CONNECTED")
        self.assertIsNone(self.journal.get_observation())
        self.assertEqual(self.receiver.calls, [])

    def test_ledger_request_failure_returns_unambiguous_503_and_api_remains_alive(self):
        self.start()
        command = self.command(kind="inspect_current", installation_id=None, target=None)
        with patch.object(self.journal, "create", side_effect=sqlite3.OperationalError("Synthetic disk failure.")):
            response = self.post("/v1/commands", command)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["code"], "CONTROL_REQUEST_FAILED")
        self.assertEqual(self.receiver.calls, [])
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertTrue(self.client.get("/health").json()["worker_alive"])
        self.assertEqual(self.get(f"/v1/commands/{command['request_id']}").status_code, 404)
        self.submit(command)
        self.wait_state(command["request_id"], "complete")
        self.assertEqual(len(self.receiver.calls), 1)

    def test_restart_of_durable_commit_becomes_unknown_without_publication_or_replay(self):
        self.start()
        self.configure()
        command = self.command(purpose="push", expected_visual="Synthetic queued push.")
        self.submit(command)
        self.wait_state(command["request_id"], "waiting_observation")
        # Model a process loss after its durable admission receipt, with no
        # physical receiver involved and no live worker left to publish it.
        self.client.__exit__(None, None, None)
        self.client = None
        self.journal.update(command["request_id"], "committed")
        self.journal.close()
        self.journal = Journal(self.path, clock=self.clock)
        self.receiver = MockReceiver()
        self.service = RobotService(self.journal, self.receiver, clock=self.clock)
        self.start()
        recovered = self.get(f"/v1/commands/{command['request_id']}").json()
        self.assertEqual(recovered["state"], "outcome_unknown")
        self.assertFalse(self.get("/v1/status").json()["armed"])
        self.assertEqual(self.post("/v1/commands", command).json(), recovered)
        self.assertEqual(self.post("/v1/commands", self.command()).status_code, 409)
        self.assertEqual(self.receiver.calls, [])

    def test_restart_disarms_and_never_replays_queued_or_uncertain_commands(self):
        self.start()
        self.configure()
        command = self.command(purpose="push", expected_visual="Synthetic pending observation.")
        self.submit(command)
        self.wait_state(command["request_id"], "waiting_observation")
        self.client.__exit__(None, None, None)
        self.client = None
        self.journal.close()
        self.journal = Journal(self.path, clock=self.clock)
        self.receiver = MockReceiver()
        self.service = RobotService(self.journal, self.receiver, clock=self.clock)
        self.start()
        interrupted = self.get(f"/v1/commands/{command['request_id']}").json()
        self.assertEqual(interrupted["state"], "interrupted_before_dispatch")
        self.assertFalse(self.get("/v1/status").json()["armed"])
        self.assertEqual(self.receiver.calls, [])
        self.assertEqual(self.post("/v1/commands", command).json(), interrupted)
        uncertain = self.command(kind="inspect_current", target=None)
        # Persist a publication whose process died before it received completion.
        self.journal.create({**uncertain, "edge_id": None, "profile": None, "expected_visual": ""})
        self.journal.update(uncertain["request_id"], "running")
        self.client.__exit__(None, None, None)
        self.client = None
        self.journal.close()
        self.journal = Journal(self.path, clock=self.clock)
        self.receiver = MockReceiver()
        self.service = RobotService(self.journal, self.receiver, clock=self.clock)
        self.start()
        recovered = self.get(f"/v1/commands/{uncertain['request_id']}").json()
        self.assertEqual(recovered["state"], "outcome_unknown")
        self.assertEqual(self.receiver.calls, [])
        self.assertFalse(self.get("/v1/status").json()["armed"])

    def test_second_service_cannot_take_over_owned_state(self):
        self.start()
        other_journal = Journal(self.path, clock=self.clock)
        self.addCleanup(other_journal.close)
        other_receiver = MockReceiver()
        other = RobotService(other_journal, other_receiver, clock=self.clock)
        with patch.object(other_receiver, "open") as opened:
            with self.assertRaises(ControlError) as error:
                other.start()
        self.assertEqual(error.exception.code, "SERVICE_OWNED")
        opened.assert_not_called()
        self.assertTrue(self.get("/v1/status").json()["worker_alive"])
        self.assertEqual(other_receiver.calls, [])


if __name__ == "__main__":
    unittest.main()
