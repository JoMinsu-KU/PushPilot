"""Config-backed physical mission driver over the existing guarded real ports.

The configuration is a private, qualified deployment artifact. Candidate
catalogues remain unavailable. No historical profile, receiver sequence or
command is restored. Translation and unloaded wrist targets are measured;
MUSE observations are delegated to the supervisor's observer callback.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from uuid import uuid4

from .coordinate_units import CoordinateBinding, CoordinateStage, CoordinateUnit
from .gates import GuardError, admit
from .mission_catalog import PrimitiveQualification, content_hash, primitive_from_dict
from .mission_policy import (CorrectionTemplate, MissionPlan, MotionReceipt, ParkingTarget,
    RouteStep, RuntimeContext, SignalGate, SiteBinding, TaughtPrimitive, ViewClearance)
from .taught_executor import ExecutionBlocked, MotionIntent, checked_frame, checked_snapshot
from .taught_ports import PrivateJournal, RealTaughtPorts, write_new


WORKSPACE_KEYS = ("destination", "route_nodes", "map_id", "map_version", "map_hash")


def _reference(value, parent):
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError("Use a hash-bound private file reference.")
    path = (parent / value["path"]).resolve()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != value["sha256"]:
        raise ValueError("A private physical deployment artifact changed.")
    return json.loads(raw)


def _primitive(value):
    return TaughtPrimitive(**value)


def plan_from_dict(value):
    """Load the exact policy shape; dataclasses validate finite limits/links."""
    data = dict(value)
    data["binding"] = SiteBinding(**data["binding"])
    steps = []
    for row in data["steps"]:
        row = dict(row)
        row["primitive"] = _primitive(row["primitive"])
        if row.get("signal_gate") is not None:
            gate = dict(row["signal_gate"])
            gate["recontact"] = _primitive(gate["recontact"])
            gate["release_to_wait"] = _primitive(gate["release_to_wait"])
            row["signal_gate"] = SignalGate(**gate)
        steps.append(RouteStep(**row))
    data["steps"] = tuple(steps)
    data["empty_return"] = tuple(_primitive(p) for p in data["empty_return"])
    data["parking"] = ParkingTarget(**data["parking"])
    data["corrections"] = tuple(CorrectionTemplate(**{**row, "primitive": _primitive(row["primitive"])})
                                 for row in data.get("corrections", ()))
    data["clearances"] = tuple(ViewClearance(**{**row, "primitive": _primitive(row["primitive"]),
        "restore": _primitive(row["restore"]) if row.get("restore") else None})
        for row in data.get("clearances", ()))
    return MissionPlan(**data)


def _plan_primitives(plan):
    result = [s.primitive for s in plan.steps] + list(plan.empty_return)
    result += [c.primitive for c in plan.corrections] + [c.primitive for c in plan.clearances]
    result += [c.restore for c in plan.clearances if c.restore]
    for step in plan.steps:
        if step.signal_gate:
            result += [step.signal_gate.recontact, step.signal_gate.release_to_wait]
    return result


class _StopAwareAPI:
    """Recheck the shared stop latch at the final arm/command API boundary."""
    def __init__(self, api, latch, validate_status=None):
        self.api, self.latch, self.validate_status = api, latch, validate_status

    def call(self, path, *args, **kwargs):
        if path in {"/v1/arm", "/v1/commands"} and self.latch.is_set():
            raise ExecutionBlocked("MISSION_STOPPED", "The mission stop latch inhibits arm/dispatch.")
        if path in {"/v1/arm", "/v1/commands"} and self.validate_status:
            self.validate_status(self.api.call("/v1/status"))
            if self.latch.is_set():
                raise ExecutionBlocked("MISSION_STOPPED", "Stop during the final profile check inhibits dispatch.")
        result = self.api.call(path, *args, **kwargs)
        if path == "/v1/status" and self.validate_status:
            self.validate_status(result)
        return result


class ConfigBackedMissionDriver:
    """Synchronous service driver. Run blocking methods in the service worker.

    `hold` may be called from another thread; it sets the stop latch before IO.
    A stop never resumes automatically. `prepare` clears it only for a new
    explicit mission after fresh readback at that recipe's qualified START.
    """
    def __init__(self, config_file, observer_callback=None, *, port_factory=None, journal_factory=None):
        self.config_file = Path(config_file)
        self.observer_callback = observer_callback
        self.port_factory = port_factory or RealTaughtPorts
        self.journal_factory = journal_factory or PrivateJournal
        self.stop_latch, self.execution_lock = threading.Event(), threading.Lock()
        self._stop_lock, self._stop_generation = threading.Lock(), 0
        self.stop_latch.set()
        self.currentplan = self.plan = None
        self.ports = self.journal = None
        self.config = self.binding = None
        self.current_context_id, self.pending_command_id = None, None
        self.before_frame = self.last_snapshot = None
        self.workspace_binding = None
        self.issued = set()
        self._configuration_error = None
        self._profile_preflight_done = False
        try:
            self._load()
        except Exception as error:
            self._configuration_error = type(error).__name__ + ": " + str(error)

    def _load(self):
        data = json.loads(self.config_file.read_bytes())
        allowed = {"schema", "enabled", "site_binding", "coordinate_binding", "ports", "journal_root",
                   "catalogue", "contexts", "primitives", "routes", "measurement_adapter", "profile_coverage"}
        if (not allowed <= set(data) or set(data) - allowed - {"observations"}
                or data["schema"] != "pushpilot.physical-mission-driver.v1"
                or type(data["enabled"]) is not bool):
            raise ValueError("Use the complete explicit physical driver deployment schema.")
        self.config = data
        self.observation_config = data.get("observations", {})
        if data["ports"].get("native_observation_source") != "host_journal":
            raise ValueError("Use the existing host Native owner; mission execution cannot add a quiet-query client.")
        self.binding = SiteBinding(**data["site_binding"])
        self.coordinate_binding = CoordinateBinding(**data["coordinate_binding"])
        if (self.binding.map_sha256 != self.coordinate_binding.map_hash
                or self.binding.tool_id != self.coordinate_binding.tool_id
                or self.binding.car_id != self.coordinate_binding.car_id
                or data["ports"]["camera_epoch"] != self.binding.camera_epoch
                or data["ports"]["registration_id"] != self.binding.calibration_id):
            raise ValueError("Policy, tool, map and camera bindings must describe one installation.")
        self.catalogue = _reference(data["catalogue"], self.config_file.parent)
        self.measured = {}
        for group in ("primitives", "phase_paths", "unloaded_wrist_edges", "empty_paths"):
            for row in self.catalogue.get(group, []):
                primitive = primitive_from_dict(row)
                if primitive.id in self.measured:
                    raise ValueError("Measured primitive IDs must be unique.")
                self.measured[primitive.id] = primitive
        self.qualifications = {}
        for pid, spec in data["primitives"].items():
            p = self.measured[spec["catalogue_id"]]
            q = PrimitiveQualification(**spec["qualification"])
            if (q.primitive_geometry_sha256 != p.geometry_sha256
                    or q.installation_id != self.binding.installation_id
                    or content_hash(spec["qualification"]) != spec["qualification_sha256"]):
                raise ValueError("Bind each released primitive to its exact geometry and installation.")
            self.qualifications[pid] = q
            if (spec["source_context_id"] not in data["contexts"]
                    or spec["target_context_id"] not in data["contexts"]):
                raise ValueError("Every primitive needs declared source and target contexts.")
            source = data["contexts"][spec["source_context_id"]]["pose_base"]
            target = data["contexts"][spec["target_context_id"]]["pose_base"]
            if tuple(source) != p.stages[0].start_base or tuple(target) != p.stages[-1].target_base:
                raise ValueError("Context coordinates differ from their measured primitive.")
            if p.kind == "partial_unit" or p.original_verdict in {"FAIL", "UNCERTAIN"} and p.kind == "coordinate_unit":
                raise ValueError("A failed or partial contact unit cannot be a released route primitive.")
            if p.kind == "contact_strokes":
                raise ValueError("Legacy contact-only courses need separately measured bounded withdrawal units.")
            if any(s.phase == "contact" for s in p.stages):
                # Retain the established <=40 mm whole-unit and <=20 mm stage
                # contracts; a mission must not concatenate hidden loaded work.
                CoordinateUnit("deployment-validation", "deployment-plan", 1, p.source, p.target,
                    self.binding.installation_id, "deployment-profile", tuple(CoordinateStage(
                        s.id, s.phase, s.start_base, s.target_base, q.review_sha256) for s in p.stages),
                    p.expected_visual, at_goal=p.at_goal, contact_travel_limit_mm=p.contact_travel_limit_mm)
            if p.kind == "wrist_edge" and not isinstance(spec.get("wrist"), dict):
                raise ValueError("An unloaded wrist primitive needs the directed joint/runtime binding.")
        self.routes = []
        for route in data["routes"]:
            plan = plan_from_dict(route["plan"])
            if plan.binding != self.binding or plan.destination != route["workspace_binding"]["destination"]:
                raise ValueError("Destination and physical site must match the exact symbolic route.")
            if set(route["workspace_binding"]) != set(WORKSPACE_KEYS):
                raise ValueError("Bind destination, exact route nodes and map identity.")
            for p in _plan_primitives(plan):
                spec = data["primitives"][p.id]
                if (not p.qualified or (p.source_context_id, p.target_context_id, p.qualification_sha256) !=
                        (spec["source_context_id"], spec["target_context_id"], spec["qualification_sha256"])):
                    raise ValueError("A policy primitive must match the released private deployment entry.")
                measured = self.measured[spec["catalogue_id"]]
                if p.empty_tool and any(s.phase == "contact" for s in measured.stages):
                    raise ValueError("A contact trajectory cannot be relabelled as empty-tool clearance or return.")
                if measured.kind == "wrist_edge" and not p.empty_tool:
                    raise ValueError("A measured unloaded wrist edge cannot become a loaded turn.")
            self.routes.append((route["workspace_binding"], plan))
        if not isinstance(data["measurement_adapter"], dict) or not data["measurement_adapter"]:
            raise ValueError("Supply the measurement adapter's original qualification configuration.")
        # Its executable observer owns exact adapter-schema and holdout checks.
        # Adding parallel 'qualified' flags would change that configuration hash.
        coverage = data["profile_coverage"]
        if not isinstance(coverage, dict) or set(coverage) != {"record", "reference_sha256"}:
            raise ValueError("A current-profile whole-route coverage review is required.")
        record = coverage["record"]
        expected_fields = {"schema", "status", "profile_sha256", "installation_sha256",
                           "primitive_geometry_sha256", "clearance_review_sha256", "kinematic_review_sha256"}
        if (not isinstance(record, dict) or set(record) != expected_fields
                or record["schema"] != "pushpilot.mission-profile-coverage.v1"
                or record["status"] != "accepted"
                or content_hash(record) != coverage["reference_sha256"]
                or any(not isinstance(record[k], str) or not re.fullmatch(r"[0-9a-f]{64}", record[k])
                       for k in ("profile_sha256", "installation_sha256", "clearance_review_sha256", "kinematic_review_sha256"))
                or record["primitive_geometry_sha256"] != {
                    pid:self.measured[spec["catalogue_id"]].geometry_sha256 for pid,spec in data["primitives"].items()}):
            raise ValueError("Bind accepted clearance/kinematic coverage to the exact current profile and every primitive.")
        self.profile_coverage = record
        if not self.routes:
            raise ValueError("At least one complete released physical recipe is required.")
        for context in data["contexts"].values():
            pose = context.get("pose_base")
            if (not isinstance(pose, list) or len(pose) != 6
                    or not all(type(v) in (int, float) and math.isfinite(v) for v in pose)
                    or type(context.get("tool_clear")) is not bool):
                raise ValueError("Contexts need literal finite BASE poses and a reviewed clearance declaration.")

    def _ensure_ports(self):
        if self.ports is None:
            root = Path(self.config["journal_root"])
            if not root.is_absolute():
                raise ValueError("The private journal root must be absolute.")
            self.journal = self.journal_factory(root)
            self.ports = self.port_factory(adapter=self.coordinate_binding, journal=self.journal, **self.config["ports"])
            if hasattr(self.ports, "api"):
                self.ports.api = _StopAwareAPI(self.ports.api, self.stop_latch, self._validate_profile)

    def _validate_profile(self, status):
        if (content_hash(status["receiver"].get("profile")) != self.profile_coverage["profile_sha256"]
                or content_hash(status["installation"]) != self.profile_coverage["installation_sha256"]):
            raise ExecutionBlocked("CURRENT_PROFILE_NOT_REVIEWED", "The current profile/installation differs from whole-route coverage evidence.")

    def _preflight_profile(self, status):
        """Pure hypothetical segment admission, never pose publication or IK IO.

        This supplements the explicit swept-clearance/kinematic evidence. It
        cannot turn a numerical bound check into physical clearance proof.
        """
        self._validate_profile(status)
        if self._profile_preflight_done:
            return
        for pid, spec in self.config["primitives"].items():
            measured = self.measured[spec["catalogue_id"]]
            for stage in measured.stages:
                receiver = {**status["receiver"], "actual_pose": list(stage.start_base)}
                command = {"kind": "rotate" if stage.phase == "wrist" else "translate",
                    "purpose": "contact_turn_trial" if status["installation"]["scope"] == "local_contact_turn_commissioning" else "contact_trial",
                    "installation_id": self.binding.installation_id,
                    "expected_receiver": {k:receiver[k] for k in ("session_id", "seq", "profile_id")},
                    "target": list(stage.target_base), "expected_visual": measured.expected_visual}
                if stage.phase == "wrist":
                    wrist = spec["wrist"]
                    receiver["actual_joint"] = list(wrist["expected_source_joint_deg"])
                    command["edge_id"] = wrist["edge_id"]
                    profile = receiver["profile"]
                    edges = [e for e in profile.get("rotation_edges", ()) if e["id"] == wrist["edge_id"]]
                    if (len(edges) != 1 or content_hash(profile.get("rotation_runtime")) != wrist["rotation_runtime_sha256"]
                            or edges[0]["expected_source_joint_deg"] != wrist["expected_source_joint_deg"]
                            or edges[0]["expected_target_joint_deg"] != wrist["expected_target_joint_deg"]):
                        raise ExecutionBlocked("PROFILE_ROUTE_COVERAGE_FAILED", "The current directed wrist/runtime does not cover " + pid)
                try:
                    admit(command, status["installation"], receiver, None, armed=True,
                          now=self.ports.now(), require_profile_binding=True, held=False)
                except GuardError as error:
                    raise ExecutionBlocked("PROFILE_ROUTE_COVERAGE_FAILED", pid + "/" + stage.id + ": " + error.code) from error
        self._profile_preflight_done = True

    def readiness(self):
        result = {"ready": False, "configured": False, "connected": False,
                  "stationary": False, "at_start": False, "destinations": [], "reasons": []}
        if self._configuration_error:
            result["reasons"].append("PHYSICAL_CONFIGURATION_INVALID")
            result["detail"] = self._configuration_error
            return result
        if not self.config["enabled"]:
            result["reasons"].append("PHYSICAL_DRIVER_DISABLED")
            return result
        result["configured"] = True
        if self.observer_callback is None:
            result["reasons"].append("QUALIFIED_OBSERVER_REQUIRED")
            return result
        observer_readiness = getattr(self.observer_callback, "readiness", None)
        if not callable(observer_readiness):
            result["reasons"].append("EXECUTABLE_MEASUREMENT_ADAPTER_REQUIRED")
            return result
        try:
            observation_status = observer_readiness(self.config)
            if not isinstance(observation_status, dict) or observation_status.get("ready") is not True:
                reasons = observation_status.get("blockers", []) if isinstance(observation_status, dict) else []
                result["reasons"].extend(reasons or ["EXECUTABLE_MEASUREMENT_ADAPTER_REQUIRED"])
                return result
        except Exception:
            result["reasons"].append("MEASUREMENT_ADAPTER_UNAVAILABLE")
            return result
        try:
            self._ensure_ports()
            # One held status read, never an independent second Native owner.
            status = self.ports._status()
            self._preflight_profile(status)
            receiver = status["receiver"]
            identity_ok = status["installation"]["installation_id"] == self.binding.installation_id
            actual = tuple(receiver["actual_pose"])
            starts = {p.start_context_id for _, p in self.routes}
            start_matches = [name for name in starts if self._matches(actual, name)]
            result.update(connected=True, stationary=True, at_start=bool(start_matches))
            result["destinations"] = [p.destination for _, p in self.routes if p.start_context_id in start_matches]
            if not identity_ok:
                result["reasons"].append("INSTALLATION_CHANGED")
            if not start_matches:
                result["reasons"].append("ROBOT_NOT_AT_START")
            if self.pending_command_id:
                result["reasons"].append("COMMAND_OUTCOME_UNRESOLVED")
            result["ready"] = not result["reasons"]
        except Exception as error:
            result["reasons"].append(error.code if isinstance(error, ExecutionBlocked) else "PHYSICAL_STATUS_UNAVAILABLE")
        return result

    def _matches(self, actual, context_id):
        target = self.config["contexts"][context_id]["pose_base"]
        return all(abs(a-b) <= .100000001 for a, b in zip(actual, target))

    def _snapshot(self):
        status = self.ports._status()
        self._validate_profile(status)
        snapshot = checked_snapshot(self.ports, self.coordinate_binding, 5.)
        if (snapshot.session_id, snapshot.sequence, snapshot.profile_id) != tuple(
                status["receiver"][key] for key in ("session_id", "seq", "profile_id")):
            raise ExecutionBlocked("PROFILE_NATIVE_BASELINE_CHANGED", "The receiver baseline changed during the current-profile check.")
        if snapshot.installation_id != self.binding.installation_id:
            raise ExecutionBlocked("INSTALLATION_CHANGED", "The physical installation binding changed.")
        self.last_snapshot = snapshot
        return snapshot

    def prepare(self, workspace_binding):
        if not self.execution_lock.acquire(blocking=False):
            raise ExecutionBlocked("MISSION_BUSY", "A physical operation is already active.")
        try:
            with self._stop_lock:
                stop_generation = self._stop_generation
            ready = self.readiness()
            if not ready["ready"]:
                raise ExecutionBlocked("MISSION_NOT_READY", ";".join(ready["reasons"]))
            if not isinstance(workspace_binding, dict) or any(k not in workspace_binding for k in
                    (*WORKSPACE_KEYS, "workspace_session_id", "plan_id", "plan_revision")):
                raise ValueError("Bind the exact approved workspace plan and map route.")
            matches = [p for key, p in self.routes if all(workspace_binding[k] == key[k] for k in WORKSPACE_KEYS)]
            if len(matches) != 1:
                raise ExecutionBlocked("ROUTE_NOT_RELEASED", "No single released physical recipe matches this exact route.")
            plan = replace(matches[0], id="physical-mission-" + uuid4().hex)
            snapshot = self._snapshot()
            if not self._matches(snapshot.tcp_base, plan.start_context_id):
                raise ExecutionBlocked("ROBOT_NOT_AT_START", "A fresh Native source must match the fixed start.")
            self.currentplan = self.plan = plan
            self.current_context_id = plan.start_context_id
            self.workspace_binding = dict(workspace_binding)
            self.pending_command_id = None
            self.before_frame = None
            self.journal.append("physical_mission_prepared", {"mission_id": plan.id,
                "workspace_binding": self.workspace_binding, "native": asdict(snapshot), "automatic_replay": False})
            with self._stop_lock:
                if self._stop_generation != stop_generation:
                    raise ExecutionBlocked("MISSION_STOPPED", "Stop during preparation cannot be cleared by that preparation.")
                self.stop_latch.clear()
            return plan
        finally:
            self.execution_lock.release()

    def context(self):
        if self.currentplan is None:
            raise ExecutionBlocked("MISSION_NOT_PREPARED", "Prepare a new explicit mission first.")
        snapshot = self._snapshot()
        match = self.current_context_id and self._matches(snapshot.tcp_base, self.current_context_id)
        fault = "MISSION_STOPPED" if self.stop_latch.is_set() else None
        if not match:
            fault = "PHYSICAL_CONTEXT_CHANGED"
        return RuntimeContext(self.ports.now(), self.binding, snapshot.session_id, snapshot.sequence,
            snapshot.native_observed_at, self.current_context_id or "UNBOUND", snapshot.held_disarmed_idle,
            bool(match and self.config["contexts"][self.current_context_id]["tool_clear"]),
            self.pending_command_id, fault)

    def capture(self):
        return checked_frame(self.ports, 2.)

    def observe(self, state):
        if self.currentplan is None or self.observer_callback is None:
            raise ExecutionBlocked("OBSERVER_UNAVAILABLE", "The qualified mission observer is unavailable.")
        if self.stop_latch.is_set():
            raise ExecutionBlocked("MISSION_STOPPED", "No new automatic operation after Stop.")
        return self.observer_callback(state, self)

    def _not_stopped(self):
        if self.stop_latch.is_set():
            raise ExecutionBlocked("MISSION_STOPPED", "No subsequent stage may arm after Stop.")

    def execute(self, primitive_id, command_id):
        if not self.execution_lock.acquire(blocking=False):
            raise ExecutionBlocked("MISSION_BUSY", "Only one physical primitive may execute.")
        dispatched = False
        try:
            self._not_stopped()
            if self.currentplan is None or not isinstance(command_id, str) or not 1 <= len(command_id) <= 200:
                raise ValueError("Use a prepared mission and a new bounded command identity.")
            allowed = {p.id: p for p in _plan_primitives(self.currentplan)}
            policy_primitive = allowed[primitive_id]
            spec = self.config["primitives"][primitive_id]
            measured = self.measured[spec["catalogue_id"]]
            qualification = self.qualifications[primitive_id]
            if self.current_context_id != policy_primitive.source_context_id:
                raise ExecutionBlocked("PRIMITIVE_SOURCE_MISMATCH", "The current measured context does not match this primitive.")
            current = self._snapshot()
            if not self._matches(current.tcp_base, self.current_context_id):
                raise ExecutionBlocked("PHYSICAL_CONTEXT_CHANGED", "Reconcile a source change before any motion.")
            if command_id in self.issued:
                raise ExecutionBlocked("COMMAND_ALREADY_USED", "A logical command may never be replayed.")
            marker = Path(self.config["journal_root"]) / ("dispatch-" + hashlib.sha256(command_id.encode()).hexdigest() + ".private.json")
            write_new(marker, json.dumps({"command_id": command_id, "primitive_id": primitive_id,
                "mission_id": self.currentplan.id, "automatic_replay": False}).encode())
            self.issued.add(command_id)
            self.pending_command_id = command_id
            if any(s.phase == "contact" for s in measured.stages):
                self.before_frame = self.capture()
            baseline = self._snapshot()
            if (baseline.session_id, baseline.sequence, baseline.profile_id, baseline.tcp_base) != (
                    current.session_id, current.sequence, current.profile_id, current.tcp_base) or any(
                    abs(a-b) > .100000001 for a, b in zip(baseline.joints_deg, current.joints_deg)):
                raise ExecutionBlocked("PRIMITIVE_SOURCE_CHANGED", "The source changed during the before observation.")
            self.journal.append("mission_primitive_intent", {"command_id": command_id,
                "primitive_id": primitive_id, "geometry_sha256": measured.geometry_sha256,
                "native_before": asdict(baseline), "approach_vision_gate": False})
            for index, stage in enumerate(measured.stages):
                self._not_stopped()
                fresh = self._snapshot()
                if (fresh.session_id, fresh.sequence, fresh.profile_id, fresh.tcp_base) != (
                        current.session_id, current.sequence, current.profile_id, current.tcp_base) or any(
                        abs(a-b) > .100000001 for a, b in zip(fresh.joints_deg, current.joints_deg)):
                    raise ExecutionBlocked("PRIMITIVE_BASELINE_CHANGED", "The Native source changed between measured stages.")
                if any(abs(a-b) > .100000001 for a, b in zip(fresh.tcp_base, stage.start_base)):
                    raise ExecutionBlocked("MEASURED_STAGE_SOURCE", "The current pose differs from the stored stage source.")
                wrist = spec.get("wrist") if stage.phase == "wrist" else None
                if wrist is None:
                    if (fresh.tcp_base[2:] != stage.target_base[2:]
                            or math.dist(fresh.tcp_base[:2], stage.target_base[:2]) > fresh.configured_stroke_mm):
                        raise ExecutionBlocked("FIXED_POSE_OR_STEP_LIMIT", "Preserve the current literal Z/Euler and step cap.")
                else:
                    self._validate_wrist(fresh, stage, wrist)
                intent = MotionIntent(str(uuid4()), self.currentplan.id, self.workspace_binding["plan_revision"],
                    measured.source, measured.target,
                    {"session_id": fresh.session_id, "seq": fresh.sequence, "profile_id": fresh.profile_id},
                    fresh.installation_id, fresh.tcp_base, stage.target_base, qualification.review_sha256, {},
                    kind="rotate" if wrist else "translate",
                    purpose="contact_turn_trial" if fresh.scope == "local_contact_turn_commissioning" else "contact_trial",
                    edge_id=wrist["edge_id"] if wrist else None, expected_visual=measured.expected_visual,
                    expected_source_joint_deg=tuple(wrist["expected_source_joint_deg"]) if wrist else None,
                    expected_target_joint_deg=tuple(wrist["expected_target_joint_deg"]) if wrist else None,
                    rotation_runtime_sha256=wrist["rotation_runtime_sha256"] if wrist else None)
                self.journal.append("mission_stage_intent", {"command_id": command_id, "stage_index": index,
                    "stage_id": stage.id, "phase": stage.phase, "intent": asdict(intent), "native_before": asdict(fresh)})
                self.journal.checkpoint({"state": "DISPATCH_UNRESOLVED", "command_id": command_id,
                    "request_id": intent.request_id, "stage_index": index, "automatic_replay": False})
                self._not_stopped()
                dispatched = True
                receipt = self.ports.execute_once(intent)
                self.ports.hold("Verify this exact endpoint before another measured stage.")
                if (receipt.request_id != intent.request_id or not receipt.endpoint_verified
                        or not re.fullmatch(r"[0-9a-f]{64}", receipt.receipt_sha256)
                        or (receipt.session_id, receipt.sequence, receipt.profile_id, receipt.installation_id, tuple(receipt.target_base)) !=
                            (fresh.session_id, fresh.sequence + 1, fresh.profile_id, fresh.installation_id, stage.target_base)):
                    raise ExecutionBlocked("MISSION_RECEIPT_MISMATCH", "The exact one-shot endpoint receipt did not verify.")
                actual = self._snapshot()
                if (actual.session_id, actual.sequence, actual.profile_id, actual.tcp_base) != (
                        receipt.session_id, receipt.sequence, receipt.profile_id, stage.target_base):
                    raise ExecutionBlocked("MISSION_NATIVE_ENDPOINT", "Fresh independent Native proof must confirm the receipt.")
                if wrist and any(abs(a-b) > .5 for a, b in zip(actual.joints_deg, wrist["expected_target_joint_deg"])):
                    raise ExecutionBlocked("MISSION_WRIST_ENDPOINT", "Actual wrist joints differ from the directed measured target.")
                self.journal.append("mission_stage_endpoint", {"command_id": command_id, "stage_index": index,
                    "receipt": asdict(receipt), "native_after": asdict(actual)})
                current = actual
            self.current_context_id = policy_primitive.target_context_id
            self.pending_command_id = None
            result = MotionReceipt(command_id, primitive_id, current.session_id,
                self.current_context_id, self.ports.now(), True, "COMPLETED")
            self.journal.append("mission_primitive_complete", {"receipt": asdict(result), "car_outcome_inferred": False})
            self.journal.checkpoint({"state": "STATIONARY_COMMAND_COMPLETE", "receipt": asdict(result), "automatic_replay": False})
            return result
        except Exception as error:
            self.stop_latch.set()
            if self.ports:
                try:
                    self.ports.hold("Physical mission stopped; no replay after source, control or endpoint uncertainty.")
                except Exception:
                    pass
            if self.journal:
                self.journal.append("mission_primitive_failed", {"command_id": command_id, "primitive_id": primitive_id,
                    "error_code": error.code if isinstance(error, ExecutionBlocked) else type(error).__name__,
                    "outcome_unknown": dispatched, "automatic_replay": False})
            raise
        finally:
            self.execution_lock.release()

    @staticmethod
    def _validate_wrist(snapshot, stage, wrist):
        edges = [e for e in snapshot.reviewed_rotation_edges if e["id"] == wrist["edge_id"]]
        if (len(edges) != 1 or snapshot.rotation_runtime_sha256 != wrist["rotation_runtime_sha256"]
                or tuple(edges[0]["expected_source_joint_deg"]) != tuple(wrist["expected_source_joint_deg"])
                or tuple(edges[0]["expected_target_joint_deg"]) != tuple(wrist["expected_target_joint_deg"])
                or tuple(edges[0]["source_orientation_deg"]) != stage.start_base[3:]
                or tuple(edges[0]["target_orientation_deg"]) != stage.target_base[3:]
                or any(abs(a-b) > .5 for a, b in zip(snapshot.joints_deg, wrist["expected_source_joint_deg"]))
                or math.dist(snapshot.tcp_base[:3], stage.target_base[:3]) > .1):
            raise ExecutionBlocked("MISSION_WRIST_SOURCE", "Use the actual installed directed wrist edge and source joints.")

    def hold(self, reason):
        # A concurrent prepare cannot clear a Stop that arrived after it began.
        with self._stop_lock:
            self._stop_generation += 1
            self.stop_latch.set()  # Before any possibly blocking network operation.
        if self.ports:
            return self.ports.hold(reason)

    def close(self):
        self.hold("Physical mission driver closed; no automatic resume.")
        if self.journal:
            self.journal.close()
