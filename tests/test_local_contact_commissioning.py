"""Synthetic offline contact-scope tests; no physical trial or calibration proof."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.robot_control.api import create_app
from backend.robot_control.gates import GuardError, admit
from backend.robot_control.mock import MockReceiver
from backend.robot_control.models import LocalContactInstallation, RobotCommand
from backend.robot_control.service import RobotService
from backend.robot_control.store import Journal
from tools import prepare_local_contact as prepare
from tools.prepare_local_commissioning import build_profile as teaching_profile
from test_local_commissioning import synthetic_installation, synthetic_robot_state


def contact_installation():
    return {**synthetic_installation(), "scope": "local_contact_commissioning",
            "installation_id": "synthetic-contact-review",
            "review_reference": "Synthetic distinct actual-site contact authorization; not physical evidence.",
            "workspace_min_mm": [-30., -30., 99.], "workspace_max_mm": [30., 30., 101.],
            "max_step_mm": 20., "max_speed_mm_s": 3., "max_accel_mm_s2": 5.,
            "car_id": "synthetic-car", "surface_id": "synthetic-surface",
            "reported_car_dimensions_mm": [45., 18., 15.], "contact_trials_authorized": True,
            "trial_max_step_mm": 5.}


class ContactScopeTests(unittest.TestCase):
    def setUp(self):
        self.local, self.state = contact_installation(), synthetic_robot_state()
        self.profile = prepare.build_profile(self.local, self.state, on_site_review=True)
        self.receiver = {**self.state, "connected": True, "idle": True, "physical_execution": True,
                         "session_id": "synthetic-session", "seq": 3, "profile_id": "synthetic-profile",
                         "profile": self.profile}
        self.command = {"kind": "translate", "purpose": "contact_trial", "installation_id": self.local["installation_id"],
                        "expected_receiver": {key: self.receiver[key] for key in ("session_id", "seq", "profile_id")},
                        "target": [5., 0., *self.state["actual_pose"][2:]],
                        "expected_visual": "Synthetic small contact response; car outcome remains unassessed."}

    def gate(self, *, command=None, installation=None, receiver=None, armed=True, held=False):
        admit(command or self.command, installation or self.local, receiver or self.receiver, None,
              armed=armed, held=held, now=100., require_profile_binding=True)

    def rejects(self, code, **kwargs):
        with self.assertRaises(GuardError) as error:
            self.gate(**kwargs)
        self.assertEqual(error.exception.code, code)

    def handoff(self, receiver=None):
        return {"kind": "profile_update", "purpose": "commissioning", "installation_id": self.local["installation_id"],
                "profile": self.profile, "expected_receiver": self.command["expected_receiver"]}

    def test_scope_requires_explicit_actual_contact_review_and_reported_geometry(self):
        self.gate()
        for changes in ({"contact_trials_authorized": False}, {"on_site_review": False},
                        {"reported_car_dimensions_mm": [45., 0., 15.]}, {"reported_car_dimensions_mm": [45., True, 15.]},
                        {"trial_max_step_mm": 20.000001}, {"map_id": "pretend-map"}, {"calibration_id": "pretend-fit"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                LocalContactInstallation.model_validate({**self.local, **changes})
        self.rejects("INSTALLATION_UNQUALIFIED", installation={**self.local, "qualified": False})
        with self.assertRaisesRegex(ValueError, "on-site-review"):
            prepare.build_profile(self.local, self.state)
        for key in ("board_registration_qualified", "vehicle_control_qualified", "rotation_qualified", "car_turn_qualified"):
            self.assertIs(self.profile["installation_binding"][key], False)

    def test_five_mm_contact_limit_is_separate_from_twenty_mm_free_approach(self):
        self.gate()
        self.rejects("STEP_LIMIT", command={**self.command, "target": [5.000001, 0., *self.state["actual_pose"][2:]]})
        self.gate(command={**self.command, "purpose": "commissioning", "target": [20., 0., *self.state["actual_pose"][2:]]})
        self.rejects("STEP_LIMIT", command={**self.command, "purpose": "commissioning",
                                           "target": [20.000001, 0., *self.state["actual_pose"][2:]]})
        for purpose in ("push", "tool_reposition"):
            self.rejects("CONTACT_OPERATION_FORBIDDEN", command={**self.command, "purpose": purpose})
        self.rejects("CONTACT_OPERATION_FORBIDDEN", command={**self.command, "kind": "rotate"})
        self.rejects("CONTACT_EXPECTED_OUTCOME_REQUIRED", command={**self.command, "expected_visual": ""})

    def test_reviewed_ten_and_twenty_mm_strokes_keep_numeric_profile_binding(self):
        for limit in (10., 20.):
            with self.subTest(limit=limit):
                local = {**self.local, "trial_max_step_mm": limit}
                LocalContactInstallation.model_validate(local)
                profile = prepare.build_profile(local, self.state, on_site_review=True)
                receiver = {**self.receiver, "profile": profile}
                command = {**self.command, "target": [limit, 0., *self.state["actual_pose"][2:]]}
                self.gate(command=command, installation=local, receiver=receiver)
                self.rejects("STEP_LIMIT", command={**command, "target": [limit + .000001, 0., *command["target"][2:]]},
                             installation=local, receiver=receiver)
                self.rejects("PROFILE_INSTALLATION_BINDING", command=command, installation=local)
                for index, code in ((2, "LOCAL_Z_CHANGED"), (5, "ORIENTATION_CHANGED")):
                    target = command["target"][:]
                    target[index] += .000001
                    self.rejects(code, command={**command, "target": target}, installation=local, receiver=receiver)

    def test_default_contact_limit_remains_one_mm(self):
        local = dict(self.local)
        del local["trial_max_step_mm"]
        self.assertEqual(LocalContactInstallation.model_validate(local).trial_max_step_mm, 1.)

    def test_exact_height_orientation_bounds_and_profile_limits_remain_mandatory(self):
        for index, code in ((2, "LOCAL_Z_CHANGED"), (5, "ORIENTATION_CHANGED")):
            target = self.command["target"][:]
            target[index] += .000001
            self.rejects(code, command={**self.command, "target": target})
        self.rejects("OUTSIDE_WORKSPACE", command={**self.command, "target": [31., 0., *self.state["actual_pose"][2:]]})
        self.rejects("NOT_ARMED", armed=False)
        self.rejects("NOT_ARMED", held=True)
        for field, value in (("translation_speed_mm_s", 3.1), ("translation_accel_mm_s2", 5.1), ("max_translation_mm", 20.1)):
            self.rejects("PROFILE_LIMIT", receiver={**self.receiver, "profile": {**self.profile, field: value}})

    def test_candidate_binding_rejects_mismatched_car_surface_tool_and_provenance(self):
        for key, value in (("car_id", "other-car"), ("surface_id", "other-surface"), ("tool_id", "other-pad"),
                           ("reported_car_dimensions_mm", [45., 19., 15.]), ("source", "invented"),
                           ("contact_trials_authorized", False), ("vehicle_control_qualified", True)):
            candidate = {**self.profile, "installation_binding": {**self.profile["installation_binding"], key: value}}
            self.rejects("PROFILE_INSTALLATION_BINDING", receiver={**self.receiver, "profile": candidate})

    def test_contact_cannot_enter_old_teaching_or_board_push_admission(self):
        old = synthetic_installation()
        old_profile = teaching_profile(old, self.state, on_site_review=True)
        self.rejects("LOCAL_OPERATION_FORBIDDEN", installation=old,
                     receiver={**self.receiver, "profile": old_profile},
                     command={**self.command, "installation_id": old["installation_id"]})
        board = {"scope": "board", "installation_id": "board", "map_id": "map", "map_hash": "hash",
                 "calibration_id": "fit", "tcp_id": self.local["tcp_id"], "tool_id": "tool",
                 "review_reference": "Synthetic board scope compatibility.", "qualified": True,
                 "workspace_min_mm": [-30., -30., 0.], "workspace_max_mm": [30., 30., 150.],
                 "min_tcp_z_mm": 90., "raised_tcp_z_mm": 120., "camera_epoch": "camera", "registration_id": "reg"}
        profile = {**self.profile, "scope": "board"}
        with self.assertRaises(GuardError) as error:
            admit({**self.command, "installation_id": "board"}, board, {**self.receiver, "profile": profile},
                  None, armed=True, now=100.)
        self.assertEqual(error.exception.code, "COMMAND_INVALID")

    def test_no_motion_handoff_requires_new_review_same_tool_exact_fresh_baseline_and_hold(self):
        old = synthetic_installation()
        receiver = {**self.receiver, "profile": teaching_profile(old, self.state, on_site_review=True)}
        command = self.handoff()
        self.gate(command=command, receiver=receiver, armed=False, held=True)
        for armed, held in ((True, True), (True, False), (False, False)):
            self.rejects("LOCAL_REFRESH_REQUIRES_HOLD", command=command, receiver=receiver, armed=armed, held=held)
        self.rejects("LOCAL_OPERATION_FORBIDDEN", command={**command, "target": self.command["target"]},
                     receiver=receiver, armed=False, held=True)
        for key in ("actual_pose", "actual_joint"):
            changed = deepcopy(receiver)
            changed[key][0] += .000001
            self.rejects("LOCAL_REFRESH_BASELINE_CHANGED", command=command, receiver=changed, armed=False, held=True)
        changed = deepcopy(receiver)
        changed["profile"]["installation_binding"]["tcp_definition_sha256"] = "b" * 64
        self.rejects("LOCAL_TOOL_BINDING", command=command, receiver=changed, armed=False, held=True)
        self.rejects("LOCAL_REFRESH_NEW_REVIEW_REQUIRED", command=command, armed=False, held=True)
        self.rejects("RECEIVER_BINDING", command=command, receiver={**receiver, "seq": 4}, armed=False, held=True)

    def test_command_schema_prevents_contact_disguised_as_inspection_rotation_or_profile(self):
        command = {**self.command, "request_id": str(uuid4())}
        RobotCommand.model_validate(command)
        for changes in ({"expected_visual": ""}, {"kind": "inspect_ik"}, {"kind": "inspect_current"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                RobotCommand.model_validate({**command, **changes})

    def test_offline_policy_validation_precedes_exclusive_profile_write(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            installation, state, output = root / "review.json", root / "state.json", root / "profile.json"
            with patch.object(prepare, "load_runtime") as load, self.assertRaises(ValueError):
                prepare.prepare(installation, state, output)
            load.assert_not_called()
            installation.write_text(json.dumps(self.local))
            state.write_text(json.dumps(self.state))
            policy = SimpleNamespace(valid=Mock(), MAX_PROFILE_BYTES=8000)
            with patch.object(prepare, "load_runtime", return_value={"policy": policy}):
                result = prepare.prepare(installation, state, output, on_site_review=True)
                policy.valid.assert_called_once()
                self.assertFalse(result["motion_issued"] or result["profile_applied"] or result["network_contacted"])
                before = output.read_bytes()
                with self.assertRaises(FileExistsError):
                    prepare.prepare(installation, state, output, on_site_review=True)
                self.assertEqual(output.read_bytes(), before)
                policy.valid.side_effect = ValueError("Synthetic inherited policy failure")
                with self.assertRaises(ValueError):
                    prepare.prepare(installation, state, root / "rejected.json", on_site_review=True)
                self.assertFalse((root / "rejected.json").exists())


class ContactApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.journal = Journal(Path(self.directory.name) / "synthetic.sqlite3")
        self.addCleanup(self.journal.close)
        self.receiver = MockReceiver()
        self.local, self.state = contact_installation(), synthetic_robot_state()
        self.profile = prepare.build_profile(self.local, self.state, on_site_review=True)
        self.receiver.state.update(**deepcopy(self.state), profile=self.profile)
        self.service = RobotService(self.journal, self.receiver)
        self.token = "synthetic-contact-token-not-production"
        self.headers = {"X-PushPilot-Control-Token": self.token}
        self.client = TestClient(create_app(self.service, self.token, manage_lifecycle=False))
        self.addCleanup(self.client.close)
        self.service.start()
        self.addCleanup(self.service.stop)

    def binding(self):
        return {key: self.receiver.state[key] for key in ("session_id", "seq", "profile_id")}

    def post(self, path, value):
        return self.client.post(path, headers=self.headers, json=value)

    def command(self, **changes):
        return {"request_id": str(uuid4()), "kind": "translate", "purpose": "contact_trial",
                "installation_id": self.local["installation_id"], "expected_receiver": self.binding(),
                "target": [2., 0., *self.state["actual_pose"][2:]],
                "expected_visual": "Synthetic experimental contact; no measured vehicle result.",
                "timeout_seconds": 3., "admission_timeout_seconds": 5., **changes}

    def arm(self):
        return self.post("/v1/arm", {"installation_id": self.local["installation_id"],
                         "expected_receiver": self.binding(), "reason": "Synthetic distinct deliberate contact-trial arm."})

    def await_terminal(self, request_id):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = self.client.get("/v1/commands/" + request_id, headers=self.headers).json()
            if job["state"] in {"complete", "rejected", "outcome_unknown"}:
                return job
            time.sleep(.01)
        self.fail("Synthetic trial did not terminate.")

    def test_one_trial_completes_robot_only_then_holds_without_vehicle_or_muse_claim(self):
        self.assertEqual(self.post("/v1/installation", self.local).status_code, 200)
        self.assertEqual(self.arm().status_code, 200)
        command = self.command()
        self.assertEqual(self.post("/v1/commands", command).status_code, 202)
        job = self.await_terminal(command["request_id"])
        self.assertEqual(job["state"], "complete", job)
        self.assertTrue(job["result"]["robot_completed"])
        self.assertFalse(job["result"]["vehicle_completion_verified"] or job["result"]["physical_contact_trial"]
                         or job["result"]["board_mission_advanced"])
        self.assertEqual(job["result"]["vehicle_outcome"], "unassessed")
        status = self.service.status()
        self.assertFalse(status["armed"])
        self.assertTrue(status["hold"])
        self.assertEqual(status["installation_scope"], "local_contact_commissioning")
        next_command = self.command(target=[3., 0., *self.state["actual_pose"][2:]])
        self.assertEqual(self.post("/v1/commands", next_command).status_code, 202)
        self.assertEqual(self.await_terminal(next_command["request_id"])["error"], "NOT_ARMED")
        self.assertEqual(len(self.receiver.calls), 1)

    def test_held_profile_handoff_retains_session_without_motion_or_rearming(self):
        self.receiver.state["profile"] = teaching_profile(synthetic_installation(), self.state, on_site_review=True)
        before = deepcopy(self.receiver.state)
        self.post("/v1/installation", self.local)
        self.post("/v1/hold", {"reason": "Synthetic deliberate held contact profile handoff."})
        command = self.command(kind="profile_update", purpose="commissioning", target=None, profile=self.profile)
        self.assertEqual(self.post("/v1/commands", command).status_code, 202)
        self.assertEqual(self.await_terminal(command["request_id"])["state"], "complete")
        self.assertEqual(self.receiver.state["actual_pose"], before["actual_pose"])
        self.assertEqual(self.receiver.state["session_id"], before["session_id"])
        self.assertEqual(self.receiver.state["seq"], before["seq"] + 1)
        self.assertFalse(self.service.status()["armed"])
        self.assertTrue(self.service.status()["hold"])

    def test_contact_baseline_is_rechecked_before_publication(self):
        self.post("/v1/installation", self.local)
        self.assertEqual(self.arm().status_code, 200)
        command = self.command()
        execute = self.receiver.execute

        def changed(value, on_event):
            self.receiver.state["actual_pose"][2] += .000001
            return execute(value, on_event)

        with patch.object(self.receiver, "execute", side_effect=changed):
            self.post("/v1/commands", command)
            job = self.await_terminal(command["request_id"])
        self.assertEqual(job["state"], "rejected", job)
        self.assertEqual(job["error"], "LOCAL_Z_CHANGED")
        self.assertEqual(self.receiver.calls, [])

    def test_unknown_trial_is_held_and_never_replayed_after_duplicate_or_restart(self):
        self.post("/v1/installation", self.local)
        self.assertEqual(self.arm().status_code, 200)
        self.receiver.failure = RuntimeError("Synthetic missing endpoint receipt")
        command = self.command()
        self.post("/v1/commands", command)
        self.assertEqual(self.await_terminal(command["request_id"])["state"], "outcome_unknown")
        self.assertTrue(self.service.status()["hold"])
        self.assertEqual(self.post("/v1/commands", command).status_code, 202)
        self.assertEqual(self.post("/v1/commands", self.command()).status_code, 409)
        self.service.stop()
        self.service.start()
        self.assertFalse(self.service.status()["armed"])
        self.assertEqual(self.await_terminal(command["request_id"])["state"], "outcome_unknown")
        self.assertEqual(len(self.receiver.calls), 1)


if __name__ == "__main__":
    unittest.main()
