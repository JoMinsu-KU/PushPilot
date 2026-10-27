"""Ephemeral camera preview, separate from recorded evidence and mission state.

Only a startup-configured numeric loopback HTTP service is contacted. Frames are
kept in a bounded memory cache; this module never persists evidence, calls MUSE,
refits a locked display transform or emits a robot command.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import ipaddress
import math
import re
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

import cv2
import httpx
import numpy as np

from backend.scene import MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, SceneError, _image_header
from backend.live_detector import LiveMarkerDetector

FRESHNESS_LIMIT_MS = 1500
_HEX_ID = re.compile(r"^[a-f0-9]{32}$")


def camera_url(value: str) -> str:
    """Reject DNS, remote hosts, credentials, paths and redirects by construction."""
    try:
        parsed = urlsplit(value)
        host = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
        if (parsed.scheme != "http" or not host.is_loopback or parsed.username is not None
                or parsed.password is not None or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment or port is None or not 1 <= port <= 65535):
            raise ValueError
    except ValueError:
        raise ValueError("Live camera URL must be an HTTP numeric loopback address with an explicit port and no path or credentials.") from None
    return value.rstrip("/")


class LiveCamera:
    """One poller and one immutable latest-frame snapshot for a browser preview."""

    def __init__(self, url: str, map_definition, detect, candidate, *, transport=None,
                 clock=time.monotonic):
        self.url = camera_url(url) if url else ""
        self.map = map_definition
        # These SceneStore helpers inspect their argument and fixed map only.
        # No recorded state, revision, registration or files are touched.
        self._detect = LiveMarkerDetector(map_definition, detect, candidate) if detect else None
        self._candidate = candidate
        self._transport = transport
        self._clock = clock
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._client = None
        self._frames: OrderedDict[str, dict] = OrderedDict()
        self._latest = None
        self._reference = None
        self._changed = False
        self._change_checks = 0
        self._last_error = None
        self._attempted = False

    def start(self):
        if not self.url or self._thread is not None:
            return
        self._client = httpx.Client(timeout=httpx.Timeout(1.5, connect=0.75),
                                    follow_redirects=False, trust_env=False,
                                    transport=self._transport)
        self._thread = threading.Thread(target=self._run, name="pushpilot-camera-preview", daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        if self._client is not None:
            self._client.close()

    def _run(self):
        while not self._stop.is_set():
            started = self._clock()
            self.poll_once()
            self._stop.wait(max(0.0, 0.125 - (self._clock() - started)))

    def poll_once(self):
        """Bounded synchronous poll; injectable transport supports device-free tests."""
        if not self.url:
            return
        if self._client is None:
            self._client = httpx.Client(timeout=httpx.Timeout(1.5, connect=0.75),
                                        follow_redirects=False, trust_env=False,
                                        transport=self._transport)
        with self._lock:
            self._attempted = True
        try:
            request_started = self._clock()
            with self._client.stream("GET", self.url + "/frame.jpg") as response:
                if response.status_code != 200:
                    raise ValueError("Camera frame is unavailable.")
                if response.headers.get("content-type", "").split(";")[0].strip() != "image/jpeg":
                    raise ValueError("Camera service did not return JPEG.")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_IMAGE_BYTES or self._clock() - request_started > 2.0:
                        raise ValueError("Camera frame exceeds the preview limit.")
                self._accept(bytes(body), response.headers, transport_age_ms=(self._clock()-request_started)*1000)
        except (httpx.HTTPError, ValueError, KeyError, OverflowError, SceneError, cv2.error):
            # Never copy a remote response or credential-bearing URL into output.
            with self._lock:
                self._last_error = "Live camera frame unavailable or invalid; the last preview is not fresh evidence."

    def _accept(self, data: bytes, headers, *, transport_age_ms=0.0):
        mime, width, height = _image_header(data)
        if mime != "jpg" or width < 32 or height < 32 or width * height > MAX_IMAGE_PIXELS:
            raise ValueError("Invalid camera image dimensions.")
        epoch = headers["X-Camera-Epoch"]
        camera_id = headers["X-Camera-Id"]
        sequence = int(headers["X-Frame-Sequence"])
        age = float(headers["X-Frame-Age-Ms"]) + transport_age_ms
        received = datetime.fromisoformat(headers["X-Frame-Received-At"].replace("Z", "+00:00"))
        if (not _HEX_ID.fullmatch(epoch) or not 1 <= len(camera_id) <= 160
                or not camera_id.isascii() or any(ord(char) < 32 for char in camera_id)
                or sequence < 0 or not math.isfinite(age) or not 0 <= age <= FRESHNESS_LIMIT_MS
                or received.tzinfo is None or received.utcoffset() is None
                or int(headers["X-Frame-Width"]) != width or int(headers["X-Frame-Height"]) != height):
            raise ValueError("Invalid camera frame identity.")
        with self._lock:
            latest = self._latest
            if latest and (latest["epoch"], latest["camera_id"]) == (epoch, camera_id):
                if sequence <= latest["frame"]["sequence"]:
                    if sequence < latest["frame"]["sequence"]:
                        raise ValueError("Camera sequence moved backwards.")
                    # Re-serving the same frame must not reset its freshness.
                    return
        accepted = self._clock()
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (height, width):
            raise ValueError("Camera JPEG cannot be decoded.")
        detection = self._detect(image)
        candidate = self._candidate(detection, width, height)
        frame_id = uuid4().hex
        item = {"data": data, "accepted": accepted, "upstream_age_ms": age,
                "camera_id": camera_id, "epoch": epoch, "detection": detection,
                "candidate": candidate, "map": self._map_identity(),
                "frame": {"id": frame_id, "image_url": f"/api/v1/live-camera/frames/{frame_id}/image",
                          "source": "live", "width": width, "height": height,
                          "received_at": received.astimezone(timezone.utc).isoformat(), "age_ms": age,
                          "sha256": hashlib.sha256(data).hexdigest(), "sequence": sequence}}
        with self._lock:
            self._frames[frame_id] = item
            while len(self._frames) > 8:
                self._frames.popitem(last=False)
            self._latest = item
            self._last_error = None
            # A confirmed identity/view change remains latched until explicit lock.
            if self._reference:
                self._registration(item, observe=True)

    def _age(self, item):
        return max(0.0, item["upstream_age_ms"] + (self._clock() - item["accepted"]) * 1000)

    def _map_identity(self):
        return self.map.id, self.map.version, self.map.geometry_hash

    def _known_corners(self):
        result = {}
        for marker in self.map.data["markers"]:
            x, y = marker["center_mm"]
            half = marker["size_mm"] / 2
            result[marker["id"]] = np.array([[x-half, y-half], [x+half, y-half],
                                               [x+half, y+half], [x-half, y+half]], dtype=np.float64)
        return result

    def _registration(self, item, *, observe=False):
        empty = {"id": None, "reference_frame_id": None, "homography": None, "residual_px": None}
        if item is None:
            return {**empty, "status": "unregistered", "message": "Connect a live camera to inspect the temporary print."}
        reference = self._reference
        if reference is None:
            candidate = item["candidate"] if item["map"] == self._map_identity() else None
            return {**empty, **(candidate or {}),
                    "status": "candidate" if candidate else "unregistered",
                    "message": "Explicitly lock a fresh view with all four consistent print markers. Display registration only; no robot coordinates."}
        identity = {**empty, "id": reference["id"], "reference_frame_id": reference["frame_id"]}
        frame = item["frame"]
        if (reference["epoch"], reference["camera_id"], reference["width"], reference["height"], reference["map"]) != (
                item["epoch"], item["camera_id"], frame["width"], frame["height"], self._map_identity()):
            self._changed = True
        if self._changed:
            return {**identity, "status": "view_changed", "message": "Camera identity, dimensions, map or verified view changed. Overlay withheld; explicitly register the current view."}
        matrix = np.array(reference["homography"], dtype=np.float64)
        known = self._known_corners()
        errors, shifts, bad_centers, bad = [], [], [], 0
        for marker in item["detection"]["markers"]:
            expected = cv2.perspectiveTransform(known[marker["id"]].reshape(-1, 1, 2), matrix).reshape(4, 2)
            observed = np.array(marker["corners"], dtype=np.float64)
            distance = np.linalg.norm(expected - observed, axis=1)
            errors.extend(distance.tolist())
            if np.sqrt(np.mean(distance**2)) > 3.0 or max(distance) > 6.0:
                bad += 1
                shifts.append(np.mean(observed - expected, axis=0))
                bad_centers.append(np.mean(known[marker["id"]], axis=0))
        coherent = False
        if len(shifts) >= 2:
            average = np.mean(shifts, axis=0)
            # Multiple markers translating coherently or a valid full-print fit
            # positively establish changed view. One doubtful marker does not.
            coherent = item["candidate"] is not None or (
                np.linalg.norm(average) > 3.0 and all(
                    np.dot(shift, average) > 0.5 * np.linalg.norm(shift) * np.linalg.norm(average)
                    for shift in shifts))
        board = self.map.data["board"]
        separation = 0.15 * math.hypot(board["width_mm"], board["height_mm"])
        distributed = any(np.linalg.norm(left-right) >= separation
                          for index, left in enumerate(bad_centers) for right in bad_centers[index+1:])
        if observe:
            self._change_checks = self._change_checks + 1 if bad >= 2 and coherent and distributed else 0
        if self._change_checks >= 3:
            self._changed = True
            return {**identity, "status": "view_changed", "message": "Multiple visible print markers confirm a changed camera view. Overlay withheld; no automatic refit was performed."}
        residual = round(float(np.sqrt(np.mean(np.array(errors)**2))), 4) if errors else None
        if not errors or bad:
            return {**identity, "homography": reference["homography"], "residual_px": residual,
                    "status": "locked_occluded", "message": "Marker evidence is temporarily hidden or insufficient. The fixed display reference is retained; current alignment is unverified and grants no motion authority."}
        partial = len(item["detection"]["markers"]) < len(known)
        return {**identity, "homography": reference["homography"], "residual_px": residual,
                "status": "locked_partial" if partial else "locked",
                "message": "Visible markers match the fixed display reference. No refit, camera-to-BASE registration or physical motion authority."}

    def snapshot(self):
        with self._lock:
            item = self._latest
            frame = deepcopy(item["frame"]) if item else None
            if frame:
                frame["age_ms"] = round(self._age(item), 1)
            state = ("live" if frame and frame["age_ms"] <= FRESHNESS_LIMIT_MS else
                     "stale" if frame else "unavailable" if self._attempted or not self.url else "connecting")
            return deepcopy({"schema_version": "pushpilot.live-camera.v1", "enabled": bool(self.url),
                             "state": state, "camera_id": item["camera_id"] if item else None,
                             "epoch": item["epoch"] if item else None, "frame": frame,
                             "map_id": self.map.id, "map_version": self.map.version, "map_hash": self.map.geometry_hash,
                             "detection": item["detection"] if item else {"marker_ids": [], "markers": []},
                             "registration": self._registration(item), "motion_authority": False,
                             "freshness_limit_ms": FRESHNESS_LIMIT_MS, "last_error": self._last_error})

    def image(self, frame_id: str) -> bytes:
        with self._lock:
            if not _HEX_ID.fullmatch(frame_id) or frame_id not in self._frames:
                raise SceneError(404, "Live frame expired from the preview cache.", "LIVE_FRAME_EXPIRED")
            return self._frames[frame_id]["data"]

    def register(self, epoch: str, frame_id: str):
        with self._lock:
            item = self._frames.get(frame_id)
            current = self._latest
            if (item is None or current is None or epoch != item["epoch"] or epoch != current["epoch"]
                    or self._age(item) > FRESHNESS_LIMIT_MS or self._age(current) > FRESHNESS_LIMIT_MS
                    or (item["camera_id"], item["frame"]["width"], item["frame"]["height"], item["map"]) !=
                       (current["camera_id"], current["frame"]["width"], current["frame"]["height"], self._map_identity())
                    or current["map"] != self._map_identity()):
                raise SceneError(409, "Select a fresh frame from the current camera epoch.", "LIVE_FRAME_CHANGED")
            if item["candidate"] is None or current["candidate"] is None:
                raise SceneError(409, "All four consistent current markers are required to lock the live display.", "LIVE_REGISTRATION_MARKERS")
            # A cached click is accepted only while its transform still matches
            # the latest frame. Neither identity nor a changed view is guessed.
            known = self._known_corners()
            matrix = np.array(item["candidate"]["homography"], dtype=np.float64)
            distances = []
            for marker in current["detection"]["markers"]:
                projected = cv2.perspectiveTransform(known[marker["id"]].reshape(-1, 1, 2), matrix).reshape(4, 2)
                distances.extend(np.linalg.norm(projected - np.array(marker["corners"]), axis=1).tolist())
            if np.sqrt(np.mean(np.array(distances)**2)) > 3.0 or max(distances) > 6.0:
                raise SceneError(409, "The camera view changed after the selected frame. Select its current view.", "LIVE_FRAME_CHANGED")
            frame = item["frame"]
            self._reference = {"id": uuid4().hex, "frame_id": frame_id, "epoch": epoch,
                               "camera_id": item["camera_id"], "width": frame["width"], "height": frame["height"],
                               "map": self._map_identity(), "homography": deepcopy(item["candidate"]["homography"])}
            self._changed = False
            self._change_checks = 0
            return self.snapshot()
