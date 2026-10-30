"""Explicit current-site delivery trials over the original guarded transport.

This release mode preserves historical provenance and labels new connections as
trials. It never invents repeatability qualification. Each exact unit receives
a fresh, narrow profile/IK preparation; policy, Native endpoint, MUSE, signal,
stop and no-replay checks remain independent.
"""
from dataclasses import asdict, replace
from copy import deepcopy
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
        review_modes = self.observation_config.get("route_review_modes", {})
        omit_c19 = self.observation_config.get('c19_native_endpoint_only', False)
        if type(omit_c19) is not bool:
            raise ValueError('C19 review omission must be an explicit boolean.')
        if not isinstance(review_modes, dict) or any(
                code != "C" or mode != "intermediate_progress" for code, mode in review_modes.items()):
            raise ValueError("Only C supports the explicit intermediate progress trial override.")
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
                if (review_modes.get(code) == "intermediate_progress"
                        and not step["primitive"]["empty_tool"] and not step["at_goal"]):
                    step["review_mode"] = "intermediate_progress"
                if omit_c19 and code == 'C' and step['id'] == 'C-step-19':
                    step['review_mode'] = 'operator_native_endpoint'
                    step['observation_required'] = False
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
        self._loaded_source_config = json.loads(raw_config)

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
            if previous and previous.get("state") not in {"STATIONARY_COMMAND_COMPLETE", "PROFILE_PREPARATION_COMPLETE",
                                                         "RECONCILED_STATIONARY_NO_MOTION", "MISSION_RETIRED_AT_START"}:
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

    def resume_review(self, workspace, accepted_plan, held, completed, receipt, *, omit_c19_review=False):
        """Reconcile one completed visual-review hold without replaying its motion."""
        import asyncio
        from .mission_resume import (require, resume_candidate, read_chain,
                                     original_frame, review_continuity)
        from .mission_policy import MissionPolicy, DecisionKind
        from uuid import uuid4
        self._reload_before_first_mission()
        if not self.execution_lock.acquire(blocking=False):
            raise ExecutionBlocked('MISSION_BUSY', 'A physical operation is already active.')
        try:
            with self._stop_lock:
                stop_generation = self._stop_generation
            require(not self._configuration_error and self.config['enabled'], 'RESUME_CONFIGURATION_INVALID')
            require(self.currentplan is None or self.currentplan.id == held.mission_id, 'RESUME_MISSION_MISMATCH')
            require(self.pending_command_id is None, 'RESUME_DISPATCH_UNRESOLVED')
            candidates = [p for key, p in self.routes if all(workspace[k] == key[k] for k in WORKSPACE_KEYS)]
            require(len(candidates) == 1, 'RESUME_ROUTE_NOT_FOUND')
            plan, state = resume_candidate(accepted_plan, candidates[0], held, completed, receipt,
                                           omit_c19_review=omit_c19_review)
            readiness = self.observer_callback.readiness(self.config)
            require(readiness.get('ready') is True, 'RESUME_OBSERVER_UNAVAILABLE')
            self._ensure_ports()
            require(not self.profile_preparer.failed, 'RESUME_PREPARATION_UNRESOLVED')
            checkpoint = self.journal.load()
            require(checkpoint.get('state') == 'STATIONARY_COMMAND_COMPLETE'
                    and checkpoint.get('receipt') == receipt, 'RESUME_CHECKPOINT_CHANGED')
            root = Path(self.config['journal_root'])
            chain = read_chain(root/'events.private.jsonl')
            endings = [r for r in chain if r['kind'] == 'mission_primitive_complete']
            require(endings and endings[-1]['payload']['receipt'] == receipt, 'RESUME_JOURNAL_RECEIPT_MISMATCH')
            endpoints = [r for r in chain if r['kind'] == 'mission_stage_endpoint']
            require(endpoints and endpoints[-1]['payload']['command_id'] == state.action_command_id,
                    'RESUME_NATIVE_HISTORY_CHANGED')
            endpoint = endpoints[-1]['payload']
            historical = endpoint['native_after']
            intents = [r for r in chain if r['kind'] == 'mission_primitive_intent'
                       and r['payload']['command_id'] == state.action_command_id]
            measured = self.measured[receipt['primitive_id']]
            require(len(intents) == 1 and intents[0]['payload']['geometry_sha256'] == measured.geometry_sha256,
                    'RESUME_COMPLETED_GEOMETRY_CHANGED')
            marker = json.loads((root/('dispatch-'+hashlib.sha256(state.action_command_id.encode()).hexdigest()+'.private.json')).read_bytes())
            require(marker['mission_id'] == plan.id and marker['primitive_id'] == measured.id,
                    'RESUME_DISPATCH_IDENTITY_CHANGED')
            terminal = self.raw_api.call('/v1/commands/'+endpoint['receipt']['request_id'])
            require(terminal.get('state') == 'complete' and terminal.get('id') == endpoint['receipt']['request_id'],
                    'RESUME_TERMINAL_OUTCOME_UNCONFIRMED')
            status = self.ports._status()
            self._reset_stationary_status(status)
            for key, old_key in (('session_id','session_id'), ('seq','sequence'), ('profile_id','profile_id'),
                                 ('actual_pose','tcp_base'), ('actual_joint','joints_deg')):
                require(status['receiver'][key] == historical[old_key], 'RESUME_NATIVE_SOURCE_CHANGED')
            require(status['installation']['installation_id'] == historical['installation_id'],
                    'RESUME_INSTALLATION_CHANGED')
            self._pin(status)
            native = self._snapshot()
            require(native.sequence == historical['sequence'] and native.session_id == held.session_id
                    and list(native.tcp_base) == historical['tcp_base']
                    and self._matches(native.tcp_base, receipt['target_context_id']), 'RESUME_NATIVE_ENDPOINT_CHANGED')
            observations = []
            for path in root.glob('mission-observation-*.private.json'):
                value = json.loads(path.read_bytes())
                task = value.get('task', {})
                if task.get('mission_id') == plan.id and task.get('action_command_id') == state.action_command_id:
                    require(value['native_after']['native_sequence'] == native.sequence
                            and value['native_after']['session_id'] == native.session_id,
                            'RESUME_OBSERVATION_SOURCE_CHANGED')
                    observations.append(value)
            require(bool(observations), 'RESUME_OBSERVATION_HISTORY_MISSING')
            original = max(observations, key=lambda o:o['frame']['captured_at'])
            before, held_frame = (original_frame(root, original[key]) for key in ('reference','frame'))
            require(before.epoch == held_frame.epoch == plan.binding.camera_epoch
                    and before.sequence < held_frame.sequence
                    and before.captured_at < state.last_motion_completed_at_s <= held_frame.captured_at,
                    'RESUME_ORIGINAL_INTERVAL_INVALID')
            # A web restart may renew the registration ID, but never the matrix,
            # reference photo, epoch or map. Compare actual archived metadata.
            old_camera = None
            for path in root.glob('camera-metadata-*.private.json'):
                if abs(path.stat().st_mtime-held_frame.captured_at) > 30:
                    continue
                value = json.loads(path.read_bytes())
                if value.get('frame', {}).get('sha256') == held_frame.sha256:
                    old_camera = value; break
            camera = self.ports._camera_status()
            require(old_camera is not None and camera['epoch'] == old_camera['epoch']
                    and all(camera['registration'].get(k) == old_camera['registration'].get(k)
                            for k in ('homography','reference_frame_id')), 'RESUME_CAMERA_REFERENCE_CHANGED')
            current = self.capture()
            continuity = ({'review_omitted_by_operator': 'C-step-19', 'visual_continuity_verified': False}
                          if omit_c19_review else asyncio.run(review_continuity(self.observer_callback.provider, held_frame, current)))
            self.journal.artifact('resume-continuity', {'mission_id':plan.id, 'held_frame':held_frame.metadata(),
                'current':current.metadata(), 'result':continuity, 'native':asdict(native)})
            require(omit_c19_review or all(continuity[k] is True for k in ('car_visible_in_both','car_position_unchanged',
                    'car_orientation_unchanged','board_view_unchanged')) and continuity['clear_problem'] is False,
                    'RESUME_SCENE_CONTINUITY_UNCONFIRMED')
            fresh = self._snapshot()
            require((fresh.session_id,fresh.sequence,fresh.profile_id,fresh.tcp_base,fresh.joints_deg) ==
                    (native.session_id,native.sequence,native.profile_id,native.tcp_base,native.joints_deg),
                    'RESUME_SOURCE_CHANGED_DURING_REVIEW')
            require(hashlib.sha256(self.config_file.read_bytes()).hexdigest() == self._loaded_config_sha256,
                    'RESUME_CONFIGURATION_CHANGED')
            self.currentplan = self.plan = plan
            self.workspace_binding = dict(workspace)
            self.current_context_id = receipt['target_context_id']
            self.issued.update(state.issued_command_ids)
            self.before_frame = before
            self.last_contact_outcome = {'command_id':state.action_command_id, 'primitive_id':measured.id,
                                        'expected_visual':measured.expected_visual}
            with self._stop_lock:
                require(self._stop_generation == stop_generation, 'RESUME_STOPPED')
                self.stop_latch.clear()
            next_step_index = state.step_index + 1
            if omit_c19_review:
                from .mission_policy import Phase
                state = replace(state, phase=Phase.READY, step_index=next_step_index,
                                reobservations=0, reason='OPERATOR_OMITTED_C19_REVIEW')
                observation = {}  # No synthetic PASS or car measurement.
            else:
                observation = self.observe(state)  # No historical FAIL is relabelled.
            context = self.context()
            decision = MissionPolicy(plan).decide(state, context, car=observation.get('car'), command_id=uuid4().hex)
            require(decision.kind == DecisionKind.DISPATCH
                    and decision.primitive_id == plan.steps[next_step_index].primitive.id
                    and decision.state.pending_role == 'ROUTE', 'RESUME_PROGRESS_UNCONFIRMED')
            proof = {'mission_id':plan.id, 'completed_command_id':state.action_command_id,
                'native_sequence':context.native_sequence, 'next_step':plan.steps[next_step_index].id,
                'original_error':held.reason, 'old_binding':asdict(accepted_plan.binding),
                'binding':asdict(plan.binding), 'continuity':continuity,
                'fresh_review':asdict(observation['car']) if observation.get('car') else None,
                'review_omitted': 'C-step-19' if omit_c19_review else None,
                'motion_issued':False, 'command_replayed':False}
            self.journal.append('explicit_review_resume_prepared', proof)
            return plan, state, observation, proof
        except Exception:
            self.stop_latch.set()
            raise
        finally:
            self.execution_lock.release()

    def retire_at_start(self, mission_id, reason):
        """Explicit no-motion retirement; an old failure never becomes success.

        An external empty return may legitimately replace the pinned per-unit
        profile. Validate the current original guarded ports, site and fresh
        Native START first, then repin. No arm, dispatch, profile installation,
        command reconciliation or automatic return is performed here.
        """
        if not self.execution_lock.acquire(blocking=False):
            raise ExecutionBlocked("MISSION_BUSY", "An in-flight operation cannot be reset.")
        self.stop_latch.set()
        temporary = None
        probe = None
        original_api = None
        original_registration = None
        config_reloaded = False
        try:
            if self._configuration_error:
                raise ExecutionBlocked("PHYSICAL_CONFIGURATION_INVALID", self._configuration_error)
            if self.currentplan is not None and self.currentplan.id != mission_id:
                raise ExecutionBlocked("RESET_MISSION_MISMATCH", "Retire only the exact ended mission.")
            journal = self.journal
            if journal is None:
                temporary = journal = self.journal_factory(Path(self.config["journal_root"]))
            previous = journal.load()
            state = previous.get("state") if previous else None
            allowed = {None, "STATIONARY_COMMAND_COMPLETE", "PROFILE_PREPARATION_COMPLETE",
                       "RECONCILED_STATIONARY_NO_MOTION", "MISSION_RETIRED_AT_START", "DISPATCH_UNRESOLVED"}
            if state not in allowed or self.pending_command_id and state != "DISPATCH_UNRESOLVED":
                raise ExecutionBlocked("RESET_RECONCILIATION_REQUIRED", "Preserve and explicitly reconcile the unresolved preparation first.")
            candidate, candidate_sha = self._retirement_registration_candidate()
            registration = (candidate or self._loaded_source_config)["ports"]["registration_id"]
            probe = self.ports or self.port_factory(adapter=self.coordinate_binding, journal=journal,
                **{**self.config["ports"], "registration_id": registration})
            original_api = probe.api
            original_registration = getattr(probe, "registration_id", None)
            probe.registration_id = registration
            raw = self.raw_api if self.ports is not None else original_api
            probe.api = raw
            terminal = None
            if state == "DISPATCH_UNRESOLVED":
                command_id, request_id = previous.get("command_id"), previous.get("request_id")
                if not isinstance(command_id, str) or not isinstance(request_id, str):
                    raise ExecutionBlocked("RESET_RECONCILIATION_REQUIRED", "The prior intent must retain exact identities.")
                marker = Path(self.config["journal_root"]) / ("dispatch-"+hashlib.sha256(command_id.encode()).hexdigest()+".private.json")
                record = json.loads(marker.read_bytes())
                if (record.get("mission_id") != mission_id or record.get("command_id") != command_id
                        or self.pending_command_id not in {None, command_id}):
                    raise ExecutionBlocked("RESET_MISSION_MISMATCH", "The preserved intent belongs to another mission.")
                terminal = raw.call("/v1/commands/"+request_id)
                if terminal.get("id") != request_id or terminal.get("state") not in {"complete", "reconciled"}:
                    raise ExecutionBlocked("RESET_COMMAND_OUTCOME_UNRESOLVED", "Reconcile the exact prior robot request before resetting.")
            before = probe._status()  # Original profile/tool/limits guards remain binding.
            self._reset_stationary_status(before)
            probe._camera_status()
            probe._native_cache = None
            native = checked_snapshot(probe, self.coordinate_binding, 5.)
            after = probe._status()
            self._reset_stationary_status(after)
            expected = (native.session_id, native.sequence, native.profile_id, native.installation_id, native.tcp_base)
            for observed in (before, after):
                receiver = observed["receiver"]
                actual = (receiver["session_id"], receiver["seq"], receiver["profile_id"],
                          observed["installation"]["installation_id"], tuple(receiver["actual_pose"]))
                if actual != expected:
                    raise ExecutionBlocked("RESET_BASELINE_CHANGED", "Keep the stationary receiver/profile unchanged during reset.")
            starts = {p.start_context_id for _, p in self.routes if self._matches(native.tcp_base, p.start_context_id)}
            if not starts:
                raise ExecutionBlocked("ROBOT_NOT_AT_START", "Return the empty tool to its measured START before reset.")
            if self.currentplan is not None and self.currentplan.start_context_id not in starts:
                raise ExecutionBlocked("RESET_START_MISMATCH", "Use this mission's measured START.")
            if hashlib.sha256(self.config_file.read_bytes()).hexdigest() != candidate_sha:
                raise ExecutionBlocked("RESET_CONFIGURATION_CHANGED", "Keep the exact deployment fixed during the stationary check.")
            proof = {"mission_id": mission_id, "reason": reason, "previous_checkpoint": previous,
                "terminal_robot_command": terminal, "native": asdict(native), "site_review_sha256": self.review_sha,
                "camera_epoch": self.binding.camera_epoch, "registration_id": registration,
                "previous_registration_id": self.binding.calibration_id,
                "previous_configuration_sha256": self._loaded_config_sha256,
                "configuration_sha256": candidate_sha, "registration_identity_rebound": candidate is not None,
                "current_profile_sha256": content_hash(after["receiver"]["profile"]),
                "motion_issued": False, "command_replayed": False, "car_reset_verified": False,
                "historical_outcome_changed": False}
            path, digest = journal.artifact("mission-retired-at-start", proof)
            journal.append("mission_retired_at_start", {"mission_id": mission_id, "proof_sha256": digest,
                "proof_path": str(path), "automatic_resume": False, "historical_outcome_changed": False})
            journal.checkpoint({"state": "MISSION_RETIRED_AT_START", "mission_id": mission_id,
                "proof_sha256": digest, "automatic_replay": False})
            if candidate is not None:
                preparer = self.profile_preparer
                self._load()  # Full schema/hash validation after retirement proof; no device IO.
                self.profile_preparer = preparer
                config_reloaded = True
            self._pin(after)
            self.currentplan = self.plan = self.current_context_id = self.pending_command_id = None
            self.workspace_binding = self.before_frame = self.last_contact_outcome = None
            self.last_snapshot = native
            if self.profile_preparer:
                self.profile_preparer.failed = False
            return {"proof_sha256": digest, "native_evidence_sha256": native.native_evidence_sha256,
                    "at_start": True, "stationary": True, "motion_issued": False, "automatic_resume": False}
        finally:
            if probe is not None and original_api is not None:
                probe.api = original_api
                if not config_reloaded and original_registration is not None:
                    probe.registration_id = original_registration
            if temporary:
                temporary.close()
            self.execution_lock.release()

    def _retirement_registration_candidate(self):
        """Permit only an explicit display identity rebind during retirement.

        Normal startup/reload remains blocked by an unresolved checkpoint.
        Camera epoch, map, geometry, physical review, signal pixels and all
        hardware settings must remain byte-equivalent JSON values. The reset
        still checks the terminal command and actual camera/Native source.
        """
        raw = self.config_file.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest == self._loaded_config_sha256:
            return None, digest
        candidate = json.loads(raw)
        registration = (candidate.get("ports") or {}).get("registration_id")
        if not isinstance(registration, str) or not 1 <= len(registration) <= 100:
            raise ExecutionBlocked("RESET_CONFIGURATION_CHANGED", "Use one explicit display registration identity.")
        permitted = deepcopy(self._loaded_source_config)
        permitted["ports"]["registration_id"] = registration
        permitted["site_binding"]["calibration_id"] = registration
        for target in (permitted.get("observations", {}).get("signal_targets") or {}).values():
            target["registration_id"] = registration
        if candidate != permitted:
            raise ExecutionBlocked("RESET_CONFIGURATION_CHANGED", "Retirement may rebind only the display registration identity.")
        return candidate, digest

    def _reset_stationary_status(self, status):
        receiver = status.get("receiver", {})
        if (status.get("hold") is not True or status.get("armed") is not False
                or status.get("active_commands") != [] or receiver.get("connected") is not True
                or receiver.get("idle") is not True or receiver.get("physical_execution") is not True
                or receiver.get("profile_pending") or receiver.get("reason") == "RECEIVER_RECONCILIATION_REQUIRED"):
            raise ExecutionBlocked("RESET_HELD_IDLE_REQUIRED", "Require held, disarmed, idle and no active or pending robot operation.")
        if any(status["installation"].get(k) != v for k, v in self.profile_review["site"].items()):
            raise ExecutionBlocked("RESET_SITE_CHANGED", "The current tool, payload, surface and fixed height must match review.")

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
