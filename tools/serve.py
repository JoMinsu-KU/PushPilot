"""Serve the built operator workspace and simulation API in one Python process.

This launcher does not install dependencies, build assets, contact a provider,
configure a service manager, or start robot/camera processes.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def bind_address(value: str) -> str:
    """Accept explicit IP addresses or localhost, without URL interpretation."""
    if value == "localhost":
        return value
    try:
        ipaddress.ip_address(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use an IP address or localhost, without a URL or port.") from error
    return value


def port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("The port must be an integer from 1 to 65535.") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("The port must be an integer from 1 to 65535.")
    return port


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=bind_address, default="127.0.0.1", help="Bind IP address (default: 127.0.0.1). LAN access requires an explicit address.")
    parser.add_argument("--port", type=port_number, default=8080, help="Unused TCP port (default: 8080).")
    parser.add_argument("--state-path", type=Path, help="SQLite file outside a release for shared state. Relative paths resolve from the calling directory.")
    parser.add_argument("--map-path", type=Path, help="Replaceable temporary-map JSON. Selected at startup; does not migrate approvals or camera registrations.")
    parser.add_argument("--api-only", action="store_true", help="Allow startup without frontend/dist/index.html for API development.")
    parser.add_argument("--live-camera-url", help="Opt in to an existing numeric loopback camera preview service (for example http://127.0.0.1:8895). Does not start a camera process.")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required for the application runtime.")
    if not args.api_only and not (ROOT / "frontend" / "dist" / "index.html").is_file():
        parser.error("The operator workspace is not built. Run npm ci and npm run build in frontend, or pass --api-only for API development.")
    if args.state_path is not None:
        state_path = args.state_path.expanduser().resolve()
        if state_path.is_dir():
            parser.error("--state-path must name a SQLite file, not a directory.")
        os.environ["PUSHPILOT_STATE_PATH"] = str(state_path)
    if args.map_path is not None:
        map_path = args.map_path.expanduser().resolve()
        if not map_path.is_file():
            parser.error("--map-path must name an existing temporary-map JSON file.")
        os.environ["PUSHPILOT_MAP_PATH"] = str(map_path)
    try:
        import uvicorn
    except ImportError:
        parser.error("Runtime dependencies are missing. Install requirements.lock into the active virtual environment.")
    # Keep imports and relative development paths independent of the shell cwd.
    sys.path.insert(0, str(ROOT))
    if args.live_camera_url is not None:
        from backend.live_camera import camera_url
        try:
            os.environ["PUSHPILOT_LIVE_CAMERA_URL"] = camera_url(args.live_camera_url)
        except ValueError as error:
            parser.error(str(error))
    os.chdir(ROOT)
    uvicorn.run("backend.app:app", host=args.host, port=args.port, workers=1,
                reload=False, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
