"""Native-resolution one-bit marker recovery with strict print-geometry guards."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from backend.live_detector import LiveMarkerDetector
from backend.maps import MapDefinition
from backend.scene import SceneStore


class LiveDetectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.map = MapDefinition()
        self.scene = SceneStore(self.temporary.name, self.map)
        self.detector = LiveMarkerDetector(self.map, self.scene._detect, self.scene._candidate)

    def image(self, *, wrong_layout=False, absent=()):
        image = np.full((1200, 1800, 3), 255, dtype=np.uint8)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        for marker in self.map.data["markers"]:
            if marker["id"] in absent:
                continue
            side = int(marker["size_mm"]*4)
            pixels = cv2.aruco.generateImageMarker(dictionary, marker["id"], side)
            if marker["id"] in {10, 11}:
                cell = side//6
                # Flip exactly one of the 4x4 data cells, preserving black border.
                pixels[cell:2*cell, cell:2*cell] = 255-pixels[cell:2*cell, cell:2*cell]
            center_x = marker["center_mm"][0]
            if wrong_layout and marker["id"] in {10, 11}:
                center_x = 400-center_x
            x = int((center_x-marker["size_mm"]/2)*4+100)
            y = int((marker["center_mm"][1]-marker["size_mm"]/2)*4+100)
            image[y:y+side, x:x+side] = cv2.cvtColor(pixels, cv2.COLOR_GRAY2BGR)
        return image

    def test_one_bit_recovery_requires_complete_consistent_print(self):
        image = self.image()
        self.assertEqual(self.scene._detect(image)["marker_ids"], [12, 13])
        recovered = self.detector(image)
        self.assertEqual(recovered["marker_ids"], [10, 11, 12, 13])
        self.assertIsNotNone(self.scene._candidate(recovered, image.shape[1], image.shape[0]))

    def test_wrong_layout_and_missing_marker_cannot_use_relaxed_recovery(self):
        for image in (self.image(wrong_layout=True), self.image(absent=(11,))):
            baseline = self.scene._detect(image)
            self.assertEqual(self.detector(image), baseline)

    def test_decoding_preserves_raw_bytes_array_and_recorded_store(self):
        success, encoded = cv2.imencode(".jpg", self.image())
        self.assertTrue(success)
        data = encoded.tobytes()
        checksum = hashlib.sha256(data).hexdigest()
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        original_pixels = image.copy()
        original_scene = self.scene.snapshot()
        result = self.detector(image)
        self.assertEqual(result["marker_ids"], [10, 11, 12, 13])
        self.assertTrue(np.array_equal(image, original_pixels))
        self.assertEqual(hashlib.sha256(data).hexdigest(), checksum)
        self.assertEqual(self.scene.snapshot(), original_scene)
        self.assertFalse((Path(self.temporary.name)/"scene.json").exists())

    def test_recovered_corners_cannot_override_conflicting_baseline(self):
        image = self.image()
        baseline = self.scene._detect(image)
        conflicting = deepcopy(baseline)
        conflicting["markers"][0]["corners"] = [[x+15, y] for x, y in conflicting["markers"][0]["corners"]]
        detector = LiveMarkerDetector(self.map, lambda _: conflicting, self.scene._candidate)
        self.assertEqual(detector(image), conflicting)

    def test_full_baseline_is_returned_without_relaxed_decode(self):
        baseline = {"marker_ids": [10, 11, 12, 13], "markers": []}
        detector = LiveMarkerDetector(self.map, lambda _: baseline, self.scene._candidate)
        with patch("backend.live_detector.cv2.cvtColor", side_effect=AssertionError("Unexpected fallback")):
            self.assertIs(detector(np.zeros((10, 10, 3), np.uint8)), baseline)

    @staticmethod
    def detection_output(markers, rejected=()):
        return ([np.array(marker["corners"], dtype=np.float32).reshape(1, 4, 2) for marker in markers],
                np.array([[marker["id"]] for marker in markers], dtype=np.int32), list(rejected))

    def test_partial_mistaken_id_is_not_merged_across_sampling_profiles(self):
        image = self.image()
        recovered = self.detector(image)
        correct = recovered["markers"]
        false_partial = deepcopy([marker for marker in correct if marker["id"] != 11])
        false_partial[0]["id"] = 11
        outputs = [self.detection_output(false_partial), self.detection_output(correct)]
        detectors = [Mock(detectMarkers=Mock(return_value=output)) for output in outputs]
        baseline = self.scene._detect(image)
        detector = LiveMarkerDetector(self.map, lambda _: baseline, self.scene._candidate)
        with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=detectors):
            self.assertEqual(detector(image), recovered)

    def test_small_native_roi_recovers_missing_id_with_original_pixel_offsets(self):
        image = self.image()
        recovered = self.detector(image)
        missing = recovered["markers"][0]
        partial = recovered["markers"][1:]
        quad = np.array(missing["corners"], dtype=np.float32).reshape(1, 4, 2)
        x, y, _width, _height = cv2.boundingRect(quad.reshape(4, 2))
        offset = [max(0, x-15), max(0, y-15)]
        local = {"id": missing["id"], "corners": (np.array(missing["corners"])-offset).tolist()}
        outputs = [self.detection_output(partial, [quad]), self.detection_output(partial, [quad]),
                   self.detection_output([local]), self.detection_output([local])]
        detectors = [Mock(detectMarkers=Mock(return_value=output)) for output in outputs]
        baseline = self.scene._detect(image)
        detector = LiveMarkerDetector(self.map, lambda _: baseline, self.scene._candidate)
        with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=detectors):
            result = detector(image)
        self.assertEqual(result["marker_ids"], [10, 11, 12, 13])
        self.assertTrue(np.allclose(result["markers"][0]["corners"], missing["corners"], atol=0.001))
        self.assertIsNotNone(self.scene._candidate(result, image.shape[1], image.shape[0]))
        roi_argument = detectors[2].detectMarkers.call_args.args[0]
        self.assertLess(roi_argument.shape[0], 200)
        self.assertLess(roi_argument.shape[1], 200)

    @staticmethod
    def reference():
        return np.array([[4., 0., 100.], [0., 4., 100.], [0., 0., 1.]])

    def reference_pixels(self, identifier, reference=None):
        matrix = self.reference() if reference is None else reference
        corners = self.scene._known_corners()[identifier]
        homogeneous = np.column_stack((corners, np.ones(4))) @ (matrix/np.max(np.abs(matrix))).T
        return homogeneous[:, :2]/homogeneous[:, 2, None]

    def reference_partial(self, identifiers=(11, 12, 13), reference=None):
        return {"marker_ids": list(identifiers), "markers": [
            {"id": identifier, "corners": self.reference_pixels(identifier, reference).tolist()}
            for identifier in identifiers]}

    def local_target(self, identifier=10, *, shift=0):
        pixels = self.reference_pixels(identifier)
        x, y, _width, _height = cv2.boundingRect(pixels.astype(np.float32))
        return {"id": identifier, "corners": (pixels-[max(0, x-15), max(0, y-15)]+shift).tolist()}

    def mocked_reference_decode(self, outputs, baseline=None, candidate=None):
        baseline = self.reference_partial() if baseline is None else baseline
        candidate = self.scene._candidate if candidate is None else candidate
        detector = LiveMarkerDetector(self.map, lambda _: baseline, candidate)
        roi_calls, global_calls = [], []

        def factory(_dictionary, parameters):
            if parameters.cornerRefinementMethod == cv2.aruco.CORNER_REFINE_APRILTAG:
                output = outputs[min(len(roi_calls), len(outputs)-1)]
                roi_calls.append(parameters)
            else:
                output = self.detection_output(baseline["markers"])
                global_calls.append(parameters)
            return Mock(detectMarkers=Mock(return_value=output))
        return detector, baseline, factory, roi_calls, global_calls

    def test_reference_roi_decodes_actual_missing_markers_before_full_frame_fallback(self):
        image = self.image()
        pixels_before = image.copy()
        baseline = self.scene._detect(image)
        self.assertEqual(baseline["marker_ids"], [12, 13])
        detector = LiveMarkerDetector(self.map, lambda _: baseline, self.scene._candidate)
        original_factory = cv2.aruco.ArucoDetector
        crops, parameters_seen = [], []

        def factory(dictionary, parameters):
            self.assertEqual(parameters.cornerRefinementMethod, cv2.aruco.CORNER_REFINE_APRILTAG)
            self.assertEqual(parameters.errorCorrectionRate, 1.0)
            self.assertEqual(parameters.perspectiveRemovePixelPerCell, 12)
            self.assertIn(parameters.perspectiveRemoveIgnoredMarginPerCell, (0.13, 0.30))
            parameters_seen.append(parameters)
            actual = original_factory(dictionary, parameters)

            def decode(roi):
                crops.append(roi.copy())
                return actual.detectMarkers(roi)
            return Mock(detectMarkers=Mock(side_effect=decode))

        with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=factory):
            recovered = detector(image, reference_homography=self.reference())
        self.assertEqual(recovered["marker_ids"], [10, 11, 12, 13])
        self.assertIsNotNone(self.scene._candidate(recovered, image.shape[1], image.shape[0]))
        self.assertLessEqual(len(parameters_seen), 4)
        self.assertTrue(np.array_equal(image, pixels_before))
        native_gray = cv2.cvtColor(pixels_before, cv2.COLOR_BGR2GRAY)
        for identifier, crop in zip((10, 11), crops):
            x, y, width, height = cv2.boundingRect(self.reference_pixels(identifier).astype(np.float32))
            expected_crop = native_gray[max(0, y-15):y+height+15, max(0, x-15):x+width+15]
            self.assertTrue(np.array_equal(crop, expected_crop))
            self.assertLessEqual(max(crop.shape), 190)
        for marker in recovered["markers"]:
            self.assertTrue(detector._matches_reference(marker["corners"], self.reference_pixels(marker["id"])))

    def test_reference_cannot_create_a_detection_for_a_genuinely_absent_marker(self):
        image = self.image(absent=(10,))
        baseline = self.scene._detect(image)
        pixels_before = image.copy()
        self.assertNotIn(10, baseline["marker_ids"])
        result = self.detector(image, reference_homography=self.reference())
        self.assertEqual(result, baseline)
        self.assertTrue(np.array_equal(image, pixels_before))

    def test_reference_roi_rejects_wrong_id_position_and_duplicate_target(self):
        local = self.local_target()
        wrong_id = deepcopy(local)
        wrong_id["id"] = 17
        wrong_known_id = deepcopy(local)
        wrong_known_id["id"] = 11
        wrong_location = self.local_target(shift=10)
        nonfinite = deepcopy(local)
        nonfinite["corners"][0][0] = float("nan")
        for targets in ([wrong_id], [wrong_known_id], [wrong_location], [local, local], [nonfinite]):
            with self.subTest(targets=targets):
                output = self.detection_output(targets)
                detector, baseline, factory, roi_calls, global_calls = self.mocked_reference_decode([output])
                with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=factory):
                    self.assertEqual(detector(np.zeros((1200, 1800, 3), np.uint8),
                                              reference_homography=self.reference()), baseline)
                self.assertEqual(len(roi_calls), 2)
                self.assertEqual(len(global_calls), 2)

    def test_reference_roi_ignores_unrelated_ids_and_requires_strict_print_candidate(self):
        local = self.local_target()
        unrelated = deepcopy(local)
        unrelated["id"] = 17
        output = self.detection_output([unrelated, local])
        for accepted in (True, False):
            with self.subTest(accepted=accepted):
                candidate = Mock(return_value={"accepted": True} if accepted else None)
                detector, baseline, factory, roi_calls, global_calls = self.mocked_reference_decode([output], candidate=candidate)
                with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=factory):
                    result = detector(np.zeros((1200, 1800, 3), np.uint8), reference_homography=self.reference())
                self.assertEqual(result["marker_ids"], [10, 11, 12, 13] if accepted else baseline["marker_ids"])
                if accepted:
                    self.assertTrue(np.allclose(result["markers"][0]["corners"], self.reference_pixels(10)))
                    self.assertEqual(len(roi_calls), 1)
                    self.assertFalse(global_calls)
                else:
                    self.assertEqual(result, baseline)
                    self.assertEqual(len(roi_calls), 2)
                candidate.assert_called()

    def test_invalid_or_changed_reference_cannot_select_a_target_roi(self):
        shifted = self.reference()
        shifted[0, 2] += 20
        invalid = [np.zeros((3, 3)), np.eye(2), np.full((3, 3), float("nan")), shifted,
                   [[1, 0, 0], [0, 1, 0], [0, 0, 0]], "invalid"]
        for reference in invalid:
            with self.subTest(reference=reference):
                detector, baseline, factory, roi_calls, global_calls = self.mocked_reference_decode(
                    [self.detection_output([self.local_target()])])
                with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=factory):
                    result = detector(np.zeros((1200, 1800, 3), np.uint8), reference_homography=reference)
                self.assertEqual(result, baseline)
                self.assertFalse(roi_calls)
                self.assertEqual(len(global_calls), 2)

    def test_current_baseline_needs_two_distributed_matching_markers(self):
        one = self.reference_partial((13,))
        outlier = self.reference_partial()
        outlier["markers"][0]["corners"][0][0] += 10
        duplicate = self.reference_partial()
        duplicate["markers"].append(deepcopy(duplicate["markers"][0]))
        mismatched_ids = self.reference_partial()
        mismatched_ids["marker_ids"] = [12, 13]
        for baseline in (one, outlier, duplicate, mismatched_ids):
            with self.subTest(baseline=baseline):
                detector, _, factory, roi_calls, _ = self.mocked_reference_decode(
                    [self.detection_output([self.local_target()])], baseline=baseline)
                with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=factory):
                    self.assertEqual(detector(np.zeros((1200, 1800, 3), np.uint8),
                                              reference_homography=self.reference()), baseline)
                self.assertFalse(roi_calls)

        # Two close map anchors cannot establish distributed current agreement.
        data = self.map.data
        data["markers"][1]["center_mm"] = [data["markers"][0]["center_mm"][0]+20,
                                            data["markers"][0]["center_mm"][1]]
        self.map = MapDefinition.from_data(data)
        self.scene.map_definition = self.map
        baseline = self.reference_partial((10, 11))
        detector, _, factory, roi_calls, _ = self.mocked_reference_decode(
            [self.detection_output([self.local_target()])], baseline=baseline)
        with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=factory):
            self.assertEqual(detector(np.zeros((1200, 1800, 3), np.uint8),
                                      reference_homography=self.reference()), baseline)
        self.assertFalse(roi_calls)

    def test_projected_crop_size_is_bounded_before_native_decode(self):
        for scale in (0.5, 12):
            with self.subTest(scale=scale):
                reference = np.array([[scale, 0., 100.], [0., scale, 100.], [0., 0., 1.]])
                baseline = self.reference_partial(reference=reference)
                detector, _, factory, roi_calls, _ = self.mocked_reference_decode(
                    [self.detection_output([self.local_target()])], baseline=baseline)
                with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=factory):
                    result = detector(np.zeros((1200, 1800, 3), np.uint8), reference_homography=reference)
                self.assertEqual(result, baseline)
                self.assertFalse(roi_calls)

    def test_complete_ordinary_decode_wins_even_with_a_reference(self):
        baseline = {"marker_ids": [10, 11, 12, 13], "markers": []}
        detector = LiveMarkerDetector(self.map, lambda _: baseline, self.scene._candidate)
        with patch("backend.live_detector.cv2.cvtColor", side_effect=AssertionError("Unexpected recovery")):
            self.assertIs(detector(np.zeros((10, 10, 3), np.uint8), reference_homography=self.reference()), baseline)

    def test_reference_search_has_at_most_eight_native_decodes(self):
        data = self.map.data
        data["markers"].extend([
            {"id": 14, "center_mm": [100., 100.], "size_mm": 16.},
            {"id": 15, "center_mm": [300., 100.], "size_mm": 16.},
        ])
        self.map = MapDefinition.from_data(data)
        self.scene.map_definition = self.map
        baseline = self.reference_partial((12, 13))
        outputs = [self.detection_output([self.local_target(identifier)])
                   for identifier in (10, 11, 14, 15)*2]
        detector, _, factory, roi_calls, global_calls = self.mocked_reference_decode(
            outputs, baseline=baseline, candidate=Mock(return_value=None))
        with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=factory):
            self.assertEqual(detector(np.zeros((1200, 1800, 3), np.uint8),
                                      reference_homography=self.reference()), baseline)
        self.assertEqual(len(roi_calls), 8)
        self.assertEqual(len(global_calls), 2)

        # A future map with more missing IDs must not expand the search budget.
        data["markers"].append({"id": 16, "center_mm": [200., 150.], "size_mm": 16.})
        self.map = MapDefinition.from_data(data)
        self.scene.map_definition = self.map
        detector, _, factory, roi_calls, _ = self.mocked_reference_decode(
            outputs, baseline=baseline, candidate=Mock(return_value=None))
        with patch("backend.live_detector.cv2.aruco.ArucoDetector", side_effect=factory):
            self.assertEqual(detector(np.zeros((1200, 1800, 3), np.uint8),
                                      reference_homography=self.reference()), baseline)
        self.assertFalse(roi_calls)
