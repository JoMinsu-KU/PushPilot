"""Synthetic same-face corner geometry; no physical response claims."""
import unittest

from backend.robot_control.corner_contact import (
    differential_contact_delta, east_first_contact, rear_overlap_range,
)


class CornerContactTests(unittest.TestCase):
    def test_nominal_three_mm_overlap_depends_on_width_and_centering(self):
        nominal = rear_overlap_range(18, [20, 20], 16)
        self.assertEqual(nominal["minimum_overlap_mm"], 3)
        self.assertEqual(nominal["maximum_overlap_mm"], 3)
        uncertain = rear_overlap_range(18, [14.5, 22], 16)
        self.assertEqual(uncertain["minimum_overlap_mm"], .25)
        self.assertEqual(uncertain["maximum_overlap_mm"], 4)
        biased = rear_overlap_range(18, [14.5, 22], 16, 1)
        self.assertEqual(biased["minimum_overlap_mm"], 0)
        self.assertEqual(biased["maximum_overlap_mm"], 5)
        self.assertFalse(biased["contact_qualified"] or biased["motion_authority"])

    def test_south_contact_band_has_positive_nominal_torque_through_ninety_degrees(self):
        for yaw in (0, 5, 15, 30, 45, 60, 75, 90):
            with self.subTest(yaw=yaw):
                result = east_first_contact(45, 18, yaw, -16, 20)
                self.assertTrue(result["nominal_contact_exists"])
                self.assertEqual(result["nominal_torque_sign"], "counterclockwise")
                self.assertLess(result["contact_y_range_mm"][1], 0)
                self.assertFalse(result["car_turn_qualified"] or result["motion_authority"])

    def test_centered_face_is_not_a_guaranteed_corner_torque(self):
        straight = east_first_contact(45, 18, 0, 0, 20)
        self.assertEqual(straight["first_contact_x_mm"], -22.5)
        self.assertEqual(straight["contact_y_range_mm"], [-9, 9])
        self.assertEqual(straight["nominal_torque_sign"], "ambiguous_or_zero")
        north = east_first_contact(45, 18, 0, 16, 20)
        self.assertEqual(north["nominal_torque_sign"], "clockwise")
        absent = east_first_contact(45, 18, 0, -30, 20)
        self.assertFalse(absent["nominal_contact_exists"])

    def test_contact_x_changes_with_car_yaw(self):
        start = east_first_contact(45, 18, 0, -16, 20)
        diagonal = east_first_contact(45, 18, 45, -16, 20)
        northbound = east_first_contact(45, 18, 90, -16, 20)
        self.assertEqual(start["first_contact_x_mm"], -22.5)
        self.assertAlmostEqual(diagonal["first_contact_x_mm"], -22.27386360737625)
        self.assertAlmostEqual(northbound["first_contact_x_mm"], -9)

    def test_fixed_face_offset_cancels_only_for_same_orientation_differentials(self):
        reference = east_first_contact(45, 18, 0, 0, 20)
        candidate = east_first_contact(45, 18, 90, -16, 20)
        delta = differential_contact_delta(reference, candidate, [10, 2], -16)
        self.assertEqual(delta["delta_from_original_contact_tcp_road_mm"], [23.5, -14])
        self.assertTrue(delta["orientation_must_equal_original_contact"])
        self.assertTrue(delta["requires_bounded_observed_car_center_delta"])
        self.assertFalse(delta["motion_authority"])

    def test_invalid_dimensions_and_guessed_missing_delta_fail(self):
        for args in ((0, 18, 0, -16, 20), (45, 18, 181, -16, 20),
                     (45, 18, 0, -16, float("nan"))):
            with self.assertRaises(ValueError):
                east_first_contact(*args)
        with self.assertRaises(ValueError):
            rear_overlap_range(18, [22, 14.5], 16)
        reference = east_first_contact(45, 18, 0, 0, 20)
        with self.assertRaises(ValueError):
            differential_contact_delta(reference, reference, None, -16)


if __name__ == "__main__":
    unittest.main()
