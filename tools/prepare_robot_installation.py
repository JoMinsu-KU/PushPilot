"""Build a fresh private translation-only profile from operator measurements.

This offline tool neither measures nor qualifies an installation. It imports no
historical profile, starts no service and publishes no command. The explicit
site-review flag records operator review; it is never inferred from validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.robot_control.legacy import DEFAULT_RUNTIME, PrewireRejected, load_runtime
from backend.robot_control.models import Installation


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and abs(value) <= 10000


def _vector(value, size, label):
    if type(value) is not list or len(value) != size or not all(_number(item) for item in value):
        raise ValueError(f"{label} must contain {size} finite numbers, not booleans.")
    return value[:]


def build_profile(installation: dict, robot_state: dict, *, site_reviewed: bool,
                  payload_kg: float, clearance_mm: float = 0, keepout_boxes=None) -> dict:
    """Create data only; the caller must validate against the hash-reviewed policy."""
    if site_reviewed is not True:
        raise ValueError("Explicit --site-reviewed is required; geometry validation cannot qualify a site.")
    if type(installation) is not dict:
        raise ValueError("Installation must be an operator-created measured JSON object.")
    if installation.get("qualified") is not True:
        raise ValueError("The operator-created measured installation is not qualified. No profile was generated.")
    # Validate before numeric normalization so booleans cannot become positions.
    for key in ("workspace_min_mm", "workspace_max_mm"):
        _vector(installation.get(key), 3, key)
    for key in ("min_tcp_z_mm", "raised_tcp_z_mm", "max_step_mm", "max_speed_mm_s",
                "max_accel_mm_s2", "observation_max_age_seconds"):
        if key in installation and not _number(installation[key]):
            raise ValueError(f"Installation {key} must be a finite number.")
    installation = Installation.model_validate(installation).model_dump(mode="json")
    if type(robot_state) is not dict or set(robot_state) != {"actual_pose", "actual_joint"}:
        raise ValueError("Robot state must contain only current actual_pose and actual_joint measurements; no profile import.")
    pose = _vector(robot_state["actual_pose"], 6, "actual_pose")
    joints = _vector(robot_state["actual_joint"], 6, "actual_joint")
    if any(not -180 <= angle <= 180 for angle in pose[3:]):
        raise ValueError("Use the measured TCP Euler representation within -180..180; this tool never normalizes it.")
    if not _number(payload_kg) or payload_kg < 0:
        raise ValueError("An explicit finite nonnegative payload_kg is required; no POC payload is inherited.")
    if not _number(clearance_mm) or clearance_mm < 0:
        raise ValueError("TCP clearance margin must be finite and nonnegative.")
    boxes = [] if keepout_boxes is None else keepout_boxes
    if type(boxes) is not list or len(boxes) > 16:
        raise ValueError("Use an explicit list of at most 16 reviewed inflated BASE keepout boxes.")
    boxes = [_vector(box, 6, "Keepout box") for box in boxes]
    if any(any(box[i] > box[i + 3] for i in range(3)) for box in boxes):
        raise ValueError("Keepout box minimums cannot exceed maximums.")
    lower = installation["workspace_min_mm"][:]
    lower[2] = max(lower[2], installation["min_tcp_z_mm"])
    upper = installation["workspace_max_mm"][:]
    if not all(lower[i] + clearance_mm <= pose[i] <= upper[i] - clearance_mm for i in range(3)):
        raise ValueError("The current measured TCP lies outside the reviewed working workspace and margin.")
    if not all(lower[i] + 2 * clearance_mm < upper[i] for i in range(3)):
        raise ValueError("The reviewed clearance margin leaves no bounded workspace.")
    binding = {key: installation[key] for key in (
        "installation_id", "map_id", "map_hash", "calibration_id", "tcp_id", "tool_id",
        "camera_epoch", "registration_id", "review_reference", "min_tcp_z_mm", "raised_tcp_z_mm")}
    binding.update(source="operator_measurements", site_review_explicit=True,
                   rotation_qualified=False, car_turn_qualified=False)
    return {
        "schema": "pushpilot.hcr1-pose-profile.experimental-v1",
        "coordinate_frame": "robot_base_mm", "pose_type": "tcp",
        "allow_motion": True, "site_verified": True,
        "tcp_id": installation["tcp_id"], "payload_kg": payload_kg,
        "review_reference": (f"Operator site review for installation {installation['installation_id']}; "
                             f"calibration {installation['calibration_id']}."),
        "expected_start_tcp_mm_deg": pose, "expected_start_joint_deg": joints,
        "tcp_bounds_base_mm": lower + upper, "tcp_clearance_margin_mm": clearance_mm,
        "inflated_keepout_boxes_base_mm": boxes,
        "translation_speed_mm_s": installation["max_speed_mm_s"],
        "translation_accel_mm_s2": installation["max_accel_mm_s2"],
        "max_translation_mm": installation["max_step_mm"],
        "orientations": [{"id": "measured_current", "rxyz_deg": pose[3:]}],
        "rotation_anchors": [], "rotation_edges": [],
        "rotation_runtime": {
            "verified": False, "primitive": "moveLinear_tcp",
            "controller_version": "unqualified", "argument_semantics": "not_commissioned",
            "speed_argument": 0, "accel_argument": 0, "completion_timeout_s": 0,
            "review_reference": "Rotation is disabled; no vehicle-turn or wrist-sweep qualification is inferred.",
        },
        "installation_binding": binding,
    }


def _read_json(path: Path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError("Input must be a bounded regular JSON file.")

    def object_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate JSON key: " + key)
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError("Nonfinite JSON number: " + value)

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=object_pairs,
                      parse_constant=invalid_constant)


def prepare(installation_path: Path, state_path: Path, output: Path, *, runtime_root: Path = DEFAULT_RUNTIME,
            site_reviewed: bool = False, payload_kg: float, clearance_mm: float = 0,
            keepouts_path: Path | None = None) -> dict:
    if not site_reviewed:
        raise ValueError("Explicit --site-reviewed is required before generating any physical profile.")
    profile = build_profile(_read_json(installation_path), _read_json(state_path),
                            site_reviewed=site_reviewed, payload_kg=payload_kg, clearance_mm=clearance_mm,
                            keepout_boxes=_read_json(keepouts_path) if keepouts_path else None)
    modules = load_runtime(runtime_root)
    modules["policy"].valid(profile, True)
    encoded = json.dumps(profile, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    if len(json.dumps(profile, ensure_ascii=True, allow_nan=False).encode("ascii")) > modules["policy"].MAX_PROFILE_BYTES:
        raise ValueError("Generated profile exceeds the installed receiver's bounded profile size.")
    output = Path(output).absolute()
    if output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        raise ValueError("Private profile output through symbolic links is unsupported.")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
    except BaseException:
        # A partial file remains evidence of interrupted preparation. Never
        # replace it or silently turn it into a current operating profile.
        raise
    return {"output": str(output), "sha256": hashlib.sha256(encoded).hexdigest(),
            "installation_id": profile["installation_binding"]["installation_id"],
            "offline_policy_validated": True, "site_review_source": "operator",
            "rotation_qualified": False, "car_turn_qualified": False,
            "network_contacted": False, "motion_issued": False, "receiver_started": False,
            "next_step": "Review the fresh measurements on site; deliberately start the separate receiver host only when ready."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True, help="Operator-created measured Installation JSON.")
    parser.add_argument("--robot-state", type=Path, required=True, help="JSON containing current actual_pose[6] and actual_joint[6] only.")
    parser.add_argument("--output", type=Path, required=True, help="New private profile file; existing files are never overwritten.")
    parser.add_argument("--receiver-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--payload-kg", type=float, required=True, help="Current reviewed payload; no historical POC default.")
    parser.add_argument("--tcp-clearance-margin-mm", type=float, default=0,
                        help="Operator-reviewed TCP boundary margin; default zero adds no clearance claim.")
    parser.add_argument("--keepouts", type=Path, help="Optional JSON list of reviewed inflated BASE boxes; site review covers the remaining workspace.")
    parser.add_argument("--site-reviewed", action="store_true", help="Record explicit on-site review; never qualifies measurements automatically.")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.installation, args.robot_state, args.output, runtime_root=args.receiver_root,
                         site_reviewed=args.site_reviewed, payload_kg=args.payload_kg,
                         clearance_mm=args.tcp_clearance_margin_mm, keepouts_path=args.keepouts)
    except (OSError, ValueError, TypeError, PrewireRejected) as error:
        parser.exit(1, f"Installation profile preparation failed: {error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
