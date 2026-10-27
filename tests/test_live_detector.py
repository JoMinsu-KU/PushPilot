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
