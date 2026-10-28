"""Synthetic camera-model evidence only; no capture or physical calibration."""
from dataclasses import replace
from contextlib import contextmanager
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from backend.robot_control.camera_intrinsics import (
    CameraIntrinsicsError, CameraIntrinsicsIdentity, CheckerboardObservation,
    CheckerboardPattern, IntrinsicsPolicy, calibrate_camera_intrinsics,
)


class CameraIntrinsicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity = CameraIntrinsicsIdentity("synthetic-camera", "synthetic-epoch", "a" * 64)
        cls.pattern = CheckerboardPattern("synthetic-square-grid", "b" * 64, 9, 6)
        cls.matrix = np.array([[1500., 0, 945.], [0, 1480., 550.], [0, 0, 1.]])
        cls.distortion = np.array([-.12, .03, .001, -.0007, .005])
        cls.train_ids = tuple(f"view-{i}" for i in range(12))
        cls.heldout_ids = tuple(f"view-{i}" for i in range(12, 16))
        cls.observations = cls.synthetic_views()

    @classmethod
    def synthetic_views(cls, *, frontoparallel=False, noise=.035):
        poses = [
            ((-.35, -.25, .05), (450, 300), 25),
            ((.30, -.20, -.08), (1450, 320), 25),
            ((-.25, .30, .10), (500, 760), 25),
            ((.30, .25, -.10), (1400, 760), 26),
            ((-.15, -.35, -.10), (900, 320), 23),
            ((.38, .12, .13), (950, 750), 25),
            ((-.30, .20, -.13), (530, 530), 22),
            ((.20, -.30, .10), (1350, 530), 24),
            ((-.12, .38, .05), (850, 550), 30),
            ((.28, -.35, -.10), (1100, 450), 28),
            ((-.35, -.10, .15), (750, 670), 27),
            ((.15, .30, -.15), (1200, 650), 29),
            ((-.22, -.32, .08), (650, 420), 26),
            ((.32, .18, -.08), (1250, 690), 24),
            ((-.28, .26, .12), (760, 700), 28),
            ((.18, -.24, -.12), (1200, 350), 27),
        ]
        points = cls.pattern.object_points()
        center = points.mean(axis=0)
        rng = np.random.default_rng(194205)
        result = []
        for i, (rotation, target, depth) in enumerate(poses):
            rvec = np.array([0., 0., rotation[2]]) if frontoparallel else np.array(rotation)
            matrix, _ = cv2.Rodrigues(rvec)
            camera_center = np.array([(target[0]-945)*depth/1500, (target[1]-550)*depth/1480, depth])
            tvec = camera_center - matrix @ center
            image_points, _ = cv2.projectPoints(points, rvec, tvec, cls.matrix, cls.distortion)
            image_points = image_points.reshape(-1, 2).astype(float)
            image_points += rng.normal(0, noise, image_points.shape)
            result.append(CheckerboardObservation(
                f"view-{i}", hashlib.sha256(f"synthetic-{i}".encode()).hexdigest(), cls.identity,
                cls.pattern.pattern_id, cls.pattern.pattern_sha256, image_points.tolist()))
        return result

    def calibrate(self, observations=None, **kwargs):
        return calibrate_camera_intrinsics(
            observations if observations is not None else self.observations,
            training_ids=kwargs.pop("training_ids", self.train_ids),
            heldout_ids=kwargs.pop("heldout_ids", self.heldout_ids),
            identity=kwargs.pop("identity", self.identity),
            pattern=kwargs.pop("pattern", self.pattern), **kwargs)

    @contextmanager
    def frozen_solver_spies(self):
        """Test separation of inputs, without comparing independent SVD runs."""
        real_calibrate, real_pose = cv2.calibrateCameraExtended, cv2.solvePnP
        calls = {"training": [], "pose": []}
        calibration_result, pose_results = [], {}

        def calibration(*args, **kwargs):
            calls["training"].append(copy.deepcopy(args[:3]))
            if not calibration_result:
                calibration_result.append(real_calibrate(*args, **kwargs))
            return copy.deepcopy(calibration_result[0])

        def pose(*args, **kwargs):
            calls["pose"].append(copy.deepcopy(args[:4]))
            key = tuple((np.asarray(a).shape, np.asarray(a).dtype.str,
                         np.asarray(a).tobytes()) for a in args[:4])
            if key not in pose_results:
                pose_results[key] = real_pose(*args, **kwargs)
            return copy.deepcopy(pose_results[key])

        with patch("backend.robot_control.camera_intrinsics.cv2.calibrateCameraExtended", side_effect=calibration), \
                patch("backend.robot_control.camera_intrinsics.cv2.solvePnP", side_effect=pose):
            yield calls

    def assert_same_training_inputs(self, calls):
        self.assertEqual(len(calls["training"]), 2)
        for objects, corners, size in calls["training"]:
            self.assertEqual(size, (1920, 1080))
            self.assertEqual(len(objects), len(self.train_ids))
            self.assertEqual(len(corners), len(self.train_ids))
            for index, (grid, points) in enumerate(zip(objects, corners)):
                np.testing.assert_array_equal(grid, self.pattern.object_points())
                np.testing.assert_array_equal(points, np.array(
                    self.observations[index].image_points_px, dtype=np.float32))

    def test_recovers_known_camera_with_distortion_and_unused_pose_checks(self):
        report = self.calibrate()
        self.assertTrue(report["accepted_image_model"], report["failure_reasons"])
        fitted = np.array(report["camera_matrix"])
        np.testing.assert_allclose(fitted, self.matrix, atol=2, rtol=0)
        self.assertLess(abs(report["distortion_coefficients"][0] - self.distortion[0]), .005)
        self.assertLess(report["opencv_training_rms_px"], .08)
        self.assertEqual([r["id"] for r in report["heldout"]], list(self.heldout_ids))
        self.assertTrue(all(r["rms_error_px"] < .1 for r in report["heldout"]))
        self.assertEqual(report["discarded_observation_ids"], [])
        self.assertEqual(report["discarded_corner_indices"], [])
        self.assertEqual(report["heldout_pose_fit_corner_indices"], list(range(0, 54, 2)))
        self.assertEqual(report["heldout_unused_check_corner_indices"], list(range(1, 54, 2)))
        for field in ("physical_qualified", "contact_face_qualified", "board_base_transform_established",
                      "motion_authority", "automatically_installed"):
            self.assertIs(report[field], False)
        self.assertIn("not physical accuracy", report["uncertainty"])
        json.dumps(report, allow_nan=False)

    def test_square_units_change_extrinsic_units_without_changing_intrinsics(self):
        first = self.calibrate()
        second = self.calibrate(pattern=replace(self.pattern, square_size_units=17))
        self.assertTrue(second["accepted_image_model"])
        np.testing.assert_allclose(first["camera_matrix"], second["camera_matrix"], atol=.001, rtol=0)
        np.testing.assert_allclose(np.array(first["training"][0]["tvec_pattern_units"])*17,
                                   second["training"][0]["tvec_pattern_units"], atol=.001, rtol=0)

    def test_corrupted_heldout_image_fails_without_refitting_training_model(self):
        observations = list(self.observations)
        points = np.array(observations[13].image_points_px)
        points[::2, 0] += 3
        points[1::2, 0] -= 3
        observations[13] = replace(observations[13], image_points_px=points.tolist())
        with self.frozen_solver_spies() as calls:
            clean = self.calibrate()
            report = self.calibrate(observations)
        self.assert_same_training_inputs(calls)
        self.assertFalse(report["accepted_image_model"])
        self.assertIn("HELDOUT_VIEW_RMS_EXCEEDED:view-13", report["failure_reasons"])
        np.testing.assert_array_equal(clean["camera_matrix"], report["camera_matrix"])
        np.testing.assert_array_equal(clean["distortion_coefficients"], report["distortion_coefficients"])
        self.assertEqual(len(report["heldout"]), 4)
        self.assertEqual(len(report["heldout"][1]["corner_errors_px"]), 54)
        self.assertEqual(report["discarded_observation_ids"], [])

    def test_unused_heldout_corruption_cannot_change_subset_fitted_pose(self):
        observations = list(self.observations)
        points = np.array(observations[14].image_points_px)
        points[1::2] += [2.5, -2]
        observations[14] = replace(observations[14], image_points_px=points.tolist())
        with self.frozen_solver_spies() as calls:
            clean = self.calibrate()
            corrupted = self.calibrate(observations)
        self.assert_same_training_inputs(calls)
        self.assertEqual(len(calls["pose"]), 8)
        for index in range(4):
            first_inputs, second_inputs = calls["pose"][index], calls["pose"][index + 4]
            for first_input, second_input in zip(first_inputs, second_inputs):
                np.testing.assert_array_equal(first_input, second_input)
            np.testing.assert_array_equal(first_inputs[0], self.pattern.object_points()[::2])
            np.testing.assert_array_equal(first_inputs[1], np.array(
                self.observations[index + 12].image_points_px, dtype=np.float64)[::2])
        self.assertFalse(corrupted["accepted_image_model"])
        self.assertIn("HELDOUT_VIEW_RMS_EXCEEDED:view-14", corrupted["failure_reasons"])
        first, second = clean["heldout"][2], corrupted["heldout"][2]
        np.testing.assert_array_equal(first["rvec"], second["rvec"])
        np.testing.assert_array_equal(first["tvec_pattern_units"], second["tvec_pattern_units"])
        self.assertEqual(first["pose_fit_rms_error_px"], second["pose_fit_rms_error_px"])
        self.assertLess(second["pose_fit_rms_error_px"], .1)
        self.assertGreater(second["unused_rms_error_px"], 3)
        self.assertEqual(second["pose_fit_corner_indices"], list(range(0, 54, 2)))
        self.assertEqual(second["check_corner_indices"], list(range(1, 54, 2)))
        json.dumps(corrupted, allow_nan=False)

    def test_one_bad_training_corner_is_preserved_and_fails_per_view_limit(self):
        observations = list(self.observations)
        points = np.array(observations[2].image_points_px)
        points[22] += [10, 7]
        observations[2] = replace(observations[2], image_points_px=points.tolist())
        report = self.calibrate(observations)
        self.assertFalse(report["accepted_image_model"])
        self.assertIn("TRAINING_VIEW_RMS_EXCEEDED:view-2", report["failure_reasons"])
        self.assertGreater(report["training"][2]["max_error_px"], 8)
        self.assertEqual(len(report["training"][2]["corner_errors_px"]), 54)

    def test_camera_epoch_settings_and_pattern_changes_are_rejected(self):
        for change in (replace(self.identity, camera_epoch="other-epoch"),
                       replace(self.identity, settings_sha256="c"*64),
                       replace(self.identity, camera_id="other-camera")):
            observations = list(self.observations)
            observations[-1] = replace(observations[-1], identity=change)
            with self.subTest(identity=change), self.assertRaisesRegex(CameraIntrinsicsError, "Mixed camera"):
                self.calibrate(observations)
        observations = list(self.observations)
        observations[0] = replace(observations[0], pattern_sha256="d"*64)
        with self.assertRaisesRegex(CameraIntrinsicsError, "same declared checkerboard"):
            self.calibrate(observations)

    def test_reused_image_and_observation_ids_are_rejected(self):
        for field, value in (("image_sha256", self.observations[0].image_sha256), ("observation_id", "view-0")):
            observations = list(self.observations)
            observations[1] = replace(observations[1], **{field: value})
            with self.subTest(field=field), self.assertRaisesRegex(CameraIntrinsicsError, "Reused"):
                self.calibrate(observations)

    def test_split_is_complete_disjoint_predeclared_and_large_enough(self):
        with self.assertRaisesRegex(CameraIntrinsicsError, "disjoint"):
            self.calibrate(heldout_ids=("view-0", "view-13", "view-14", "view-15"))
        with self.assertRaisesRegex(CameraIntrinsicsError, "every supplied"):
            self.calibrate(training_ids=self.train_ids[:-1])
        with self.assertRaisesRegex(CameraIntrinsicsError, "at least 10"):
            self.calibrate(training_ids=self.train_ids[:9])
        with self.assertRaisesRegex(CameraIntrinsicsError, "cannot repeat"):
            self.calibrate(training_ids=(*self.train_ids, "view-0"))

    def test_invalid_native_points_and_incomplete_or_folded_grids_fail(self):
        for value in (float("nan"), float("inf"), True, -1, 1920):
            points = [list(p) for p in self.observations[0].image_points_px]
            points[0][0] = value
            with self.subTest(value=value), self.assertRaises(CameraIntrinsicsError):
                replace(self.observations[0], image_points_px=points)
        observations = list(self.observations)
        observations[0] = replace(observations[0], image_points_px=observations[0].image_points_px[:-1])
        with self.assertRaisesRegex(CameraIntrinsicsError, "complete declared"):
            self.calibrate(observations)
        points = list(self.observations[0].image_points_px)
        points[0], points[1] = points[1], points[0]
        observations[0] = replace(self.observations[0], image_points_px=points)
        with self.assertRaisesRegex(CameraIntrinsicsError, "folded"):
            self.calibrate(observations)

    def test_translation_and_distance_changes_without_tilt_are_insufficient(self):
        observations = self.synthetic_views(frontoparallel=True, noise=0)
        # Radial distortion can perturb a planar homography, so use exact
        # pinhole observations here to isolate missing tilt observability.
        clean = []
        for observation in observations:
            points = np.array(observation.image_points_px)
            undistorted = cv2.undistortPoints(points, self.matrix, self.distortion, P=self.matrix).reshape(-1, 2)
            clean.append(replace(observation, image_points_px=undistorted.tolist()))
        with self.assertRaisesRegex(CameraIntrinsicsError, "tilts|unobservable"):
            self.calibrate(clean)

    def test_repeated_same_view_with_different_hashes_has_no_spatial_diversity(self):
        observations = [replace(o, image_points_px=self.observations[0].image_points_px) for o in self.observations]
        with self.assertRaisesRegex(CameraIntrinsicsError, "spatial diversity"):
            self.calibrate(observations)

    def test_limits_cannot_be_weakened_after_observing_results(self):
        for field in ("max_training_rms_px", "max_per_view_rms_px", "max_heldout_rms_px"):
            with self.subTest(field=field), self.assertRaisesRegex(CameraIntrinsicsError, "cannot be relaxed"):
                IntrinsicsPolicy(**{field: 1.5})
        with self.assertRaises(CameraIntrinsicsError):
            replace(self.pattern, square_size_units=True)
        with self.assertRaisesRegex(CameraIntrinsicsError, "native"):
            replace(self.identity, width=1280, height=720)

    def test_solver_failure_retains_failed_report_without_substitute_model(self):
        with patch("backend.robot_control.camera_intrinsics.cv2.calibrateCameraExtended",
                   side_effect=cv2.error("synthetic numerical failure")):
            report = self.calibrate()
        self.assertFalse(report["accepted_image_model"])
        self.assertEqual(report["failure_reasons"], ["OPENCV_CALIBRATION_FAILED"])
        self.assertNotIn("camera_matrix", report)
        self.assertFalse(report["motion_authority"])
        self.assertEqual(report["discarded_observation_ids"], [])

    def test_nonfinite_solver_result_is_not_serialised_as_a_camera_model(self):
        invalid = (float("nan"), np.eye(3), np.zeros((1, 5)), [], [], np.zeros((18, 1)),
                   np.zeros((72, 1)), np.zeros((12, 1)))
        with patch("backend.robot_control.camera_intrinsics.cv2.calibrateCameraExtended", return_value=invalid):
            report = self.calibrate()
        self.assertEqual(report["failure_reasons"], ["NONFINITE_CALIBRATION_RESULT"])
        self.assertFalse(report["accepted_image_model"])
        self.assertNotIn("camera_matrix", report)
        self.assertFalse(report["motion_authority"])
        json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
