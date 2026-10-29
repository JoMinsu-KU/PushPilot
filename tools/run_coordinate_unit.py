"""Validate or explicitly execute one reviewed experimental coordinate unit.

No IO occurs without --execute. This is current-site commissioning, not an
accepted city route or permission from a simulation/MUSE result. Restarted
journals never resume; an incomplete review requires explicit read-only recovery.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.robot_control.coordinate_units import CoordinateBinding, CoordinateStage, CoordinateUnit, CoordinateUnitExecutor
from backend.robot_control.taught_ports import PrivateJournal, RealTaughtPorts
from backend.robot_control.taught_executor import ExecutionBlocked, SignalObservationTarget
from tools.run_taught_executor import read_json, reference


def unit_geometry(unit):
    value = asdict(unit)
    value["stages"] = [{key: val for key, val in row.items() if key != "review_sha256"}
                       for row in value["stages"]]
    return json.loads(json.dumps(value, allow_nan=False))


def load_unit(path):
    path = Path(path)
    bundle = read_json(path)
    required = {"schema", "binding", "unit", "site_review"}
    if (not required <= set(bundle) or set(bundle)-required-{"signal_target_evidence"}
            or bundle["schema"] != "pushpilot.experimental-coordinate-unit.v1"):
        raise ValueError("Use the exact experimental coordinate-unit bundle schema.")
    binding = CoordinateBinding(**bundle["binding"])
    data = dict(bundle["unit"])
    data["stages"] = tuple(CoordinateStage(**stage) for stage in data["stages"])
    if data.get("required_signal_observation") is not None:
        data["required_signal_observation"] = SignalObservationTarget(**data["required_signal_observation"])
    unit = CoordinateUnit(**data)
    target = unit.required_signal_observation
    if target is not None:
        source = bundle.get("signal_target_evidence")
        if not isinstance(source, dict) or source.get("sha256") != target.target_evidence_sha256:
            raise ValueError("Retain the exact private signal placement evidence before configuring joint visibility.")
        original = reference(source, path.parent)
        metadata = {key: value for key, value in asdict(target).items() if key != "target_evidence_sha256"}
        if (original.get("schema") != "pushpilot.signal-observation-target.v1"
                or original.get("visibility_only") is not True or original.get("signal_color_qualified") is not False
                or original.get("target") != json.loads(json.dumps(metadata))):
            raise ValueError("Signal placement evidence must match the exact incoming edge, native region and view; no color qualification.")
    elif "signal_target_evidence" in bundle:
        raise ValueError("Unbound signal evidence cannot invent a joint-view target.")
    review = reference(bundle["site_review"], path.parent)
    if (review.get("schema") != "pushpilot.operator-coordinate-unit-review.v1"
            or review.get("source") != "operator" or review.get("on_site_review") is not True
            or review.get("experimental_contact_authorized") is not True
            or not isinstance(review.get("operator_instruction_reference"), str)
            or not review["operator_instruction_reference"].strip()
            or review.get("binding") != asdict(binding)
            or review.get("unit_geometry") != unit_geometry(unit)
            or any(stage.review_sha256 != bundle["site_review"]["sha256"] for stage in unit.stages)):
        raise ValueError("Bind every stage, actual identity and experimental unit geometry to the explicit site review.")
    return binding, unit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-file", type=Path, required=True)
    parser.add_argument("--config-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    journal = ports = None
    try:
        binding, unit = load_unit(args.unit_file)
        if not args.execute:
            print(json.dumps({"status": "offline_validated", "hardware_contacted": False,
                              "stages": len(unit.stages), "route_qualification_claimed": False}))
            return 0
        if not args.config_file or not args.output_dir or args.output_dir.absolute().is_relative_to(ROOT):
            raise ValueError("Physical IO needs an explicit private config and a new journal outside source.")
        config = read_json(args.config_file)
        allowed = {"runtime", "token_file", "meta_env_file", "camera_epoch", "registration_id", "expected_visual",
                   "robot_origin", "camera_origin", "command_timeout_s", "native_observation_source", "confirm_joint_publication"}
        if not isinstance(config, dict) or set(config)-allowed:
            raise ValueError("Use only reviewed real-port configuration fields.")
        journal = PrivateJournal(args.output_dir)
        ports = RealTaughtPorts(adapter=binding, journal=journal, **config)
        executor = CoordinateUnitExecutor(unit, binding, ports)
        result = executor.run()
        print(json.dumps(result))
        return 0 if result["state"] == "ACCEPTED" else 2
    except Exception as error:
        code = error.code if isinstance(error, ExecutionBlocked) else "CONFIGURATION_OR_IO_ERROR"
        cleanup_error_type = None
        if ports:
            try:
                ports.hold("Experimental coordinate unit stopped; no replay, route advance or automatic recovery.")
            except Exception as hold_error:
                cleanup_error_type = type(hold_error).__name__
        if journal:
            journal.append("coordinate_unit_failed", {"error_type": type(error).__name__, "error_code": code,
                           "hold_error_type": cleanup_error_type, "automatic_replay": False})
        print(json.dumps({"status": "stopped", "error_type": type(error).__name__, "error_code": code,
                          "hold_error_type": cleanup_error_type, "automatic_replay": False}), file=sys.stderr)
        return 3
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
