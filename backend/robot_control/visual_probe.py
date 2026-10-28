"""Pure, bounded red-tool displacement diagnostics from unchanged native images.

Callers verify the original JPEG SHA-256 before decoding and bind stationary
robot readback separately. This module never captures, persists or moves.
The segmented area centroid is a visual feature, not a TCP or car centre.
Its inverse-homography projection is apparent position on the paper plane;
raised-feature parallax and the physical feature-to-TCP offset are unmeasured.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np


class VisualProbeError(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise VisualProbeError(code)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _digest(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class ProbeIdentity:
    camera_id: str
    camera_epoch: str
    map_id: str
    map_version: str
    map_hash: str
    registration_id: str

    def __post_init__(self):
        _require(all(type(value) is str and 0 < len(value) <= 160 and value == value.strip()
                     for value in vars(self).values()), "INVALID_PROBE_IDENTITY")
        _require(_digest(self.map_hash), "INVALID_MAP_HASH")


@dataclass(frozen=True)
class ProbeFrame:
    image_bgr: np.ndarray
    frame_id: str
    frame_sha256: str
    sequence: int
    captured_at: float
    identity: ProbeIdentity

    def __post_init__(self):
        image = self.image_bgr
        _require(type(image) is np.ndarray and image.dtype == np.uint8 and image.ndim == 3
                 and image.shape[2] == 3 and min(image.shape[:2]) >= 32
                 and image.shape[0] * image.shape[1] <= 20_000_000, "INVALID_NATIVE_BGR_IMAGE")
        _require(type(self.identity) is ProbeIdentity and type(self.frame_id) is str
                 and 0 < len(self.frame_id) <= 160 and _digest(self.frame_sha256), "INVALID_FRAME_BINDING")
        _require(type(self.sequence) is int and self.sequence >= 0
                 and _finite(self.captured_at) and self.captured_at > 0, "INVALID_FRAME_ORDER")


@dataclass(frozen=True)
class ProbePolicy:
    min_component_area_px: int = 64
    max_roi_area_px: int = 1024 * 1024
    min_mask_iou: float = 0.96
    max_area_fraction_change: float = 0.05
    max_median_value_change: float = 35
    min_displacement_px: float = 1.0
    max_displacement_px: float = 100.0
    max_pair_interval_seconds: float = 10.0
    max_after_age_seconds: float = 2.0
    min_flow_points: int = 8

    def __post_init__(self):
        _require(type(self.min_component_area_px) is int and self.min_component_area_px >= 9
                 and type(self.max_roi_area_px) is int and 64 <= self.max_roi_area_px <= 4_194_304,
                 "INVALID_PROBE_POLICY")
        _require(type(self.min_flow_points) is int and 8 <= self.min_flow_points <= 80, "INVALID_PROBE_POLICY")
        _require(all(_finite(value) and value > 0 for key, value in vars(self).items()
                     if key not in {"min_component_area_px", "max_roi_area_px", "min_flow_points"}), "INVALID_PROBE_POLICY")
        _require(0.8 <= self.min_mask_iou <= 1 and self.max_area_fraction_change <= 0.2
                 and self.max_median_value_change <= 80
                 and self.min_displacement_px < self.max_displacement_px <= 500
                 and self.max_after_age_seconds <= self.max_pair_interval_seconds <= 60,
                 "INVALID_PROBE_POLICY")


def _roi(value, image, policy):
    _require(type(value) in (list, tuple) and len(value) == 4
             and all(type(v) is int for v in value), "INVALID_NATIVE_ROI")
    x, y, width, height = value
    _require(x >= 0 and y >= 0 and width >= 8 and height >= 8
             and x + width <= image.shape[1] and y + height <= image.shape[0]
             and width * height <= policy.max_roi_area_px, "INVALID_NATIVE_ROI")
    return x, y, width, height


def _component(image, roi, policy):
    x, y, width, height = roi
    hsv = cv2.cvtColor(image[y:y+height, x:x+width], cv2.COLOR_BGR2HSV)
    # Both ends of OpenCV's circular red hue range. No source image is altered.
    red = (((hsv[:, :, 0] <= 10) | (hsv[:, :, 0] >= 170))
           & (hsv[:, :, 1] >= 100) & (hsv[:, :, 2] >= 50)).astype(np.uint8)
    count, labels, stats, centres = cv2.connectedComponentsWithStats(red, connectivity=8)
    candidates = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= policy.min_component_area_px]
    if len(candidates) != 1:
        return None, "RED_FEATURE_MISSING_OR_AMBIGUOUS"
    index = candidates[0]
    left, top, box_width, box_height, area = stats[index]
    if left == 0 or top == 0 or left + box_width == width or top + box_height == height:
        return None, "RED_FEATURE_CLIPPED"
    mask = (labels == index).astype(np.uint8)
    return {"mask": mask, "centre": centres[index], "area": int(area),
            "pixel": centres[index] + [x, y],
            "value": float(np.median(hsv[:, :, 2][mask != 0]))}, None


def _sparse_flow(before, after, first_roi, second_roi, policy):
    """Conservative translation of a selected red textured PATCH, not its outline.

    Forward/backward LK, retained-point fraction, translation dispersion and
    patch correlation must agree. Repetitive template alternatives are rejected.
    A patch may clip the physical tool; source native images remain unchanged.
    """
    x, y, width, height = first_roi
    gray_before = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)
    gray_after = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)
    patch = gray_before[y:y+height, x:x+width]
    hsv = cv2.cvtColor(before[y:y+height, x:x+width], cv2.COLOR_BGR2HSV)
    mask = ((((hsv[:, :, 0] <= 10) | (hsv[:, :, 0] >= 170))
             & (hsv[:, :, 1] >= 100) & (hsv[:, :, 2] >= 50)).astype(np.uint8) * 255)
    points = cv2.goodFeaturesToTrack(patch, 80, 0.02, 4, mask=mask, blockSize=5)
    quality = {"method": "sparse_flow", "calibrated_probability": False}
    if points is None or len(points) < policy.min_flow_points:
        return None, None, quality, "FLOW_LOW_TEXTURE"
    points = points + np.array([[[x, y]]], dtype=np.float32)
    options = {"winSize": (21, 21), "maxLevel": 2,
               "criteria": (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, .01)}
    following, status, error = cv2.calcOpticalFlowPyrLK(gray_before, gray_after, points, None, **options)
    if following is None:
        return None, None, quality, "FLOW_TRACKING_UNAVAILABLE"
    returning, back_status, _ = cv2.calcOpticalFlowPyrLK(gray_after, gray_before, following, None, **options)
    if returning is None:
        return None, None, quality, "FLOW_TRACKING_UNAVAILABLE"
    initial, final = points.reshape(-1, 2), following.reshape(-1, 2)
    fb = np.linalg.norm(returning.reshape(-1, 2) - initial, axis=1)
    sx, sy, sw, sh = second_roi
    good = ((status.ravel() == 1) & (back_status.ravel() == 1)
            & np.isfinite(final).all(axis=1) & np.isfinite(fb) & (fb <= .5)
            & (error.ravel() <= 12) & (final[:, 0] >= sx) & (final[:, 0] < sx + sw)
            & (final[:, 1] >= sy) & (final[:, 1] < sy + sh))
    quality.update(initial_points=len(initial), retained_points=int(np.count_nonzero(good)),
                   retained_fraction=float(np.mean(good)),
                   forward_status_points=int(np.count_nonzero(status)),
                   backward_status_points=int(np.count_nonzero(back_status)),
                   forward_backward_consistent_points=int(np.count_nonzero(np.isfinite(fb) & (fb <= .5))),
                   photometric_consistent_points=int(np.count_nonzero(error.ravel() <= 12)),
                   inside_after_roi_points=int(np.count_nonzero((final[:, 0] >= sx) & (final[:, 0] < sx+sw)
                                                               & (final[:, 1] >= sy) & (final[:, 1] < sy+sh))))
    if np.count_nonzero(good) < policy.min_flow_points or np.mean(good) < .85:
        return None, None, quality, "FLOW_OCCLUDED_OR_INCONSISTENT"
    displacements = final[good] - initial[good]
    delta = np.median(displacements, axis=0)
    dispersion = float(np.quantile(np.linalg.norm(displacements - delta, axis=1), .9))
    quality.update(flow_dispersion_p90_px=dispersion, forward_backward_max_px=float(np.max(fb[good])))
    if dispersion > .35:
        return None, None, quality, "FLOW_NOT_A_CONSISTENT_TRANSLATION"
    padding = min(100, int(math.ceil(policy.max_displacement_px)))
    ax, ay = max(0, x-padding), max(0, y-padding)
    bx, by = min(after.shape[1], x+width+padding), min(after.shape[0], y+height+padding)
    scores = cv2.matchTemplate(gray_after[ay:by, ax:bx], patch, cv2.TM_CCOEFF_NORMED)
    _, peak, _, peak_location = cv2.minMaxLoc(scores)
    proposed = initial[good].mean(axis=0) + delta
    template_delta = np.array(peak_location) + [ax-x, ay-y]
    quality.update(template_correlation=float(peak), template_flow_disagreement_px=float(np.linalg.norm(template_delta-delta)))
    if not np.isfinite(scores).all() or peak < .95 or np.linalg.norm(template_delta - delta) > 1.25:
        return None, None, quality, "FLOW_TEMPLATE_DISAGREEMENT"
    alternatives = scores.copy()
    px, py = peak_location
    alternatives[max(0, py-4):py+5, max(0, px-4):px+5] = -1
    next_peak = float(np.max(alternatives))
    quality["template_alternative_correlation"] = next_peak
    if next_peak > peak - .02:
        return None, None, quality, "FLOW_REPETITIVE_OR_AMBIGUOUS_PATCH"
    return initial[good].mean(axis=0).astype(float), proposed.astype(float), quality, None


def observe_tool_displacement(before, after, homography, before_roi, after_roi=None, *, now,
                              base_delta_xy_mm=None, policy=None, observation_mode="live", method="component"):
    """Report matched feature displacement; invalid bindings raise, occlusion waits.

    ROIs use unchanged native (x, y, width, height) pixels. Different ROIs may
    follow the same feature, but a new registration or camera never matches.
    Shape consistency can reject visible rotation; symmetric red shapes cannot
    reveal all rotations, so fixed physical orientation remains caller-owned.
    Recorded mode permits retrospective diagnostics with the real current time;
    it does not relabel historical images as live or grant physical admission.
    """
    policy = ProbePolicy() if policy is None else policy
    _require(type(policy) is ProbePolicy and type(before) is ProbeFrame and type(after) is ProbeFrame,
             "INVALID_PROBE_INPUT")
    _require(before.identity == after.identity and before.image_bgr.shape == after.image_bgr.shape,
             "PROBE_IDENTITY_CHANGED")
    _require(before.frame_id != after.frame_id and before.frame_sha256 != after.frame_sha256
             and before.sequence < after.sequence and before.captured_at < after.captured_at,
             "STALE_OR_REUSED_PROBE_FRAME")
    _require(observation_mode in ("live", "recorded"), "INVALID_OBSERVATION_MODE")
    _require(method in ("component", "sparse_flow"), "INVALID_OBSERVATION_METHOD")
    _require(_finite(now) and now >= after.captured_at
             and (observation_mode == "recorded" or now - after.captured_at <= policy.max_after_age_seconds)
             and after.captured_at - before.captured_at <= policy.max_pair_interval_seconds,
             "PROBE_FRAME_NOT_FRESH")
    try:
        raw_matrix = np.asarray(homography)
        _require(raw_matrix.dtype.kind in "iuf", "INVALID_FIXED_HOMOGRAPHY")
        matrix = np.asarray(homography, dtype=np.float64)
        _require(matrix.shape == (3, 3) and np.isfinite(matrix).all()
                 and np.max(np.abs(matrix)) > 0, "INVALID_FIXED_HOMOGRAPHY")
        matrix = matrix / np.max(np.abs(matrix))  # Homogeneous scale, source matrix untouched.
        _require(np.linalg.matrix_rank(matrix) == 3 and np.linalg.cond(matrix) < 1e12,
                 "INVALID_FIXED_HOMOGRAPHY")
        inverse = np.linalg.inv(matrix)
    except (TypeError, ValueError, np.linalg.LinAlgError):
        raise VisualProbeError("INVALID_FIXED_HOMOGRAPHY") from None
    first_roi = _roi(before_roi, before.image_bgr, policy)
    second_roi = _roi(after_roi if after_roi is not None else before_roi, after.image_bgr, policy)
    if base_delta_xy_mm is not None:
        _require(type(base_delta_xy_mm) in (list, tuple) and len(base_delta_xy_mm) == 2
                 and all(_finite(v) and abs(v) <= 100 for v in base_delta_xy_mm), "INVALID_REPORTED_BASE_DELTA")
    result = {"schema": "pushpilot.visual-tool-displacement.v1", "status": "unknown",
              "observation_mode": observation_mode, "physical_admission_allowed": False,
              "method": method,
              "identity": vars(before.identity).copy(),
              "before_frame_id": before.frame_id, "after_frame_id": after.frame_id,
              "before_sha256": before.frame_sha256, "after_sha256": after.frame_sha256,
              "native_dimensions": [before.image_bgr.shape[1], before.image_bgr.shape[0]],
              "source": "native_red_component_area_centroid" if method == "component" else "native_red_patch_sparse_flow",
              "relative_only": True,
              "absolute_tcp_measured": False, "car_pose_measured": False,
              "parallax_corrected": False, "physical_qualified": False,
              "motion_issued": False, "homography_changed": False,
              "sensor_exposure_time_known": False,
              "jpeg_hash_verification": "caller_required_before_decode",
              "physical_orientation_checked": False,
              "reported_base_delta_xy_mm": list(base_delta_xy_mm) if base_delta_xy_mm is not None else None}
    if method == "sparse_flow":
        before_point, after_point, quality, issue = _sparse_flow(before.image_bgr, after.image_bgr, first_roi, second_roi, policy)
        result["quality"] = quality
        if issue:
            return {**result, "reason": issue}
        first, second = {"pixel": before_point}, {"pixel": after_point}
    else:
        first, issue = _component(before.image_bgr, first_roi, policy)
        second, next_issue = _component(after.image_bgr, second_roi, policy)
        if issue or next_issue:
            return {**result, "reason": issue or next_issue}
        area_change = abs(second["area"] / first["area"] - 1)
        value_change = abs(second["value"] - first["value"])
        translation = second["centre"] - first["centre"]
        aligned = cv2.warpAffine(first["mask"], np.array([[1., 0., translation[0]], [0., 1., translation[1]]]),
                                 (second["mask"].shape[1], second["mask"].shape[0]), flags=cv2.INTER_NEAREST)
        union = np.count_nonzero(aligned | second["mask"])
        iou = np.count_nonzero(aligned & second["mask"]) / union if union else 0.0
        result["quality"] = {"aligned_mask_iou": float(iou), "area_fraction_change": area_change,
                             "median_value_change": value_change, "calibrated_probability": False}
        if area_change > policy.max_area_fraction_change or iou < policy.min_mask_iou:
            return {**result, "reason": "FEATURE_OCCLUDED_ROTATED_OR_CHANGED"}
        if value_change > policy.max_median_value_change:
            return {**result, "reason": "FEATURE_LIGHTING_CHANGED"}
    delta = second["pixel"] - first["pixel"]
    if not policy.min_displacement_px <= np.linalg.norm(delta) <= policy.max_displacement_px:
        return {**result, "reason": "FEATURE_MOTION_NOT_OBSERVABLE_OR_OUT_OF_RANGE"}
    pixels = np.array([first["pixel"], second["pixel"]], dtype=np.float64)
    homogeneous = np.column_stack((pixels, np.ones(2))) @ inverse.T
    _require(np.isfinite(homogeneous).all() and np.all(np.abs(homogeneous[:, 2]) > 1e-9)
             and np.prod(np.sign(homogeneous[:, 2])) > 0, "PROJECTION_CROSSES_PAPER_HORIZON")
    apparent = homogeneous[:, :2] / homogeneous[:, 2, None]
    _require(np.isfinite(apparent).all(), "INVALID_APPARENT_PROJECTION")
    return {**result, "status": "observed", "reason": None,
            "before_feature_pixel_xy": first["pixel"].tolist(),
            "after_feature_pixel_xy": second["pixel"].tolist(), "pixel_delta_xy": delta.tolist(),
            "apparent_paper_plane_delta_mm": (apparent[1] - apparent[0]).tolist()}
