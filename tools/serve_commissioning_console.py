"""Launch the isolated, authenticated workbench. Startup never moves a robot."""
import argparse
from pathlib import Path
import secrets
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8192)
    parser.add_argument("--allowed-host", action="append", default=[])
    args = parser.parse_args(argv)
    if args.port in {502, 8080, 8897, 19507} or not 1024 <= args.port <= 65535:
        parser.error("Use a dedicated GUI port, not a product, robot API, Native or RODI port.")
    from backend.commissioning_console.service import ConsoleService
    from backend.commissioning_console.api import create_app
    from backend.robot_control.taught_ports import private_directory, write_new
    from backend.robot_control.legacy import verify_runtime
    import uvicorn
    private_directory(args.token_file.parent)
    if not args.token_file.exists():
        write_new(args.token_file, (secrets.token_urlsafe(32) + "\n").encode())
    token = args.token_file.read_text().strip()
    service = ConsoleService(args.config, args.state)
    # Catch a missing/tampered runtime manifest before exposing an Acquire
    # button. Verification reads exact source bytes; it opens no connection.
    try:
        verify_runtime(Path(service.adapter.preview.config["ports"]["runtime"]))
    except Exception:
        service.close()
        raise
    hosts = args.allowed_host or [f"127.0.0.1:{args.port}"]
    app = create_app(service, token, allowed_hosts=hosts)
    # No credential is printed. This server never starts/restarts another
    # service, a receiver, camera, a route, or an automatic background mission.
    uvicorn.run(app, host=args.host, port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
