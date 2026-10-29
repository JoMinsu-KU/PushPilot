"""Explicit current-site delivery trials over the original guarded transport.

This release mode preserves historical provenance and labels new connections as
trials. It never invents repeatability qualification. Each exact unit receives
a fresh, narrow profile/IK preparation; policy, Native endpoint, MUSE, signal,
stop and no-replay checks remain independent.
"""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

from .coordinate_units import CoordinateBinding, CoordinateStage, CoordinateUnit
from .legacy import load_runtime
from .mission_catalog import EvidenceReference, MeasuredPrimitive, MeasuredStage, content_hash
from .mission_driver import ConfigBackedMissionDriver, WORKSPACE_KEYS, _reference, _StopAwareAPI, _plan_primitives, plan_from_dict
from .mission_policy import SiteBinding
from .mission_profile import ReviewedProfilePreparer, resolve_wrist_descriptor, validate_site_review
from .taught_executor import ExecutionBlocked, checked_snapshot
from tools.build_delivery_release import policy_plan


def packet_primitive(row, packet_reference):
    """The packet is a geometry source, never an invented original receipt."""
    evidence = EvidenceReference(packet_reference["path"], row["id"], packet_reference["sha256"])
    stages = tuple(MeasuredStage(s["id"], s["phase"], tuple(s["start_base"]), tuple(s["target_base"]),
        "geometry-stage-" + str(i), evidence) for i, s in enumerate(row["stages"]))
    return MeasuredPrimitive(row["id"], row["kind"], stages, row["source_context_id"],
        row["target_context_id"], row["expected_visual"], "MISSING", False, (evidence,),
        ("CURRENT_SITE_TRIAL_NOT_REPEATABILITY_QUALIFIED",),
        contact_travel_limit_mm=row.get("contact_travel_limit_mm", 20.))


class SiteTrialMissionDriver(ConfigBackedMissionDriver):
    def _load(self):
        raw_config = self.config_file.read_bytes()
        data = json.loads(raw_config)
        required = {"schema", "enabled", "site_binding", "coordinate_binding", "ports", "journal_root",
                    "packet", "profile_review", "workspace_bindings", "measurement_adapter", "observations", "wrist_intents"}
        if set(data) != required or data["schema"] != "pushpilot.site-trial-driver.v1" or type(data["enabled"]) is not bool:
            raise ValueError("Use the explicit current-site delivery trial configuration.")
        self.config = data
        self.binding = SiteBinding(**data["site_binding"])
        self.coordinate_binding = CoordinateBinding(**data["coordinate_binding"])
        self.observation_config = data["observations"]
        if (data["ports"].get("native_observation_source") != "host_journal"
                or self.coordinate_binding.map_hash != self.binding.map_sha256
                or self.coordinate_binding.car_id != self.binding.car_id
                or self.coordinate_binding.tool_id != self.binding.tool_id
                or data["ports"]["registration_id"] != self.binding.calibration_id
                or data["ports"]["camera_epoch"] != self.binding.camera_epoch):
            raise ValueError("Bind the actual current site, tool, car and fixed camera.")
        packet = _reference(data["packet"], self.config_file.parent)
        if packet["schema"] != "pushpilot.current-site-delivery-packet.v1" or packet["repeatability_qualified"] is not False:
            raise ValueError("A trial packet must preserve its unqualified provenance.")
        self.profile_review = validate_site_review(_reference(data["profile_review"], self.config_file.parent))
        self.review_sha = content_hash(self.profile_review)
        if (not Path(data["journal_root"]).is_absolute()
                or any(self.profile_review["site"][key] != getattr(self.coordinate_binding, key)
                       for key in ("tcp_definition_sha256", "tool_id", "car_id", "surface_id"))):
            raise ValueError("The current-site review, coordinate adapter and absolute private journal must agree.")
        if set(packet.get("blockers", ())) & {"UNRESOLVED_LITERAL_SOURCE_CONTEXT_JOIN", "EXPLICIT_FIXED_Z_POSTURE_BINDING_REQUIRED"}:
            raise ValueError("Resolve literal source/posture joins before enabling a site trial.")
        self.measured = {pid: packet_primitive(row, data["packet"]) for pid, row in packet["primitives"].items()}
        self.config["contexts"] = packet["contexts"]
        for context in self.config["contexts"].values():
            pose = context.get("pose_base")
            if (not isinstance(pose, list) or len(pose) != 6
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in pose)
                    or type(context.get("tool_clear")) is not bool):
                raise ValueError("Contexts require finite literal poses and explicit clearance states.")
        self.config["primitives"] = {}
        self.qualifications = {}
        for pid, measured in self.measured.items():
            row = packet["primitives"][pid]
            if pid != measured.id or type(row.get("empty_tool")) is not bool:
                raise ValueError("Each packet primitive needs a consistent ID and explicit empty-tool state.")
            if measured.geometry_sha256 not in self.profile_review["allowed_geometry_sha256"]:
                raise ValueError("The explicit site review must cover every runtime geometry.")
            if (tuple(self.config["contexts"][row["source_context_id"]]["pose_base"]) != measured.stages[0].start_base
                    or tuple(self.config["contexts"][row["target_context_id"]]["pose_base"]) != measured.stages[-1].target_base):
                raise ValueError("Context coordinates differ from the exact reviewed primitive geometry.")
            has_contact = any(s.phase == "contact" for s in measured.stages)
            if row["empty_tool"] and has_contact or measured.kind == "wrist_edge" and not row["empty_tool"]:
                raise ValueError("Loaded contacts and unloaded wrist/return geometry cannot be relabelled.")
            if has_contact:
                CoordinateUnit("site-validation", "site-plan", 1, measured.source, measured.target,
                    self.binding.installation_id, "pending-profile", tuple(CoordinateStage(
                        s.id, s.phase, s.start_base, s.target_base, self.review_sha) for s in measured.stages),
                    measured.expected_visual, contact_travel_limit_mm=measured.contact_travel_limit_mm)
            if measured.kind == "wrist_edge":
                intent = data["wrist_intents"].get(pid)
                # Geometry and directed intent are static; actual joint winding
                # is resolved again from fresh Native data before execution.
                resolve_wrist_descriptor(measured, self.profile_review, measured.stages[0].start_base,
                                         [0.]*6, intent)
            elif pid in data["wrist_intents"]:
                raise ValueError("A wrist intent cannot be attached to a translation unit.")
            self.config["primitives"][pid] = {"catalogue_id": pid,
                "source_context_id": row["source_context_id"], "target_context_id": row["target_context_id"]}
            # Parent execution consumes this review reference only. It is not a
            # PrimitiveQualification and carries no physical-release boolean.
            self.qualifications[pid] = SimpleNamespace(review_sha256=self.review_sha)
        self.routes = []
        self.config["routes"] = []
        for code, route in packet["routes"].items():
            if route.get("blockers"):
                raise ValueError("Resolve explicit geometry discontinuities before a site trial.")
            workspace = data["workspace_bindings"][code]
            if (set(workspace) != set(WORKSPACE_KEYS) or workspace["destination"] != route["destination"]
                    or (workspace["map_id"], workspace["map_version"], workspace["map_hash"]) !=
                        (self.coordinate_binding.map_id, self.coordinate_binding.map_version, self.binding.map_sha256)):
                raise ValueError("Bind the exact current symbolic destination and route.")
            raw = policy_plan(packet, code, data["site_binding"], self.review_sha, plan_id="site-trial-"+code)
            for step in raw["steps"]:
                if step["primitive"]["empty_tool"] and not step.get("signal_gate") and not step["at_goal"]:
                    step["observation_required"] = False
            plan = plan_from_dict(raw)
            for primitive in _plan_primitives(plan):
                row = packet["primitives"][primitive.id]
                if (primitive.qualified or primitive.release_mode != "site_trial"
                        or primitive.current_site_review_sha256 != self.review_sha
                        or (primitive.source_context_id, primitive.target_context_id, primitive.empty_tool) !=
                            (row["source_context_id"], row["target_context_id"], row["empty_tool"])):
                    raise ValueError("Every policy action must retain its reviewed site-trial geometry and state.")
            self.routes.append((workspace, plan))
            self.config["routes"].append({"workspace_binding": workspace, "plan": raw})
        if not self.routes or set(data["workspace_bindings"]) != set(packet["routes"]):
            raise ValueError("Bind every available route exactly once.")
        if set(data["wrist_intents"]) != {pid for pid, p in self.measured.items() if p.kind == "wrist_edge"}:
            raise ValueError("Provide exactly one reviewed directed intent per wrist primitive.")
        self.actual_installation_id = None
        self.pinned_profile_sha256 = self.pinned_installation_sha256 = None
        self._preparing_profile = False
        self.profile_preparer = None
        self._loaded_config_sha256 = hashlib.sha256(raw_config).hexdigest()

    def _reload_before_first_mission(self):
        """Accept a complete revised deployment only before a mission exists.

        Display registration may acquire a new identity after the web starts.
        An explicitly updated private deployment can bind it without restarting
        the web again. Active/stopped missions retain their original binding.
        This never clears Stop, replays a journal, arms, or touches services.
        """
        digest = hashlib.sha256(self.config_file.read_bytes()).hexdigest()
        if digest == getattr(self, "_loaded_config_sha256", None):
            return
        if self.currentplan is not None or self.pending_command_id or getattr(self, "_preparing_profile", False):
            return
        if getattr(self, "profile_preparer", None) is not None and self.profile_preparer.failed:
            raise ExecutionBlocked("SITE_TRIAL_RECONCILIATION_REQUIRED", "A failed preparation cannot be replaced by config reload.")
        if not self.execution_lock.acquire(blocking=False):
            raise ExecutionBlocked("CONFIGURATION_RELOAD_PENDING", "Refresh the complete deployment before starting a new mission.")
        temporary = None
        try:
            journal = self.journal
            if journal is None and getattr(self, "_loaded_config_sha256", None) is not None:
                old_root = Path(self.config["journal_root"])
                if old_root.exists():
                    temporary = journal = self.journal_factory(old_root)
            previous = journal.load() if journal else None
            if previous and previous.get("state") not in {"STATIONARY_COMMAND_COMPLETE", "PROFILE_PREPARATION_COMPLETE"}:
                raise ExecutionBlocked("SITE_TRIAL_RECONCILIATION_REQUIRED", "An unresolved journal prohibits deployment replacement.")
            if self.journal:
                self.journal.close()  # Release file ownership only; no device IO.
            self.ports = self.journal = self.profile_preparer = None
            self.raw_api = None
            try:
                self._load()
                self._configuration_error = None
            except Exception as error:
                self._configuration_error = type(error).__name__ + ": " + str(error)
        finally:
            if temporary:
                temporary.close()
            self.execution_lock.release()

    def prepare(self, workspace_binding):
        self._reload_before_first_mission()
        return super().prepare(workspace_binding)

    def _pin(self, status):
        self.actual_installation_id = status["installation"]["installation_id"]
        self.pinned_profile_sha256 = content_hash(status["receiver"]["profile"])
        self.pinned_installation_sha256 = content_hash(status["installation"])

    def _validate_profile(self, status):
        if self._preparing_profile:
            return
        if self.pinned_profile_sha256 is not None and (
            content_hash(status["receiver"]["profile"]) != self.pinned_profile_sha256
            or content_hash(status["installation"]) != self.pinned_installation_sha256):
            raise ExecutionBlocked("CURRENT_PROFILE_CHANGED", "Reconcile an external profile or installation change.")

    def _ensure_ports(self):
        if self.ports is not None:
            return
        journal = self.journal_factory(Path(self.config["journal_root"]))
        try:
            previous = journal.load()
            if previous and previous.get("state") in {"DISPATCH_UNRESOLVED", "PROFILE_PREPARATION_UNRESOLVED", "PROFILE_PREPARATION_FAILED"}:
                raise ExecutionBlocked("SITE_TRIAL_RECONCILIATION_REQUIRED", "An unresolved prior operation cannot be resumed or replayed.")
            ports = self.port_factory(adapter=self.coordinate_binding, journal=journal, **self.config["ports"])
            raw_api = ports.api
            ports.api = _StopAwareAPI(raw_api, self.stop_latch, self._validate_profile)
            policy = load_runtime(Path(self.config["ports"]["runtime"]))["policy"]
            preparer = ReviewedProfilePreparer(api=lambda path, payload=None: raw_api.call(path, payload),
                journal=journal, native_snapshot=lambda: checked_snapshot(ports, self.coordinate_binding, 5.),
                receiver_policy=policy, stop_check=self._not_stopped)
        except Exception:
            journal.close()
            raise
        self.journal, self.ports, self.raw_api, self.profile_preparer = journal, ports, raw_api, preparer

    def readiness(self):
        result = {"ready": False, "configured": False, "connected": False, "stationary": False, "at_start": False,
            "destinations": [], "reasons": [], "capabilities": {"release_mode": "site_trial", "parking_alignment": False}}
        try:
            self._reload_before_first_mission()
        except Exception as error:
            result["reasons"] = [getattr(error, "code", "PHYSICAL_CONFIGURATION_UNAVAILABLE")]
            result["detail"] = type(error).__name__ + ": " + str(error)
            return result
        if self._configuration_error:
            result["reasons"] = ["PHYSICAL_CONFIGURATION_INVALID"]
            result["detail"] = self._configuration_error
            return result
        if not self.config["enabled"]:
            result["reasons"] = ["PHYSICAL_DRIVER_DISABLED"]
            return result
        result["configured"] = True
        try:
            observer_ready = getattr(self.observer_callback, "readiness", None)
            if not callable(observer_ready):
                result["reasons"] = ["EXECUTABLE_MEASUREMENT_ADAPTER_REQUIRED"]
                return result
            observed = observer_ready(self.config)
            if not isinstance(observed, dict) or observed.get("ready") is not True:
                result["reasons"] = observed.get("blockers", []) if isinstance(observed, dict) else []
                result["reasons"] = result["reasons"] or ["EXECUTABLE_MEASUREMENT_ADAPTER_REQUIRED"]
                return result
            self._ensure_ports()
            if self.profile_preparer.failed:
                raise ExecutionBlocked("SITE_TRIAL_RECONCILIATION_REQUIRED", "A failed preparation cannot advertise another automatic trial.")
            status = self.ports._status()
            self._validate_profile(status)
            self.ports._camera_status()
            if self.pinned_profile_sha256 is None:
                self._pin(status)
            site = self.profile_review["site"]
            if any(status["installation"].get(k) != v for k, v in site.items()):
                raise ExecutionBlocked("SITE_IDENTITY_CHANGED", "Current tool, height or site differs from review.")
            if (status["receiver"].get("profile_pending") or
                    status["receiver"].get("reason") == "RECEIVER_RECONCILIATION_REQUIRED"):
                raise ExecutionBlocked("SITE_TRIAL_RECONCILIATION_REQUIRED", "Resolve the receiver's existing pending operation first.")
            matches = [plan for _, plan in self.routes if self._matches(status["receiver"]["actual_pose"], plan.start_context_id)]
            result.update(connected=True, stationary=True, at_start=bool(matches),
                destinations=[plan.destination for plan in matches])
            if not matches:
                result["reasons"].append("ROBOT_NOT_AT_START")
            if self.pending_command_id:
                result["reasons"].append("COMMAND_OUTCOME_UNRESOLVED")
            result["ready"] = not result["reasons"]
        except Exception as error:
            result["reasons"].append(getattr(error, "code", "PHYSICAL_STATUS_UNAVAILABLE"))
            result["detail"] = type(error).__name__ + ": " + str(error)
        return result

    def _snapshot(self):
        status = self.ports._status()
        self._validate_profile(status)
        snapshot = checked_snapshot(self.ports, self.coordinate_binding, 5.)
        if ((snapshot.session_id, snapshot.sequence, snapshot.profile_id) != tuple(
                status["receiver"][k] for k in ("session_id", "seq", "profile_id"))
                or snapshot.installation_id != self.actual_installation_id):
            raise ExecutionBlocked("PHYSICAL_BASELINE_CHANGED", "The actual current receiver/profile changed.")
        self.last_snapshot = snapshot
        return snapshot

    def _prepare_measured(self, primitive_id, command_id):
        self._not_stopped()
        marker = Path(self.config["journal_root"]) / ("dispatch-" + hashlib.sha256(command_id.encode()).hexdigest() + ".private.json")
        if command_id in self.issued or marker.exists() or self.pending_command_id:
            raise ExecutionBlocked("COMMAND_ALREADY_USED", "No preparation or command replay after a used or unresolved operation.")
        if self.profile_preparer.failed:
            raise ExecutionBlocked("SITE_TRIAL_RECONCILIATION_REQUIRED", "Reconcile the failed profile preparation first.")
        measured = self.measured[primitive_id]
        current = self._snapshot()
        if current.tcp_base != measured.stages[0].start_base:
            raise ExecutionBlocked("EXACT_SITE_TRIAL_SOURCE_REQUIRED", "No guessed translation or posture rebasing at runtime.")
        expected = {"session_id": current.session_id, "seq": current.sequence, "profile_id": current.profile_id}
        self._preparing_profile = True
        try:
            result = self.profile_preparer.prepare(measured, self.profile_review, expected,
                operation_id=command_id, wrist=self.config["wrist_intents"].get(primitive_id))
            self._pin(result["status"])
            wrist = result.get("wrist")
            if wrist:
                self.config["primitives"][primitive_id]["wrist"] = {
                    "edge_id": wrist["edge_id"], "expected_source_joint_deg": wrist["expected_source_joint_deg"],
                    "expected_target_joint_deg": wrist["expected_target_joint_deg"],
                    "rotation_runtime_sha256": content_hash(result["profile"]["rotation_runtime"])}
        finally:
            self._preparing_profile = False


def configured_driver(path, observer_callback):
    schema = json.loads(Path(path).read_bytes()).get("schema")
    cls = SiteTrialMissionDriver if schema == "pushpilot.site-trial-driver.v1" else ConfigBackedMissionDriver
    return cls(path, observer_callback=observer_callback)
