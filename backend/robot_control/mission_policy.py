"""Pure, bounded mission policy for qualified coordinate primitives.

The policy emits primitive IDs, never robot coordinates or image-derived TCPs.
The service must durably persist ``decision.state`` before dispatch and execute
the ID through the existing Native/profile/coordinate-unit admission checks.
Constructing a qualification hash here does not qualify a physical trajectory.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import math
import re


def _number(value, *, minimum=None, maximum=None):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or minimum is not None and value < minimum
            or maximum is not None and value > maximum):
        raise ValueError("Expected a finite value within its declared bounds.")


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("Expected a nonempty bounded identity.")


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected an original evidence SHA-256.")


def angle_error(actual: float, target: float, *, parallel_axis=False) -> float:
    """Signed degrees; parallel parking may accept either nose direction."""
    period = 180. if parallel_axis else 360.
    return (actual - target + period / 2) % period - period / 2


class Phase(StrEnum):
    READY = "READY"
    IN_FLIGHT = "IN_FLIGHT"
    OBSERVE = "OBSERVE"
    WAIT_SIGNAL = "WAIT_SIGNAL"
    ENTRY_SIGNAL = "ENTRY_SIGNAL"
    ADMITTED_ENTRY = "ADMITTED_ENTRY"
    RETURNING = "RETURNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"


class DecisionKind(StrEnum):
    DISPATCH = "DISPATCH"
    OBSERVE = "OBSERVE"
    WAIT = "WAIT"
    COMPLETE = "COMPLETE"
    HOLD = "HOLD"


@dataclass(frozen=True)
class SiteBinding:
    installation_id: str
    map_sha256: str
    calibration_id: str
    tool_id: str
    car_id: str
    camera_epoch: str

    def __post_init__(self):
        for value in vars(self).values():
            _name(value)
        _sha(self.map_sha256)


@dataclass(frozen=True)
class TaughtPrimitive:
    id: str
    source_context_id: str
    target_context_id: str
    qualification_sha256: str
    qualified: bool = False
    empty_tool: bool = False
    release_mode: str = "qualified"
    current_site_review_sha256: str | None = None

    def __post_init__(self):
        for value in (self.id, self.source_context_id, self.target_context_id):
            _name(value)
        _sha(self.qualification_sha256)
        if type(self.qualified) is not bool or type(self.empty_tool) is not bool:
            raise ValueError("Qualification and empty-tool declarations are explicit booleans.")
        if self.release_mode not in {"qualified", "site_trial"}:
            raise ValueError("Use an explicit physical release mode.")
        if self.release_mode == "site_trial":
            _sha(self.current_site_review_sha256)
            if self.qualified:
                raise ValueError("A current-site trial cannot claim repeatability qualification.")


@dataclass(frozen=True)
class SignalGate:
    id: str
    right_wait_context_id: str
    last_contact_context_id: str
    recontact: TaughtPrimitive
    release_to_wait: TaughtPrimitive
    green_valid_for_s: float = 15.
    entry_policy: str = "fresh_entry"

    def __post_init__(self):
        for value in (self.id, self.right_wait_context_id, self.last_contact_context_id):
            _name(value)
        _number(self.green_valid_for_s, minimum=.1, maximum=30.)
        if self.entry_policy not in {"fresh_entry", "single_departure"}:
            raise ValueError("Select an explicit signal admission policy.")
        if (self.right_wait_context_id == self.last_contact_context_id
                or (self.recontact.source_context_id, self.recontact.target_context_id) !=
                    (self.right_wait_context_id, self.last_contact_context_id)
                or (self.release_to_wait.source_context_id, self.release_to_wait.target_context_id) !=
                    (self.last_contact_context_id, self.right_wait_context_id)
                or not self.release_to_wait.empty_tool):
            raise ValueError("Bind distinct RIGHT observation and last CONTACT contexts and their reviewed paths.")


@dataclass(frozen=True)
class RouteStep:
    id: str
    primitive: TaughtPrimitive
    car_zone_id: str
    expected_heading_deg: float
    at_goal: bool = False
    signal_gate: SignalGate | None = None
    observation_required: bool = True
    review_mode: str = "expected_outcome"

    def __post_init__(self):
        _name(self.id)
        _name(self.car_zone_id)
        _number(self.expected_heading_deg, minimum=-180., maximum=180.)
        if self.review_mode not in {"expected_outcome", "intermediate_progress"}:
            raise ValueError("Use an explicit observation policy.")
        if self.review_mode == "intermediate_progress" and (self.at_goal or self.primitive.empty_tool):
            raise ValueError("Progress-only review applies only to intermediate loaded units.")
        if type(self.at_goal) is not bool:
            raise ValueError("Goal membership must be explicit.")
        if type(self.observation_required) is not bool or (not self.observation_required
                and (not self.primitive.empty_tool or self.at_goal or self.signal_gate)):
            raise ValueError("Only unloaded intermediate repositioning can omit a car outcome review.")
        if self.signal_gate and self.primitive.target_context_id != self.signal_gate.right_wait_context_id:
            raise ValueError("A signal-stop step must finish at its selected far-RIGHT wait park.")


@dataclass(frozen=True)
class CorrectionTemplate:
    """Measured response envelope attached to one finite coordinate primitive."""
    primitive: TaughtPrimitive
    step_id: str
    car_zone_id: str
    yaw_error_range_deg: tuple[float, float]
    lateral_error_range_mm: tuple[float, float]
    expected_yaw_change_deg: float
    expected_lateral_change_mm: float
    parking_only: bool = False

    def __post_init__(self):
        _name(self.step_id)
        _name(self.car_zone_id)
        for name in ("yaw_error_range_deg", "lateral_error_range_mm"):
            values = tuple(getattr(self, name))
            if len(values) != 2:
                raise ValueError("A correction envelope needs lower and upper limits.")
            for value in values:
                _number(value)
            if values[0] > values[1]:
                raise ValueError("Correction envelope limits are reversed.")
            object.__setattr__(self, name, values)
        _number(self.expected_yaw_change_deg, minimum=-45., maximum=45.)
        _number(self.expected_lateral_change_mm, minimum=-40., maximum=40.)
        if self.primitive.empty_tool or type(self.parking_only) is not bool:
            raise ValueError("A correction is an explicitly qualified vehicle contact primitive.")


@dataclass(frozen=True)
class ViewClearance:
    primitive: TaughtPrimitive
    step_id: str
    side: str
    car_visible_qualified: bool
    signal_visible_qualified: bool = False
    occlusion_causes: tuple[str, ...] = ("TOOL", "HOSE", "UNKNOWN")
    restore: TaughtPrimitive | None = None

    def __post_init__(self):
        _name(self.step_id)
        if self.side not in {"RIGHT", "LEFT"} or not self.primitive.empty_tool:
            raise ValueError("View clearance uses a qualified empty-tool RIGHT or LEFT path.")
        if (type(self.car_visible_qualified) is not bool
                or type(self.signal_visible_qualified) is not bool):
            raise ValueError("Visibility qualification must be explicit.")
        causes = tuple(self.occlusion_causes)
        if not causes or any(c not in {"TOOL", "HOSE", "HAND", "UNKNOWN"} for c in causes):
            raise ValueError("Use declared observation occlusion causes.")
        object.__setattr__(self, "occlusion_causes", causes)
        if self.restore is not None and (not self.restore.empty_tool
                or (self.restore.source_context_id, self.restore.target_context_id) !=
                    (self.primitive.target_context_id, self.primitive.source_context_id)):
            raise ValueError("A clearance restore is a separately reviewed empty return to the original observation context.")


@dataclass(frozen=True)
class ParkingTarget:
    heading_deg: float
    tolerance_deg: float = 15.
    parallel_axis: bool = True
    lateral_tolerance_mm: float | None = None
    mode: str = "parallel_alignment"

    def __post_init__(self):
        _number(self.heading_deg, minimum=-180., maximum=180.)
        _number(self.tolerance_deg, minimum=1., maximum=20.)
        if type(self.parallel_axis) is not bool:
            raise ValueError("Parallel-axis parking must be explicitly selected.")
        if self.lateral_tolerance_mm is not None:
            _number(self.lateral_tolerance_mm, minimum=.1, maximum=20.)
        if self.mode not in {"parallel_alignment", "delivery_only"}:
            raise ValueError("Explicitly select parallel_alignment or delivery_only completion.")


@dataclass(frozen=True)
class MissionPlan:
    id: str
    destination: str
    binding: SiteBinding
    steps: tuple[RouteStep, ...]
    parking: ParkingTarget
    empty_return: tuple[TaughtPrimitive, ...]
    start_context_id: str
    corrections: tuple[CorrectionTemplate, ...] = ()
    clearances: tuple[ViewClearance, ...] = ()
    max_corrections_per_step: int = 3
    max_reobservations: int = 3
    max_clearances_per_step: int = 2
    max_nonimproving_corrections: int = 2
    max_green_expirations: int = 2
    car_max_age_s: float = 30.
    signal_max_age_s: float = 15.
    native_max_age_s: float = 5.
    route_heading_tolerance_deg: float = 15.
    release_mode: str = "qualified"

    def __post_init__(self):
        for value in (self.id, self.destination, self.start_context_id):
            _name(value)
        if self.release_mode not in {"qualified", "site_trial"}:
            raise ValueError("Use an explicit physical release mode.")
        if self.release_mode == "site_trial" and (self.parking.mode != "delivery_only" or self.corrections):
            raise ValueError("The current-site delivery trial excludes unqualified numeric corrections.")
        if any(s.review_mode == "intermediate_progress" for s in self.steps) and (
                self.release_mode != "site_trial" or self.parking.mode != "delivery_only" or self.corrections):
            raise ValueError("Progress-only review is an explicit delivery trial, not metric qualification.")
        for name in ("steps", "empty_return", "corrections", "clearances"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if (not self.steps or not self.steps[-1].at_goal
                or any(s.at_goal for s in self.steps[:-1])
                or len({s.id for s in self.steps}) != len(self.steps)
                or not self.empty_return or any(not p.empty_tool for p in self.empty_return)
                or self.empty_return[-1].target_context_id != self.start_context_id):
            raise ValueError("Use a finite route with one final goal and a separate empty-tool return to START.")
        for a, b in zip(self.steps, self.steps[1:]):
            source = a.signal_gate.last_contact_context_id if a.signal_gate else a.primitive.target_context_id
            if source != b.primitive.source_context_id:
                raise ValueError("Route continuity must include the signal recontact endpoint.")
        if any(a.target_context_id != b.source_context_id for a, b in zip(self.empty_return, self.empty_return[1:])):
            raise ValueError("The empty return must be a continuous reviewed path.")
        if any(c.step_id not in {s.id for s in self.steps} for c in self.corrections + self.clearances):
            raise ValueError("Every correction/clearance belongs to an existing route step.")
        for name in ("max_corrections_per_step", "max_reobservations", "max_clearances_per_step",
                     "max_nonimproving_corrections", "max_green_expirations"):
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= 10:
                raise ValueError("Recovery budgets must be finite positive integers.")
        for name, maximum in (("car_max_age_s", 120.), ("signal_max_age_s", 30.), ("native_max_age_s", 5.)):
            _number(getattr(self, name), minimum=.1, maximum=maximum)
        _number(self.route_heading_tolerance_deg, minimum=1., maximum=20.)


@dataclass(frozen=True)
class RuntimeContext:
    now_s: float
    binding: SiteBinding
    session_id: str
    native_sequence: int
    native_observed_at_s: float
    context_id: str
    stationary: bool
    tool_clear: bool
    pending_command_id: str | None = None
    control_fault: str | None = None

    def __post_init__(self):
        _number(self.now_s, minimum=0)
        _number(self.native_observed_at_s, minimum=0)
        _name(self.session_id)
        _name(self.context_id)
        if (type(self.native_sequence) is not int or self.native_sequence < 0
                or type(self.stationary) is not bool or type(self.tool_clear) is not bool):
            raise ValueError("Use literal Native sequence and stationary/clearance facts.")


@dataclass(frozen=True)
class CarObservation:
    mission_id: str
    step_id: str
    action_command_id: str
    binding: SiteBinding
    session_id: str
    native_sequence: int
    context_id: str
    captured_at_s: float
    image_sha256: str
    provider_receipt_sha256: str
    verdict: str
    car_visible: bool
    within_road: bool | None
    expected_progress: bool
    heading_matches_expected: bool
    arrived: bool
    car_zone_id: str | None
    heading_deg: float | None = None
    heading_uncertainty_deg: float | None = None
    lateral_error_mm: float | None = None
    lateral_uncertainty_mm: float | None = None
    measurement_source: str = "unmeasured"
    measurement_evidence_sha256: str | None = None
    occlusion_cause: str = "NONE"
    signal_visible: bool = False
    progress_status: str | None = None
    visible_change: bool | None = None
    clear_problem: bool | None = None

    def __post_init__(self):
        for name in ("mission_id", "step_id", "action_command_id", "session_id", "context_id"):
            _name(getattr(self, name))
        _sha(self.image_sha256)
        _sha(self.provider_receipt_sha256)
        _number(self.captured_at_s, minimum=0)
        if self.verdict not in {"PASS", "FAIL", "UNCERTAIN"}:
            raise ValueError("Use the original model verdict.")
        if self.progress_status not in {None, "PROGRESS_OBSERVED", "NO_PROGRESS", "UNCERTAIN", "CLEAR_PROBLEM"}:
            raise ValueError("Use the original progress status.")
        if any(v is not None and type(v) is not bool for v in (self.visible_change, self.clear_problem)):
            raise ValueError("Progress facts must be boolean or unknown.")
        if (any(type(getattr(self, name)) is not bool for name in
                ("car_visible", "expected_progress", "heading_matches_expected", "arrived", "signal_visible"))
                or self.within_road is not None and type(self.within_road) is not bool
                or type(self.native_sequence) is not int or self.native_sequence < 0):
            raise ValueError("Use actual boolean judgments and the exact Native sequence.")
        if self.measurement_source not in {"qualified_estimator", "muse_estimate", "unmeasured"}:
            raise ValueError("Declare numeric pose provenance independently of qualitative MUSE judgment.")
        for name in ("heading_deg", "lateral_error_mm"):
            if getattr(self, name) is not None:
                _number(getattr(self, name))
        for name in ("heading_uncertainty_deg", "lateral_uncertainty_mm"):
            if getattr(self, name) is not None:
                _number(getattr(self, name), minimum=0)
        if self.measurement_source == "qualified_estimator":
            _sha(self.measurement_evidence_sha256)
        if self.occlusion_cause not in {"NONE", "TOOL", "HOSE", "HAND", "UNKNOWN"}:
            raise ValueError("Use a declared occlusion cause.")

    @property
    def measured_heading(self):
        return (self.measurement_source == "qualified_estimator" and self.heading_deg is not None
                and self.heading_uncertainty_deg is not None)

    @property
    def measured_lateral(self):
        return (self.measurement_source == "qualified_estimator" and self.lateral_error_mm is not None
                and self.lateral_uncertainty_mm is not None)


@dataclass(frozen=True)
class StartObservation:
    """One pre-mission car check, not an approach-time vision control loop."""
    mission_id: str
    binding: SiteBinding
    session_id: str
    native_sequence: int
    context_id: str
    captured_at_s: float
    image_sha256: str
    provider_receipt_sha256: str
    car_visible: bool
    at_fixed_start: bool
    heading_matches_start: bool
    within_road: bool

    def __post_init__(self):
        _sha(self.image_sha256)
        _sha(self.provider_receipt_sha256)
        _number(self.captured_at_s, minimum=0)
        if any(type(getattr(self, name)) is not bool for name in
               ("car_visible", "at_fixed_start", "heading_matches_start", "within_road")):
            raise ValueError("Initial car checks must be explicit booleans.")


@dataclass(frozen=True)
class SignalObservation:
    gate_id: str
    binding: SiteBinding
    session_id: str
    native_sequence: int
    context_id: str
    captured_at_s: float
    image_sha256: str
    provider_receipt_sha256: str
    color: str
    car_visible: bool
    signal_visible: bool
    car_unchanged_since_stop: bool
    exclusive_green: bool = False

    def __post_init__(self):
        for name in ("gate_id", "session_id", "context_id"):
            _name(getattr(self, name))
        _sha(self.image_sha256)
        _sha(self.provider_receipt_sha256)
        _number(self.captured_at_s, minimum=0)
        if self.color not in {"RED", "GREEN", "UNKNOWN"}:
            raise ValueError("Only a fresh unambiguous GREEN may release a stop.")
        if (any(type(getattr(self, name)) is not bool for name in
                ("car_visible", "signal_visible", "car_unchanged_since_stop", "exclusive_green"))
                or type(self.native_sequence) is not int or self.native_sequence < 0):
            raise ValueError("Use explicit signal visibility/consistency and Native facts.")


@dataclass(frozen=True)
class MotionReceipt:
    command_id: str
    primitive_id: str
    session_id: str
    target_context_id: str
    completed_at_s: float
    native_verified: bool
    outcome: str  # COMPLETED, REJECTED_BEFORE_DISPATCH, UNKNOWN, FAILED


@dataclass(frozen=True)
class MissionState:
    mission_id: str
    session_id: str
    phase: Phase = Phase.READY
    step_index: int = 0
    return_index: int = 0
    pending_command_id: str | None = None
    pending_primitive_id: str | None = None
    pending_target_context_id: str | None = None
    pending_role: str | None = None
    pending_since_s: float | None = None
    resume_phase: Phase | None = None
    action_command_id: str | None = None
    last_motion_completed_at_s: float = 0.
    correction_count: int = 0
    reobservations: int = 0
    used_clearances: tuple[str, ...] = ()
    seen_images: tuple[str, ...] = ()
    issued_command_ids: tuple[str, ...] = ()
    before_correction_score: float | None = None
    nonimproving_corrections: int = 0
    signal_step_index: int | None = None
    green_expires_at_s: float | None = None
    admitted_signal_step_index: int | None = None
    green_expirations: int = 0
    green_image_sha256s: tuple[str, ...] = ()
    green_last_captured_at_s: float = 0.
    vehicle_delivered: bool = False
    start_verified: bool = False
    reason: str = "READY"


@dataclass(frozen=True)
class PolicyDecision:
    kind: DecisionKind
    state: MissionState
    reason: str
    primitive_id: str | None = None
    command_id: str | None = None


class MissionPolicy:
    """Deterministic coordinator; every call is IO-free and returns frozen state."""

    def __init__(self, plan: MissionPlan):
        self.plan = plan

    def initial_state(self, session_id: str) -> MissionState:
        _name(session_id)
        return MissionState(self.plan.id, session_id)

    @staticmethod
    def restart(state: MissionState) -> MissionState:
        return replace(state, phase=Phase.NEEDS_RECONCILIATION, reason="RESTART_REQUIRES_RECONCILIATION")

    @staticmethod
    def _decision(kind, state, reason, primitive=None, command=None):
        return PolicyDecision(kind, replace(state, reason=reason), reason, primitive, command)

    def _fail(self, state, reason, *, reconcile=False):
        return self._decision(DecisionKind.HOLD, replace(state,
            phase=Phase.NEEDS_RECONCILIATION if reconcile else Phase.FAILED), reason)

    def _admitted(self, primitive):
        if self.plan.release_mode == "qualified":
            return primitive.qualified and primitive.release_mode == "qualified"
        return (primitive.release_mode == "site_trial" and not primitive.qualified
                and primitive.current_site_review_sha256 is not None)

    def _dispatch(self, state, context, primitive, role, command_id, **changes):
        if not self._admitted(primitive):
            return self._fail(state, "PRIMITIVE_NOT_QUALIFIED:" + primitive.id)
        if primitive.source_context_id != context.context_id:
            if role in {"ROUTE", "RETURN"}:
                restores = [c.restore for c in self.plan.clearances if c.restore is not None
                    and self._admitted(c.restore) and c.restore.source_context_id == context.context_id
                    and c.restore.target_context_id == primitive.source_context_id]
                if restores:
                    restore = sorted(restores, key=lambda p: p.id)[0]
                    return self._dispatch(state, context, restore, "RESTORE", command_id,
                                          resume_phase=state.phase)
            return self._fail(state, "PRIMITIVE_SOURCE_MISMATCH", reconcile=True)
        if not isinstance(command_id, str) or not command_id or command_id in state.issued_command_ids:
            return self._fail(state, "NEW_DURABLE_COMMAND_ID_REQUIRED", reconcile=True)
        if primitive.empty_tool and not context.tool_clear and role != "RELEASE_EXPIRED_GREEN":
            return self._fail(state, "EMPTY_TOOL_CLEARANCE_UNCONFIRMED")
        next_state = replace(state, phase=Phase.IN_FLIGHT, pending_command_id=command_id,
            pending_primitive_id=primitive.id, pending_target_context_id=primitive.target_context_id,
            pending_role=role, pending_since_s=context.now_s,
            issued_command_ids=(*state.issued_command_ids, command_id), **changes)
        return self._decision(DecisionKind.DISPATCH, next_state, role, primitive.id, command_id)

    def accept_receipt(self, state: MissionState, receipt: MotionReceipt) -> MissionState:
        """Unknown dispatch/receipt never becomes an automatic retry or retreat."""
        if (state.phase != Phase.IN_FLIGHT or receipt.command_id != state.pending_command_id
                or receipt.primitive_id != state.pending_primitive_id or receipt.session_id != state.session_id
                or receipt.target_context_id != state.pending_target_context_id
                or not receipt.native_verified or receipt.outcome != "COMPLETED"
                or type(receipt.completed_at_s) not in (int, float) or not math.isfinite(receipt.completed_at_s)
                or receipt.completed_at_s < state.pending_since_s):
            return replace(state, phase=Phase.NEEDS_RECONCILIATION, reason="MOTION_OUTCOME_UNRESOLVED")
        role = state.pending_role
        next_state = replace(state, pending_command_id=None, pending_primitive_id=None,
            pending_target_context_id=None, pending_role=None, pending_since_s=None,
            last_motion_completed_at_s=receipt.completed_at_s, reobservations=0)
        if role == "RETURN":
            return replace(next_state, phase=Phase.RETURNING, return_index=state.return_index + 1)
        if role == "RECONTACT":
            gate = self.plan.steps[state.step_index].signal_gate
            phase = Phase.ADMITTED_ENTRY if gate.entry_policy == "single_departure" else Phase.ENTRY_SIGNAL
            return replace(next_state, phase=phase, step_index=state.step_index + 1,
                           green_image_sha256s=(), green_last_captured_at_s=0.)
        if role == "RELEASE_EXPIRED_GREEN":
            return replace(next_state, phase=Phase.WAIT_SIGNAL, step_index=state.signal_step_index,
                           green_expires_at_s=None)
        if role == "CLEARANCE":
            return replace(next_state, phase=state.resume_phase or Phase.OBSERVE, resume_phase=None)
        if role == "RESTORE":
            return replace(next_state, phase=state.resume_phase, resume_phase=None)
        if role == "ROUTE" and not self.plan.steps[state.step_index].observation_required:
            return replace(next_state, phase=Phase.READY, step_index=state.step_index + 1)
        return replace(next_state, phase=Phase.OBSERVE, action_command_id=receipt.command_id)

    def _valid_car(self, state, context, car):
        return (car is not None and car.mission_id == self.plan.id
            and car.step_id == self.plan.steps[state.step_index].id
            and car.action_command_id == state.action_command_id
            and (car.binding, car.session_id, car.native_sequence, car.context_id) ==
                (self.plan.binding, context.session_id, context.native_sequence, context.context_id)
            and state.last_motion_completed_at_s <= car.captured_at_s <= context.now_s
            and context.now_s - car.captured_at_s <= self.plan.car_max_age_s)

    def _reobserve(self, state, reason):
        if state.reobservations >= self.plan.max_reobservations:
            return self._fail(state, "OBSERVATION_BUDGET_EXHAUSTED:" + reason)
        return self._decision(DecisionKind.OBSERVE,
            replace(state, reobservations=state.reobservations + 1), reason)

    def _clearance(self, state, context, cause, command_id, *, signal=False):
        step = self.plan.steps[state.step_index]
        if len(state.used_clearances) >= self.plan.max_clearances_per_step:
            return None
        candidates = [c for c in self.plan.clearances if c.step_id == step.id
            and self._admitted(c.primitive) and c.primitive.source_context_id == context.context_id
            and c.primitive.id not in state.used_clearances and cause in c.occlusion_causes
            and c.car_visible_qualified and (not signal or c.signal_visible_qualified)
            and (not signal or c.side == "RIGHT"
                 and c.primitive.target_context_id == step.signal_gate.right_wait_context_id)]
        if not candidates:
            return None
        chosen = sorted(candidates, key=lambda c: (c.side != "RIGHT", c.primitive.id))[0]
        return self._dispatch(state, context, chosen.primitive, "CLEARANCE", command_id,
            resume_phase=state.phase, used_clearances=(*state.used_clearances, chosen.primitive.id))

    def _errors(self, step, car, parking):
        target = self.plan.parking.heading_deg if parking else step.expected_heading_deg
        error = angle_error(car.heading_deg, target, parallel_axis=parking and self.plan.parking.parallel_axis)
        yaw_tolerance = self.plan.parking.tolerance_deg if parking else self.plan.route_heading_tolerance_deg
        lateral = car.lateral_error_mm if car.measured_lateral else 0.
        score = (abs(error) + car.heading_uncertainty_deg) / yaw_tolerance
        if self.plan.parking.lateral_tolerance_mm is not None and parking and car.measured_lateral:
            score = max(score, (abs(lateral) + car.lateral_uncertainty_mm) / self.plan.parking.lateral_tolerance_mm)
        return error, lateral, score

    def _correct(self, state, context, car, command_id, *, parking):
        step = self.plan.steps[state.step_index]
        if not car.measured_heading or not car.measured_lateral:
            return self._reobserve(state, "MEASURED_CORRECTION_PRECONDITIONS_REQUIRED")
        yaw, lateral, score = self._errors(step, car, parking)
        # Lateral correction progress also matters when final parking only
        # specifies an axis angle. This score selects/limits recovery; it does
        # not introduce a new hidden final parking tolerance.
        score = max(score, (abs(lateral) + car.lateral_uncertainty_mm) / 5.)
        if state.before_correction_score is not None:
            failures = state.nonimproving_corrections + 1 if score >= state.before_correction_score - .05 else 0
            state = replace(state, nonimproving_corrections=failures, before_correction_score=None)
            if failures >= self.plan.max_nonimproving_corrections:
                return self._fail(state, "CORRECTIONS_NOT_IMPROVING")
        if state.correction_count >= self.plan.max_corrections_per_step:
            return self._fail(state, "CORRECTION_BUDGET_EXHAUSTED")
        candidates = []
        for template in self.plan.corrections:
            if (template.step_id != step.id or not template.primitive.qualified
                    or template.primitive.source_context_id != context.context_id
                    or template.car_zone_id != car.car_zone_id or template.parking_only and not parking):
                continue
            y0, y1 = template.yaw_error_range_deg
            l0, l1 = template.lateral_error_range_mm
            if (not y0 <= yaw - car.heading_uncertainty_deg <= yaw + car.heading_uncertainty_deg <= y1
                    or not l0 <= lateral - car.lateral_uncertainty_mm <= lateral + car.lateral_uncertainty_mm <= l1):
                continue
            yaw_gain = abs(yaw) - abs(yaw + template.expected_yaw_change_deg)
            lateral_gain = abs(lateral) - abs(lateral + template.expected_lateral_change_mm)
            if yaw_gain < -.01 or lateral_gain < -.01 or not (yaw_gain >= 2. or lateral_gain >= 1.):
                continue
            candidates.append((-(yaw_gain / self.plan.parking.tolerance_deg + lateral_gain / 5.), template.primitive.id, template))
        if not candidates:
            return self._fail(state, "NO_QUALIFIED_CORRECTION_FOR_OBSERVED_STATE")
        selected = min(candidates, key=lambda item: item[:2])[2]
        return self._dispatch(state, context, selected.primitive, "PARKING" if parking else "CORRECTION", command_id,
            correction_count=state.correction_count + 1, before_correction_score=score)

    def _valid_signal(self, state, context, gate, signal):
        return (signal is not None and signal.gate_id == gate.id
            and (signal.binding, signal.session_id, signal.native_sequence, signal.context_id) ==
                (self.plan.binding, context.session_id, context.native_sequence, context.context_id)
            and state.last_motion_completed_at_s <= signal.captured_at_s <= context.now_s
            and context.now_s - signal.captured_at_s <= min(self.plan.signal_max_age_s, gate.green_valid_for_s))

    def _green_sample(self, state, context, gate, signal):
        freshness = min(self.plan.signal_max_age_s, gate.green_valid_for_s)
        if context.now_s - state.green_last_captured_at_s > freshness:
            state = replace(state, green_image_sha256s=())
        if signal.image_sha256 in state.green_image_sha256s or signal.captured_at_s <= state.green_last_captured_at_s:
            return state, False
        # Two separate original images, never two provider reviews of one frame.
        updated = replace(state, green_image_sha256s=(*state.green_image_sha256s, signal.image_sha256),
                          green_last_captured_at_s=signal.captured_at_s)
        return updated, len(updated.green_image_sha256s) >= 2

    def _entry_signal(self, state, context, signal, command_id):
        gate = self.plan.steps[state.signal_step_index].signal_gate
        if context.context_id != gate.last_contact_context_id:
            return self._fail(state, "ENTRY_REQUIRES_LAST_CONTACT_CONTEXT", reconcile=True)
        valid = self._valid_signal(state, context, gate, signal)
        if valid and signal.color == "GREEN" and signal.exclusive_green and signal.signal_visible and signal.car_visible and signal.car_unchanged_since_stop:
            state, stable = self._green_sample(state, context, gate, signal)
            if not stable:
                return self._decision(DecisionKind.WAIT, state, "ENTRY_WAIT_SECOND_EXCLUSIVE_GREEN_FRAME")
            # Freshness is checked again here, after recontact; a long recontact
            # never stretches the old green capture timestamp into permission.
            step = self.plan.steps[state.step_index]
            return self._dispatch(state, context, step.primitive, "ROUTE", command_id,
                                  green_expires_at_s=None, green_image_sha256s=())
        if signal is None:
            return self._decision(DecisionKind.WAIT, state, "ENTRY_READ_FRESH_SIGNAL")
        if state.green_expirations >= self.plan.max_green_expirations:
            return self._fail(state, "SIGNAL_ENTRY_RECOVERY_BUDGET_EXHAUSTED")
        return self._dispatch(state, context, gate.release_to_wait, "RELEASE_EXPIRED_GREEN", command_id,
            green_expirations=state.green_expirations + 1, green_image_sha256s=(), green_last_captured_at_s=0.)

    def _admitted_entry(self, state, context, command_id):
        # Explicit one-stop scenario: fresh GREEN admits the finite coordinate
        # recontact + next push/withdrawal. It is not a continuously fresh color.
        # Only the exact completed recontact can reach this phase. No grant
        # survives a restart, ambiguous receipt, delayed handoff or session change.
        index = state.admitted_signal_step_index
        if (index is None or index != state.signal_step_index or index + 1 != state.step_index
                or not 0 <= index < len(self.plan.steps) - 1):
            return self._fail(state, "SIGNAL_DEPARTURE_GRANT_MISSING", reconcile=True)
        gate = self.plan.steps[index].signal_gate
        if (not gate or gate.entry_policy != "single_departure"
                or context.context_id != gate.last_contact_context_id
                or not 0 <= context.now_s - state.last_motion_completed_at_s <= self.plan.native_max_age_s):
            return self._fail(state, "SIGNAL_DEPARTURE_HANDOFF_UNCONFIRMED", reconcile=True)
        return self._dispatch(state, context, self.plan.steps[state.step_index].primitive, "ROUTE", command_id,
            admitted_signal_step_index=None, green_expires_at_s=None, green_image_sha256s=())

    def _signal(self, state, context, car, signal, command_id):
        step = self.plan.steps[state.step_index]
        gate = step.signal_gate
        if not gate:
            return self._fail(state, "SIGNAL_GATE_MISSING")
        if context.context_id != gate.right_wait_context_id:
            return self._fail(state, "SIGNAL_REQUIRES_SELECTED_RIGHT_WAIT_CONTEXT", reconcile=True)
        # Signal polling is intentionally not exhausted by RED/UNKNOWN or a
        # temporarily covered face. No contact/approach motion is retried.
        valid = self._valid_signal(state, context, gate, signal)
        if not valid:
            return self._decision(DecisionKind.WAIT, replace(state, green_image_sha256s=()), "WAIT_FRESH_BOUND_SIGNAL")
        if not signal.car_visible or not signal.signal_visible:
            # A hand, cable tie or black paddle temporarily obscuring a printed
            # face is expected during manual color changes. Stay parked.
            return self._decision(DecisionKind.WAIT, replace(state, green_image_sha256s=()), "WAIT_CAR_AND_SIGNAL_VISIBLE")
        if not signal.car_unchanged_since_stop:
            return self._fail(state, "CAR_MOVED_DURING_SIGNAL_WAIT")
        if signal.color != "GREEN" or not signal.exclusive_green:
            return self._decision(DecisionKind.WAIT, replace(state, green_image_sha256s=()), "WAIT_" + signal.color)
        if not self._valid_car(state, context, car) or not car.car_visible or car.within_road is not True:
            return self._decision(DecisionKind.WAIT, state, "WAIT_FRESH_CONSISTENT_CAR")
        state, stable = self._green_sample(state, context, gate, signal)
        if not stable:
            return self._decision(DecisionKind.WAIT, state, "WAIT_SECOND_EXCLUSIVE_GREEN_FRAME")
        return self._dispatch(state, context, gate.recontact, "RECONTACT", command_id,
            signal_step_index=state.step_index, green_expires_at_s=signal.captured_at_s + gate.green_valid_for_s,
            admitted_signal_step_index=state.step_index if gate.entry_policy == "single_departure" else None)

    def decide(self, state: MissionState, context: RuntimeContext, *, car: CarObservation | None = None,
               signal: SignalObservation | None = None, command_id: str | None = None,
               start: StartObservation | None = None) -> PolicyDecision:
        if state.phase in {Phase.FAILED, Phase.NEEDS_RECONCILIATION}:
            return self._decision(DecisionKind.HOLD, state, state.reason)
        if state.phase == Phase.COMPLETE:
            return self._decision(DecisionKind.COMPLETE, state, "DELIVERED_AND_RETURNED")
        if (state.mission_id != self.plan.id or context.binding != self.plan.binding
                or context.session_id != state.session_id or context.control_fault):
            return self._fail(state, "RUNTIME_BINDING_OR_CONTROL_CHANGED", reconcile=True)
        if state.phase == Phase.IN_FLIGHT:
            if context.pending_command_id not in {None, state.pending_command_id}:
                return self._fail(state, "UNEXPECTED_IN_FLIGHT_COMMAND", reconcile=True)
            return self._decision(DecisionKind.WAIT, state, "AWAIT_EXACT_COMMAND_RECEIPT")
        if (context.pending_command_id is not None or not context.stationary
                or not 0 <= context.now_s - context.native_observed_at_s <= self.plan.native_max_age_s):
            return self._fail(state, "STATIONARY_NATIVE_CONTEXT_UNCONFIRMED", reconcile=True)
        if state.phase == Phase.RETURNING:
            if state.return_index == len(self.plan.empty_return):
                if context.context_id != self.plan.start_context_id:
                    return self._fail(state, "RETURN_ENDPOINT_MISMATCH", reconcile=True)
                return self._decision(DecisionKind.COMPLETE, replace(state, phase=Phase.COMPLETE), "DELIVERED_AND_RETURNED")
            return self._dispatch(state, context, self.plan.empty_return[state.return_index], "RETURN", command_id)
        if not 0 <= state.step_index < len(self.plan.steps):
            return self._fail(state, "ROUTE_CURSOR_INVALID", reconcile=True)
        step = self.plan.steps[state.step_index]
        if state.phase == Phase.READY:
            if not state.start_verified:
                valid_start = (state.step_index == 0 and start is not None and start.mission_id == self.plan.id
                    and (start.binding, start.session_id, start.native_sequence, start.context_id) ==
                        (self.plan.binding, context.session_id, context.native_sequence, context.context_id)
                    and 0 <= context.now_s - start.captured_at_s <= self.plan.car_max_age_s
                    and start.car_visible and start.at_fixed_start and start.heading_matches_start and start.within_road)
                if not valid_start:
                    return self._reobserve(state, "FIXED_START_CAR_PRECONDITION_REQUIRED")
                state = replace(state, start_verified=True, reobservations=0)
            return self._dispatch(state, context, step.primitive, "ROUTE", command_id, green_expires_at_s=None)
        if state.phase == Phase.WAIT_SIGNAL:
            return self._signal(state, context, car, signal, command_id)
        if state.phase == Phase.ENTRY_SIGNAL:
            return self._entry_signal(state, context, signal, command_id)
        if state.phase == Phase.ADMITTED_ENTRY:
            return self._admitted_entry(state, context, command_id)
        if not context.tool_clear:
            return self._fail(state, "OUTCOME_REQUIRES_COMPLETED_WITHDRAWAL")
        if not self._valid_car(state, context, car):
            return self._reobserve(state, "FRESH_BOUND_CAR_OBSERVATION_REQUIRED")
        if car.image_sha256 in state.seen_images:
            return self._reobserve(state, "NEW_ORIGINAL_FRAME_REQUIRED")
        state = replace(state, seen_images=(*state.seen_images, car.image_sha256))
        progress_only = step.review_mode == "intermediate_progress"
        if progress_only and (car.progress_status == "CLEAR_PROBLEM" or car.clear_problem is True):
            return self._fail(state, "VISIBLE_PHYSICAL_PROBLEM")
        if not car.car_visible or car.occlusion_cause != "NONE":
            cause = "UNKNOWN" if car.occlusion_cause == "NONE" else car.occlusion_cause
            clearance = self._clearance(state, context, cause, command_id, signal=step.signal_gate is not None)
            return clearance or self._reobserve(state, "CAR_OCCLUDED")
        if progress_only:
            if car.progress_status == "NO_PROGRESS":
                return self._reobserve(state, "CAR_NO_VISIBLE_PROGRESS")
            if (car.progress_status != "PROGRESS_OBSERVED" or car.visible_change is not True
                    or car.clear_problem is True or car.verdict != "PASS"):
                return self._reobserve(state, "CAR_PROGRESS_UNCONFIRMED")
            # An unknown problem flag alone does not veto visible progress.
            # Preserve None as unknown; freshness, visibility, Native guards,
            # explicit problems and signal admission still apply independently.
            if step.signal_gate:
                waiting = replace(state, phase=Phase.WAIT_SIGNAL, signal_step_index=state.step_index)
                return self._signal(waiting, context, car, signal, command_id)
            next_state = replace(state, phase=Phase.READY, step_index=state.step_index + 1,
                correction_count=0, reobservations=0, used_clearances=(), before_correction_score=None,
                nonimproving_corrections=0)
            return self.decide(next_state, context, command_id=command_id)
        if car.within_road is False:
            return self._fail(state, "CAR_OUTSIDE_QUALIFIED_ROAD")
        if car.within_road is not True or car.car_zone_id != step.car_zone_id:
            return self._reobserve(state, "CAR_ROAD_OR_ZONE_UNCONFIRMED")
        if car.verdict == "UNCERTAIN":
            return self._reobserve(state, "MUSE_UNCERTAIN")
        if step.at_goal and self.plan.parking.mode == "delivery_only":
            # Final delivery has no alignment/correction objective, even when
            # arrival is unconfirmed. Reobserve or hold with the actual reason.
            # Source/Native/visibility/road/zone guards above still apply.
            if not car.arrived:
                return self._reobserve(state, "GOAL_ARRIVAL_UNCONFIRMED")
            if car.verdict != "PASS":
                return self._reobserve(state, "DELIVERY_REQUIRES_ORIGINAL_PASS")
            return self.decide(replace(state, phase=Phase.RETURNING, vehicle_delivered=True),
                               context, command_id=command_id)
        if step.at_goal and car.arrived:
            if not car.measured_heading:
                return self._reobserve(state, "MEASURED_PARKING_HEADING_REQUIRED")
            _, _, score = self._errors(step, car, True)
            if self.plan.parking.lateral_tolerance_mm is not None and not car.measured_lateral:
                return self._reobserve(state, "MEASURED_PARKING_LATERAL_REQUIRED")
            if score > 1.:
                return self._correct(state, context, car, command_id, parking=True)
            if car.verdict != "PASS":
                return self._reobserve(state, "PARKING_REQUIRES_ORIGINAL_PASS")
            return self.decide(replace(state, phase=Phase.RETURNING, vehicle_delivered=True), context, command_id=command_id)
        measured_bad_heading = (car.measured_heading and abs(angle_error(car.heading_deg, step.expected_heading_deg))
                                + car.heading_uncertainty_deg > self.plan.route_heading_tolerance_deg)
        if car.verdict != "PASS" or not car.expected_progress or not car.heading_matches_expected or measured_bad_heading:
            return self._correct(state, context, car, command_id, parking=False)
        if step.at_goal:
            return self._reobserve(state, "GOAL_ARRIVAL_UNCONFIRMED")
        if step.signal_gate:
            waiting = replace(state, phase=Phase.WAIT_SIGNAL, signal_step_index=state.step_index)
            return self._signal(waiting, context, car, signal, command_id)
        next_state = replace(state, phase=Phase.READY, step_index=state.step_index + 1,
            correction_count=0, reobservations=0, used_clearances=(), before_correction_score=None,
            nonimproving_corrections=0)
        return self.decide(next_state, context, command_id=command_id)
