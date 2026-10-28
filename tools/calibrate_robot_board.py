"""Fit measured drawing-to-BASE pairs offline; never install or authorize motion.

Input and output contain private operating coordinates. A fit and independent
check report are measurements, not an installation qualification or TCP profile.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.robot_control.registration import (
    DrawingDomain, FitPolicy, MeasuredPoint, RegistrationIdentity,
    fit_registration, validate_independent_check,
)

INPUT_SCHEMA = "pushpilot.measured-board-base-pairs.v1"
OUTPUT_SCHEMA = "pushpilot.board-base-calibration-report.v1"


def read_pairs(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("INPUT_REQUIRES_BOUNDED_REGULAR_JSON")

    def unique_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_INPUT_KEY")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("NONFINITE_INPUT_NUMBER")

    return json.loads(path.read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_pairs, parse_constant=invalid_constant)


def fit_measured_pairs(data):
    """Require explicit measured pairs and a held-out point, without networking."""
    required = {"schema", "calibration_id", "identity", "domain", "policy",
                "fit_points", "independent_check"}
    if type(data) is not dict or set(data) != required or data["schema"] != INPUT_SCHEMA:
        raise ValueError("INVALID_MEASURED_PAIRS_SCHEMA")
    if (type(data["fit_points"]) is not list or not 3 <= len(data["fit_points"]) <= 32):
        raise ValueError("REQUIRE_3_TO_32_MEASURED_FIT_POINTS")
    identity = RegistrationIdentity(**data["identity"])
    domain = DrawingDomain(**data["domain"])
    policy = FitPolicy(**data["policy"])

    def point(value):
        if type(value) is not dict or "identity" in value:
            raise ValueError("POINT_USES_THE_EXPLICIT_SHARED_IDENTITY")
        return MeasuredPoint(identity=identity, **value)

    fitted = fit_registration(data["calibration_id"],
                              [point(value) for value in data["fit_points"]], domain, policy)
    check = validate_independent_check(fitted, point(data["independent_check"]))
    return {
        "schema": OUTPUT_SCHEMA,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "measured_drawing_to_base_pairs",
        "registration": fitted.to_dict(),
        "independent_check": check.to_dict(),
        "independent_check_accepted": check.accepted,
        "installation_qualified": False,
        "route_coverage_qualified": False,
        "motion_issued": False,
        "profile_created": False,
        "scope": "Planar XY measurement only. Contact Z, tool offset, print scale, plane level, workspace clearance and physical motion need separate qualification.",
    }


def save_report(path, report):
    path = Path(path).absolute()
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("OUTPUT_SYMLINK_UNSUPPORTED")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    encoded = json.dumps(report, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, required=True,
                        help="Private measured pairs JSON; do not supply nominal graph coordinates as BASE measurements.")
    parser.add_argument("--output", type=Path, required=True,
                        help="New private calibration report path; never overwritten or auto-installed.")
    args = parser.parse_args(argv)
    try:
        report = fit_measured_pairs(read_pairs(args.pairs))
        save_report(args.output, report)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "rejected", "error_type": type(error).__name__,
                          "motion_issued": False, "profile_created": False}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "checked" if report["independent_check_accepted"] else "check_failed",
                      "independent_check_accepted": report["independent_check_accepted"],
                      "installation_qualified": False, "motion_issued": False,
                      "profile_created": False, "saved_private_path": str(args.output)}))
    return 0 if report["independent_check_accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
