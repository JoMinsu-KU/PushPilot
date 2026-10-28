"""Prepare an explicitly reviewed experimental contact profile offline.

This neither performs the review nor applies a profile. Calibration and the
existing-pad contact-offset work precede physical trial activation.
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

from backend.robot_control.gates import (
    GuardError, local_contact_profile_binding, validate_contact_profile,
)
from backend.robot_control.legacy import DEFAULT_RUNTIME, PrewireRejected, load_runtime
from backend.robot_control.models import LocalBaseInstallation, LocalContactInstallation
from tools.prepare_local_commissioning import build_profile as build_teaching_profile
from tools.prepare_robot_installation import _read_json


def build_profile(installation, robot_state, *, on_site_review=False):
    if on_site_review is not True:
        raise ValueError("Explicit actual --on-site-review is required; no contact authority is inferred.")
    local = LocalContactInstallation.model_validate(installation).model_dump(mode="json")
    if not (local["qualified"] and local["on_site_review"] and local["contact_trials_authorized"]):
        raise ValueError("An actual current review explicitly authorizing experimental contact is required.")
    # Reuse the offline numerical/profile-format builder, then explicitly bind
    # the separate contact scope. No teaching profile is saved or activated.
    numerical = {**{key: local[key] for key in LocalBaseInstallation.model_fields},
                 "scope": "local_base_commissioning"}
    profile = build_teaching_profile(numerical, robot_state, on_site_review=True)
    profile.update(scope="local_contact_commissioning", installation_binding=local_contact_profile_binding(local))
    profile["rotation_runtime"] = {**profile["rotation_runtime"], "review_reference":
        "Local contact review permits no wrist rotation, vertical travel or board route; experimental contact translation is separately bounded."}
    validate_contact_profile(local, {"physical_execution": True, "profile": profile,
                                     "actual_pose": robot_state["actual_pose"]})
    return profile


def prepare(installation_path, state_path, output, *, runtime_root=DEFAULT_RUNTIME, on_site_review=False):
    if on_site_review is not True:
        raise ValueError("Explicit actual --on-site-review is required before reading profile inputs.")
    profile = build_profile(_read_json(installation_path), _read_json(state_path), on_site_review=True)
    policy = load_runtime(Path(runtime_root))["policy"]
    policy.valid(profile, True)
    if len(json.dumps(profile, ensure_ascii=True, allow_nan=False).encode("ascii")) > policy.MAX_PROFILE_BYTES:
        raise ValueError("Experimental contact profile exceeds the installed receiver limit.")
    encoded = json.dumps(profile, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    output = Path(output).absolute()
    if output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        raise ValueError("Private contact profile output through symbolic links is unsupported.")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {"output": str(output), "sha256": hashlib.sha256(encoded).hexdigest(),
            "scope": "local_contact_commissioning", "offline_policy_validated": True,
            "board_registration_qualified": False, "vehicle_control_qualified": False,
            "rotation_qualified": False, "car_turn_qualified": False,
            "network_contacted": False, "motion_issued": False, "profile_applied": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--robot-state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receiver-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--on-site-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.installation, args.robot_state, args.output,
                         runtime_root=args.receiver_root, on_site_review=args.on_site_review)
    except (OSError, ValueError, TypeError, GuardError, PrewireRejected) as error:
        parser.exit(1, f"Contact profile preparation failed: {error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
