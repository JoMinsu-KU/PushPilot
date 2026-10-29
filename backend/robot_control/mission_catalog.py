"""Measured geometry catalogue; historical evidence never becomes a command.

This module is deliberately free of IO.  A successful historical observation
is useful evidence for a primitive, but does not qualify its vehicle-state
envelope, a new installation, or a complete autonomous course.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import re
from uuid import uuid4

from .coordinate_units import CoordinateStage, CoordinateUnit
from .tcp_path import Pose, _pose


def content_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def _digest(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True)
class EvidenceReference:
    container: str
    member: str
    sha256: str
    container_sha256: str | None = None

    def __post_init__(self):
        if (not self.container or not self.member or not _digest(self.sha256)
                or self.container_sha256 is not None and not _digest(self.container_sha256)):
            raise ValueError("Evidence needs an original member hash and optional archive hash.")


@dataclass(frozen=True)
class MeasuredStage:
    id: str
    phase: str
    start_base: Pose
    target_base: Pose
    original_request_id: str
    evidence: EvidenceReference

    def __post_init__(self):
        start, target = _pose(self.start_base), _pose(self.target_base)
        if (not self.id or not self.original_request_id or self.phase not in
                {"approach", "contact", "withdraw", "empty", "unclassified", "wrist"}):
            raise ValueError("Measured stages need explicit original identities and phase.")
        if self.phase != "wrist" and (start[2:] != target[2:]
                or not 0 < math.dist(start[:2], target[:2]) <= 20 + 1e-9):
            raise ValueError("A translation must retain literal Z/Euler and be at most 20 mm.")
        object.__setattr__(self, "start_base", start)
        object.__setattr__(self, "target_base", target)


@dataclass(frozen=True)
class MeasuredPrimitive:
    id: str
    kind: str
    stages: tuple[MeasuredStage, ...]
    source: str
    target: str
    expected_visual: str
    original_verdict: str
    original_arrived: bool
    evidence: tuple[EvidenceReference, ...]
    blockers: tuple[str, ...]
    at_goal: bool = False
    contact_travel_limit_mm: float = 20.

    def __post_init__(self):
        stages = tuple(self.stages)
        if (not self.id or self.kind not in {"coordinate_unit", "contact_strokes",
                "empty_path", "recontact_path", "observation_path", "wrist_edge", "partial_unit"}
                or not stages or len({s.original_request_id for s in stages}) != len(stages)
                or self.original_verdict not in {"PASS", "FAIL", "UNCERTAIN", "MISSING", "ARRIVED"}
                or type(self.original_arrived) is not bool or type(self.at_goal) is not bool
                or not self.evidence):
            raise ValueError("Use distinct measured stages and retain the original outcome.")
        if any(a.target_base != b.start_base for a, b in zip(stages, stages[1:])):
            raise ValueError("Measured primitive geometry is discontinuous; never fit away a gap.")
        if self.kind != "wrist_edge" and any(s.phase == "wrist" for s in stages):
            raise ValueError("Unloaded wrist edges remain separate from translation paths.")
        if self.kind == "wrist_edge" and (len(stages) != 1 or stages[0].phase != "wrist"):
            raise ValueError("Keep one directed measured wrist edge per primitive.")
        object.__setattr__(self, "stages", stages)

    @property
    def geometry_sha256(self) -> str:
        # History/session/profile identities do not enter runtime geometry.
        return content_hash({"kind": self.kind, "stages": [
            {"phase": s.phase, "start_base": s.start_base, "target_base": s.target_base}
            for s in self.stages], "source": self.source, "target": self.target,
            "contact_travel_limit_mm": self.contact_travel_limit_mm})

    @property
    def last_contact_base(self) -> Pose | None:
        return next((s.target_base for s in reversed(self.stages) if s.phase == "contact"), None)

    @property
    def observation_base(self) -> Pose | None:
        return self.stages[-1].target_base if self.stages[-1].phase == "withdraw" else None

    @property
    def observed_success(self) -> bool:
        return self.original_verdict in {"PASS", "ARRIVED"}

    def to_dict(self) -> dict:
        value = asdict(self)
        value.update(geometry_sha256=self.geometry_sha256,
                     last_contact_base=self.last_contact_base, observation_base=self.observation_base,
                     observed_success=self.observed_success, automatically_executable=False)
        return value


@dataclass(frozen=True)
class PrimitiveQualification:
    """Current installation release, obtained independently of archive import.

    These hashes identify the runtime policy's actual precondition contract,
    swept clearance review and outcome criteria.  A caller must not manufacture
    them from historical PASS labels.  The importer never emits this class.
    """
    primitive_geometry_sha256: str
    installation_id: str
    car_precondition_sha256: str
    swept_clearance_sha256: str
    outcome_contract_sha256: str
    review_sha256: str
    physical_release_verified: bool

    def __post_init__(self):
        if (not self.installation_id or any(not _digest(h) for h in
                (self.primitive_geometry_sha256, self.car_precondition_sha256,
                 self.swept_clearance_sha256, self.outcome_contract_sha256, self.review_sha256))
                or self.physical_release_verified is not True):
            raise ValueError("A measured primitive needs a separate current physical release.")


@dataclass(frozen=True)
class RuntimeUnitContext:
    plan_id: str
    revision: int
    installation_id: str
    profile_id: str
    current_pose: Pose
    source_tolerance: float = 0.1

    def __post_init__(self):
        if (type(self.source_tolerance) not in (float, int) or not math.isfinite(self.source_tolerance)
                or not 0 <= self.source_tolerance <= 0.1):
            raise ValueError("Keep source admission at or below the original 0.1-unit tolerance.")
        object.__setattr__(self, "current_pose", _pose(self.current_pose))


def compile_coordinate_primitive(primitive: MeasuredPrimitive, context: RuntimeUnitContext,
                                 qualification: PrimitiveQualification) -> CoordinateUnit:
    """Compile NEW commands after policy preconditions; never restore mailboxes.

    Source admission allows only the original bounded telemetry tolerance;
    stored geometry is never translated, rotated, snapped or reversed. The
    physical ports separately bind fresh Native joints, profile and session.
    """
    if (primitive.kind != "coordinate_unit" or not primitive.observed_success
            or qualification.primitive_geometry_sha256 != primitive.geometry_sha256
            or qualification.installation_id != context.installation_id
            or any(abs(a-b) > context.source_tolerance + 1e-10 for a, b in
                   zip(context.current_pose, primitive.stages[0].start_base))):
        raise ValueError("Current source/release must match a successful measured coordinate unit.")
    fresh_id = "mission-unit-" + uuid4().hex
    return CoordinateUnit(fresh_id, context.plan_id, context.revision,
        primitive.source, primitive.target, context.installation_id, context.profile_id,
        tuple(CoordinateStage(f"{fresh_id}-{index}", stage.phase, stage.start_base,
                              stage.target_base, qualification.review_sha256)
              for index, stage in enumerate(primitive.stages)),
        primitive.expected_visual, at_goal=primitive.at_goal,
        contact_travel_limit_mm=primitive.contact_travel_limit_mm)


def primitive_from_dict(value: dict) -> MeasuredPrimitive:
    stages = tuple(MeasuredStage(s["id"], s["phase"], tuple(s["start_base"]),
        tuple(s["target_base"]), s["original_request_id"], EvidenceReference(**s["evidence"]))
        for s in value["stages"])
    result = MeasuredPrimitive(value["id"], value["kind"], stages, value["source"], value["target"],
        value["expected_visual"], value["original_verdict"], value["original_arrived"],
        tuple(EvidenceReference(**e) for e in value["evidence"]), tuple(value["blockers"]),
        value.get("at_goal", False), value.get("contact_travel_limit_mm", 20.))
    if value.get("geometry_sha256", result.geometry_sha256) != result.geometry_sha256:
        raise ValueError("Catalogue geometry digest differs from its measured coordinates.")
    return result


def check_recipe_continuity(primitives: tuple[MeasuredPrimitive, ...]) -> tuple[dict, ...]:
    """Report every gap, including literal posture changes; create no connector."""
    gaps = []
    for previous, following in zip(primitives, primitives[1:]):
        a, b = previous.stages[-1].target_base, following.stages[0].start_base
        if a != b:
            gaps.append({"from": previous.id, "to": following.id,
                         "xyz_gap_mm": math.dist(a[:3], b[:3]),
                         "literal_euler_difference_deg": [y-x for x, y in zip(a[3:], b[3:])],
                         "connector_created": False})
    return tuple(gaps)


def measured_subpath(primitive: MeasuredPrimitive, start: Pose, end: Pose, *, path_id: str) -> MeasuredPrimitive:
    """Select an exact contiguous measured clearance suffix; never reverse it.

    Repeated matching endpoints are ambiguous and therefore need an explicit
    original-stage selection rather than a guessed shorter path.
    """
    if primitive.kind not in {"empty_path", "observation_path", "recontact_path"}:
        raise ValueError("Only an already classified measured clearance/approach path can be sliced.")
    matches = [(a, b) for a, sa in enumerate(primitive.stages) for b, sb in enumerate(primitive.stages)
               if a <= b and sa.start_base == tuple(start) and sb.target_base == tuple(end)]
    if len(matches) != 1:
        raise ValueError("The requested measured subpath is absent or ambiguous; do not infer a connector.")
    a, b = matches[0]
    return replace(primitive, id=path_id, stages=primitive.stages[a:b+1],
                   blockers=primitive.blockers + ("MEASURED_SUBPATH_REQUIRES_OWN_RELEASE",))


def disabled_route_template(destination: str, sections: list[dict], return_sections: list[dict],
                            measured: dict[str, MeasuredPrimitive], *, signal_plan: dict,
                            arrival_evidence: dict, additional_gaps: list[dict] | None = None) -> dict:
    """Emit concrete measured geometry and unresolved slots for one destination.

    This deliberately cannot be promoted by changing ``enabled`` alone. Null
    release, live-site, car-state and route fields must be supplied by a later
    physical release; gap slots are not silently discarded by this generator.
    """
    if destination not in {"OFFICE_BUILDING", "VILLA", "HANOK"}:
        raise ValueError("Use the three explicitly requested physical destinations.")
    contexts, specs, all_gaps = {}, {}, list(additional_gaps or [])

    def context_id(pose):
        cid = "base-context-" + content_hash(pose)[:20]
        contexts[cid] = {"pose_base": list(pose), "tool_clear": None,
                         "clearance_qualification": "REQUIRED"}
        return cid

    def program(rows):
        result, previous = [], None
        for section in rows:
            if "historical_reconciliation" in section:
                link = section["historical_reconciliation"]
                if (not link.get("evidence") or link.get("original_done_missing") is not True
                        or link.get("new_command_issued") is not False
                        or link.get("automatically_executable") is not False):
                    raise ValueError("A historical reconciliation must preserve missing DONE and its evidence.")
                result.append({"kind": "historical_reconciliation", **link})
                all_gaps.append({"id": link["id"], "category": "runtime_qualification",
                    "historical_geometry_missing": False, "reason": link["release_blocker"]})
                previous = None
                continue
            if "gap" in section:
                gap = dict(section["gap"])
                if not gap.get("id") or not gap.get("reason"):
                    raise ValueError("Every missing physical segment needs a named reason.")
                gap.update(automatically_executable=False, connector_created=False)
                result.append({"kind": "unresolved_gap", **gap})
                all_gaps.append(gap)
                previous = None
                continue
            ids = section.get("primitive_ids", [])
            if not ids:
                raise ValueError("A measured route section must contain concrete catalogue primitives.")
            for pid in ids:
                p = measured[pid]
                if previous:
                    for gap in check_recipe_continuity((previous, p)):
                        all_gaps.append({"id": "LITERAL_LINK:"+previous.id+":"+pid,
                            "reason": "Stored source and target differ; no fitting, snapping or connector was applied.", **gap})
                source, target = context_id(p.stages[0].start_base), context_id(p.stages[-1].target_base)
                specs[pid] = {"catalogue_id": pid, "source_context_id": source,
                    "target_context_id": target, "qualification": None, "qualification_sha256": None}
                result.append({"kind": "measured_candidate", "role": section["role"], "catalogue_id": pid,
                    "source_context_id": source, "target_context_id": target,
                    "geometry_sha256": p.geometry_sha256, "stages": len(p.stages),
                    "original_verdict": p.original_verdict, "original_arrived": p.original_arrived,
                    "automatically_executable": False, "blockers": list(p.blockers)})
                previous = p
        return result

    route, returning = program(sections), program(return_sections)
    ids = [r["catalogue_id"] for r in route if r["kind"] == "measured_candidate"]
    return_ids = [r["catalogue_id"] for r in returning if r["kind"] == "measured_candidate"]
    workspace = {"destination": destination, "route_nodes": None, "map_id": None, "map_version": None, "map_hash": None}
    driver = {"schema": "pushpilot.physical-mission-driver.v1", "enabled": False,
        "site_binding": None, "coordinate_binding": None, "ports": None, "journal_root": None,
        "catalogue": None, "contexts": contexts, "primitives": specs,
        "measurement_adapter": None, "observations": None, "profile_coverage": None,
        "routes": [{"workspace_binding": workspace, "plan": None}]}
    return {"schema": "pushpilot.measured-route-release-template.v1", "destination": destination,
        "enabled": False, "automatic_execution_qualified": False, "driver_configuration_template": driver,
        "route_program": route, "empty_return_program": returning, "signal_plan": signal_plan,
        "arrival_evidence": arrival_evidence, "gaps": all_gaps,
        "counts": {"route_primitives": len(ids), "route_stages": sum(len(measured[i].stages) for i in ids),
            "return_primitives": len(return_ids), "return_stages": sum(len(measured[i].stages) for i in return_ids),
            "named_gaps": len(all_gaps)},
        "release_requirements": ["RESOLVE_EVERY_NAMED_GAP", "CURRENT_PROFILE_WHOLE_ROUTE_COVERAGE",
            "PHYSICAL_CAR_PRECONDITIONS_AND_CORRECTION_RESPONSES", "QUALIFIED_NUMERIC_CAR_MEASUREMENT",
            "ACTUAL_SIGNAL_TARGET_AND_STOP_VIEW", "MEASURED_PARKING_OUTCOME", "INDEPENDENT_AUTONOMOUS_REPETITION"],
        "qualified_plan_created": False, "historical_session_profile_mailbox_replay": False}


def match_measured_recontact(observation_base: Pose, last_contact_base: Pose,
                            candidates: tuple[MeasuredPrimitive, ...]) -> MeasuredPrimitive | None:
    """Select an already measured approach; do not reverse a withdrawal."""
    start, target = _pose(observation_base), _pose(last_contact_base)
    matches = [p for p in candidates if p.kind == "recontact_path"
               and all(s.phase == "approach" for s in p.stages)
               and p.stages[0].start_base == start and p.stages[-1].target_base == target]
    return min(matches, key=lambda p: (len(p.stages), p.id)) if matches else None


def deduplicate_motions(rows: list[dict]) -> tuple[list[dict], int]:
    """UUID deduplication checks complete physical identity, not seq alone."""
    result: dict[str, dict] = {}
    identity = ("session_id", "receiver_endpoint_sequence", "kind", "start_base_mm_deg", "end_base_mm_deg")
    duplicates = 0
    for row in rows:
        previous = result.get(row["request_id"])
        if previous is not None:
            if any(previous[key] != row[key] for key in identity):
                raise ValueError("Conflicting physical records share a request UUID.")
            duplicates += 1
        else:
            result[row["request_id"]] = row
    return list(result.values()), duplicates


def verify_journal(raw: bytes) -> list[dict]:
    """Check order and complete chain before using a recorded phase label."""
    previous, events = "0" * 64, []
    for index, line in enumerate(raw.splitlines(), 1):
        event = json.loads(line)
        digest = event.pop("sha256")
        if (event.get("index") != index or event.get("previous_sha256") != previous
                or content_hash(event) != digest):
            raise ValueError("The original event journal chain is invalid.")
        previous = digest
        events.append(event)
    return events
