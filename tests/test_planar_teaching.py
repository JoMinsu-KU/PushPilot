"""Synthetic noncontact teaching review/admission tests; no physical authority."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from backend.robot_control.api import create_app
from backend.robot_control.gates import GuardError, admit, planar_teaching_profile_binding
from backend.robot_control.legacy import load_runtime
from backend.robot_control.mock import MockReceiver
from backend.robot_control.models import PlanarTeachingInstallation
from backend.robot_control.service import RobotService
from backend.robot_control.store import Journal
from tests.test_local_commissioning import synthetic_installation, synthetic_robot_state
from tools.prepare_local_commissioning import build_profile


def teaching_fixture():
    base, state = synthetic_installation(), synthetic_robot_state()
    installation = {key: value for key, value in base.items() if key != "fixed_orientation_deg"}
    installation.update(
        scope="planar_teaching", installation_id="synthetic-planar-teaching",
        review_reference="Synthetic new planar sweep review; never actual hardware evidence.",
        car_removed=True, noncontact_teaching_authorized=True,
        workspace_min_mm=[-250., -200., 99.5], workspace_max_mm=[250., 200., 100.5],
        fixed_roll_pitch_deg=[180., 0.], max_step_mm=20., max_speed_mm_s=5., max_accel_mm_s2=10.,
        orientations=[{"id": "east", "rxyz_deg": [180., 0., 0.]}, {"id": "north", "rxyz_deg": [180., 0., 90.]}],
        rotation_anchors=[{"id": "junction", "xyz_base_mm": [0., 0., 100.], "site_verified": True,
                           "review_reference": "Synthetic tool, arm and cable swept-window review.",
                           "position_window_mm": 2., "max_in_place_correction_mm": .5,
                           "window_and_correction_reviewed": True}],
        rotation_edges=[{"id": "east-north", "from": "east", "to": "north", "anchor_id": "junction",
                         "site_verified": True, "review_reference": "Synthetic directed wrist-edge clearance review.",
                         "expected_source_joint_deg": [0.]*6, "expected_target_joint_deg": [0.]*5+[90.],
                         "wrist_only": True, "joint_path_reviewed": True}],
        rotation_runtime={"verified": True, "primitive": "moveJoint_wrist", "controller_version": "synthetic-only",
                          "argument_semantics": "Synthetic known degree units; not physical runtime validation.",
                          "speed_argument": 5., "accel_argument": 10., "completion_timeout_s": 60.,
                          "review_reference": "Synthetic runtime evidence fixture only."})
    installation = PlanarTeachingInstallation.model_validate(installation).model_dump(mode="json", by_alias=True)
    old = build_profile(base, state, on_site_review=True)
    profile = {**deepcopy(old), "scope": "planar_teaching",
               "tcp_bounds_base_mm": installation["workspace_min_mm"]+installation["workspace_max_mm"],
               "translation_speed_mm_s": 5., "translation_accel_mm_s2": 10., "max_translation_mm": 20.,
               "review_reference": installation["review_reference"],
               "installation_binding": planar_teaching_profile_binding(deepcopy(installation))}
    for key in ("orientations", "rotation_anchors", "rotation_edges", "rotation_runtime"):
        profile[key] = deepcopy(installation[key])
    receiver = {"connected": True, "idle": True, "physical_execution": True,
                "session_id": "synthetic-teaching-session", "seq": 1, "profile_id": "synthetic-profile",
                **state, "profile": profile}
    command = {"kind": "translate", "purpose": "commissioning", "installation_id": installation["installation_id"],
               "expected_receiver": {key: receiver[key] for key in ("session_id", "seq", "profile_id")},
               "target": [10., 0., 100., 180., 0., 0.]}
    return installation, receiver, command, old


class PlanarTeachingAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.installation, self.receiver, self.command, self.old = teaching_fixture()

    def gate(self, *, command=None, installation=None, receiver=None, armed=True, held=False):
        admit(command or self.command, installation or self.installation, receiver or self.receiver,
              None, armed=armed, held=held, now=100., require_profile_binding=True)

    def rejects(self, code, **kwargs):
        with self.assertRaises(GuardError) as caught:
            self.gate(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def rotation(self):
        return {**self.command, "kind": "rotate", "purpose": "tool_reposition", "edge_id": "east-north",
                "target": [0., 0., 100., 180., 0., 90.]}

    def handoff(self):
        return {key: value for key, value in {**self.command, "kind": "profile_update", "target": None,
                "profile": deepcopy(self.receiver["profile"])}.items()}

    def test_named_teaching_has_no_board_contact_or_camera_claim(self):
        self.gate()
        self.gate(command=self.rotation())
        binding = self.receiver["profile"]["installation_binding"]
        self.assertFalse(binding["board_registration_qualified"] or binding["vehicle_control_qualified"] or binding["car_turn_qualified"])
        for key in ("map_id", "map_hash", "calibration_id", "camera_epoch", "registration_id"):
            self.assertNotIn(key, binding)
            with self.subTest(key=key), self.assertRaises(ValueError):
                PlanarTeachingInstallation.model_validate({**self.installation, key: "forged"})

    def test_no_combined_yaw_translation_or_vertical_roll_pitch_motion(self):
        self.rejects("ORIENTATION_CHANGED", command={**self.command, "target": [10., 0., 100., 180., 0., 90.]})
        self.rejects("ROTATION_TRANSLATES", command={**self.rotation(), "target": [1., 0., 100., 180., 0., 90.]})
        self.rejects("TEACHING_Z_CHANGED", command={**self.command, "target": [10., 0., 100.000001, 180., 0., 0.]})
        self.rejects("TEACHING_ROLL_PITCH_CHANGED", command={**self.rotation(), "target": [0., 0., 100., 179.999999, 0., 90.]})

    def test_no_contact_purpose_or_unarmed_execution(self):
        for purpose in ("push", "contact_trial", "tool_reposition"):
            self.rejects("TEACHING_OPERATION_FORBIDDEN", command={**self.command, "purpose": purpose})
        self.rejects("NOT_ARMED", armed=False)
        self.rejects("NOT_ARMED", held=True)

    def test_source_binding_and_joint_anchor_edge_fail_closed(self):
        self.rejects("RECEIVER_BINDING", receiver={**self.receiver, "seq": 2})
        self.rejects("ROTATION_EDGE", command={**self.rotation(), "edge_id": "unknown"})
        self.rejects("ROTATION_EDGE", command={**self.rotation(), "target": [0., 0., 100., 180., 0., 89.]})
        self.rejects("ROTATION_SOURCE_CHANGED", command=self.rotation(), receiver={**self.receiver, "actual_joint": [0.]*5+[.51]})
        self.rejects("ROTATION_ANCHOR", command={**self.rotation(), "target": [3., 0., 100., 180., 0., 90.]},
                     receiver={**self.receiver, "actual_pose": [3., 0., 100., 180., 0., 0.]})

    def test_actual_review_cannot_be_inferred_from_permission_or_profile(self):
        for key in ("on_site_review", "car_removed", "noncontact_teaching_authorized"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                PlanarTeachingInstallation.model_validate({**self.installation, key: False})
        self.rejects("INSTALLATION_UNQUALIFIED", installation={**self.installation, "qualified": False})
        for changes in ({"site_verified": False}, {"scope": "board"}, {"map_id": "forged"},
                        {"board_registration_qualified": True}, {"vehicle_control_qualified": True},
                        {"coordinate_frame": "drawing_mm"}):
            self.rejects("PROFILE_UNQUALIFIED" if "site_verified" in changes else "PROFILE_SCOPE",
                         receiver={**self.receiver, "profile": {**self.receiver["profile"], **changes}})

    def test_bounds_step_keepouts_and_complete_geometry_binding(self):
        self.rejects("OUTSIDE_WORKSPACE", command={**self.command, "target": [251., 0., 100., 180., 0., 0.]})
        self.rejects("STEP_LIMIT", command={**self.command, "target": [20.000001, 0., 100., 180., 0., 0.]})
        self.rejects("STEP_LIMIT", command={**self.command, "target": self.receiver["actual_pose"]})
        changed = deepcopy(self.receiver)
        changed["profile"]["rotation_anchors"][0]["position_window_mm"] = 3.
        self.rejects("TEACHING_REVIEW_BINDING", receiver=changed)
        changed = deepcopy(self.receiver)
        changed["profile"]["installation_binding"]["on_site_review"] = 1
        self.rejects("PROFILE_INSTALLATION_BINDING", receiver=changed)
        installation = deepcopy(self.installation)
        installation["inflated_keepout_boxes_base_mm"] = [[4., -1., 99.5, 6., 1., 100.5]]
        receiver = deepcopy(self.receiver)
        receiver["profile"]["inflated_keepout_boxes_base_mm"] = deepcopy(installation["inflated_keepout_boxes_base_mm"])
        receiver["profile"]["installation_binding"] = planar_teaching_profile_binding(installation)
        self.rejects("CROSSES_KEEPOUT", installation=installation, receiver=receiver)

    def test_model_cannot_increase_caps_or_fabricate_rotation_review(self):
        for change in ({"workspace_max_mm": [751., 200., 100.5]}, {"workspace_max_mm": [250., 200., 101.6]},
                       {"max_step_mm": 20.1}, {"max_speed_mm_s": 10.1}, {"max_accel_mm_s2": 20.1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                PlanarTeachingInstallation.model_validate({**self.installation, **change})
        for key, field in (("rotation_anchors", "site_verified"), ("rotation_edges", "joint_path_reviewed")):
            changed = deepcopy(self.installation)
            changed[key][0][field] = False
            with self.subTest(key=key), self.assertRaises(ValueError):
                PlanarTeachingInstallation.model_validate(changed)
        changed = deepcopy(self.installation)
        changed["rotation_runtime"]["verified"] = False
        with self.assertRaises(ValueError):
            PlanarTeachingInstallation.model_validate(changed)

    def test_handoff_is_held_disarmed_exact_new_review_no_motion(self):
        receiver = {**self.receiver, "profile": self.old}
        self.gate(command=self.handoff(), receiver=receiver, armed=False, held=True)
        self.rejects("TEACHING_REFRESH_REQUIRES_HOLD", command=self.handoff(), receiver=receiver)
        stale = self.handoff()
        stale["profile"]["expected_start_joint_deg"][5] = .01
        self.rejects("TEACHING_BASELINE_CHANGED", command=stale, receiver=receiver, armed=False, held=True)
        changed_tool = deepcopy(receiver)
        changed_tool["profile"]["installation_binding"]["tcp_definition_sha256"] = "b"*64
        self.rejects("TEACHING_TOOL_BINDING", command=self.handoff(), receiver=changed_tool, armed=False, held=True)
        self.rejects("TEACHING_NEW_REVIEW_REQUIRED", command=self.handoff(), armed=False, held=True)
        self.rejects("TEACHING_OPERATION_FORBIDDEN", command={**self.handoff(), "target": self.command["target"]},
                     receiver=receiver, armed=False, held=True)
        self.rejects("PROFILE_SCOPE", command=self.handoff(), receiver={**receiver, "profile": {**self.old, "scope": "board"}}, armed=False, held=True)

    def test_existing_inherited_policy_accepts_genuine_scope_without_changes(self):
        runtime_path = Path(__file__).resolve().parents[1]/"runtime/robot-control/receiver"
        if not runtime_path.exists():
            self.skipTest("Optional private installed runtime is not distributed with the standalone repository.")
        runtime = load_runtime(runtime_path)
        policy = runtime["policy"]
        profile = self.receiver["profile"]
        policy.valid(profile, True)
        policy.profile_update(self.old, profile, True, self.receiver["actual_pose"], self.receiver["actual_pose"], self.receiver["actual_joint"])
        policy.operation(profile, self.receiver["actual_pose"], self.command["target"], "translate", motion=True)
        policy.operation(profile, self.receiver["actual_pose"], self.rotation()["target"], "rotate", "east-north", True,
                         self.receiver["actual_joint"], self.receiver["actual_pose"], native_joint_sample=True)
        with self.assertRaises(ValueError):
            policy.operation(profile, self.receiver["actual_pose"], [1., 0., 100., 180., 0., 90.], "translate", motion=True)


class PlanarTeachingApiTests(unittest.TestCase):
    def test_scope_parses_reports_exact_capabilities_and_does_not_arm(self):
        installation, receiver, _, _ = teaching_fixture()
        with TemporaryDirectory() as directory:
            journal = Journal(Path(directory)/"control.sqlite3")
            backend = MockReceiver()
            backend.state = deepcopy(receiver)
            service = RobotService(journal, backend, physical=True)
            headers = {"X-PushPilot-Control-Token": "t"*40}
            with TestClient(create_app(service, "t"*40, manage_lifecycle=False)) as client:
                result = client.post("/v1/installation", headers=headers, json=installation)
                self.assertEqual(result.status_code, 200, result.text)
                status = client.get("/v1/status", headers=headers).json()
                self.assertEqual(status["installation_scope"], "planar_teaching")
                self.assertEqual(status["permitted_mutations"], ["fixed_z_translate", "reviewed_fixed_xyz_yaw_rotation"])
                self.assertEqual(status["permitted_held_mutations"], ["planar_teaching_profile_handoff"])
                self.assertFalse(status["armed"] or status["local_scope_qualifies_board_registration"])
                self.assertEqual(backend.calls, [])
                result = client.post("/v1/arm", headers=headers, json={"installation_id": installation["installation_id"],
                    "expected_receiver": {key: receiver[key] for key in ("session_id", "seq", "profile_id")},
                    "reason": "Synthetic teaching arm check; no command submitted."})
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(backend.calls, [])
            journal.close()


if __name__ == "__main__":
    unittest.main()
