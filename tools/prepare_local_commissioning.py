"""Prepare a newly reviewed local BASE-only commissioning profile, offline.

This tool neither measures nor qualifies clearance. A supplied actual on-site
review is required separately from the explicit invocation flag. No map,
camera, drawing calibration, push or car-turn qualification is inferred.
No socket, mailbox, controller setting or command is written by this tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.robot_control.gates import GuardError, local_profile_binding, validate_local_profile
from backend.robot_control.legacy import DEFAULT_RUNTIME, PrewireRejected, load_runtime
from backend.robot_control.models import LocalBaseInstallation
from tools.prepare_robot_installation import _read_json, _vector


def build_profile(installation: dict, robot_state: dict, *, on_site_review: bool = False) -> dict:
    """Build data from an actual reviewed local envelope and fresh readback.

    The review is a physical input, never an output of schema validation or
    small numerical limits. This helper has no hardware or file access.
    """
    if on_site_review is not True:
        raise ValueError("Explicit --on-site-review is required; software validation cannot qualify a physical volume.")
    local = LocalBaseInstallation.model_validate(installation).model_dump(mode="json")
    if local["qualified"] is not True or local["on_site_review"] is not True:
        raise ValueError("Actual measured local BASE envelope is not qualified by an explicit on-site review.")
    if type(robot_state) is not dict or set(robot_state) != {"actual_pose", "actual_joint"}:
        raise ValueError("Use only fresh actual_pose and actual_joint readback; no profile or historical state import.")
    pose = _vector(robot_state["actual_pose"], 6, "actual_pose")
    joints = _vector(robot_state["actual_joint"], 6, "actual_joint")
    profile = {
        "schema": "pushpilot.hcr1-pose-profile.experimental-v1",
        "scope": "local_base_commissioning", "coordinate_frame": "robot_base_mm", "pose_type": "tcp",
        "allow_motion": True, "site_verified": True,
        "tcp_id": local["tcp_id"], "payload_kg": local["payload_kg"],
        "review_reference": local["review_reference"],
        "expected_start_tcp_mm_deg": pose, "expected_start_joint_deg": joints,
        "tcp_bounds_base_mm": local["workspace_min_mm"] + local["workspace_max_mm"],
        "tcp_clearance_margin_mm": local["tcp_clearance_margin_mm"],
        "inflated_keepout_boxes_base_mm": local["inflated_keepout_boxes_base_mm"],
        "translation_speed_mm_s": local["max_speed_mm_s"],
        "translation_accel_mm_s2": local["max_accel_mm_s2"],
        "max_translation_mm": local["max_step_mm"],
        "orientations": [{"id": "measured_current", "rxyz_deg": local["fixed_orientation_deg"]}],
        "rotation_anchors": [], "rotation_edges": [],
        "rotation_runtime": {
            "verified": False, "primitive": "moveLinear_tcp", "controller_version": "unqualified",
            "argument_semantics": "not_commissioned", "speed_argument": 0, "accel_argument": 0,
            "completion_timeout_s": 0,
            "review_reference": "Local BASE review permits no wrist rotation, vertical travel, pushing or board route.",
        },
        "installation_binding": local_profile_binding(local),
    }
    validate_local_profile(local, {"physical_execution": True, "profile": profile, "actual_pose": pose})
    return profile


def prepare(installation_path: Path, state_path: Path, output: Path, *, runtime_root: Path = DEFAULT_RUNTIME,
            on_site_review: bool = False) -> dict:
    if on_site_review is not True:
        raise ValueError("Explicit --on-site-review is required before reading any physical profile inputs.")
    profile = build_profile(_read_json(installation_path), _read_json(state_path), on_site_review=True)
    modules = load_runtime(runtime_root)
    # The unmodified inherited policy independently validates every required
    # wire field, including the complete disabled rotation-runtime object.
    modules["policy"].valid(profile, True)
    compact = json.dumps(profile, ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(compact) > modules["policy"].MAX_PROFILE_BYTES:
        raise ValueError("The local profile exceeds the installed receiver profile limit.")
    encoded = json.dumps(profile, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    output = Path(output).absolute()
    if output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        raise ValueError("Private local profile output through symbolic links is unsupported.")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "output": str(output), "sha256": hashlib.sha256(encoded).hexdigest(),
        "installation_id": profile["installation_binding"]["installation_id"],
        "scope": "local_base_commissioning", "site_review_source": "explicit_measured_on_site_review",
        "offline_policy_validated": True, "board_registration_qualified": False,
        "vehicle_control_qualified": False, "rotation_qualified": False, "car_turn_qualified": False,
        "network_contacted": False, "motion_issued": False, "receiver_started": False,
        "next_step": "Review this local profile and current physical facts; persistent connection and a separate bound arm remain required.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True, help="Actual measured LocalBaseInstallation JSON; no drawing or camera identities.")
    parser.add_argument("--robot-state", type=Path, required=True, help="Fresh actual_pose[6] and actual_joint[6] JSON only.")
    parser.add_argument("--output", type=Path, required=True, help="New private profile file; existing files are never overwritten.")
    parser.add_argument("--receiver-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--on-site-review", action="store_true", help="Explicitly record an actual completed local tool/arm/cable/obstacle clearance review; not automatic qualification.")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.installation, args.robot_state, args.output,
                         runtime_root=args.receiver_root, on_site_review=args.on_site_review)
    except (OSError, ValueError, TypeError, GuardError, PrewireRejected) as error:
        parser.exit(1, f"Local commissioning profile preparation failed: {error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
