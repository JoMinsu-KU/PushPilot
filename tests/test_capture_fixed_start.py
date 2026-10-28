"""Coordinate-only fixed-start capture stays independent of visual occlusion."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.robot_control.start_reference import StartIdentity
from tools import capture_fixed_start as tool


class FixedStartCaptureTests(unittest.TestCase):
    def setUp(self):
        self.identity = StartIdentity("synthetic-map", "v1", "a" * 64, "synthetic-tcp", "b" * 64, "synthetic-tool")
        self.pose = [10.037, -20.046, 100.049, -179.997, .003, -.041]
        self.joint = [1., 2., 3., 4., 5., 6.]
        self.state = {"armed": False, "active_commands": [], "receiver": {
            "connected": True, "idle": True, "reason": "RECEIVER_IDLE",
            "session_id": "a" * 32, "profile_id": "c" * 64, "seq": 7,
            "actual_pose": self.pose, "actual_joint": self.joint}}
        self.row = {"program_before": [2], "program_after": [2], "flags": [1, 1, 0, 0, 0, 0],
                    "pose": [10., -20., 100., -180., 0., 0.], "joint": self.joint, "speed": [0.] * 6}
        self.native = SimpleNamespace(snapshot=Mock(side_effect=lambda **kwargs: deepcopy(self.row)))
        self.load = Mock(return_value={"transport": SimpleNamespace(Native=Mock(return_value=self.native))})
        self.reader = Mock(side_effect=lambda: deepcopy(self.state))

    def capture(self, **changes):
        return tool.capture(self.identity, Path("synthetic-runtime"), changes.pop("get_status", self.reader),
                            operator_fixed_setup=True, runtime_loader=self.load, sleep=Mock(),
                            clock=Mock(side_effect=[1000., 1000.1, 1000.2, 1000.3, 1000.4]), **changes)

    def test_current_capture_needs_no_image_or_visible_car_and_never_returns_robot(self):
        result = self.capture().to_dict()
        self.assertEqual(self.reader.call_count, 2)
        self.assertEqual(self.native.snapshot.call_count, 3)
        self.assertEqual(list(result["tcp_mm_deg"]), self.pose)
        self.assertEqual(result["car_initial_source"], "operator_fixed_setup")
        self.assertFalse(result["car_pose_measured"] or result["geometry_qualified"] or result["motion_issued"])
        self.assertNotIn("car_visible", result)

    def test_acknowledgement_precedes_any_io(self):
        with self.assertRaises(ValueError):
            tool.capture(self.identity, "unused", self.reader, runtime_loader=self.load)
        self.reader.assert_not_called()
        self.load.assert_not_called()

    def test_changed_session_sequence_or_pose_cannot_be_frozen(self):
        for key, value in (("seq", 8), ("session_id", "d" * 32), ("actual_pose", [11.] + self.pose[1:])):
            before, after = deepcopy(self.state), deepcopy(self.state)
            after["receiver"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "CHANGED_DURING_CAPTURE"):
                self.capture(get_status=Mock(side_effect=[before, after]))

    def test_armed_or_active_capture_rejected_before_native_construction(self):
        for state in ({**self.state, "armed": True}, {**self.state, "active_commands": [{"pending": True}]}):
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.capture(get_status=Mock(return_value=state))
        self.load.assert_not_called()

    def test_native_failure_is_not_retried_or_replaced_with_previous_readback(self):
        self.native.snapshot.side_effect = TimeoutError("synthetic-private-detail")
        with self.assertRaises(TimeoutError):
            self.capture()
        self.assertEqual(self.native.snapshot.call_count, 1)

    def test_private_reference_is_new_exclusive_file(self):
        reference = self.capture()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "private/start.json"
            tool.save_reference(path, reference)
            saved = path.read_bytes()
            self.assertEqual(json.loads(saved)["schema"], "pushpilot.fixed-start-reference.v1")
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                tool.save_reference(path, reference)
            self.assertEqual(path.read_bytes(), saved)

    def test_remote_or_credentialed_url_rejected_before_token_read(self):
        for url in ("http://192.168.10.31:8897", "https://127.0.0.1:8897", "http://user@127.0.0.1:8897",
                    "http://127.0.0.1:8897/other", "http://127.0.0.1:8897?x=1", "http://:pw@127.0.0.1:8897"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                tool.status_reader(url, Path("nonexistent-token"))

    def test_status_reader_constructs_only_authenticated_get(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "control.token"
            path.write_text("test-token-" + "x" * 40)
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = json.dumps(self.state).encode()
            opener = Mock()
            opener.open.return_value = response
            with patch.object(tool.urllib.request, "build_opener", return_value=opener):
                self.assertEqual(tool.status_reader("http://127.0.0.1:8897", path)(), self.state)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_method(), "GET")
            self.assertTrue(request.full_url.endswith("/v1/status"))
            self.assertIsNone(request.data)


if __name__ == "__main__":
    unittest.main()
