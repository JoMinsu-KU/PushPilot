"""Synthetic feature diagnostics only; no camera or robot connection."""
from dataclasses import replace
import hashlib
import json
import unittest

import cv2
import numpy as np

from backend.robot_control.visual_probe import (
    ProbeFrame, ProbeIdentity, ProbePolicy, VisualProbeError, observe_tool_displacement,
)


class VisualProbeTests(unittest.TestCase):
    def setUp(self):
        self.identity = ProbeIdentity("synthetic-camera", "synthetic-epoch", "synthetic-map", "v1",
                                      "a" * 64, "synthetic-registration")
        self.matrix = [[2., 0., 100.], [0., 2., 50.], [0., 0., 1.]]
        self.roi = (170, 120, 160, 140)
        self.before = self.frame(1, (220, 180))
        self.after = self.frame(2, (230, 186))

    def frame(self, sequence, centre, *, image=None):
        if image is None:
            image = np.full((1080, 1920, 3), 90, np.uint8)
            x, y = centre
            cv2.rectangle(image, (x - 25, y - 15), (x + 25, y + 15), (0, 0, 255), -1)
        # Synthetic pixels stand in for a caller-verified original JPEG hash.
        digest = hashlib.sha256(image.tobytes() + str(sequence).encode()).hexdigest()
        return ProbeFrame(image, f"synthetic-frame-{sequence}", digest, sequence,
                          1000. + sequence * .25, self.identity)

    def observe(self, before=None, after=None, **kwargs):
        return observe_tool_displacement(before or self.before, after or self.after,
                                         kwargs.pop("homography", self.matrix), self.roi,
                                         now=kwargs.pop("now", 1000.6), **kwargs)

    def test_native_translation_and_apparent_paper_delta_are_not_tcp_measurements(self):
        original_before = self.before.image_bgr.copy()
        original_after = self.after.image_bgr.copy()
        original_matrix = [row[:] for row in self.matrix]
        result = self.observe(base_delta_xy_mm=[2., 0.])
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["native_dimensions"], [1920, 1080])
        np.testing.assert_allclose(result["pixel_delta_xy"], [10, 6])
        np.testing.assert_allclose(result["apparent_paper_plane_delta_mm"], [5, 3])
        self.assertEqual(result["reported_base_delta_xy_mm"], [2, 0])
        self.assertTrue(result["relative_only"])
        for field in ("absolute_tcp_measured", "car_pose_measured", "parallax_corrected",
                      "physical_qualified", "motion_issued", "homography_changed"):
            self.assertFalse(result[field])
        np.testing.assert_array_equal(self.before.image_bgr, original_before)
        np.testing.assert_array_equal(self.after.image_bgr, original_after)
        self.assertEqual(self.matrix, original_matrix)
        json.dumps(result, allow_nan=False)

    def test_different_native_rois_preserve_absolute_pixel_displacement(self):
        result = self.observe(after_roi=(200, 150, 130, 110))
        self.assertEqual(result["status"], "observed")
        np.testing.assert_allclose(result["pixel_delta_xy"], [10, 6])

    def test_homogeneous_matrix_scale_has_no_effect_and_input_matrix_is_untouched(self):
        for scale in (1e-12, 1e12):
            matrix = np.array(self.matrix) * scale
            original = matrix.copy()
            result = self.observe(homography=matrix)
            self.assertEqual(result["status"], "observed")
            np.testing.assert_allclose(result["apparent_paper_plane_delta_mm"], [5, 3])
            np.testing.assert_array_equal(matrix, original)

    def test_partial_occlusion_cannot_become_centroid_motion(self):
        image = self.after.image_bgr.copy()
        image[172:201, 218:230] = 90
        result = self.observe(after=self.frame(2, None, image=image))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "FEATURE_OCCLUDED_ROTATED_OR_CHANGED")
        self.assertNotIn("pixel_delta_xy", result)

    def test_complete_occlusion_waits_without_a_fabricated_feature(self):
        image = np.full((1080, 1920, 3), 90, np.uint8)
        result = self.observe(after=self.frame(2, None, image=image))
        self.assertEqual(result["reason"], "RED_FEATURE_MISSING_OR_AMBIGUOUS")
        self.assertNotIn("apparent_paper_plane_delta_mm", result)

    def test_red_map_background_outside_roi_is_excluded(self):
        images = [frame.image_bgr.copy() for frame in (self.before, self.after)]
        for image in images:
            cv2.rectangle(image, (600, 600), (1200, 900), (0, 0, 255), -1)
        result = self.observe(before=self.frame(1, None, image=images[0]),
                              after=self.frame(2, None, image=images[1]))
        self.assertEqual(result["status"], "observed")
        np.testing.assert_allclose(result["pixel_delta_xy"], [10, 6])

    def test_second_red_component_inside_roi_is_ambiguous(self):
        image = self.after.image_bgr.copy()
        cv2.rectangle(image, (290, 210), (310, 230), (0, 0, 255), -1)
        result = self.observe(after=self.frame(2, None, image=image))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "RED_FEATURE_MISSING_OR_AMBIGUOUS")

    def test_roi_clipping_and_large_lighting_change_wait(self):
        clipped = self.frame(2, (180, 140))
        self.assertEqual(self.observe(after=clipped)["reason"], "RED_FEATURE_CLIPPED")
        image = self.after.image_bgr.copy()
        image[(image[:, :, 2] == 255) & (image[:, :, 1] == 0)] = [0, 0, 150]
        self.assertEqual(self.observe(after=self.frame(2, None, image=image))["reason"], "FEATURE_LIGHTING_CHANGED")

    def test_visible_rotation_is_rejected_as_shape_change(self):
        image = np.full((1080, 1920, 3), 90, np.uint8)
        corners = cv2.boxPoints(((230, 186), (50, 30), 20)).astype(np.int32)
        cv2.fillConvexPoly(image, corners, (0, 0, 255))
        result = self.observe(after=self.frame(2, None, image=image))
        self.assertEqual(result["reason"], "FEATURE_OCCLUDED_ROTATED_OR_CHANGED")

    def test_unchanged_feature_is_unknown_even_with_new_frame_identity(self):
        result = self.observe(after=self.frame(2, (220, 180)))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "FEATURE_MOTION_NOT_OBSERVABLE_OR_OUT_OF_RANGE")

    def test_identity_changes_never_match_as_feature_motion(self):
        for field, value in (("camera_id", "camera2"), ("camera_epoch", "epoch2"), ("map_id", "map2"),
                             ("map_version", "v2"), ("map_hash", "b" * 64), ("registration_id", "reg2")):
            frame = replace(self.after, identity=replace(self.identity, **{field: value}))
            with self.subTest(field=field), self.assertRaisesRegex(VisualProbeError, "IDENTITY_CHANGED"):
                self.observe(after=frame)

    def test_reused_frame_id_hash_sequence_or_time_is_rejected(self):
        for changes in ({"frame_id": self.before.frame_id}, {"frame_sha256": self.before.frame_sha256},
                        {"sequence": self.before.sequence}, {"captured_at": self.before.captured_at}):
            with self.subTest(changes=changes), self.assertRaisesRegex(VisualProbeError, "STALE_OR_REUSED"):
                self.observe(after=replace(self.after, **changes))

    def test_old_future_or_overlong_pairs_are_rejected(self):
        for now in (1000.4, 1010.):
            with self.subTest(now=now), self.assertRaisesRegex(VisualProbeError, "NOT_FRESH"):
                self.observe(now=now)
        with self.assertRaisesRegex(VisualProbeError, "NOT_FRESH"):
            self.observe(before=replace(self.before, captured_at=900))

    def test_recorded_old_pair_is_explicit_diagnostic_without_physical_admission(self):
        result = self.observe(now=5000., observation_mode="recorded")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["observation_mode"], "recorded")
        self.assertFalse(result["physical_admission_allowed"] or result["physical_qualified"])
        for kwargs in ({"now": 1000.4}, {"now": 5000., "before": replace(self.before, captured_at=900)}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(VisualProbeError, "NOT_FRESH"):
                self.observe(observation_mode="recorded", **kwargs)

    def test_live_old_pair_stays_rejected_and_invalid_mode_cannot_relax_freshness(self):
        with self.assertRaisesRegex(VisualProbeError, "NOT_FRESH"):
            self.observe(now=5000., observation_mode="live")
        with self.assertRaisesRegex(VisualProbeError, "OBSERVATION_MODE"):
            self.observe(now=5000., observation_mode="ignore_age")

    def test_invalid_homography_and_horizon_do_not_project(self):
        for matrix in ([[1, 0], [0, 1]], [[1, 0, 0], [0, 0, 0], [0, 0, 1]],
                       [[1, 0, 0], [0, float("nan"), 0], [0, 0, 1]],
                       [[1, 0, 0], [0, 1, 0], [0, 0, 1e-13]],
                       np.eye(3, dtype=bool), np.eye(3).astype(str)):
            with self.subTest(matrix=matrix), self.assertRaisesRegex(VisualProbeError, "HOMOGRAPHY"):
                self.observe(homography=matrix)
        # H^-1's denominator vanishes at the first feature's x=220.
        inverse = np.array([[1., 0., 0.], [0., 1., 0.], [1., 0., -220.]])
        with self.assertRaisesRegex(VisualProbeError, "HORIZON"):
            self.observe(homography=np.linalg.inv(inverse))

    def test_invalid_native_roi_bgr_metadata_and_reported_base_delta_fail(self):
        for roi in ((0, 0, 4000, 2000), (170, 120, True, 100), (-1, 20, 100, 100)):
            with self.subTest(roi=roi), self.assertRaisesRegex(VisualProbeError, "ROI"):
                self.observe(after_roi=roi)
        for delta in ((True, 0), (0, float("inf")), (1000, 0), (0, 0, 0)):
            with self.subTest(delta=delta), self.assertRaisesRegex(VisualProbeError, "BASE_DELTA"):
                self.observe(base_delta_xy_mm=delta)
        with self.assertRaisesRegex(VisualProbeError, "NATIVE_BGR"):
            replace(self.after, image_bgr=self.after.image_bgr.astype(np.float32))
        with self.assertRaisesRegex(VisualProbeError, "FRAME_BINDING"):
            replace(self.after, frame_sha256="unverified")
        with self.assertRaisesRegex(VisualProbeError, "PROBE_INPUT"):
            self.observe(policy=False)

    def textured_pair(self, dx=4, dy=3):
        image = np.full((1080, 1920, 3), 90, np.uint8)
        random = np.random.default_rng(14)
        texture = np.kron(random.integers(120, 255, (20, 20), np.uint8), np.ones((5, 5), np.uint8))
        image[140:240, 200:300] = 0
        image[140:240, 200:300, 2] = texture
        after = cv2.warpAffine(image, np.array([[1., 0., dx], [0., 1., dy]]), (1920, 1080),
                               borderValue=(90, 90, 90))
        return self.frame(1, None, image=image), self.frame(2, None, image=after)

    def test_explicit_sparse_flow_tracks_textured_red_patch(self):
        before, after = self.textured_pair()
        result = self.observe(before, after, method="sparse_flow")
        self.assertEqual(result["status"], "observed", result)
        self.assertEqual(result["method"], "sparse_flow")
        np.testing.assert_allclose(result["pixel_delta_xy"], [4, 3], atol=.05)
        self.assertGreaterEqual(result["quality"]["retained_points"], 8)
        self.assertFalse(result["quality"]["calibrated_probability"])
        self.assertFalse(result["absolute_tcp_measured"])

    def test_sparse_flow_partial_occlusion_and_mixed_motion_wait(self):
        before, after = self.textured_pair()
        image = after.image_bgr.copy()
        image[143:210, 204:265] = 90
        result = self.observe(before, self.frame(2, None, image=image), method="sparse_flow")
        self.assertEqual(result["status"], "unknown")
        image = np.full_like(before.image_bgr, 90)
        image[140:240, 196:246] = before.image_bgr[140:240, 200:250]
        image[140:240, 254:304] = before.image_bgr[140:240, 250:300]
        result = self.observe(before, self.frame(2, None, image=image), method="sparse_flow")
        self.assertEqual(result["status"], "unknown")

    def test_sparse_flow_static_noisy_and_low_texture_do_not_invent_motion(self):
        before, after = self.textured_pair(0, 0)
        self.assertEqual(self.observe(before, after, method="sparse_flow")["reason"],
                          "FEATURE_MOTION_NOT_OBSERVABLE_OR_OUT_OF_RANGE")
        before, after = self.textured_pair()
        image = np.clip(after.image_bgr.astype(np.int16) + np.random.default_rng(3).integers(
            -45, 46, after.image_bgr.shape), 0, 255).astype(np.uint8)
        self.assertEqual(self.observe(before, self.frame(2, None, image=image), method="sparse_flow")["status"], "unknown")
        self.assertEqual(self.observe(method="sparse_flow")["reason"], "FLOW_LOW_TEXTURE")

    def test_sparse_flow_repetitive_patch_is_ambiguous_and_never_a_silent_fallback(self):
        image = np.zeros((1080, 1920, 3), np.uint8)
        yy, xx = np.indices((1080, 1920))
        pattern = (((yy // 5 + xx // 5) % 2) * 90 + 140).astype(np.uint8)
        image[:, :, 2] = pattern
        after_image = cv2.warpAffine(image, np.array([[1., 0., 4.], [0., 1., 0.]]), (1920, 1080))
        result = self.observe(self.frame(1, None, image=image), self.frame(2, None, image=after_image), method="sparse_flow")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(self.observe()["method"], "component")
        with self.assertRaisesRegex(VisualProbeError, "OBSERVATION_METHOD"):
            self.observe(method="auto")


if __name__ == "__main__":
    unittest.main()
