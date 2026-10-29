"""Synthetic-only pose-contract tests; no fixture qualifies the physical setup."""
from copy import deepcopy
import hashlib
import unittest

import cv2
import numpy as np

from backend.robot_control.mission_measurement import QualifiedCarMeasurement, canonical_sha256
from backend.robot_control.taught_executor import Frame


def configuration(*, accepted=False):
    value = {"kind": "planar_car_axis_v1", "camera_epoch": "synthetic-camera", "map_sha256": "a" * 64,
        "car_id": "synthetic-white-car", "coordinate_frame_id": "synthetic-plane-x-right-y-down-mm",
        "working_z_mm": 7.4, "frame_size_px": [300, 200], "car_dimensions_mm": [45., 18., 15.],
        "image_to_car_plane_homography": [[.5, 0., 0.], [0., .5, 0.], [0., 0., 1.]],
        "detector": {"roi_xywh": [0, 0, 300, 200], "area_range_px2": [2500., 4000.],
                     "long_side_range_px": [80., 100.], "short_side_range_px": [30., 45.]}}
    if accepted:
        # Fictional accepted record exercises validation logic. Its synthetic
        # dataset identity must never be installed as physical release evidence.
        samples = []
        for index, (x, y) in enumerate(((80, 60), (220, 60), (80, 140), (220, 140))):
            samples.append({"id": f"synthetic-holdout-{index}", "frame_sha256": str(index + 1) * 64,
                "independent_reference": True, "image_centroid_px": [x, y],
                "estimated_center_mm": [x / 2, y / 2], "reference_center_mm": [x / 2 + .3, y / 2 + .2],
                "estimated_axis_deg": 17., "reference_axis_deg": 15.})
        record = {"schema": "pushpilot.car-axis-holdout.v1", "status": "accepted",
            "source": "independent_physical_holdout", "configuration_sha256": canonical_sha256(value),
            "used_for_fitting": False, "roi_xywh": value["detector"]["roi_xywh"],
            "independent_reference_dataset_sha256": hashlib.sha256(b"SYNTHETIC TEST DATA ONLY").hexdigest(),
            "max_xy_error_mm": 1., "max_axis_error_deg": 3., "samples": samples}
        value["qualification"] = {"record": record, "reference_sha256": canonical_sha256(record)}
    return value


def frame(*, angle=0., center=(150., 100.), second=False):
    image = np.full((200, 300, 3), 65, dtype=np.uint8)
    polygon = cv2.boxPoints((center, (90., 36.), angle)).round().astype(np.int32)
    cv2.fillConvexPoly(image, polygon, (245, 245, 245))
    if second:
        extra = cv2.boxPoints(((80., 45.), (90., 36.), 0.)).round().astype(np.int32)
        cv2.fillConvexPoly(image, extra, (245, 245, 245))
    success, encoded = cv2.imencode(".jpg", image)
    assert success
    data = encoded.tobytes()
    return Frame("synthetic-frame", "synthetic-camera", 1, 12., hashlib.sha256(data).hexdigest(), data)


def context(original):
    return {"map_sha256": "a" * 64, "car_id": "synthetic-white-car", "working_z_mm": 7.4,
        "occlusion_clear": True, "occlusion_frame_sha256": original.sha256,
        "target_lane": {"coordinate_frame_id": "synthetic-plane-x-right-y-down-mm",
                        "point_mm": [75., 50.], "heading_deg": 0., "parallel_axis": True}}


def rehash(config):
    config["qualification"]["reference_sha256"] = canonical_sha256(config["qualification"]["record"])
    return config


class MissionMeasurementTests(unittest.TestCase):
    def test_unqualified_configuration_produces_diagnostics_without_metric_authority(self):
        estimator, original = QualifiedCarMeasurement(configuration()), frame(angle=25.)
        result = estimator.estimate(original, context(original))
        self.assertEqual(result["status"], "diagnostic_only")
        self.assertEqual(result["measurement_source"], "unmeasured")
        self.assertIsNone(result["heading_deg"])
        self.assertIsNone(result["lateral_error_mm"])
        self.assertAlmostEqual(result["diagnostic_heading_deg"], 25., delta=1.)
        self.assertFalse(estimator.readiness()["available"])

    def test_exact_bound_holdout_configuration_exposes_numeric_axis_and_error(self):
        estimator, original = QualifiedCarMeasurement(configuration(accepted=True)), frame(angle=25.)
        result = estimator.estimate(original, context(original))
        self.assertEqual(result["measurement_source"], "qualified_estimator")
        self.assertAlmostEqual(result["heading_deg"], 25., delta=1.)
        self.assertGreaterEqual(result["heading_uncertainty_deg"], 3.)
        self.assertGreaterEqual(result["lateral_uncertainty_mm"], 1.)
        self.assertAlmostEqual(result["lateral_error_mm"], 0., delta=.5)
        self.assertEqual(len(result["measurement_evidence_sha256"]), 64)
        self.assertFalse(result["heading_front_back_resolved"])

    def test_lateral_error_uses_declared_lane_normal_and_plane_not_pixels(self):
        estimator, original = QualifiedCarMeasurement(configuration(accepted=True)), frame(center=(150., 110.))
        inputs = context(original)
        result = estimator.estimate(original, inputs)
        self.assertAlmostEqual(result["lateral_error_mm"], 5., delta=.5)
        inputs["target_lane"]["heading_deg"] = 90.
        inputs["target_lane"]["point_mm"] = [70., 50.]
        result = estimator.estimate(original, inputs)
        self.assertAlmostEqual(result["lateral_error_mm"], -5., delta=.5)

    def test_coordinate_frame_mismatch_blocks_even_matching_numeric_angle(self):
        estimator, original = QualifiedCarMeasurement(configuration(accepted=True)), frame()
        inputs = context(original)
        inputs["target_lane"]["coordinate_frame_id"] = "ROBOT_BASE"
        result = estimator.estimate(original, inputs)
        self.assertEqual(result["reasons"], ["TARGET_COORDINATE_FRAME_MISMATCH"])
        self.assertEqual(result["measurement_source"], "unmeasured")

    def test_directional_heading_is_never_inferred_from_white_car_axis(self):
        estimator, original = QualifiedCarMeasurement(configuration(accepted=True)), frame()
        inputs = context(original)
        inputs["target_lane"]["parallel_axis"] = False
        result = estimator.estimate(original, inputs)
        self.assertEqual(result["measurement_source"], "unmeasured")
        self.assertIn("DIRECTED_HEADING", result["reasons"][0])

    def test_missing_or_other_frame_occlusion_check_cannot_qualify(self):
        estimator, original = QualifiedCarMeasurement(configuration(accepted=True)), frame()
        for changes in ({"occlusion_clear": False}, {"occlusion_frame_sha256": "f" * 64}):
            with self.subTest(changes=changes):
                result = estimator.estimate(original, {**context(original), **changes})
                self.assertEqual(result["measurement_source"], "unmeasured")
                self.assertEqual(result["reasons"], ["SAME_FRAME_OCCLUSION_EXCLUSION_REQUIRED"])

    def test_map_car_height_or_camera_change_invalidates_measurement(self):
        estimator, original = QualifiedCarMeasurement(configuration(accepted=True)), frame()
        for changes in ({"map_sha256": "b" * 64}, {"car_id": "different-car"}, {"working_z_mm": 8.}):
            with self.subTest(changes=changes):
                result = estimator.estimate(original, {**context(original), **changes})
                self.assertEqual(result["reasons"], ["MEASUREMENT_BINDING_CHANGED"])
        different = Frame(original.id, "new-camera", 1, 12., original.sha256, original.original_jpeg)
        self.assertEqual(estimator.estimate(different, context(different))["measurement_source"], "unmeasured")

    def test_outside_validation_hull_never_extrapolates_accepted_bounds(self):
        estimator, original = QualifiedCarMeasurement(configuration(accepted=True)), frame(center=(240., 100.))
        result = estimator.estimate(original, context(original))
        self.assertEqual(result["measurement_source"], "unmeasured")
        self.assertEqual(result["reasons"], ["OUTSIDE_INDEPENDENT_VALIDATION_COVERAGE"])

    def test_ambiguous_white_objects_never_select_nearest_guess(self):
        estimator, original = QualifiedCarMeasurement(configuration(accepted=True)), frame(second=True)
        result = estimator.estimate(original, context(original))
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["measurement_source"], "unmeasured")

    def test_tampered_hash_and_changed_detector_or_matrix_are_rejected(self):
        for mutate in (lambda v: v["qualification"].update(reference_sha256="f" * 64),
                       lambda v: v["detector"].update(saturation_max=45),
                       lambda v: v["image_to_car_plane_homography"][0].__setitem__(0, .6)):
            value = configuration(accepted=True)
            mutate(value)
            with self.assertRaises(ValueError):
                QualifiedCarMeasurement(value)

    def test_training_samples_or_bad_original_holdout_residuals_rejected(self):
        for mutate in (lambda r: r.update(used_for_fitting=True),
                       lambda r: r.update(source="tcp_target_replay"),
                       lambda r: r["samples"][0].update(reference_axis_deg=60.),
                       lambda r: r["samples"][0].update(reference_center_mm=[999., 999.]),
                       lambda r: r["samples"][0].update(independent_reference=False)):
            value = configuration(accepted=True)
            mutate(value["qualification"]["record"])
            with self.assertRaises(ValueError):
                QualifiedCarMeasurement(rehash(value))

    def test_collinear_holdout_points_do_not_validate_a_two_dimensional_region(self):
        value = configuration(accepted=True)
        for index, sample in enumerate(value["qualification"]["record"]["samples"]):
            sample["image_centroid_px"] = [50. + index * 40., 100.]
        with self.assertRaises(ValueError):
            QualifiedCarMeasurement(rehash(value))

    def test_image_evidence_hash_binds_original_bytes(self):
        estimator, original = QualifiedCarMeasurement(configuration(accepted=True)), frame()
        tampered = Frame(original.id, original.epoch, 1, 12., "f" * 64, original.original_jpeg)
        with self.assertRaises(ValueError):
            estimator.estimate(tampered, context(tampered))

    def test_estimator_preserves_original_configuration_and_frame(self):
        value, original = configuration(accepted=True), frame(angle=20.)
        before, source = deepcopy(value), original.original_jpeg
        estimator = QualifiedCarMeasurement(value)
        estimator.estimate(original, context(original))
        self.assertEqual(value, before)
        self.assertEqual(original.original_jpeg, source)


if __name__ == "__main__":
    unittest.main()
