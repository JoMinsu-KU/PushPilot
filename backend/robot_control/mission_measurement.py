"""Fixed-camera vehicle-axis measurement with independently bounded qualification.

White-car silhouette geometry is useful after tool withdrawal. It does not
identify the nose, reconstruct occlusion, track the tool, refit the camera, or
turn a nominal board homography into accepted physical metrology. A deployment
must supply original accepted holdout evidence for the exact configuration.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math

import cv2
import numpy as np

from .taught_executor import Frame
from .vehicle_observation import VehicleObservationConfig, observe_white_vehicle


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode("utf-8")).hexdigest()


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _axis_error(actual, target):
    return (actual - target + 90.) % 180. - 90.


class QualifiedCarMeasurement:
    """Synchronous, IO-free adapter for a mission observer.

    ``estimate(frame, context)`` accepts the original ``Frame``. Context binds
    map_sha256, car_id, working_z_mm, occlusion_clear and the exact
    occlusion_frame_sha256, plus target_lane={point_mm, heading_deg,
    parallel_axis}. Only parallel-axis observations can be qualified: a white
    body axis cannot independently resolve the 180-degree front/back ambiguity.

    A qualification record contains the canonical configuration hash, four or
    more independent physical holdout samples, accepted error bounds and the
    exact reviewed ROI. Sample coordinates must come from independent external
    reference measurements, not TCP targets or the same visual estimator.
    This class validates their bindings and residuals; it cannot establish the
    authenticity of a supplied physical survey. Release review owns that fact.
    """

    def __init__(self, config: dict):
        self.config = deepcopy(config)
        if not isinstance(config, dict) or config.get("kind") != "planar_car_axis_v1":
            raise ValueError("Use a planar_car_axis_v1 measurement configuration.")
        for key in ("camera_epoch", "car_id", "coordinate_frame_id"):
            if not isinstance(config.get(key), str) or not 0 < len(config[key]) <= 150:
                raise ValueError("Bind the camera epoch and actual car identity.")
        if not _sha(config.get("map_sha256")) or not _finite(config.get("working_z_mm")):
            raise ValueError("Bind the actual map hash and working robot Z.")
        image_size = tuple(config.get("frame_size_px", ()))
        if len(image_size) != 2 or any(type(v) is not int or not 1 <= v <= 8192 for v in image_size):
            raise ValueError("Use the unchanged native frame width and height.")
        dimensions = tuple(config.get("car_dimensions_mm", ()))
        if len(dimensions) != 3 or any(not _finite(v) or not 0 < v <= 500 for v in dimensions):
            raise ValueError("Bind the actual car length, width and height.")
        matrix = np.asarray(config.get("image_to_car_plane_homography"), dtype=np.float64)
        if matrix.shape != (3, 3) or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-12:
            raise ValueError("Use a fixed nonsingular image-to-car-plane homography.")
        self.matrix, self.image_size, self.dimensions = matrix, image_size, dimensions
        self.detector = VehicleObservationConfig(**config["detector"])
        x, y, width, height = self.detector.roi_xywh
        if x + width > image_size[0] or y + height > image_size[1]:
            raise ValueError("The reviewed car ROI must lie inside the native frame.")
        # Include every configuration field except the evidence envelope so an
        # altered ROI, optics/height field, matrix, or threshold invalidates it.
        base = {k: v for k, v in config.items() if k != "qualification"}
        self.configuration_sha256 = canonical_sha256(base)
        self.qualified = False
        self.validation_hull = None
        self.validation_reference_sha256 = None
        self.error_xy_mm, self.error_axis_deg = None, None
        self.blockers = ["Independent physical car-axis/position validation is not installed."]
        if config.get("qualification") is not None:
            self._load_qualification(config["qualification"])

    def _load_qualification(self, envelope):
        if not isinstance(envelope, dict) or not isinstance(envelope.get("record"), dict):
            raise ValueError("Supply the original accepted qualification record and canonical SHA-256.")
        record = envelope["record"]
        digest = canonical_sha256(record)
        if not _sha(envelope.get("reference_sha256")) or digest != envelope["reference_sha256"]:
            raise ValueError("The qualification reference hash does not match its original record.")
        if (record.get("schema") != "pushpilot.car-axis-holdout.v1"
                or record.get("status") != "accepted"
                or record.get("source") != "independent_physical_holdout"
                or record.get("configuration_sha256") != self.configuration_sha256
                or record.get("used_for_fitting") is not False
                or tuple(record.get("roi_xywh", ())) != tuple(self.detector.roi_xywh)
                or not _sha(record.get("independent_reference_dataset_sha256"))):
            raise ValueError("Qualification must be independent accepted holdout evidence for this exact configuration and ROI.")
        xy_bound, angle_bound = record.get("max_xy_error_mm"), record.get("max_axis_error_deg")
        if (not _finite(xy_bound) or not 0 < xy_bound <= 10
                or not _finite(angle_bound) or not 0 < angle_bound <= 15):
            raise ValueError("Use positive independently accepted physical error bounds.")
        samples = record.get("samples")
        if not isinstance(samples, list) or not 4 <= len(samples) <= 500:
            raise ValueError("Use at least four spatially distributed independent holdout samples.")
        image_centers, ids = [], set()
        for sample in samples:
            if not isinstance(sample, dict) or not isinstance(sample.get("id"), str) or sample["id"] in ids:
                raise ValueError("Each holdout sample must have a unique original identity.")
            ids.add(sample["id"])
            if not _sha(sample.get("frame_sha256")) or sample.get("independent_reference") is not True:
                raise ValueError("Every holdout sample needs an original frame and independent reference.")
            points = []
            for key in ("image_centroid_px", "estimated_center_mm", "reference_center_mm"):
                point = sample.get(key)
                if not isinstance(point, (list, tuple)) or len(point) != 2 or any(not _finite(v) for v in point):
                    raise ValueError("Use finite original image and independent physical centre coordinates.")
                points.append(point)
            estimated_angle, reference_angle = sample.get("estimated_axis_deg"), sample.get("reference_axis_deg")
            if not _finite(estimated_angle) or not _finite(reference_angle):
                raise ValueError("Holdout axis values must be independently measured numeric angles.")
            if math.dist(points[1], points[2]) > xy_bound or abs(_axis_error(estimated_angle, reference_angle)) > angle_bound:
                raise ValueError("Original held-out residuals exceed the declared accepted error bounds.")
            x, y, width, height = self.detector.roi_xywh
            if not x <= points[0][0] <= x + width or not y <= points[0][1] <= y + height:
                raise ValueError("Validation samples must lie inside the reviewed car ROI.")
            image_centers.append(points[0])
        hull = cv2.convexHull(np.asarray(image_centers, dtype=np.float32))
        if cv2.contourArea(hull) < 100.:
            raise ValueError("Independent holdout samples must cover a two-dimensional image region.")
        self.validation_hull = hull
        self.validation_reference_sha256 = digest
        self.error_xy_mm, self.error_axis_deg = xy_bound, angle_bound
        self.qualified, self.blockers = True, []

    def readiness(self):
        return {"qualified": self.qualified, "available": self.qualified,
                "blockers": list(self.blockers), "configuration_sha256": self.configuration_sha256,
                "validation_reference_sha256": self.validation_reference_sha256,
                "front_back_resolved": False, "parallel_axis_only": True}

    def estimate(self, frame: Frame, context: dict) -> dict:
        if not isinstance(frame, Frame) or not isinstance(context, dict):
            raise ValueError("Use the original Frame and explicit measurement context.")
        if hashlib.sha256(frame.original_jpeg).hexdigest() != frame.sha256:
            raise ValueError("The original frame hash does not match its bytes.")
        result = {"heading_deg": None, "heading_uncertainty_deg": None,
            "lateral_error_mm": None, "lateral_uncertainty_mm": None,
            "measurement_source": "unmeasured", "measurement_evidence_sha256": None,
            "physical_metric_pose_qualified": False, "heading_front_back_resolved": False,
            "configuration_sha256": self.configuration_sha256,
            "validation_reference_sha256": self.validation_reference_sha256,
            "frame_sha256": frame.sha256, "status": "unavailable", "reasons": [],
            "axis_deg_mod180": None, "centroid_nominal_plane_mm": None}
        if (frame.epoch != self.config["camera_epoch"]
                or context.get("map_sha256", context.get("map_hash")) != self.config["map_sha256"]
                or context.get("car_id") != self.config["car_id"]
                or not _finite(context.get("working_z_mm"))
                or abs(context["working_z_mm"] - self.config["working_z_mm"]) > .1):
            result["reasons"] = ["MEASUREMENT_BINDING_CHANGED"]
            return result
        clear = (context.get("occlusion_clear") is True and context.get("occlusion_frame_sha256") == frame.sha256)
        observed = observe_white_vehicle(frame.original_jpeg, self.detector,
            source_identity={"camera_epoch": frame.epoch, "frame_id": frame.id, "frame_sha256": frame.sha256},
            nominal_image_to_board_homography=self.matrix, reported_car_dimensions_mm=self.dimensions,
            occlusion_status="clear" if clear else "unknown")
        result["diagnostic"] = observed
        if tuple(observed["image_size_px"]) != self.image_size:
            result["reasons"] = ["NATIVE_RESOLUTION_CHANGED"]
            return result
        if observed["status"] != "readable":
            result.update(status=observed["status"], reasons=["CAR_SILHOUETTE_NOT_UNAMBIGUOUS"])
            return result
        nominal = observed["nominal_board"]
        axis = nominal["axis_nominal_board_deg_mod180"]
        center = nominal["centroid_nominal_board_mm"]
        result.update(status="diagnostic_only", axis_deg_mod180=axis, centroid_nominal_plane_mm=center)
        target = context.get("target_lane")
        if isinstance(target, dict) and target.get("coordinate_frame_id") != self.config["coordinate_frame_id"]:
            result["reasons"] = ["TARGET_COORDINATE_FRAME_MISMATCH"]
            return result
        if (not isinstance(target, dict) or target.get("parallel_axis") is not True
                or not _finite(target.get("heading_deg"))
                or not isinstance(target.get("point_mm"), (list, tuple)) or len(target["point_mm"]) != 2
                or any(not _finite(v) for v in target["point_mm"])):
            result["reasons"] = ["DIRECTED_HEADING_UNRESOLVED_OR_TARGET_LANE_MISSING"]
            return result
        heading = target["heading_deg"] + _axis_error(axis, target["heading_deg"])
        heading = (heading + 180.) % 360. - 180.
        direction = math.radians(target["heading_deg"])
        normal = (-math.sin(direction), math.cos(direction))
        lateral = sum((center[i] - target["point_mm"][i]) * normal[i] for i in range(2))
        result["diagnostic_heading_deg"] = heading
        result["diagnostic_lateral_error_mm"] = lateral
        if not self.qualified:
            result["reasons"] = ["INDEPENDENT_PHYSICAL_VALIDATION_REQUIRED"]
            return result
        if not clear:
            result["reasons"] = ["SAME_FRAME_OCCLUSION_EXCLUSION_REQUIRED"]
            return result
        if cv2.pointPolygonTest(self.validation_hull, tuple(observed["centroid_px"]), False) < 0:
            result["reasons"] = ["OUTSIDE_INDEPENDENT_VALIDATION_COVERAGE"]
            return result
        # Threshold spread is added to an independently bounded error. Alone it
        # is segmentation sensitivity, never a physical accuracy certificate.
        angle_error = self.error_axis_deg + nominal["threshold_axis_spread_nominal_deg"]
        position_error = self.error_xy_mm + nominal["threshold_centroid_spread_nominal_mm"]
        result.update(status="qualified", heading_deg=heading, heading_uncertainty_deg=angle_error,
            lateral_error_mm=lateral, lateral_uncertainty_mm=position_error,
            measurement_source="qualified_estimator", physical_metric_pose_qualified=True, reasons=[])
        result["measurement_evidence_sha256"] = canonical_sha256({
            "configuration_sha256": self.configuration_sha256,
            "validation_reference_sha256": self.validation_reference_sha256,
            "frame_sha256": frame.sha256, "frame_id": frame.id, "camera_epoch": frame.epoch,
            "target_lane": target, "centroid_plane_mm": center, "heading_deg": heading,
            "heading_uncertainty_deg": angle_error, "lateral_error_mm": lateral,
            "lateral_uncertainty_mm": position_error, "occlusion_excluded_on_frame": frame.sha256})
        return result
