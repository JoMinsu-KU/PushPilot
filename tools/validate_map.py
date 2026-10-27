"""Audit a replacement drawing map without contacting providers or hardware."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.maps import DEFAULT_MAP, MapDefinition  # noqa: E402


def audit_definition(definition: MapDefinition) -> dict:
    """Inspect directed reachability without substituting a selected route."""
    return definition.planning_audit()


def audit(path: str | Path) -> dict:
    return audit_definition(MapDefinition(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map_path", nargs="?", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--map-path", type=Path, dest="selected_map_path", help="Explicit candidate JSON; overrides the optional positional path.")
    args = parser.parse_args()
    try:
        result = audit(args.selected_map_path or args.map_path)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as error:
        print(json.dumps({"status": "failed", "error": str(error), "equipment_contacted": False}))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
