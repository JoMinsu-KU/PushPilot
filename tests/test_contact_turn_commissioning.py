"""Synthetic contact-turn commissioning boundaries; no measured site evidence."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.robot_control.api import create_app
from backend.robot_control.gates import GuardError, admit, contact_turn_profile_binding
from backend.robot_control.legacy import load_runtime
from backend.robot_control.mock import MockReceiver
from backend.robot_control.models import LocalContactTurnInstallation, RobotCommand
from backend.robot_control.service import RobotService
from backend.robot_control.store import Journal
from tests.test_local_contact_commissioning import contact_installation
from tests.test_local_commissioning import synthetic_robot_state
from tools.prepare_contact_turn import build_profile
from tools.prepare_local_contact import build_profile as build_contact_profile


def turn_fixture():
    old, state = contact_installation(), synthetic_robot_state()
    # A synthetic full-Euler example proves the API does not assume a pure RZ
    # change. Only the physical receiver's actual IK/FK can validate such poses.
    state["actual_pose"][3:] = [179.8, .1, 0.]
    old["fixed_orientation_deg"] = state["actual_pose"][3:]
    old_profile = build_contact_profile(old, state, on_site_review=True)
    installation = {**deepcopy(old), "scope": "local_contact_turn_commissioning",
        "installation_id": "synthetic-contact-turn",
        "review_reference": "Synthetic new contact-turn review, not actual tool or clearance evidence.",
        "contact_turn_trials_authorized": True, "max_rotation_increment_deg": 10.,
        "orientations": [{"id": "current", "rxyz_deg": state["actual_pose"][3:]},
                         {"id": "wrist-next", "rxyz_deg": [179.79, .12, 10.]}],
        "rotation_anchors": [{"id": "local-anchor", "xyz_base_mm": state["actual_pose"][:3],
            "site_verified": True, "review_reference": "Synthetic full gripper, arm, cable and contact sweep review.",
            "position_window_mm": .5, "max_in_place_correction_mm": .1, "window_and_correction_reviewed": True}],
        "rotation_edges": [{"id": "current-next", "from": "current", "to": "wrist-next", "anchor_id": "local-anchor",
            "site_verified": True, "review_reference": "Synthetic one directed wrist-only contact experiment review.",
            "expected_source_joint_deg": [0.]*6, "expected_target_joint_deg": [0.]*5+[10.],
            "wrist_only": True, "joint_path_reviewed": True}],
        "rotation_runtime": {"verified": True, "primitive": "moveJoint_wrist", "controller_version": "synthetic-only",
            "argument_semantics": "Synthetic degree units; actual installation must supply independent controller evidence.",
            "speed_argument": 3., "accel_argument": 5., "completion_timeout_s": 60.,
            "review_reference": "Synthetic runtime semantics fixture, not a physical qualification."}}
    installation = LocalContactTurnInstallation.model_validate(installation).model_dump(mode="json", by_alias=True)
    profile = build_profile(installation, state, on_site_review=True)
    receiver = {"connected": True, "idle": True, "physical_execution": True,
        "session_id": "synthetic-contact-turn-session", "seq": 1, "profile_id": "synthetic-turn-profile",
        **state, "profile": profile}
    command = {"kind": "rotate", "purpose": "contact_turn_trial", "installation_id": installation["installation_id"],
        "expected_receiver": {key: receiver[key] for key in ("session_id", "seq", "profile_id")},
        "target": [*state["actual_pose"][:3], 179.79, .12, 10.], "edge_id": "current-next",
        "expected_visual": "Synthetic small contact-turn response with no unobserved arrival claim."}
    return installation, receiver, command, old_profile


class ContactTurnAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.local, self.receiver, self.command, self.old = turn_fixture()

    def gate(self, *, local=None, receiver=None, command=None, armed=True, held=False):
        admit(command or self.command, local or self.local, receiver or self.receiver,
              None, armed=armed, held=held, now=100., require_profile_binding=True)

    def reject(self, code, **kwargs):
        with self.assertRaises(GuardError) as caught:
            self.gate(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def translation(self):
        return {**self.command, "kind": "translate", "edge_id": None,
                "target": [5., 0., *self.receiver["actual_pose"][2:]]}

    def handoff(self):
        return {**self.command, "kind": "profile_update", "purpose": "commissioning", "target": None,
                "edge_id": None, "profile": deepcopy(self.receiver["profile"])}

    def test_explicit_experimental_full_euler_rotation_and_translation(self):
        self.gate()
        self.gate(command=self.translation())
        RobotCommand.model_validate({**self.command, "request_id": str(uuid4())})
        binding = self.receiver["profile"]["installation_binding"]
        self.assertFalse(binding["car_turn_qualified"] or binding["vehicle_control_qualified"] or binding["board_registration_qualified"])
        self.assertNotIn("map_id", binding)

    def test_default_rejects_missing_authorization_and_fake_registration(self):
        for changes in ({"contact_turn_trials_authorized": False}, {"contact_trials_authorized": False},
                        {"on_site_review": False}, {"map_id": "fake"}, {"car_removed": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                LocalContactTurnInstallation.model_validate({**self.local, **changes})
        self.reject("INSTALLATION_UNQUALIFIED", local={**self.local, "qualified": False})
        unqualified = {**self.local, "qualified": False}
        unqualified.pop("contact_turn_trials_authorized")
        self.assertFalse(LocalContactTurnInstallation.model_validate(unqualified).contact_turn_trials_authorized)

    def test_no_purpose_disguise_or_missing_expected_outcome(self):
        for purpose in ("commissioning", "push", "contact_trial", "tool_reposition"):
            self.reject("CONTACT_TURN_OPERATION_FORBIDDEN", command={**self.command, "purpose": purpose})
        self.reject("CONTACT_EXPECTED_OUTCOME_REQUIRED", command={**self.command, "expected_visual": " "})
        with self.assertRaises(ValueError):
            RobotCommand.model_validate({**self.command, "request_id": str(uuid4()), "expected_visual": " "})
        self.reject("NOT_ARMED", armed=False)
        self.reject("NOT_ARMED", held=True)

    def test_no_combined_motion_unknown_edge_or_source_substitution(self):
        self.reject("ROTATION_TRANSLATES", command={**self.command, "target": [1., *self.command["target"][1:]]})
        changed = self.command["target"][:]
        changed[2] += .000001
        self.reject("LOCAL_Z_CHANGED", command={**self.command, "target": changed})
        self.reject("ORIENTATION_CHANGED", command={**self.translation(), "target": [5., 0., 100., 179.8, .1, 1.]})
        self.reject("ROTATION_EDGE", command={**self.command, "edge_id": "unknown"})
        self.reject("ROTATION_EDGE", command={**self.command, "target": [0., 0., 100., 179.79, .12, 9.]})
        self.reject("ROTATION_SOURCE_CHANGED", receiver={**self.receiver, "actual_joint": [.51]+[0.]*5})
        self.reject("RECEIVER_BINDING", receiver={**self.receiver, "seq": 2})

    def test_tiny_actual_baseline_difference_never_authorizes_target_z_or_orientation_delta(self):
        receiver = deepcopy(self.receiver)
        receiver["actual_pose"][2] += .05
        self.reject("LOCAL_Z_CHANGED", receiver=receiver)
        translation = self.translation()
        translation["target"][2] = receiver["actual_pose"][2]
        self.gate(command=translation, receiver=receiver)

    def test_runtime_and_joint_edge_limits_are_not_relaxed(self):
        for field, value in (("primitive", "moveLinear_tcp"), ("verified", False), ("speed_argument", 3.1),
                             ("accel_argument", 5.1), ("completion_timeout_s", 14.99)):
            changed = deepcopy(self.local)
            changed["rotation_runtime"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                LocalContactTurnInstallation.model_validate(changed)
        for field, value in (("wrist_only", False), ("joint_path_reviewed", False),
                             ("expected_target_joint_deg", [1.]+[0.]*4+[10.]),
                             ("expected_target_joint_deg", [0.]*5+[10.000001])):
            changed = deepcopy(self.local)
            changed["rotation_edges"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                LocalContactTurnInstallation.model_validate(changed)
        with self.assertRaises(ValueError):
            LocalContactTurnInstallation.model_validate({**self.local, "max_rotation_increment_deg": 90.000001})

    def test_envelope_anchor_step_keepout_and_review_binding_fail_closed(self):
        self.reject("STEP_LIMIT", command={**self.translation(), "target": [5.000001, 0., *self.receiver["actual_pose"][2:]]})
        self.reject("OUTSIDE_WORKSPACE", command={**self.translation(), "target": [201., 0., *self.receiver["actual_pose"][2:]]})
        receiver = deepcopy(self.receiver)
        receiver["actual_pose"][0] = .500001
        self.reject("ROTATION_ANCHOR", receiver=receiver, command={**self.command, "target": [.500001, *self.command["target"][1:]]})
        receiver = deepcopy(self.receiver)
        receiver["profile"]["rotation_edges"][0]["expected_target_joint_deg"][5] = 9.
        self.reject("CONTACT_TURN_REVIEW_BINDING", receiver=receiver)
        local, receiver = deepcopy(self.local), deepcopy(self.receiver)
        local["inflated_keepout_boxes_base_mm"] = [[2., -1., 99., 3., 1., 101.]]
        receiver["profile"]["inflated_keepout_boxes_base_mm"] = local["inflated_keepout_boxes_base_mm"]
        receiver["profile"]["installation_binding"] = contact_turn_profile_binding(local)
        self.reject("CROSSES_KEEPOUT", local=local, receiver=receiver, command=self.translation())

    def test_handoff_requires_hold_new_review_exact_fresh_baseline_same_tool(self):
        receiver = {**self.receiver, "profile": self.old}
        self.gate(command=self.handoff(), receiver=receiver, armed=False, held=True)
        self.reject("LOCAL_REFRESH_REQUIRES_HOLD", command=self.handoff(), receiver=receiver)
        self.reject("LOCAL_REFRESH_NEW_REVIEW_REQUIRED", command=self.handoff(), armed=False, held=True)
        command = self.handoff()
        command["profile"]["expected_start_joint_deg"][0] += .000001
        self.reject("LOCAL_REFRESH_BASELINE_CHANGED", command=command, receiver=receiver, armed=False, held=True)
        receiver = deepcopy(receiver)
        receiver["profile"]["installation_binding"]["tcp_definition_sha256"] = "b"*64
        self.reject("CONTACT_TURN_TOOL_BINDING", command=self.handoff(), receiver=receiver, armed=False, held=True)

    def test_handoff_back_to_fixed_contact_keeps_exact_current_orientation(self):
        state = {key: self.receiver[key] for key in ("actual_pose", "actual_joint")}
        local = contact_installation()
        local.update(installation_id="synthetic-return-contact", review_reference="Synthetic new fixed-contact return review.",
                     fixed_orientation_deg=state["actual_pose"][3:])
        profile = build_contact_profile(local, state, on_site_review=True)
        self.gate(local=local, command={**self.handoff(), "installation_id": local["installation_id"], "profile": profile}, armed=False, held=True)

    def test_builder_requires_actual_flag_and_exact_baseline(self):
        state = {key: self.receiver[key] for key in ("actual_pose", "actual_joint")}
        with self.assertRaises(ValueError):
            build_profile(self.local, state)
        changed = deepcopy(state)
        changed["actual_pose"][3] += .000001
        with self.assertRaises(ValueError):
            build_profile(self.local, changed, on_site_review=True)

    def test_inherited_runtime_validation_and_exact_fk_preflight_remain_independent(self):
        path = Path(__file__).resolve().parents[1]/"runtime/robot-control/receiver"
        if not path.exists():
            self.skipTest("Optional private installed runtime is not distributed.")
        runtime = load_runtime(path)
        policy, profile = runtime["policy"], self.receiver["profile"]
        policy.valid(profile, True)
        policy.profile_update(self.old, profile, True, self.receiver["actual_pose"], self.receiver["actual_pose"], self.receiver["actual_joint"])
        policy.operation(profile, self.receiver["actual_pose"], self.command["target"], "rotate", self.command["edge_id"], True,
                         self.receiver["actual_joint"], self.receiver["actual_pose"], native_joint_sample=True)
        # Valid schema/edge data never fabricates the actual controller FK report.
        with self.assertRaises(ValueError):
            runtime["wrist"].validate_preflight({"primitive": "moveJoint_wrist", "source_joint": [0.]*6,
                "target_joint": [0.]*5+[10.], "fk_samples": []}, profile, self.command)


class ContactTurnServiceTests(unittest.TestCase):
    def test_api_rotational_trial_is_robot_only_then_held_without_replay(self):
        local, receiver, command, _ = turn_fixture()
        with TemporaryDirectory() as directory:
            journal = Journal(Path(directory)/"control.sqlite3")
            backend = MockReceiver()
            backend.state = deepcopy(receiver)
            service = RobotService(journal, backend)
            service.start()
            headers = {"X-PushPilot-Control-Token": "t"*40}
            try:
                with TestClient(create_app(service, "t"*40, manage_lifecycle=False)) as client:
                    response = client.post("/v1/installation", headers=headers, json=local)
                    self.assertEqual(response.status_code, 200, response.text)
                    status = service.status()
                    self.assertIn("experimental_reviewed_fixed_xyz_wrist_rotation", status["permitted_mutations"])
                    self.assertEqual(status["permitted_held_mutations"], ["local_contact_turn_profile_handoff"])
                    service.arm({"installation_id": local["installation_id"], "expected_receiver": command["expected_receiver"],
                                 "reason": "Synthetic explicit experiment arm only."})
                    request = {**command, "request_id": str(uuid4()), "timeout_seconds": 3., "admission_timeout_seconds": 3.}
                    response = client.post("/v1/commands", headers=headers, json=request)
                    self.assertEqual(response.status_code, 202, response.text)
                    deadline = time.monotonic()+3
                    while time.monotonic() < deadline:
                        job = journal.get(request["request_id"])
                        if job["state"] in {"complete", "rejected", "outcome_unknown"}:
                            break
                        time.sleep(.01)
                    self.assertEqual(job["state"], "complete", job)
                    self.assertTrue(job["result"]["contact_turn_trial"])
                    self.assertFalse(job["result"]["car_turn_qualified"] or job["result"]["vehicle_completion_verified"])
                    self.assertEqual(job["result"]["vehicle_outcome"], "unassessed")
                    self.assertTrue(service.status()["hold"])
                    self.assertFalse(service.status()["armed"])
                    self.assertEqual(len(backend.calls), 1)
            finally:
                service.stop()
                journal.close()


if __name__ == "__main__":
    unittest.main()
