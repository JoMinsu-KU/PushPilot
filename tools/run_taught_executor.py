"""Validate, or explicitly run, one approved private taught physical course.

No network or hardware is contacted without --execute. Interrupted journals are
never resumed. Do not feed a simulated action/approval receipt into this runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.maps import MapDefinition
from backend.robot_control.taught_executor import (
    ApprovedRoute, ExecutionBlocked, MeasuredRoad, MeasuredTransition, MeasuredTransitionAction,
    MeasuredObservationClearance, TaughtAdapter, TaughtExecutor, compile_taught_route,
)
from backend.robot_control.taught_ports import PrivateJournal, RealTaughtPorts


def read_json(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 2_000_000:
        raise ValueError("Use a bounded ordinary private JSON file.")
    return json.loads(path.read_bytes())


def reference(reference, parent):
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        raise ValueError("Evidence references require the original path and SHA-256.")
    path = Path(reference["path"])
    if not path.is_absolute():
        path = parent / path
    value = read_json(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
        raise ValueError("Private source evidence does not match its recorded hash.")
    return value


def load_route(path):
    path = Path(path)
    value = read_json(path)
    if set(value) != {"schema", "route", "provider_evidence", "physical_approval"} or value["schema"] != "pushpilot.physical-approved-route.v1":
        raise ValueError("Use the exact physically approved route bundle schema.")
    route = ApprovedRoute(**value["route"])
    provider = reference(value["provider_evidence"], path.parent)
    result = provider.get("provider_result") or provider.get("result") or {}
    context = provider.get("map_context") or {}
    if (provider.get("source") != "meta" or provider.get("input_kind") != "live_native_frame_and_graph"
            or provider.get("id") != route.muse_provider_receipt
            or result.get("requires_clarification") is not False
            or result.get("route_nodes") != list(route.node_ids) or result.get("destination") != route.destination
            or (context.get("map_id"), context.get("map_version"), context.get("map_hash"))
            != (route.map_id, route.map_version, route.map_hash)):
        raise ValueError("Bind the actual original MUSE graph result to this exact route; no demo substitution.")
    approval = reference(value["physical_approval"], path.parent)
    if (approval.get("schema") != "pushpilot.operator-physical-course-approval.v1"
            or approval.get("source") != "operator" or approval.get("id") != route.approval_receipt
            or approval.get("approved") is not True or approval.get("simulation_approval") is not False
            or not isinstance(approval.get("operator_instruction_reference"), str)
            or not approval["operator_instruction_reference"].strip()
            or any(approval.get(key) != value["route"][key] for key in
                   ("plan_id", "revision", "destination", "node_ids", "map_id", "map_version", "map_hash"))
            or approval.get("commissioning_without_signals") != route.commissioning_without_signals):
        raise ValueError("A distinct current operator physical-course approval must bind this exact plan revision.")
    # A live planning record can correctly remain simulation_only=true: its
    # symbolic intent is useful, but physical authority comes from the separate
    # actual operator instruction, reviewed adapter and robot service checks.
    return route


def load_adapter(path):
    path = Path(path)
    value = read_json(path)
    if set(value) != {"schema", "adapter", "qualification_evidence"} or value["schema"] != "pushpilot.taught-physical-adapter.v1":
        raise ValueError("Use the exact privately reviewed taught adapter bundle schema.")
    data = dict(value["adapter"])
    data["roads"] = tuple(MeasuredRoad(**road) for road in data["roads"])
    transitions = []
    for item in data.get("transitions", []):
        transition = dict(item)
        transition["actions"] = tuple(MeasuredTransitionAction(**action) for action in transition["actions"])
        transitions.append(MeasuredTransition(**transition))
    data["transitions"] = tuple(transitions)
    clearances = []
    for item in data.get("observation_clearances", []):
        clearance = dict(item)
        if clearance.get("withdrawal") is not None:
            clearance["withdrawal"] = MeasuredTransitionAction(**clearance["withdrawal"])
        clearance["withdrawal_actions"] = tuple(MeasuredTransitionAction(**action)
                                                 for action in clearance.get("withdrawal_actions", []))
        if clearance.get("recontact") is not None:
            clearance["recontact"] = MeasuredTransitionAction(**clearance["recontact"])
        clearances.append(MeasuredObservationClearance(**clearance))
    data["observation_clearances"] = tuple(clearances)
    adapter = TaughtAdapter(**data)
    sources = {item["sha256"]: reference(item, path.parent) for item in value["qualification_evidence"]}
    required = {adapter.review_sha256} | {road.qualification_sha256 for road in adapter.roads}
    required |= {item.qualification_sha256 for item in adapter.transitions}
    required |= {action.qualification_sha256 for item in adapter.transitions for action in item.actions}
    required |= {item.qualification_sha256 for item in adapter.observation_clearances}
    required |= {action.qualification_sha256 for item in adapter.observation_clearances for action in item.withdrawal_actions}
    required |= {item.recontact.qualification_sha256 for item in adapter.observation_clearances if item.recontact is not None}
    if not required <= sources.keys():
        raise ValueError("Retain the original actual review and qualification record for every selected corridor.")
    review = sources[adapter.review_sha256]
    if (review.get("schema") != "pushpilot.taught-course-qualification.v1"
            or review.get("qualification") != "accepted" or review.get("physical_execution") is not True
            or review.get("map_identity") != {"id": adapter.map_id, "version": adapter.map_version, "hash": adapter.map_hash}
            or review.get("scope") != ("measured_contact_route_with_transitions" if adapter.transitions else "fixed_pose_contact_corridor")):
        raise ValueError("A proposed geometry or synthetic test is not an accepted actual contact-corridor review.")
    return adapter


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-file", type=Path, required=True)
    parser.add_argument("--adapter-file", type=Path, required=True)
    parser.add_argument("--map-file", type=Path, required=True)
    parser.add_argument("--config-file", type=Path, help="Private RealTaughtPorts paths/view/expected-outcome configuration.")
    parser.add_argument("--output-dir", type=Path, help="New private journal outside the source repository.")
    parser.add_argument("--execute", action="store_true", help="Explicitly run physical IO; absent means offline validation only.")
    parser.add_argument("--commissioning-without-signals", action="store_true", help="Explicit separate physical course qualification before signal integration.")
    parser.add_argument("--stroke-mm", type=float, default=10.)
    parser.add_argument("--max-strokes", type=int, default=100)
    parser.add_argument("--max-reobservations", type=int, default=3)
    args = parser.parse_args(argv)
    journal = ports = executor = None
    try:
        if not 0 < args.stroke_mm <= 20 or not 1 <= args.max_strokes <= 500 or not 0 <= args.max_reobservations <= 10:
            raise ValueError("Use a <=20 mm cadence and finite stroke/reobservation budgets.")
        route, adapter = load_route(args.route_file), load_adapter(args.adapter_file)
        drawing = MapDefinition(args.map_file)
        roads = compile_taught_route(route, adapter, drawing)
        if args.commissioning_without_signals != route.commissioning_without_signals:
            raise ValueError("The explicit commissioning signal mode must match the approved route.")
        if not args.execute:
            print(json.dumps({"status": "offline_validated", "motion_issued": False,
                              "selected_edges": [[r.source, r.target] for r in roads],
                              "physical_qualification_claimed_by_test": False}))
            return 0
        if not args.config_file or not args.output_dir:
            raise ValueError("Explicit physical execution requires private IO configuration and a separate evidence directory.")
        output = args.output_dir.absolute()
        if output.is_relative_to(ROOT):
            raise ValueError("Keep real operating evidence outside the source repository.")
        config = read_json(args.config_file)
        allowed = {"runtime", "token_file", "meta_env_file", "camera_epoch", "registration_id", "expected_visual",
                   "robot_origin", "camera_origin", "command_timeout_s", "native_observation_source"}
        if not isinstance(config, dict) or set(config)-allowed:
            raise ValueError("Use only reviewed private IO path/view settings; no injected executable callbacks.")
        journal = PrivateJournal(output)
        ports = RealTaughtPorts(adapter=adapter, journal=journal, **config)
        executor = TaughtExecutor(route, adapter, drawing, ports, stroke_mm=args.stroke_mm)
        if executor.state != "READY":
            raise ExecutionBlocked("RESTART_RECONCILIATION", "Existing evidence requires independent reconciliation; no automatic resume.")
        journal.append("course_started", {"route_file_sha256": hashlib.sha256(args.route_file.read_bytes()).hexdigest(),
                       "adapter_file_sha256": hashlib.sha256(args.adapter_file.read_bytes()).hexdigest(),
                       "route": route.__dict__, "stroke_mm": args.stroke_mm,
                       "commissioning_without_signals": route.commissioning_without_signals})
        result = None
        for _ in range(args.max_strokes):
            try:
                result = executor.advance()
            except (TimeoutError, urllib.error.URLError):
                if executor.state not in {"WAIT_REVIEW", "WAIT_CLEARANCE_REVIEW"}:
                    raise
                result = {"state": executor.state}
            attempts = 0
            while result["state"] in {"WAIT_REVIEW", "WAIT_CLEARANCE_REVIEW"} and attempts < args.max_reobservations:
                time.sleep(1)
                try:
                    result = executor.reobserve()
                except (TimeoutError, urllib.error.URLError):
                    if executor.state not in {"WAIT_REVIEW", "WAIT_CLEARANCE_REVIEW"}:
                        raise
                    result = {"state": executor.state}
                attempts += 1
            if result["state"] not in {"READY", "CLEARANCE_READY"}:
                break
        if result and result["state"] == "WAIT_HUMAN_RESET":
            print(json.dumps({"status": "vehicle_goal_verified_wait_human_reset", "destination": route.destination,
                              "human_reset_required": True, "automatic_return": False, "automatic_replay": False}))
            return 0
        ports.hold("Taught course reached its bounded stroke/reobservation limit or requires reconciliation.")
        print(json.dumps({"status": result["state"] if result else executor.state,
                          "vehicle_goal_completed": False, "automatic_replay": False}))
        return 2
    except Exception as error:
        if ports is not None:
            try:
                ports.hold("Taught executor stopped after an error. Reconcile the recorded UUID before any additional action.")
            except Exception:
                pass
        # Do not print provider exception strings, local credential paths or keys.
        print(json.dumps({"status": "stopped", "code": getattr(error, "code", "CONFIGURATION_OR_IO_ERROR"),
                          "state": executor.state if executor else "UNSTARTED",
                          "error_type": type(error).__name__, "automatic_retry": False}), file=sys.stderr)
        return 2
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
