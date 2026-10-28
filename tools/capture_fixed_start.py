"""Save an acknowledged fixed robot start without needing vehicle visibility.

This uses authenticated GET status and read-only Native FC03 only. It neither
returns the robot to that pose nor claims that a car reset or contact is known.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.maps import MapDefinition
from backend.robot_control.legacy import DEFAULT_RUNTIME, load_runtime
from backend.robot_control.start_reference import StartIdentity, freeze_start
from tools.prepare_robot_installation import _read_json
from tools.read_robot_pose import ReadOnlyLog, validate_snapshot


def status_reader(url, token_file):
    parsed = urllib.parse.urlsplit(url)
    try:
        valid = (parsed.scheme == "http" and ipaddress.ip_address(parsed.hostname or "").is_loopback
                 and parsed.path in ("", "/") and not parsed.query and not parsed.fragment
                 and parsed.username is None and parsed.password is None)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("NUMERIC_LOOPBACK_CONTROL_URL_REQUIRED")
    token_file = Path(token_file)
    if token_file.is_symlink() or token_file.stat().st_size > 4096:
        raise ValueError("PRIVATE_CONTROL_TOKEN_FILE_REQUIRED")
    token = token_file.read_text(encoding="ascii").strip()
    if not 32 <= len(token) <= 256:
        raise ValueError("PRIVATE_CONTROL_TOKEN_FILE_REQUIRED")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get_status():
        request = urllib.request.Request(url.rstrip("/") + "/v1/status",
                                         headers={"X-PushPilot-Control-Token": token})
        with opener.open(request, timeout=3) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("BOUNDED_CONTROL_STATUS_REQUIRED")
        return json.loads(raw)

    return get_status


def capture(identity, runtime, get_status, *, operator_fixed_setup=False,
            runtime_loader=None, clock=time.time, sleep=time.sleep):
    if operator_fixed_setup is not True:
        raise ValueError("OPERATOR_FIXED_SETUP_ACKNOWLEDGEMENT_REQUIRED")
    first = get_status()
    if first.get("armed") is not False or first.get("active_commands") != []:
        raise ValueError("DISARMED_INACTIVE_CAPTURE_REQUIRED")
    native = (runtime_loader or load_runtime)(Path(runtime))["transport"].Native(ReadOnlyLog())
    rows = []
    for index in range(3):
        row = validate_snapshot(native.snapshot(timeout_s=2))
        rows.append({"captured_at": clock(), "snapshot": row})
        if index < 2:
            sleep(.1)
    second = get_status()
    stamp = clock()
    if second.get("armed") is not False or second.get("active_commands") != []:
        raise ValueError("DISARMED_INACTIVE_CAPTURE_REQUIRED")
    before, after = first["receiver"], second["receiver"]
    for key in ("session_id", "seq", "profile_id", "actual_pose", "actual_joint"):
        if before.get(key) != after.get(key):
            raise ValueError("RECEIVER_CHANGED_DURING_CAPTURE")
    return freeze_start(identity, after, rows, receiver_captured_at=stamp, now=clock(),
                        operator_fixed_setup=True)


def save_reference(path, reference):
    path = Path(path).absolute()
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("OUTPUT_SYMLINK_UNSUPPORTED")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(json.dumps(reference.to_dict(), indent=2, allow_nan=False).encode() + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-path", type=Path, required=True)
    parser.add_argument("--installation", type=Path, required=True,
                        help="Current private measured installation with TCP definition hash and tool identity.")
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--url", default="http://127.0.0.1:8897")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operator-fixed-start", action="store_true",
                        help="Record the operator's fixed initial setup; never asserts a visible or measured car pose.")
    args = parser.parse_args(argv)
    try:
        if not args.operator_fixed_start:
            raise ValueError("OPERATOR_FIXED_SETUP_ACKNOWLEDGEMENT_REQUIRED")
        mapping, installation = MapDefinition(args.map_path), _read_json(args.installation)
        if installation.get("map_id", mapping.id) != mapping.id or installation.get("map_hash", mapping.geometry_hash) != mapping.geometry_hash:
            raise ValueError("MAP_IDENTITY_CHANGED")
        identity = StartIdentity(mapping.id, mapping.version, mapping.geometry_hash,
                                 installation["tcp_id"], installation["tcp_definition_sha256"], installation["tool_id"])
        reader = status_reader(args.url, args.token_file)

        def bound_status():
            state = reader()
            if state.get("installation") != installation:
                raise ValueError("CURRENT_INSTALLATION_CHANGED")
            profile = state.get("receiver", {}).get("profile") or {}
            binding = profile.get("installation_binding") or {}
            if (profile.get("tcp_id") != identity.tcp_id
                    or binding.get("tcp_definition_sha256") != identity.tcp_definition_sha256
                    or binding.get("tool_id") != identity.tool_id):
                raise ValueError("CURRENT_TCP_TOOL_BINDING_CHANGED")
            return state

        reference = capture(identity, args.runtime, bound_status,
                            operator_fixed_setup=True)
        save_reference(args.output, reference)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        print(json.dumps({"status": "rejected", "error_type": type(error).__name__, "motion_issued": False}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "captured", "source": "receiver_and_native_fc03",
                      "vehicle_visibility_required": False, "car_pose_measured": False,
                      "geometry_qualified": False, "motion_issued": False,
                      "saved_private_path": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
