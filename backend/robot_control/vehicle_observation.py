"""Car-only original-frame diagnostics; never a TCP detector or motion gate.

The caller selects an open-road ROI and expected image-size range before the
measurement. White silhouettes are compared across thresholds, without
inpainting, temporal prediction or filling an occluded car. A readable image
estimate is not proof that the complete body is visible: an independent scene
review must still check tool occlusion. Nominal board projection deliberately
leaves the reported 15 mm body height/parallax uncorrected.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math

import cv2
import numpy as np


@dataclass(frozen=True)
class VehicleObservationConfig:
    roi_xywh: tuple[int, int, int, int]
    area_range_px2: tuple[float, float]
    long_side_range_px: tuple[float, float]
    short_side_range_px: tuple[float, float]
    value_thresholds: tuple[int, ...] = (170, 180, 190, 200)
    saturation_max: int = 60
    min_solidity: float = .85
    min_rectangle_fill: float = .60
    border_margin_px: int = 2
    max_centroid_spread_px: float = 3.
    max_axis_spread_deg: float = 3.

    def __post_init__(self):
        if (len(self.roi_xywh) != 4 or any(type(value) is not int for value in self.roi_xywh)
            or min(self.roi_xywh[:2]) < 0 or min(self.roi_xywh[2:]) <= 0):
            raise ValueError("Use an explicit positive integer original-image ROI.")
        for limits in (self.area_range_px2, self.long_side_range_px, self.short_side_range_px):
            if (len(limits) != 2 or any(type(value) not in (int, float) or not math.isfinite(value) for value in limits)
                or not 0 < limits[0] < limits[1]):
                raise ValueError("Supply positive bounded expected car pixel area and side ranges.")
        if (not 3 <= len(self.value_thresholds) <= 8 or len(set(self.value_thresholds)) != len(self.value_thresholds)
            or any(type(value) is not int or not 1 <= value <= 254 for value in self.value_thresholds)
            or type(self.saturation_max) is not int or not 0 <= self.saturation_max <= 255):
            raise ValueError("Use three to eight distinct finite white-body thresholds.")
        if (type(self.border_margin_px) is not int or self.border_margin_px < 1
            or not .5 <= self.min_solidity <= 1 or not .5 <= self.min_rectangle_fill <= 1
            or not 0 < self.max_centroid_spread_px <= 20 or not 0 < self.max_axis_spread_deg < 45):
            raise ValueError("Use explicit bounded shape, border and sensitivity limits.")


def _axis_delta(first: float, second: float) -> float:
    return (second-first+90.) % 180.-90.


def project_vehicle_axis(centroid_px, axis_deg_mod180, image_to_board_homography, *, axis_half_length_px=20.) -> dict:
    """Project observed image points through a supplied locked display matrix.

    This does not correct the object's elevation or make the resulting mm
    accurate. The two explicit axis points make the coordinate convention and
    projective transformation inspectable without finding a gripper feature.
    """
    center = np.asarray(centroid_px, dtype=np.float64)
    matrix = np.asarray(image_to_board_homography, dtype=np.float64)
    if (center.shape != (2,) or not np.isfinite(center).all() or matrix.shape != (3, 3)
        or not np.isfinite(matrix).all() or abs(float(np.linalg.det(matrix))) < 1e-12
        or type(axis_deg_mod180) not in (int, float) or not math.isfinite(axis_deg_mod180)
        or type(axis_half_length_px) not in (int, float) or not 0 < axis_half_length_px <= 1000):
        raise ValueError("Supply finite image centre/axis points and a nonsingular locked image-to-board display homography.")
    direction = np.array([math.cos(math.radians(axis_deg_mod180)), math.sin(math.radians(axis_deg_mod180))])
    points = np.asarray([center, center-axis_half_length_px*direction, center+axis_half_length_px*direction])
    projected = cv2.perspectiveTransform(points.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    if not np.isfinite(projected).all() or np.linalg.norm(projected[2]-projected[1]) < 1e-12:
        raise ValueError("The observed image axis cannot be projected onto this nominal display plane.")
    vector = projected[2]-projected[1]
    return {"centroid_nominal_board_mm": projected[0].tolist(),
        "axis_nominal_board_deg_mod180": math.degrees(math.atan2(vector[1], vector[0])) % 180.,
        "source_axis_points_px": points[1:].tolist(), "projected_axis_points_nominal_mm": projected[1:].tolist(),
        "image_to_board_homography_sha256": hashlib.sha256(matrix.astype("<f8").tobytes()).hexdigest(),
        "physical_metric_pose_qualified": False, "plane_projection_parallax_corrected": False,
        "physical_parallax_and_shape_error_bound": None,
        "warning": "Nominal display-plane coordinates only. Elevated 3D car shape, lens distortion and parallax errors are unbounded; no BASE authority."}


def _contour_measurement(contour: np.ndarray) -> dict:
    points = contour.reshape(-1, 2).astype(np.float64)
    moments = cv2.moments(contour)
    center = np.array([moments["m10"]/moments["m00"], moments["m01"]/moments["m00"]])
    # Area moments measure the filled observed silhouette, not only a variable
    # number of edge samples. No unobserved part of the body is reconstructed.
    covariance = np.array([[moments["mu20"], moments["mu11"]],
                           [moments["mu11"], moments["mu02"]]])/moments["m00"]
    values, vectors = np.linalg.eigh(covariance)
    direction = vectors[:, int(np.argmax(values))]
    angle = math.degrees(math.atan2(direction[1], direction[0])) % 180.
    rectangle = cv2.minAreaRect(points.astype(np.float32))
    short, long = sorted(float(value) for value in rectangle[1])
    area = float(cv2.contourArea(contour))
    hull_area = float(cv2.contourArea(cv2.convexHull(contour)))
    return {"centroid_px": center.tolist(), "axis_deg_mod180": angle,
            "area_px2": area, "long_side_px": long, "short_side_px": short,
            "solidity": area/hull_area if hull_area else 0.,
            "rectangle_fill": area/(long*short) if long*short else 0.}


def _nominal_projection(contour: np.ndarray, matrix, dimensions_mm) -> dict:
    homography = np.asarray(matrix, dtype=np.float64)
    if (homography.shape != (3, 3) or not np.isfinite(homography).all()
        or abs(float(np.linalg.det(homography))) < 1e-12):
        raise ValueError("Supply the unchanged finite nonsingular board-mm-to-original-image display homography.")
    projected = cv2.perspectiveTransform(contour.astype(np.float64), np.linalg.inv(homography))
    if not np.isfinite(projected).all():
        raise ValueError("The contour cannot be projected onto the nominal display plane.")
    measured = _contour_measurement(projected.astype(np.float32))
    return {"centroid_nominal_board_mm": measured["centroid_px"],
            "axis_nominal_board_deg_mod180": measured["axis_deg_mod180"],
            "bounding_long_short_nominal_mm": [measured["long_side_px"], measured["short_side_px"]],
            "reported_car_length_width_height_mm": list(dimensions_mm),
            "bounding_size_difference_from_reported_mm": [measured["long_side_px"]-dimensions_mm[0],
                                                          measured["short_side_px"]-dimensions_mm[1]],
            "plane_projection_parallax_corrected": False, "physical_metric_pose_qualified": False,
            "warning": "Display-plane projection only: car height, lens distortion and face parallax remain unqualified; no BASE mapping."}


def observe_white_vehicle(original_frame: bytes, config: VehicleObservationConfig, *,
                          source_identity: dict, nominal_board_to_image_homography=None,
                          nominal_image_to_board_homography=None, reported_car_dimensions_mm=(45., 18., 15.),
                          occlusion_status="unknown") -> dict:
    """Analyze one unchanged frame in a caller-reviewed car-only search window.

    source_identity requires camera_epoch, frame_id and frame_sha256. Other
    provenance is retained verbatim. No acquisition, freshness assertion,
    robot script, command, gripper position or inferred hidden centre exists.
    """
    if type(original_frame) is not bytes or not 0 < len(original_frame) <= 10*1024*1024:
        raise ValueError("Use original encoded camera bytes, bounded to 10 MiB.")
    if (nominal_board_to_image_homography is not None and nominal_image_to_board_homography is not None
        or occlusion_status not in {"clear", "occluded", "unknown"}):
        raise ValueError("Use one explicit homography direction and an explicit external occlusion assessment.")
    if nominal_image_to_board_homography is not None:
        matrix = np.asarray(nominal_image_to_board_homography, dtype=np.float64)
        if matrix.shape != (3, 3) or not np.isfinite(matrix).all() or abs(float(np.linalg.det(matrix))) < 1e-12:
            raise ValueError("Supply a finite nonsingular locked image-to-board display homography.")
        nominal_board_to_image_homography = np.linalg.inv(matrix)
    digest = hashlib.sha256(original_frame).hexdigest()
    if (type(source_identity) is not dict or source_identity.get("frame_sha256") != digest
        or any(type(source_identity.get(key)) is not str or not source_identity[key] for key in ("camera_epoch", "frame_id"))):
        raise ValueError("Bind the original frame hash and explicit camera/frame identities.")
    if (len(reported_car_dimensions_mm) != 3 or any(type(value) not in (int, float)
        or not math.isfinite(value) or not 0 < value <= 500 for value in reported_car_dimensions_mm)):
        raise ValueError("Use bounded reported car length, width and height, without implying a survey.")
    image = cv2.imdecode(np.frombuffer(original_frame, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The original frame cannot be decoded.")
    height, width = image.shape[:2]
    x, y, roi_width, roi_height = config.roi_xywh
    if x+roi_width > width or y+roi_height > height:
        raise ValueError("The car search ROI must lie wholly inside the original frame.")
    hsv = cv2.cvtColor(image[y:y+roi_height, x:x+roi_width], cv2.COLOR_BGR2HSV)
    samples, contours_by_threshold = [], []
    for value in config.value_thresholds:
        mask = np.uint8((hsv[:, :, 1] <= config.saturation_max) & (hsv[:, :, 2] >= value))*255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates, clipped_body = [], False
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if not config.area_range_px2[0] <= area <= config.area_range_px2[1]:
                continue
            measured = _contour_measurement(contour)
            bx, by, bw, bh = cv2.boundingRect(contour)
            touches_border = (bx < config.border_margin_px or by < config.border_margin_px
                or bx+bw > roi_width-config.border_margin_px or by+bh > roi_height-config.border_margin_px)
            if touches_border:
                clipped_body = True
                continue
            if not (config.long_side_range_px[0] <= measured["long_side_px"] <= config.long_side_range_px[1]
                    and config.short_side_range_px[0] <= measured["short_side_px"] <= config.short_side_range_px[1]
                    and measured["solidity"] >= config.min_solidity and measured["rectangle_fill"] >= config.min_rectangle_fill):
                continue
            absolute = contour.copy()
            absolute[:, 0, 0] += x
            absolute[:, 0, 1] += y
            measured["centroid_px"][0] += x
            measured["centroid_px"][1] += y
            candidates.append((measured, absolute))
        sample = {"value_threshold": value, "candidate_count": len(candidates), "clipped_body_candidate": clipped_body}
        if len(candidates) == 1 and not clipped_body:
            sample.update(candidates[0][0])
            contours_by_threshold.append(candidates[0][1])
        else:
            contours_by_threshold.append(None)
        samples.append(sample)
    result = {"schema": "pushpilot.vehicle-image-observation.v1", "source": "original_image_diagnostic",
        "source_identity": dict(source_identity), "original_frame_sha256": digest, "image_size_px": [width, height],
        "config": asdict(config), "threshold_samples": samples, "status": "unreadable",
        "centroid_px": None, "axis_deg_mod180": None, "nominal_board": None,
        "heading_front_back_resolved": False, "occlusion_independently_excluded": False,
        "external_occlusion_assessment": occlusion_status,
        "tcp_tracking_used": False, "motion_authority": False, "physical_metric_pose_qualified": False,
        "limitations": ["A white silhouette cannot independently exclude partial tool occlusion or similar printed artwork.",
                        "Search ROI and size bounds must isolate the physical car from paper, buildings and printed cars.",
                        "Axis has an inherent 180-degree front/back ambiguity; no hidden outline is filled.",
                        "Threshold spread is segmentation sensitivity only; physical parallax and shape error remain unbounded."]}
    if occlusion_status == "occluded":
        result["status"] = "occluded"
        return result
    if any(sample["candidate_count"] > 1 for sample in samples):
        result["status"] = "ambiguous"
        return result
    if any(contour is None for contour in contours_by_threshold):
        return result
    centers = np.asarray([sample["centroid_px"] for sample in samples])
    angles = np.asarray([sample["axis_deg_mod180"] for sample in samples])
    reference = float(angles[0])
    unwrapped = np.array([reference+_axis_delta(reference, float(angle)) for angle in angles])
    center_spread, axis_spread = float(np.linalg.norm(np.ptp(centers, axis=0))), float(np.ptp(unwrapped))
    result["centroid_spread_px"] = center_spread
    result["axis_spread_deg"] = axis_spread
    if center_spread > config.max_centroid_spread_px or axis_spread > config.max_axis_spread_deg:
        result["status"] = "uncertain"
        return result
    result.update(status="readable", centroid_px=np.median(centers, axis=0).tolist(),
                  axis_deg_mod180=float(np.median(unwrapped) % 180.))
    if nominal_board_to_image_homography is not None:
        projections = [_nominal_projection(contour, nominal_board_to_image_homography, reported_car_dimensions_mm)
                       for contour in contours_by_threshold]
        nominal = dict(projections[len(projections)//2])
        board_centers = np.asarray([value["centroid_nominal_board_mm"] for value in projections])
        board_angles = [value["axis_nominal_board_deg_mod180"] for value in projections]
        board_unwrapped = [board_angles[0]+_axis_delta(board_angles[0], value) for value in board_angles]
        nominal["centroid_nominal_board_mm"] = np.median(board_centers, axis=0).tolist()
        nominal["axis_nominal_board_deg_mod180"] = float(np.median(board_unwrapped) % 180.)
        nominal["threshold_centroid_spread_nominal_mm"] = float(np.linalg.norm(np.ptp(board_centers, axis=0)))
        nominal["threshold_axis_spread_nominal_deg"] = float(np.ptp(board_unwrapped))
        nominal["display_homography_sha256"] = hashlib.sha256(np.asarray(nominal_board_to_image_homography, dtype="<f8").tobytes()).hexdigest()
        nominal["physical_parallax_and_shape_error_bound"] = None
        nominal["projected_observed_axis"] = project_vehicle_axis(result["centroid_px"], result["axis_deg_mod180"],
            np.linalg.inv(np.asarray(nominal_board_to_image_homography, dtype=np.float64)),
            axis_half_length_px=float(np.median([sample["long_side_px"] for sample in samples]))/2.)
        result["nominal_board"] = nominal
    return result


def compare_vehicle_observations(before: dict, after: dict, *, previous_directed_heading_deg=None,
                                 previous_nominal_board_heading_deg=None, max_axis_change_deg=35.) -> dict:
    """Compare visible outcomes; heading unwrapping needs an explicit prior.

    A bounded image-axis delta does not resolve which physical end is the
    front. A caller-provided initial heading must come from actual setup, and
    remains an assumption rather than a fresh semantic front detector.
    """
    if type(max_axis_change_deg) not in (int, float) or not 0 < max_axis_change_deg < 90:
        raise ValueError("Temporal axis comparison requires a declared change bound below 90 degrees.")
    for heading in (previous_directed_heading_deg, previous_nominal_board_heading_deg):
        if heading is not None and (type(heading) not in (int, float) or not math.isfinite(heading)):
            raise ValueError("An optional actual-setup directed heading must be finite.")
    result = {"schema": "pushpilot.vehicle-image-comparison.v1", "status": "unreadable",
              "original_frame_sha256": [value.get("original_frame_sha256") for value in (before, after)],
              "centroid_delta_px": None, "axis_delta_deg": None, "directed_heading_deg": None,
              "front_identity_source": "caller_prior_assumption" if previous_directed_heading_deg is not None else "unresolved",
              "motion_authority": False, "physical_metric_pose_qualified": False, "nominal_board_delta": None,
              "camera_motion_independently_excluded": False, "physical_parallax_and_shape_error_bound": None}
    if before.get("status") != "readable" or after.get("status") != "readable":
        return result
    if (before["source_identity"]["camera_epoch"] != after["source_identity"]["camera_epoch"]
        or before["image_size_px"] != after["image_size_px"]
        or before["original_frame_sha256"] == after["original_frame_sha256"]):
        result["status"] = "source_mismatch"
        return result
    delta = _axis_delta(before["axis_deg_mod180"], after["axis_deg_mod180"])
    result["axis_threshold_spread_sum_deg"] = before["axis_spread_deg"]+after["axis_spread_deg"]
    result["centroid_threshold_spread_sum_px"] = before["centroid_spread_px"]+after["centroid_spread_px"]
    if abs(delta)+result["axis_threshold_spread_sum_deg"] > max_axis_change_deg:
        result["status"] = "axis_change_exceeds_declared_bound"
        return result
    result.update(status="readable", centroid_delta_px=(np.array(after["centroid_px"])-before["centroid_px"]).tolist(), axis_delta_deg=delta)
    if previous_directed_heading_deg is not None:
        if abs(_axis_delta(previous_directed_heading_deg, before["axis_deg_mod180"])) > max_axis_change_deg:
            result.update(status="heading_prior_disagrees", centroid_delta_px=None, axis_delta_deg=None)
            return result
        before_heading = previous_directed_heading_deg+_axis_delta(previous_directed_heading_deg, before["axis_deg_mod180"])
        result["directed_heading_deg"] = before_heading+delta
    first, second = before.get("nominal_board"), after.get("nominal_board")
    if first and second and first["display_homography_sha256"] == second["display_homography_sha256"]:
        result["nominal_board_delta"] = {"centroid_delta_nominal_mm": (np.array(second["centroid_nominal_board_mm"])-first["centroid_nominal_board_mm"]).tolist(),
            "axis_delta_nominal_deg": _axis_delta(first["axis_nominal_board_deg_mod180"], second["axis_nominal_board_deg_mod180"]),
            "plane_projection_parallax_corrected": False, "physical_metric_pose_qualified": False,
            "physical_parallax_and_shape_error_bound": None, "directed_heading_nominal_board_deg": None}
        if previous_nominal_board_heading_deg is not None:
            prior_delta = _axis_delta(previous_nominal_board_heading_deg, first["axis_nominal_board_deg_mod180"])
            observed_delta = result["nominal_board_delta"]["axis_delta_nominal_deg"]
            sensitivity = first["threshold_axis_spread_nominal_deg"]+second["threshold_axis_spread_nominal_deg"]
            if abs(prior_delta) <= max_axis_change_deg and abs(observed_delta)+sensitivity <= max_axis_change_deg:
                result["nominal_board_delta"]["directed_heading_nominal_board_deg"] = previous_nominal_board_heading_deg+prior_delta+observed_delta
    return result
