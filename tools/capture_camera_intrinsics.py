"""Bounded camera-only checkerboard acquisition; never sends robot commands.

Run on GX10 with the existing camera/web/receiver kept alive. A separately
captured optics monitor must prove unchanged manual focus and zoom. Outputs
remain private; a successful pixel model is not robot or face calibration.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
from uuid import uuid4

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.robot_control.camera_intrinsics import (
    CameraIntrinsicsError, CameraIntrinsicsIdentity, CheckerboardObservation,
    CheckerboardPattern, calibrate_camera_intrinsics,
)


def _save(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def run(output: Path, optics_path: Path, target_path: Path, seconds: int, count: int) -> dict:
    if not 60 <= seconds <= 300 or not 16 <= count <= 24:
        raise ValueError("Use 60-300 seconds and 16-24 accepted views.")
    os.umask(0o077)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    token = (Path.home() / "pushpilot-robot-control/shared/control.token").read_text().strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def fetch(url: str, authenticated: bool = False) -> bytes:
        headers = {"X-PushPilot-Control-Token": token} if authenticated else {}
        with opener.open(urllib.request.Request(url, headers=headers), timeout=5) as response:
            return response.read()

    def status() -> dict:
        value = json.loads(fetch("http://127.0.0.1:8897/v1/status", True))
        if value["armed"] or not value["hold"] or value["active_commands"]:
            raise RuntimeError("ROBOT_NOT_HELD_AND_DISARMED")
        if not value["receiver"]["connected"] or not value["receiver"]["idle"]:
            raise RuntimeError("RECEIVER_NOT_CONNECTED_IDLE")
        return value

    def optics() -> dict:
        value = json.loads(optics_path.read_text())
        timestamp = dt.datetime.fromisoformat(value["checked_at_utc"])
        age = (dt.datetime.now(dt.timezone.utc) - timestamp).total_seconds()
        if not 0 <= age <= 5 or not value["valid"]:
            raise RuntimeError("FRESH_VERIFIED_OPTICS_MONITOR_REQUIRED")
        if value["controls"]["focus_automatic_continuous"] != 0:
            raise RuntimeError("AUTOFOCUS_IS_NOT_A_FIXED_INTRINSIC_MODEL")
        return value

    before = status()
    initial_optics = optics()
    camera = json.loads(fetch("http://127.0.0.1:8080/api/v1/live-camera"))
    if camera["state"] != "live" or camera["frame"]["age_ms"] > 500:
        raise RuntimeError("FRESH_NATIVE_CAMERA_REQUIRED")
    controls = initial_optics["controls"]
    settings_payload = {"camera_id": camera["camera_id"], "epoch": camera["epoch"],
                        "size": [1920, 1080], "format": "native_mjpeg",
                        "focus_automatic_continuous": 0, "focus_absolute": controls["focus_absolute"],
                        "zoom_absolute": controls["zoom_absolute"],
                        "pan_absolute": controls["pan_absolute"], "tilt_absolute": controls["tilt_absolute"]}
    settings_hash = hashlib.sha256(json.dumps(settings_payload, sort_keys=True).encode()).hexdigest()
    identity = CameraIntrinsicsIdentity(camera["camera_id"], camera["epoch"], settings_hash)
    pattern = CheckerboardPattern("pushpilot-tablet-checkerboard-10x7-v1",
                                 hashlib.sha256(target_path.read_bytes()).hexdigest(), 9, 6)
    _save(output / "before.status.private.json", before)
    _save(output / "initial-optics.private.json", initial_optics)
    _save(output / "settings.private.json", settings_payload)
    observations = []
    last_sequence = -1
    previous_corners = None
    last_accepted_time = float("-inf")
    deadline = time.monotonic() + seconds
    polled = 0
    terminal_reason = "CAPTURE_BUDGET_EXHAUSTED"
    try:
        while time.monotonic() < deadline and len(observations) < count:
            current_optics = optics()
            if current_optics["controls"] != controls:
                raise RuntimeError("CAMERA_OPTICS_CHANGED")
            current = status()
            for key in ("session_id", "seq", "profile_id", "actual_pose"):
                if current["receiver"][key] != before["receiver"][key]:
                    raise RuntimeError("ROBOT_BASELINE_CHANGED")
            camera = json.loads(fetch("http://127.0.0.1:8080/api/v1/live-camera"))
            frame = camera["frame"]
            if camera["epoch"] != identity.camera_epoch or camera["camera_id"] != identity.camera_id:
                raise RuntimeError("CAMERA_IDENTITY_CHANGED")
            if camera["state"] != "live" or frame["age_ms"] > 500:
                raise RuntimeError("CAMERA_OBSERVATION_UNAVAILABLE")
            if frame["sequence"] <= last_sequence:
                time.sleep(.15)
                continue
            last_sequence = frame["sequence"]
            raw = fetch("http://127.0.0.1:8080" + frame["image_url"])
            digest = hashlib.sha256(raw).hexdigest()
            if digest != frame["sha256"]:
                raise RuntimeError("ORIGINAL_FRAME_HASH_MISMATCH")
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if image is None or image.shape != (1080, 1920):
                raise RuntimeError("NATIVE_RESOLUTION_CHANGED")
            polled += 1
            found, corners = cv2.findChessboardCornersSB(image, (9, 6), flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
            if not found:
                previous_corners = None
                time.sleep(.15)
                continue
            points = corners.reshape(-1, 2)
            area = cv2.contourArea(cv2.convexHull(points.astype(np.float32)))
            stable = previous_corners is not None and np.sqrt(np.mean(np.sum((points-previous_corners)**2, axis=1))) <= 5
            previous_corners = points
            if not stable or area < .01 * 1920 * 1080 or time.monotonic() - last_accepted_time < .8:
                continue
            if observations:
                distances = [np.sqrt(np.mean(np.sum((points-np.asarray(o.image_points_px))**2, axis=1))) for o in observations]
                if min(distances) < 25:
                    continue
            observation_id = f"view-{len(observations):02d}"
            observation = CheckerboardObservation(observation_id, digest, identity, pattern.pattern_id,
                                                   pattern.pattern_sha256, points.tolist())
            observations.append(observation)
            (output / (observation_id + ".native.jpg")).write_bytes(raw)
            _save(output / (observation_id + ".camera.private.json"), camera)
            _save(output / (observation_id + ".corners.private.json"), asdict(observation))
            last_accepted_time = time.monotonic()
            print(json.dumps({"camera_only": True, "accepted_views": len(observations), "target_views": count}), flush=True)
        terminal_reason = "REQUESTED_VIEWS_CAPTURED" if len(observations) == count else terminal_reason
        after = status()
        final_optics = optics()
        if final_optics["controls"] != controls:
            raise RuntimeError("CAMERA_OPTICS_CHANGED")
        for key in ("session_id", "seq", "profile_id", "actual_pose"):
            if after["receiver"][key] != before["receiver"][key]:
                raise RuntimeError("ROBOT_BASELINE_CHANGED")
        _save(output / "after.status.private.json", after)
        _save(output / "final-optics.private.json", final_optics)
    except Exception as error:
        terminal_reason = str(error) if isinstance(error, RuntimeError) else type(error).__name__
    ids = [o.observation_id for o in observations]
    # This split is declared by capture index, before any model fitting.
    checks = [name for i, name in enumerate(ids) if i % 4 == 3]
    training = [name for name in ids if name not in checks]
    summary = {"schema": "pushpilot.private-camera-intrinsics-capture.v1", "session_id": uuid4().hex,
               "terminal_reason": terminal_reason, "polled_frames": polled, "accepted_views": len(observations),
               "identity": asdict(identity), "pattern": asdict(pattern), "training_ids": training, "heldout_ids": checks,
               "motion_issued": False, "robot_commands_created": False, "camera_restarted": False,
               "physical_qualified": False, "model_attempted": False, "accepted_image_model": False}
    if terminal_reason == "REQUESTED_VIEWS_CAPTURED":
        try:
            model = calibrate_camera_intrinsics(observations, training_ids=training, heldout_ids=checks,
                                                identity=identity, pattern=pattern)
            _save(output / "intrinsics-candidate.private.json", model)
            summary.update(model_attempted=True, accepted_image_model=model["accepted_image_model"],
                           model_failure_reasons=model["failure_reasons"])
        except CameraIntrinsicsError as error:
            summary.update(model_attempted=True, model_failure_reasons=[str(error)])
    _save(output / "capture.private.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--optics", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=ROOT / "tools/camera_calibration_target.html")
    parser.add_argument("--seconds", type=int, default=240)
    parser.add_argument("--views", type=int, default=20)
    arguments = parser.parse_args()
    result = run(arguments.output, arguments.optics, arguments.target, arguments.seconds, arguments.views)
    print(json.dumps(result, allow_nan=False), flush=True)
    raise SystemExit(0 if result["accepted_image_model"] else 2)
