"""Run equipment-free development checks from the standalone application root."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORIES = ("backend", "frontend", "contracts", "prompts", "tests", "tools", "deploy", "docs")
EXCLUDED_DIRECTORIES = {".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build", "runtime", "secrets", "logs", "uploads"}


def source_files():
    """Inspect source trees without following links or loading local credentials."""
    for directory in SOURCE_DIRECTORIES:
        base = ROOT / directory
        if not base.exists():
            continue
        for current, directories, filenames in os.walk(base, followlinks=False):
            directories[:] = sorted(
                name for name in directories
                if name not in EXCLUDED_DIRECTORIES and not (Path(current) / name).is_symlink()
            )
            for name in sorted(filenames):
                path = Path(current) / name
                if path.is_symlink():
                    raise ValueError(f"Source symlinks are unsupported: {path.relative_to(ROOT)}")
                if ".local." in name or name.startswith(".env"):
                    continue
                yield path


def check() -> int:
    """Check source syntax only; never initialize application or robot services."""
    counts = {"python_files": 0, "json_files": 0}
    try:
        for path in source_files():
            if path.suffix == ".py":
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path.relative_to(ROOT)))
                counts["python_files"] += 1
            elif path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8-sig"))
                counts["json_files"] += 1
    except (OSError, ValueError, SyntaxError) as error:
        print(f"Development check failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", **counts, "equipment_contacted": False}))
    return 0


def test() -> int:
    """Run application-workspace tests without starting operating services."""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, env=environment, check=False,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "test"))
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required for the application workspace.")
    return check() if args.command == "check" else test()


if __name__ == "__main__":
    raise SystemExit(main())
