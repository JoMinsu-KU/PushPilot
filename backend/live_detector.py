"""Guarded native-resolution marker recovery for the live preview only.

Small foreshortened markers may need the DICT_4X4_50 dictionary's supported
one-bit correction. A relaxed decode is accepted only as a complete four-marker
print with the existing strict geometry checks and agreement with baseline IDs.
The display JPEG, recorded detector and locked homography are never modified.
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

    def __call__(self, image):
        baseline = self.baseline(image)
        expected = {marker["id"] for marker in self.map.data["markers"]}
        if set(baseline["marker_ids"]) == expected:
            # A complete ordinary decode wins, including its geometry rejection.
            return baseline
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
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
                return baseline
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
                    return baseline
        return self._complete(pool, expected, image.shape) or baseline

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
