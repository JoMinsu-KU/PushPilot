"""Equipment-free commissioning admission and observation-failure boundaries."""
from copy import deepcopy
import unittest

from backend.robot_control.gates import GuardError, admit


class RobotControlGateTests(unittest.TestCase):
    def setUp(self):
        self.installation = {
            "installation_id": "installation-test", "map_id": "map-test", "map_hash": "map-hash",
            "calibration_id": "calibration-test", "tcp_id": "tcp-test", "tool_id": "tool-test",
            "review_reference": "Synthetic installation review", "qualified": True,
            "workspace_min_mm": [-100, -100, 0], "workspace_max_mm": [100, 100, 150],
            "min_tcp_z_mm": 10, "raised_tcp_z_mm": 50,
            "camera_epoch": "camera-test", "registration_id": "registration-test",
        }
        self.receiver = {
            "connected": True, "stage": "idle", "session_id": "receiver-test", "seq": 7,
            "profile_id": "profile-test", "physical_execution": True,
            "actual_pose": [0, 0, 15, 180, 0, 0],
            "profile": {"tcp_id": "tcp-test", "allow_motion": True, "site_verified": True,
                        "translation_speed_mm_s": 15, "translation_accel_mm_s2": 30,
                        "rotation_edges": [{"id": "edge-test", "site_verified": True,
                                            "review_reference": "Synthetic raised sweep review"}]},
        }
        self.command = {
            "kind": "translate", "purpose": "push", "installation_id": "installation-test",
            "expected_receiver": {key: self.receiver[key] for key in ("session_id", "seq", "profile_id")},
            "target": [10, 0, 15, 180, 0, 0], "timeout_seconds": 60,
        }
        self.observation = {
            **{key: self.installation[key] for key in ("installation_id", "map_id", "map_hash", "calibration_id",
                                                        "camera_epoch", "registration_id")},
            "observation_id": "observation-test", "frame_id": "frame-test", "frame_sha256": "a" * 64,
            "captured_at": 99.0, "view_status": "fixed", "marker_count": 4,
            "car_visible": True, "car_pose": [1, 2, 0],
        }

    def gate(self, command=None, installation=None, receiver=None, observation=None, **kwargs):
        admit(command or self.command, installation or self.installation, receiver or self.receiver,
              self.observation if observation is None else observation, armed=kwargs.get("armed", True), now=100.0,
              require_profile_binding=kwargs.get("require_profile_binding", False))

    def assert_guard(self, code, *, retryable=False, **kwargs):
        with self.assertRaises(GuardError) as error:
            self.gate(**kwargs)
        self.assertEqual(error.exception.code, code)
        self.assertEqual(error.exception.retryable, retryable)

    def test_zero_markers_do_not_block_visible_car_under_same_fixed_registration(self):
        for count in (0, 1, 4):
            with self.subTest(count=count):
                observation = {**self.observation, "view_status": "marker_occluded", "marker_count": count}
                self.gate(observation=observation)

    def test_unknown_car_or_stale_image_waits_without_new_motion_authority(self):
        for change in ({"car_visible": False}, {"car_pose": None}, {"car_pose": [1, float("nan"), 0]},
                       {"captured_at": 89.9}, {"captured_at": 101}, {"captured_at": True}):
            with self.subTest(change=change):
                self.assert_guard("WAIT_OBSERVATION", retryable=True, observation={**self.observation, **change})
        with self.assertRaises(GuardError) as error:
            admit(self.command, self.installation, self.receiver, None, armed=True, now=100)
        self.assertEqual((error.exception.code, error.exception.retryable), ("WAIT_OBSERVATION", True))

    def test_contradictory_view_or_identity_requires_review(self):
        for status in ("view_changed", "unregistered", "unknown"):
            self.assert_guard("VIEW_CHANGED", observation={**self.observation, "view_status": status})
        for key in ("installation_id", "map_id", "map_hash", "calibration_id", "camera_epoch", "registration_id"):
            self.assert_guard("OBSERVATION_BINDING", observation={**self.observation, key: "different"})

    def test_receiver_binding_and_mode_are_exact(self):
        for key, value in (("session_id", "new"), ("seq", 8), ("profile_id", "new"), ("seq", True)):
            self.assert_guard("RECEIVER_BINDING", receiver={**self.receiver, key: value})
        self.assert_guard("RECEIVER_NOT_READY", receiver={**self.receiver, "connected": False})
        self.assert_guard("RECEIVER_NOT_READY", receiver={**self.receiver, "stage": "moving"})
        self.assert_guard("PHYSICAL_RECEIVER_REQUIRED", receiver={**self.receiver, "physical_execution": False})

    def test_inspection_needs_binding_but_no_arm_or_installation(self):
        command = {**self.command, "kind": "inspect_current", "installation_id": None, "target": None}
        admit(command, None, {**self.receiver, "physical_execution": False}, None, armed=False, now=100)
        command.update(kind="inspect_ik", target=[10, 0, 15, 180, 0, 0])
        admit(command, None, self.receiver, None, armed=False, now=100)
        command["target"][0] = float("inf")
        self.assert_guard("TARGET_INVALID", command=command)

    def test_receiver_idle_boolean_is_supported_without_stage(self):
        receiver = {**self.receiver, "idle": True}
        receiver.pop("stage")
        self.gate(receiver=receiver)
        receiver["idle"] = False
        self.assert_guard("RECEIVER_NOT_READY", receiver=receiver)

    def test_arming_and_qualified_installation_are_mandatory(self):
        self.assert_guard("NOT_ARMED", armed=False)
        self.assert_guard("INSTALLATION_UNQUALIFIED", installation={**self.installation, "qualified": False})
        self.assert_guard("INSTALLATION_MISMATCH", command={**self.command, "installation_id": "old"})
        for key in ("calibration_id", "tcp_id", "tool_id", "review_reference"):
            self.assert_guard("INSTALLATION_INVALID", installation={**self.installation, key: ""})

    def test_translations_hold_orientation_and_separate_vertical_from_lateral(self):
        self.assert_guard("LIFT_LATERAL_COMBINED", command={**self.command, "target": [10, 0, 20, 180, 0, 0]})
        self.assert_guard("ORIENTATION_CHANGED", command={**self.command, "target": [10, 0, 15, 180, 0, 90]})
        self.gate(command={**self.command, "purpose": "tool_reposition", "target": [0, 0, 25, 180, 0, 0]}, observation={})

    def test_bounds_minimum_height_and_step_limit_apply_to_source_and_target(self):
        self.assert_guard("OUTSIDE_WORKSPACE", command={**self.command, "target": [101, 0, 15, 180, 0, 0]})
        self.assert_guard("OUTSIDE_WORKSPACE", receiver={**self.receiver, "actual_pose": [-101, 0, 15, 180, 0, 0]})
        self.assert_guard("BELOW_WORKING_Z", command={**self.command, "target": [0, 0, 9, 180, 0, 0]})
        self.assert_guard("STEP_LIMIT", command={**self.command, "target": [31, 0, 15, 180, 0, 0]})
        self.assert_guard("TARGET_INVALID", command={**self.command, "target": [True, 0, 15, 180, 0, 0]})

    def test_receiver_profile_limits_cannot_bypass_installation(self):
        for key, value, code in (("translation_speed_mm_s", 16, "PROFILE_LIMIT"),
                                 ("translation_accel_mm_s2", 31, "PROFILE_LIMIT"),
                                 ("translation_speed_mm_s", True, "PROFILE_LIMIT"),
                                 ("tcp_id", "different", "TCP_MISMATCH"),
                                 ("site_verified", False, "PROFILE_UNQUALIFIED")):
            self.assert_guard(code, receiver={**self.receiver, "profile": {**self.receiver["profile"], key: value}})
        self.assert_guard("PROFILE_REQUIRED", receiver={**self.receiver, "profile": None})

    def test_profile_update_is_explicit_and_cannot_expand_installation(self):
        profile = {**deepcopy(self.receiver["profile"]), "tcp_bounds_base_mm": [-20, -20, 10, 20, 20, 60]}
        command = {**self.command, "kind": "profile_update", "purpose": "commissioning", "profile": profile, "target": None}
        self.gate(command=command, observation={})
        self.assert_guard("PROFILE_REQUIRED", command={**command, "profile": None})
        self.assert_guard("PROFILE_BOUNDS", command={**command, "profile": {**profile, "tcp_bounds_base_mm": [-101, -20, 10, 20, 20, 60]}})
        self.assert_guard("PROFILE_BOUNDS", command={**command, "profile": {**profile, "tcp_bounds_base_mm": [20, -20, 10, 20, 20, 60]}})
        self.assert_guard("PROFILE_UNQUALIFIED", command={**command, "profile": {**profile, "allow_motion": False}})

    def test_wrist_rotation_is_raised_reviewed_tool_reposition_only(self):
        receiver = {**self.receiver, "actual_pose": [0, 0, 50, 180, 0, 0]}
        command = {**self.command, "kind": "rotate", "purpose": "tool_reposition", "target": [0, 0, 50, 180, 0, 90], "edge_id": "edge-test"}
        self.gate(command=command, receiver=receiver, observation={})
        self.assert_guard("ROTATION_PURPOSE", command={**command, "purpose": "push"}, receiver=receiver)
        self.assert_guard("ROTATION_NOT_RAISED", command={**command, "target": [0, 0, 15, 180, 0, 90]})
        self.assert_guard("ROTATION_TRANSLATES", command={**command, "target": [1, 0, 50, 180, 0, 90]}, receiver=receiver)
        self.assert_guard("ROTATION_EDGE", command={**command, "edge_id": "unreviewed"}, receiver=receiver)

    def test_installation_caps_and_original_frame_identity_are_validated(self):
        for key, value in (("max_step_mm", 101), ("max_speed_mm_s", 101), ("max_accel_mm_s2", 501),
                           ("observation_max_age_seconds", 61), ("max_step_mm", True)):
            self.assert_guard("INSTALLATION_INVALID", installation={**self.installation, key: value})
        for change in ({"frame_sha256": "not-a-hash"}, {"marker_count": True}, {"observation_id": ""}):
            self.assert_guard("OBSERVATION_INVALID", observation={**self.observation, **change})

    def measured_binding(self):
        return {**{key: self.installation[key] for key in (
            "installation_id", "map_id", "map_hash", "calibration_id", "tcp_id", "tool_id",
            "camera_epoch", "registration_id")}, "site_review_explicit": True}

    def test_physical_motion_rejects_old_profile_despite_matching_tcp(self):
        self.assert_guard("PROFILE_INSTALLATION_BINDING", require_profile_binding=True)
        receiver = deepcopy(self.receiver)
        binding = self.measured_binding()
        receiver["profile"]["installation_binding"] = binding
        self.gate(receiver=receiver, require_profile_binding=True)
        for key in ("installation_id", "map_id", "map_hash", "calibration_id", "tcp_id", "tool_id",
                    "camera_epoch", "registration_id"):
            receiver["profile"]["installation_binding"] = {**binding, key: "historical"}
            self.assert_guard("PROFILE_INSTALLATION_BINDING", receiver=receiver, require_profile_binding=True)
        for value in (False, 1, "true", None):
            receiver["profile"]["installation_binding"] = {**binding, "site_review_explicit": value}
            self.assert_guard("PROFILE_INSTALLATION_BINDING", receiver=receiver, require_profile_binding=True)

    def test_physical_profile_update_requires_fresh_candidate_binding_but_can_replace_old_profile(self):
        profile = {**deepcopy(self.receiver["profile"]), "tcp_bounds_base_mm": [-20, -20, 10, 20, 20, 60]}
        command = {**self.command, "kind": "profile_update", "purpose": "commissioning", "profile": profile, "target": None}
        self.assert_guard("PROFILE_INSTALLATION_BINDING", command=command, require_profile_binding=True)
        command["profile"]["installation_binding"] = self.measured_binding()
        self.gate(command=command, require_profile_binding=True)
        command["profile"]["installation_binding"]["calibration_id"] = "old-calibration"
        self.assert_guard("PROFILE_INSTALLATION_BINDING", command=command, require_profile_binding=True)

    def test_offline_helper_binding_admits_physical_push_with_all_markers_covered(self):
        from tools.prepare_robot_installation import build_profile
        installation = {**self.installation, "map_hash": "b" * 64}
        profile = build_profile(installation, {"actual_pose": self.receiver["actual_pose"], "actual_joint": [0] * 6},
                                site_reviewed=True, payload_kg=0.25)
        receiver = {**self.receiver, "profile": profile}
        observation = {**self.observation, "map_hash": "b" * 64, "view_status": "marker_occluded", "marker_count": 0}
        self.gate(installation=installation, receiver=receiver, observation=observation, require_profile_binding=True)

    def test_inspection_remains_available_before_a_bound_installation_is_prepared(self):
        command = {**self.command, "kind": "inspect_current", "installation_id": None, "target": None}
        admit(command, None, self.receiver, None, armed=False, now=100, require_profile_binding=True)


if __name__ == "__main__":
    unittest.main()
