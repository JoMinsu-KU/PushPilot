"""Guarded native-resolution marker recovery for the live preview only.

Small foreshortened markers may need the DICT_4X4_50 dictionary's supported
one-bit correction. Independent recovery requires a complete consistent print;
a bound reference may also support fresh partial observations at its expected
positions. The display JPEG, recorded detector and locked homography are never
modified.
"""
from __future__ import annotations

from copy import deepcopy

import cv2
import numpy as np


class LiveMarkerDetector:
    def __init__(self, map_definition, baseline, candidate):
        self.map = map_definition
        self.baseline = baseline
        self.candidate = candidate
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    def __call__(self, image, *, reference_homography=None):
        baseline = self.baseline(image)
        expected = {marker["id"] for marker in self.map.data["markers"]}
        if set(baseline["marker_ids"]) == expected:
            # A complete ordinary decode wins, including its geometry rejection.
            return baseline
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        partial_reference = None
        if reference_homography is not None:
            recovered = self._reference_rois(gray, baseline, expected, reference_homography)
            if recovered is not None:
                if set(recovered["marker_ids"]) == expected:
                    return recovered
                # A partial ROI observation must not prevent an independent
                # complete decode of the same native frame below.
                partial_reference = recovered
        # Two bounded sampling choices handle blurred foreshortened cells.
        # These are internal bit decoding, never a resized camera/display image.
        pool = {}
        rejected = []
        for cell_pixels, ignored_margin in ((8, 0.13), (12, 0.30)):
            # A partial relaxed decode can contain a mistaken ID. Never merge
            # partial IDs across independent sampling profiles.
            pool = {marker["id"]: deepcopy(marker) for marker in baseline["markers"]}
            parameters = cv2.aruco.DetectorParameters()
            parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
            # This dictionary has maxCorrectionBits == 1. The default fraction
            # 0.6 rounds below one bit; 1.0 uses its capacity, never extra bits.
            parameters.errorCorrectionRate = 1.0
            parameters.perspectiveRemovePixelPerCell = cell_pixels
            parameters.perspectiveRemoveIgnoredMarginPerCell = ignored_margin
            corners, ids, rejected = cv2.aruco.ArucoDetector(self.dictionary, parameters).detectMarkers(gray)
            if not self._merge(pool, corners, ids, expected):
                pool = {marker["id"]: deepcopy(marker) for marker in baseline["markers"]}
                continue
            recovered = self._complete(pool, expected, image.shape)
            if recovered is not None:
                return recovered

        # Refine only small rejected quads, not the full 1080p image. Native
        # pixels and offsets are preserved, with at most 32 crops / 64 decodes.
        # This avoids the expensive full-frame AprilTag quad extractor.
        rois = 0
        for quad in rejected:
            x, y, width, height = cv2.boundingRect(np.asarray(quad).reshape(4, 2))
            if not (12 <= width <= 160 and 12 <= height <= 160):
                continue
            if rois >= 32:
                return partial_reference or baseline
            rois += 1
            x0, y0 = max(0, x-15), max(0, y-15)
            roi = gray[y0:min(gray.shape[0], y+height+15), x0:min(gray.shape[1], x+width+15)]
            for margin in (0.13, 0.30):
                parameters = cv2.aruco.DetectorParameters()
                parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG
                parameters.errorCorrectionRate = 1.0
                parameters.perspectiveRemovePixelPerCell = 12
                parameters.perspectiveRemoveIgnoredMarginPerCell = margin
                corners, ids, _ = cv2.aruco.ArucoDetector(self.dictionary, parameters).detectMarkers(roi)
                shifted = [np.asarray(points).reshape(4, 2)+[x0, y0] for points in corners]
                if not self._merge(pool, shifted, ids, expected):
                    return partial_reference or baseline
        return self._complete(pool, expected, image.shape) or partial_reference or baseline

    def _reference_rois(self, gray, baseline, expected, homography):
        """Search fresh native pixels near missing markers, never infer corners.

        The caller binds the reference to the current camera, map and frame.
        Current ordinary detections must independently support its geometry
        before it may select a bounded crop. A missed or covered marker adds
        no observation, and the existing independent fallback remains intact.
        """
        try:
            matrix = np.asarray(homography, dtype=np.float64)
            if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
                return None
            scale = float(np.max(np.abs(matrix)))
            if scale == 0:
                return None
            matrix = matrix / scale
            if np.linalg.matrix_rank(matrix) != 3:
                return None
            known, projected = {}, {}
            for marker in self.map.data["markers"]:
                x, y = marker["center_mm"]
                half = marker["size_mm"] / 2
                corners = np.array([[x-half, y-half], [x+half, y-half],
                                    [x+half, y+half], [x-half, y+half]], dtype=np.float64)
                homogeneous = np.column_stack((corners, np.ones(4))) @ matrix.T
                denominator = homogeneous[:, 2]
                # Reject a horizon through a marker instead of normalizing it.
                if (not np.isfinite(homogeneous).all() or np.any(np.abs(denominator) < 1e-9)
                        or not (np.all(denominator > 0) or np.all(denominator < 0))):
                    return None
                pixels = homogeneous[:, :2] / denominator[:, None]
                if not np.isfinite(pixels).all():
                    return None
                known[marker["id"]] = corners
                projected[marker["id"]] = pixels
            pool, centers = {}, []
            for marker in baseline["markers"]:
                identifier = marker["id"]
                if (identifier not in expected or identifier in pool
                        or not self._matches_reference(marker["corners"], projected[identifier])):
                    return None
                pool[identifier] = deepcopy(marker)
                centers.append(known[identifier].mean(axis=0))
            if set(pool) != set(baseline["marker_ids"]) or len(pool) < 2:
                return None
            board = self.map.data["board"]
            separation = 0.15 * np.hypot(board["width_mm"], board["height_mm"])
            if not any(np.linalg.norm(first-second) >= separation
                       for index, first in enumerate(centers) for second in centers[index+1:]):
                return None
            missing = sorted(expected-set(pool))
            if not 1 <= len(missing) <= 4:
                return None
            crops = {}
            for identifier in missing:
                pixels = projected[identifier]
                if (np.any(pixels < 0) or np.any(pixels[:, 0] >= gray.shape[1])
                        or np.any(pixels[:, 1] >= gray.shape[0])):
                    return None
                x, y, width, height = cv2.boundingRect(pixels.astype(np.float32))
                if not (12 <= width <= 160 and 12 <= height <= 160):
                    return None
                x0, y0 = max(0, x-15), max(0, y-15)
                crops[identifier] = (x0, y0, gray[y0:min(gray.shape[0], y+height+15),
                                                 x0:min(gray.shape[1], x+width+15)])
        except (KeyError, TypeError, ValueError, OverflowError, np.linalg.LinAlgError, cv2.error):
            return None

        # Each profile starts from the same ordinary same-frame detections.
        # Keep one observed pool, never combine partial sampling profiles.
        # At most four missing IDs and three profiles mean at most 12 decodes.
        # Keep the existing AprilTag profiles first. The last native contour
        # profile handles tiny foreshortened cells without image resampling.
        profiles = ((cv2.aruco.CORNER_REFINE_APRILTAG, 7, 0.13),
                    (cv2.aruco.CORNER_REFINE_APRILTAG, 7, 0.30),
                    (cv2.aruco.CORNER_REFINE_NONE, 3, 0.30))
        best_partial = None
        for refinement, threshold_constant, margin in profiles:
            recovered_pool = deepcopy(pool)
            for identifier in missing:
                x0, y0, roi = crops[identifier]
                parameters = cv2.aruco.DetectorParameters()
                parameters.cornerRefinementMethod = refinement
                parameters.adaptiveThreshConstant = threshold_constant
                parameters.errorCorrectionRate = 1.0
                parameters.perspectiveRemovePixelPerCell = 12
                parameters.perspectiveRemoveIgnoredMarginPerCell = margin
                corners, ids, _ = cv2.aruco.ArucoDetector(self.dictionary, parameters).detectMarkers(roi)
                targeted = [] if ids is None else [points for value, points in zip(ids.flatten().tolist(), corners)
                                                   if value == identifier]
                # Neither an unrelated ID nor a duplicate target can fill a gap.
                if len(targeted) != 1:
                    continue
                observed = np.asarray(targeted[0]).reshape(4, 2).astype(float)+[x0, y0]
                if not self._matches_reference(observed, projected[identifier]):
                    continue
                recovered_pool[identifier] = {"id": identifier, "corners": observed.tolist()}
            recovered = self._complete(recovered_pool, expected, gray.shape)
            if recovered is not None:
                return recovered
            # A failed full-print candidate cannot be relabelled as a partial
            # success. Additional partial observations are current native
            # detections only; they neither fit nor replace the reference.
            if len(pool) < len(recovered_pool) < len(expected) and (
                    best_partial is None or len(recovered_pool) > len(best_partial["markers"])):
                best_partial = {"marker_ids": sorted(recovered_pool),
                                "markers": [recovered_pool[value] for value in sorted(recovered_pool)]}
        return best_partial

    @staticmethod
    def _matches_reference(observed, projected):
        observed = np.asarray(observed, dtype=np.float64)
        if observed.shape != (4, 2) or not np.isfinite(observed).all():
            return False
        distances = np.linalg.norm(observed-projected, axis=1)
        return np.sqrt(np.mean(distances**2)) <= 3.0 and max(distances) <= 6.0

    @staticmethod
    def _merge(pool, corners, ids, expected):
        encountered = set()
        if ids is not None:
            for value, points in zip(ids.flatten().tolist(), corners):
                if value not in expected:
                    continue
                if value in encountered:
                    return False
                encountered.add(value)
                observed = np.asarray(points).reshape(4, 2).astype(float)
                if value in pool:
                    distances = np.linalg.norm(observed-np.array(pool[value]["corners"]), axis=1)
                    if np.sqrt(np.mean(distances**2)) > 3.0 or max(distances) > 6.0:
                        return False
                else:
                    pool[value] = {"id": int(value), "corners": observed.tolist()}
        return True

    def _complete(self, pool, expected, shape):
        if set(pool) != expected:
            return None
        recovered = {"marker_ids": sorted(pool), "markers": [pool[value] for value in sorted(pool)]}
        if self.candidate(recovered, shape[1], shape[0]) is None:
            return None
        return recovered
