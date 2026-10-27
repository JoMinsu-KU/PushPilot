"""Resume an exact server-held display transform with fresh partial evidence."""
from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

import httpx
import numpy as np

from backend.live_camera import LiveCamera
from backend.scene import SceneError
from tests import test_live_camera as camera_fixtures


class LiveReferenceTests(unittest.TestCase):
    markers = camera_fixtures.LiveCameraTests.markers
    candidate = camera_fixtures.LiveCameraTests.candidate
    respond = camera_fixtures.LiveCameraTests.respond
    poll = camera_fixtures.LiveCameraTests.poll
    lock = camera_fixtures.LiveCameraTests.lock

    def setUp(self):
        camera_fixtures.LiveCameraTests.setUp(self)
        self.receipt = self.lock()
        self.preview.close()
        self.preview = LiveCamera("http://127.0.0.1:8895", self.map,
                                  lambda _: deepcopy(self.detection), self.candidate,
                                  transport=httpx.MockTransport(self.respond), clock=lambda: self.now[0])
        self.addCleanup(self.preview.close)
        self.poll(detection=self.markers(missing=(10,)))

    def reject(self, receipt=None, code=None):
        with self.assertRaises(SceneError) as raised:
            self.preview.restore_reference(self.receipt if receipt is None else receipt)
        if code:
            self.assertEqual(raised.exception.code, code)

    def test_three_marker_resume_uses_exact_old_matrix_new_binding_and_original_pixels(self):
        original = deepcopy(self.receipt["registration"]["homography"])
        detector = self.preview._detect
        with patch.object(self.preview, "_candidate", side_effect=AssertionError("Resuming must never refit.")):
            resumed = self.preview.restore_reference(self.receipt)
        registration = resumed["registration"]
        self.assertEqual(registration["status"], "locked_partial")
        self.assertEqual(registration["homography"], original)
        self.assertNotEqual(registration["id"], self.receipt["registration"]["id"])
        self.assertEqual(registration["resumed_from"], self.receipt["registration"]["id"])
        self.assertEqual(registration["reference_frame_id"], self.receipt["registration"]["reference_frame_id"])
        self.assertEqual(registration["resume_frame_id"], resumed["frame"]["id"])
        self.assertEqual(resumed["detection"]["marker_ids"], [11, 12, 13])
        self.assertIs(self.preview._detect, detector)
        self.assertEqual(self.preview.image(resumed["frame"]["id"]), self.jpeg)
        self.assertFalse(resumed["motion_authority"])
        self.assertFalse(self.preview.capture()["metadata"]["sensor_exposure_time_known"])
        self.assertEqual(self.preview.restore_reference(self.receipt)["registration"]["id"], registration["id"])

    def test_two_distributed_markers_suffice_without_synthesizing_hidden_regions(self):
        self.poll(detection=self.markers(missing=(10, 12)))
        resumed = self.preview.restore_reference(self.receipt)
        self.assertEqual(resumed["registration"]["status"], "locked_partial")
        self.assertEqual(resumed["detection"]["marker_ids"], [11, 13])
        self.assertEqual(resumed["registration"]["homography"], self.receipt["registration"]["homography"])

    def test_zero_or_one_visible_marker_rejects_without_installing_a_reference(self):
        for missing in ((10, 11, 12, 13), (10, 11, 12)):
            self.poll(detection=self.markers(missing=missing))
            self.reject(code="LIVE_REFERENCE_MARKERS")
            self.assertIsNone(self.preview._reference)

    def test_nearby_marker_pair_is_insufficient_for_distributed_agreement(self):
        first = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
        known = {11: first, 13: first + [2, 0]}
        self.preview._latest["detection"] = {"marker_ids": [11, 13], "markers": [
            {"id": identifier, "corners": corners.tolist()} for identifier, corners in known.items()]}
        with patch.object(self.preview, "_known_corners", return_value=known):
            self.reject(code="LIVE_REFERENCE_MARKERS")
        self.assertIsNone(self.preview._reference)

    def test_wrong_schema_camera_epoch_dimensions_map_or_sequence_is_rejected(self):
        mutations = []
        for key, value in (("schema_version", "other"), ("epoch", "b" * 32), ("camera_id", "another-camera"),
                           ("map_id", "other"), ("map_version", "other"), ("map_hash", "other"),
                           ("motion_authority", True), ("enabled", False)):
            receipt = deepcopy(self.receipt)
            receipt[key] = value
            mutations.append(receipt)
        for key, value in (("width", 1920), ("height", 1080), ("sequence", None), ("sequence", 10000)):
            receipt = deepcopy(self.receipt)
            receipt["frame"][key] = value
            mutations.append(receipt)
        for key in ("id", "reference_frame_id"):
            receipt = deepcopy(self.receipt)
            receipt["registration"][key] = "invalid"
            mutations.append(receipt)
        receipt = deepcopy(self.receipt)
        receipt["registration"]["status"] = "view_changed"
        mutations.append(receipt)
        for receipt in mutations:
            with self.subTest(receipt=receipt):
                self.reject(receipt, "LIVE_REFERENCE_IDENTITY")
                self.assertIsNone(self.preview._reference)

    def test_nonfinite_singular_malformed_or_shifted_matrix_is_rejected(self):
        matrices = [None, [[1, 0], [0, 1]], [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
                    [[float("nan"), 0, 0], [0, 1, 0], [0, 0, 1]],
                    [[True, 0, 0], [0, 1, 0], [0, 0, 1]], [[1, 0, 12], [0, 1, 0], [0, 0, 1]]]
        for matrix in matrices:
            receipt = deepcopy(self.receipt)
            receipt["registration"]["homography"] = matrix
            with self.subTest(matrix=matrix):
                self.reject(receipt)
                self.assertIsNone(self.preview._reference)

    def test_coherent_current_shift_and_any_bad_visible_marker_reject_exact_old_reference(self):
        self.poll(detection=self.markers(missing=(10,), shift=(12, 0)))
        self.reject(code="LIVE_REFERENCE_MARKERS")
        detection = self.markers(missing=(10,))
        detection["markers"][0]["corners"][0][0] += 7
        self.poll(detection=detection)
        self.reject(code="LIVE_REFERENCE_MARKERS")
        self.assertIsNone(self.preview._reference)

    def test_current_frame_must_be_fresh_cached_error_free_and_from_current_map(self):
        self.now[0] += 2
        self.reject(code="LIVE_REFERENCE_UNAVAILABLE")
        self.poll()
        self.preview._last_error = "Synthetic error."
        self.reject(code="LIVE_REFERENCE_UNAVAILABLE")
        self.preview._last_error = None
        self.preview._frames.clear()
        self.reject(code="LIVE_REFERENCE_UNAVAILABLE")
        self.poll()
        self.map.geometry_hash = "changed-map"
        self.reject(code="LIVE_REFERENCE_UNAVAILABLE")

    def test_confirmed_changed_view_or_unrelated_current_reference_cannot_be_replaced(self):
        self.preview._changed = True
        self.reject(code="LIVE_REFERENCE_CHANGED")
        self.preview._changed = False
        self.poll(detection=self.markers())
        current = self.preview.snapshot()
        self.preview.register(current["epoch"], current["frame"]["id"])
        existing = deepcopy(self.preview._reference)
        self.reject(code="LIVE_REFERENCE_IDENTITY")
        self.assertEqual(self.preview._reference, existing)


if __name__ == "__main__":
    unittest.main()
