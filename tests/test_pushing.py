"""Synthetic, equipment-free regression fixtures; none are physical evidence."""
import math
import unittest
from dataclasses import replace

from backend.robot_control.pushing import (
    CarFootprint, FitPolicy, MeasuredPose, PushIdentity, PushTrial,
    SelectionPolicy, contact_geometry, fit_response, select_next,
)


class EmpiricalPushingTests(unittest.TestCase):
    def setUp(self):
        self.car = CarFootprint(20, 10)
        self.identity = PushIdentity("site", "base-fit", "pad", "a" * 64,
                                     "car", self.car.geometry_sha256, "paper", "response-v1")
        self.pose = MeasuredPose(30, 30, 0, 100, self.identity)
        self.roads = ((0, 0, 150, 100),)

    def model(self, contact, gains=(1, 0, 0), distances=(1, 2, 3)):
        # These samples emulate measured provenance only inside this synthetic fixture.
        return fit_response(tuple(PushTrial(f"{contact}-{index}", self.identity, contact, distance,
                                            *(gain * distance for gain in gains))
                                  for index, distance in enumerate(distances)))

    def select(self, models, **changes):
        arguments = dict(identity=self.identity, waypoint_mm=(80, 30), desired_heading_deg=0,
                         path_origin_mm=(0, 30), now_s=100.5, road_rectangles_mm=self.roads)
        arguments.update(changes)
        return select_next(self.pose, self.car, tuple(models), **arguments)

    def test_contacts_use_measured_dimensions_and_right_handed_torque(self):
        contacts = {c.name: c for c in contact_geometry(self.car)}
        self.assertEqual(contacts["rear_center"].point_body_mm, (-10, 0))
        self.assertEqual(contacts["rear_left"].point_body_mm, (-10, 3))
        self.assertEqual(contacts["rear_left"].nominal_torque_sign, -1)
        self.assertEqual(contacts["rear_right"].nominal_torque_sign, 1)
        self.assertEqual(contacts["left_center"].push_direction_body, (0, -1))

    def test_fit_preserves_supported_range_gains_ids_and_error(self):
        model = self.model("rear_right", (0.7, -0.1, 0.8))
        self.assertAlmostEqual(model.gain_body_x, 0.7)
        self.assertAlmostEqual(model.gain_body_y, -0.1)
        self.assertAlmostEqual(model.gain_yaw_deg_per_mm, 0.8)
        self.assertEqual((model.min_distance_mm, model.max_distance_mm), (1, 3))
        self.assertEqual(len(model.trial_ids), 3)
        self.assertLess(model.error_mm, 1e-12)

    def test_fewer_or_duplicate_trials_cannot_establish_response(self):
        trial = PushTrial("one", self.identity, "rear_center", 1, 1, 0, 0)
        for trials in ((trial,), (trial, trial, trial)):
            with self.assertRaises(ValueError):
                fit_response(trials)

    def test_nonphysical_trial_sources_and_identity_changes_are_rejected(self):
        trials = tuple(PushTrial(str(i), self.identity, "rear_center", i + 1, i + 1, 0, 0)
                       for i in range(3))
        for change in ({"source": "meta"}, {"source": "simulation"},
                       {"identity": replace(self.identity, surface_id="other-paper")},
                       {"contact": "rear_left"}):
            with self.assertRaises(ValueError):
                fit_response((replace(trials[0], **change), *trials[1:]))

    def test_noisy_or_large_trials_are_rejected(self):
        trials = tuple(PushTrial(str(i), self.identity, "rear_center", 1, x, 0, 0)
                       for i, x in enumerate((0, 1, 3)))
        with self.assertRaises(ValueError):
            fit_response(trials)
        with self.assertRaises(ValueError):
            self.model("rear_right", (1, 0, 8))
        with self.assertRaises(ValueError):
            self.model("rear_center", distances=(1, 2, 11))

    def test_straight_progress_and_world_contact_are_proposals_only(self):
        result = self.select((self.model("rear_center"),))
        self.assertEqual(result.status, "proposal")
        self.assertEqual(result.distance_mm, 3)
        self.assertEqual(result.contact_point_mm, (20, 30))
        self.assertEqual(result.push_direction, (1, 0))
        self.assertEqual(result.expected_car_pose, (33, 30, 0))
        self.assertFalse(result.motion_qualified)
        self.assertEqual(result.coverage, "interpolated_car_rectangle_only")
        self.assertFalse(hasattr(result, "tcp_target"))

    def test_body_response_rotates_into_world(self):
        self.pose = replace(self.pose, yaw_deg=90)
        result = self.select((self.model("rear_center"),), waypoint_mm=(30, 80),
                             path_origin_mm=(30, 0), desired_heading_deg=90)
        self.assertEqual(result.status, "proposal")
        self.assertAlmostEqual(result.expected_car_pose[0], 30)
        self.assertAlmostEqual(result.expected_car_pose[1], 33)
        self.assertAlmostEqual(result.contact_point_mm[1], 20)
        self.assertAlmostEqual(result.push_direction[1], 1)

    def test_lateral_drift_selects_measured_side_contact(self):
        self.pose = replace(self.pose, y_mm=35)
        result = self.select((self.model("rear_center", (1, 0.5, 0)),
                              self.model("left_center", (0, -1, 0))))
        self.assertEqual(result.contact, "left_center")
        self.assertLess(result.expected_car_pose[1], self.pose.y_mm)

    def test_heading_correction_selects_measured_offset_contact(self):
        self.pose = replace(self.pose, yaw_deg=7)
        result = self.select((self.model("rear_center"),
                              self.model("rear_left", (0.5, 0, -1)),
                              self.model("rear_right", (0.5, 0, 1))))
        self.assertEqual(result.contact, "rear_left")
        self.assertLess(abs(result.expected_car_pose[2]), abs(self.pose.yaw_deg))

    def test_wrong_turn_sign_is_not_substituted_for_needed_turn(self):
        result = self.select((self.model("rear_left", (0, 0, -1)),), desired_heading_deg=90)
        self.assertEqual(result.status, "needs_measurements")

    def test_ninety_degree_goal_is_split_into_measured_small_steps(self):
        result = self.select((self.model("rear_right", (0, 0, 1)),), desired_heading_deg=90)
        self.assertEqual(result.status, "proposal")
        self.assertEqual(result.expected_car_pose[2], 3)
        self.assertLess(result.expected_car_pose[2], 90)

    def test_never_extrapolates_to_smaller_unmeasured_distance(self):
        result = self.select((self.model("rear_center", distances=(2, 3, 4)),),
                             policy=SelectionPolicy(max_step_mm=1))
        self.assertEqual(result.status, "needs_measurements")

    def test_untrained_contact_reports_need_for_measurements(self):
        self.assertEqual(self.select(()).status, "needs_measurements")

    def test_source_staleness_ambiguity_and_occlusion_require_observation(self):
        for changes in ({"observed_at_s": 98}, {"observed_at_s": 101},
                        {"ambiguous": True}, {"occluded": True}, {"source": "meta"},
                        {"uncertainty_xy_mm": 2}, {"uncertainty_yaw_deg": 4},
                        {"identity": replace(self.identity, calibration_id="new-fit")}):
            self.pose = replace(MeasuredPose(30, 30, 0, 100, self.identity), **changes)
            self.assertEqual(self.select((self.model("rear_center"),)).status, "needs_observation")

    def test_full_physical_identity_is_required(self):
        for name in vars(self.identity):
            other = replace(self.identity, **{name: "c" * 64 if name.endswith("sha256") else "different"})
            model = replace(self.model("rear_center"), identity=other)
            with self.assertRaises(ValueError):
                self.select((model,))

    def test_footprint_dimensions_are_bound_to_response_model_identity(self):
        self.car = CarFootprint(21, 10)
        with self.assertRaises(ValueError):
            self.select((self.model("rear_center"),))

    def test_heading_overshoot_is_not_admitted_for_translation_reward(self):
        self.pose = replace(self.pose, yaw_deg=-3)
        result = self.select((self.model("rear_right", (1, 0, 4)),))
        self.assertEqual(result.status, "proposal")
        self.assertEqual(result.distance_mm, 1)
        self.assertAlmostEqual(result.expected_car_pose[2], 1)

    def test_no_move_when_target_position_and_heading_are_met(self):
        result = self.select((), waypoint_mm=(30, 30))
        self.assertEqual(result.status, "at_target")
        self.assertIsNone(result.distance_mm)

    def test_missing_road_validation_and_narrow_road_reject_proposals(self):
        model = self.model("rear_center")
        self.assertEqual(self.select((model,), road_rectangles_mm=()).status, "coverage_validation_required")
        result = self.select((model,), road_rectangles_mm=((0, 26, 100, 34),))
        self.assertEqual(result.status, "needs_measurements")

    def test_road_union_hole_is_not_passed_by_corner_only_checks(self):
        # Four outer strips contain all car corners, but leave its center outside the road.
        strips = ((0, 0, 25, 100), (35, 0, 150, 100), (0, 0, 150, 25), (0, 35, 150, 100))
        self.assertEqual(self.select((self.model("rear_center"),), road_rectangles_mm=strips).status,
                         "needs_measurements")

    def test_intermediate_rotation_footprint_cannot_skip_road_boundary(self):
        self.pose = replace(self.pose, yaw_deg=40)
        # A 20 x 10 rectangle fits the endpoints' AABB but not its widest interpolated yaw.
        result = self.select((self.model("rear_right", (0, 0, 1), distances=(3, 4, 5)),),
                             desired_heading_deg=90, road_rectangles_mm=((18.1, 15, 41.9, 45),))
        self.assertEqual(result.status, "needs_measurements")

    def test_invalid_finite_and_geometry_inputs(self):
        for invalid in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                CarFootprint(invalid, 10)
            with self.assertRaises(ValueError):
                self.select((self.model("rear_center"),), now_s=invalid)
        with self.assertRaises(ValueError):
            self.select((self.model("rear_center"),), road_rectangles_mm=((1, 0, 0, 1),))
        with self.assertRaises(ValueError):
            fit_response(tuple(PushTrial(str(i), self.identity, "rear_center", 1, math.nan, 0, 0)
                               for i in range(3)))


if __name__ == "__main__":
    unittest.main()
