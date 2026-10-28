"""Synthetic geometry and evidence-boundary checks; no hardware commands."""
from copy import deepcopy
import math
import unittest

from backend.robot_control.wrist_commissioning import (
    local_wrist_pose, propose_wrist_turn, verify_endpoint_ik,
)


class WristCommissioningTests(unittest.TestCase):
    def setUp(self):
        self.pose = [10., -20., 100., -180., 0., 10.]
        self.joints = [0., -90., -90., -90., 90., -120.]

    def test_downward_tool_yaw_has_opposite_base_rz_sign(self):
        target = local_wrist_pose(self.pose, 90.)
        self.assertEqual(target[:3], self.pose[:3])
        self.assertAlmostEqual(target[5], -80.)
        self.assertAlmostEqual(abs(target[3]), 180.)

    def test_tilted_tool_needs_composition_instead_of_fixed_roll_pitch(self):
        pose = self.pose[:3]+[-179.8, .3, 10.]
        target = local_wrist_pose(pose, 45.)
        self.assertNotEqual(target[3:5], pose[3:5])
        self.assertTrue(all(-180 <= item <= 180 for item in target[3:]))
        restored = local_wrist_pose(target, -45.)
        for actual, expected in zip(restored, pose):
            self.assertAlmostEqual(actual, expected)

    def test_queries_and_predicted_joints_are_not_measured_path_evidence(self):
        candidate = propose_wrist_turn(self.pose, self.joints, 45.)
        self.assertEqual(candidate["target_joint"], self.joints[:5]+[-75.])
        self.assertEqual(len(candidate["ik_query_targets"]), 19)
        self.assertEqual(candidate["ik_query_targets"][-1], candidate["target_pose"])
        for pose in candidate["ik_query_targets"]:
            self.assertEqual(pose[:3], self.pose[:3])
        self.assertFalse(candidate["query_targets_are_measured_fk"])
        self.assertTrue(candidate["receiver_nineteen_joint_fk_samples_still_required"])
        self.assertFalse(candidate["motion_authority"] or candidate["car_turn_qualified"])

    def test_invalid_input_or_joint_winding_never_produces_candidate(self):
        for delta in (0, 90.001, -90.001, float("nan"), True):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                propose_wrist_turn(self.pose, self.joints, delta)
        for pose in ([0.]*5, self.pose[:5]+[181.], self.pose[:5]+[float("inf")]):
            with self.assertRaises(ValueError):
                propose_wrist_turn(pose, self.joints, 45.)
        with self.assertRaises(ValueError):
            propose_wrist_turn(self.pose, self.joints[:5]+[350.], 20.)

    def test_endpoint_ik_checks_reported_fixed_joint_solution_without_granting_motion(self):
        candidate = propose_wrist_turn(self.pose, self.joints, 45.)
        inspection = {"status": "ok", "motion_issued": False,
                      "source_joint": self.joints, "source_pose": self.pose,
                      "solution_joint": candidate["target_joint"],
                      "target_fk": candidate["target_pose"]}
        result = verify_endpoint_ik(candidate, inspection)
        self.assertTrue(result["endpoint_ik_consistent"])
        self.assertFalse(result["exact_joint_path_fk_verified"] or result["motion_authority"])
        for key in ("source_joint", "solution_joint", "source_pose", "target_fk"):
            changed = deepcopy(inspection)
            changed[key][0] += .2
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_endpoint_ik(candidate, changed)
        for changes in ({"status": "no_solution"}, {"motion_issued": True},
                        {"solution_joint": self.joints[:5]+[285.]}):
            with self.assertRaises(ValueError):
                verify_endpoint_ik(candidate, {**inspection, **changes})

    def test_actual_negative_ninety_float_boundary_stays_inside_original_guard(self):
        source = -231.19340651106128
        requested = -90.
        rounded_target = source+requested
        self.assertGreater(abs(rounded_target-source), 90.)
        joints = self.joints[:5]+[source]
        candidate = propose_wrist_turn(self.pose, joints, requested)
        self.assertEqual(candidate["source_joint"], joints)
        self.assertEqual(candidate["target_joint"][:5], joints[:5])
        self.assertEqual(candidate["target_joint"][5], math.nextafter(rounded_target, source))
        actual = candidate["target_joint"][5]-source
        self.assertLessEqual(abs(actual), 90.)
        self.assertLess(actual, 0.)
        self.assertEqual(candidate["requested_delta_j6_deg"], requested)
        self.assertEqual(candidate["delta_j6_deg"], actual)
        self.assertEqual(candidate["representable_delta_j6_deg"], actual)
        self.assertTrue(candidate["target_j6_nextafter_applied"])
        self.assertEqual(candidate["target_pose"], local_wrist_pose(self.pose, actual))
        self.assertEqual(candidate["ik_query_targets"][-1], candidate["target_pose"])

    def test_both_ninety_directions_and_near_joint_winding_bounds_use_actual_increment(self):
        cases = ((-231.19340651106128, -90.), (231.19340651106128, 90.),
                 (-231.19340651106128, 90.), (231.19340651106128, -90.),
                 (math.nextafter(270., 0.), 90.), (math.nextafter(-270., 0.), -90.),
                 (math.nextafter(360., 0.), 360.-math.nextafter(360., 0.)),
                 (math.nextafter(-360., 0.), -360.-math.nextafter(-360., 0.)))
        for source, requested in cases:
            with self.subTest(source=source, requested=requested):
                joints = self.joints[:5]+[source]
                candidate = propose_wrist_turn(self.pose, joints, requested)
                effective = candidate["target_joint"][5]-source
                self.assertEqual(candidate["source_joint"], joints)
                self.assertLessEqual(abs(candidate["target_joint"][5]), 360.)
                self.assertTrue(0 < abs(effective) <= min(abs(requested), 90.))
                self.assertGreater(effective*requested, 0.)
                self.assertEqual(candidate["delta_j6_deg"], effective)
                self.assertEqual(candidate["target_pose"], local_wrist_pose(self.pose, effective))
                self.assertEqual(candidate["ik_query_targets"][-1], candidate["target_pose"])
                for i, query in enumerate(candidate["ik_query_targets"][:-1]):
                    self.assertEqual(query, local_wrist_pose(self.pose, effective*(i/18)))

    def test_joint_bound_and_unrepresentable_zero_still_reject_without_relaxation(self):
        for source, requested in ((math.nextafter(270., math.inf), 90.),
                                  (math.nextafter(-270., -math.inf), -90.),
                                  (360., 1.), (-360., -1.), (-231.19340651106128, 1e-20)):
            with self.subTest(source=source, requested=requested), self.assertRaises(ValueError):
                propose_wrist_turn(self.pose, self.joints[:5]+[source], requested)


if __name__ == "__main__":
    unittest.main()
