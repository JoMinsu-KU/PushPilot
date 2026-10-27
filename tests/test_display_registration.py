"""Server-held display-reference continuity; synthetic frames, no device access."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core import WorkspaceStore
from backend.display_registration import DisplayRegistrationService
from backend.live_camera import LiveCamera
from backend.scene import SceneError
from backend.settings import Settings
import test_live_camera as camera_fixtures


class NoProvider:
    def interpret(self, _text):
        raise AssertionError("Display registration must not call a provider.")


class DisplayRegistrationTests(unittest.TestCase):
    def setUp(self):
        # Reuse fixture helpers by composition; do not rediscover its test methods.
        self.fixture = camera_fixtures.LiveCameraTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = WorkspaceStore(":memory:", provider=NoProvider(), map_definition=self.fixture.map)
        self.addCleanup(self.store.close)
        self.registration = DisplayRegistrationService(self.store, self.fixture.preview)

    def restart_preview(self, missing=(10,)):
        self.fixture.preview.close()
        self.fixture.preview = LiveCamera("http://127.0.0.1:8895", self.fixture.map,
            lambda _image: deepcopy(self.fixture.detection), self.fixture.candidate,
            transport=httpx.MockTransport(self.fixture.respond), clock=lambda: self.fixture.now[0])
        self.addCleanup(self.fixture.preview.close)
        self.registration = DisplayRegistrationService(self.store, self.fixture.preview)
        return self.fixture.poll(detection=self.fixture.markers(missing=missing))

    def register(self):
        current = self.fixture.poll()
        return self.registration.register(current["epoch"], current["frame"]["id"])

    def test_server_receipt_survives_ram_restart_and_partial_resume_reuses_exact_transform(self):
        mission = self.store.snapshot()
        locked = self.register()
        row = self.store._db.execute("SELECT value FROM display_reference_receipts").fetchone()
        saved = json.loads(row["value"])
        self.assertEqual(saved, locked)
        partial = self.restart_preview(missing=(10,))
        self.assertEqual(partial["registration"]["status"], "unregistered")
        self.assertTrue(self.registration.available())
        with patch.object(self.fixture.preview, "_candidate", side_effect=AssertionError("Resume must not refit a candidate.")), \
                patch("backend.live_camera.cv2.findHomography", side_effect=AssertionError("Resume must not fit a transform.")):
            resumed = self.registration.resume(self.fixture.epoch)
        self.assertEqual(resumed["registration"]["status"], "locked_partial")
        self.assertEqual(resumed["registration"]["homography"], locked["registration"]["homography"])
        self.assertNotEqual(resumed["registration"]["id"], locked["registration"]["id"])
        self.assertEqual(self.store.snapshot(), mission)
        self.assertEqual(self.registration.resume(self.fixture.epoch), resumed)
        self.assertFalse(resumed["motion_authority"])

    def test_missing_or_wrong_epoch_receipts_fail_closed(self):
        self.fixture.poll()
        self.assertFalse(self.registration.available())
        with self.assertRaises(SceneError) as missing:
            self.registration.resume(self.fixture.epoch)
        self.assertEqual(missing.exception.code, "LIVE_REFERENCE_MISSING")
        self.register()
        self.restart_preview(missing=(10,))
        with self.assertRaises(SceneError) as wrong:
            self.registration.resume("b" * 32)
        self.assertEqual(wrong.exception.code, "LIVE_REFERENCE_CHANGED")
        self.assertIsNone(self.fixture.preview._reference)
        self.fixture.poll(epoch="b" * 32)
        self.assertFalse(self.registration.available())
        with self.assertRaises(SceneError):
            self.registration.resume("b" * 32)
        self.assertIsNone(self.fixture.preview._reference)

    def test_api_rejects_client_homography_and_reports_matching_epoch_receipt(self):
        settings = Settings(db_path=":memory:")
        with TestClient(create_app(settings, live_camera_url="")) as client:
            app = client.app
            app.state.live_camera = self.fixture.preview
            app.state.display_registration.camera = self.fixture.preview
            app.state.live_intelligence.camera = self.fixture.preview
            mission = client.get("/api/v1/state").json()
            frame = self.fixture.poll()["frame"]
            self.assertFalse(client.get("/api/v1/live-camera").json()["saved_reference_available"])
            lock_payload = {"epoch": self.fixture.epoch, "frame_id": frame["id"]}
            malicious = {**lock_payload, "homography": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
            self.assertEqual(client.post("/api/v1/live-camera/registration", json=malicious).status_code, 422)
            locked = client.post("/api/v1/live-camera/registration", json=lock_payload)
            self.assertEqual(locked.status_code, 200)
            self.assertTrue(client.get("/api/v1/live-camera").json()["saved_reference_available"])
            self.assertEqual(client.post("/api/v1/live-camera/registration/resume", json={
                "epoch": self.fixture.epoch, "homography": malicious["homography"],
            }).status_code, 422)
            self.restart_preview(missing=(10,))
            app.state.live_camera = self.fixture.preview
            app.state.display_registration.camera = self.fixture.preview
            app.state.live_intelligence.camera = self.fixture.preview
            resumed = client.post("/api/v1/live-camera/registration/resume", json={"epoch": self.fixture.epoch})
            self.assertEqual(resumed.status_code, 200)
            self.assertEqual(resumed.json()["registration"]["homography"], locked.json()["registration"]["homography"])
            self.assertEqual(client.get("/api/v1/state").json(), mission)
            self.fixture.poll(epoch="c" * 32)
            self.assertFalse(client.get("/api/v1/live-camera").json()["saved_reference_available"])


if __name__ == "__main__":
    unittest.main()
