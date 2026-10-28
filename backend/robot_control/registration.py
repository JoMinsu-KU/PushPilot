"""Measured planar drawing-to-BASE registration, independent of image fitting.

This module has no I/O, device access, profile creation or motion authority.
Pairs must describe the SAME physical reference point in drawing millimetres
and robot BASE millimetres, with any probe/TCP offset already accounted for.
An arbitrary contacting TCP is not a measurement of the vehicle centre.

Drawing axes are declared explicitly. Printed map coordinates commonly grow
right/down, so their Y coordinate is negated before an orientation-preserving
rigid fit into right-handed BASE XY. Unexpected mirror fits, automatic scale
correction, dropped outliers and extrapolation outside the drawing are refused.
Contact Z, tool orientation, contact geometry and collision qualification are
separate measured installation inputs; a good fit does not establish them.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


class RegistrationError(ValueError):
    """Invalid, stale or geometrically inconsistent calibration evidence."""


def _number(value: object, name: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise RegistrationError(f"{name} must be a finite number, not a boolean.")
    if positive and value <= 0:
        raise RegistrationError(f"{name} must be positive.")
    return float(value)


def _text(value: object, name: str, maximum: int = 128) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > maximum:
        raise RegistrationError(f"{name} must be nonempty bounded text without surrounding whitespace.")
    return value


def _digest(value: object, name: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise RegistrationError(f"{name} must be a lowercase SHA-256 digest.")
    return value


def _xy(value: object, name: str, *, maximum: float = 10000) -> tuple[float, float]:
    if type(value) not in (list, tuple) or len(value) != 2:
        raise RegistrationError(f"{name} must contain exactly two millimetre coordinates; Z is separate.")
    result = tuple(_number(item, name) for item in value)
    if any(abs(item) > maximum for item in result):
        raise RegistrationError(f"{name} exceeds the finite {maximum:g} mm coordinate domain.")
    return result


@dataclass(frozen=True)
class RegistrationIdentity:
    map_id: str
    map_version: str
    map_hash: str
    camera_epoch: str
    registration_id: str
    tcp_id: str
    tcp_definition_sha256: str
    tool_id: str
    drawing_axes: str = "x_right_y_down"

    def __post_init__(self) -> None:
        for name in ("map_id", "map_version", "camera_epoch", "registration_id", "tcp_id", "tool_id"):
            _text(getattr(self, name), name)
        for name in ("map_hash", "tcp_definition_sha256"):
            _digest(getattr(self, name), name)
        if self.drawing_axes not in ("x_right_y_down", "x_right_y_up"):
            raise RegistrationError("drawing_axes must explicitly declare x_right_y_down or x_right_y_up.")

    def to_dict(self) -> dict:
        return dict(vars(self))


@dataclass(frozen=True)
class DrawingDomain:
    min_x_mm: float
    min_y_mm: float
    max_x_mm: float
    max_y_mm: float

    def __post_init__(self) -> None:
        for name in ("min_x_mm", "min_y_mm", "max_x_mm", "max_y_mm"):
            value = _number(getattr(self, name), name)
            if abs(value) > 10000:
                raise RegistrationError("Drawing domain exceeds 10000 mm.")
            object.__setattr__(self, name, value)
        if not (self.min_x_mm < self.max_x_mm and self.min_y_mm < self.max_y_mm):
            raise RegistrationError("Drawing domain must have positive ordered dimensions.")

    def require_inside(self, point: tuple[float, float]) -> None:
        tolerance = 1e-8
        if not (self.min_x_mm - tolerance <= point[0] <= self.max_x_mm + tolerance
                and self.min_y_mm - tolerance <= point[1] <= self.max_y_mm + tolerance):
            raise RegistrationError("Point is outside the declared drawing domain; extrapolation is not admitted.")

    def to_dict(self) -> dict:
        return dict(vars(self))


@dataclass(frozen=True)
class FitPolicy:
    """Site-selected metrology thresholds, never inferred from the samples."""

    max_fit_residual_mm: float
    max_check_error_mm: float
    scale_tolerance: float = 0.02
    min_span_mm: float = 20.0
    min_shape_ratio: float = 0.01
    min_check_separation_mm: float = 5.0

    def __post_init__(self) -> None:
        for name in vars(self):
            value = _number(getattr(self, name), name, positive=True)
            object.__setattr__(self, name, value)
        if (self.max_fit_residual_mm > 100 or self.max_check_error_mm > 100
                or self.min_span_mm > 10000 or self.min_check_separation_mm > 10000
                or self.scale_tolerance >= 0.25 or self.min_shape_ratio >= 1):
            raise RegistrationError("Registration policy exceeds its finite metrology bounds.")

    def to_dict(self) -> dict:
        return dict(vars(self))


@dataclass(frozen=True)
class MeasuredPoint:
    measurement_id: str
    drawing_xy_mm: tuple[float, float]
    base_xy_mm: tuple[float, float]
    identity: RegistrationIdentity
    evidence_reference: str
    source: str

    def __post_init__(self) -> None:
        _text(self.measurement_id, "measurement_id")
        _text(self.evidence_reference, "evidence_reference", 500)
        if type(self.identity) is not RegistrationIdentity:
            raise RegistrationError("Each measured point requires an explicit registration identity.")
        if self.source != "measured":
            raise RegistrationError("Nominal coordinates alone are not a measured correspondence.")
        object.__setattr__(self, "drawing_xy_mm", _xy(self.drawing_xy_mm, "drawing_xy_mm"))
        object.__setattr__(self, "base_xy_mm", _xy(self.base_xy_mm, "base_xy_mm"))

    def to_dict(self) -> dict:
        return {**vars(self), "drawing_xy_mm": list(self.drawing_xy_mm),
                "base_xy_mm": list(self.base_xy_mm), "identity": self.identity.to_dict()}


def _normalise(point: tuple[float, float], identity: RegistrationIdentity) -> tuple[float, float]:
    return point[0], -point[1] if identity.drawing_axes == "x_right_y_down" else point[1]


def _geometry(points: list[tuple[float, float]], policy: FitPolicy, name: str) -> tuple[float, float]:
    centre = tuple(math.fsum(point[axis] for point in points) / len(points) for axis in (0, 1))
    centred = [(point[0] - centre[0], point[1] - centre[1]) for point in points]
    xx = math.fsum(x * x for x, _ in centred)
    yy = math.fsum(y * y for _, y in centred)
    xy = math.fsum(x * y for x, y in centred)
    largest = (xx + yy + math.hypot(xx - yy, 2 * xy)) / 2
    # det / largest avoids cancellation in the small eigenvalue for thin data.
    smallest = max(0.0, xx * yy - xy * xy) / largest if largest > 0 else 0.0
    span = max(math.dist(a, b) for i, a in enumerate(points) for b in points[i + 1:])
    if span < policy.min_span_mm or largest <= 0 or smallest / largest < policy.min_shape_ratio:
        raise RegistrationError(f"{name} points are degenerate, near-collinear or too narrowly spaced.")
    return centre


@dataclass(frozen=True)
class PlanarRegistration:
    """A measured XY fit; construction alone grants no physical qualification."""

    calibration_id: str
    identity: RegistrationIdentity
    domain: DrawingDomain
    policy: FitPolicy
    cos_theta: float
    sin_theta: float
    translation_base_mm: tuple[float, float]
    points: tuple[MeasuredPoint, ...]
    residuals_mm: tuple[float, ...]
    estimated_scale: float

    def __post_init__(self) -> None:
        _text(self.calibration_id, "calibration_id")
        if (type(self.identity) is not RegistrationIdentity or type(self.domain) is not DrawingDomain
                or type(self.policy) is not FitPolicy):
            raise RegistrationError("A fit requires validated identity, domain and policy objects.")
        c, s = _number(self.cos_theta, "cos_theta"), _number(self.sin_theta, "sin_theta")
        if abs(c * c + s * s - 1) > 1e-10:
            raise RegistrationError("A rigid fit must preserve unit rotation and scale.")
        # The frame-origin offset can exceed either point coordinate: it is a
        # difference between BASE points and a rotated drawing-origin vector.
        object.__setattr__(self, "translation_base_mm", _xy(self.translation_base_mm, "translation_base_mm", maximum=30000))
        object.__setattr__(self, "points", tuple(self.points))
        object.__setattr__(self, "residuals_mm", tuple(self.residuals_mm))
        if (not 3 <= len(self.points) <= 100 or len(self.points) != len(self.residuals_mm)
                or any(type(point) is not MeasuredPoint or point.identity != self.identity for point in self.points)):
            raise RegistrationError("A fit report must retain its bound measured correspondences and residuals.")
        for residual in self.residuals_mm:
            if not 0 <= _number(residual, "residual_mm") <= self.policy.max_fit_residual_mm + 1e-9:
                raise RegistrationError("Fit report residual exceeds its metrology policy.")
        scale = _number(self.estimated_scale, "estimated_scale", positive=True)
        if abs(scale - 1) > self.policy.scale_tolerance + 1e-12:
            raise RegistrationError("Fit report scale exceeds its metrology policy.")

    def _require_identity(self, identity: RegistrationIdentity) -> None:
        if type(identity) is not RegistrationIdentity or identity != self.identity:
            raise RegistrationError("Current map, camera, registration, TCP or tool identity differs from the fit.")

    def drawing_to_base(self, point: object, *, identity: RegistrationIdentity) -> tuple[float, float]:
        self._require_identity(identity)
        drawing = _xy(point, "drawing_xy_mm")
        self.domain.require_inside(drawing)
        x, y = _normalise(drawing, self.identity)
        tx, ty = self.translation_base_mm
        return _xy((self.cos_theta * x - self.sin_theta * y + tx,
                    self.sin_theta * x + self.cos_theta * y + ty), "mapped_base_xy_mm")

    def base_to_drawing(self, point: object, *, identity: RegistrationIdentity) -> tuple[float, float]:
        self._require_identity(identity)
        bx, by = _xy(point, "base_xy_mm")
        x, y = bx - self.translation_base_mm[0], by - self.translation_base_mm[1]
        normalised = (self.cos_theta * x + self.sin_theta * y,
                      -self.sin_theta * x + self.cos_theta * y)
        drawing = _normalise(normalised, self.identity)
        self.domain.require_inside(drawing)
        return drawing

    def to_dict(self) -> dict:
        return {
            "schema": "pushpilot.planar-registration.v1", "calibration_id": self.calibration_id,
            "identity": self.identity.to_dict(), "drawing_domain_mm": self.domain.to_dict(),
            "policy": self.policy.to_dict(),
            "transform": {"model": "rigid_xy_after_declared_axis_normalisation", "scale_applied": 1.0,
                          "rotation_deg": math.degrees(math.atan2(self.sin_theta, self.cos_theta)),
                          "cos_theta": self.cos_theta, "sin_theta": self.sin_theta,
                          "translation_base_mm": list(self.translation_base_mm)},
            "fit": {"source": "measured", "count": len(self.points),
                    "rms_error_mm": math.sqrt(math.fsum(r * r for r in self.residuals_mm) / len(self.points)),
                    "max_error_mm": max(self.residuals_mm), "estimated_scale": self.estimated_scale,
                    "residuals": [{"measurement_id": p.measurement_id, "error_mm": r}
                                  for p, r in zip(self.points, self.residuals_mm)],
                    "discarded_points": []},
            "measurements": [point.to_dict() for point in self.points],
            "independent_check_required": True, "physical_qualified": False,
            "contact_z_fitted": False,
            "route_coverage_qualified": False,
            "domain_scope": "Declared drawing domain is a mathematical boundary, not measured calibration coverage or a reviewed robot workspace.",
        }


def fit_registration(calibration_id: str, points: Iterable[MeasuredPoint],
                     domain: DrawingDomain, policy: FitPolicy) -> PlanarRegistration:
    """Fit all paired measurements using equal-weight 2D rigid least squares.

    The unrestricted similarity scale is reported and checked, but never
    applied: both input spaces must already use physical millimetres. No point
    is silently dropped. Calibration and independent-check thresholds are not
    collision, pushing, robot stop or installation qualification thresholds.
    """
    _text(calibration_id, "calibration_id")
    if type(domain) is not DrawingDomain or type(policy) is not FitPolicy:
        raise RegistrationError("An explicit drawing domain and fit policy are required.")
    measurements = tuple(points)
    if not 3 <= len(measurements) <= 100 or any(type(point) is not MeasuredPoint for point in measurements):
        raise RegistrationError("A fit requires 3 to 100 measured correspondences.")
    identity = measurements[0].identity
    if any(point.identity != identity for point in measurements):
        raise RegistrationError("All calibration measurements must have the same current identity.")
    if len({point.measurement_id for point in measurements}) != len(measurements):
        raise RegistrationError("Calibration measurement IDs must be unique.")
    if len({point.drawing_xy_mm for point in measurements}) != len(measurements):
        raise RegistrationError("Calibration drawing coordinates must be distinct.")
    for point in measurements:
        domain.require_inside(point.drawing_xy_mm)
    drawing = [_normalise(point.drawing_xy_mm, identity) for point in measurements]
    base = [point.base_xy_mm for point in measurements]
    dp, bp = _geometry(drawing, policy, "Drawing"), _geometry(base, policy, "BASE")
    p = [(x - dp[0], y - dp[1]) for x, y in drawing]
    q = [(x - bp[0], y - bp[1]) for x, y in base]
    h00 = math.fsum(a[0] * b[0] for a, b in zip(p, q))
    h01 = math.fsum(a[0] * b[1] for a, b in zip(p, q))
    h10 = math.fsum(a[1] * b[0] for a, b in zip(p, q))
    h11 = math.fsum(a[1] * b[1] for a, b in zip(p, q))
    if h00 * h11 - h01 * h10 <= 0:
        raise RegistrationError("Correspondences imply a reflection or inconsistent axis convention.")
    a, b = h00 + h11, h01 - h10
    magnitude = math.hypot(a, b)
    energy = math.fsum(x * x + y * y for x, y in p)
    estimated_scale = magnitude / energy
    if abs(estimated_scale - 1) > policy.scale_tolerance + 1e-12:
        raise RegistrationError(f"Measured scale {estimated_scale:.6f} differs from millimetres; no scale correction applied.")
    c, s = a / magnitude, b / magnitude
    translation = (bp[0] - c * dp[0] + s * dp[1], bp[1] - s * dp[0] - c * dp[1])
    residuals = tuple(math.dist((c * x - s * y + translation[0], s * x + c * y + translation[1]), target)
                      for (x, y), target in zip(drawing, base))
    maximum = max(residuals)
    if maximum > policy.max_fit_residual_mm + 1e-9:
        worst = measurements[residuals.index(maximum)].measurement_id
        raise RegistrationError(f"Fit residual {maximum:.6f} mm at {worst} exceeds policy; no outlier was discarded.")
    return PlanarRegistration(calibration_id, identity, domain, policy, c, s, translation,
                              measurements, residuals, estimated_scale)


@dataclass(frozen=True)
class IndependentCheckReport:
    calibration_id: str
    point: MeasuredPoint
    predicted_base_xy_mm: tuple[float, float]
    error_mm: float
    maximum_error_mm: float
    accepted: bool

    def to_dict(self) -> dict:
        return {"schema": "pushpilot.planar-independent-check.v1", "calibration_id": self.calibration_id,
                "measurement": self.point.to_dict(), "predicted_base_xy_mm": list(self.predicted_base_xy_mm),
                "error_mm": self.error_mm, "maximum_error_mm": self.maximum_error_mm,
                "accepted": self.accepted, "source": "measured", "physical_qualified": False}


def validate_independent_check(registration: PlanarRegistration, point: MeasuredPoint) -> IndependentCheckReport:
    """Check a new, spatially separate measurement without refitting the model.

    Reused fit samples and identity changes are invalid evidence (exceptions).
    A genuine new measurement above the error threshold returns accepted=False.
    Either outcome leaves the fit untouched and grants no motion qualification.
    """
    if type(registration) is not PlanarRegistration or type(point) is not MeasuredPoint:
        raise RegistrationError("Independent checking requires a fitted registration and a measured point.")
    registration._require_identity(point.identity)
    if any(point.measurement_id == fitted.measurement_id
           or point.evidence_reference == fitted.evidence_reference
           or math.dist(point.drawing_xy_mm, fitted.drawing_xy_mm) < registration.policy.min_check_separation_mm
           or math.dist(point.base_xy_mm, fitted.base_xy_mm) < registration.policy.min_check_separation_mm
           for fitted in registration.points):
        raise RegistrationError("Independent check must use new evidence and a spatially separate reference point.")
    predicted = registration.drawing_to_base(point.drawing_xy_mm, identity=point.identity)
    error = math.dist(predicted, point.base_xy_mm)
    return IndependentCheckReport(registration.calibration_id, point, predicted, error,
                                  registration.policy.max_check_error_mm,
                                  error <= registration.policy.max_check_error_mm + 1e-9)
