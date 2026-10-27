"""Native MJPEG transport checks using synthetic bytes, without equipment."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import stat
import struct
import threading
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch

from tools.camera_preview import (CameraServer, FrameStore, JPEGFrames, MAX_STDERR_BYTES,
                                  ensure_device_unowned, ffmpeg_arguments, handler_for, main)


def segment(marker: int, data: bytes) -> bytes:
    return bytes((0xFF, marker)) + struct.pack(">H", len(data) + 2) + data


def jpeg(width=1920, height=1080, extra=b"", entropy=b"pixels\xff\x00stuff\xff\xd0restart"):
    # A minimal delimiter fixture, not a decoded image or camera photograph.
    sof = segment(0xC0, b"\x08" + struct.pack(">HH", height, width) + b"\x01\x01\x11\x00")
    sos = segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    return b"\xff\xd8" + extra + sof + sos + entropy + b"\xff\xd9"


class JPEGParserTests(unittest.TestCase):
    def test_every_chunk_boundary_preserves_exact_native_bytes(self):
        # EXIF-like payload includes a thumbnail's complete SOI/EOI pair.
        frame = jpeg(extra=segment(0xE1, b"opaque\xff\xd8thumbnail\xff\xd9payload"))
        for size in (1, 2, 3, 7, 17, len(frame), len(frame) + 5):
            parser = JPEGFrames()
            result = []
            source = b"noise\xff" + frame + frame + b"trailing noise"
            for index in range(0, len(source), size):
                result.extend(parser.feed(source[index:index + size]))
            self.assertEqual(result, [(frame, (1920, 1080)), (frame, (1920, 1080))])
            self.assertLessEqual(len(parser.buffer), 1)

    def test_progressive_multiple_scans_and_marker_fill(self):
        scan = segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
        frame = jpeg(entropy=b"first" + segment(0xC4, b"table") + scan + b"second\xff")
        self.assertEqual(list(JPEGFrames().feed(frame)), [(frame, (1920, 1080))])

    def test_malformed_and_truncated_input_recovers_at_next_soi(self):
        good = jpeg()
        for broken in (b"\xff\xd8\xff\xe0\x00\x01bad", b"\xff\xd8\xff\xd9",
                       jpeg()[:-2], b"\xff\xd8not-a-marker", jpeg(width=0)):
            parser = JPEGFrames()
            result = list(parser.feed(broken + good))
            self.assertEqual(result[-1:], [(good, (1920, 1080))])
            self.assertGreater(parser.discarded_frames, 0)

    def test_oversized_entropy_and_noise_remain_bounded(self):
        parser = JPEGFrames(max_bytes=128)
        source = jpeg(entropy=b"x" * 10000) + jpeg()
        output = []
        for offset in range(0, len(source), 31):
            output.extend(parser.feed(source[offset:offset + 31]))
            self.assertLessEqual(len(parser.buffer), 128)
        self.assertEqual(output, [(jpeg(), (1920, 1080))])
        self.assertGreater(parser.discarded_frames, 0)
        self.assertEqual(list(parser.feed(b"n" * 100000)), [])
        self.assertLessEqual(len(parser.buffer), 1)


class CameraTransportTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.store = FrameStore("Brio500-SYNTHETIC", "/dev/video0", clock=lambda: self.now)

    def test_lifecycle_epoch_native_dimensions_and_stderr_bound(self):
        self.assertEqual(self.store.snapshot()[0]["state"], "starting")
        self.assertNotEqual(self.store.epoch, FrameStore("Brio500-SYNTHETIC", "/dev/video0").epoch)
        with self.assertRaises(ValueError):
            self.store.publish(jpeg(width=1280), (1280, 1080))
        self.store.publish(jpeg(), (1920, 1080))
        metadata, frame = self.store.snapshot()
        self.assertEqual(metadata["state"], "live")
        self.assertEqual(frame.data, jpeg())
        self.assertEqual(metadata["frame_sequence"], 1)
        self.now += 2.001
        metadata, frame = self.store.snapshot()
        self.assertEqual((metadata["state"], metadata["frame_age_ms"], frame), ("stale", 2001, None))
        self.store.append_stderr(b"x" * (MAX_STDERR_BYTES * 2))
        self.store.append_stderr(b"tail")
        self.assertLessEqual(len(self.store.snapshot()[0]["stderr_tail"]), MAX_STDERR_BYTES)
        self.assertTrue(self.store.snapshot()[0]["stderr_tail"].endswith("tail"))
        self.store.set_fault("Disconnected; no automatic reopen.")
        self.assertEqual(self.store.snapshot()[0]["state"], "fault")

    def test_camera_id_rejects_header_injection(self):
        for camera_id in ("", "Brio\r\nBad: yes", "a" * 161, "카메라"):
            with self.assertRaises(ValueError):
                FrameStore(camera_id, "/dev/video0")

    def test_native_ffmpeg_copy_command_has_no_decode_or_scale(self):
        command = ffmpeg_arguments("/dev/video0")
        self.assertEqual(command[command.index("-c:v") + 1], "copy")
        self.assertEqual(command[command.index("-input_format") + 1], "mjpeg")
        self.assertEqual(command[command.index("-video_size") + 1], "1920x1080")
        self.assertNotIn("-vf", command)
        self.assertNotIn("-s", command)

    def test_existing_device_owner_is_refused_without_termination(self):
        with patch("tools.camera_preview.shutil.which", return_value="/usr/bin/fuser"), \
                patch("tools.camera_preview.subprocess.run", return_value=Mock(returncode=0, stdout=b" 123 456")) as run:
            with self.assertRaisesRegex(RuntimeError, "already open.*123 456"):
                ensure_device_unowned("/dev/video0")
            self.assertEqual(run.call_args.args[0], ["fuser", "--", "/dev/video0"])
        with patch("tools.camera_preview.shutil.which", return_value=None), \
                patch("tools.camera_preview.subprocess.run") as run:
            ensure_device_unowned("/dev/video0")
            run.assert_not_called()

    def test_ssh_terminal_hangup_enters_capture_cleanup(self):
        # Exercise the actual main loop's HUP path without a signal or hardware.
        handlers = {}
        restored = []

        def register(signum, handler):
            if callable(handler):
                handlers[int(signum)] = handler
                return "previous-handler"
            restored.append(int(signum))

        with patch("tools.camera_preview.os.name", "posix"), \
                patch("tools.camera_preview.Path") as path, \
                patch("tools.camera_preview.os.stat", return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
                patch("tools.camera_preview.DeviceLock"), \
                patch("tools.camera_preview.CameraServer") as server, \
                patch("tools.camera_preview.CameraCapture") as capture, \
                patch("tools.camera_preview.ensure_device_unowned"), \
                patch("tools.camera_preview.signal.SIGHUP", 1, create=True), \
                patch("tools.camera_preview.signal.signal", side_effect=register), \
                redirect_stdout(io.StringIO()):
            path.return_value.resolve.return_value = "/dev/video0"
            server.return_value.__enter__.return_value.handle_request.side_effect = lambda: handlers[1](1, None)
            self.assertEqual(main(["--device", "/dev/video0", "--camera-id", "Brio500-SYNTHETIC"]), 0)
            capture.return_value.start.assert_called_once_with()
            capture.return_value.stop.assert_called_once_with()
        self.assertIn(1, restored)

    def test_http_bytes_headers_and_identity_are_from_same_snapshot(self):
        server = CameraServer(("127.0.0.1", 0), handler_for(self.store))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: worker.join(timeout=2))
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}"
        with self.assertRaises(urllib.error.HTTPError) as response:
            urllib.request.urlopen(url + "/frame.jpg", timeout=2)
        self.assertEqual(response.exception.code, 503)
        response.exception.close()
        self.store.publish(jpeg(), (1920, 1080))
        with urllib.request.urlopen(url + "/status", timeout=2) as response:
            status = json.load(response)
        with urllib.request.urlopen(url + "/frame.jpg", timeout=2) as response:
            self.assertEqual(response.read(), jpeg())
            self.assertEqual(response.headers["Content-Type"], "image/jpeg")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Camera-Id"], status["camera_id"])
            self.assertEqual(response.headers["X-Camera-Epoch"], status["camera_epoch"])
            self.assertEqual(response.headers["X-Frame-Sequence"], "1")
            self.assertEqual(response.headers["X-Frame-Received-At"], status["frame_received_at"])
            self.assertEqual(response.headers["X-Frame-Width"], "1920")
            self.assertEqual(response.headers["X-Frame-Height"], "1080")
            self.assertEqual(response.headers["X-Frame-Age-Ms"], "0")
        self.now += 3
        with self.assertRaises(urllib.error.HTTPError) as response:
            urllib.request.urlopen(url + "/frame.jpg", timeout=2)
        self.assertEqual(response.exception.code, 503)
        response.exception.close()


if __name__ == "__main__":
    unittest.main()
