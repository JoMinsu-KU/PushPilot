"""Offline, source-bound checkerboard camera-model estimation.

Only supplied corner arrays are consumed. This module does not capture images,
change a camera, write files, install a model, or access a robot. Image-model
reprojection checks do not establish a millimetre accuracy bound, an actual
contact-face position, or a drawing-to-BASE transformation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Sequence

import cv2
import numpy as np


class CameraIntrinsicsError(ValueError):
    """Invalid, mixed, reused, or insufficient calibration observations."""


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > 160:
        raise CameraIntrinsicsError(f"{name} must be nonempty bounded text.")
    return value


def _digest(value: object, name: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise CameraIntrinsicsError(f"{name} must be a lowercase SHA-256 digest.")
    return value


def _number(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise CameraIntrinsicsError(f"{name} must be a finite number, not a boolean.")
    return float(value)


@dataclass(frozen=True)
class CameraIntrinsicsIdentity:
    camera_id: str
    camera_epoch: str
    settings_sha256: str
    width: int = 1920
    height: int = 1080

    def __post_init__(self) -> None:
        _text(self.camera_id, "camera_id")
        _text(self.camera_epoch, "camera_epoch")
        _digest(self.settings_sha256, "settings_sha256")
        if type(self.width) is not int or type(self.height) is not int or (self.width, self.height) != (1920, 1080):
            raise CameraIntrinsicsError("Only unchanged native 1920 x 1080 observations are supported.")


@dataclass(frozen=True)
class CheckerboardPattern:
    pattern_id: str
    pattern_sha256: str
    columns: int
    rows: int
    square_size_units: float = 1.0

    def __post_init__(self) -> None:
        _text(self.pattern_id, "pattern_id")
        _digest(self.pattern_sha256, "pattern_sha256")
        if (type(self.columns) is not int or type(self.rows) is not int
                or not 5 <= self.columns <= 20 or not 4 <= self.rows <= 16):
            raise CameraIntrinsicsError("Declare 5-20 by 4-16 internal checkerboard corners.")
        size = _number(self.square_size_units, "square_size_units")
        if not 0 < size <= 10000:
            raise CameraIntrinsicsError("square_size_units must be positive and bounded.")
        object.__setattr__(self, "square_size_units", size)

    def object_points(self) -> np.ndarray:
        points = np.zeros((self.columns * self.rows, 3), dtype=np.float32)
        points[:, :2] = np.mgrid[0:self.columns, 0:self.rows].T.reshape(-1, 2)
        points[:, :2] *= self.square_size_units
        return points


@dataclass(frozen=True)
class CheckerboardObservation:
    observation_id: str
    image_sha256: str
    identity: CameraIntrinsicsIdentity
    pattern_id: str
    pattern_sha256: str
    image_points_px: Sequence[Sequence[float]]

    def __post_init__(self) -> None:
        _text(self.observation_id, "observation_id")
        _digest(self.image_sha256, "image_sha256")
        if type(self.identity) is not CameraIntrinsicsIdentity:
            raise CameraIntrinsicsError("Each observation requires an explicit camera identity.")
        _text(self.pattern_id, "pattern_id")
        _digest(self.pattern_sha256, "pattern_sha256")
        try:
            points = tuple(tuple(_number(v, "image_points_px") for v in p) for p in self.image_points_px)
        except TypeError as error:
            raise CameraIntrinsicsError("image_points_px must be a sequence of two-number points.") from error
        if not points or any(len(p) != 2 for p in points):
            raise CameraIntrinsicsError("image_points_px must contain two-number points.")
        if any(not (0 <= x < self.identity.width and 0 <= y < self.identity.height) for x, y in points):
            raise CameraIntrinsicsError("All original corner coordinates must lie inside the native frame.")
        object.__setattr__(self, "image_points_px", points)


@dataclass(frozen=True)
class IntrinsicsPolicy:
    """Predeclared image criteria. Custom criteria may only be stricter."""

    max_training_rms_px: float = 0.5
    max_per_view_rms_px: float = 0.8
    max_heldout_rms_px: float = 0.7

    def __post_init__(self) -> None:
        for name, ceiling in (("max_training_rms_px", 0.5), ("max_per_view_rms_px", 0.8),
                              ("max_heldout_rms_px", 0.7)):
            value = _number(getattr(self, name), name)
            if not 0 < value <= ceiling:
                raise CameraIntrinsicsError("Image criteria cannot be relaxed beyond the predeclared limits.")
            object.__setattr__(self, name, value)


def _ids(values: Sequence[str], name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise CameraIntrinsicsError(f"{name} must explicitly list observation IDs.")
    result = tuple(_text(value, name) for value in values)
    if len(result) != len(set(result)):
        raise CameraIntrinsicsError(f"{name} cannot repeat an observation ID.")
    return result


def _view_geometry(points: np.ndarray, pattern: CheckerboardPattern) -> dict:
    hull = cv2.convexHull(points.astype(np.float32))
    area = float(cv2.contourArea(hull))
    if area < 0.01 * 1920 * 1080:
        raise CameraIntrinsicsError("Checkerboard view is too small or geometrically degenerate.")
    grid = points.reshape(pattern.rows, pattern.columns, 2)
    horizontal = grid[:-1, 1:] - grid[:-1, :-1]
    vertical = grid[1:, :-1] - grid[:-1, :-1]
    crosses = horizontal[:, :, 0] * vertical[:, :, 1] - horizontal[:, :, 1] * vertical[:, :, 0]
    if np.min(np.abs(crosses)) < 1 or not (np.all(crosses > 0) or np.all(crosses < 0)):
        raise CameraIntrinsicsError("Checkerboard row-major corner ordering is folded or degenerate.")
    span = np.ptp(points, axis=0)
    if span[0] < 80 or span[1] < 60:
        raise CameraIntrinsicsError("Checkerboard view has insufficient native-pixel extent.")
    return {"area_px2": area, "center_px": points.mean(axis=0).tolist(), "span_px": span.tolist()}


def _pre_fit_diversity(points: list[np.ndarray], geometries: list[dict], object_points: np.ndarray) -> dict:
    centers = np.array([g["center_px"] for g in geometries])
    center_span = np.ptp(centers, axis=0)
    coverage = float(cv2.contourArea(cv2.convexHull(np.vstack(points).astype(np.float32)))) / (1920 * 1080)
    areas = [g["area_px2"] for g in geometries]
    area_ratio = max(areas) / min(areas)
    if center_span[0] < 0.15 * 1920 or center_span[1] < 0.15 * 1080 or coverage < 0.20:
        raise CameraIntrinsicsError("Training views need spatial diversity and at least 20 percent image coverage.")
    if area_ratio < 1.3:
        raise CameraIntrinsicsError("Training views need different apparent sizes, not repeated distance.")
    # Normalised image coordinates avoid arbitrary native-pixel conditioning in
    # the planar metric observability check. No RANSAC or view deletion is used.
    constraints = []
    for image_points in points:
        normalised = (image_points - np.array([960, 540])) / 1920
        homography, _ = cv2.findHomography(object_points[:, :2].astype(np.float64), normalised, method=0)
        if homography is None or not np.isfinite(homography).all():
            raise CameraIntrinsicsError("A complete checkerboard view has no finite homography.")

        def metric(i: int, j: int) -> np.ndarray:
            a, b = homography[:, i], homography[:, j]
            return np.array([a[0]*b[0], a[0]*b[1]+a[1]*b[0], a[1]*b[1],
                             a[2]*b[0]+a[0]*b[2], a[2]*b[1]+a[1]*b[2], a[2]*b[2]])

        for row in (metric(0, 1), metric(0, 0) - metric(1, 1)):
            norm = np.linalg.norm(row)
            if norm < 1e-12:
                raise CameraIntrinsicsError("Training metric constraints are degenerate.")
            constraints.append(row / norm)
    singular = np.linalg.svd(np.array(constraints), compute_uv=False)
    if singular[4] / singular[0] < 1e-4:
        raise CameraIntrinsicsError("Training views lack independent planar tilts; intrinsic parameters are unobservable.")
    return {"center_span_px": center_span.tolist(), "convex_hull_image_fraction": coverage,
            "largest_to_smallest_board_area_ratio": area_ratio,
            "normalised_planar_constraint_singular_values": singular.tolist()}


def _residual(object_points: np.ndarray, points: np.ndarray, rvec: np.ndarray,
              tvec: np.ndarray, matrix: np.ndarray, distortion: np.ndarray) -> dict:
    projected, _ = cv2.projectPoints(object_points, rvec, tvec, matrix, distortion)
    if not np.isfinite(projected).all():
        raise CameraIntrinsicsError("Projection contains nonfinite coordinates.")
    errors = np.linalg.norm(projected.reshape(-1, 2) - points, axis=1)
    rotation, _ = cv2.Rodrigues(rvec)
    depths = (object_points.astype(np.float64) @ rotation.T + tvec.reshape(1, 3))[:, 2]
    if not np.isfinite(errors).all() or not np.isfinite(depths).all():
        raise CameraIntrinsicsError("Projection residual or depth is nonfinite.")
    return {"rms_error_px": float(np.sqrt(np.mean(errors**2))), "max_error_px": float(np.max(errors)),
            "corner_errors_px": errors.tolist(), "positive_depth": bool(np.all(depths > 0)),
            "rvec": rvec.reshape(3).tolist(), "tvec_pattern_units": tvec.reshape(3).tolist()}


def calibrate_camera_intrinsics(
    observations: Sequence[CheckerboardObservation], *, training_ids: Sequence[str],
    heldout_ids: Sequence[str], identity: CameraIntrinsicsIdentity, pattern: CheckerboardPattern,
    policy: IntrinsicsPolicy | None = None,
) -> dict:
    """Estimate K/Brown distortion from training only; check every held-out view.

    Pattern units set extrinsic translation units only. A real measured square
    size is unnecessary for K, but the displayed pattern must actually be flat,
    square, and unchanged. Those physical facts are not certified by this API.
    """
    if type(identity) is not CameraIntrinsicsIdentity or type(pattern) is not CheckerboardPattern:
        raise CameraIntrinsicsError("Explicit native identity and checkerboard declaration are required.")
    policy = IntrinsicsPolicy() if policy is None else policy
    if type(policy) is not IntrinsicsPolicy:
        raise CameraIntrinsicsError("Use an explicit predeclared IntrinsicsPolicy.")
    train_ids, check_ids = _ids(training_ids, "training_ids"), _ids(heldout_ids, "heldout_ids")
    if len(train_ids) < 10 or len(check_ids) < 4 or len(train_ids) + len(check_ids) > 80:
        raise CameraIntrinsicsError("Require at least 10 training and 4 held-out views, at most 80 total.")
    if set(train_ids) & set(check_ids):
        raise CameraIntrinsicsError("Training and held-out IDs must be disjoint and declared before fitting.")
    indexed: dict[str, CheckerboardObservation] = {}
    hashes: set[str] = set()
    geometry: dict[str, dict] = {}
    for observation in observations:
        if type(observation) is not CheckerboardObservation:
            raise CameraIntrinsicsError("Each input must be a declared CheckerboardObservation.")
        if observation.identity != identity:
            raise CameraIntrinsicsError("Mixed camera epoch, native size or settings identity is not admitted.")
        if (observation.pattern_id != pattern.pattern_id
                or observation.pattern_sha256 != pattern.pattern_sha256):
            raise CameraIntrinsicsError("Every view must bind the same declared checkerboard pattern.")
        if observation.observation_id in indexed or observation.image_sha256 in hashes:
            raise CameraIntrinsicsError("Reused observation IDs or image bytes are not independent evidence.")
        points = np.array(observation.image_points_px, dtype=np.float64)
        if points.shape != (pattern.columns * pattern.rows, 2):
            raise CameraIntrinsicsError("Every view must contain the complete declared internal-corner grid.")
        geometry[observation.observation_id] = _view_geometry(points, pattern)
        indexed[observation.observation_id] = observation
        hashes.add(observation.image_sha256)
    if set(indexed) != set(train_ids) | set(check_ids):
        raise CameraIntrinsicsError("The predefined split must include every supplied observation exactly once.")
    objects = pattern.object_points()
    heldout_pose_indices = np.arange(0, len(objects), 2, dtype=int)
    heldout_check_indices = np.arange(1, len(objects), 2, dtype=int)
    training = [np.array(indexed[i].image_points_px, dtype=np.float32) for i in train_ids]
    diversity = _pre_fit_diversity(training, [geometry[i] for i in train_ids], objects)
    base_report = {"schema": "pushpilot.offline-camera-intrinsics-candidate.v1", "identity": asdict(identity),
        "pattern": asdict(pattern), "policy": {**asdict(policy), "min_training_views": 10,
            "min_heldout_views": 4, "max_total_views": 80, "min_single_view_frame_area_fraction": 0.01,
            "min_training_center_span_frame_fraction_xy": [0.15, 0.15],
            "min_training_convex_hull_frame_fraction": 0.20, "min_training_board_area_ratio": 1.3,
            "min_training_normal_span_deg": 20, "min_training_normal_xy_component_span": 0.15},
        "training_ids": list(train_ids),
        "heldout_ids": list(check_ids), "discarded_observation_ids": [], "discarded_corner_indices": [],
        "heldout_pose_fit_corner_indices": heldout_pose_indices.tolist(),
        "heldout_unused_check_corner_indices": heldout_check_indices.tolist(),
        "heldout_validation": "Pose uses predefined even corner indices; RMS admission scores unused odd indices. K and distortion are never refitted.",
        "model": "pinhole_zero_skew_five_coefficient_brown_conrady", "distortion_order": ["k1", "k2", "p1", "p2", "k3"],
        "training_diversity": diversity, "accepted_image_model": False, "automatically_installed": False,
        "physical_qualified": False, "contact_face_qualified": False, "board_base_transform_established": False,
        "motion_authority": False, "uncertainty": "Calibration standard deviations and pixel residuals are diagnostics, not physical accuracy or confidence bounds.",
        "physical_assumptions_unverified": ["Flat unchanged square checkerboard", "Unchanged optics, focus, exposure mode and digital crop", "Adequate unmodelled lens-distortion residuals outside observed corners"],
        "observations": [{"id": i, "image_sha256": indexed[i].image_sha256,
            "corner_count": len(indexed[i].image_points_px), **geometry[i]} for i in (*train_ids, *check_ids)]}
    observation_payload = [{"id": i, "image_sha256": indexed[i].image_sha256,
        "points": indexed[i].image_points_px} for i in (*train_ids, *check_ids)]
    base_report["ordered_observations_sha256"] = hashlib.sha256(json.dumps(
        observation_payload, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    try:
        rms, matrix, distortion, rvecs, tvecs, intrinsic_std, extrinsic_std, _ = cv2.calibrateCameraExtended(
            [objects.copy() for _ in training], training, (identity.width, identity.height), None, None,
            flags=0, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-10))
    except cv2.error as error:
        return {**base_report, "failure_reasons": ["OPENCV_CALIBRATION_FAILED"],
                "calibration_error": str(error), "training": [], "heldout": []}
    numeric_arrays = (matrix, distortion, intrinsic_std, extrinsic_std, *rvecs, *tvecs)
    if not math.isfinite(float(rms)) or any(not np.isfinite(a).all() for a in numeric_arrays):
        return {**base_report, "failure_reasons": ["NONFINITE_CALIBRATION_RESULT"], "training": [], "heldout": []}
    distortion = distortion.reshape(-1)
    failures = []
    if (matrix.shape != (3, 3) or distortion.shape != (5,)
            or not 480 <= matrix[0, 0] <= 7680 or not 480 <= matrix[1, 1] <= 7680
            or not 0.8 <= matrix[0, 0] / matrix[1, 1] <= 1.25
            or not 192 <= matrix[0, 2] <= 1728 or not 108 <= matrix[1, 2] <= 972):
        failures.append("IMPLAUSIBLE_INTRINSIC_MATRIX")
    train_reports, check_reports, normals = [], [], []
    for i, points, rvec, tvec in zip(train_ids, training, rvecs, tvecs):
        rotation, _ = cv2.Rodrigues(rvec)
        normals.append(rotation[:, 2])
        try:
            row = {"id": i, **_residual(objects, points, rvec, tvec, matrix, distortion)}
        except (cv2.error, CameraIntrinsicsError) as error:
            train_reports.append({"id": i, "projection_evaluated": False, "error": str(error)})
            failures.append(f"TRAINING_PROJECTION_FAILED:{i}")
            continue
        train_reports.append(row)
        if not row["positive_depth"]:
            failures.append(f"NONPOSITIVE_TRAINING_DEPTH:{i}")
        if row["rms_error_px"] > policy.max_per_view_rms_px:
            failures.append(f"TRAINING_VIEW_RMS_EXCEEDED:{i}")
    normals = np.array(normals)
    normal_span = float(np.degrees(np.max(np.arccos(np.clip(normals @ normals.T, -1, 1)))))
    normal_component_span = np.ptp(normals[:, :2], axis=0)
    diversity.update(normal_span_deg=normal_span, normal_xy_component_span=normal_component_span.tolist())
    if normal_span < 20 or np.min(normal_component_span) < 0.15:
        failures.append("INSUFFICIENT_RECOVERED_TILT_DIVERSITY")
    if rms > policy.max_training_rms_px:
        failures.append("TRAINING_RMS_EXCEEDED")
    # Only each held-out plane pose is solved, using the predefined even-index
    # subset. Odd corners are unused by both camera fitting and this pose fit.
    # Every corner is still reported; admission scores only the unused subset.
    for i in check_ids:
        points = np.array(indexed[i].image_points_px, dtype=np.float64)
        try:
            ok, rvec, tvec = cv2.solvePnP(
                objects[heldout_pose_indices], points[heldout_pose_indices], matrix, distortion,
                flags=cv2.SOLVEPNP_ITERATIVE)
            if not ok or not np.isfinite(rvec).all() or not np.isfinite(tvec).all():
                raise CameraIntrinsicsError("Held-out pose has no finite solution.")
            row = {"id": i, **_residual(objects, points, rvec, tvec, matrix, distortion)}
            errors = np.array(row["corner_errors_px"])
            row.update(pose_fit_corner_indices=heldout_pose_indices.tolist(),
                       check_corner_indices=heldout_check_indices.tolist(),
                       pose_fit_rms_error_px=float(np.sqrt(np.mean(errors[heldout_pose_indices]**2))),
                       unused_rms_error_px=float(np.sqrt(np.mean(errors[heldout_check_indices]**2))),
                       unused_max_error_px=float(np.max(errors[heldout_check_indices])))
            if not row["positive_depth"]:
                failures.append(f"NONPOSITIVE_HELDOUT_DEPTH:{i}")
            if row["rms_error_px"] > policy.max_per_view_rms_px:
                failures.append(f"HELDOUT_ALL_CORNER_RMS_EXCEEDED:{i}")
            if row["unused_rms_error_px"] > policy.max_heldout_rms_px:
                failures.append(f"HELDOUT_VIEW_RMS_EXCEEDED:{i}")
        except (cv2.error, CameraIntrinsicsError) as error:
            row = {"id": i, "pose_solved": False, "error": str(error)}
            failures.append(f"HELDOUT_POSE_FAILED:{i}")
        check_reports.append(row)
    solved_checks = [row for row in check_reports if "rms_error_px" in row]
    heldout_rms = (float(np.sqrt(np.mean([row["unused_rms_error_px"]**2 for row in solved_checks])))
                   if len(solved_checks) == len(check_ids) else None)
    return {**base_report, "accepted_image_model": not failures, "failure_reasons": failures,
        "camera_matrix": matrix.tolist(), "distortion_coefficients": distortion.tolist(),
        "opencv_training_rms_px": float(rms), "heldout_rms_px": heldout_rms,
        "training": train_reports, "heldout": check_reports,
        "standard_deviations_intrinsics": intrinsic_std.reshape(-1).tolist(),
        "standard_deviations_extrinsics": extrinsic_std.reshape(-1).tolist(),
        "standard_deviation_note": "OpenCV local fit uncertainty only; not an accuracy/confidence bound or millimetre claim."}
