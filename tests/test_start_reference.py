"""Fixed setup regressions with synthetic readback; no device or vision calls."""
from dataclasses import FrozenInstanceError, replace
import copy
import json
import math
import unittest

from backend.robot_control.start_reference import (
    StartIdentity, StartReferenceError, freeze_start, verify_start,
)


class FixedStartTests(unittest.TestCase):
    def setUp(self):
        self.identity = StartIdentity("synthetic-city", "synthetic-v1", "a" * 64,
                                      "synthetic-tcp", "b" * 64, "synthetic-tool")
        self.receiver = {"connected": True, "idle": True, "reason": "RECEIVER_IDLE",
                         "session_id": "c" * 32, "seq": 3, "profile_id": "d" * 64,
                         "actual_pose": [30.034, -80.028, 12.043, -179.974, .012, 25.024],
                         "actual_joint": [-10.024, -20.032, 50.012, -60.019, 90.013, -100.021]}
        native = {"program_before": [2], "program_after": [2], "flags": [1, 1, 0, 0, 0, 0],
                  "pose": [30, -80, 12, -180, 0, 25], "joint": [-10, -20, 50, -60, 90, -100],
                  "speed": [0] * 6}
        self.samples = [{"captured_at": 100.1 + i * .1, "snapshot": copy.deepcopy(native)}
                        for i in range(3)]

    def freeze(self, **kwargs):
        return freeze_start(self.identity, self.receiver, self.samples,
                            receiver_captured_at=100.05, now=100.4,
                            operator_fixed_setup=kwargs.pop("operator_fixed_setup", True), **kwargs)

    def verify(self, reference, identity=None):
        fresh_samples = [{**row, "captured_at": row["captured_at"] + 1} for row in self.samples]
        return verify_start(reference, identity or self.identity, self.receiver, fresh_samples,
                            receiver_captured_at=101.05, now=101.4)

    def test_covered_car_needs_no_image_and_keeps_full_precision(self):
        record = self.freeze()
        encoded = json.dumps(record.to_dict(), allow_nan=False)
        self.assertEqual(record.tcp_mm_deg, tuple(self.receiver["actual_pose"]))
        self.assertEqual(record.joint_deg, tuple(self.receiver["actual_joint"]))
        self.assertIn('"car_initial_source": "operator_fixed_setup"', encoded)
        for key in ("car_visible", "car_detected", "allow_motion", "site_verified", "profile"):
            self.assertNotIn(key, record.to_dict())
        self.assertFalse(record.to_dict()["geometry_qualified"])
        self.assertFalse(record.to_dict()["contact_model_measured"])
        self.assertFalse(record.to_dict()["car_pose_measured"])

    def test_record_is_frozen_and_does_not_alias_mutable_observations(self):
        record = self.freeze()
        before = record.to_dict()
        self.receiver["actual_pose"][0] = 900
        self.samples[-1]["snapshot"]["pose"][0] = 900
        self.assertEqual(before, record.to_dict())
        with self.assertRaises(FrozenInstanceError):
            record.seq = 99

    def test_known_setup_requires_literal_operator_acknowledgement(self):
        for value in (False, None, 1, "true"):
            with self.subTest(value=value), self.assertRaisesRegex(StartReferenceError, "ACKNOWLEDGEMENT"):
                self.freeze(operator_fixed_setup=value)

    def test_current_robot_match_never_verifies_car_return(self):
        result = self.verify(self.freeze())
        self.assertTrue(result["robot_matches_start"])
        self.assertFalse(result["car_return_verified"])
        self.assertFalse(result["motion_issued"])
        self.assertEqual(result["car_current_source"], "unobserved")

    def test_different_robot_location_is_reported_without_auto_return(self):
        record = self.freeze()
        self.receiver["actual_pose"][0] += 2
        for row in self.samples:
            row["snapshot"]["pose"][0] += 2
        result = self.verify(record)
        self.assertFalse(result["robot_matches_start"])
        self.assertAlmostEqual(result["tcp_literal_delta_mm_deg"][0], 2)
        self.assertFalse(result["motion_issued"])

    def test_all_identity_changes_invalidate_reference(self):
        record = self.freeze()
        for key in vars(self.identity):
            new_value = "f" * 64 if key.endswith("hash") or key.endswith("sha256") else "changed"
            changed = replace(self.identity, **{key: new_value})
            with self.subTest(key=key), self.assertRaisesRegex(StartReferenceError, "IDENTITY_CHANGED"):
                self.verify(record, changed)

    def test_native_quantization_does_not_destroy_full_precision_pose(self):
        self.receiver["actual_pose"][0] = 30.0999
        record = self.freeze()
        self.assertEqual(record.tcp_mm_deg[0], 30.0999)
        self.receiver["actual_pose"][0] = 30.1001
        with self.assertRaisesRegex(StartReferenceError, "DISAGREEMENT"):
            self.freeze()

    def test_literal_euler_opposite_branch_is_not_equivalent(self):
        self.receiver["actual_pose"][3] = 180
        with self.assertRaisesRegex(StartReferenceError, "DISAGREEMENT"):
            self.freeze()

    def test_unstationary_or_faulted_native_never_establishes_start(self):
        mutations = [("speed", [0, 0, .1, 0, 0, 0]), ("flags", [1, 1, 0, 1, 0, 0]),
                     ("program_after", [6]), ("joint", [-10, -20, 50, -60, 90, -101])]
        for key, value in mutations:
            samples = copy.deepcopy(self.samples)
            self.samples[1]["snapshot"][key] = value
            with self.subTest(key=key), self.assertRaises(StartReferenceError):
                self.freeze()
            self.samples = samples

    def test_idle_state_must_be_connected_fresh_and_unheld(self):
        for key, value in (("connected", False), ("idle", False), ("reason", "RECEIVER_OPERATOR_HOLD")):
            before = copy.deepcopy(self.receiver)
            self.receiver[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(StartReferenceError, "IDLE_REQUIRED"):
                self.freeze()
            self.receiver = before
        with self.assertRaisesRegex(StartReferenceError, "STALE"):
            freeze_start(self.identity, self.receiver, self.samples, receiver_captured_at=97,
                         now=100.4, operator_fixed_setup=True)

    def test_missing_stale_future_or_duplicate_samples_fail(self):
        original = copy.deepcopy(self.samples)
        for samples in (original[:1], [{**original[0], "captured_at": 97}, *original[1:]],
                        [*original[:2], {**original[2], "captured_at": 101}],
                        [original[0], original[0]]):
            self.samples = samples
            with self.subTest(samples=len(samples)), self.assertRaises(StartReferenceError):
                self.freeze()

    def test_invalid_numbers_or_boolean_pose_cannot_be_captured(self):
        for value in (math.nan, math.inf, True, "30"):
            self.receiver["actual_pose"][0] = value
            with self.subTest(value=value), self.assertRaisesRegex(StartReferenceError, "VECTOR"):
                self.freeze()

    def test_current_joint_change_prevents_robot_start_match(self):
        record = self.freeze()
        self.receiver["actual_joint"][1] -= 1
        for row in self.samples:
            row["snapshot"]["joint"][1] -= 1
        self.assertFalse(self.verify(record)["robot_matches_start"])

    def test_start_capture_samples_cannot_be_reused_as_fresh_verification(self):
        record = self.freeze()
        with self.assertRaisesRegex(StartReferenceError, "NEW_NATIVE"):
            verify_start(record, self.identity, self.receiver, self.samples,
                         receiver_captured_at=100.5, now=100.6)
        with self.assertRaisesRegex(StartReferenceError, "FRESH_RECEIVER"):
            verify_start(record, self.identity, self.receiver, self.samples,
                         receiver_captured_at=100.05, now=100.6)

    def test_changed_program_between_individually_coherent_reads_is_refused(self):
        self.samples[1]["snapshot"].update(program_before=[6], program_after=[6])
        with self.assertRaisesRegex(StartReferenceError, "STATE_CHANGED"):
            self.freeze()

    def test_all_pairs_checked_for_drift_not_just_the_receiver_midpoint(self):
        self.receiver["actual_pose"][0] = 30
        self.samples[0]["snapshot"]["pose"][0] = 29.9
        self.samples[2]["snapshot"]["pose"][0] = 30.1
        with self.assertRaisesRegex(StartReferenceError, "COORDINATES_CHANGED"):
            self.freeze()


if __name__ == "__main__":
    unittest.main()
