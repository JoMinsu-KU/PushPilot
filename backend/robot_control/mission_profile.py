"""Narrow current-site experimental profile preparation, never motion dispatch.

All IO is injected. The caller supplies an existing explicit operator/site
review and exact allowlisted geometry; this code does not establish physical
qualification. It retains the guarded receiver's independent 19-sample wrist
FK checks before READY/GO. Read-only endpoint IK is not that path proof.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import time
from uuid import uuid4

from .mission_catalog import MeasuredPrimitive, content_hash
from .gates import NATIVE_BASELINE_COMPARISON_QUANTIZATION
from .models import LocalContactInstallation
from .taught_executor import ExecutionBlocked, Snapshot
from .taught_ports import write_new, sync_directory
from .wrist_commissioning import propose_wrist_turn, verify_endpoint_ik
from tools.prepare_local_contact import build_profile as contact_profile
from tools.prepare_contact_turn import build_profile as wrist_profile


def _require(condition, code):
    if not condition:
        raise ExecutionBlocked(code, "Current-site profile preparation stopped; reconcile before another operation.")


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _pose(value, length=6):
    return (isinstance(value, (list, tuple)) and len(value) == length
            and all(_finite(v) and abs(v) <= 10000 for v in value))


def _near(first, second, tolerance=.1):
    return _pose(first) and _pose(second) and all(abs(a-b) <= tolerance for a, b in zip(first, second))


def validate_site_review(review):
    """Validate a supplied authorization record; never create one from history."""
    required = {"schema", "status", "operator_authorization_sha256", "review_reference", "site",
                "workspace_min_mm", "workspace_max_mm", "allowed_geometry_sha256",
                "max_speed_mm_s", "max_accel_mm_s2", "max_step_mm", "unloaded_wrist_authorized",
                "wrist_descriptor_sha256s"}
    _require(isinstance(review, dict) and set(review) == required
        and review["schema"] == "pushpilot.current-site-profile-review.v1"
        and review["status"] == "accepted_current_site_experiment"
        and _sha(review["operator_authorization_sha256"])
        and isinstance(review["review_reference"], str) and 10 <= len(review["review_reference"]) <= 500,
        "EXPLICIT_CURRENT_SITE_REVIEW_REQUIRED")
    site_keys = {"tcp_id", "tcp_definition_sha256", "tool_id", "car_id", "surface_id", "payload_kg", "fixed_tcp_z_mm"}
    site = review["site"]
    _require(isinstance(site, dict) and set(site) == site_keys
        and all(isinstance(site[k], str) and 0 < len(site[k]) <= 80 for k in
                ("tcp_id", "tool_id", "car_id", "surface_id"))
        and _sha(site["tcp_definition_sha256"]) and _finite(site["payload_kg"]) and site["payload_kg"] >= 0
        and _finite(site["fixed_tcp_z_mm"]), "CURRENT_SITE_IDENTITY_REQUIRED")
    lower, upper = review["workspace_min_mm"], review["workspace_max_mm"]
    _require(_pose(lower, 3) and _pose(upper, 3) and all(a < b for a, b in zip(lower, upper)),
             "REVIEWED_SITE_BOUNDS_REQUIRED")
    for key, maximum in (("max_speed_mm_s", 5.), ("max_accel_mm_s2", 10.), ("max_step_mm", 20.)):
        _require(_finite(review[key]) and 0 < review[key] <= maximum, "ORIGINAL_SPEED_ACCEL_STEP_LIMITS_REQUIRED")
    for key in ("allowed_geometry_sha256", "wrist_descriptor_sha256s"):
        values = review[key]
        _require(isinstance(values, (list, tuple)) and all(_sha(v) for v in values)
                 and len(set(values)) == len(values), "EXACT_GEOMETRY_ALLOWLIST_REQUIRED")
    _require(bool(review["allowed_geometry_sha256"]) and type(review["unloaded_wrist_authorized"]) is bool,
             "EXACT_GEOMETRY_ALLOWLIST_REQUIRED")
    return deepcopy(review)


def resolve_wrist_descriptor(measured, review, source, joints, wrist):
    """Bind one reviewed wrist intent to the actual joint winding.

    A semantic intent contains edge_id, delta_j6_deg, rotation_runtime and
    unloaded=True. Its hash and the literal target geometry must both be
    allowlisted. A fresh joint baseline changes only the resolved joint
    descriptor; it never changes the reviewed target pose or joint direction.
    Exact historical descriptors remain supported for archival checks.
    """
    literal = {"edge_id", "expected_source_joint_deg", "expected_target_joint_deg", "rotation_runtime", "unloaded"}
    semantic = {"edge_id", "delta_j6_deg", "rotation_runtime", "unloaded"}
    _require(measured.kind == "wrist_edge" and review["unloaded_wrist_authorized"] is True
        and isinstance(wrist, dict) and (set(wrist) == literal or set(wrist) == semantic)
        and wrist["unloaded"] is True and content_hash(wrist) in review["wrist_descriptor_sha256s"],
        "UNLOADED_WRIST_REVIEW_REQUIRED")
    _require(isinstance(wrist["edge_id"], str) and 1 <= len(wrist["edge_id"]) <= 80,
             "DIRECTED_WRIST_EDGE_REQUIRED")
    if set(wrist) == literal:
        return deepcopy(wrist)
    proposal = propose_wrist_turn(source, joints, wrist["delta_j6_deg"])
    target = measured.stages[0].target_base
    _require(tuple(proposal["target_pose"][:3]) == tuple(target[:3])
        and _near(proposal["target_pose"], target, 1e-6), "SEMANTIC_WRIST_TARGET_CHANGED")
    return {"edge_id": wrist["edge_id"], "expected_source_joint_deg": proposal["source_joint"],
        "expected_target_joint_deg": proposal["target_joint"],
        "rotation_runtime": deepcopy(wrist["rotation_runtime"]), "unloaded": True}


def _native_identity(native, installation):
    return (native.installation_id == installation["installation_id"]
        and native.scope == installation["scope"]
        and all(getattr(native, key) == installation[key] for key in
                ("tcp_definition_sha256", "tool_id", "car_id", "surface_id")))


def build_unit_profile(measured, review, status, native, *, installation_id, wrist=None, review_reference=None,
                       inspected_source_joint=None):
    """Pure construction from a fresh baseline and an already reviewed unit.

    ``wrist`` is an exact joint descriptor or reviewed semantic joint-6 intent.
    Its canonical hash must occur in wrist_descriptor_sha256s. Semantic intents
    resolve from the current Native-matched joints, retaining the measured pose.
    """
    review = validate_site_review(review)
    _require(isinstance(measured, MeasuredPrimitive) and measured.geometry_sha256 in review["allowed_geometry_sha256"],
             "UNIT_GEOMETRY_NOT_REVIEWED")
    old, receiver = status["installation"], status["receiver"]
    source, joints = receiver["actual_pose"], receiver["actual_joint"]
    _require(_pose(source) and _pose(joints) and isinstance(native, Snapshot), "FRESH_NATIVE_SOURCE_REQUIRED")
    _require(tuple(source) == measured.stages[0].start_base
        and _near(native.native_tcp_base, source, NATIVE_BASELINE_COMPARISON_QUANTIZATION)
        and tuple(native.tcp_base) == tuple(source)
        and _near(native.joints_deg, joints, NATIVE_BASELINE_COMPARISON_QUANTIZATION)
        and native.held_disarmed_idle, "EXACT_CURRENT_UNIT_SOURCE_REQUIRED")
    _require(_native_identity(native, old), "CURRENT_NATIVE_IDENTITY_CHANGED")
    _require(old.get("qualified") is True and old.get("on_site_review") is True
        and old.get("contact_trials_authorized") is True, "EXISTING_LOCAL_REVIEW_REQUIRED")
    _require(all(old.get(k) == v for k, v in review["site"].items())
        and source[2] == review["site"]["fixed_tcp_z_mm"], "CURRENT_SITE_IDENTITY_CHANGED")
    for key in ("max_speed_mm_s", "max_accel_mm_s2", "max_step_mm"):
        _require(old.get(key) == review[key], "ORIGINAL_LIMITS_CHANGED")
    _require(all(stage.phase != "unclassified" for stage in measured.stages), "UNCLASSIFIED_GEOMETRY_FORBIDDEN")
    points = [source, *(s.target_base for s in measured.stages)]
    is_wrist = measured.kind == "wrist_edge"
    if not is_wrist:
        _require(wrist is None and all(tuple(p[2:]) == tuple(source[2:]) for p in points), "FIXED_Z_EULER_REQUIRED")
        _require(all(math.dist(s.start_base[:2], s.target_base[:2]) <= review["max_step_mm"]
                     for s in measured.stages), "ORIGINAL_STAGE_LIMIT_EXCEEDED")
    padding = (.6, .6, .6 if is_wrist else .15)
    lower = [min(p[i] for p in points)-padding[i] for i in range(3)]
    upper = [max(p[i] for p in points)+padding[i] for i in range(3)]
    _require(all(review["workspace_min_mm"][i] <= lower[i] < upper[i] <= review["workspace_max_mm"][i]
                 for i in range(3)), "UNIT_EXCEEDS_REVIEWED_SITE_BOUNDS")
    local = {**{key: deepcopy(old[key]) for key in LocalContactInstallation.model_fields},
        "scope": "local_contact_commissioning", "installation_id": installation_id,
        "review_reference": review_reference or review["review_reference"], "workspace_min_mm": lower, "workspace_max_mm": upper,
        "fixed_tcp_z_mm": source[2], "fixed_orientation_deg": list(source[3:]),
        "trial_max_step_mm": review["max_step_mm"]}
    robot = {"actual_pose": list(source), "actual_joint": list(joints)}
    if not is_wrist:
        return local, contact_profile(local, robot, on_site_review=True)
    if inspected_source_joint is not None:
        _require(_near(inspected_source_joint, joints, NATIVE_BASELINE_COMPARISON_QUANTIZATION)
            and _near(inspected_source_joint, native.joints_deg, NATIVE_BASELINE_COMPARISON_QUANTIZATION),
            "INSPECTED_JOINT_NATIVE_DISAGREEMENT")
    # Native FC03 joints are quantized to 0.1 degree. Preserve their exact
    # baseline in the wire profile, but derive directed wrist targets from the
    # fresh full-precision inspect_current result whenever preparation has it.
    wrist = resolve_wrist_descriptor(measured, review, source,
        inspected_source_joint if inspected_source_joint is not None else joints, wrist)
    target = list(measured.stages[0].target_base)
    sj, tj = wrist["expected_source_joint_deg"], wrist["expected_target_joint_deg"]
    _require(target[:3] == list(source[:3]) and _pose(sj) and _pose(tj)
        and all(abs(v) <= 360 for v in (*sj, *tj)) and list(sj[:5]) == list(tj[:5])
        and 0 < abs(tj[5]-sj[5]) <= 90.
        and _near(sj, joints, NATIVE_BASELINE_COMPARISON_QUANTIZATION), "DIRECTED_WRIST_WINDING_REQUIRED")
    runtime = deepcopy(wrist["rotation_runtime"])
    _require(runtime.get("verified") is True and runtime.get("primitive") == "moveJoint_wrist"
        and runtime.get("speed_argument") == 5. and runtime.get("accel_argument") == 10.
        and 15 <= runtime.get("completion_timeout_s", 0) <= 150, "ORIGINAL_WRIST_RUNTIME_REQUIRED")
    ref = local["review_reference"]
    local.update(scope="local_contact_turn_commissioning", contact_turn_trials_authorized=True,
        max_rotation_increment_deg=90., rotation_runtime=runtime,
        orientations=[{"id": "current", "rxyz_deg": list(source[3:])}, {"id": "target", "rxyz_deg": target[3:]}],
        rotation_anchors=[{"id": "withdrawn-anchor", "xyz_base_mm": list(source[:3]), "site_verified": True,
            "review_reference": ref, "position_window_mm": .5, "max_in_place_correction_mm": .1,
            "window_and_correction_reviewed": True}],
        rotation_edges=[{"id": wrist["edge_id"], "from": "current", "to": "target", "anchor_id": "withdrawn-anchor",
            "site_verified": True, "review_reference": ref, "expected_source_joint_deg": list(sj),
            "expected_target_joint_deg": list(tj), "wrist_only": True, "joint_path_reviewed": True}])
    return local, wrist_profile(local, robot, on_site_review=True)


class ReviewedProfilePreparer:
    """One serialized preparation with durable intent and no automatic resend.

    api(path, payload=None) is the existing authenticated local guarded API.
    native_snapshot() returns Snapshot with fresh independent Native evidence.
    The owner must serialize this operation against every motion operation.
    A durable unresolved prep blocks a new preparer until external reconciliation.
    """
    def __init__(self, *, api, journal, native_snapshot, receiver_policy, stop_check,
                 clock=time.time, monotonic=time.monotonic, sleep=time.sleep):
        self.api, self.journal, self.native_snapshot = api, journal, native_snapshot
        self.receiver_policy, self.stop_check = receiver_policy, stop_check
        self.clock, self.monotonic, self.sleep = clock, monotonic, sleep
        self.failed = False
        previous = journal.load()
        _require(not previous or previous.get("state") not in
            {"PROFILE_PREPARATION_UNRESOLVED", "PROFILE_PREPARATION_FAILED"}, "PROFILE_PREPARATION_RECONCILIATION_REQUIRED")

    def _idle(self):
        self.stop_check()
        status = self.api("/v1/status")
        receiver = status.get("receiver", {})
        _require(status.get("hold") is True and status.get("armed") is False and status.get("active_commands") == []
            and receiver.get("connected") is True and receiver.get("idle") is True
            and receiver.get("physical_execution") is True and not receiver.get("profile_pending")
            and receiver.get("reason") != "RECEIVER_RECONCILIATION_REQUIRED", "HELD_IDLE_RECEIVER_REQUIRED")
        return status

    @staticmethod
    def _binding(status):
        return {key: status["receiver"][key] for key in ("session_id", "seq", "profile_id")}

    def _same_source(self, status, source, joints, session):
        receiver = status["receiver"]
        _require(receiver["session_id"] == session and tuple(receiver["actual_pose"]) == tuple(source)
            and _near(receiver["actual_joint"], joints, NATIVE_BASELINE_COMPARISON_QUANTIZATION), "PROFILE_SOURCE_CHANGED")

    def _query(self, kind, installation_id, expected, source, joints, *, target=None, profile=None):
        current = self._idle()
        _require(self._binding(current) == expected, "PROFILE_COMMAND_BASELINE_CHANGED")
        self._same_source(current, source, joints, expected["session_id"])
        command = {"request_id": str(uuid4()), "kind": kind, "purpose": "commissioning",
            "installation_id": installation_id, "expected_receiver": expected,
            "timeout_seconds": 30., "admission_timeout_seconds": 10.}
        if target is not None:
            command["target"] = list(target)
        if profile is not None:
            command["profile"] = profile
        self.journal.artifact("profile-query-intent", command)
        self.stop_check()
        self.api("/v1/commands", command)  # Exactly once, even after transport ambiguity.
        deadline = self.monotonic()+40.
        while True:
            self.stop_check()
            job = self.api("/v1/commands/"+command["request_id"])
            if job.get("state") in {"complete", "rejected", "cancelled", "outcome_unknown"}:
                break
            _require(self.monotonic() < deadline, "PROFILE_QUERY_OUTCOME_UNRESOLVED")
            self.sleep(.15)
        self.journal.artifact("profile-query-result", job)
        _require(job.get("state") == "complete", "PROFILE_QUERY_OUTCOME_UNRESOLVED")
        receipt = job.get("result", {}).get("robot_receipt", {})
        expected_kind = "profile_applied_verified" if kind == "profile_update" else "ik_result_verified"
        _require(receipt.get("kind") == expected_kind, "PROFILE_QUERY_RECEIPT_MISMATCH")
        after = self._idle()
        self._same_source(after, source, joints, expected["session_id"])
        _require(after["receiver"]["seq"] == expected["seq"]+1, "PROFILE_QUERY_SEQUENCE_CHANGED")
        if kind != "profile_update":
            _require(after["receiver"]["profile_id"] == expected["profile_id"], "INSPECTION_CHANGED_PROFILE")
        else:
            _require(after["receiver"].get("profile") == profile, "APPLIED_PROFILE_READBACK_MISMATCH")
        return receipt.get("data", {}), after

    def prepare(self, measured, review, expected_receiver, *, operation_id, wrist=None):
        _require(not self.failed, "PROFILE_PREPARATION_RECONCILIATION_REQUIRED")
        _require(isinstance(operation_id, str) and 1 <= len(operation_id) <= 200, "NEW_PREPARATION_ID_REQUIRED")
        review = validate_site_review(review)
        marker = Path(self.journal.root) / ("profile-prep-"+hashlib.sha256(operation_id.encode()).hexdigest()+".private.json")
        # O_EXCL survives a crash/restart. Never regenerate an unknown operation.
        write_new(marker, json.dumps({"operation_id": operation_id, "geometry_sha256": measured.geometry_sha256,
            "review_sha256": content_hash(review), "automatic_replay": False}).encode())
        sync_directory(self.journal.root)
        self.journal.checkpoint({"state": "PROFILE_PREPARATION_UNRESOLVED", "operation_id": operation_id,
                                 "automatic_replay": False})
        try:
            before = self._idle()
            _require(self._binding(before) == expected_receiver, "PROFILE_PREPARATION_BASELINE_CHANGED")
            native = self.native_snapshot()
            _require(isinstance(native, Snapshot) and _sha(native.native_evidence_sha256)
                and 0 <= self.clock()-native.native_observed_at <= 5.
                and (native.session_id, native.sequence, native.profile_id) ==
                    tuple(expected_receiver[k] for k in ("session_id", "seq", "profile_id")), "FRESH_NATIVE_SOURCE_REQUIRED")
            source, joints = before["receiver"]["actual_pose"], before["receiver"]["actual_joint"]
            resolved_wrist = None
            installation_id = "mission-unit-"+uuid4().hex
            review_path, _ = self.journal.artifact("unit-current-site-review", {
                "supplied_site_review": review, "actual_native_source": asdict(native),
                "geometry_sha256": measured.geometry_sha256, "scope_derivation_only": True,
                "new_physical_clearance_measurement": False, "motion_issued": False})
            local, profile = build_unit_profile(measured, review, before, native,
                installation_id=installation_id, wrist=wrist, review_reference=str(review_path))
            current, status = self._query("inspect_current", before["installation"]["installation_id"],
                expected_receiver, source, joints)
            _require(current.get("status") == "ok" and current.get("motion_issued") is False
                and _near(current.get("source_pose"), source, NATIVE_BASELINE_COMPARISON_QUANTIZATION)
                and _near(current.get("source_joint"), joints, NATIVE_BASELINE_COMPARISON_QUANTIZATION),
                "CURRENT_IK_INSPECTION_FAILED")
            if measured.kind == "wrist_edge":
                resolved_wrist = resolve_wrist_descriptor(measured, review, source, current["source_joint"], wrist)
                local, profile = build_unit_profile(measured, review, before, native,
                    installation_id=installation_id, wrist=wrist, review_reference=str(review_path),
                    inspected_source_joint=current["source_joint"])
            self.receiver_policy.valid(profile, True)
            _require(len(json.dumps(profile, ensure_ascii=True, allow_nan=False).encode("ascii")) <=
                self.receiver_policy.MAX_PROFILE_BYTES, "RECEIVER_PROFILE_SIZE_EXCEEDED")
            self.journal.artifact("profile-preparation-source", {"review": review, "native": asdict(native),
                "current_inspection": current, "installation": local, "profile": profile,
                "geometry_sha256": measured.geometry_sha256,
                "vehicle_control_qualified": False, "board_registration_qualified": False})
            # The receiver also bounds read-only IK query targets against its
            # installed profile. Apply this exact reviewed unit while held and
            # disarmed before inspecting targets outside the previous unit.
            # Profile application grants no motion; every IK and final Native
            # check must still pass before the caller can dispatch anything.
            latest = self._idle()
            _require(self._binding(latest) == self._binding(status), "PROFILE_INSTALL_BASELINE_CHANGED")
            self._same_source(latest, source, joints, expected_receiver["session_id"])
            self.journal.artifact("profile-install-intent", {"installation": local, "expected_receiver": self._binding(latest)})
            self.stop_check()
            self.api("/v1/installation", local)
            installed = self._idle()
            _require(installed.get("installation") == local and self._binding(installed) == self._binding(latest),
                     "INSTALLATION_READBACK_MISMATCH")
            _, status = self._query("profile_update", installation_id, self._binding(installed), source, joints, profile=profile)
            # A profile update invalidates the receiver's read-only IK baseline.
            # Re-establish it under the installed profile; retain the original
            # precise inspection as an independent stationary-source check.
            applied_current, status = self._query("inspect_current", installation_id,
                self._binding(status), source, joints)
            _require(applied_current.get("status") == "ok" and applied_current.get("motion_issued") is False
                and _near(applied_current.get("source_pose"), source, NATIVE_BASELINE_COMPARISON_QUANTIZATION)
                and _near(applied_current.get("source_joint"), joints, NATIVE_BASELINE_COMPARISON_QUANTIZATION)
                and _near(applied_current.get("source_joint"), current["source_joint"], .05),
                "APPLIED_PROFILE_CURRENT_IK_FAILED")
            for stage in measured.stages:
                checked, status = self._query("inspect_ik", installation_id,
                    self._binding(status), source, joints, target=stage.target_base)
                _require(checked.get("status") == "ok" and checked.get("motion_issued") is False
                    and _near(checked.get("source_pose"), source, NATIVE_BASELINE_COMPARISON_QUANTIZATION)
                    and _near(checked.get("source_joint"), joints, NATIVE_BASELINE_COMPARISON_QUANTIZATION)
                    and _near(checked.get("source_joint"), current["source_joint"], .05)
                    and _near(checked.get("target_fk"), stage.target_base)
                    and _pose(checked.get("solution_joint")), "TARGET_IK_INSPECTION_FAILED")
                if measured.kind == "wrist_edge":
                    verify_endpoint_ik({"schema": "pushpilot.wrist-turn-candidate.v1", "motion_authority": False,
                        "source_pose": source, "target_pose": list(stage.target_base),
                        "source_joint": resolved_wrist["expected_source_joint_deg"],
                        "target_joint": resolved_wrist["expected_target_joint_deg"]}, checked)
            after = self._idle()
            _require(self._binding(after) == self._binding(status), "PROFILE_FINAL_BASELINE_CHANGED")
            self._same_source(after, source, joints, expected_receiver["session_id"])
            final_native = self.native_snapshot()
            _require(isinstance(final_native, Snapshot) and _sha(final_native.native_evidence_sha256)
                and 0 <= self.clock()-final_native.native_observed_at <= 5.
                and (final_native.session_id, final_native.sequence, final_native.profile_id) ==
                    tuple(self._binding(after)[k] for k in ("session_id", "seq", "profile_id"))
                and final_native.held_disarmed_idle
                and _near(final_native.native_tcp_base, source, NATIVE_BASELINE_COMPARISON_QUANTIZATION)
                and tuple(final_native.tcp_base) == tuple(source)
                and _near(final_native.joints_deg, joints, NATIVE_BASELINE_COMPARISON_QUANTIZATION),
                "PROFILE_FINAL_NATIVE_UNCONFIRMED")
            _require(_native_identity(final_native, local), "PROFILE_FINAL_NATIVE_IDENTITY_CHANGED")
            result = {"operation_id": operation_id, "installation": local, "profile": profile,
                "expected_receiver": self._binding(after), "geometry_sha256": measured.geometry_sha256,
                "review_sha256": content_hash(review), "profile_handoff_verified": True, "motion_issued": False,
                "car_turn_qualified": False, "vehicle_control_qualified": False, "board_registration_qualified": False,
                "receiver_nineteen_joint_fk_samples_still_required": measured.kind == "wrist_edge",
                "exact_joint_path_fk_verified": False, "native": asdict(final_native),
                "inspected_source_joint_deg": current["source_joint"],
                "status": after, "wrist": resolved_wrist,
                "wrist_intent_sha256": content_hash(wrist) if wrist is not None else None}
            self.journal.artifact("profile-preparation-complete", result)
            self.journal.checkpoint({"state": "PROFILE_PREPARATION_COMPLETE", "operation_id": operation_id,
                "expected_receiver": result["expected_receiver"], "automatic_replay": False})
            return result
        except Exception as error:
            self.failed = True
            self.journal.checkpoint({"state": "PROFILE_PREPARATION_FAILED", "operation_id": operation_id,
                "error_code": getattr(error, "code", type(error).__name__), "automatic_replay": False})
            raise
