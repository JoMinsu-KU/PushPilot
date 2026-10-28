"""Finite fixed-pose action units: coordinates first, MUSE after withdrawal.

Importing this module performs no IO. It does not qualify a contact path or
select targets from pixels. The caller supplies an explicitly reviewed unit;
the existing physical ports retain API/profile/Native admission and limits.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import threading
from uuid import uuid4

from .taught_executor import (
    ExecutionBlocked, ExecutorPorts, Frame, MotionIntent, TaughtAdapter,
    VehicleReview, _finite, _hash, _require, checked_frame, checked_snapshot,
)
from .tcp_path import Pose, _pose


@dataclass(frozen=True)
class CoordinateBinding:
    """Current-site commissioning identities, without invented qualified roads.

    This binds the real ports' camera and tool checks. It grants no route
    qualification or motion authority; each unit still needs explicit site
    review and the existing installed physical contact profile/admission.
    """
    map_id: str
    map_version: str
    map_hash: str
    tcp_definition_sha256: str
    tool_id: str
    car_id: str
    surface_id: str

    def __post_init__(self):
        if (not all(isinstance(x, str) and 0 < len(x) <= 150 for x in
                    (self.map_id, self.map_version, self.tool_id, self.car_id, self.surface_id))
                or not _hash(self.map_hash) or not _hash(self.tcp_definition_sha256)):
            raise ValueError("Bind the exact current map/view and physical tool/car/surface identities.")

    @property
    def observation_clearances(self):
        # Unit withdrawal is explicit. This component has no legacy automatic
        # occlusion-triggered path and no paper signal permission.
        return ()


@dataclass(frozen=True)
class CoordinateStage:
    id: str
    phase: str
    start_base: Pose
    target_base: Pose
    review_sha256: str

    def __post_init__(self):
        a, b = _pose(self.start_base), _pose(self.target_base)
        if (not isinstance(self.id, str) or not 1 <= len(self.id) <= 100
                or self.phase not in {"approach", "contact", "withdraw"}
                or a[2:] != b[2:] or not 0 < math.dist(a[:2], b[:2]) <= 20
                or not _hash(self.review_sha256)):
            raise ValueError("Bind one reviewed <=20 mm XY stage at literal fixed Z/orientation.")
        object.__setattr__(self, "start_base", a)
        object.__setattr__(self, "target_base", b)


@dataclass(frozen=True)
class CoordinateUnit:
    id: str
    plan_id: str
    revision: int
    source: str
    target: str
    installation_id: str
    profile_id: str
    stages: tuple[CoordinateStage, ...]
    expected_visual: str
    at_goal: bool = False

    def __post_init__(self):
        stages = tuple(self.stages)
        phases = [s.phase for s in stages if isinstance(s, CoordinateStage)]
        if (not all(isinstance(x, str) and 0 < len(x) <= 150 for x in
                    (self.id, self.plan_id, self.source, self.target, self.installation_id, self.profile_id))
                or type(self.revision) is not int or self.revision < 1 or type(self.at_goal) is not bool
                or not 2 <= len(stages) <= 64 or len(phases) != len(stages)
                or len({s.id for s in stages}) != len(stages)
                or phases.count("contact") != 1 or phases[-1] != "withdraw"
                or phases != sorted(phases, key={"approach": 0, "contact": 1, "withdraw": 2}.get)
                or any(a.target_base != b.start_base for a, b in zip(stages, stages[1:]))
                or any(s.start_base[2:] != stages[0].start_base[2:] for s in stages)
                or not isinstance(self.expected_visual, str) or not 10 <= len(self.expected_visual) <= 700):
            raise ValueError("Use a continuous finite approach/contact/withdraw unit with exactly one bounded contact trial.")
        object.__setattr__(self, "stages", stages)


class CoordinateUnitPorts(ExecutorPorts):
    def review_coordinate_unit(self, unit: CoordinateUnit, completed: tuple[dict, ...],
                               before: Frame, after: Frame) -> CoordinateUnitReview: ...


@dataclass(frozen=True)
class CoordinateUnitReview(VehicleReview):
    car_footprint: str = "UNCERTAIN"
    heading_matches_expected: bool = False


class CoordinateUnitExecutor:
    """One explicit unit per instance; no background queue or automatic replay.

    All internal stages use the current exact receiver/Native baseline. Camera
    capture occurs only before the unit and after its complete withdrawal.
    Capturing a before image does not require car segmentation or a verdict.
    Review failure allows read-only reobservation, never motion replay. A new
    instance with an existing journal always requires independent reconciliation.
    Wrist reorientation is deliberately separate from this fixed-pose runner.
    """
    def __init__(self, unit: CoordinateUnit, adapter: TaughtAdapter | CoordinateBinding, ports: CoordinateUnitPorts,
                 *, native_max_age_s=5., frame_max_age_s=2.):
        if not all(_finite(x) and 0 < x <= 5 for x in (native_max_age_s, frame_max_age_s)):
            raise ValueError("Preserve finite fresh evidence windows.")
        self.unit, self.adapter, self.ports = unit, adapter, ports
        self.native_max_age_s, self.frame_max_age_s = native_max_age_s, frame_max_age_s
        self.state, self.completed, self.pending = "READY", [], None
        self.before, self.last_actual = None, None
        self.lock = threading.Lock()
        prior = ports.load_checkpoint()
        if prior is not None:
            self.state = "NEEDS_RECONCILIATION"
            ports.hold("Existing coordinate-unit evidence never resumes or replays motion.")
            ports.append_event("coordinate_unit_restart", {"prior_checkpoint": prior})

    def _checkpoint(self):
        value = {"unit_id": self.unit.id, "state": self.state,
                 "completed_stage_ids": [row["stage"]["id"] for row in self.completed],
                 "pending_request_id": self.pending.request_id if self.pending else None,
                 "automatic_replay": False, "approach_vision_gate": False,
                 "vehicle_arrival_verified": False}
        self.ports.save_checkpoint(value)
        return value

    def _snapshot(self):
        state = checked_snapshot(self.ports, self.adapter, self.native_max_age_s)
        _require((state.installation_id, state.profile_id) ==
                 (self.unit.installation_id, self.unit.profile_id),
                 "UNIT_BINDING", "Do not switch installation or profile inside a coordinate unit.")
        return state

    @staticmethod
    def _same(a, b):
        _require((a.session_id, a.sequence, a.profile_id, a.installation_id, a.tcp_base) ==
                 (b.session_id, b.sequence, b.profile_id, b.installation_id, b.tcp_base)
                 and all(abs(x-y) <= .100001 for x, y in zip(a.joints_deg, b.joints_deg)),
                 "UNIT_BASELINE_CHANGED", "Reconcile manual motion, receiver changes or joint disagreement.")

    def run(self):
        _require(self.lock.acquire(blocking=False), "BUSY", "Only one coordinate unit may execute.")
        try:
            _require(self.state == "READY", "NOT_READY", "A unit is dispatched only once.")
            current = self._snapshot()
            _require(current.tcp_base == self.unit.stages[0].start_base,
                     "UNIT_SOURCE", "Use the actual exact reviewed unit source.")
            # Outcome evidence is selected at the observation park, without
            # asking a model to admit approach or identify the tool/contact tip.
            self.before = checked_frame(self.ports, self.frame_max_age_s)
            self._same(current, self._snapshot())
            self.state = "RUNNING"
            self.ports.append_event("coordinate_unit_input", {
                "unit": asdict(self.unit), "before": self.before.metadata(),
                "approach_vision_gate": False, "review_scope": "whole_unit"})
            self._checkpoint()
            for stage in self.unit.stages:
                fresh = self._snapshot()
                self._same(current, fresh)
                _require(fresh.tcp_base == stage.start_base and
                         math.dist(stage.start_base[:2], stage.target_base[:2]) <= fresh.configured_stroke_mm,
                         "UNIT_STAGE_LIMIT", "Keep the actual source and current controller step limit.")
                intent = MotionIntent(str(uuid4()), self.unit.plan_id, self.unit.revision,
                    self.unit.source, self.unit.target,
                    {"session_id": fresh.session_id, "seq": fresh.sequence, "profile_id": fresh.profile_id},
                    fresh.installation_id, fresh.tcp_base, stage.target_base, stage.review_sha256,
                    {}, purpose="contact_turn_trial" if fresh.scope == "local_contact_turn_commissioning" else "contact_trial",
                    expected_visual=self.unit.expected_visual)
                self.pending, self.state = intent, "DISPATCH_UNRESOLVED"
                self.ports.append_event("coordinate_stage_intent", {
                    "phase": stage.phase, "stage_id": stage.id, "intent": asdict(intent),
                    "native_before": asdict(fresh), "image_admission_required": False})
                self._checkpoint()  # Durable before the sole POST, including withdrawals.
                receipt = self.ports.execute_once(intent)
                self.ports.hold("Coordinate stage completed; verify Native before the next stored stage.")
                _require(receipt.request_id == intent.request_id and receipt.endpoint_verified is True
                         and (receipt.session_id, receipt.sequence, receipt.profile_id, receipt.installation_id) ==
                         (fresh.session_id, fresh.sequence+1, fresh.profile_id, fresh.installation_id)
                         and tuple(receipt.target_base) == stage.target_base and _hash(receipt.receipt_sha256),
                         "UNIT_RECEIPT", "Retain the exact original endpoint receipt; never replay an unknown result.")
                self.state = "WAIT_NATIVE"
                self.ports.append_event("coordinate_stage_receipt", {"receipt": asdict(receipt)})
                self._checkpoint()
                actual = self._snapshot()
                _require((actual.session_id, actual.sequence, actual.profile_id, actual.installation_id, actual.tcp_base) ==
                         (receipt.session_id, receipt.sequence, receipt.profile_id, receipt.installation_id, stage.target_base),
                         "UNIT_ENDPOINT", "Independent Native confirmation must agree with this stored endpoint.")
                record = {"stage": asdict(stage), "intent": asdict(intent), "receipt": asdict(receipt),
                          "native_after": asdict(actual)}
                self.ports.append_event("coordinate_stage_endpoint", record)
                self.completed.append(record)
                current = self.last_actual = actual
                self.pending, self.state = None, "RUNNING"
                self._checkpoint()
            self.state = "WAIT_REVIEW"
            self._checkpoint()
            return self._review()
        except Exception as error:
            if isinstance(error, ExecutionBlocked) and error.code == "UNIT_BASELINE_CHANGED":
                self.state = "NEEDS_RECONCILIATION"
            if self.state not in {"READY", "WAIT_REVIEW", "ACCEPTED", "NEEDS_RECONCILIATION"}:
                self.state = "NEEDS_RECONCILIATION"
            self.ports.hold("Coordinate unit stopped; no automatic replay or next loaded action.")
            self._checkpoint()
            raise
        finally:
            self.lock.release()

    def _review(self):
        self._same(self.last_actual, self._snapshot())
        after = checked_frame(self.ports, self.frame_max_age_s)
        _require(after.epoch == self.before.epoch and after.sequence > self.before.sequence
                 and after.captured_at > self.before.captured_at,
                 "UNIT_FRAMES", "Review fresh same-view originals after the complete withdrawal.")
        self._same(self.last_actual, self._snapshot())
        review = self.ports.review_coordinate_unit(self.unit, tuple(self.completed), self.before, after)
        _require(isinstance(review, CoordinateUnitReview) and review.request_id == self.unit.id and review.provider_receipt
                 and (review.before_sha256, review.after_sha256) == (self.before.sha256, after.sha256)
                 and review.verdict in {"PASS", "FAIL", "UNCERTAIN"}
                 and all(type(x) is bool for x in (review.car_visible, review.expected_progress,
                                                  review.excessive_yaw, review.arrived, review.heading_matches_expected))
                 and review.car_footprint in {"WITHIN_ROAD", "OVERLAPS_ISLAND", "UNCERTAIN"},
                 "UNIT_REVIEW", "Preserve the actual whole-unit result and original frame binding.")
        self.ports.append_event("coordinate_unit_review", {"result": asdict(review),
            "scope": "whole_unit", "isolated_push_or_withdrawal_qualified": False})
        try:
            self._same(self.last_actual, self._snapshot())
        except Exception:
            self.state = "NEEDS_RECONCILIATION"
            raise
        accepted = (review.verdict == "PASS" and review.car_visible and review.expected_progress
                    and not review.excessive_yaw and review.heading_matches_expected
                    and review.car_footprint == "WITHIN_ROAD")
        self.state = "ACCEPTED" if accepted else "WAIT_REVIEW"
        result = self._checkpoint()
        result.update(vehicle_arrival_verified=accepted and self.unit.at_goal and review.arrived,
                      empty_tool_return_required=accepted and self.unit.at_goal and review.arrived,
                      automatic_next_unit=False)
        return result

    def reobserve(self):
        """Explicit read-only outcome recovery; never execute a stage again."""
        _require(self.lock.acquire(blocking=False), "BUSY", "Only one review may run.")
        try:
            _require(self.state == "WAIT_REVIEW" and len(self.completed) == len(self.unit.stages),
                     "NOT_WITHDRAWN", "Finish and independently confirm withdrawal before outcome review.")
            try:
                return self._review()
            except ExecutionBlocked as error:
                if error.code == "UNIT_BASELINE_CHANGED":
                    self.state = "NEEDS_RECONCILIATION"
                    self._checkpoint()
                raise
        finally:
            self.lock.release()
