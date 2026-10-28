"""Synthetic car-only observation tests; no site, BASE or vehicle qualification."""
from copy import deepcopy
import hashlib
import unittest

import cv2
import numpy as np

from backend.robot_control.vehicle_observation import (
    VehicleObservationConfig, compare_vehicle_observations, observe_white_vehicle, project_vehicle_axis,
)


def encoded_scene(*, center=(150, 120), angle=0., extra_car=False, clipping=False, shadow=False):
    image = np.full((240, 400, 3), 65, dtype=np.uint8)
    if clipping:
        center = (100, 120)
    box = cv2.boxPoints((center, (100, 40), angle)).astype(np.int32)
    cv2.fillConvexPoly(image, box, (225, 225, 225))
    if shadow:
        image[100:141, 100:135] = 175
    if extra_car:
        cv2.rectangle(image, (235, 100), (335, 140), (225, 225, 225), -1)
    # Small printed white car and coloured pusher are excluded by shape/colour.
    cv2.rectangle(image, (345, 110), (365, 120), (245, 245, 245), -1)
    if not clipping:
        cv2.rectangle(image, (75, 95), (95, 145), (10, 15, 230), -1)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def config(**changes):
    return VehicleObservationConfig(**{
        "roi_xywh": (80, 65, 260, 115), "area_range_px2": (2500., 6000.),
        "long_side_range_px": (80., 120.), "short_side_range_px": (30., 55.), **changes})


def observation(raw=None, *, identifier="synthetic-frame", settings=None, homography=None):
    raw = raw or encoded_scene()
    return observe_white_vehicle(raw, settings or config(),
        source_identity={"camera_epoch": "synthetic-camera", "frame_id": identifier,
                         "frame_sha256": hashlib.sha256(raw).hexdigest()},
        nominal_board_to_image_homography=homography)


class VehicleObservationTests(unittest.TestCase):
    def test_original_hash_visible_body_centroid_and_axis_have_no_robot_authority(self):
        raw = encoded_scene()
        result = observation(raw)
        self.assertEqual(result["status"], "readable", result)
        self.assertEqual(result["original_frame_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertAlmostEqual(result["centroid_px"][0], 150., places=3)
        self.assertAlmostEqual(result["centroid_px"][1], 120., places=3)
        self.assertAlmostEqual(result["axis_deg_mod180"], 0., places=3)
        self.assertFalse(result["tcp_tracking_used"] or result["motion_authority"] or result["physical_metric_pose_qualified"])
        self.assertFalse(result["heading_front_back_resolved"] or result["occlusion_independently_excluded"])

    def test_body_at_roi_boundary_is_not_reconstructed(self):
        result = observation(encoded_scene(clipping=True))
        self.assertEqual(result["status"], "unreadable")
        self.assertIsNone(result["centroid_px"])
        self.assertTrue(any(sample["clipped_body_candidate"] for sample in result["threshold_samples"]))

    def test_multiple_physical_size_candidates_do_not_choose_nearest_or_largest(self):
        result = observation(encoded_scene(extra_car=True))
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["centroid_px"])

    def test_partial_shadow_changes_are_uncertain_without_filling(self):
        result = observation(encoded_scene(shadow=True), settings=config(min_solidity=.5))
        self.assertNotEqual(result["status"], "readable")
        self.assertIsNone(result["centroid_px"])

    def test_threshold_sensitivity_rejects_a_contradictory_outline(self):
        image = np.full((240, 400, 3), 65, dtype=np.uint8)
        cv2.rectangle(image, (100, 100), (200, 140), (225,)*3, -1)
        cv2.rectangle(image, (100, 100), (119, 140), (185,)*3, -1)
        ok, encoded = cv2.imencode(".png", image)
        self.assertTrue(ok)
        result = observation(encoded.tobytes(), settings=config(long_side_range_px=(70., 120.)))
        self.assertEqual(result["status"], "uncertain", result)
        self.assertGreater(result["centroid_spread_px"], 3.)

    def test_config_hash_roi_and_homography_are_explicit(self):
        for changes in ({"value_thresholds": (170, 180)}, {"value_thresholds": (170, 170, 200)},
                        {"area_range_px2": (6000., 2500.)}, {"max_axis_spread_deg": 45.},
                        {"border_margin_px": 0}, {"long_side_range_px": (80., float("nan"))}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                config(**changes)
        with self.assertRaises(ValueError):
            observe_white_vehicle(encoded_scene(), config(), source_identity={"frame_sha256": "a"*64})
        with self.assertRaises(ValueError):
            observation(settings=config(roi_xywh=(80, 65, 350, 115)))
        with self.assertRaises(ValueError):
            observation(homography=np.zeros((3, 3)))

    def test_nominal_plane_projection_retains_body_height_and_parallax_limit(self):
        result = observation(homography=[[2., 0., 0.], [0., 2., 0.], [0., 0., 1.]])
        nominal = result["nominal_board"]
        self.assertAlmostEqual(nominal["centroid_nominal_board_mm"][0], 75., places=3)
        self.assertAlmostEqual(nominal["centroid_nominal_board_mm"][1], 60., places=3)
        self.assertEqual(nominal["reported_car_length_width_height_mm"], [45., 18., 15.])
        self.assertFalse(nominal["plane_projection_parallax_corrected"] or nominal["physical_metric_pose_qualified"])
        self.assertIsNone(nominal["physical_parallax_and_shape_error_bound"])

    def test_explicit_image_to_board_projection_has_inspectable_axis_points(self):
        matrix = [[.5, 0., 0.], [0., .25, 0.], [0., 0., 1.]]
        projected = project_vehicle_axis([150., 120.], 45., matrix)
        self.assertEqual(projected["centroid_nominal_board_mm"], [75., 30.])
        self.assertAlmostEqual(projected["axis_nominal_board_deg_mod180"], 26.565051, places=5)
        self.assertIsNone(projected["physical_parallax_and_shape_error_bound"])
        raw = encoded_scene()
        result = observe_white_vehicle(raw, config(), source_identity={"camera_epoch": "synthetic-camera",
            "frame_id": "projection", "frame_sha256": hashlib.sha256(raw).hexdigest()},
            nominal_image_to_board_homography=matrix)
        self.assertEqual(result["nominal_board"]["centroid_nominal_board_mm"], [75., 30.])

    def test_explicit_external_occlusion_suppresses_centroid_instead_of_filling(self):
        raw = encoded_scene()
        result = observe_white_vehicle(raw, config(), source_identity={"camera_epoch": "synthetic-camera",
            "frame_id": "occluded", "frame_sha256": hashlib.sha256(raw).hexdigest()}, occlusion_status="occluded")
        self.assertEqual(result["status"], "occluded")
        self.assertIsNone(result["centroid_px"])

    def test_comparison_uses_distinct_bound_frames_and_keeps_pixel_units(self):
        before = observation()
        after = observation(encoded_scene(center=(160, 125), angle=10.), identifier="synthetic-after")
        comparison = compare_vehicle_observations(before, after)
        self.assertEqual(comparison["status"], "readable", comparison)
        self.assertAlmostEqual(comparison["centroid_delta_px"][0], 9.5, delta=1.)
        self.assertAlmostEqual(comparison["centroid_delta_px"][1], 4.5, delta=1.)
        self.assertAlmostEqual(comparison["axis_delta_deg"], 10., delta=1.)
        self.assertIsNone(comparison["directed_heading_deg"])
        self.assertFalse(comparison["physical_metric_pose_qualified"] or comparison["motion_authority"])
        self.assertEqual(compare_vehicle_observations(before, before)["status"], "source_mismatch")
        changed = deepcopy(after)
        changed["source_identity"]["camera_epoch"] = "new-camera"
        self.assertEqual(compare_vehicle_observations(before, changed)["status"], "source_mismatch")

    def test_bounded_temporal_axis_wrap_requires_explicit_prior_for_front(self):
        before = observation(encoded_scene(angle=-4.))
        after = observation(encoded_scene(angle=4.), identifier="after-wrap")
        result = compare_vehicle_observations(before, after, previous_directed_heading_deg=356.)
        self.assertEqual(result["status"], "readable", result)
        self.assertAlmostEqual(result["directed_heading_deg"], 364., delta=1.)
        self.assertEqual(result["front_identity_source"], "caller_prior_assumption")
        self.assertEqual(compare_vehicle_observations(before, after, previous_directed_heading_deg=90.)["status"], "heading_prior_disagrees")
        self.assertEqual(compare_vehicle_observations(before, after, max_axis_change_deg=5.)["status"], "axis_change_exceeds_declared_bound")

    def test_unreadable_inputs_and_changed_display_projection_never_supply_nominal_delta(self):
        before = observation(homography=[[2., 0., 0.], [0., 2., 0.], [0., 0., 1.]])
        after = observation(encoded_scene(center=(160, 120)), homography=[[3., 0., 0.], [0., 3., 0.], [0., 0., 1.]])
        result = compare_vehicle_observations(before, after)
        self.assertEqual(result["status"], "readable")
        self.assertIsNone(result["nominal_board_delta"])
        after["status"] = "unreadable"
        self.assertEqual(compare_vehicle_observations(before, after)["status"], "unreadable")


if __name__ == "__main__":
    unittest.main()
