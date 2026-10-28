"""Synthetic offline local BASE scope tests; no real device, profile or site."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.robot_control.api import create_app
from backend.robot_control.gates import GuardError, admit, validate_local_profile
from backend.robot_control.mock import MockReceiver
from backend.robot_control.models import Installation, LocalBaseInstallation
from backend.robot_control.service import RobotService
from backend.robot_control.store import Journal
from tools import prepare_local_commissioning as prepare


def synthetic_installation():
    return {
        "scope": "local_base_commissioning", "installation_id": "synthetic-local-volume",
        "tcp_id": "synthetic-current-tcp", "tcp_definition_sha256": "a" * 64,
        "tool_id": "synthetic-current-tool", "payload_kg": 0.25,
        "review_reference": "Synthetic actual-site review fixture; not physical clearance evidence.",
        "qualified": True, "on_site_review": True,
        "workspace_min_mm": [-4., -4., 99.], "workspace_max_mm": [4., 4., 101.],
        "fixed_tcp_z_mm": 100., "fixed_orientation_deg": [180., 0., 0.],
        "tcp_clearance_margin_mm": 0., "inflated_keepout_boxes_base_mm": [],
        "max_step_mm": 2., "max_speed_mm_s": 1., "max_accel_mm_s2": 2.,
    }


def synthetic_robot_state():
    return {"actual_pose": [0., 0., 100., 180., 0., 0.], "actual_joint": [0.] * 6}


class LocalCommissioningTests(unittest.TestCase):
    def setUp(self):
        self.installation = synthetic_installation()
        self.state = synthetic_robot_state()
        self.profile = prepare.build_profile(self.installation, self.state, on_site_review=True)
        self.receiver = {
            "connected": True, "idle": True, "session_id": "synthetic-local-session", "seq": 1,
            "profile_id": "synthetic-local-profile", "physical_execution": True,
            "actual_pose": self.state["actual_pose"], "profile": self.profile,
        }
        self.command = {
            "kind": "translate", "purpose": "commissioning", "installation_id": self.installation["installation_id"],
            "expected_receiver": {key: self.receiver[key] for key in ("session_id", "seq", "profile_id")},
            "target": [1., 0., 100., 180., 0., 0.],
        }

    def gate(self, *, command=None, installation=None, receiver=None, armed=True):
        return admit(command or self.command, installation or self.installation, receiver or self.receiver,
                     None, armed=armed, now=100., require_profile_binding=True)

    def assert_guard(self, code, **kwargs):
        with self.assertRaises(GuardError) as error:
            self.gate(**kwargs)
        self.assertEqual(error.exception.code, code)

    def test_local_scope_has_no_map_camera_or_drawing_registration_claim(self):
        self.gate()
        binding = self.profile["installation_binding"]
        self.assertFalse(binding["board_registration_qualified"] or binding["vehicle_control_qualified"])
        self.assertFalse(binding["rotation_qualified"] or binding["car_turn_qualified"])
        for key in ("map_id", "map_hash", "camera_epoch", "registration_id", "calibration_id"):
            self.assertNotIn(key, self.profile)
            self.assertNotIn(key, binding)
            with self.subTest(key=key), self.assertRaises(ValueError):
                LocalBaseInstallation.model_validate({**self.installation, key: "forged-board-binding"})

    def test_review_and_qualification_are_separate_inputs_never_inferred(self):
        with self.assertRaisesRegex(ValueError, "on-site-review"):
            prepare.build_profile(self.installation, self.state)
        for changes in ({"qualified": False}, {"qualified": True, "on_site_review": False},
                        {"qualified": 1}, {"on_site_review": "true"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare.build_profile({**self.installation, **changes}, self.state, on_site_review=True)
        self.assert_guard("NOT_ARMED", armed=False)
        self.assert_guard("INSTALLATION_UNQUALIFIED", installation={**self.installation, "qualified": False})

    def test_local_scope_cannot_push_reposition_rotate_or_update_profile(self):
        for changes in ({"purpose": "push"}, {"purpose": "tool_reposition"},
                        {"kind": "rotate", "purpose": "tool_reposition"}, {"kind": "profile_update"}):
            with self.subTest(changes=changes):
                self.assert_guard("LOCAL_OPERATION_FORBIDDEN", command={**self.command, **changes})

    def test_every_vertical_change_and_literal_orientation_change_is_rejected(self):
        for target in ([1., 0., 100.1, 180., 0., 0.], [0., 0., 100.1, 180., 0., 0.],
                       [1., 0., 100.000001, 180., 0., 0.]):
            self.assert_guard("LOCAL_Z_CHANGED", command={**self.command, "target": target})
        for target in ([1., 0., 100., -180., 0., 0.], [1., 0., 100., 180., 0., 0.000001]):
            self.assert_guard("ORIENTATION_CHANGED", command={**self.command, "target": target})
        self.assert_guard("LOCAL_Z_CHANGED", receiver={**self.receiver, "actual_pose": [0., 0., 100.1, 180., 0., 0.]})
        self.assert_guard("ORIENTATION_CHANGED", receiver={**self.receiver, "actual_pose": [0., 0., 100., 180., 0., 1.]})

    def test_source_target_step_margin_and_profile_bounds_apply(self):
        self.assert_guard("OUTSIDE_WORKSPACE", command={**self.command, "target": [5., 0., 100., 180., 0., 0.]})
        self.assert_guard("OUTSIDE_WORKSPACE", receiver={**self.receiver, "actual_pose": [-5., 0., 100., 180., 0., 0.]})
        self.assert_guard("STEP_LIMIT", command={**self.command, "target": [2.1, 0., 100., 180., 0., 0.]})
        self.assert_guard("STEP_LIMIT", command={**self.command, "target": self.state["actual_pose"]})
        self.assert_guard("PROFILE_BOUNDS", receiver={**self.receiver, "profile": {
            **self.profile, "tcp_bounds_base_mm": [-5., -4., 99., 4., 4., 101.]}})
        installation = {**self.installation, "tcp_clearance_margin_mm": 0.5}
        profile = prepare.build_profile(installation, self.state, on_site_review=True)
        self.assert_guard("OUTSIDE_WORKSPACE", installation=installation,
                          receiver={**self.receiver, "profile": profile},
                          command={**self.command, "target": [3.6, 0., 100., 180., 0., 0.]})

    def test_local_volume_and_speed_caps_cannot_be_whole_board_limits(self):
        for changes in ({"workspace_max_mm": [16.1, 4., 101.]}, {"max_step_mm": 5.01},
                        {"max_speed_mm_s": 5.01}, {"max_accel_mm_s2": 10.01},
                        {"max_step_mm": True}, {"max_speed_mm_s": float("nan")},
                        {"workspace_min_mm": [-4., False, 99.]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare.build_profile({**self.installation, **changes}, self.state, on_site_review=True)
        for key, value in (("max_translation_mm", 3.), ("translation_speed_mm_s", 2.),
                           ("translation_accel_mm_s2", 3.), ("translation_speed_mm_s", True)):
            self.assert_guard("PROFILE_LIMIT", receiver={**self.receiver, "profile": {**self.profile, key: value}})

    def test_changed_tool_definition_payload_and_review_reject_current_profile(self):
        for key, value in (("tcp_definition_sha256", "b" * 64), ("tool_id", "changed-tool"),
                           ("review_reference", "A genuinely different local site review.")):
            self.assert_guard("PROFILE_INSTALLATION_BINDING", installation={**self.installation, key: value})
        self.assert_guard("LOCAL_TOOL_BINDING", installation={**self.installation, "payload_kg": 0.3})
        self.assert_guard("TCP_MISMATCH", installation={**self.installation, "tcp_id": "different-tcp"})
        self.assert_guard("PHYSICAL_RECEIVER_REQUIRED", receiver={**self.receiver, "physical_execution": False})

    def test_forged_board_qualification_or_dropped_keepouts_are_rejected(self):
        for changes in ({"board_registration_qualified": True}, {"map_id": "forged"},
                        {"site_review_explicit": 1}, {"scope": "board"}):
            profile = {**self.profile, "installation_binding": {**self.profile["installation_binding"], **changes}}
            self.assert_guard("PROFILE_INSTALLATION_BINDING", receiver={**self.receiver, "profile": profile})
        self.assert_guard("PROFILE_SCOPE", receiver={**self.receiver, "profile": {**self.profile, "map_id": "forged"}})
        installation = {**self.installation, "inflated_keepout_boxes_base_mm": [[3., 3., 99., 4., 4., 101.]]}
        self.assert_guard("LOCAL_CLEARANCE_BINDING", installation=installation)

    def test_local_profile_cannot_migrate_to_board_push_even_with_same_tcp(self):
        board = {
            "installation_id": "board-review", "map_id": "synthetic-map", "map_hash": "b" * 64,
            "calibration_id": "synthetic-calibration", "tcp_id": self.installation["tcp_id"], "tool_id": "synthetic-tool",
            "review_reference": "Synthetic board review fixture.", "qualified": True,
            "workspace_min_mm": [-5., -5., 90.], "workspace_max_mm": [5., 5., 110.],
            "min_tcp_z_mm": 99., "raised_tcp_z_mm": 105.,
            "camera_epoch": "synthetic-camera", "registration_id": "synthetic-registration",
        }
        self.assert_guard("PROFILE_SCOPE", installation=board,
                          command={**self.command, "installation_id": "board-review", "purpose": "push"})

    def test_inspections_remain_read_only_without_arming_or_board_qualification(self):
        for kind in ("inspect_current", "inspect_ik"):
            admit({**self.command, "kind": kind}, self.installation, self.receiver, None,
                  armed=False, now=100., require_profile_binding=True)
        self.assert_guard("RECEIVER_NOT_READY", receiver={**self.receiver, "connected": False})
        self.assert_guard("RECEIVER_BINDING", receiver={**self.receiver, "seq": 2})
        self.assert_guard("INSTALLATION_INVALID", installation={**self.installation, "scope": "unknown"})

    def test_profile_is_complete_for_inherited_policy_but_keeps_rotation_disabled(self):
        self.assertEqual(self.profile["expected_start_tcp_mm_deg"], self.state["actual_pose"])
        self.assertEqual(self.profile["expected_start_joint_deg"], self.state["actual_joint"])
        self.assertFalse(self.profile["rotation_runtime"]["verified"])
        self.assertEqual(self.profile["rotation_edges"], [])
        self.assertEqual(self.profile["rotation_anchors"], [])
        self.assertEqual(set(self.profile["rotation_runtime"]), {
            "verified", "primitive", "controller_version", "argument_semantics", "speed_argument",
            "accel_argument", "completion_timeout_s", "review_reference"})
        self.assertEqual(self.profile["orientations"], [{"id": "measured_current", "rxyz_deg": [180., 0., 0.]}])

    def test_unsafe_state_or_old_profile_import_is_not_normalized(self):
        for state in ({**self.state, "profile": {"old": True}},
                      {**self.state, "actual_pose": [0., 0., 100., 180., 0., 360.]},
                      {**self.state, "actual_pose": [0., 0., 100.1, 180., 0., 0.]},
                      {**self.state, "actual_joint": [True] * 6}):
            with self.subTest(state=state), self.assertRaises((ValueError, GuardError)):
                prepare.build_profile(self.installation, state, on_site_review=True)

    def test_explicit_flag_precedes_inputs_and_policy_precedes_exclusive_write(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            installation, state, output = root / "installation.json", root / "state.json", root / "private/profile.json"
            with patch.object(prepare, "load_runtime") as load, self.assertRaisesRegex(ValueError, "on-site-review"):
                prepare.prepare(installation, state, output)
            load.assert_not_called()
            installation.write_text(json.dumps(self.installation))
            state.write_text(json.dumps(self.state))
            policy = SimpleNamespace(valid=Mock(), MAX_PROFILE_BYTES=8000)
            with patch.object(prepare, "load_runtime", return_value={"policy": policy}):
                result = prepare.prepare(installation, state, output, on_site_review=True)
                self.assertEqual(policy.valid.call_args.args[1], True)
                self.assertEqual(result["scope"], "local_base_commissioning")
                self.assertFalse(result["board_registration_qualified"] or result["motion_issued"] or result["network_contacted"])
                saved = output.read_bytes()
                with self.assertRaises(FileExistsError):
                    prepare.prepare(installation, state, output, on_site_review=True)
                self.assertEqual(output.read_bytes(), saved)
                if os.name != "nt":
                    self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            failed = root / "failed.json"
            policy.valid.side_effect = ValueError("Synthetic inherited policy rejection")
            with patch.object(prepare, "load_runtime", return_value={"policy": policy}), self.assertRaises(ValueError):
                prepare.prepare(installation, state, failed, on_site_review=True)
            self.assertFalse(failed.exists())

    def test_empty_unqualified_local_configuration_cannot_create_profile(self):
        local = LocalBaseInstallation.model_validate({**self.installation, "qualified": False, "on_site_review": False})
        self.assertFalse(local.qualified or local.on_site_review)
        with self.assertRaisesRegex(ValueError, "not qualified"):
            prepare.build_profile(local.model_dump(mode="json"), self.state, on_site_review=True)


class LocalCommissioningApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.journal = Journal(Path(self.directory.name) / "synthetic.sqlite3")
        self.addCleanup(self.journal.close)
        self.installation = synthetic_installation()
        self.receiver = MockReceiver()
        self.receiver.state["actual_pose"] = synthetic_robot_state()["actual_pose"]
        self.receiver.state["profile"] = prepare.build_profile(self.installation, synthetic_robot_state(), on_site_review=True)
        self.service = RobotService(self.journal, self.receiver)
        self.token = "synthetic-local-api-token-not-production"
        self.headers = {"X-PushPilot-Control-Token": self.token}
        self.client = TestClient(create_app(self.service, self.token, manage_lifecycle=False))
        self.addCleanup(self.client.close)

    def binding(self):
        return {key: self.receiver.state[key] for key in ("session_id", "seq", "profile_id")}

    def post(self, path, value):
        return self.client.post(path, headers=self.headers, json=value)

    def test_api_accepts_distinct_local_scope_and_reports_its_limit_without_map_ids(self):
        response = self.post("/v1/installation", self.installation)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["scope"], "local_base_commissioning")
        status = self.client.get("/v1/status", headers=self.headers).json()
        self.assertEqual(status["installation_scope"], "local_base_commissioning")
        self.assertEqual(status["permitted_mutations"], ["fixed_z_orientation_local_translate"])
        self.assertFalse(status["local_scope_qualifies_board_registration"] or status["armed"])
        self.assertEqual(self.receiver.calls, [])
        response = self.post("/v1/arm", {"installation_id": self.installation["installation_id"],
                             "expected_receiver": self.binding(), "reason": "Synthetic local volume arm fixture."})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["scope"], "local_base_commissioning")
        self.assertFalse(response.json()["local_scope_qualifies_board_registration"])
        self.assertEqual(self.receiver.calls, [])

    def test_api_rejects_forced_board_fields_and_unreviewed_local_arm(self):
        for key in ("map_id", "calibration_id", "registration_id"):
            response = self.post("/v1/installation", {**self.installation, key: "forged"})
            self.assertEqual(response.status_code, 422, response.text)
        response = self.post("/v1/installation", {**self.installation, "qualified": False, "on_site_review": False})
        self.assertEqual(response.status_code, 200)
        response = self.post("/v1/arm", {"installation_id": self.installation["installation_id"],
                             "expected_receiver": self.binding(), "reason": "Synthetic unqualified local arm attempt."})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "INSTALLATION_UNQUALIFIED")

    def test_local_arm_rechecks_exact_profile_tool_and_bound_scope(self):
        self.post("/v1/installation", self.installation)
        self.receiver.state["profile"]["installation_binding"]["tcp_definition_sha256"] = "b" * 64
        response = self.post("/v1/arm", {"installation_id": self.installation["installation_id"],
                             "expected_receiver": self.binding(), "reason": "Synthetic changed TCP definition attempt."})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "PROFILE_INSTALLATION_BINDING")
        self.assertFalse(self.service.status()["armed"])

    def test_api_arm_submit_and_complete_one_local_trial_without_board_registration(self):
        self.service.start()
        self.addCleanup(self.service.stop)
        self.assertEqual(self.post("/v1/installation", self.installation).status_code, 200)
        response = self.post("/v1/arm", {"installation_id": self.installation["installation_id"],
                             "expected_receiver": self.binding(), "reason": "Synthetic locally reviewed trial."})
        self.assertEqual(response.status_code, 200, response.text)
        request_id = str(uuid4())
        command = {"request_id": request_id, "kind": "translate", "purpose": "commissioning",
                   "installation_id": self.installation["installation_id"], "expected_receiver": self.binding(),
                   "target": [1., 0., 100., 180., 0., 0.], "timeout_seconds": 3., "admission_timeout_seconds": 5.}
        response = self.post("/v1/commands", command)
        self.assertEqual(response.status_code, 202, response.text)
        deadline = time.monotonic() + 3
        job = None
        while time.monotonic() < deadline:
            job = self.client.get("/v1/commands/" + request_id, headers=self.headers).json()
            if job["state"] == "complete":
                break
            time.sleep(0.01)
        self.assertEqual(job["state"], "complete", job)
        self.assertEqual(len(self.receiver.calls), 1)
        self.assertEqual(self.receiver.calls[0]["purpose"], "commissioning")
        self.assertFalse(job["result"]["physical_execution"])
        self.assertFalse(job["result"]["vehicle_completion_verified"])
        self.assertEqual(self.receiver.state["actual_pose"], command["target"])
        # Same armed scope must reject a relabelled push without executing it.
        forbidden_id = str(uuid4())
        forbidden = {**command, "request_id": forbidden_id, "expected_receiver": self.binding(),
                     "purpose": "push", "expected_visual": "Synthetic forbidden vehicle move."}
        self.assertEqual(self.post("/v1/commands", forbidden).status_code, 202)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            rejected = self.client.get("/v1/commands/" + forbidden_id, headers=self.headers).json()
            if rejected["state"] == "rejected":
                break
            time.sleep(0.01)
        self.assertEqual(rejected["error"], "LOCAL_OPERATION_FORBIDDEN")
        self.assertEqual(len(self.receiver.calls), 1)

    def test_unknown_scope_cannot_fall_back_to_board(self):
        response = self.post("/v1/installation", {**self.installation, "scope": "unknown"})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIsNone(self.service.status()["installation"])

    def test_legacy_board_requests_still_default_to_board_scope(self):
        board = {
            "installation_id": "synthetic-board", "map_id": "synthetic-map", "map_hash": "c" * 64,
            "calibration_id": "synthetic-calibration", "tcp_id": "synthetic-tcp", "tool_id": "synthetic-tool",
            "review_reference": "Synthetic board compatibility fixture.", "qualified": False,
            "workspace_min_mm": [-50., -50., 0.], "workspace_max_mm": [50., 50., 150.],
            "min_tcp_z_mm": 10., "raised_tcp_z_mm": 120.,
            "camera_epoch": "synthetic-camera", "registration_id": "synthetic-registration",
        }
        self.assertEqual(Installation.model_validate(board).scope, "board")
        response = self.post("/v1/installation", board)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["scope"], "board")


if __name__ == "__main__":
    unittest.main()
