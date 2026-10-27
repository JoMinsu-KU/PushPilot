"""Authenticated local commissioning client. No script evaluation or implicit motion retry."""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "events", "installation", "arm", "hold", "observe", "command", "get", "cancel", "review", "reconcile"))
    parser.add_argument("--url", default="http://127.0.0.1:8897")
    parser.add_argument("--token-file", type=Path, default=ROOT / "runtime/robot-control/control.token")
    parser.add_argument("--data", type=Path, help="Explicit bounded UTF-8 JSON file; never executed.")
    parser.add_argument("--id", help="Command UUID for get/cancel/review/reconcile.")
    args = parser.parse_args(argv)
    parsed = urllib.parse.urlsplit(args.url)
    try:
        if parsed.scheme != "http" or not ipaddress.ip_address(parsed.hostname or "").is_loopback or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
            raise ValueError()
    except ValueError:
        parser.error("Use a numeric loopback HTTP URL, including an explicit SSH-forwarded port if needed.")
    if args.action in {"get", "cancel", "review", "reconcile"}:
        try:
            identifier = str(UUID(args.id or ""))
        except ValueError:
            parser.error("This action requires --id with the command UUID.")
        path = f"/v1/commands/{identifier}" + (f"/{args.action}" if args.action != "get" else "")
    else:
        path = "/v1/" + {"observe": "observations", "command": "commands"}.get(args.action, args.action)
    method = "GET" if args.action in {"status", "events", "get"} else "POST"
    try:
        token = args.token_file.read_text(encoding="ascii").strip()
        body = None
        if method == "POST":
            if args.action == "cancel":
                body = b"{}"
            else:
                if not args.data or args.data.stat().st_size > 65536:
                    parser.error("This action requires --data with a bounded JSON file.")
                value = json.loads(args.data.read_text(encoding="utf-8-sig"))
                body = json.dumps(value, allow_nan=False).encode()
        request = urllib.request.Request(args.url.rstrip("/") + path, data=body, method=method,
                                        headers={"X-PushPilot-Control-Token": token, "Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=10) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Control response exceeds the client limit.")
        print(json.dumps(json.loads(raw), indent=2))
        return 0
    except urllib.error.HTTPError as error:
        print(error.read(65536).decode("utf-8", errors="replace"), file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"Control request unavailable: {type(error).__name__}. Query status; do not resend a move with a new ID.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
