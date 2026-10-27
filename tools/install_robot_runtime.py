"""Copy only hash-reviewed POC runtime sources, never profiles, commands or runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.robot_control.legacy import DEFAULT_RUNTIME, PrewireRejected, source_manifest


def install(package_root: Path, destination: Path = DEFAULT_RUNTIME) -> dict:
    manifest = source_manifest()
    source = Path(package_root) / manifest["source_directory"]
    destination = Path(destination).absolute()
    for path in (source, destination):
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError("Runtime installation through symbolic links is unsupported.")
    payload = {}
    # Verify every input before creating or writing the installation directory.
    for name, record in manifest["files"].items():
        if Path(name).name != name:
            raise ValueError("Invalid reviewed runtime filename.")
        path = source / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != record["bytes"]:
            raise ValueError("Missing or changed reviewed runtime source: " + name)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("Runtime source hash mismatch: " + name)
        payload[name] = data
    for alias, original in manifest["aliases"].items():
        if Path(alias).name != alias:
            raise ValueError("Invalid reviewed runtime alias.")
        payload[alias] = payload[original]
    # Do not replace an existing installation or active operating state.
    if destination.exists():
        for name, data in payload.items():
            path = destination / name
            if path.is_symlink() or (path.exists() and path.read_bytes() != data):
                raise ValueError("Different runtime already exists; preserve it: " + name)
        if any((destination / name).exists() for name in ("current_session.json", "executor-owner.lock", "runs")):
            raise ValueError("An operating runtime exists; installation cannot modify it.")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in payload.items():
        path = destination / name
        if path.exists():
            continue
        descriptor, temporary_name = tempfile.mkstemp(prefix=".install-", dir=destination)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            # No-overwrite even if another installer starts concurrently.
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"installed_directory": str(destination), "files": sorted(payload), "build": manifest["build"],
            "scripts_executed": False, "network_contacted": False, "profiles_imported": False,
            "commands_replayed": False, "motion_authority": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path, help="Extracted PushPilot_Main_Project_20261026 handoff root.")
    parser.add_argument("--destination", type=Path, default=DEFAULT_RUNTIME)
    arguments = parser.parse_args(argv)
    try:
        result = install(arguments.package_root, arguments.destination)
    except (OSError, ValueError, PrewireRejected) as error:
        parser.exit(1, f"Robot runtime installation failed: {error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
