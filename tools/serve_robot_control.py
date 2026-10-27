"""Start an independent commissioning API; mock by default, never start Rodi or cameras."""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]


def private_token(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Control token cannot be a symbolic link.")
    if not path.exists():
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(secrets.token_urlsafe(32)); stream.flush(); os.fsync(stream.fileno())
    token = path.read_text(encoding="ascii").strip()
    if len(token) < 32 or len(token) > 256:
        raise ValueError("Invalid private control token file.")
    return token


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("mock", "legacy"), default="mock")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8897)
    parser.add_argument("--state", type=Path, default=ROOT / "runtime/robot-control/control.sqlite3")
    parser.add_argument("--token-file", type=Path, default=ROOT / "runtime/robot-control/control.token")
    parser.add_argument("--receiver-root", type=Path, default=ROOT / "runtime/robot-control/receiver")
    args = parser.parse_args(argv)
    try:
        if not ipaddress.ip_address(args.host).is_loopback or not 1 <= args.port <= 65535:
            parser.error("The commissioning API binds numeric loopback only; use SSH forwarding for remote access.")
    except ValueError:
        parser.error("Use a numeric loopback IP address.")
    if args.backend == "legacy" and sys.platform != "linux":
        parser.error("The actual receiver mailbox backend must run on its Linux GX10 host.")
    sys.path.insert(0, str(ROOT))
    from backend.robot_control.api import create_app
    from backend.robot_control.legacy import LegacyReceiver
    from backend.robot_control.mock import MockReceiver
    from backend.robot_control.service import RobotService
    from backend.robot_control.store import Journal
    import uvicorn
    backend = LegacyReceiver(args.receiver_root.resolve()) if args.backend == "legacy" else MockReceiver()
    service = RobotService(Journal(args.state.resolve()), backend, physical=args.backend == "legacy")
    app = create_app(service, private_token(args.token_file.resolve()))
    print(f"Robot commissioning API: {args.backend}; startup disarmed; no automatic replay. Token stays in its private file.", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, workers=1, reload=False, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
