"""New intelligence frames must postdate the action in host-receive order.

Transport acceptance alone is insufficient: an upstream frame can arrive late.
These synthetic clock tests establish ordering guards, not sensor exposure time.
"""
from __future__ import annotations

import unittest

from backend.scene import SceneError
from tests import test_live_camera as camera_fixtures


class LiveCaptureOrderTests(unittest.TestCase):
    setUp = camera_fixtures.LiveCameraTests.setUp
    markers = camera_fixtures.LiveCameraTests.markers
    candidate = camera_fixtures.LiveCameraTests.candidate
    respond = camera_fixtures.LiveCameraTests.respond
    poll = camera_fixtures.LiveCameraTests.poll
    lock = camera_fixtures.LiveCameraTests.lock

    def assert_capture_code(self, code, **conditions):
        with self.assertRaises(SceneError) as raised:
            self.preview.capture(**conditions)
        self.assertEqual(raised.exception.code, code)

    def test_transport_accepted_after_boundary_but_host_received_before_is_rejected(self):
        self.lock()
        before = self.preview.capture()["metadata"]
        boundary = self.now[0]
        self.now[0] += 0.1
        self.poll(headers_override={"X-Frame-Age-Ms": "200"})
        item = self.preview._latest
        self.assertGreater(item["accepted"], boundary)
        self.assertGreater(item["frame"]["sequence"], before["sequence"])
        self.assertLess(item["accepted"] - item["upstream_age_ms"] / 1000, boundary)
        self.assert_capture_code("LIVE_CAPTURE_NOT_NEW", after_sequence=before["sequence"], not_before=boundary)
        self.now[0] += 0.1
        self.poll(headers_override={"X-Frame-Age-Ms": "10"})
        selected = self.preview.capture(after_sequence=before["sequence"], not_before=boundary)
        self.assertGreater(selected["metadata"]["sequence"], before["sequence"])
        self.assertEqual(selected["data"], self.jpeg)
        self.assertEqual(selected["metadata"]["timestamp_source"], "camera_host_receive")
        self.assertFalse(selected["metadata"]["sensor_exposure_time_known"])

    def test_host_receive_equal_to_boundary_is_not_strictly_new(self):
        self.lock()
        boundary = self.now[0]
        self.now[0] += 0.25
        self.poll(headers_override={"X-Frame-Age-Ms": "250"})
        self.assert_capture_code("LIVE_CAPTURE_NOT_NEW", not_before=boundary)

    def test_repeated_sequence_does_not_become_new_when_polled_after_boundary(self):
        self.lock()
        before = self.preview.capture()["metadata"]
        frame_id = before["id"]
        self.now[0] += 0.5
        self.preview.poll_once()  # Same epoch and sequence; the cache cannot be refreshed.
        self.assertEqual(self.preview.snapshot()["frame"]["id"], frame_id)
        self.assert_capture_code("LIVE_CAPTURE_NOT_NEW", after_sequence=before["sequence"])
        self.poll()
        after = self.preview.capture(after_sequence=before["sequence"])["metadata"]
        self.assertEqual(after["epoch"], before["epoch"])
        self.assertGreater(after["sequence"], before["sequence"])

    def test_backward_sequence_makes_capture_unavailable_instead_of_reordering(self):
        self.lock()
        before = self.preview.capture()["metadata"]
        self.sequence -= 1
        self.preview.poll_once()
        self.assertEqual(self.preview.snapshot()["frame"]["id"], before["id"])
        self.assert_capture_code("LIVE_CAPTURE_UNAVAILABLE", after_sequence=before["sequence"])

    def test_higher_sequence_from_new_epoch_cannot_reuse_old_registered_binding(self):
        self.lock()
        before = self.preview.capture()["metadata"]
        self.now[0] += 0.1
        changed = self.poll(epoch="c" * 32, sequence=200)
        self.assertGreater(changed["frame"]["sequence"], before["sequence"])
        self.assertEqual(changed["registration"]["status"], "view_changed")
        self.assert_capture_code("LIVE_CAPTURE_REGISTRATION", after_sequence=before["sequence"])
        self.preview.register(changed["epoch"], changed["frame"]["id"])
        current = self.preview.capture(after_sequence=before["sequence"])["metadata"]
        self.assertNotEqual(current["epoch"], before["epoch"])
        with self.assertRaises(SceneError) as raised:
            self.preview.check_binding(before)
        self.assertEqual(raised.exception.code, "LIVE_CAPTURE_CHANGED")


if __name__ == "__main__":
    unittest.main()
