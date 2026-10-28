"""One-action physical course coordinator; transport and inference are IO ports.

An approved symbolic MUSE route chooses reviewed BASE road primitives. Drawing
pixels never produce robot targets. This module does not expand an installation,
arm the robot, qualify a turn, or turn a robot receipt into vehicle arrival.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import re
import threading
from typing import Protocol
from uuid import uuid4

from backend.maps import MapDefinition
from .tcp_path import Pose, _pose
from .taught_roads import next_fixed_pose_target


class ExecutionBlocked(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _require(condition, code, message):
    if not condition:
        raise ExecutionBlocked(code, message)


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class MeasuredRoad:
    """A reviewed directed contact corridor, not a fit or a success flag.

    qualification_sha256 must identify actual response/clearance/contact evidence
    independently inspected by the installation adapter. Synthetic tests supply
    synthetic values; constructing this object does not create physical proof.
    """
    source: str
    target: str
    start_base: Pose
    end_base: Pose
    qualification_sha256: str
    contact_face_id: str
    qualified_stroke_mm: float

    def __post_init__(self):
        a, b = _pose(self.start_base), _pose(self.end_base)
        if (not self.source or not self.target or self.source == self.target
                or a[2:] != b[2:] or math.dist(a[:2], b[:2]) <= 0
                or not _hash(self.qualification_sha256) or not self.contact_face_id
                or not _finite(self.qualified_stroke_mm) or not 0 < self.qualified_stroke_mm <= 20):
            raise ValueError("A measured road requires a directed fixed-pose corridor and actual response evidence.")
        object.__setattr__(self, "start_base", a)
        object.__setattr__(self, "end_base", b)


@dataclass(frozen=True)
class TaughtAdapter:
    map_id: str
    map_version: str
    map_hash: str
    review_sha256: str
    tcp_definition_sha256: str
    tool_id: str
    car_id: str
    surface_id: str
    roads: tuple[MeasuredRoad, ...]

    def __post_init__(self):
        roads = tuple(self.roads)
        if (not all(_hash(x) for x in (self.map_hash, self.review_sha256, self.tcp_definition_sha256))
                or not all(isinstance(x, str) and x for x in
                           (self.map_id, self.map_version, self.tool_id, self.car_id, self.surface_id))
                or not roads or not all(isinstance(x, MeasuredRoad) for x in roads)
                or len({(x.source, x.target) for x in roads}) != len(roads)):
            raise ValueError("Use one reviewed adapter with unique directed measured road primitives.")
        object.__setattr__(self, "roads", roads)


@dataclass(frozen=True)
class ApprovedRoute:
    plan_id: str
    revision: int
    destination: str
    node_ids: tuple[str, ...]
    map_id: str
    map_version: str
    map_hash: str
    muse_provider_receipt: str
    approval_receipt: str
    # The current commissioning course deliberately precedes signal qualification.
    # It cannot silently become the production traffic-light mission.
    commissioning_without_signals: bool = False

    def __post_init__(self):
        if (type(self.revision) is not int or self.revision < 1
                or not all(isinstance(x, str) and x for x in
                           (self.plan_id, self.muse_provider_receipt, self.approval_receipt))
                or type(self.commissioning_without_signals) is not bool):
            raise ValueError("Bind the exact MUSE route revision and explicit operator approval receipt.")
        object.__setattr__(self, "node_ids", tuple(self.node_ids))


def compile_taught_route(route: ApprovedRoute, adapter: TaughtAdapter, drawing: MapDefinition) -> tuple[MeasuredRoad, ...]:
    """Validate the exact symbolic path; no shortest-path replacement or XY fit.

    A changed direction requires a separately measured contact-turn primitive.
    Current LocalContactInstallation supports fixed-pose translation only, so
    this coordinator refuses those routes until a real turn runtime is added.
    """
    identity = drawing.id, drawing.version, drawing.geometry_hash
    _require((route.map_id, route.map_version, route.map_hash) == identity
             == (adapter.map_id, adapter.map_version, adapter.map_hash),
             "MAP_IDENTITY", "The approved path and reviewed adapter must match the current graph revision.")
    selected = drawing.route_from_nodes(route.destination, list(route.node_ids))
    _require(not selected["junction_ids"] or route.commissioning_without_signals,
             "SIGNAL_RUNTIME_REQUIRED", "Production junctions require qualified physical stop/signal/crossing primitives.")
    indexed = {(road.source, road.target): road for road in adapter.roads}
    roads = []
    for edge in zip(route.node_ids, route.node_ids[1:]):
        _require(edge in indexed, "ROAD_UNQUALIFIED", f"The exact selected directed road {edge} has no measured primitive.")
        road = indexed[edge]
        if roads:
            prior = roads[-1]
            _require(prior.end_base == road.start_base, "CONTACT_TURN_REQUIRED",
                     "Recontact, a changed TCP orientation or a discontinuous anchor requires a measured transition.")
            u = tuple(b-a for a, b in zip(prior.start_base[:2], prior.end_base[:2]))
            v = tuple(b-a for a, b in zip(road.start_base[:2], road.end_base[:2]))
            # A small survey discrepancy is not a qualified steering primitive.
            collinear = abs(u[0]*v[1]-u[1]*v[0]) <= 1e-9 * math.hypot(*u)*math.hypot(*v)
            _require(collinear and sum(a*b for a, b in zip(u, v)) > 0
                     and prior.contact_face_id == road.contact_face_id,
                     "CONTACT_TURN_REQUIRED", "A changed road direction/face requires a measured contact-turn primitive.")
        roads.append(road)
    return tuple(roads)


@dataclass(frozen=True)
class Frame:
    id: str
    epoch: str
    sequence: int
    captured_at: float
    sha256: str
    original_jpeg: bytes

    def metadata(self):
        return {key: getattr(self, key) for key in ("id", "epoch", "sequence", "captured_at", "sha256")}


@dataclass(frozen=True)
class Snapshot:
    session_id: str
    sequence: int
    profile_id: str
    installation_id: str
    tcp_base: Pose
    joints_deg: tuple[float, ...]
    native_tcp_base: Pose
    native_evidence_sha256: str
    native_observed_at: float
    held_disarmed_idle: bool
    scope: str
    tcp_definition_sha256: str
    tool_id: str
    car_id: str
    surface_id: str
    configured_stroke_mm: float


@dataclass(frozen=True)
class MotionIntent:
    request_id: str
    plan_id: str
    revision: int
    source: str
    target: str
    expected_receiver: dict
    installation_id: str
    start_base: Pose
    target_base: Pose
    qualification_sha256: str
    before_frame: dict
    kind: str = "translate"
    purpose: str = "contact_trial"


@dataclass(frozen=True)
class MotionReceipt:
    request_id: str
    session_id: str
    sequence: int
    profile_id: str
    installation_id: str
    endpoint_verified: bool
    target_base: Pose
    receipt_sha256: str


@dataclass(frozen=True)
class VehicleReview:
    request_id: str
    provider_receipt: str
    before_sha256: str
    after_sha256: str
    verdict: str
    car_visible: bool
    expected_progress: bool
    excessive_yaw: bool
    arrived: bool
    summary: str


class ExecutorPorts(Protocol):
    """Adapters retain all existing API, profile, IK, Native and camera checks.

    snapshot returns full-precision receiver TCP plus independent stationary,
    eligible Native FC03 coordinates/evidence and a current receiver binding.
    execute_once arms/posts exactly this new UUID once and
    returns the original endpoint receipt, never a fabricated success. Every
    capture archives the unchanged JPEG and metadata before returning. Review
    sends both originals with physical-action/expected-outcome context to MUSE.
    append_event must durably append private evidence; checkpoint is crash-safe.
    hold inhibits later commands; it is not an emergency-stop claim.
    """
    def now(self) -> float: ...
    def snapshot(self) -> Snapshot: ...
    def capture(self) -> Frame: ...
    def execute_once(self, intent: MotionIntent) -> MotionReceipt: ...
    def review(self, intent: MotionIntent, before: Frame, after: Frame, *, at_goal: bool) -> VehicleReview: ...
    def hold(self, reason: str) -> None: ...
    def append_event(self, kind: str, payload: dict) -> None: ...
    def save_checkpoint(self, value: dict) -> None: ...
    def load_checkpoint(self) -> dict | None: ...


class TaughtExecutor:
    """One fresh stroke, Native receipt, then one image-pair review per call.

    Not a background queue. Caller invokes advance after inspecting its returned
    state. Occlusion/provider failure retains a completed stroke for review and
    cannot repeat that stroke. A new process always requires reconciliation.
    """
    def __init__(self, route: ApprovedRoute, adapter: TaughtAdapter, drawing: MapDefinition,
                 ports: ExecutorPorts, *, stroke_mm=10., endpoint_tolerance_mm=.15,
                 corridor_tolerance_mm=1., native_max_age_s=5., frame_max_age_s=2.):
        self.roads = compile_taught_route(route, adapter, drawing)
        if (not all(_finite(x) and x > 0 for x in (stroke_mm, endpoint_tolerance_mm,
                    corridor_tolerance_mm, native_max_age_s, frame_max_age_s))
                or stroke_mm > 20 or endpoint_tolerance_mm > 1 or corridor_tolerance_mm > 5):
            raise ValueError("Declare finite bounded stroke and physical review tolerances before execution.")
        self.route, self.adapter, self.ports = route, adapter, ports
        self.stroke_mm, self.endpoint_tolerance_mm = stroke_mm, endpoint_tolerance_mm
        self.corridor_tolerance_mm = corridor_tolerance_mm
        self.native_max_age_s, self.frame_max_age_s = native_max_age_s, frame_max_age_s
        self.index, self.state, self.pending = 0, "READY", None
        self.last_actual = None
        self.lock = threading.Lock()
        prior = ports.load_checkpoint()
        if prior is not None:
            self.state = "NEEDS_RECONCILIATION"
            ports.hold("Restart never resumes a physical route or repeats an intent.")
            ports.append_event("restart_requires_reconciliation", {"prior_checkpoint": prior})

    def _checkpoint(self):
        value = {"plan_id": self.route.plan_id, "revision": self.route.revision,
                 "adapter_sha256": self.adapter.review_sha256, "road_index": self.index,
                 "state": self.state, "automatic_replay": False,
                 "pending_request_id": self.pending[0].request_id if self.pending else None}
        self.ports.save_checkpoint(value)
        return value

    def _snapshot(self):
        state = self.ports.snapshot()
        age = self.ports.now()-state.native_observed_at
        _require(state.held_disarmed_idle is True and state.scope == "local_contact_commissioning"
                 and type(state.sequence) is int and state.sequence >= 1
                 and state.session_id and state.profile_id and state.installation_id
                 and _hash(state.native_evidence_sha256) and _finite(age) and 0 <= age <= self.native_max_age_s,
                 "ROBOT_STATE", "Use fresh verified stationary Native data and a held, disarmed, idle contact receiver.")
        _require((state.tcp_definition_sha256, state.tool_id, state.car_id, state.surface_id)
                 == (self.adapter.tcp_definition_sha256, self.adapter.tool_id, self.adapter.car_id, self.adapter.surface_id),
                 "TOOL_BINDING", "The current installation differs from the measured contact adapter.")
        _pose(state.tcp_base)
        _pose(state.native_tcp_base)
        _require(all(abs(a-b) <= .100000001 for a, b in zip(state.tcp_base, state.native_tcp_base)),
                 "NATIVE_DISAGREEMENT", "The independent 0.1-unit Native registers must agree with receiver TCP.")
        _require(len(state.joints_deg) == 6 and all(_finite(x) for x in state.joints_deg)
                 and _finite(state.configured_stroke_mm) and 0 < state.configured_stroke_mm <= 20,
                 "ROBOT_STATE", "Preserve actual joints and the explicitly reviewed current stroke limit.")
        return state

    def _frame(self):
        frame = self.ports.capture()
        age = self.ports.now()-frame.captured_at
        _require(isinstance(frame.original_jpeg, bytes) and frame.original_jpeg.startswith(b"\xff\xd8")
                 and frame.original_jpeg.endswith(b"\xff\xd9")
                 and _hash(frame.sha256) and hashlib.sha256(frame.original_jpeg).hexdigest() == frame.sha256
                 and frame.id and frame.epoch and type(frame.sequence) is int and frame.sequence >= 1
                 and _finite(age) and 0 <= age <= self.frame_max_age_s,
                 "FRAME_INVALID", "Select a fresh immutable original JPEG with a verified hash.")
        return frame

    def _on_road(self, current, road):
        a, b = road.start_base, road.end_base
        u = b[0]-a[0], b[1]-a[1]
        q = current[0]-a[0], current[1]-a[1]
        length = math.hypot(*u)
        along = sum(x*y for x, y in zip(q, u))/length
        cross = abs(q[0]*u[1]-q[1]*u[0])/length
        _require(cross <= self.corridor_tolerance_mm
                 and -self.endpoint_tolerance_mm <= along <= length+self.endpoint_tolerance_mm,
                 "OFF_CORRIDOR", "The fresh actual TCP is outside the reviewed taught corridor.")
        _require(all(abs(x-y) <= self.endpoint_tolerance_mm for x, y in zip(current[2:], a[2:])),
                 "FIXED_POSE_CHANGED", "Reconcile a changed working height/orientation; never normalize it silently.")

    def advance(self):
        _require(self.lock.acquire(blocking=False), "BUSY", "Only one physical operation may run at a time.")
        try:
            _require(self.state == "READY", "NOT_READY", "Review, reconcile or reset the existing operation first.")
            before_state = self._snapshot()
            road = self.roads[self.index]
            if self.last_actual is None:
                _require(math.dist(before_state.tcp_base[:3], road.start_base[:3]) <= self.endpoint_tolerance_mm,
                         "START_NOT_AT_ANCHOR", "A new course starts at its freshly reviewed physical contact anchor.")
            else:
                _require(before_state.tcp_base == self.last_actual,
                         "BASELINE_CHANGED", "Reconcile manual/external movement since the last accepted vehicle review.")
            self._on_road(before_state.tcp_base, road)
            limit = min(self.stroke_mm, before_state.configured_stroke_mm, road.qualified_stroke_mm)
            target = next_fixed_pose_target(before_state.tcp_base, (*road.end_base[:2], *before_state.tcp_base[2:]), limit)
            _require(target is not None, "ANCHOR_WITHOUT_VEHICLE_REVIEW", "A TCP at its anchor alone does not prove car progress or arrival.")
            before = self._frame()
            # Capture can take time: bind immediately before dispatch as well.
            current = self._snapshot()
            _require((current.session_id, current.sequence, current.profile_id, current.installation_id,
                      current.tcp_base, current.joints_deg, current.configured_stroke_mm)
                     == (before_state.session_id, before_state.sequence, before_state.profile_id,
                         before_state.installation_id, before_state.tcp_base, before_state.joints_deg,
                         before_state.configured_stroke_mm),
                     "BASELINE_CHANGED", "The receiver/profile/Native baseline changed during capture.")
            intent = MotionIntent(str(uuid4()), self.route.plan_id, self.route.revision, road.source, road.target,
                {"session_id": current.session_id, "seq": current.sequence, "profile_id": current.profile_id},
                current.installation_id, current.tcp_base, target, road.qualification_sha256, before.metadata())
            # Durable intent precedes the sole dispatch attempt. An exception from
            # execute_once has an unknown outcome and is never automatically retried.
            self.pending = intent, before, None
            self.state = "DISPATCH_UNRESOLVED"
            self.ports.append_event("motion_intent", {"intent": asdict(intent), "native_before": asdict(current)})
            self._checkpoint()
            try:
                receipt = self.ports.execute_once(intent)
                self.ports.hold("Complete one bounded stroke before any vehicle review or later command.")
                _require(receipt.request_id == intent.request_id and receipt.endpoint_verified is True
                         and (receipt.session_id, receipt.profile_id, receipt.installation_id)
                         == (current.session_id, current.profile_id, current.installation_id)
                         and receipt.sequence == current.sequence+1
                         and tuple(receipt.target_base) == target and _hash(receipt.receipt_sha256),
                         "ROBOT_OUTCOME_UNKNOWN", "The bound endpoint receipt and independent Native result must agree.")
                self.pending = intent, before, receipt
                self.state = "WAIT_ENDPOINT_CONFIRMATION"
                self.ports.append_event("robot_receipt", {"receipt": asdict(receipt), "vehicle_arrival_verified": False})
                self._checkpoint()
                return self._confirm_endpoint()
            except Exception:
                self.ports.hold("No additional motion after an unverified outcome or failed review.")
                self._checkpoint()
                raise
        finally:
            self.lock.release()

    def _confirm_endpoint(self):
        intent, _, receipt = self.pending
        after = self._snapshot()
        _require((after.session_id, after.profile_id, after.installation_id, after.sequence)
                 == (receipt.session_id, receipt.profile_id, receipt.installation_id, receipt.sequence)
                 and math.dist(after.tcp_base[:3], intent.target_base[:3]) <= self.endpoint_tolerance_mm
                 and after.tcp_base[2:] == intent.start_base[2:],
                 "ENDPOINT_CONFIRMATION_REQUIRED", "The separately collected actual endpoint must agree with this existing receipt.")
        self.state = "WAIT_REVIEW"
        self.ports.append_event("robot_endpoint", {"receipt": asdict(receipt), "native_after": asdict(after),
                                                   "vehicle_arrival_verified": False})
        self._checkpoint()
        return self._review(after)

    def recheck_endpoint(self):
        """Explicit fresh read-only evidence recovery; never resend a known command."""
        _require(self.lock.acquire(blocking=False), "BUSY", "Only one operation may run at a time.")
        try:
            _require(self.state == "WAIT_ENDPOINT_CONFIRMATION" and self.pending and self.pending[2] is not None,
                     "NO_ENDPOINT_CONFIRMATION_PENDING", "An ambiguous wire result cannot be released by a Native-only retry.")
            self.ports.hold("Explicit read-only endpoint evidence recovery; the original command is never repeated.")
            return self._confirm_endpoint()
        finally:
            self.lock.release()

    def reobserve(self):
        """A new after-frame may resolve occlusion; the completed move is not sent again."""
        _require(self.lock.acquire(blocking=False), "BUSY", "Only one operation may run at a time.")
        try:
            _require(self.state == "WAIT_REVIEW" and self.pending and self.pending[2] is not None,
                     "NO_REVIEW_PENDING", "An unresolved robot command requires explicit reconciliation, not a vision retry.")
            return self._review(self._snapshot())
        finally:
            self.lock.release()

    def _review(self, actual):
        intent, before, receipt = self.pending
        _require((actual.session_id, actual.sequence, actual.profile_id, actual.installation_id)
                 == (receipt.session_id, receipt.sequence, receipt.profile_id, receipt.installation_id)
                 and math.dist(actual.tcp_base[:3], intent.target_base[:3]) <= self.endpoint_tolerance_mm
                 and actual.tcp_base[2:] == intent.start_base[2:],
                 "REVIEW_BASELINE_CHANGED", "The robot must remain at this receipt while new vehicle imagery is reviewed.")
        after = self._frame()
        _require(after.epoch == before.epoch and after.sequence > before.sequence
                 and after.captured_at > before.captured_at and after.id != before.id,
                 "FRAME_REUSED", "A completed action requires a newer frame from the unchanged camera epoch.")
        self.ports.append_event("vehicle_review_input", {"request_id": intent.request_id,
            "before": before.metadata(), "after": after.metadata(), "physical_action": True})
        road = self.roads[self.index]
        at_end = math.dist(actual.tcp_base[:2], road.end_base[:2]) <= self.endpoint_tolerance_mm
        at_goal = at_end and self.index == len(self.roads)-1
        review = self.ports.review(intent, before, after, at_goal=at_goal)
        _require(review.request_id == intent.request_id and review.provider_receipt
                 and review.before_sha256 == before.sha256 and review.after_sha256 == after.sha256
                 and review.verdict in {"PASS", "FAIL", "UNCERTAIN"}
                 and all(type(v) is bool for v in (review.car_visible, review.expected_progress,
                                                  review.excessive_yaw, review.arrived)),
                 "REVIEW_BINDING", "Preserve the original physical action/image-pair MUSE result and exact request binding.")
        self.ports.append_event("vehicle_review", {"result": asdict(review), "robot_endpoint_verified": True})
        # Provider latency cannot authorize a transition on a changed robot
        # baseline. Native freshness is checked anew, independent of MUSE.
        current = self._snapshot()
        _require((current.session_id, current.sequence, current.profile_id, current.installation_id, current.tcp_base)
                 == (actual.session_id, actual.sequence, actual.profile_id, actual.installation_id, actual.tcp_base),
                 "REVIEW_BASELINE_CHANGED", "The robot changed while the provider was reviewing this action.")
        if review.verdict == "FAIL" or review.excessive_yaw:
            self.state = "NEEDS_RECONCILIATION"
        elif review.verdict != "PASS" or not review.car_visible or not review.expected_progress:
            self.state = "WAIT_REVIEW"
        elif at_goal:
            # Actual car arrival is separate from reaching the taught TCP anchor.
            self.state = "WAIT_HUMAN_RESET" if review.arrived else "WAIT_REVIEW"
        else:
            if at_end:
                self.index += 1
            self.last_actual = current.tcp_base
            self.pending, self.state = None, "READY"
        result = self._checkpoint()
        result["vehicle_arrival_verified"] = self.state == "WAIT_HUMAN_RESET"
        result["human_reset_required"] = self.state == "WAIT_HUMAN_RESET"
        return result
