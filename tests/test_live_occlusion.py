"""Expected marker covers preserve fixed-view continuity and live eligibility."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from backend.scene import SceneError
from tests import test_live_camera as fixtures


class LiveOcclusionTests(unittest.TestCase):
    setUp = fixtures.LiveCameraTests.setUp
    markers = fixtures.LiveCameraTests.markers
    candidate = fixtures.LiveCameraTests.candidate
    respond = fixtures.LiveCameraTests.respond
    poll = fixtures.LiveCameraTests.poll
    lock = fixtures.LiveCameraTests.lock

    def assert_inference_withheld(self, metadata):
        for operation in (self.preview.capture, lambda: self.preview.check_binding(metadata)):
            with self.assertRaises(SceneError) as error:
                operation()
            self.assertEqual(error.exception.code, "LIVE_CAPTURE_REGISTRATION")

    def test_covering_then_uncovering_preserves_reference_and_keeps_new_native_frames(self):
        original = self.lock()
        binding = self.preview.capture()["metadata"]
        previous_sequence = original["frame"]["sequence"]
        for missing, status in (((10,), "locked_partial"), ((10, 11), "locked_partial"),
                                ((10, 11, 12), "locked_occluded"), ((10, 11, 12, 13), "locked_occluded"),
                                ((), "locked")):
            current = self.poll(detection=self.markers(missing=missing))
            self.assertEqual(current["registration"]["status"], status)
            self.assertEqual(current["registration"]["id"], original["registration"]["id"])
            self.assertEqual(current["registration"]["homography"], original["registration"]["homography"])
            self.assertGreater(current["frame"]["sequence"], previous_sequence)
            self.assertEqual(current["detection"]["marker_ids"], [value for value in (10, 11, 12, 13) if value not in missing])
            self.assertEqual(self.preview.image(current["frame"]["id"]), self.jpeg)
            self.assertEqual(self.preview.capture()["metadata"]["registration"]["status"], status)
            if status == "locked_occluded":
                self.assertEqual(current["registration"]["verification"], "insufficient_visibility")
            self.preview.check_binding(binding)
            previous_sequence = current["frame"]["sequence"]

    def test_clustered_markers_do_not_verify_alignment_or_block_fixed_view_operation(self):
        original = self.lock()
        binding = self.preview.capture()["metadata"]
        corners = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        known = {10: corners, 11: corners + [2, 0]}
        detection = {"marker_ids": [10, 11], "markers": [
            {"id": identifier, "corners": value.tolist()} for identifier, value in known.items()]}
        with patch.object(self.preview, "_known_corners", return_value=known):
            current = self.poll(detection=detection)
            self.assertEqual(current["registration"]["status"], "locked_occluded")
            self.assertEqual(current["registration"]["homography"], original["registration"]["homography"])
            self.assertEqual(current["registration"]["verification"], "insufficient_visibility")
            self.preview.check_binding(binding)

    def test_disagreement_and_duplicate_ids_cannot_qualify_partial_evidence(self):
        original = self.lock()
        binding = self.preview.capture()["metadata"]
        doubtful = self.markers(missing=(10,))
        doubtful["markers"][0]["corners"][0][0] += 8
        doubtful["markers"][1]["corners"][0][0] += 8
        duplicate = self.markers(missing=(10, 11, 12))
        duplicate["markers"].append(deepcopy(duplicate["markers"][0]))
        nonfinite = self.markers(missing=(10,))
        nonfinite["markers"][0]["corners"][0][0] = float("nan")
        for detection in (doubtful, duplicate, nonfinite):
            current = self.poll(detection=detection)
            self.assertEqual(current["registration"]["status"], "locked_occluded")
            self.assertEqual(current["registration"]["verification"], "marker_disagreement")
            self.assertEqual(current["registration"]["id"], original["registration"]["id"])
            self.assert_inference_withheld(binding)

    def test_one_noisy_marker_does_not_block_distributed_matching_support(self):
        original = self.lock()
        binding = self.preview.capture()["metadata"]
        noisy = self.markers()
        noisy["markers"][0]["corners"][0][0] += 8
        current = self.poll(detection=noisy)
        self.assertEqual(current["registration"]["status"], "locked_partial")
        self.assertEqual(current["registration"]["verification"], "visible_markers")
        self.assertEqual(current["registration"]["homography"], original["registration"]["homography"])
        self.preview.check_binding(binding)

    def test_repeated_sequence_cannot_confirm_displacement_and_latch_survives_cover(self):
        original = self.lock()
        shifted = self.markers(shift=(12, 0))
        first = self.poll(detection=shifted)
        self.assertEqual(first["registration"]["status"], "locked_occluded")
        for _ in range(4):
            self.preview.poll_once()
            self.assertEqual(self.preview.snapshot()["registration"]["status"], "locked_occluded")
        self.poll(detection=self.markers(missing=(10, 11, 12, 13)))
        self.poll(detection=shifted)
        self.poll(detection=shifted)
        changed = self.poll(detection=shifted)
        self.assertEqual(changed["registration"]["status"], "view_changed")
        self.assertIsNone(changed["registration"]["homography"])
        for missing in ((10, 11, 12, 13), ()):
            current = self.poll(detection=self.markers(missing=missing))
            self.assertEqual(current["registration"]["status"], "view_changed")
            self.assertEqual(current["registration"]["id"], original["registration"]["id"])

    def test_search_hint_is_bound_to_current_camera_identity_and_latched_view(self):
        with patch.object(self.preview, "_detect", wraps=self.preview._detect) as detector:
            original = self.lock()
            self.assertIsNone(detector.call_args.kwargs["reference_homography"])
            self.poll(detection=self.markers(missing=(10,)))
            self.assertEqual(detector.call_args.kwargs["reference_homography"], original["registration"]["homography"])
            self.poll(epoch="b" * 32)
            self.assertIsNone(detector.call_args.kwargs["reference_homography"])
            self.poll(epoch="a" * 32)
            self.assertIsNone(detector.call_args.kwargs["reference_homography"])
