"""Private, explicitly reserved commissioning IO over the existing robot driver.

Construction and ``routes`` only read deployment files.  ``acquire`` is called
by the console owner *after* the product commissioning broker has reserved this
owner and the exact production ``runner.owner.lock`` has been acquired.  The
core service owns that cross-process lock; this module never steals it or
changes the production configuration.  One execute call runs one existing
logical primitive, including its internal guarded <=20 mm stages, then stops.

The public method return shapes are JSON values except ``camera`` which returns
``{"metadata": dict, "jpeg": bytes}``.  Routes are a list of objects containing
``code``, ``destination``, ``steps`` and ``empty_return``.  Signal helpers have
the stable IDs ``<step>/recontact`` and ``<step>/release-to-wait``.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import asdict, is_dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace
from uuid import uuid4

from backend.robot_control.coordinate_units import (
    CoordinateStage, CoordinateUnit, validate_normal_disengagement,
)
from backend.robot_control.mission_catalog import EvidenceReference, content_hash
from backend.robot_control.mission_observer import MissionObserver
from backend.robot_control.mission_policy import MissionState, Phase
from backend.robot_control.mission_profile import validate_site_review
from backend.robot_control.mission_vision import MetaMissionVision
from backend.robot_control.site_trial_driver import SiteTrialMissionDriver
from backend.robot_control.taught_executor import ExecutionBlocked, checked_snapshot
from backend.robot_control.taught_ports import LocalHTTP, encoded
from tools.check_muse_api import load_key

REVIEWED_FIELDS = ("fixed_z_orientation", "tool_car_hose_clearance", "contact_release",
                   "path_continuity", "bounded_xy_region")


def _require(condition, code, message):
    if not condition:
        raise ExecutionBlocked(code, message)


def _json_value(value):
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    return value


class _ArchivedVision(MetaMissionVision):
    """Existing MUSE prompts/schema with exact private provider-body evidence."""

    def __init__(self, ports):
        super().__init__("")
        self.ports = ports

    def _configured(self):
        # Read only the explicitly configured private file, never process env.
        load_key(self.ports.meta_env_file)

    async def _request(self, prompt, content, schema_name, schema, validator, label):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": content}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": schema_name, "strict": True, "schema": schema}},
            "reasoning_effort": "minimal", "max_completion_tokens": self.max_completion_tokens,
        }
        # Image bytes already have source-bound camera artifacts.  Preserve the
        # exact request hash and text, without duplicating base64 or credentials.
        summary = []
        for item in content:
            if item.get("type") == "text":
                summary.append(deepcopy(item))
            elif item.get("type") == "image_url":
                url = item.get("image_url", {}).get("url", "")
                summary.append({"type": "image_url", "data_url_sha256": hashlib.sha256(url.encode()).hexdigest()})
        journal = self.ports.journal
        journal.artifact("console-muse-input", {
            "source": "meta", "label": label, "model": self.model,
            "prompt": prompt, "content": summary, "schema": schema,
            "payload_sha256": hashlib.sha256(encoded(payload)).hexdigest(),
            "automatic_retry": False, "motion_authority": False,
        })

        def send():
            request = urllib.request.Request(self.endpoint, data=encoded(payload), headers={
                "Authorization": "Bearer " + load_key(self.ports.meta_env_file),
                "Content-Type": "application/json"})
            try:
                with self.ports.provider_opener.open(request, timeout=45) as response:
                    return response.status, response.read(1_000_001)
            except urllib.error.HTTPError as error:
                with error:
                    return error.code, error.read(1_000_001)

        try:
            status, raw = await asyncio.to_thread(send)
            _require(len(raw) <= 1_000_000, "MUSE_RESPONSE_SIZE", "Provider response exceeds the original bounded limit.")
            path, digest = journal.artifact("console-muse-raw-response", {
                "http_status": status, "body_sha256": hashlib.sha256(raw).hexdigest(),
                "raw_body_utf8": raw.decode("utf-8", errors="strict"),
                "payload_sha256": hashlib.sha256(encoded(payload)).hexdigest(),
                "automatic_retry": False})
            _require(status == 200, "MUSE_PROVIDER_FAILURE", "The provider did not accept this actual observation.")
            envelope = json.loads(raw)
            choice = envelope["choices"][0]
            _require(choice.get("finish_reason") == "stop" and not choice["message"].get("refusal"),
                     "MUSE_INCOMPLETE", "No incomplete or refused response may become a PASS.")
            result = validator(json.loads(choice["message"]["content"]))
            journal.artifact("console-muse-parsed-result", {
                "result": result, "raw_artifact": path.name, "raw_artifact_sha256": digest,
                "original_body_sha256": hashlib.sha256(raw).hexdigest(),
                "motion_authority": False})
            return result
        except Exception as error:
            journal.artifact("console-muse-failed", {"error_type": type(error).__name__,
                "code": getattr(error, "code", "MUSE_FAILED"), "automatic_retry": False})
            raise


class ConsoleAdapter:
    """No IO with the robot until an independently reserved acquire call.

    The core service must serialize calls and hold the production journal's
    ProcessLock throughout ownership.  Stop is deliberately independent of the
    operation lock, so it can inhibit later stages while execute is blocking.
    """

    def __init__(self, config_path, *, owner_id=None):
        self.config_path = Path(config_path).absolute()
        self.owner_id = owner_id or "commissioning-" + uuid4().hex
        self._source_sha = hashlib.sha256(self.config_path.read_bytes()).hexdigest()
        self.preview = self._load_driver()
        self.production_journal_root = Path(self.preview.config["journal_root"])
        options = self.preview.config["ports"]
        self.robot = LocalHTTP(options.get("robot_origin", "http://127.0.0.1:8897"), options["token_file"])
        self.product = LocalHTTP(options.get("camera_origin", "http://127.0.0.1:8080"))
        self.driver = None
        self._operation_lock = threading.Lock()
        self._last = None
        self._before_native = self._after_native = None
        self._observer = None
        self._mission_id = "console-mission-" + uuid4().hex
        self._completed = []
        self._signal_proofs = {}
        self._artifacts = {}
        self._frame_artifacts = {}
        self._latest_frame = None

    def _load_driver(self):
        driver = SiteTrialMissionDriver(self.config_path)
        _require(driver._configuration_error is None, "CONSOLE_CONFIGURATION_INVALID",
                 "The exact existing private deployment must validate before inspection or execution.")
        return driver

    def _unchanged_source(self):
        _require(hashlib.sha256(self.config_path.read_bytes()).hexdigest() == self._source_sha,
                 "CONSOLE_CONFIGURATION_CHANGED", "Reload explicitly after any deployment/configuration change.")

    def _entries(self, driver=None):
        driver = driver or self.driver or self.preview
        entries = {}
        for code_entry, plan in driver.routes:
            code = next((key for key, item in driver.config["workspace_bindings"].items()
                         if item == code_entry), None)
            _require(code is not None, "CONSOLE_ROUTE_BINDING", "Every exported route needs its exact workspace binding.")
            rows = []
            for index, step in enumerate(plan.steps):
                rows.append((step.id, "route", step.primitive, index, step))
                if step.signal_gate:
                    rows.append((step.id + "/recontact", "signal_recontact", step.signal_gate.recontact, index, step))
                    rows.append((step.id + "/release-to-wait", "signal_release", step.signal_gate.release_to_wait, index, step))
            rows.extend((p.id, "return", p, None, None) for p in plan.empty_return)
            entries[code] = (code_entry, plan, {row[0]: row for row in rows})
        return entries

    def routes(self):
        """File-only effective geometry; no journal, API or model invocation."""
        self._unchanged_source()
        driver = self.driver or self.preview
        result = []
        for code, (_, plan, rows) in self._entries(driver).items():
            steps, returns = [], []
            for identifier, role, primitive, index, step in rows.values():
                measured = driver.measured[primitive.id]
                row = {"id": identifier, "primitive_id": primitive.id, "role": role,
                    "step_index": index, "kind": measured.kind, "empty_tool": primitive.empty_tool,
                    "at_goal": bool(step and step.at_goal), "expected_visual": measured.expected_visual,
                    "geometry_sha256": measured.geometry_sha256,
                    "source_context_id": primitive.source_context_id,
                    "target_context_id": primitive.target_context_id,
                    "source_base": list(measured.stages[0].start_base),
                    "target_base": list(measured.stages[-1].target_base),
                    "stages": [{"id": s.id, "phase": s.phase, "start_base": list(s.start_base),
                                "target_base": list(s.target_base)} for s in measured.stages],
                    "contact_travel_limit_mm": measured.contact_travel_limit_mm,
                    "observation_required": bool(step and step.observation_required and role == "route"),
                    "signal_gate_id": step.signal_gate.id if step and step.signal_gate else None,
                    "signal_gate": {"id": step.signal_gate.id} if step and step.signal_gate and role == "route" else None}
                (returns if role == "return" else steps).append(row)
            result.append({"code": code, "destination": plan.destination, "steps": steps,
                "empty_return": returns, "start_context_id": plan.start_context_id,
                "start_base": driver.config["contexts"][plan.start_context_id]["pose_base"],
                "source_config_sha256": self._source_sha, "release_mode": "site_trial",
                "repeatability_qualified": False})
        return {"routes": result, "read_only": self.driver is None,
                "draft_reviewed_fields": list(REVIEWED_FIELDS)}

    def passive_status(self):
        """GET-only metadata, returned as {robot: dict, physical: dict}."""
        return {"robot": self.robot.call("/v1/status"),
                "physical": self.product.call("/api/v1/physical/status")}

    def camera(self):
        metadata = self.product.call("/api/v1/live-camera")
        frame = metadata.get("frame") or {}
        path = frame.get("image_url")
        _require(isinstance(path, str) and path == "/api/v1/live-camera/frames/" + str(frame.get("id")) + "/image",
                 "CONSOLE_CAMERA_SOURCE", "Use the exact immutable original frame URL.")
        data = self.product.call(path, binary=True)
        _require(hashlib.sha256(data).hexdigest() == frame.get("sha256"),
                 "CONSOLE_CAMERA_HASH", "The original frame bytes must match their published SHA-256.")
        return {"metadata": metadata, "jpeg": data}

    def _product_post(self, path, payload):
        request = urllib.request.Request(self.product.origin + path, data=encoded(payload),
            headers={"Content-Type": "application/json", "Origin": self.product.origin})
        try:
            # Broker ownership handoff can include a bounded eight-second
            # Native proof plus its status round trips.  A longer observation
            # window changes no robot command/commit timeout and never retries.
            with self.product.opener.open(request, timeout=30) as response:
                raw = response.read(2_000_001)
        except urllib.error.HTTPError as response:
            status_code = response.code
            with response:
                raw = response.read(2_000_001)
            code = "CONSOLE_BROKER_REJECTED"
            if len(raw) <= 2_000_000:
                try:
                    body = json.loads(raw)
                    detail = body.get("detail", body.get("error", body))
                    value = detail.get("code", detail.get("message", "")) if isinstance(detail, dict) else detail
                    prefix = value.split(":", 1)[0] if isinstance(value, str) else ""
                    if re.fullmatch(r"[A-Z][A-Z0-9_]{1,100}", prefix):
                        code = prefix
                except (ValueError, TypeError, AttributeError):
                    pass
            error = ExecutionBlocked(code, "The product commissioning broker rejected this ownership operation.")
            error.status_code = status_code
            error.broker_rejected = 400 <= status_code < 500
            raise error from None
        _require(len(raw) <= 2_000_000, "CONSOLE_BROKER_RESPONSE", "Broker response exceeds its limit.")
        return json.loads(raw)

    def reserve(self, owner_id, reason, *, request_id=None):
        _require(self.driver is None and isinstance(owner_id, str) and 1 <= len(owner_id) <= 200,
                 "CONSOLE_OWNER_INVALID", "Reserve one explicit console owner before acquiring IO.")
        status = self.product.call("/api/v1/physical/status")
        self.owner_id = owner_id  # Preserve the exact attempted identity even if POST response is lost.
        result = self._product_post("/api/v1/physical/commissioning/acquire", {
            "request_id": request_id or str(uuid4()), "expected_revision": status["revision"],
            "owner_id": owner_id, "reason": reason})
        return result

    def release_reservation(self, owner_id, reason):
        _require(self.driver is None and owner_id == self.owner_id, "CONSOLE_OWNER_INVALID",
                 "Close owned IO and release the process lock before releasing the broker reservation.")
        status = self.product.call("/api/v1/physical/status")
        return self._product_post("/api/v1/physical/commissioning/release", {
            "request_id": str(uuid4()), "expected_revision": status["revision"],
            "owner_id": owner_id, "reason": reason})

    def _reserved(self):
        status = self.product.call("/api/v1/physical/status")
        owner = status.get("commissioning") or {}
        _require(owner.get("reserved") is True and owner.get("owner_id") == self.owner_id,
                 "CONSOLE_RESERVATION_REQUIRED", "The product broker must reserve this exact console owner.")
        return status

    def acquire(self, journal_root):
        """Core caller already holds the exact production runner ProcessLock."""
        _require(self.driver is None, "CONSOLE_ALREADY_ACQUIRED", "One console owner may acquire only once.")
        self._unchanged_source()
        self._reserved()
        root = Path(journal_root).absolute()
        _require(root != self.production_journal_root and not root.is_relative_to(self.config_path.parent),
                 "CONSOLE_JOURNAL_SEPARATE", "Use a new private console journal outside production configuration/state.")
        driver = self._load_driver()
        driver.config["journal_root"] = str(root)
        # Expose the owner to the pure Stop signal before a possibly long fresh
        # Native wait.  Acquisition never clears an arriving Stop generation.
        self.driver = driver
        with driver._stop_lock:
            driver._prepare_wait_generation = driver._stop_generation
        try:
            driver._ensure_ports()
            original_capture = driver.ports.capture

            def capture():
                frame = original_capture()
                self._register_frame(driver, frame)
                self._latest_frame = frame
                return frame

            driver.ports.capture = capture
            status = driver.ports._status()
            _require(all(status["installation"].get(k) == v for k, v in driver.profile_review["site"].items()),
                     "CONSOLE_SITE_CHANGED", "The original reviewed site, height, tool and payload must match.")
            driver._pin(status)
            native = driver._snapshot()
            driver.ports._camera_status()
            driver.journal.append("console_io_acquired", {"owner_id": self.owner_id,
                "source_config_sha256": self._source_sha, "native": asdict(native),
                "production_configuration_written": False, "automatic_motion": False})
            self._observer = MissionObserver(provider=_ArchivedVision(driver.ports))
            driver.observer_callback = self._observer
            _require(self._observer.readiness(driver.config).get("ready") is True,
                     "CONSOLE_OBSERVER_CONFIGURATION", "Use the complete existing observation and signal configuration.")
            return {"owner_id": self.owner_id, "native": asdict(native), "motion_issued": False}
        except Exception:
            if driver.journal:
                driver.journal.close()
            self.driver = None
            raise
        finally:
            driver._prepare_wait_generation = None

    def _owned(self):
        _require(self.driver is not None, "CONSOLE_NOT_ACQUIRED", "Acquire reserved IO before an operation.")
        self._unchanged_source()
        self._reserved()
        _require(self.driver.pending_command_id is None, "CONSOLE_OUTCOME_UNRESOLVED",
                 "Reconcile the exact pending command before another operation.")
        return self.driver

    def _register_frame(self, driver, frame):
        if frame.sha256 not in self._frame_artifacts:
            path, digest = driver.journal.artifact("console-observation-frame", frame.original_jpeg, binary=True)
            identifier = "image-" + uuid4().hex
            self._artifacts[identifier] = (path, digest)
            self._frame_artifacts[frame.sha256] = identifier
        return self._frame_artifacts[frame.sha256]

    def artifact(self, identifier):
        _require(isinstance(identifier, str) and identifier in self._artifacts,
                 "CONSOLE_ARTIFACT_NOT_FOUND", "Only this session's registered immutable JPEG artifacts can be read.")
        path, digest = self._artifacts[identifier]
        _require(not path.is_symlink() and path.is_file(), "CONSOLE_ARTIFACT_CHANGED", "The registered original artifact changed.")
        data = path.read_bytes()
        _require(len(data) <= 12_000_000 and hashlib.sha256(data).hexdigest() == digest
                 and data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"),
                 "CONSOLE_ARTIFACT_CHANGED", "Require the exact recorded original JPEG bytes.")
        return data

    @staticmethod
    def _same_native(first, second):
        keys = ("session_id", "sequence", "profile_id", "installation_id", "tcp_base")
        return (len(first.get("joints_deg", ())) == len(second.get("joints_deg", ())) == 6
                and all(_json_value(first.get(k)) == _json_value(second.get(k)) for k in keys)
                and all(abs(a - b) <= .100000001
                        for a, b in zip(first.get("joints_deg", ()), second.get("joints_deg", ()))))

    def _check_signal_selection(self, driver, route, plan, role, index, step, native):
        """A raw GUI selection is never authority to skip a signal gate."""
        if role == "return":
            return
        for gate_index, gate_step in enumerate(plan.steps):
            gate = gate_step.signal_gate
            if gate is None:
                continue
            if role.startswith("signal_") or role == "route" and index is not None and index > gate_index:
                _require(gate.entry_policy == "single_departure", "CONSOLE_SIGNAL_POLICY_UNSUPPORTED",
                         "This console retains the selected single-departure policy; another policy needs its own reviewed flow.")
            proof = self._signal_proofs.get((route, gate.id))
            if role == "signal_recontact" and index == gate_index:
                _require(proof is not None and proof.get("state") == "GREEN_ACCEPTED"
                         and proof.get("expires_at_s", 0) >= driver.ports.now()
                         and self._same_native(proof["native"], asdict(native)),
                         "CONSOLE_SIGNAL_GREEN_REQUIRED", "Exact recontact requires fresh accepted stopped GREEN and unchanged Native source.")
            elif role == "signal_release" and index == gate_index:
                _require(proof is not None and proof.get("state") == "RECONTACT_COMPLETE",
                         "CONSOLE_SIGNAL_RELEASE_CONTEXT", "Only the recorded exact recontact can be withdrawn to its signal wait.")
            elif role == "route" and index is not None and index > gate_index:
                _require(proof is not None and (proof.get("state") == "CONSUMED" or
                         index == gate_index + 1 and proof.get("state") == "RECONTACT_COMPLETE"
                         and self._same_native(proof["recontact_native"], asdict(native))),
                         "CONSOLE_SIGNAL_GATE_NOT_CONSUMED", "A later route step cannot bypass its actual GREEN and exact recontact receipt.")

    def _record_signal_execution(self, driver, route, plan, role, index, receipt, actual):
        for gate_index, step in enumerate(plan.steps):
            gate = step.signal_gate
            if gate is None:
                continue
            key = (route, gate.id)
            proof = self._signal_proofs.get(key)
            if role == "signal_recontact" and index == gate_index:
                proof.update(state="RECONTACT_COMPLETE", recontact_receipt=asdict(receipt),
                             recontact_native=asdict(actual))
                driver.journal.append("console_signal_recontact_complete", deepcopy(proof))
            elif role == "signal_release" and index == gate_index:
                proof.update(state="WAITING", expires_at_s=0)
                driver.journal.append("console_signal_returned_to_wait", deepcopy(proof))
            elif role == "route" and index == gate_index + 1:
                proof.update(state="CONSUMED", crossing_receipt=asdict(receipt))
                driver.journal.append("console_signal_departure_consumed", deepcopy(proof))

    def _geometry(self, driver, measured, rows, expected_visual):
        _require(measured.kind != "wrist_edge", "CONSOLE_WRIST_EDIT_FORBIDDEN", "Directed wrist teaching is immutable here.")
        _require(isinstance(rows, list) and len(rows) == len(measured.stages),
                 "CONSOLE_DRAFT_PHASES", "Retain every original stage and phase.")
        stages = []
        for original, row in zip(measured.stages, rows, strict=True):
            _require(isinstance(row, dict) and set(row) == {"id", "phase", "start_base", "target_base"}
                     and row["id"] == original.id and row["phase"] == original.phase,
                     "CONSOLE_DRAFT_PHASES", "Do not relabel a contact, withdrawal or unloaded phase.")
            stage = replace(original, start_base=tuple(row["start_base"]), target_base=tuple(row["target_base"]))
            _require(stage.start_base[2:] == stage.target_base[2:] == measured.stages[0].start_base[2:],
                     "CONSOLE_FIXED_POSTURE", "Keep the original fixed height and literal orientation.")
            stages.append(stage)
        candidate = replace(measured, stages=tuple(stages), expected_visual=expected_visual,
                            original_verdict="MISSING", original_arrived=False)
        _require(candidate.stages[0].start_base == measured.stages[0].start_base
                 and candidate.stages[-1].target_base == measured.stages[-1].target_base,
                 "CONSOLE_DRAFT_ANCHORS", "Keep the original first source and final target; do not silently rebase following steps.")
        _require(isinstance(expected_visual, str) and 10 <= len(expected_visual) <= 700,
                 "CONSOLE_DRAFT_EXPECTATION", "Use a bounded explicit observation expectation.")
        for stage in candidate.stages:
            _require(all(driver.profile_review["workspace_min_mm"][i] <= p[i] <= driver.profile_review["workspace_max_mm"][i]
                         for p in (stage.start_base, stage.target_base) for i in range(3)),
                     "CONSOLE_DRAFT_BOUNDS", "A draft cannot enlarge the existing reviewed site.")
        normal = None
        contacts = [stage for stage in candidate.stages if stage.phase == "contact"]
        if contacts:
            last = max(i for i, s in enumerate(measured.stages) if s.phase == "contact")
            _require(last + 1 < len(measured.stages), "CONSOLE_DRAFT_RELEASE_REQUIRED", "Keep the original normal withdrawal.")
            release = measured.stages[last + 1]
            delta = [release.target_base[i] - release.start_base[i] for i in range(2)]
            distance = math.hypot(*delta)
            normal = [-v / distance for v in delta]
            contact = measured.stages[last]
            forward = [contact.target_base[i] - contact.start_base[i] for i in range(2)]
            length = math.hypot(*forward)
            _require(sum(normal[i] * forward[i] / length for i in range(2)) > 1 - 1e-6,
                     "CONSOLE_DRAFT_FACE_REVIEW_REQUIRED", "Only a stored normal-backoff contact family can be edited here.")
            unit = CoordinateUnit("console-draft", "console-draft-plan", 1,
                candidate.source, candidate.target, "pending-installation", "pending-profile",
                tuple(CoordinateStage(s.id, s.phase, s.start_base, s.target_base, driver.review_sha)
                      for s in candidate.stages), candidate.expected_visual,
                contact_travel_limit_mm=candidate.contact_travel_limit_mm)
            validate_normal_disengagement(unit, normal, 10.)
        return candidate, normal

    def validate_draft(self, step, value):
        """Pure bounded-geometry checks; neither approval nor IO preparation."""
        self._unchanged_source()
        _require(isinstance(step, dict) and isinstance(value, dict), "CONSOLE_DRAFT_FORMAT", "Use one registered step and draft.")
        measured = self.preview.measured[step["primitive_id"]]
        _require(step.get("role") not in {"signal_recontact", "signal_release"},
                 "CONSOLE_SIGNAL_GEOMETRY_IMMUTABLE", "Exact signal withdrawal and recontact cannot be edited here.")
        candidate, normal = self._geometry(self.preview, measured, value.get("stages"), value.get("expected_visual"))
        _require(isinstance(value.get("reason"), str) and 10 <= len(value["reason"].strip()) <= 500,
                 "CONSOLE_DRAFT_REASON", "Record an explicit bounded-coordinate experiment reason.")
        return {"stages": [{"id": s.id, "phase": s.phase, "start_base": list(s.start_base),
                            "target_base": list(s.target_base)} for s in candidate.stages],
                "expected_visual": candidate.expected_visual, "reason": value["reason"],
                "geometry_sha256": candidate.geometry_sha256,
                "original_geometry_sha256": measured.geometry_sha256,
                "required_reviewed_fields": list(REVIEWED_FIELDS),
                "required_contact_normal_base_xy": normal,
                "offline_geometry_valid": True, "physical_clearance_verified": False,
                "ik_verified": False, "repeatability_qualified": False}

    def _candidate(self, driver, measured, draft):
        """A private explicit experiment derivative, never an original PASS."""
        _require(isinstance(draft, dict), "CONSOLE_DRAFT_FORMAT", "Use an explicit reviewed draft.")
        candidate, normal = self._geometry(driver, measured, draft.get("stages"), draft.get("expected_visual"))
        approval = draft.get("approval") or {}
        _require(isinstance(approval, dict) and approval.get("approved") is True
                 and isinstance(approval.get("reason"), str) and 1 <= len(approval["reason"].strip()) <= 1000
                 and approval.get("geometry_sha256") == candidate.geometry_sha256
                 and isinstance(approval.get("reviewed_fields"), list)
                 and set(REVIEWED_FIELDS) <= set(approval["reviewed_fields"]),
                 "CONSOLE_EXPLICIT_DRAFT_REVIEW", "Approval must name the exact candidate hash, reason and reviewed physical conditions.")
        _require(approval.get("contact_normal_base_xy") == normal,
                 "CONSOLE_DRAFT_FACE_NORMAL", "Approval must retain the explicitly reviewed original nominal face normal.")
        manifest = {"schema": "pushpilot.console-derived-geometry.v1",
            "original_geometry_sha256": measured.geometry_sha256,
            "candidate_geometry_sha256": candidate.geometry_sha256,
            "original_stage_ids": [stage.id for stage in measured.stages],
            "stages": [{"id": stage.id, "phase": stage.phase,
                "start_base": list(stage.start_base), "target_base": list(stage.target_base)}
                for stage in candidate.stages],
            "approval": deepcopy(approval), "physical_execution": False,
            "original_completed_receipt_claimed": False}
        manifest_path, manifest_digest = driver.journal.artifact("console-candidate-geometry", manifest)
        evidence = EvidenceReference(str(manifest_path), "derived-candidate-stages", manifest_digest)
        candidate = replace(candidate, stages=tuple(replace(stage,
            original_request_id="console-derived-geometry-" + str(index), evidence=evidence)
            for index, stage in enumerate(candidate.stages)), evidence=(evidence, *measured.evidence))
        child = deepcopy(driver.profile_review)
        record = {"schema": "pushpilot.console-candidate-review.v1", "owner_id": self.owner_id,
            "original_config_sha256": self._source_sha, "original_geometry_sha256": measured.geometry_sha256,
            "candidate_geometry_sha256": candidate.geometry_sha256, "candidate": candidate.to_dict(),
            "approval": deepcopy(approval), "scope": "accepted_current_site_experiment",
            "physical_repeatability_qualified": False, "original_evidence_rewritten": False}
        path, digest = driver.journal.artifact("console-candidate-review", record)
        child["allowed_geometry_sha256"] = sorted(set(child["allowed_geometry_sha256"]) | {candidate.geometry_sha256})
        child["operator_authorization_sha256"] = digest
        child["review_reference"] = str(path)
        return candidate, validate_site_review(child)

    def execute(self, route, step_id, draft_or_none, command_id):
        _require(self._operation_lock.acquire(blocking=False), "CONSOLE_BUSY", "Only one console operation may run.")
        driver = self.driver
        execution_started = False
        try:
            _require(driver is not None, "CONSOLE_NOT_ACQUIRED", "Acquire reserved IO before execution.")
            with driver._stop_lock:
                generation = driver._stop_generation
                _require(not driver.stop_latch.is_set() or driver.currentplan is None,
                         "CONSOLE_STOPPED", "A stopped console operation requires explicit preparation and reconciliation.")
                driver._prepare_wait_generation = generation
            driver = self._owned()
            entry, plan, rows = self._entries(driver)[route]
            identifier, role, primitive, index, step = rows[step_id]
            native = driver._snapshot()
            # Each new selection starts from the immutable effective source,
            # never from a previously edited in-memory candidate.
            measured = self.preview.measured[primitive.id]
            _require(native.tcp_base == measured.stages[0].start_base,
                     "CONSOLE_EXACT_SOURCE", "The actual source must exactly match the selected stored primitive.")
            self._check_signal_selection(driver, route, plan, role, index, step, native)
            driver.ports._camera_status()
            if draft_or_none is not None:
                _require(role not in {"signal_recontact", "signal_release"}, "CONSOLE_SIGNAL_GEOMETRY_IMMUTABLE",
                         "Signal release and recontact retain exact reviewed geometry.")
                measured, review = self._candidate(driver, measured, draft_or_none)
                driver.measured[primitive.id] = measured
                driver.profile_review, driver.review_sha = review, content_hash(review)
                driver.qualifications[primitive.id] = SimpleNamespace(review_sha256=driver.review_sha)
            else:
                driver.measured[primitive.id] = measured
                driver.qualifications[primitive.id] = SimpleNamespace(review_sha256=driver.review_sha)
            driver.currentplan = driver.plan = replace(plan, id=self._mission_id)
            driver.workspace_binding = {**entry, "workspace_session_id": self.owner_id,
                "plan_id": self._mission_id, "plan_revision": 1}
            driver.current_context_id = primitive.source_context_id
            self._before_native = asdict(native)
            with driver._stop_lock:
                _require(driver._stop_generation == generation,
                         "CONSOLE_STOPPED", "Stop during source validation prevents dispatch.")
                driver.stop_latch.clear()
            driver.journal.append("console_primitive_selected", {"route": route, "step_id": identifier,
                "role": role, "command_id": command_id, "geometry_sha256": measured.geometry_sha256,
                "native_before": self._before_native, "operator_selected": True})
            with driver._stop_lock:
                _require(driver._stop_generation == generation and not driver.stop_latch.is_set(),
                         "CONSOLE_STOPPED", "Stop during selection prevents dispatch.")
            execution_started = True  # Preparation may itself have durable queries.
            receipt = driver.execute(primitive.id, command_id)
            actual = driver._snapshot()
            self._after_native = asdict(actual)
            self._record_signal_execution(driver, route, plan, role, index, receipt, actual)
            before_id = self._frame_artifacts.get(driver.before_frame.sha256) if driver.before_frame else None
            self._last = {"route": route, "step_id": identifier, "role": role,
                "step_index": index, "primitive_id": primitive.id, "receipt": asdict(receipt),
                "native_before": self._before_native, "native_after": self._after_native,
                "geometry_sha256": measured.geometry_sha256, "observation": None,
                "before_artifact_id": before_id, "after_artifact_id": None}
            self._completed.append(deepcopy(self._last))
            driver.journal.append("console_primitive_complete", self._last)
            return {**asdict(receipt), **deepcopy(self._last)}
        except Exception as error:
            # The core may distinguish a rejected selection/expired GREEN from
            # an ambiguous preparation or move.  Once driver.execute begins,
            # preserve its conservative original reconciliation policy.
            if not execution_started:
                error.known_before_execute = True
            raise
        finally:
            if driver is not None:
                driver._prepare_wait_generation = None
            self._operation_lock.release()

    def observe(self):
        _require(self._operation_lock.acquire(blocking=False), "CONSOLE_BUSY", "Only one observation or motion may run.")
        try:
            driver = self._owned()
            _require(self._last is not None, "CONSOLE_OBSERVATION_CONTEXT", "Complete a stored primitive before its review.")
            plan = driver.currentplan
            index = self._last["step_index"]
            step = plan.steps[index] if index is not None else None
            if self._last["role"] != "route" or not step.observation_required:
                after = driver.capture()
                result = {"review": None, "observation_required": False,
                    "summary": "Native endpoint verified; unloaded repositioning has no invented vehicle PASS.",
                    "before_artifact_id": self._last.get("before_artifact_id"),
                    "after_artifact_id": self._frame_artifacts[after.sha256]}
                if step and step.signal_gate:
                    proof = self._signal_proofs.get((self._last["route"], step.signal_gate.id)) or {}
                    result["signal_gate"] = {"id": step.signal_gate.id,
                        "accepted": proof.get("state") in {"RECONTACT_COMPLETE", "CONSUMED"}}
                self._last["observation"] = deepcopy(result)
                driver.journal.append("console_unloaded_endpoint_observed", result)
                return result
            _require(driver.last_contact_outcome is not None, "CONSOLE_CONTACT_OUTCOME_REQUIRED", "Bind the actual completed contact unit.")
            state = MissionState(plan.id, self._after_native["session_id"], phase=Phase.OBSERVE,
                step_index=self._last["step_index"], action_command_id=self._last["receipt"]["command_id"],
                last_motion_completed_at_s=self._last["receipt"]["completed_at_s"],
                start_verified=True, issued_command_ids=tuple(r["receipt"]["command_id"] for r in self._completed))
            result = driver.observe(state)
            result = _json_value(result)
            self._last["observation"] = deepcopy(result)
            driver.journal.append("console_observation_complete", {"step_id": step.id, "result": result,
                "automatic_next_step": False})
            after = self._latest_frame
            output = {"review": result, "summary": result.get("summary"),
                "before_artifact_id": self._frame_artifacts.get(driver.before_frame.sha256) if driver.before_frame else None,
                "after_artifact_id": self._frame_artifacts.get(after.sha256) if after else None}
            if step.signal_gate:
                key = (self._last["route"], step.signal_gate.id)
                self._signal_proofs[key] = {"route": self._last["route"], "step_id": step.id,
                    "gate_id": step.signal_gate.id, "state": "WAITING", "expires_at_s": 0}
                output["signal_gate"] = {"id": step.signal_gate.id, "accepted": False}
            return output
        finally:
            self._operation_lock.release()

    def observe_signal(self, route=None, step_id=None):
        _require(self._operation_lock.acquire(blocking=False), "CONSOLE_BUSY", "Only one signal observation may run.")
        try:
            driver = self._owned()
            _require(self._last is not None, "CONSOLE_SIGNAL_STOP_REFERENCE", "Complete the actual signal stop first.")
            route = route or self._last["route"]
            step_id = step_id or self._last["step_id"].split("/", 1)[0]
            _, plan, rows = self._entries(driver)[route]
            _, role, primitive, index, step = rows[step_id]
            _require(role == "route" and step.signal_gate is not None
                     and self._last["step_id"] in {step_id, step_id + "/release-to-wait"} and self._last["route"] == route
                     and self._last["observation"] is not None,
                     "CONSOLE_SIGNAL_STOP_REFERENCE", "Observe the actual completed and visually reviewed signal-stop primitive first.")
            _require(driver.currentplan is not None and driver.currentplan.destination == plan.destination,
                     "CONSOLE_SIGNAL_PLAN", "Keep this exact stopped route and signal binding.")
            actual = driver._snapshot()
            _require(actual.tcp_base == driver.measured[primitive.id].stages[-1].target_base,
                     "CONSOLE_SIGNAL_WAIT_POSITION", "Wait at the exact stored right-side observation position.")
            state = MissionState(driver.currentplan.id, actual.session_id, phase=Phase.WAIT_SIGNAL,
                step_index=index, start_verified=True, action_command_id=self._last["receipt"]["command_id"],
                last_motion_completed_at_s=self._last["receipt"]["completed_at_s"],
                issued_command_ids=tuple(r["receipt"]["command_id"] for r in self._completed))
            result = _json_value(driver.observe(state))
            samples = result.get("samples") or []
            signals = [sample.get("signal") or {} for sample in samples]
            images = [signal.get("image_sha256") for signal in signals]
            accepted = (len(signals) == 2 and len(set(images)) == 2 and all(
                signal.get("gate_id") == step.signal_gate.id and signal.get("color") == "GREEN"
                and signal.get("exclusive_green") is True and signal.get("signal_visible") is True
                and signal.get("car_visible") is True and signal.get("car_unchanged_since_stop") is True
                and signal.get("session_id") == actual.session_id
                and signal.get("native_sequence") == actual.sequence for signal in signals))
            fresh = driver._snapshot()
            _require(self._same_native(asdict(actual), asdict(fresh)), "CONSOLE_SIGNAL_SOURCE_CHANGED",
                     "The stopped source changed while judging the signal.")
            key = (route, step.signal_gate.id)
            self._signal_proofs[key] = {"route": route, "step_id": step_id,
                "gate_id": step.signal_gate.id, "state": "GREEN_ACCEPTED" if accepted else "WAITING",
                "native": asdict(fresh), "observation": deepcopy(result),
                "expires_at_s": min(signal["captured_at_s"] for signal in signals) + min(
                    plan.signal_max_age_s, step.signal_gate.green_valid_for_s) if accepted else 0}
            driver.journal.append("console_signal_observation", {"route": route, "step_id": step_id,
                "result": result, "automatic_motion": False})
            return {"signal_gate": {"id": step.signal_gate.id, "accepted": accepted,
                        "stable_green_frames": 2 if accepted else 0},
                    "review": result, "summary": result.get("summary"),
                    "after_artifact_id": self._frame_artifacts.get(self._latest_frame.sha256) if self._latest_frame else None}
        finally:
            self._operation_lock.release()

    def ready_to_release(self):
        driver, native = self._operator_stationary_read(clear_stop=False)
        starts = {tuple(driver.config["contexts"][plan.start_context_id]["pose_base"]) for _, plan in driver.routes}
        _require(len(starts) == 1 and native.tcp_base == next(iter(starts)),
                 "CONSOLE_RELEASE_START_REQUIRED", "A fresh exact common START proof is required before product ownership returns.")
        checkpoint = driver.journal.load() or {}
        _require(checkpoint.get("state") not in {"DISPATCH_UNRESOLVED", "PROFILE_PREPARATION_UNRESOLVED", "PROFILE_PREPARATION_FAILED"},
                 "CONSOLE_OUTCOME_UNRESOLVED", "Preserve an unresolved preparation or command; never force-clear it.")
        proof = {"owner_id": self.owner_id, "native": asdict(native), "at_start": True, "motion_issued": False}
        driver.journal.artifact("console-release-start-proof", proof)
        return proof

    def stop(self, reason):
        if self.driver is None:
            return {"hold": False, "owned": False, "robot_stop_issued": False}
        self.driver.request_stop()  # Pure synchronous cancellation before IO.
        return self.driver.hold(reason)

    def request_stop(self):
        """Pure, nonblocking signal used before the core takes its own lock."""
        if self.driver is not None:
            self.driver.request_stop()

    def _operator_stationary_read(self, *, clear_stop):
        driver = self.driver
        _require(driver is not None, "CONSOLE_NOT_ACQUIRED", "Acquire reserved IO before stationary verification.")
        _require(not self._operation_lock.locked(), "CONSOLE_BUSY", "Finish the active operation before acknowledging its result.")
        with driver._stop_lock:
            generation = driver._stop_generation
            driver._prepare_wait_generation = generation
        try:
            self._owned()
            checkpoint = driver.journal.load() or {}
            _require(checkpoint.get("state") not in {"DISPATCH_UNRESOLVED", "PROFILE_PREPARATION_UNRESOLVED", "PROFILE_PREPARATION_FAILED"},
                     "CONSOLE_OUTCOME_UNRESOLVED", "Acknowledgment never clears an unresolved command or preparation.")
            actual = driver._snapshot()
            if self._after_native is not None:
                _require(self._same_native(self._after_native, asdict(actual)), "CONSOLE_ENDPOINT_CHANGED",
                         "The current exact endpoint differs from the completed unit.")
            with driver._stop_lock:
                _require(driver._stop_generation == generation, "CONSOLE_STOPPED",
                         "A new Stop during verification cannot be cleared by an older acknowledgment.")
                if clear_stop:
                    driver.stop_latch.clear()
            return driver, actual
        finally:
            driver._prepare_wait_generation = None

    def confirm_stationary(self):
        driver, actual = self._operator_stationary_read(clear_stop=True)
        proof = {"native": asdict(actual), "model_verdict_overwritten": False, "motion_issued": False}
        driver.journal.artifact("console-ack-stationary-proof", proof)
        return proof

    def close(self):
        if self.driver is not None:
            _require(not self._operation_lock.locked(), "CONSOLE_BUSY", "Do not close an operation that is still waiting for its result.")
            driver = self.driver
            driver.close()
            self.driver = None

