"""Unchanged-print route receipt derivation; synthetic native frames, no devices."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import httpx
import numpy as np

from backend.display_revision import derive_route_revision_reference
from backend.live_camera import LiveCamera
from backend.maps import MapDefinition
from backend.scene import SceneError


CITY_MAP = Path(__file__).resolve().parents[1] / "backend" / "data" / "seoul-city-a3.json"


class DisplayRevisionTests(unittest.TestCase):
    def setUp(self):
        self.previous = MapDefinition(CITY_MAP)
        revised = self.previous.data
        revised["version"] += ".route-test"
        revised["edges"][0]["bidirectional"] = not revised["edges"][0]["bidirectional"]
        self.current = MapDefinition(data=revised)
        self.matrix = [[2.0, 0.1, 100.0], [0.03, 2.0, 100.0], [0.00001, 0.00002, 1.0]]
        ok, encoded = cv2.imencode(".jpg", np.full((960, 1280, 3), 220, np.uint8))
        assert ok
        self.jpeg = encoded.tobytes()
        self.received_at = datetime.now(timezone.utc).isoformat()
        self.snapshot = {
            "schema_version": "pushpilot.live-camera.v1", "enabled": True, "state": "live",
            "camera_id": "synthetic-route-revision", "epoch": "a" * 32,
            "map_id": self.previous.id, "map_version": self.previous.version,
            "map_hash": self.previous.geometry_hash, "motion_authority": False, "last_error": None,
            "frame": {"id": "b" * 32, "image_url": f"/api/v1/live-camera/frames/{'b' * 32}/image",
                      "source": "live", "width": 1280, "height": 960, "sequence": 20,
                      "age_ms": 100.0, "received_at": self.received_at,
                      "sha256": hashlib.sha256(self.jpeg).hexdigest()},
            "registration": {"id": "c" * 32, "reference_frame_id": "d" * 32,
                             "status": "locked_partial", "verification": "visible_markers",
                             "homography": deepcopy(self.matrix), "residual_px": 0.0},
            "detection": self.markers(self.previous, (11, 12, 13)),
        }

    def markers(self, definition, identifiers):
        markers = []
        for marker in definition.data["markers"]:
            if marker["id"] not in identifiers:
                continue
            x, y = marker["center_mm"]
            half = marker["size_mm"] / 2
            corners = np.array([[x-half, y-half], [x+half, y-half],
                                [x+half, y+half], [x-half, y+half]], dtype=np.float64)
            observed = cv2.perspectiveTransform(corners.reshape(-1, 1, 2),
                                                np.array(self.matrix)).reshape(4, 2)
            markers.append({"id": marker["id"], "corners": observed.tolist()})
        return {"marker_ids": [marker["id"] for marker in markers], "markers": markers}

    def derive(self, snapshot=None, previous=None, current=None):
        return derive_route_revision_reference(previous or self.previous, current or self.current,
                                               self.snapshot if snapshot is None else snapshot)

    def assert_rejected(self, snapshot=None, previous=None, current=None, code="DISPLAY_REVISION_SNAPSHOT"):
        with self.assertRaises(SceneError) as raised:
            self.derive(snapshot, previous, current)
        self.assertEqual(raised.exception.code, code)

    def test_explicit_route_revision_retains_exact_transform_and_native_observations(self):
        original = deepcopy(self.snapshot)
        with patch("cv2.findHomography", side_effect=AssertionError("Route revision must never fit.")):
            derived = self.derive()
        self.assertEqual(self.snapshot, original)
        self.assertEqual(derived["frame"], original["frame"])
        self.assertEqual(derived["detection"], original["detection"])
        self.assertEqual(derived["registration"]["homography"], original["registration"]["homography"])
        self.assertEqual(derived["registration"]["reference_frame_id"], original["registration"]["reference_frame_id"])
        self.assertNotEqual(derived["registration"]["id"], original["registration"]["id"])
        self.assertNotEqual(self.derive()["registration"]["id"], derived["registration"]["id"])
        self.assertEqual(derived["map_version"], self.current.version)
        self.assertEqual(derived["map_hash"], self.current.geometry_hash)
        record = derived["registration"]["route_revision"]
        self.assertEqual(record["reason"], "unchanged_print_route_revision")
        self.assertEqual(record["source_reference_id"], original["registration"]["id"])
        self.assertEqual(record["previous_map"]["geometry_hash"], self.previous.geometry_hash)
        self.assertEqual(record["current_map"]["geometry_hash"], self.current.geometry_hash)
        self.assertEqual(record["source_frame_id"], original["frame"]["id"])
        self.assertFalse(record["homography_changed"])
        self.assertEqual(record["coordinate_authority"], "display_only")
        self.assertFalse(record["motion_authority"])
        derived["frame"]["sequence"] = 999
        derived["detection"]["markers"].clear()
        derived["registration"]["homography"][0][0] = 99
        self.assertEqual(self.snapshot, original)

    def test_two_distributed_markers_are_sufficient_without_recreating_hidden_markers(self):
        self.snapshot["detection"] = self.markers(self.previous, (11, 13))
        derived = self.derive()
        self.assertEqual(derived["detection"]["marker_ids"], [11, 13])
        self.assertEqual(len(derived["detection"]["markers"]), 2)

    def test_rejects_changed_print_and_calibration_facts(self):
        changes = [
            ("map identity", lambda data: data.update(id="different-print")),
            ("source bytes", lambda data: data["source"].update(sha256="0" * 64)),
            ("source dimensions", lambda data: data["source"].update(image_size_px=[2401, 1697])),
            ("board", lambda data: data["board"].update(road_width_mm=43)),
            ("page", lambda data: data["page"].update(width_mm=421)),
            ("marker layout", lambda data: data["markers"][0].update(center_mm=[13.0, 10.0])),
            ("panel", lambda data: data["building_panels"][0]["bounds_mm"].__setitem__(0, 61.0)),
            ("registration mode", lambda data: data.update(camera_registration_supported=False)),
        ]
        for label, mutate in changes:
            with self.subTest(change=label):
                data = self.current.data
                mutate(data)
                self.assert_rejected(current=MapDefinition(data=data), code="DISPLAY_REVISION_MAP")
        # Corrupted private input is rejected even before its normal map validator.
        corrupt = deepcopy(self.current)
        corrupt._data["marker_dictionary"] = "DICT_5X5_50"
        self.assert_rejected(current=corrupt, code="DISPLAY_REVISION_MAP")

    def test_rejects_absent_or_malformed_source_identity_and_nonrevision(self):
        for source in ({}, {"sha256": "invalid", "image_size_px": [2400, 1697]},
                       {"sha256": "0" * 64, "image_size_px": [True, 1697]}):
            with self.subTest(source=source):
                data = self.current.data
                data["source"] = source
                self.assert_rejected(current=MapDefinition(data=data), code="DISPLAY_REVISION_MAP")
        self.assert_rejected(current=self.previous, code="DISPLAY_REVISION_MAP")
        data = self.previous.data
        data["version"] += ".version-only"
        self.assert_rejected(current=MapDefinition(data=data), code="DISPLAY_REVISION_MAP")
        data = self.current.data
        data["version"] = self.previous.version
        self.assert_rejected(current=MapDefinition(data=data), code="DISPLAY_REVISION_MAP")

    def test_rejects_stale_unregistered_changed_or_contradictory_snapshots(self):
        changes = [
            ("enabled", lambda item: item.update(enabled=False)),
            ("stale state", lambda item: item.update(state="stale")),
            ("stale age", lambda item: item["frame"].update(age_ms=1500.1)),
            ("negative age", lambda item: item["frame"].update(age_ms=-1)),
            ("nonfinite age", lambda item: item["frame"].update(age_ms=float("nan"))),
            ("unregistered", lambda item: item["registration"].update(status="unregistered")),
            ("view changed", lambda item: item["registration"].update(status="view_changed")),
            ("disagreement", lambda item: item["registration"].update(verification="marker_disagreement")),
            ("unverified", lambda item: item["registration"].update(verification="insufficient_visibility")),
            ("transport error", lambda item: item.update(last_error="Unavailable frame.")),
            ("motion authority", lambda item: item.update(motion_authority=True)),
        ]
        for label, mutate in changes:
            with self.subTest(change=label):
                item = deepcopy(self.snapshot)
                mutate(item)
                self.assert_rejected(item)

    def test_rejects_wrong_old_map_identity_and_invalid_native_frame_identity(self):
        changes = [
            lambda item: item.update(map_id="another-print"),
            lambda item: item.update(map_version="earlier"),
            lambda item: item.update(map_hash="0" * 64),
            lambda item: item.update(epoch="invalid"),
            lambda item: item.update(camera_id=""),
            lambda item: item.update(camera_id="camera\ninvalid"),
            lambda item: item["frame"].update(source="recorded"),
            lambda item: item["frame"].update(sequence=-1),
            lambda item: item["frame"].update(sequence=True),
            lambda item: item["frame"].update(width=True),
            lambda item: item["frame"].update(width=100000),
            lambda item: item["frame"].update(id="invalid"),
            lambda item: item["frame"].update(sha256="invalid"),
            lambda item: item["frame"].update(image_url="https://example.invalid/frame.jpg"),
            lambda item: item["frame"].update(received_at="2026-10-28T00:00:00"),
            lambda item: item["registration"].update(reference_frame_id="invalid"),
        ]
        for index, mutate in enumerate(changes):
            with self.subTest(change=index):
                item = deepcopy(self.snapshot)
                mutate(item)
                self.assert_rejected(item)
        for malformed in ([], None, {}, {"schema_version": "wrong"}):
            with self.subTest(snapshot=malformed):
                with self.assertRaises(SceneError):
                    derive_route_revision_reference(self.previous, self.current, malformed)

    def test_rejects_invalid_or_singular_exact_homographies(self):
        for matrix in (None, [], [[1, 0], [0, 1]], [[1, 0, 0], [0, 0, 0], [0, 0, 1]],
                       [[True, 0, 0], [0, 1, 0], [0, 0, 1]],
                       [[float("nan"), 0, 0], [0, 1, 0], [0, 0, 1]]):
            with self.subTest(matrix=matrix):
                item = deepcopy(self.snapshot)
                item["registration"]["homography"] = matrix
                self.assert_rejected(item)

    def test_rejects_missing_unknown_duplicate_and_inconsistent_marker_evidence(self):
        changes = [
            lambda item: item.update(detection={}),
            lambda item: item.update(detection=self.markers(self.previous, (11,))),
            lambda item: item["detection"]["markers"][0].update(id=49),
            lambda item: item["detection"]["markers"].append(deepcopy(item["detection"]["markers"][0])),
            lambda item: item["detection"]["marker_ids"].append(11),
            lambda item: item["detection"].update(marker_ids=[11, 12]),
            lambda item: item["detection"]["markers"][0].update(corners=[[0, 0]]),
            lambda item: item["detection"]["markers"][0]["corners"][0].__setitem__(0, float("inf")),
            lambda item: item["detection"]["markers"][0]["corners"][0].__setitem__(0, True),
            lambda item: item["detection"]["markers"][0]["corners"][0].__setitem__(0, -1),
        ]
        for index, mutate in enumerate(changes):
            with self.subTest(change=index):
                item = deepcopy(self.snapshot)
                mutate(item)
                self.assert_rejected(item, code="DISPLAY_REVISION_MARKERS")

    def test_rejects_per_marker_rms_and_maximum_disagreement_without_refitting(self):
        for mode in ("rms", "maximum"):
            item = deepcopy(self.snapshot)
            corners = item["detection"]["markers"][0]["corners"]
            if mode == "rms":
                item["detection"]["markers"][0]["corners"] = [[x+3.1, y] for x, y in corners]
            else:
                # One 6.1 px corner exceeds the max even if other markers reduce aggregate RMS.
                corners[0][0] += 6.1
            with self.subTest(mode=mode), patch("cv2.findHomography", side_effect=AssertionError("No fit.")):
                self.assert_rejected(item, code="DISPLAY_REVISION_MARKERS")

    def test_exact_pixel_residual_limits_remain_eligible(self):
        for mode in ("rms", "maximum"):
            item = deepcopy(self.snapshot)
            corners = item["detection"]["markers"][0]["corners"]
            if mode == "rms":
                item["detection"]["markers"][0]["corners"] = [[x+3.0, y] for x, y in corners]
            else:
                corners[0][0] += 6.0
            with self.subTest(mode=mode):
                self.assertEqual(self.derive(item)["registration"]["homography"], self.matrix)

    def test_rejects_two_markers_without_spatial_coverage(self):
        previous_data = self.previous.data
        previous_data["markers"][1]["center_mm"] = [14.0, 11.0]
        previous = MapDefinition(data=previous_data)
        current_data = previous.data
        current_data["version"] += ".route-test"
        current_data["edges"][0]["bidirectional"] = not current_data["edges"][0]["bidirectional"]
        current = MapDefinition(data=current_data)
        snapshot = deepcopy(self.snapshot)
        snapshot.update(map_hash=previous.geometry_hash)
        snapshot["detection"] = self.markers(previous, (10, 11))
        self.assert_rejected(snapshot, previous, current, "DISPLAY_REVISION_MARKERS")

    def preview(self, *, epoch=None, sequence=21, shift=0):
        def respond(_request):
            return httpx.Response(200, content=self.jpeg, headers={
                "Content-Type": "image/jpeg", "X-Camera-Id": self.snapshot["camera_id"],
                "X-Camera-Epoch": epoch or self.snapshot["epoch"], "X-Frame-Sequence": str(sequence),
                "X-Frame-Received-At": self.received_at, "X-Frame-Age-Ms": "20",
                "X-Frame-Width": "1280", "X-Frame-Height": "960",
            })
        detection = deepcopy(self.snapshot["detection"])
        if shift:
            for marker in detection["markers"]:
                marker["corners"] = [[x+shift, y] for x, y in marker["corners"]]
        preview = LiveCamera("http://127.0.0.1:8895", self.current,
                             lambda _image: deepcopy(detection), lambda *_args: None,
                             transport=httpx.MockTransport(respond))
        self.addCleanup(preview.close)
        preview.poll_once()
        return preview

    def test_derived_receipt_still_uses_standard_fresh_restore_and_cannot_reuse_old_map_receipt(self):
        derived = self.derive()
        preview = self.preview()
        with self.assertRaises(SceneError) as old:
            preview.restore_reference(self.snapshot)
        self.assertEqual(old.exception.code, "LIVE_REFERENCE_IDENTITY")
        with patch("cv2.findHomography", side_effect=AssertionError("Restore must not fit.")):
            resumed = preview.restore_reference(derived)
        self.assertEqual(resumed["registration"]["status"], "locked_partial")
        self.assertEqual(resumed["registration"]["homography"], self.matrix)
        self.assertEqual(resumed["registration"]["resumed_from"], derived["registration"]["id"])
        self.assertFalse(resumed["motion_authority"])
        self.assertEqual(resumed["detection"]["marker_ids"], [11, 12, 13])

    def test_derived_receipt_cannot_bypass_current_epoch_sequence_or_marker_checks(self):
        for parameters, code in (({"epoch": "e" * 32}, "LIVE_REFERENCE_IDENTITY"),
                                 ({"sequence": 19}, "LIVE_REFERENCE_IDENTITY"),
                                 ({"shift": 8}, "LIVE_REFERENCE_MARKERS")):
            with self.subTest(parameters=parameters):
                preview = self.preview(**parameters)
                with self.assertRaises(SceneError) as rejected:
                    preview.restore_reference(self.derive())
                self.assertEqual(rejected.exception.code, code)
                self.assertIsNone(preview._reference)


if __name__ == "__main__":
    unittest.main()
