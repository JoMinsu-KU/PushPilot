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
        if "resumed_from" in reference:
            identity.update(resumed_from=reference["resumed_from"], resume_frame_id=reference["resume_frame_id"])
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

    def capture(self, *, after_sequence: int | None = None, not_before: float | None = None) -> dict:
        """Explicitly pin one native frame for a separate intelligence operation.

        Preview polling still persists nothing. The calling service owns any
        durable evidence. A locked drawing view is not a robot calibration.
        """
        with self._lock:
            if not self.map.camera_registration_supported:
                raise SceneError(409, "This spatial-only map has no declared camera registration. Use its model preview; do not reuse another map's live image.", "LIVE_CAPTURE_MAP_MODE")
            item = self._latest
            if not self.url or item is None or self._age(item) > FRESHNESS_LIMIT_MS or self._last_error:
                raise SceneError(409, "A fresh native camera frame is required.", "LIVE_CAPTURE_UNAVAILABLE")
            registration = self._registration(item)
            if registration["status"] not in {"locked", "locked_partial"}:
                raise SceneError(409, "A verified locked drawing view is required; no automatic refit was performed.", "LIVE_CAPTURE_REGISTRATION")
            if ((after_sequence is not None and item["frame"]["sequence"] <= after_sequence)
                    or (not_before is not None and item["accepted"] - item["upstream_age_ms"] / 1000 <= not_before)):
                raise SceneError(409, "Wait for a new camera frame after this operation.", "LIVE_CAPTURE_NOT_NEW")
            metadata = {**deepcopy(item["frame"]), "age_at_selection_ms": round(self._age(item), 1),
                        "camera_id": item["camera_id"], "epoch": item["epoch"],
                        "map_id": self.map.id, "map_version": self.map.version, "map_hash": self.map.geometry_hash,
                        "timestamp_source": "camera_host_receive", "sensor_exposure_time_known": False,
                        "registration": deepcopy(registration), "motion_authority": False}
            return {"data": item["data"], "metadata": metadata}

    def check_binding(self, metadata: dict) -> None:
        """Check current identity/view, without demanding the old frame stay fresh."""
        current = self.capture()["metadata"]
        keys = ("epoch", "camera_id", "width", "height", "map_id", "map_version", "map_hash")
        if (any(current[key] != metadata[key] for key in keys)
                or current["registration"]["id"] != metadata["registration"]["id"]):
            raise SceneError(409, "The camera or registered map changed while MUSE was working.", "LIVE_CAPTURE_CHANGED")

    def register(self, epoch: str, frame_id: str):
        with self._lock:
            if not self.map.camera_registration_supported:
                raise SceneError(409, "Camera registration is unavailable for this spatial-only map.", "LIVE_REGISTRATION_MAP_MODE")
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

    def restore_reference(self, receipt: dict):
        """Explicitly resume a server-held fixed display reference after restart.

        This does not fit a transform, recreate hidden markers or restore motion
        authority. The caller must supply a prior private server snapshot rather
        than accepting an arbitrary homography from a public request body.
        """
        with self._lock:
            if not self.map.camera_registration_supported:
                raise SceneError(409, "This map has no declared camera registration.", "LIVE_REFERENCE_MAP_MODE")
            if self._changed:
                raise SceneError(409, "A confirmed view change requires a new four-marker lock; its old reference cannot be resumed.", "LIVE_REFERENCE_CHANGED")
            item = self._latest
            if (not self.url or item is None or self._frames.get(item["frame"]["id"]) is not item
                    or self._age(item) > FRESHNESS_LIMIT_MS or self._last_error
                    or item["map"] != self._map_identity()):
                raise SceneError(409, "A fresh current native camera frame is required to resume a fixed reference.", "LIVE_REFERENCE_UNAVAILABLE")
            try:
                if (not isinstance(receipt, dict) or receipt.get("schema_version") != "pushpilot.live-camera.v1"
                        or receipt.get("enabled") is not True or receipt.get("motion_authority") is not False
                        or receipt.get("state") not in {"live", "stale"}):
                    raise ValueError
                registration, old_frame = receipt["registration"], receipt["frame"]
                if (not isinstance(registration, dict) or not isinstance(old_frame, dict)
                        or registration.get("status") not in {"locked", "locked_partial", "locked_occluded"}
                        or not isinstance(registration.get("id"), str) or not _HEX_ID.fullmatch(registration["id"])
                        or not isinstance(registration.get("reference_frame_id"), str) or not _HEX_ID.fullmatch(registration["reference_frame_id"])
                        or not isinstance(old_frame.get("id"), str) or not _HEX_ID.fullmatch(old_frame["id"])
                        or old_frame.get("source") != "live" or type(old_frame.get("sequence")) is not int
                        or old_frame["sequence"] < 0):
                    raise ValueError
                previous_identity = (receipt["epoch"], receipt["camera_id"], old_frame["width"], old_frame["height"],
                                     receipt["map_id"], receipt["map_version"], receipt["map_hash"])
                current_identity = (item["epoch"], item["camera_id"], item["frame"]["width"], item["frame"]["height"], *self._map_identity())
                if (previous_identity != current_identity or type(old_frame["width"]) is not int
                        or type(old_frame["height"]) is not int or item["frame"]["sequence"] < old_frame["sequence"]):
                    raise ValueError
                homography = registration["homography"]
                if (not isinstance(homography, list) or len(homography) != 3
                        or any(not isinstance(row, list) or len(row) != 3 for row in homography)
                        or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                               for row in homography for value in row)):
                    raise ValueError
                matrix = np.array(homography, dtype=np.float64)
                determinant = float(np.linalg.det(matrix))
                if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
                    raise ValueError
                existing = self._reference
                if existing and (existing.get("resumed_from") != registration["id"]
                                 or existing["homography"] != homography
                                 or (existing["epoch"], existing["camera_id"], existing["width"], existing["height"], existing["map"]) !=
                                    (item["epoch"], item["camera_id"], item["frame"]["width"], item["frame"]["height"], self._map_identity())):
                    raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError):
                raise SceneError(409, "The prior server reference does not match this camera epoch, dimensions, map or valid fixed transform.", "LIVE_REFERENCE_IDENTITY") from None
            known = self._known_corners()
            centers, errors, seen = [], [], set()
            try:
                for marker in item["detection"]["markers"]:
                    identifier = marker["id"]
                    if identifier not in known or identifier in seen:
                        raise ValueError
                    observed = np.array(marker["corners"], dtype=np.float64)
                    if observed.shape != (4, 2) or not np.isfinite(observed).all():
                        raise ValueError
                    expected = cv2.perspectiveTransform(known[identifier].reshape(-1, 1, 2), matrix).reshape(4, 2)
                    if not np.isfinite(expected).all():
                        raise ValueError
                    distances = np.linalg.norm(observed - expected, axis=1)
                    if float(np.sqrt(np.mean(distances**2))) > 3.0 or float(np.max(distances)) > 6.0:
                        raise ValueError
                    centers.append(np.mean(known[identifier], axis=0))
                    errors.extend(distances.tolist())
                    seen.add(identifier)
                board = self.map.data["board"]
                separation = 0.15 * math.hypot(board["width_mm"], board["height_mm"])
                distributed = any(np.linalg.norm(first-second) >= separation
                                  for index, first in enumerate(centers) for second in centers[index+1:])
                if len(seen) < 2 or not distributed or not errors:
                    raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError, cv2.error):
                raise SceneError(409, "At least two distributed known visible markers must agree with the exact prior fixed reference.", "LIVE_REFERENCE_MARKERS") from None
            if self._reference is None:
                frame = item["frame"]
                self._reference = {"id": uuid4().hex, "frame_id": registration["reference_frame_id"],
                                   "epoch": item["epoch"], "camera_id": item["camera_id"],
                                   "width": frame["width"], "height": frame["height"], "map": self._map_identity(),
                                   "homography": deepcopy(homography), "resumed_from": registration["id"],
                                   "resume_frame_id": frame["id"]}
                self._change_checks = 0
            return self.snapshot()
