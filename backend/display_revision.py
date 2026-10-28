"""Derive a private display receipt for an explicit unchanged-print route revision.

This deployment helper performs no fitting, persistence, device access or motion.
The returned record still needs ``LiveCamera.restore_reference`` against a fresh
current frame; deriving it never registers a view or resumes a mission by itself.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
import re
from uuid import uuid4

import cv2
import numpy as np

from backend.live_camera import FRESHNESS_LIMIT_MS
from backend.maps import MapDefinition
from backend.scene import MAX_IMAGE_PIXELS, SceneError

_IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _map_identity(definition):
    return {"id": definition.id, "version": definition.version,
            "geometry_hash": definition.geometry_hash}


def derive_route_revision_reference(previous: MapDefinition, current: MapDefinition,
                                    snapshot: dict) -> dict:
    """Rebind an unchanged fixed transform to a reviewed route-only map revision.

    Call only with a private server snapshot captured explicitly for deployment.
    A new map identity invalidates old plans independently. This function cannot
    establish physical print scale, robot coordinates or current motion authority.
    """
    try:
        if not isinstance(previous, MapDefinition) or not isinstance(current, MapDefinition):
            raise ValueError
        before, after = previous.data, current.data
        if (previous.id != current.id or previous.version == current.version
                or previous.geometry_hash == current.geometry_hash
                or not previous.camera_registration_supported or not current.camera_registration_supported
                or any(before[field] != after[field] for field in
                       ("board", "page", "markers", "marker_dictionary", "building_panels"))):
            raise ValueError
        old_source, new_source = before["source"], after["source"]
        source_hash = old_source["sha256"]
        dimensions = old_source["image_size_px"]
        if (not isinstance(source_hash, str) or not _SHA256.fullmatch(source_hash)
                or source_hash != new_source["sha256"]
                or not isinstance(dimensions, list) or len(dimensions) != 2
                or any(type(value) is not int or value < 1 for value in dimensions)
                or dimensions != new_source["image_size_px"]):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise SceneError(409, "Route revision requires the same identified print, dimensions, board, page, marker layout and registration mode.",
                         "DISPLAY_REVISION_MAP") from None

    try:
        if (not isinstance(snapshot, dict) or snapshot.get("schema_version") != "pushpilot.live-camera.v1"
                or snapshot.get("enabled") is not True or snapshot.get("state") != "live"
                or snapshot.get("motion_authority") is not False or snapshot.get("last_error") is not None
                or (snapshot["map_id"], snapshot["map_version"], snapshot["map_hash"]) !=
                   (previous.id, previous.version, previous.geometry_hash)):
            raise ValueError
        frame, registration = snapshot["frame"], snapshot["registration"]
        camera_id = snapshot["camera_id"]
        if (not isinstance(frame, dict) or not isinstance(registration, dict)
                or not isinstance(snapshot["epoch"], str) or not _IDENTIFIER.fullmatch(snapshot["epoch"])
                or not isinstance(camera_id, str) or not 1 <= len(camera_id) <= 160
                or not camera_id.isascii() or any(ord(char) < 32 for char in camera_id)
                or frame.get("source") != "live"
                or type(frame.get("sequence")) is not int or frame["sequence"] < 0
                or not _finite(frame.get("age_ms")) or not 0 <= frame["age_ms"] <= FRESHNESS_LIMIT_MS
                or type(frame.get("width")) is not int or type(frame.get("height")) is not int
                or min(frame["width"], frame["height"]) < 32
                or frame["width"] * frame["height"] > MAX_IMAGE_PIXELS
                or registration.get("status") not in {"locked", "locked_partial"}
                or registration.get("verification") != "visible_markers"):
            raise ValueError
        for identifier in (frame.get("id"), registration.get("id"), registration.get("reference_frame_id")):
            if not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier):
                raise ValueError
        if (not isinstance(frame.get("sha256"), str) or not _SHA256.fullmatch(frame["sha256"])
                or frame.get("image_url") != f"/api/v1/live-camera/frames/{frame['id']}/image"
                or not isinstance(frame.get("received_at"), str)):
            raise ValueError
        received = datetime.fromisoformat(frame["received_at"].replace("Z", "+00:00"))
        if received.tzinfo is None or received.utcoffset() is None:
            raise ValueError
        homography = registration["homography"]
        if (not isinstance(homography, list) or len(homography) != 3
                or any(not isinstance(row, list) or len(row) != 3 for row in homography)
                or any(not _finite(value) for row in homography for value in row)):
            raise ValueError
        matrix = np.array(homography, dtype=np.float64)
        determinant = float(np.linalg.det(matrix))
        if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        raise SceneError(409, "A fresh registered native live snapshot from the exact previous map is required for a route revision.",
                         "DISPLAY_REVISION_SNAPSHOT") from None

    try:
        detection = snapshot["detection"]
        if (not isinstance(detection, dict) or not isinstance(detection.get("markers"), list)
                or not isinstance(detection.get("marker_ids"), list)):
            raise ValueError
        known = {}
        for marker in before["markers"]:
            x, y = marker["center_mm"]
            half = marker["size_mm"] / 2
            known[marker["id"]] = np.array([[x-half, y-half], [x+half, y-half],
                                             [x+half, y+half], [x-half, y+half]], dtype=np.float64)
        centers, errors, seen = [], [], set()
        for marker in detection["markers"]:
            identifier, corners = marker["id"], marker["corners"]
            if (type(identifier) is not int or identifier not in known or identifier in seen
                    or not isinstance(corners, list) or len(corners) != 4
                    or any(not isinstance(point, list) or len(point) != 2 for point in corners)
                    or any(not _finite(value) for point in corners for value in point)):
                raise ValueError
            observed = np.array(corners, dtype=np.float64)
            expected = cv2.perspectiveTransform(known[identifier].reshape(-1, 1, 2), matrix).reshape(4, 2)
            if (not np.isfinite(expected).all()
                    or any(np.any(points < 0) or np.any(points[:, 0] >= frame["width"])
                           or np.any(points[:, 1] >= frame["height"]) for points in (observed, expected))):
                raise ValueError
            distances = np.linalg.norm(observed - expected, axis=1)
            if float(np.sqrt(np.mean(distances**2))) > 3.0 or float(np.max(distances)) > 6.0:
                raise ValueError
            centers.append(np.mean(known[identifier], axis=0))
            errors.extend(distances.tolist())
            seen.add(identifier)
        ids = detection["marker_ids"]
        if (any(type(identifier) is not int for identifier in ids) or len(ids) != len(set(ids))
                or set(ids) != seen):
            raise ValueError
        separation = 0.15 * math.hypot(before["board"]["width_mm"], before["board"]["height_mm"])
        distributed = any(np.linalg.norm(first-second) >= separation
                          for index, first in enumerate(centers) for second in centers[index+1:])
        if (len(seen) < 2 or not distributed or not errors
                or float(np.sqrt(np.mean(np.array(errors)**2))) > 3.0 or max(errors) > 6.0):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError, cv2.error):
        raise SceneError(409, "At least two distributed known native marker observations must agree with the unchanged exact transform.",
                         "DISPLAY_REVISION_MARKERS") from None

    result = deepcopy(snapshot)
    result.update(map_id=current.id, map_version=current.version, map_hash=current.geometry_hash)
    result["registration"]["id"] = uuid4().hex
    result["registration"]["route_revision"] = {
        "schema_version": "pushpilot.display-route-revision.v1",
        "reason": "unchanged_print_route_revision",
        "source_reference_id": registration["id"],
        "previous_map": _map_identity(previous), "current_map": _map_identity(current),
        "source_sha256": source_hash, "source_image_size_px": deepcopy(dimensions),
        "source_frame_id": frame["id"], "source_frame_sequence": frame["sequence"],
        "homography_changed": False, "coordinate_authority": "display_only",
        "motion_authority": False,
    }
    return result
