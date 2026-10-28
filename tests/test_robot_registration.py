"""Synthetic metrology regressions; these tests contain no physical calibration."""
from dataclasses import replace
import json
import math
import unittest

from backend.robot_control.registration import (
    DrawingDomain, FitPolicy, MeasuredPoint, RegistrationError,
    RegistrationIdentity, fit_registration, validate_independent_check,
)


class RobotRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.identity = RegistrationIdentity(
            "synthetic-map", "synthetic-v1", "a" * 64, "synthetic-camera-epoch",
            "synthetic-image-registration", "synthetic-tcp", "b" * 64, "synthetic-tool",
        )
        self.domain = DrawingDomain(0, 0, 420, 297)
        self.policy = FitPolicy(max_fit_residual_mm=0.5, max_check_error_mm=0.75)
        self.angle = math.radians(37)
        self.translation = (123.4, -816.1)
        self.references = ((20, 20), (380, 20), (30, 270), (380, 270))

    def expected(self, xy, scale=1, reflection=False, identity=None):
        identity = identity or self.identity
        x, y = xy
        if identity.drawing_axes == "x_right_y_down":
            y = -y
        if reflection:
            y = -y
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (scale * (c * x - s * y) + self.translation[0],
                scale * (s * x + c * y) + self.translation[1])

    def point(self, index, xy, base=None, identity=None):
        identity = identity or self.identity
        return MeasuredPoint(f"synthetic-{index}", xy, base or self.expected(xy, identity=identity),
                             identity, f"synthetic-only/measurement-{index}.json", source="measured")

    def fit(self, points=None, **kwargs):
        return fit_registration("synthetic-calibration", points or tuple(
            self.point(i, xy) for i, xy in enumerate(self.references)
        ), kwargs.get("domain", self.domain), kwargs.get("policy", self.policy))

    def assertXYAlmostEqual(self, actual, expected, places=8):
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=places)

    def test_rigid_fit_handles_declared_downward_map_axis_and_negative_base(self):
        fitted = self.fit()
        self.assertAlmostEqual(fitted.cos_theta, math.cos(self.angle))
        self.assertAlmostEqual(fitted.sin_theta, math.sin(self.angle))
        self.assertXYAlmostEqual(fitted.translation_base_mm, self.translation)
        self.assertAlmostEqual(fitted.estimated_scale, 1)
        self.assertXYAlmostEqual(fitted.drawing_to_base((210, 148.5), identity=self.identity),
                                 self.expected((210, 148.5)))

    def test_upward_map_convention_is_explicit_and_supported(self):
        identity = replace(self.identity, drawing_axes="x_right_y_up")
        fitted = self.fit([self.point(i, xy, identity=identity) for i, xy in enumerate(self.references)])
        self.assertXYAlmostEqual(fitted.drawing_to_base((100, 120), identity=identity),
                                 self.expected((100, 120), identity=identity))

    def test_round_trip_covers_corners_and_interior_without_scale_or_z(self):
        fitted = self.fit()
        for xy in ((0, 0), (420, 0), (420, 297), (0, 297), (200.2, 117.6)):
            with self.subTest(xy=xy):
                base = fitted.drawing_to_base(xy, identity=self.identity)
                self.assertEqual(len(base), 2)
                self.assertXYAlmostEqual(fitted.base_to_drawing(base, identity=self.identity), xy)
        with self.assertRaisesRegex(RegistrationError, "Z is separate"):
            fitted.drawing_to_base((20, 20, 10.3), identity=self.identity)

    def test_least_squares_uses_all_points_with_small_balanced_noise(self):
        points = [self.point(i, xy, tuple(value + sign * delta for value, delta in
                   zip(self.expected(xy), (0.08, -0.06))))
                  for i, (xy, sign) in enumerate(zip(self.references, (1, -1, -1, 1)))]
        fitted = self.fit(points)
        report = fitted.to_dict()
        self.assertEqual(report["fit"]["count"], 4)
        self.assertEqual(report["fit"]["discarded_points"], [])
        self.assertLess(report["fit"]["max_error_mm"], 0.2)
        self.assertGreater(report["fit"]["rms_error_mm"], 0)

    def test_reflection_and_wrong_axis_convention_are_rejected(self):
        points = [self.point(i, xy, self.expected(xy, reflection=True))
                  for i, xy in enumerate(self.references)]
        with self.assertRaisesRegex(RegistrationError, "reflection"):
            self.fit(points)

    def test_wrong_physical_print_scale_is_rejected_without_rescaling(self):
        for scale in (0.95, 1.05, 2):
            points = [self.point(i, xy, self.expected(xy, scale=scale))
                      for i, xy in enumerate(self.references)]
            with self.subTest(scale=scale), self.assertRaisesRegex(RegistrationError, "scale"):
                self.fit(points)

    def test_outlier_is_rejected_and_not_silently_removed(self):
        points = [self.point(i, xy) for i, xy in enumerate(self.references)]
        points[-1] = replace(points[-1], base_xy_mm=(points[-1].base_xy_mm[0] + 3,
                                                   points[-1].base_xy_mm[1]))
        with self.assertRaisesRegex(RegistrationError, "no outlier was discarded"):
            self.fit(points)

    def test_anisotropic_print_distortion_is_not_absorbed_into_a_rigid_fit(self):
        points = [self.point(i, xy, self.expected((xy[0] * 1.03, xy[1] * 0.97)))
                  for i, xy in enumerate(self.references)]
        with self.assertRaisesRegex(RegistrationError, "Fit residual"):
            self.fit(points)

    def test_three_noncollinear_points_work_but_two_do_not(self):
        points = [self.point(i, xy) for i, xy in enumerate(self.references)]
        self.assertEqual(len(self.fit(points[:3]).points), 3)
        with self.assertRaisesRegex(RegistrationError, "3 to 100"):
            self.fit(points[:2])

    def test_collinear_near_collinear_and_narrow_calibration_fail(self):
        for points in (((0, 0), (100, 100), (200, 200)),
                       ((0, 0), (100, 100), (200, 200.001)),
                       ((1, 1), (2, 1), (1, 2))):
            with self.subTest(points=points), self.assertRaisesRegex(RegistrationError, "degenerate"):
                self.fit([self.point(i, xy) for i, xy in enumerate(points)])

    def test_degenerate_base_measurements_fail_even_with_good_drawing_geometry(self):
        points = [self.point(i, xy, (100 + i * 100, -200)) for i, xy in enumerate(self.references)]
        with self.assertRaisesRegex(RegistrationError, "BASE points are degenerate"):
            self.fit(points)

    def test_new_independent_point_is_checked_without_refitting(self):
        fitted = self.fit()
        before = fitted.to_dict()
        xy = (210, 148)
        expected = self.expected(xy)
        checked = validate_independent_check(fitted, self.point("check", xy, (expected[0] + 0.3, expected[1] + 0.4)))
        self.assertTrue(checked.accepted)
        self.assertAlmostEqual(checked.error_mm, 0.5)
        self.assertEqual(fitted.to_dict(), before)
        self.assertFalse(checked.to_dict()["physical_qualified"])

    def test_independent_failure_returns_a_rejected_metric_report(self):
        fitted = self.fit()
        xy = (210, 148)
        expected = self.expected(xy)
        checked = validate_independent_check(fitted, self.point("bad-check", xy, (expected[0] + 2, expected[1])))
        self.assertFalse(checked.accepted)
        self.assertAlmostEqual(checked.error_mm, 2)
        self.assertFalse(checked.to_dict()["physical_qualified"])

    def test_reusing_fit_id_file_or_location_cannot_be_an_independent_check(self):
        fitted = self.fit()
        original = fitted.points[0]
        for point in (original, replace(self.point("check", (210, 148)), measurement_id=original.measurement_id),
                      replace(self.point("check", (210, 148)), evidence_reference=original.evidence_reference),
                      self.point("near", (21, 20))):
            with self.subTest(point=point), self.assertRaisesRegex(RegistrationError, "Independent check"):
                validate_independent_check(fitted, point)

    def test_all_current_identity_fields_invalidate_transform_and_check(self):
        fitted = self.fit()
        changes = {"map_id": "replacement", "map_version": "v2", "map_hash": "c" * 64,
                   "camera_epoch": "new-epoch", "registration_id": "new-registration", "tcp_id": "new-tcp",
                   "tcp_definition_sha256": "d" * 64, "tool_id": "new-tool", "drawing_axes": "x_right_y_up"}
        for field, value in changes.items():
            identity = replace(self.identity, **{field: value})
            with self.subTest(field=field):
                with self.assertRaisesRegex(RegistrationError, "identity differs"):
                    fitted.drawing_to_base((100, 100), identity=identity)
                with self.assertRaisesRegex(RegistrationError, "identity differs"):
                    fitted.base_to_drawing(self.expected((100, 100)), identity=identity)
                with self.assertRaisesRegex(RegistrationError, "identity differs"):
                    validate_independent_check(fitted, self.point("check", (210, 148), identity=identity))

    def test_mixed_identity_and_duplicate_ids_or_drawing_points_fail(self):
        points = [self.point(i, xy) for i, xy in enumerate(self.references)]
        for last, message in ((replace(points[-1], identity=replace(self.identity, map_version="v2")), "same current identity"),
                              (replace(points[-1], measurement_id=points[0].measurement_id), "IDs must be unique"),
                              (replace(points[-1], drawing_xy_mm=points[0].drawing_xy_mm), "coordinates must be distinct")):
            with self.subTest(message=message), self.assertRaisesRegex(RegistrationError, message):
                self.fit([*points[:-1], last])

    def test_extrapolation_is_not_admitted_in_either_direction(self):
        fitted = self.fit()
        for xy in ((-1, 10), (421, 10), (20, 298)):
            with self.subTest(xy=xy):
                with self.assertRaisesRegex(RegistrationError, "outside"):
                    fitted.drawing_to_base(xy, identity=self.identity)
                with self.assertRaisesRegex(RegistrationError, "outside"):
                    fitted.base_to_drawing(self.expected(xy), identity=self.identity)
                with self.assertRaisesRegex(RegistrationError, "outside"):
                    self.fit([self.point(i, value) for i, value in enumerate((*self.references[:3], xy))])

    def test_nonfinite_boolean_and_extra_coordinate_inputs_are_rejected(self):
        for xy in ((True, 1), (1, float("nan")), (1, float("inf")), (1, 10001), (1, 2, 3), "12"):
            with self.subTest(xy=xy), self.assertRaises(RegistrationError):
                self.point("bad", xy, base=(0, 0))
        with self.assertRaises(RegistrationError):
            self.point("bad", (10, 10), (False, 0))
        with self.assertRaises(RegistrationError):
            DrawingDomain(0, 0, float("inf"), 297)

    def test_nominal_metadata_cannot_be_used_as_measured_evidence(self):
        point = self.point("nominal", (100, 100))
        for source in ("nominal", "simulation", "operator_guess", "meta"):
            with self.subTest(source=source), self.assertRaisesRegex(RegistrationError, "not a measured correspondence"):
                replace(point, source=source)
        for changes in ({"map_hash": "short"}, {"tcp_definition_sha256": "z" * 64},
                        {"tcp_id": ""}, {"drawing_axes": "automatic"}):
            with self.subTest(changes=changes), self.assertRaises(RegistrationError):
                replace(self.identity, **changes)

    def test_policy_is_finite_explicit_and_cannot_hide_arbitrary_errors(self):
        for changes in ({"max_fit_residual_mm": True}, {"max_check_error_mm": float("nan")},
                        {"min_span_mm": 0}, {"min_shape_ratio": 1}, {"scale_tolerance": 0.3},
                        {"max_fit_residual_mm": 1000}):
            with self.subTest(changes=changes), self.assertRaises(RegistrationError):
                replace(self.policy, **changes)
        with self.assertRaises(RegistrationError):
            DrawingDomain(10, 0, 0, 297)

    def test_serialized_fit_preserves_measurement_provenance_and_no_motion_claim(self):
        fitted = self.fit()
        report = json.loads(json.dumps(fitted.to_dict(), allow_nan=False))
        self.assertEqual(report["identity"], self.identity.to_dict())
        self.assertTrue(report["independent_check_required"])
        self.assertFalse(report["physical_qualified"] or report["contact_z_fitted"])
        self.assertEqual(report["transform"]["scale_applied"], 1)
        self.assertEqual(report["measurements"][0]["source"], "measured")
        self.assertNotIn("allow_motion", report)
        self.assertNotIn("site_verified", report)


if __name__ == "__main__":
    unittest.main()
