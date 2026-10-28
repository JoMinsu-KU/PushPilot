"""Road proposals from taught BASE coordinates, independent of map registration.

The two frontage lines and one connecting-road reference define geometric
proposals. They do not establish contact dynamics, swept clearance or motion
authority. In particular, a fixed-pose TCP endpoint is not a measured car centre.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from collections.abc import Sequence

from .tcp_path import Pose, split_fixed_pose_tcp_segment

XY = tuple[float, float]


def _cross(a: XY, b: XY) -> float:
    return a[0]*b[1]-a[1]*b[0]


def _subtract(a: XY, b: XY) -> XY:
    return a[0]-b[0], a[1]-b[1]


def _dot(a: XY, b: XY) -> float:
    return a[0]*b[0]+a[1]*b[1]


@dataclass(frozen=True)
class TaughtPoint:
    id: str
    pose_base_mm_deg: Pose
    observation_sha256: str

    def __post_init__(self):
        if not isinstance(self.id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", self.id):
            raise ValueError("A taught point needs a bounded identifier.")
        try:
            values = tuple(self.pose_base_mm_deg)
        except TypeError:
            raise ValueError("A taught point needs six finite BASE TCP values.") from None
        if (len(values) != 6 or any(type(v) not in (int, float) or not math.isfinite(v)
                                   or abs(v) > 10000 for v in values)):
            raise ValueError("A taught point needs six finite BASE TCP values.")
        if not isinstance(self.observation_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.observation_sha256):
            raise ValueError("Bind the actual private teaching observation by SHA-256.")
        object.__setattr__(self, "pose_base_mm_deg", tuple(float(v) for v in values))


@dataclass(frozen=True)
class TaughtRoads:
    """A/B and C/D are frontage lines; E locates a perpendicular connector.

    Perpendicularity is a declared road-layout assumption, not inferred paper
    metrology. Every generated junction and leg remains a proposal for review.
    """
    points: tuple[TaughtPoint, ...]
    south_junction_xy: XY
    north_junction_xy: XY
    frontage_disagreement_deg: float

    def _point(self, point_id: str) -> TaughtPoint:
        return next(p for p in self.points if p.id == point_id)

    def route_preview(self, destination: str, start: TaughtPoint) -> dict:
        if destination not in {"B", "C", "D"}:
            raise ValueError("Select a directly taught destination B, C or D.")
        fixed = self.points[0].pose_base_mm_deg[2:]
        if start.pose_base_mm_deg[2:] != fixed:
            raise ValueError("The fresh start must retain taught literal Z and orientation.")
        a, b = (self._point(name).pose_base_mm_deg[:2] for name in ("A", "B"))
        ab = _subtract(b, a)
        squared_length = _dot(ab, ab)
        start_fraction = _dot(_subtract(start.pose_base_mm_deg[:2],a),ab)/squared_length
        junction_fraction = _dot(_subtract(self.south_junction_xy,a),ab)/squared_length
        if not 0 <= start_fraction <= junction_fraction:
            raise ValueError("The selected incoming start must lie along the taught frontage before its connector.")
        start_cross_track = abs(_cross(_subtract(start.pose_base_mm_deg[:2], a), ab))/math.hypot(*ab)
        # Include a fresh start, never replay calibration point A as a car start.
        xy_points = [(start.id, start.pose_base_mm_deg[:2])]
        xy_points.append(("SOUTH_JUNCTION_PROPOSED", self.south_junction_xy))
        if destination != "B":
            xy_points.extend([("E", self._point("E").pose_base_mm_deg[:2]),
                              ("NORTH_JUNCTION_PROPOSED", self.north_junction_xy)])
        xy_points.append((destination, self._point(destination).pose_base_mm_deg[:2]))
        legs = []
        for (from_id, a), (to_id, b) in zip(xy_points, xy_points[1:]):
            distance = math.dist(a, b)
            if distance <= 1e-9:
                continue
            direction = ((b[0]-a[0])/distance, (b[1]-a[1])/distance)
            prior = legs[-1]["direction_base_xy"] if legs else None
            turn = math.degrees(math.atan2(_cross(prior, direction), _dot(prior, direction))) if prior else None
            legs.append({"from":from_id, "to":to_id, "start_base_xy_mm":list(a),
                         "end_base_xy_mm":list(b), "length_mm":distance,
                         "direction_base_xy":list(direction), "relative_turn_deg":turn,
                         "turn_contact_qualified":False, "swept_clearance_qualified":False})
        return {
            "schema":"pushpilot.taught-route-preview.v1", "coordinate_frame":"BASE",
            "destination":destination, "destination_semantics":"taught_fixed_pose_tcp_reference",
            "goal_pose_base_mm_deg":list(self._point(destination).pose_base_mm_deg),
            "fresh_start_observation_sha256":start.observation_sha256,
            "teaching_observations":{p.id:p.observation_sha256 for p in self.points},
            "literal_working_z_orientation":list(fixed),
            "geometry_source":"taught_BASE_frontage_lines_and_connector_reference",
            "map_transform_used":False, "gripper_pixel_tracking_used":False,
            "connector_perpendicularity":"declared_layout_assumption_requires_physical_review",
            "start_cross_track_from_AB_mm":start_cross_track,
            "frontage_disagreement_deg":self.frontage_disagreement_deg,
            "legs":legs, "execution_ready":False, "motion_authority":False,
            "vehicle_arrival_verified":False, "automatic_replay":False,
            "required_before_execution":["fresh_start_contact_and_tool_binding",
                "actual_corridor_and_swept_tool_review", "current_receiver_profile",
                "measured_turn_and_recontact_response_for_changed_directions",
                "contact_reference_offset_for_any_changed_tool_orientation",
                "separate_vehicle_outcome_evidence"],
        }


def propose_taught_roads(points: Sequence[TaughtPoint], *, max_frontage_disagreement_deg: float = 5) -> TaughtRoads:
    """Construct unqualified junction proposals; never fit against map pixels/mm."""
    points = tuple(points)
    if len(points) != 5 or any(not isinstance(p, TaughtPoint) for p in points) or {p.id for p in points} != set("ABCDE"):
        raise ValueError("Supply exactly the five distinct current taught points A through E.")
    if (type(max_frontage_disagreement_deg) not in (int, float)
        or not math.isfinite(max_frontage_disagreement_deg) or not 0 <= max_frontage_disagreement_deg <= 10):
        raise ValueError("Use an explicit finite frontage sanity limit from zero to ten degrees.")
    by_id = {p.id:p for p in points}
    points = tuple(by_id[key] for key in "ABCDE")
    if any(p.pose_base_mm_deg[2:] != points[0].pose_base_mm_deg[2:] for p in points):
        raise ValueError("Teaching must share literal Z and tool orientation.")
    xy = {p.id:p.pose_base_mm_deg[:2] for p in points}
    lower, upper = _subtract(xy['B'],xy['A']), _subtract(xy['D'],xy['C'])
    lengths = math.hypot(*lower), math.hypot(*upper)
    if min(lengths) < 1:
        raise ValueError("Frontage references must be at least one millimetre apart.")
    lu = lower[0]/lengths[0], lower[1]/lengths[0]
    uu = upper[0]/lengths[1], upper[1]/lengths[1]
    angle = abs(math.degrees(math.atan2(_cross(lu,uu),_dot(lu,uu))))
    if angle > max_frontage_disagreement_deg+1e-9:
        raise ValueError("The declared frontage directions disagree; do not silently reverse or shear a route.")
    tangent = lu[0]+uu[0], lu[1]+uu[1]
    tangent_length = math.hypot(*tangent)
    normal = -tangent[1]/tangent_length, tangent[0]/tangent_length

    def intersection(origin: XY, frontage: XY):
        determinant = _cross(frontage,normal)
        if abs(determinant) < 1e-9:
            raise ValueError("The proposed connector cannot intersect the frontage.")
        fraction = _cross(_subtract(xy['E'],origin),normal)/determinant
        if not 0 < fraction < 1:
            raise ValueError("The proposed junction falls outside the actually taught frontage span.")
        return origin[0]+fraction*frontage[0], origin[1]+fraction*frontage[1]

    south, north = intersection(xy['A'],lower), intersection(xy['C'],upper)
    segment = _subtract(north,south)
    size_squared = _dot(segment,segment)
    if size_squared < 1:
        raise ValueError("The two road crossings must remain distinct.")
    fraction = _dot(_subtract(xy['E'],south),segment)/size_squared
    if not 0 < fraction < 1:
        raise ValueError("The connecting reference E must lie between the proposed junctions.")
    return TaughtRoads(points,south,north,angle)


def next_fixed_pose_target(actual_pose: Sequence[float], end_pose: Sequence[float], step_mm: float = 2) -> Pose | None:
    """One coordinate target from a fresh actual pose; caller retains all guards.

    The returned point is not dispatched or stored in a replayable queue. A
    controller receipt alone must never be promoted to vehicle-arrival success.
    """
    targets = split_fixed_pose_tcp_segment(actual_pose,end_pose,step_mm)
    return targets[0] if targets else None
