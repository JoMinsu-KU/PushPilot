"""Serve one native MJPEG camera on loopback without decoding or saving frames.

Run deliberately on GX10 with an explicit camera device and identity. This tool
owns only its ffmpeg child. It never starts robot services, changes camera
controls, retries an open, or writes images to disk. A new process has a new
camera epoch. Frame timestamps are host receive times, not exposure timestamps.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import threading
import time
from typing import Callable
import uuid


MAX_FRAME_BYTES = 8 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
MAX_STDERR_BYTES = 16 * 1024
NATIVE_WIDTH = 1920
NATIVE_HEIGHT = 1080
STALE_AFTER_MS = 2000
SOF_MARKERS = frozenset((0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                         0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF))


class JPEGFrames:
    """Incrementally delimit JPEGs, honoring segment lengths and byte stuffing.

    No image decoder or encoder is used. Embedded EXIF thumbnails cannot end a
    frame because length-delimited segment payloads are skipped as opaque bytes.
    Malformed and oversized frames are discarded; memory remains bounded.
    """

    def __init__(self, max_bytes: int = MAX_FRAME_BYTES):
        if max_bytes < 32:
            raise ValueError("The JPEG byte limit must be at least 32.")
        self.max_bytes = max_bytes
        self.buffer = bytearray()
        self.position = 0
        self.mode = "seek"
        self.dimensions: tuple[int, int] | None = None
        self.saw_scan = False
        self.discarded_frames = 0

    def _reset(self):
        self.position = 0
        self.mode = "seek"
        self.dimensions = None
        self.saw_scan = False

    def _discard(self, end: int = 2):
        del self.buffer[:end]
        self.discarded_frames += 1
        self._reset()

    def feed(self, data: bytes):
        # The capture reader uses 64 KiB chunks. Also bound arbitrary callers.
        for offset in range(0, len(data), READ_CHUNK_BYTES):
            self.buffer.extend(data[offset:offset + READ_CHUNK_BYTES])
            yield from self._extract()

    def _extract(self):
        while True:
            if self.mode == "seek":
                start = self.buffer.find(b"\xff\xd8")
                if start < 0:
                    # Retain a possible split SOI marker, not unbounded noise.
                    self.buffer[:] = b"\xff" if self.buffer[-1:] == b"\xff" else b""
                    return
                del self.buffer[:start]
                self.position = 2
                self.mode = "marker"

            if self.position > self.max_bytes:
                self._discard()
                continue

            if self.mode == "entropy":
                found = self.buffer.find(b"\xff", self.position)
                if found < 0:
                    self.position = len(self.buffer)
                    if len(self.buffer) > self.max_bytes:
                        self._discard()
                        continue
                    return
                self.position = found
                if found + 1 >= len(self.buffer):
                    if len(self.buffer) > self.max_bytes:
                        self._discard()
                        continue
                    return
                code = self.buffer[found + 1]
                if code == 0x00 or 0xD0 <= code <= 0xD7:
                    self.position += 2
                    continue
                if code == 0xFF:
                    self.position += 1
                    continue
                self.mode = "marker"

            if self.position + 2 > len(self.buffer):
                return
            if self.buffer[self.position] != 0xFF:
                self._discard(self.position + 1)
                continue
            code = self.buffer[self.position + 1]
            if code == 0xFF:
                self.position += 1
                continue
            if code == 0xD8:
                # Restart after a truncated or malformed preceding frame.
                self._discard(self.position)
                continue
            if code == 0xD9:
                end = self.position + 2
                if not self.saw_scan or self.dimensions is None or end > self.max_bytes:
                    self._discard(end)
                    continue
                frame = bytes(self.buffer[:end])
                dimensions = self.dimensions
                del self.buffer[:end]
                self._reset()
                yield frame, dimensions
                continue
            if code == 0x00 or code == 0x01 or 0xD0 <= code <= 0xD7:
                self._discard(self.position + 2)
                continue
            if self.position + 4 > len(self.buffer):
                return
            length = int.from_bytes(self.buffer[self.position + 2:self.position + 4], "big")
            end = self.position + 2 + length
            if length < 2 or end > self.max_bytes:
                self._discard(self.position + 2)
                continue
            if end > len(self.buffer):
                return
            if code in SOF_MARKERS:
                if length < 8:
                    self._discard(end)
                    continue
                height = int.from_bytes(self.buffer[self.position + 5:self.position + 7], "big")
                width = int.from_bytes(self.buffer[self.position + 7:self.position + 9], "big")
                if width < 1 or height < 1:
                    self._discard(end)
                    continue
                self.dimensions = (width, height)
            self.position = end
            if code == 0xDA:
                self.saw_scan = True
                self.mode = "entropy"


@dataclass(frozen=True)
class Frame:
    data: bytes
    sequence: int
    received_at: str
    received_monotonic: float
    width: int
    height: int


class FrameStore:
    def __init__(self, camera_id: str, device: str,
                 clock: Callable[[], float] = time.monotonic,
                 stale_after_ms: int = STALE_AFTER_MS):
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", camera_id):
            raise ValueError("Camera identity must contain 1 to 160 ASCII identity characters.")
        self.camera_id = camera_id
        self.device = device
        self.epoch = uuid.uuid4().hex
        self.clock = clock
        self.stale_after_ms = stale_after_ms
        self.lock = threading.Lock()
        self.latest: Frame | None = None
        self.fault: str | None = None
        self.stderr = deque()
        self.stderr_bytes = 0
        self.discarded_frames = 0

    def publish(self, data: bytes, dimensions: tuple[int, int]):
        if dimensions != (NATIVE_WIDTH, NATIVE_HEIGHT):
            raise ValueError("Camera frame dimensions differ from the requested native 1920 x 1080 mode.")
        if len(data) > MAX_FRAME_BYTES:
            raise ValueError("Camera frame exceeds the bounded native JPEG limit.")
        received_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        received_monotonic = self.clock()
        with self.lock:
            sequence = 1 if self.latest is None else self.latest.sequence + 1
            self.latest = Frame(data, sequence, received_at, received_monotonic, *dimensions)

    def set_fault(self, message: str):
        with self.lock:
            self.fault = message[:1000]

    def append_stderr(self, data: bytes):
        # A bounded byte tail also covers ffmpeg messages without line breaks.
        data = data[-MAX_STDERR_BYTES:]
        with self.lock:
            self.stderr.append(data)
            self.stderr_bytes += len(data)
            while self.stderr_bytes > MAX_STDERR_BYTES:
                excess = self.stderr_bytes - MAX_STDERR_BYTES
                first = self.stderr.popleft()
                if len(first) > excess:
                    self.stderr.appendleft(first[excess:])
                    self.stderr_bytes -= excess
                else:
                    self.stderr_bytes -= len(first)

    def snapshot(self) -> tuple[dict, Frame | None]:
        with self.lock:
            frame = self.latest
            age = None if frame is None else max(0, round((self.clock() - frame.received_monotonic) * 1000))
            state = ("fault" if self.fault else "starting" if frame is None
                     else "stale" if age > self.stale_after_ms else "live")
            metadata = {
                "state": state, "camera_id": self.camera_id,
                "camera_epoch": self.epoch, "device": self.device,
                "format": "mjpeg", "width": NATIVE_WIDTH, "height": NATIVE_HEIGHT,
                "requested_fps": 30, "frame_sequence": None if frame is None else frame.sequence,
                "frame_received_at": None if frame is None else frame.received_at,
                "frame_age_ms": age, "stale_after_ms": self.stale_after_ms,
                "timestamp_basis": "host_receive_time_not_camera_exposure",
                "discarded_frames": self.discarded_frames,
                "error": self.fault,
                "stderr_tail": b"".join(self.stderr).decode("utf-8", errors="replace"),
            }
            return metadata, frame if state == "live" else None


def ffmpeg_arguments(device: str) -> list[str]:
    return ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
            "-f", "v4l2", "-input_format", "mjpeg", "-video_size", "1920x1080",
            "-framerate", "30", "-i", device, "-an", "-c:v", "copy",
            "-f", "image2pipe", "pipe:1"]


def ensure_device_unowned(device: str):
    """Refuse existing owners when fuser is available; never terminate them."""
    if shutil.which("fuser") is None:
        return
    result = subprocess.run(["fuser", "--", device], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=3, check=False)
    if result.returncode == 0:
        owners = " ".join(re.findall(r"\b[0-9]+\b", result.stdout.decode("ascii", errors="ignore")))
        raise RuntimeError(f"The selected camera is already open (PIDs {owners or 'unavailable'}); no owner was stopped.")
    if result.returncode != 1:
        raise RuntimeError("Camera ownership inspection failed; no camera was opened.")


class CameraCapture:
    def __init__(self, store: FrameStore):
        self.store = store
        self.process: subprocess.Popen | None = None
        self.stopping = threading.Event()
        self.threads: list[threading.Thread] = []

    def start(self):
        if self.process is not None or self.threads:
            raise RuntimeError("A camera capture instance can be started only once.")
        try:
            self.process = subprocess.Popen(ffmpeg_arguments(self.store.device), stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        except OSError as error:
            self.store.set_fault(f"Could not start the native camera reader: {error}")
            return
        self.threads = [threading.Thread(target=self._read_frames, daemon=True, name="camera-jpeg-reader"),
                        threading.Thread(target=self._read_stderr, daemon=True, name="camera-stderr-reader")]
        for thread in self.threads:
            thread.start()

    def _read_frames(self):
        assert self.process is not None and self.process.stdout is not None
        parser = JPEGFrames()
        try:
            while not self.stopping.is_set():
                data = self.process.stdout.read(READ_CHUNK_BYTES)
                if not data:
                    break
                for frame, dimensions in parser.feed(data):
                    self.store.publish(frame, dimensions)
                with self.store.lock:
                    self.store.discarded_frames = parser.discarded_frames
            if not self.stopping.is_set():
                code = self.process.wait(timeout=2)
                self.store.set_fault(f"Native camera reader exited (code {code}); manual restart is required.")
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            if not self.stopping.is_set():
                self.store.set_fault(f"Native camera capture failed: {error}")
                self.process.terminate()

    def _read_stderr(self):
        assert self.process is not None and self.process.stderr is not None
        try:
            while True:
                data = self.process.stderr.read(4096)
                if not data:
                    return
                self.store.append_stderr(data)
        except OSError:
            return

    def stop(self):
        self.stopping.set()
        process = self.process
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            for thread in self.threads:
                thread.join(timeout=1)
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()


def handler_for(store: FrameStore):
    class CameraHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *_args):
            pass

        def _send(self, status: int, data: bytes, content_type: str, headers: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            for key, value in (headers or {}).items():
                self.send_header(key, str(value))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                pass
            self.close_connection = True

        def do_GET(self):
            metadata, frame = store.snapshot()
            if self.path == "/status":
                self._send(200, json.dumps(metadata).encode("utf-8"), "application/json")
            elif self.path == "/frame.jpg":
                if frame is None:
                    self._send(503, json.dumps(metadata).encode("utf-8"), "application/json")
                    return
                self._send(200, frame.data, "image/jpeg", {
                    "X-Camera-Id": metadata["camera_id"], "X-Camera-Epoch": metadata["camera_epoch"],
                    "X-Frame-Sequence": frame.sequence, "X-Frame-Received-At": frame.received_at,
                    "X-Frame-Age-Ms": metadata["frame_age_ms"], "X-Frame-Width": frame.width,
                    "X-Frame-Height": frame.height,
                })
            else:
                self._send(404, b'{"error":"Unknown camera preview endpoint."}', "application/json")

    return CameraHandler


class CameraServer(ThreadingHTTPServer):
    """Bound connected request threads, including stalled local consumers."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler):
        self.request_slots = threading.BoundedSemaphore(8)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_slots.release()


class DeviceLock:
    """Advisory single-owner lock shared by copies of this launcher on Linux."""
    def __init__(self, device: str):
        self.device = device
        self.descriptor: int | None = None

    def __enter__(self):
        import fcntl
        digest = hashlib.sha256(os.path.realpath(self.device).encode()).hexdigest()[:20]
        path = f"/tmp/pushpilot-camera-{digest}.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
                raise RuntimeError("The camera lock has an unexpected type or owner.")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            os.close(descriptor)
            raise
        self.descriptor = descriptor
        return self

    def __exit__(self, *_args):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, help="Explicit Linux V4L2 character device, such as /dev/video0.")
    parser.add_argument("--camera-id", required=True, help="Stable reviewed hardware identity, including its serial number.")
    parser.add_argument("--port", type=int, default=8084, help="Loopback HTTP port (default: 8084).")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("The port must be from 1 to 65535.")
    if os.name != "posix":
        parser.error("Native V4L2 capture requires Linux; no hardware was opened.")
    device = str(Path(args.device).resolve())
    if not re.fullmatch(r"/dev/video[0-9]+", device):
        parser.error("The explicit camera device must resolve to /dev/video followed by digits.")
    try:
        if not stat.S_ISCHR(os.stat(device).st_mode):
            parser.error("The selected camera path is not a character device.")
        store = FrameStore(args.camera_id, device)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    stopping = threading.Event()
    previous_handlers = {}
    # Closing the SSH terminal must enter the same cleanup path as Ctrl+C.
    stop_signals = (signal.SIGINT, signal.SIGTERM)
    if hasattr(signal, "SIGHUP"):
        stop_signals += (signal.SIGHUP,)
    for signum in stop_signals:
        previous_handlers[signum] = signal.signal(signum, lambda *_args: stopping.set())
    capture = CameraCapture(store)
    try:
        with DeviceLock(device), CameraServer(("127.0.0.1", args.port), handler_for(store)) as server:
            server.timeout = 0.3
            ensure_device_unowned(device)
            capture.start()
            print(json.dumps({"status": "camera_preview_started", "bind": "127.0.0.1", "port": args.port,
                              "camera_id": store.camera_id, "camera_epoch": store.epoch, "device": device,
                              "timestamp_basis": "host_receive_time_not_camera_exposure"}), flush=True)
            while not stopping.is_set():
                server.handle_request()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "camera_preview_failed", "error": str(error)}), flush=True)
        return 1
    finally:
        capture.stop()
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
