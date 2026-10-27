"""Offline profile preparation never borrows historical geometry or starts equipment."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import prepare_robot_installation as prepare


class RobotInstallationTests(unittest.TestCase):
    def setUp(self):
        self.installation = {
            "installation_id": "synthetic-installation", "map_id": "synthetic-map", "map_hash": "a" * 64,
            "calibration_id": "synthetic-calibration", "tcp_id": "synthetic-tcp", "tool_id": "synthetic-tool",
            "review_reference": "Synthetic operator review; not physical evidence.", "qualified": True,
            "workspace_min_mm": [-50, -60, 0], "workspace_max_mm": [50, 60, 140],
            "min_tcp_z_mm": 12, "raised_tcp_z_mm": 55,
            "max_step_mm": 17, "max_speed_mm_s": 7, "max_accel_mm_s2": 14,
            "camera_epoch": "synthetic-camera", "registration_id": "synthetic-registration",
        }
        self.state = {"actual_pose": [3, 4, 60, 179, 0, -91], "actual_joint": [1, 2, 3, 4, 5, 6]}

    def build(self, installation=None, state=None, **kwargs):
        return prepare.build_profile(installation or self.installation, state or self.state,
                                     site_reviewed=kwargs.pop("site_reviewed", True), payload_kg=kwargs.pop("payload_kg", 0.25), **kwargs)

    def test_profile_uses_only_measured_state_installation_and_explicit_payload(self):
        profile = self.build()
        self.assertEqual(profile["expected_start_tcp_mm_deg"], self.state["actual_pose"])
        self.assertEqual(profile["expected_start_joint_deg"], self.state["actual_joint"])
        self.assertEqual(profile["tcp_bounds_base_mm"], [-50, -60, 12, 50, 60, 140])
        self.assertEqual(profile["tcp_id"], "synthetic-tcp")
        self.assertEqual(profile["payload_kg"], 0.25)
        self.assertEqual(profile["translation_speed_mm_s"], 7)
        self.assertEqual(profile["translation_accel_mm_s2"], 14)
        self.assertEqual(profile["max_translation_mm"], 17)
        self.assertEqual(profile["installation_binding"]["calibration_id"], "synthetic-calibration")
        self.assertEqual(profile["installation_binding"]["map_hash"], "a" * 64)
        self.assertTrue(profile["allow_motion"] and profile["site_verified"])
        self.assertEqual(self.state["actual_pose"], [3, 4, 60, 179, 0, -91])

    def test_review_flag_and_prequalified_measurements_are_both_required(self):
        with self.assertRaisesRegex(ValueError, "site-reviewed"):
            self.build(site_reviewed=False)
        for value in (False, "true", 1):
            with self.assertRaisesRegex(ValueError, "not qualified"):
                self.build(installation={**self.installation, "qualified": value})
        self.assertTrue(self.installation["qualified"])

    def test_default_rotation_is_complete_but_unqualified_with_no_edges(self):
        profile = self.build()
        self.assertFalse(profile["rotation_runtime"]["verified"])
        self.assertEqual(profile["rotation_anchors"], [])
        self.assertEqual(profile["rotation_edges"], [])
        self.assertFalse(profile["installation_binding"]["car_turn_qualified"])
        self.assertTrue(all(key in profile["rotation_runtime"] for key in (
            "primitive", "controller_version", "argument_semantics", "speed_argument", "accel_argument",
            "completion_timeout_s", "review_reference")))

    def test_invalid_measurements_bounds_and_implicit_payload_are_rejected(self):
        for changes in ({"workspace_min_mm": [50, -60, 0]}, {"min_tcp_z_mm": 141},
                        {"workspace_min_mm": [True, -60, 0]}, {"max_speed_mm_s": float("nan")}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.build(installation={**self.installation, **changes})
        for payload in (True, -0.1, float("inf")):
            with self.assertRaises(ValueError):
                self.build(payload_kg=payload)
        with self.assertRaisesRegex(ValueError, "outside"):
            self.build(state={**self.state, "actual_pose": [3, 4, 10, 179, 0, -91]})
        with self.assertRaisesRegex(ValueError, "never normalizes"):
            self.build(state={**self.state, "actual_pose": [3, 4, 60, 179, 0, 269]})

    def test_old_profile_or_extra_state_cannot_be_imported(self):
        with self.assertRaisesRegex(ValueError, "no profile import"):
            self.build(state={**self.state, "profile": {"old": True}})
        with self.assertRaises(ValueError):
            self.build(state={"actual_pose": [1] * 6})

    def test_keepouts_are_explicit_finite_and_bounded_in_number(self):
        box = [-10, -10, 12, -5, -5, 100]
        profile = self.build(keepout_boxes=[box])
        self.assertEqual(profile["inflated_keepout_boxes_base_mm"], [box])
        for boxes in ([[0, 0, 0, -1, 1, 1]], [[0, 0, float("nan"), 1, 1, 1]], [box] * 17):
            with self.assertRaises(ValueError):
                self.build(keepout_boxes=boxes)

    def test_prepare_validates_reviewed_policy_before_exclusive_private_write(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            installation, state, output = base / "installation.json", base / "state.json", base / "private/profile.local.json"
            installation.write_text(json.dumps(self.installation))
            state.write_text(json.dumps(self.state))
            policy = SimpleNamespace(valid=Mock(), MAX_PROFILE_BYTES=8000)
            with patch.object(prepare, "load_runtime", return_value={"policy": policy}) as load:
                result = prepare.prepare(installation, state, output, site_reviewed=True, payload_kg=0.25)
                load.assert_called_once_with(prepare.DEFAULT_RUNTIME)
                policy.valid.assert_called_once()
                self.assertIs(policy.valid.call_args.args[1], True)
                self.assertFalse(result["motion_issued"] or result["network_contacted"] or result["receiver_started"])
                self.assertFalse(result["car_turn_qualified"])
                original = output.read_bytes()
                with self.assertRaises(FileExistsError):
                    prepare.prepare(installation, state, output, site_reviewed=True, payload_kg=0.25)
                self.assertEqual(output.read_bytes(), original)
                if os.name != "nt":
                    self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_no_file_or_runtime_read_without_explicit_flag_and_policy_failure_leaves_no_output(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            output = base / "profile.local.json"
            with patch.object(prepare, "load_runtime") as load, self.assertRaisesRegex(ValueError, "site-reviewed"):
                prepare.prepare(base / "missing.json", base / "missing-state.json", output, payload_kg=0.25)
            load.assert_not_called()
            self.assertFalse(output.exists())
            installation, state = base / "installation.json", base / "state.json"
            installation.write_text(json.dumps(self.installation))
            state.write_text(json.dumps(self.state))
            policy = SimpleNamespace(valid=Mock(side_effect=ValueError("Policy rejected")), MAX_PROFILE_BYTES=8000)
            with patch.object(prepare, "load_runtime", return_value={"policy": policy}), self.assertRaisesRegex(ValueError, "Policy rejected"):
                prepare.prepare(installation, state, output, site_reviewed=True, payload_kg=0.25)
            self.assertFalse(output.exists())

    def test_duplicate_json_keys_cannot_change_qualification_or_coordinates(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"qualified":false,"qualified":true}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                prepare._read_json(path)


if __name__ == "__main__":
    unittest.main()
