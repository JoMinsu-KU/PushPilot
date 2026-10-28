"""Camera capture must fail closed without creating robot commands."""
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from tools.capture_camera_intrinsics import run


class CaptureIntrinsicsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        token = self.root / "pushpilot-robot-control/shared/control.token"
        token.parent.mkdir(parents=True)
        token.write_text("unit-test-token")
        self.target = self.root / "target.html"
        self.target.write_text("unit-test-checkerboard")
        self.optics = self.root / "optics.json"
        self.write_optics()
        self.robot = {"armed": False, "hold": True, "active_commands": [],
                      "receiver": {"connected": True, "idle": True, "session_id": "test-session",
                                   "seq": 7, "profile_id": "test-profile", "actual_pose": [0, 0, 7, 180, 0, 0]}}

    def write_optics(self, *, auto=0, age=0, zoom=131):
        record = {"checked_at_utc": (dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=age)).isoformat(),
                  "valid": True, "controls": {"focus_automatic_continuous": auto, "focus_absolute": 20,
                    "zoom_absolute": zoom, "pan_absolute": 0, "tilt_absolute": 0}}
        self.optics.write_text(json.dumps(record))

    def invoke(self, opener):
        with patch("tools.capture_camera_intrinsics.Path.home", return_value=self.root), \
             patch("tools.capture_camera_intrinsics.urllib.request.build_opener", return_value=opener):
            return run(self.root/"new-private-output", self.optics, self.target, 60, 16)

    def opener(self, width=1920, height=1080, change_zoom=False):
        case = self
        _, image = cv2.imencode(".jpg", np.zeros((height, width, 3), np.uint8))
        raw = image.tobytes()

        class Opener:
            def __init__(self):
                self.calls = []
                self.status_reads = 0
                self.frames = 0

            def open(self, request, timeout):
                self.calls.append(request)
                case.assertEqual(request.get_method(), "GET")
                case.assertIsNone(request.data)
                if request.full_url == "http://127.0.0.1:8897/v1/status":
                    self.status_reads += 1
                    if change_zoom and self.status_reads == 2:
                        case.write_optics(zoom=132)
                    payload = json.dumps(case.robot).encode()
                elif request.full_url == "http://127.0.0.1:8080/api/v1/live-camera":
                    self.frames += 1
                    payload = json.dumps({"camera_id": "test-camera", "epoch": "test-epoch", "state": "live",
                        "frame": {"age_ms": 10, "sequence": self.frames, "image_url": "/native-test.jpg",
                                  "sha256": hashlib.sha256(raw).hexdigest()}}).encode()
                elif request.full_url == "http://127.0.0.1:8080/native-test.jpg":
                    payload = raw
                else:
                    raise AssertionError("Unexpected endpoint, never admit a command path")
                return io.BytesIO(payload)
        return Opener()

    def test_autofocus_is_rejected_before_any_camera_frame_read(self):
        self.write_optics(auto=1)
        opener = self.opener()
        with self.assertRaisesRegex(RuntimeError, "AUTOFOCUS"):
            self.invoke(opener)
        self.assertEqual([r.full_url for r in opener.calls], ["http://127.0.0.1:8897/v1/status"])

    def test_stale_optics_cannot_be_substituted_for_current_settings(self):
        self.write_optics(age=30)
        with self.assertRaisesRegex(RuntimeError, "FRESH_VERIFIED_OPTICS"):
            self.invoke(self.opener())

    def test_active_robot_is_rejected_before_capture_or_arming(self):
        self.robot["armed"] = True
        opener = self.opener()
        with self.assertRaisesRegex(RuntimeError, "ROBOT_NOT_HELD"):
            self.invoke(opener)
        self.assertEqual(len(opener.calls), 1)

    def test_resolution_change_preserves_failure_without_model_or_commands(self):
        opener = self.opener(width=640, height=480)
        result = self.invoke(opener)
        self.assertEqual(result["terminal_reason"], "NATIVE_RESOLUTION_CHANGED")
        self.assertFalse(result["model_attempted"])
        self.assertFalse(result["physical_qualified"])
        self.assertFalse(result["robot_commands_created"])
        saved = json.loads((self.root/"new-private-output/capture.private.json").read_text())
        self.assertEqual(saved, result)

    def test_optics_change_stops_without_retry_or_model_fitting(self):
        opener = self.opener(change_zoom=True)
        with patch("tools.capture_camera_intrinsics.cv2.findChessboardCornersSB", return_value=(False, None)), \
             patch("tools.capture_camera_intrinsics.time.sleep"):
            result = self.invoke(opener)
        self.assertEqual(result["terminal_reason"], "CAMERA_OPTICS_CHANGED")
        self.assertEqual(result["accepted_views"], 0)
        self.assertFalse(result["model_attempted"])
        self.assertFalse(result["motion_issued"])


if __name__ == "__main__":
    unittest.main()
