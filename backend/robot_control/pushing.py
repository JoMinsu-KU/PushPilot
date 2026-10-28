"""Empirical, one-step planar pushing proposals; no I/O or motion authority.

Vehicle coordinates are right-handed: x forward, y left, yaw counterclockwise.
The car is explicitly approximated by a rectangle. Local response is learned
from physical small-push trials, never assumed from a friction constant. The
selector enumerates a finite receding horizon; it is not a full MPC solver.
Road coverage concerns only the interpolated rectangular car model, not the
tool, robot, hose, contact approach or the actual unobserved physical sweep.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math


def _finite(value: float, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError("Expected a finite number in the declared positive domain.")
    return float(value)


def _angle(value: float) -> float:
    return (value + 180) % 360 - 180


def _rotate(x: float, y: float, degrees: float) -> tuple[float, float]:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return c * x - s * y, s * x + c * y


@dataclass(frozen=True)
class PushIdentity:
    installation_id: str
    calibration_id: str
    tool_id: str
    tcp_definition_sha256: str
    car_id: str
    car_geometry_sha256: str
    surface_id: str
    model_id: str

    def __post_init__(self):
        for name, value in vars(self).items():
            if not isinstance(value, str) or not value or len(value) > 128 or value != value.strip():
                raise ValueError(f"Invalid binding: {name}.")
            if name.endswith("sha256") and (len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
                raise ValueError(f"Invalid SHA-256 binding: {name}.")


@dataclass(frozen=True)
class CarFootprint:
    length_mm: float
    width_mm: float
    approximation: str = "rectangle"

    def __post_init__(self):
        if self.approximation != "rectangle":
            raise ValueError("This selector supports only the explicit rectangle approximation.")
        for value in (self.length_mm, self.width_mm):
            if _finite(value, positive=True) > 500:
                raise ValueError("Car dimensions exceed this small tabletop model domain.")

    @property
    def geometry_sha256(self) -> str:
        """Bind these exact rectangle dimensions; this digest is not measurement proof."""
        canonical = f"pushpilot.rectangle.v1:{float(self.length_mm):.17g},{float(self.width_mm):.17g}"
        return hashlib.sha256(canonical.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class MeasuredPose:
    x_mm: float
    y_mm: float
    yaw_deg: float
    observed_at_s: float
    identity: PushIdentity
    uncertainty_xy_mm: float = 0.0
    uncertainty_yaw_deg: float = 0.0
    source: str = "measured"
    ambiguous: bool = False
    occluded: bool = False

    def __post_init__(self):
        for name in ("x_mm", "y_mm", "yaw_deg", "observed_at_s", "uncertainty_xy_mm", "uncertainty_yaw_deg"):
            _finite(getattr(self, name))
        if self.uncertainty_xy_mm < 0 or self.uncertainty_yaw_deg < 0:
            raise ValueError("Pose uncertainty cannot be negative.")
        if (abs(self.x_mm) > 10000 or abs(self.y_mm) > 10000
                or abs(self.yaw_deg) > 180 or self.observed_at_s < 0):
            raise ValueError("Pose must use bounded millimetres, -180..180 degrees and nonnegative time.")


@dataclass(frozen=True)
class Contact:
    name: str
    point_body_mm: tuple[float, float]
    push_direction_body: tuple[float, float]
    nominal_torque_sign: int


def contact_geometry(car: CarFootprint) -> tuple[Contact, ...]:
    """Nominal face contacts; torque sign is a geometric proposal, not dynamics."""
    rear, side = -car.length_mm / 2, car.width_mm / 2
    return (
        Contact("rear_center", (rear, 0), (1, 0), 0),
        Contact("rear_left", (rear, side * 0.6), (1, 0), -1),
        Contact("rear_right", (rear, -side * 0.6), (1, 0), 1),
        Contact("left_center", (0, side), (0, -1), 0),
        Contact("right_center", (0, -side), (0, 1), 0),
    )


@dataclass(frozen=True)
class PushTrial:
    trial_id: str
    identity: PushIdentity
    contact: str
    push_distance_mm: float
    delta_body_x_mm: float
    delta_body_y_mm: float
    delta_yaw_deg: float
    measurement_error_mm: float = 0.0
    measurement_error_deg: float = 0.0
    source: str = "measured"


@dataclass(frozen=True)
class FitPolicy:
    max_trial_distance_mm: float = 10.0
    max_trial_yaw_deg: float = 15.0
    max_residual_mm: float = 0.5
    max_residual_deg: float = 2.0

    def __post_init__(self):
        for value in vars(self).values():
            _finite(value, positive=True)


@dataclass(frozen=True)
class ResponseModel:
    identity: PushIdentity
    contact: str
    gain_body_x: float
    gain_body_y: float
    gain_yaw_deg_per_mm: float
    min_distance_mm: float
    max_distance_mm: float
    error_mm: float
    error_deg: float
    trial_ids: tuple[str, ...]
    source: str = "measured"


def fit_response(trials: tuple[PushTrial, ...], policy: FitPolicy = FitPolicy()) -> ResponseModel:
    """Fit a zero-intercept local response; errors are empirical, not confidence intervals."""
    if len(trials) < 3 or len({t.trial_id for t in trials}) != len(trials):
        raise ValueError("At least three independent, distinct measured trial IDs are required.")
    first = trials[0]
    known = {contact.name for contact in contact_geometry(CarFootprint(1, 1))}
    if first.contact not in known:
        raise ValueError("Unknown contact geometry.")
    for trial in trials:
        if (not trial.trial_id or trial.source != "measured" or trial.identity != first.identity
                or trial.contact != first.contact):
            raise ValueError("Trials must share exact physical identity and contact, with measured provenance.")
        values = (trial.push_distance_mm, trial.delta_body_x_mm, trial.delta_body_y_mm,
                  trial.delta_yaw_deg, trial.measurement_error_mm, trial.measurement_error_deg)
        for value in values:
            _finite(value)
        if (not 0.05 <= trial.push_distance_mm <= min(10, policy.max_trial_distance_mm)
                or math.hypot(trial.delta_body_x_mm, trial.delta_body_y_mm) > 20
                or abs(trial.delta_yaw_deg) > policy.max_trial_yaw_deg
                or trial.measurement_error_mm < 0 or trial.measurement_error_deg < 0):
            raise ValueError("Trial exceeds the small-push measurement domain.")
    denominator = sum(t.push_distance_mm ** 2 for t in trials)
    gains = tuple(sum(t.push_distance_mm * getattr(t, name) for t in trials) / denominator
                  for name in ("delta_body_x_mm", "delta_body_y_mm", "delta_yaw_deg"))
    error_mm = max(math.hypot(t.delta_body_x_mm - gains[0] * t.push_distance_mm,
                            t.delta_body_y_mm - gains[1] * t.push_distance_mm)
                   + t.measurement_error_mm for t in trials)
    error_deg = max(abs(t.delta_yaw_deg - gains[2] * t.push_distance_mm)
                    + t.measurement_error_deg for t in trials)
    if error_mm > policy.max_residual_mm or error_deg > policy.max_residual_deg:
        raise ValueError("Measured response is too inconsistent for this local fit policy.")
    return ResponseModel(first.identity, first.contact, *gains,
                         min(t.push_distance_mm for t in trials), max(t.push_distance_mm for t in trials),
                         error_mm, error_deg, tuple(t.trial_id for t in trials))


@dataclass(frozen=True)
class SelectionPolicy:
    max_pose_age_s: float = 1.0
    max_pose_uncertainty_mm: float = 1.0
    max_pose_uncertainty_deg: float = 3.0
    max_step_mm: float = 5.0
    max_step_yaw_deg: float = 10.0
    max_predicted_translation_mm: float = 10.0
    position_tolerance_mm: float = 1.0
    heading_tolerance_deg: float = 2.0
    clearance_mm: float = 1.0
    heading_weight_mm_per_deg: float = 0.5
    cross_track_weight: float = 2.0
    uncertainty_weight: float = 1.0

    def __post_init__(self):
        for value in vars(self).values():
            _finite(value, positive=True)


@dataclass(frozen=True)
class ActionProposal:
    status: str
    reason: str
    contact: str | None = None
    contact_point_mm: tuple[float, float] | None = None
    push_direction: tuple[float, float] | None = None
    distance_mm: float | None = None
    expected_car_pose: tuple[float, float, float] | None = None
    coverage: str = "not_checked"
    motion_qualified: bool = False


def _covered(box: tuple[float, float, float, float], roads: tuple[tuple[float, float, float, float], ...]) -> bool:
    """Exact union containment for an axis-aligned box, including holes between roads."""
    x0, y0, x1, y1 = box
    cuts = sorted({x0, x1} | {edge for r in roads for edge in (r[0], r[2]) if x0 < edge < x1})
    for left, right in zip(cuts, cuts[1:]):
        intervals = sorted((r[1], r[3]) for r in roads if r[0] <= left and right <= r[2])
        top = y0
        for low, high in intervals:
            if low > top:
                break
            top = max(top, high)
        if top < y1:
            return False
    return True


def _sweep_covered(pose: MeasuredPose, target: tuple[float, float, float], car: CarFootprint,
                   inflation: float, roads: tuple[tuple[float, float, float, float], ...]) -> bool:
    dx, dy, da = target[0] - pose.x_mm, target[1] - pose.y_mm, _angle(target[2] - pose.yaw_deg)
    steps = max(1, math.ceil(math.hypot(dx, dy) / 0.5), math.ceil(abs(da)))
    radius = math.hypot(car.length_mm, car.width_mm) / 2 + inflation
    # Inflate samples for the maximum displacement to their nearest interpolated pose.
    margin = inflation + math.hypot(dx, dy) / (2 * steps) + radius * math.radians(abs(da)) / (2 * steps)
    half_l, half_w = car.length_mm / 2 + margin, car.width_mm / 2 + margin
    for i in range(steps + 1):
        fraction = i / steps
        yaw = math.radians(pose.yaw_deg + da * fraction)
        extent_x = abs(math.cos(yaw)) * half_l + abs(math.sin(yaw)) * half_w
        extent_y = abs(math.sin(yaw)) * half_l + abs(math.cos(yaw)) * half_w
        x, y = pose.x_mm + dx * fraction, pose.y_mm + dy * fraction
        if not _covered((x - extent_x, y - extent_y, x + extent_x, y + extent_y), roads):
            return False
    return True


def select_next(pose: MeasuredPose, car: CarFootprint, models: tuple[ResponseModel, ...], *,
                identity: PushIdentity, waypoint_mm: tuple[float, float], desired_heading_deg: float,
                path_origin_mm: tuple[float, float], now_s: float,
                road_rectangles_mm: tuple[tuple[float, float, float, float], ...] = (),
                policy: SelectionPolicy = SelectionPolicy()) -> ActionProposal:
    """Propose one supported push, requiring a new measured pose before another call.

    Recontact/approach, contact-height, BASE mapping and complete robot collision
    qualification are separate executor requirements. This never returns a TCP.
    """
    for value in (*waypoint_mm, *path_origin_mm, desired_heading_deg, now_s):
        _finite(value)
    if len(waypoint_mm) != 2 or len(path_origin_mm) != 2:
        raise ValueError("Waypoint and path origin must be 2D millimetre pairs.")
    if car.geometry_sha256 != identity.car_geometry_sha256:
        raise ValueError("Car rectangle dimensions do not match the bound response-model geometry.")
    if (pose.identity != identity or pose.source != "measured" or pose.ambiguous or pose.occluded
            or not 0 <= now_s - pose.observed_at_s <= policy.max_pose_age_s
            or pose.uncertainty_xy_mm > policy.max_pose_uncertainty_mm
            or pose.uncertainty_yaw_deg > policy.max_pose_uncertainty_deg):
        return ActionProposal("needs_observation", "A fresh, unambiguous measured car pose with matching identity is required.")
    goal_distance = math.hypot(waypoint_mm[0] - pose.x_mm, waypoint_mm[1] - pose.y_mm)
    heading_error = _angle(desired_heading_deg - pose.yaw_deg)
    if goal_distance <= policy.position_tolerance_mm and abs(heading_error) <= policy.heading_tolerance_deg:
        return ActionProposal("at_target", "Measured position and heading are within the requested tolerances.")
    contacts = {c.name: c for c in contact_geometry(car)}
    for model in models:
        if model.identity != identity or model.source != "measured" or model.contact not in contacts:
            raise ValueError("Response model provenance, identity or contact does not match this installation.")
        for value in (model.gain_body_x, model.gain_body_y, model.gain_yaw_deg_per_mm,
                      model.min_distance_mm, model.max_distance_mm, model.error_mm, model.error_deg):
            _finite(value)
        if (len(set(model.trial_ids)) < 3 or not 0 < model.min_distance_mm <= model.max_distance_mm
                or model.error_mm < 0 or model.error_deg < 0):
            raise ValueError("A supported measured response model is required.")
    if not models:
        return ActionProposal("needs_measurements", "No measured contact-response trials are available.")
    if not road_rectangles_mm:
        return ActionProposal("coverage_validation_required", "Supply current road rectangles before selecting a car-sweep proposal.")
    for rectangle in road_rectangles_mm:
        if len(rectangle) != 4 or any(not math.isfinite(_finite(v)) for v in rectangle) or not (
                rectangle[0] < rectangle[2] and rectangle[1] < rectangle[3]):
            raise ValueError("Road rectangles must be finite, ordered axis-aligned millimetre boxes.")
    line_x, line_y = waypoint_mm[0] - path_origin_mm[0], waypoint_mm[1] - path_origin_mm[1]
    line_length = math.hypot(line_x, line_y)
    def cross_track(x, y):
        return abs(line_x * (y - path_origin_mm[1]) - line_y * (x - path_origin_mm[0])) / line_length if line_length else 0.0
    initial_cross = cross_track(pose.x_mm, pose.y_mm)
    best = None
    for model in models:
        distances = sorted({model.min_distance_mm, (model.min_distance_mm + model.max_distance_mm) / 2,
                            model.max_distance_mm})
        for distance in distances:
            yaw_delta = model.gain_yaw_deg_per_mm * distance
            if distance > policy.max_step_mm or abs(yaw_delta) > policy.max_step_yaw_deg:
                continue
            if abs(heading_error) > policy.heading_tolerance_deg and yaw_delta * heading_error < 0:
                continue
            dx, dy = _rotate(model.gain_body_x * distance, model.gain_body_y * distance, pose.yaw_deg)
            if not math.isfinite(math.hypot(dx, dy)) or math.hypot(dx, dy) > min(20, policy.max_predicted_translation_mm):
                continue
            target = pose.x_mm + dx, pose.y_mm + dy, _angle(pose.yaw_deg + yaw_delta)
            new_heading = abs(_angle(desired_heading_deg - target[2]))
            if abs(heading_error) > policy.heading_tolerance_deg and new_heading > abs(heading_error):
                continue
            inflation = (policy.clearance_mm + pose.uncertainty_xy_mm + model.error_mm
                         + math.hypot(car.length_mm, car.width_mm) / 2
                         * math.radians(pose.uncertainty_yaw_deg + model.error_deg))
            if not _sweep_covered(pose, target, car, inflation, road_rectangles_mm):
                continue
            uncertainty = model.error_mm + math.hypot(car.length_mm, car.width_mm) / 2 * math.radians(model.error_deg)
            score = (goal_distance - math.hypot(waypoint_mm[0] - target[0], waypoint_mm[1] - target[1])
                     + policy.cross_track_weight * (initial_cross - cross_track(target[0], target[1]))
                     + policy.heading_weight_mm_per_deg * (abs(heading_error) - new_heading)
                     - policy.uncertainty_weight * uncertainty)
            if score <= 1e-9 or (best is not None and score <= best[0]):
                continue
            contact = contacts[model.contact]
            cx, cy = _rotate(*contact.point_body_mm, pose.yaw_deg)
            proposal = ActionProposal("proposal", "Measured local response improves the bounded path/heading objective; reobserve after this step.",
                                      model.contact, (pose.x_mm + cx, pose.y_mm + cy),
                                      _rotate(*contact.push_direction_body, pose.yaw_deg), distance, target,
                                      "interpolated_car_rectangle_only")
            best = score, proposal
    return best[1] if best else ActionProposal("needs_measurements", "No measured, supported, road-contained improving step; collect a suitable contact response or revise geometry.")
