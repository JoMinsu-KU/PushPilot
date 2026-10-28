"""Capture current HCR1 coordinates through verified read-only Native FC03 reads.

This tool needs no pendant session, motion profile or robot-control API. A
stationary teaching observation is a coordinate record, never motion authority.
Run on the robot network; output contains private operating coordinates.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.robot_control.legacy import DEFAULT_RUNTIME, load_runtime

DEFAULT_OUTPUT = ROOT / "runtime/robot-control/teaching"
VECTOR_KEYS = ("pose", "joint", "speed")
DRIFT_TOLERANCE = .2


class ReadOnlyLog:
    """Native emits its row here; no server journal or receiver state is opened."""

    def event(self, kind, data):
        if kind != "native_readonly":
            raise ValueError("UNEXPECTED_NATIVE_EVENT")


def _validate_label(label):
    if label is not None and (type(label) is not str or
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}", label) is None):
        raise ValueError("LABEL_REQUIRES_1_TO_64_SAFE_ENGLISH_CHARACTERS")


def validate_snapshot(row):
    """Validate a literal FC03 row without substituting old or predicted values."""
    if type(row) is not dict or set(row) != {
            "program_before", "program_after", "flags", "joint", "speed", "pose"}:
        raise ValueError("INVALID_NATIVE_FIELDS")
    for key in VECTOR_KEYS:
        values = row[key]
        if (type(values) is not list or len(values) != 6 or
                any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 10000
                    for v in values)):
            raise ValueError("INVALID_NATIVE_VECTOR")
    for key, count in (("flags", 6), ("program_before", 1), ("program_after", 1)):
        if (type(row[key]) is not list or len(row[key]) != count or
                any(type(v) is not int or not 0 <= v <= 65535 for v in row[key])):
            raise ValueError("INVALID_NATIVE_REGISTER")
    return row


def assess_samples(samples):
    """Accept only coherent stationary observations at Native's existing precision.

    Native speed is quantized to 0.1 degrees/second. Exact reported zero is
    required; this cannot prove motion below that resolution is absent. TCP
    translation/orientation and joint drift must also stay within 0.2 mm/degrees.
    """
    if len(samples) < 2:
        return False, "AT_LEAST_TWO_FRESH_SAMPLES_REQUIRED"
    rows = [validate_snapshot(item["snapshot"]) for item in samples]
    program = rows[0]["program_before"]
    flags = rows[0]["flags"]
    for row in rows:
        if row["program_before"] != row["program_after"] or row["program_after"] != program:
            return False, "PROGRAM_STATE_CHANGED_DURING_CAPTURE"
        if row["flags"] != flags:
            return False, "ROBOT_FLAGS_CHANGED_DURING_CAPTURE"
        if flags[0] != 1 or flags[1] not in (0, 1) or flags[2:] != [0, 0, 0, 0]:
            return False, "ROBOT_FLAGS_REQUIRE_INSPECTION"
        if any(value != 0 for value in row["speed"]):
            return False, "NONZERO_QUANTIZED_JOINT_SPEED"
    for index, first in enumerate(rows):
        for second in rows[index + 1:]:
            for key in ("pose", "joint"):
                for axis, (a, b) in enumerate(zip(first[key], second[key])):
                    delta = (a - b + 180) % 360 - 180 if key == "pose" and axis >= 3 else a - b
                    if abs(delta) > DRIFT_TOLERANCE + 1e-9:
                        return False, "COORDINATES_CHANGED_DURING_CAPTURE"
    return True, "STATIONARY_NATIVE_COORDINATES_CAPTURED"


def _private_output_directory(output_dir):
    directory = Path(output_dir).absolute()
    if directory.is_symlink() or any(parent.is_symlink() for parent in directory.parents):
        raise ValueError("OUTPUT_SYMLINK_UNSUPPORTED")
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    if os.name != "nt":
        directory.chmod(0o700)
    return directory


def collect(runtime, output_dir=DEFAULT_OUTPUT, *, label=None, samples=3,
            runtime_loader=None, sleep=time.sleep):
    """Read a bounded fresh series, save private evidence, and return (record, path).

    A read error ends acquisition. No saved sample is replayed, and no failed
    read is retried. Runtime verification precedes construction of Native.
    """
    _validate_label(label)
    if type(samples) is not int or not 1 <= samples <= 10:
        raise ValueError("SAMPLE_COUNT_REQUIRES_1_TO_10")
    directory = _private_output_directory(output_dir)
    record = {
        "schema": "pushpilot.native-teaching-observation.v1",
        "source": "native_fc03_readonly",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "label": label,
        "requested_samples": samples,
        "samples": [],
        "accepted_teaching_point": False,
        "acquisition_status": "unavailable",
        "reason": "NO_FRESH_NATIVE_OBSERVATION",
        "motion_issued": False,
        "coordinate_units": {"tcp_translation": "mm", "tcp_orientation": "deg",
                             "joint": "deg", "speed": "deg/s"},
        "native_resolution": {"tcp_mm_or_deg": .1, "joint_deg": .1, "speed_deg_s": .1},
        "stationary_criteria": {"minimum_samples": 2, "quantized_joint_speed": 0,
                                "maximum_pairwise_drift_mm_or_deg": DRIFT_TOLERANCE},
        "program_state_scope": "Register coherence only; no program-state readiness or execution permission is inferred.",
        "scope": "Current coordinates only; no tool-definition readback, installation qualification or control authority.",
    }
    try:
        modules = (runtime_loader or load_runtime)(Path(runtime))
        native = modules["transport"].Native(ReadOnlyLog())
        for index in range(samples):
            row = native.snapshot(timeout_s=2)
            validate_snapshot(row)
            record["samples"].append({
                "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "captured_monotonic_ns": time.monotonic_ns(),
                "snapshot": copy.deepcopy(row),
            })
            if index + 1 < samples:
                sleep(.1)
        accepted, reason = assess_samples(record["samples"])
        record.update(accepted_teaching_point=accepted, reason=reason,
                      acquisition_status="captured" if accepted else "diagnostic")
    except Exception as error:
        # Do not expose driver messages, private paths, addresses or credentials.
        record.update(reason="NATIVE_ACQUISITION_FAILED", error_type=type(error).__name__)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / (stamp + "-" + uuid.uuid4().hex[:12] + ".private.json")
    encoded = json.dumps(record, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return record, path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT,
                        help="Private coordinate evidence directory; keep outside Git.")
    parser.add_argument("--label", help="Optional English teaching-point label; no coordinates are inferred.")
    parser.add_argument("--samples", type=int, choices=range(1, 11), default=3)
    args = parser.parse_args(argv)
    try:
        record, path = collect(args.runtime, args.output_dir, label=args.label, samples=args.samples)
    except (OSError, ValueError) as error:
        print(json.dumps({"source": "native_fc03_readonly", "status": "unavailable",
                          "error_type": type(error).__name__, "motion_issued": False}), file=sys.stderr)
        return 2
    latest = record["samples"][-1]["snapshot"] if record["samples"] else None
    print(json.dumps({
        "source": record["source"], "status": record["acquisition_status"],
        "accepted_teaching_point": record["accepted_teaching_point"], "reason": record["reason"],
        "fresh_samples": len(record["samples"]), "tcp_mm_deg": latest["pose"] if latest else None,
        "joint_deg": latest["joint"] if latest else None, "motion_issued": False,
        "saved_private_path": str(path),
    }, allow_nan=False))
    return 0 if record["accepted_teaching_point"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
