"""Ephemeral preview contracts with synthetic JPEGs and in-process HTTP only."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.live_camera import LiveCamera, camera_url
from backend.maps import MapDefinition
from backend.scene import SceneError, SceneStore
from backend.settings import Settings


class LiveCameraTests(unittest.TestCase):
    def setUp(self):
        self.map = MapDefinition()
        self.now = [100.0]
        self.sequence = 1
        self.epoch = "a" * 32
        self.camera_id = "synthetic-preview"
        self.status = 200
        self.headers_override = {}
        self.detection = self.markers()
        success, encoded = cv2.imencode(".jpg", np.full((96, 128, 3), 220, np.uint8))
        assert success
        self.jpeg = encoded.tobytes()
        self.preview = LiveCamera("http://127.0.0.1:8895", self.map,
                                  lambda _: deepcopy(self.detection), self.candidate,
                                  transport=httpx.MockTransport(self.respond), clock=lambda: self.now[0])
        self.addCleanup(self.preview.close)

    def markers(self, missing=(), shift=(0, 0)):
        items = []
        for marker in self.map.data["markers"]:
            if marker["id"] in missing:
                continue
            x, y = marker["center_mm"]
            half = marker["size_mm"] / 2
            items.append({"id": marker["id"], "corners": [
                [x-half+shift[0], y-half+shift[1]], [x+half+shift[0], y-half+shift[1]],
                [x+half+shift[0], y+half+shift[1]], [x-half+shift[0], y+half+shift[1]]]})
        return {"marker_ids": [item["id"] for item in items], "markers": items}

    def candidate(self, detection, _width, _height):
        if len(detection["markers"]) != 4:
            return None
        marker = self.map.data["markers"][0]
        observed = detection["markers"][0]["corners"][0]
        dx = observed[0] - marker["center_mm"][0] + marker["size_mm"] / 2
        dy = observed[1] - marker["center_mm"][1] + marker["size_mm"] / 2
        return {"homography": [[1, 0, dx], [0, 1, dy], [0, 0, 1]], "residual_px": 0.0}

    def respond(self, request):
        self.assertEqual(str(request.url), "http://127.0.0.1:8895/frame.jpg")
        return httpx.Response(self.status, content=self.jpeg, headers={
            "Content-Type": "image/jpeg", "X-Camera-Id": self.camera_id,
            "X-Camera-Epoch": self.epoch, "X-Frame-Sequence": str(self.sequence),
            "X-Frame-Received-At": datetime.now(timezone.utc).isoformat(),
            "X-Frame-Age-Ms": "20", "X-Frame-Width": "128", "X-Frame-Height": "96",
            **self.headers_override,
        })

    def poll(self, **kwargs):
        self.sequence += 1
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.preview.poll_once()
        return self.preview.snapshot()

    def lock(self):
        state = self.poll()
        return self.preview.register(state["epoch"], state["frame"]["id"])

    def test_url_is_numeric_loopback_only_without_redirect_target_input(self):
        self.assertEqual(camera_url("http://127.0.0.1:8895/"), "http://127.0.0.1:8895")
        self.assertEqual(camera_url("http://[::1]:8084"), "http://[::1]:8084")
        for value in ("http://192.0.2.20:8084", "https://127.0.0.1:8084", "http://localhost:8084",
                      "http://127.0.0.1:8084/path", "http://user@127.0.0.1:8084", "http://127.0.0.1",
                      "http://127.0.0.1:8084?url=x", "http://127.0.0.1:8084#fragment"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                camera_url(value)

    def test_disabled_default_does_not_create_client(self):
        preview = LiveCamera("", self.map, None, None)
        preview.start()
        self.assertIsNone(preview._client)
        self.assertFalse(preview.snapshot()["enabled"])
        self.assertFalse(preview.snapshot()["motion_authority"])

    def test_native_bytes_frame_identity_cache_and_no_disk_writes(self):
        state = self.poll()
        frame = state["frame"]
        self.assertEqual(state["state"], "live")
        self.assertEqual(state["registration"]["status"], "candidate")
        self.assertEqual(frame["sha256"], hashlib.sha256(self.jpeg).hexdigest())
        self.assertEqual(self.preview.image(frame["id"]), self.jpeg)
        for _ in range(8):
            self.poll()
        self.assertEqual(len(self.preview._frames), 8)
        with self.assertRaises(SceneError) as error:
            self.preview.image(frame["id"])
        self.assertEqual(error.exception.code, "LIVE_FRAME_EXPIRED")

    def test_repeated_sequence_cannot_refresh_age_and_failure_becomes_stale(self):
        first = self.poll()
        self.now[0] += 1
        self.preview.poll_once()
        self.assertEqual(self.preview.snapshot()["frame"]["id"], first["frame"]["id"])
        self.assertGreaterEqual(self.preview.snapshot()["frame"]["age_ms"], 1020)
        self.now[0] += 1
        stale = self.poll(status=503)
        self.assertEqual(stale["state"], "stale")
        self.assertIsNotNone(stale["last_error"])
        self.assertEqual(stale["frame"]["id"], first["frame"]["id"])

    def test_redirect_and_malformed_headers_do_not_accept_frame(self):
        self.assertEqual(self.poll(status=302)["state"], "unavailable")
        self.status = 200
        for change in ({"X-Camera-Epoch": "bad"}, {"X-Frame-Age-Ms": "nan"},
                       {"X-Frame-Width": "1920"}, {"X-Frame-Received-At": "2026-10-27T12:00:00"},
                       {"X-Frame-Age-Ms": "2000"}):
            self.assertIsNone(self.poll(headers_override=change)["frame"])

    def test_camera_identity_length_matches_native_service_boundary(self):
        accepted = self.poll(camera_id="c"*160)
        self.assertEqual(accepted["state"], "live")
        self.assertEqual(accepted["camera_id"], "c"*160)
        rejected = self.poll(camera_id="c"*161)
        self.assertEqual(rejected["frame"]["id"], accepted["frame"]["id"])
        self.assertIsNotNone(rejected["last_error"])

    def test_lock_partial_and_total_occlusion_preserve_same_transform(self):
        locked = self.lock()
        matrix = locked["registration"]["homography"]
        partial = self.poll(detection=self.markers(missing=(10,)))
        self.assertEqual(partial["registration"]["status"], "locked_partial")
        hidden = self.poll(detection=self.markers(missing=(10, 11, 12, 13)))
        self.assertEqual(hidden["registration"]["status"], "locked_occluded")
        self.assertEqual(hidden["registration"]["homography"], matrix)
        restored = self.poll(detection=self.markers())
        self.assertEqual(restored["registration"]["status"], "locked")
        self.assertEqual(restored["registration"]["id"], locked["registration"]["id"])

    def test_one_doubtful_marker_does_not_confirm_camera_movement(self):
        self.lock()
        detection = self.markers()
        detection["markers"][0]["corners"] = [[x+25, y] for x, y in detection["markers"][0]["corners"]]
        state = self.poll(detection=detection)
        self.assertEqual(state["registration"]["status"], "locked_occluded")
        self.assertIsNotNone(state["registration"]["homography"])

    def test_confirmed_view_change_latches_without_automatic_refit(self):
        original = self.lock()
        moved = self.poll(detection=self.markers(shift=(12, 0)))
        self.assertEqual(moved["registration"]["status"], "locked_occluded")
        self.poll()
        moved = self.poll()
        self.assertEqual(moved["registration"]["status"], "view_changed")
        self.assertIsNone(moved["registration"]["homography"])
        hidden = self.poll(detection=self.markers(missing=(10, 11, 12, 13)))
        self.assertEqual(hidden["registration"]["status"], "view_changed")
        current = self.poll(detection=self.markers(shift=(12, 0)))
        locked = self.preview.register(current["epoch"], current["frame"]["id"])
        self.assertNotEqual(locked["registration"]["homography"], original["registration"]["homography"])
        self.assertEqual(locked["registration"]["status"], "locked")

    def test_epoch_camera_and_map_changes_withhold_overlay(self):
        for key, value in (("epoch", "b"*32), ("camera_id", "another-camera")):
            self.lock()
            state = self.poll(**{key: value})
            self.assertEqual(state["registration"]["status"], "view_changed")
        self.lock()
        self.map.geometry_hash = "changed-map"
        self.assertEqual(self.preview.snapshot()["registration"]["status"], "view_changed")

    def test_registration_accepts_fresh_cached_click_only_while_latest_view_matches(self):
        chosen = self.poll()
        self.poll()
        self.assertEqual(self.preview.register(chosen["epoch"], chosen["frame"]["id"])["registration"]["status"], "locked")
        self.poll(detection=self.markers(shift=(12, 0)))
        with self.assertRaises(SceneError):
            self.preview.register(chosen["epoch"], chosen["frame"]["id"])
        self.now[0] += 2
        current = self.preview.snapshot()
        with self.assertRaises(SceneError):
            self.preview.register(current["epoch"], current["frame"]["id"])

    def test_api_does_not_mutate_recorded_scene_or_mission(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(db_path=str(Path(directory)/"workspace.sqlite3"))
            with TestClient(create_app(settings, live_camera_url="")) as client:
                app = client.app
                scene = client.get("/api/v1/scene").json()
                mission = client.get("/api/v1/state").json()
                app.state.live_camera = self.preview
                app.state.display_registration.camera = self.preview
                app.state.live_intelligence.camera = self.preview
                frame = self.poll()["frame"]
                response = client.get(frame["image_url"])
                self.assertEqual(response.content, self.jpeg)
                self.assertEqual(response.headers["cache-control"], "private, max-age=30, immutable")
                response = client.post("/api/v1/live-camera/registration", json={"epoch": self.epoch, "frame_id": frame["id"]})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(client.get("/api/v1/scene").json(), scene)
                self.assertEqual(client.get("/api/v1/state").json(), mission)
                self.assertTrue(client.get("/api/health").json()["camera_preview_connected"])
                self.assertFalse(client.get("/api/health").json()["robot_connected"])
                self.assertEqual(client.get("/api/v1/live-camera").headers["cache-control"], "no-store")
                bad = client.post("/api/v1/live-camera/registration", json={"epoch": self.epoch, "frame_id": frame["id"], "url": "http://example.com"})
                self.assertEqual(bad.status_code, 422)

    def test_reused_scene_helpers_detect_real_synthetic_jpeg_without_recorded_ingest(self):
        with tempfile.TemporaryDirectory() as directory:
            scene = SceneStore(directory, self.map)
            original = scene.snapshot()
            image = np.full((1200, 1800, 3), 255, dtype=np.uint8)
            dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            for marker in self.map.data["markers"]:
                side = int(marker["size_mm"] * 4)
                pixels = cv2.aruco.generateImageMarker(dictionary, marker["id"], side)
                x = int((marker["center_mm"][0]-marker["size_mm"]/2)*4+100)
                y = int((marker["center_mm"][1]-marker["size_mm"]/2)*4+100)
                image[y:y+side, x:x+side] = cv2.cvtColor(pixels, cv2.COLOR_GRAY2BGR)
            success, encoded = cv2.imencode(".jpg", image)
            self.assertTrue(success)
            self.jpeg = encoded.tobytes()
            self.headers_override = {"X-Frame-Width": "1800", "X-Frame-Height": "1200"}
            self.preview._detect, self.preview._candidate = scene._detect, scene._candidate
            state = self.poll()
            self.assertEqual(state["detection"]["marker_ids"], [10, 11, 12, 13])
            self.assertEqual(state["registration"]["status"], "candidate")
            self.assertEqual(scene.snapshot(), original)
            self.assertFalse((Path(directory)/"scene.json").exists())
