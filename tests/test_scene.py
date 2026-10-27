"""Synthetic print geometry tests; no camera, .env or provider traffic."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.scene import MAX_IMAGE_BYTES, SceneError, SceneStore
from backend.scene_api import router


class TestMap:
    id = "synthetic-test-print"
    version = "1"

    def __init__(self, geometry_hash="test-geometry"):
        self.geometry_hash = geometry_hash
        self.data = json.loads((Path(__file__).resolve().parents[1] / "backend" / "data" / "little-town-temporary.json").read_text(encoding="utf-8"))

    def snapshot(self):
        return {**deepcopy(self.data), "id": self.id, "version": self.version, "geometry_hash": self.geometry_hash}


def print_image(missing=(), shift=(0, 0)) -> bytes:
    """Generate our own test image, not supplied map artwork or camera media."""
    image = np.full((1200, 1800, 3), 255, dtype=np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for marker in TestMap().data["markers"]:
        if marker["id"] in missing:
            continue
        side = int(marker["size_mm"] * 4)
        if hasattr(cv2.aruco, "generateImageMarker"):
            pixels = cv2.aruco.generateImageMarker(dictionary, marker["id"], side)
        else:
            pixels = cv2.aruco.drawMarker(dictionary, marker["id"], side)
        x = int((marker["center_mm"][0] - marker["size_mm"] / 2) * 4 + 100 + shift[0])
        y = int((marker["center_mm"][1] - marker["size_mm"] / 2) * 4 + 100 + shift[1])
        image[y:y + side, x:x + side] = cv2.cvtColor(pixels, cv2.COLOR_GRAY2BGR)
    success, encoded = cv2.imencode(".png", image)
    assert success
    return encoded.tobytes()


def review():
    return {"verdict": "USABLE", "summary": "The temporary print is visible; no physical car or paper signal is present.", "visible_places": [], "car_visible": False, "signal": "UNKNOWN", "limitations": ["Recorded image only; no motion authority."]}


class SceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full = print_image()
        cls.partial = print_image(missing=(10,))
        cls.moved = print_image(shift=(10, 0))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = SceneStore(self.temporary.name, TestMap())

    def lock(self):
        snapshot = self.store.ingest(self.full)
        return self.store.register(snapshot["revision"], snapshot["frame"]["id"])

    def test_full_markers_candidate_and_explicit_lock(self):
        snapshot = self.store.ingest(self.full, "2026-10-27T15:01:36+09:00", "recorded")
        self.assertEqual(snapshot["detection"]["marker_ids"], [10, 11, 12, 13])
        self.assertEqual(snapshot["registration"]["status"], "candidate")
        self.assertIsNone(snapshot["registration"]["id"])
        self.assertEqual(snapshot["frame"]["sha256"], hashlib.sha256(self.full).hexdigest())
        self.assertEqual(snapshot["frame"]["timestamp_source"], "operator_provided")
        locked = self.store.register(snapshot["revision"], snapshot["frame"]["id"])
        self.assertEqual(locked["registration"]["status"], "locked")
        self.assertIsNotNone(locked["registration"]["id"])
        self.assertFalse(locked["capabilities"]["robot"])
        self.assertFalse(locked["capabilities"]["live_camera"])

    def test_partial_does_not_register(self):
        snapshot = self.store.ingest(self.partial)
        self.assertEqual(snapshot["registration"]["status"], "partial")
        with self.assertRaises(SceneError) as raised:
            self.store.register(snapshot["revision"], snapshot["frame"]["id"])
        self.assertEqual(raised.exception.code, "REGISTRATION_MARKERS")

    def test_occlusion_retains_reference_without_refit(self):
        locked = self.lock()
        partial = self.store.ingest(self.partial)
        self.assertEqual(partial["registration"]["status"], "locked_partial")
        self.assertEqual(partial["registration"]["homography"], locked["registration"]["homography"])
        self.assertEqual(partial["registration"]["id"], locked["registration"]["id"])

    def test_moved_view_withholds_overlay_and_requires_explicit_registration(self):
        self.lock()
        moved = self.store.ingest(self.moved)
        self.assertEqual(moved["registration"]["status"], "view_changed")
        self.assertIsNone(moved["registration"]["homography"])
        registered = self.store.register(moved["revision"], moved["frame"]["id"])
        self.assertEqual(registered["registration"]["status"], "locked")

    def test_no_markers_cannot_verify_reference(self):
        self.lock()
        frame = print_image(missing=(10, 11, 12, 13))
        snapshot = self.store.ingest(frame)
        self.assertEqual(snapshot["registration"]["status"], "view_changed")
        self.assertIsNone(snapshot["registration"]["homography"])

    def test_registration_stale_revision_or_frame_rejected(self):
        old = self.store.ingest(self.full)
        current = self.store.ingest(self.full)
        with self.assertRaises(SceneError) as raised:
            self.store.register(old["revision"], old["frame"]["id"])
        self.assertEqual(raised.exception.status_code, 409)
        with self.assertRaises(SceneError) as raised:
            self.store.register(current["revision"], old["frame"]["id"])
        self.assertEqual(raised.exception.code, "FRAME_CHANGED")

    def test_snapshot_and_persisted_reference_identity(self):
        locked = self.lock()
        locked["detection"]["marker_ids"].clear()
        reopened = SceneStore(self.temporary.name, TestMap())
        self.assertEqual(reopened.snapshot()["registration"]["status"], "locked")
        self.assertEqual(reopened.snapshot()["detection"]["marker_ids"], [10, 11, 12, 13])
        changed = SceneStore(self.temporary.name, TestMap("replacement-geometry"))
        self.assertIsNone(changed.snapshot()["frame"])
        self.assertEqual(changed.snapshot()["registration"]["status"], "unregistered")

    def test_geometry_rejects_flipped_or_inconsistent_markers(self):
        snapshot = self.store.ingest(self.full)
        swapped = deepcopy(snapshot["detection"])
        swapped["markers"][0]["corners"], swapped["markers"][1]["corners"] = swapped["markers"][1]["corners"], swapped["markers"][0]["corners"]
        self.assertIsNone(self.store._candidate(swapped, 1800, 1200))
        noisy = deepcopy(snapshot["detection"])
        noisy["markers"][0]["corners"][0][0] += 40
        self.assertIsNone(self.store._candidate(noisy, 1800, 1200))

    def test_version_only_replacement_invalidates_frame_reference_and_inspection(self):
        locked = self.lock()
        async def provider(_data, _mime, _expected):
            return review()
        self.store._review_provider = provider
        inspected = asyncio.run(self.store.inspect(locked["revision"], locked["frame"]["id"], "Inspect the printed map."))
        self.assertIsNotNone(inspected["inspection"])
        replacement = TestMap()
        replacement.version = "2"
        reopened = SceneStore(self.temporary.name, replacement)
        snapshot = reopened.snapshot()
        self.assertGreater(snapshot["revision"], inspected["revision"])
        self.assertIsNone(snapshot["frame"])
        self.assertIsNone(snapshot["inspection"])
        self.assertIsNone(snapshot["registration"]["homography"])
        self.assertEqual(snapshot["registration"]["status"], "unregistered")

    def test_unsupported_oversized_and_dimension_bomb_images(self):
        for content in (b"not an image", b"GIF89a" + b"x" * 50):
            with self.assertRaises(SceneError) as raised:
                self.store.ingest(content)
            self.assertEqual(raised.exception.status_code, 415)
        with self.assertRaises(SceneError) as raised:
            self.store.ingest(b"x" * (MAX_IMAGE_BYTES + 1))
        self.assertEqual(raised.exception.status_code, 413)
        bomb = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 100000, 100000) + b"\x08\x02\x00\x00\x00" + b"\x00" * 4
        with self.assertRaises(SceneError) as raised:
            self.store.ingest(bomb)
        self.assertEqual(raised.exception.code, "IMAGE_DIMENSIONS")

    def test_capture_time_requires_explicit_timezone(self):
        with self.assertRaises(SceneError):
            self.store.ingest(self.full, "2026-10-27T15:01:36")
        snapshot = self.store.ingest(self.full)
        self.assertIsNone(snapshot["frame"]["captured_at"])
        self.assertEqual(snapshot["frame"]["timestamp_source"], "unknown")

    def test_frame_paths_are_immutable_and_bounded(self):
        first = self.store.ingest(self.full)
        self.store.ingest(self.partial)
        path, mime = self.store.frame_file(first["frame"]["id"])
        self.assertEqual(path.read_bytes(), self.full)
        self.assertEqual(mime, "image/png")
        for value in ("../scene", "a" * 33, "f" * 32):
            with self.assertRaises(SceneError) as raised:
                self.store.frame_file(value)
            self.assertEqual(raised.exception.status_code, 404)

    def test_explicit_inspection_binds_frame_and_has_no_motion_authority(self):
        calls = []
        async def fake(data, mime, expected):
            calls.append((data, mime, expected))
            return review()
        self.store._review_provider = fake
        state = self.store.ingest(self.full)
        self.assertEqual(calls, [])
        result = asyncio.run(self.store.inspect(state["revision"], state["frame"]["id"], "Check print visibility."))
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["inspection"]["source"], "meta")
        self.assertEqual(result["inspection"]["frame_id"], state["frame"]["id"])
        self.assertFalse(result["inspection"]["motion_authority"])
        self.assertEqual(result["inspection"]["signal"], "UNKNOWN")
        evidence = json.loads(next((Path(self.temporary.name) / "inspections").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(evidence["frame_sha256"], state["frame"]["sha256"])
        self.assertEqual(evidence["map_hash"], TestMap().geometry_hash)
        self.assertIsNone(self.store.ingest(self.partial)["inspection"])

    def test_late_inspection_cannot_attach_to_new_frame(self):
        async def scenario():
            started = asyncio.Event()
            resume = asyncio.Event()
            async def fake(data, mime, expected):
                started.set()
                await resume.wait()
                return review()
            self.store._review_provider = fake
            state = self.store.ingest(self.full)
            task = asyncio.create_task(self.store.inspect(state["revision"], state["frame"]["id"], "Inspect this frame."))
            await started.wait()
            self.store.ingest(self.partial)
            resume.set()
            with self.assertRaises(SceneError) as raised:
                await task
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIsNone(self.store.snapshot()["inspection"])
        asyncio.run(scenario())

    def test_provider_failure_and_invalid_schema_do_not_fallback(self):
        async def failed(data, mime, expected):
            raise RuntimeError("sensitive provider response")
        async def invalid(data, mime, expected):
            return {**review(), "robot_command": "move"}
        state = self.store.ingest(self.full)
        for provider in (failed, invalid):
            self.store._review_provider = provider
            with self.assertRaises(SceneError) as raised:
                asyncio.run(self.store.inspect(state["revision"], state["frame"]["id"], "Inspect this frame."))
            self.assertEqual(raised.exception.status_code, 502)
            self.assertNotIn("sensitive", str(raised.exception))
            self.assertIsNone(self.store.snapshot()["inspection"])

    def test_api_upload_registration_and_immutable_image(self):
        app = FastAPI()
        app.state.scene = self.store
        app.include_router(router)
        with TestClient(app) as client:
            state = client.post("/api/v1/scene/frames", files={"file": ("frame.png", self.full, "image/png")}).json()
            self.assertEqual(state["registration"]["status"], "candidate")
            response = client.get(state["frame"]["image_url"])
            self.assertEqual(response.content, self.full)
            self.assertIn("immutable", response.headers["cache-control"])
            locked = client.post("/api/v1/scene/registration", json={"expected_revision": state["revision"], "frame_id": state["frame"]["id"]})
            self.assertEqual(locked.status_code, 200)
            self.assertEqual(locked.json()["registration"]["status"], "locked")
            stale = client.post("/api/v1/scene/registration", json={"expected_revision": state["revision"], "frame_id": state["frame"]["id"]})
            self.assertEqual(stale.status_code, 409)
            self.assertEqual(stale.json()["detail"]["code"], "STALE_SCENE")
            invalid = client.post("/api/v1/scene/frames", files={"file": ("frame.gif", b"GIF89a", "image/gif")})
            self.assertEqual(invalid.status_code, 415)

    def test_meta_http_payload_and_private_key_boundary(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(review())}}]})
        self.store._api_key = "synthetic-test-credential"
        original_client = httpx.AsyncClient
        client = original_client(transport=httpx.MockTransport(handler), follow_redirects=False)
        state = self.store.ingest(self.full)
        with patch("backend.scene.httpx.AsyncClient", return_value=client):
            result = asyncio.run(self.store.inspect(state["revision"], state["frame"]["id"], "Check car presence."))
        self.assertEqual(str(requests[0].url), "https://api.meta.ai/v1/chat/completions")
        self.assertEqual(requests[0].headers["authorization"], "Bearer synthetic-test-credential")
        payload = json.loads(requests[0].content)
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        self.assertIn("data:image/png;base64,", payload["messages"][1]["content"][1]["image_url"]["url"])
        self.assertIn("Tiny printed traffic-light illustrations", payload["messages"][0]["content"])
        self.assertNotIn("synthetic-test-credential", json.dumps(result))
        self.assertFalse(result["inspection"]["motion_authority"])

    def test_meta_redirect_and_provider_errors_are_sanitized(self):
        self.store._api_key = "synthetic-test-credential"
        state = self.store.ingest(self.full)
        original_client = httpx.AsyncClient
        for status in (302, 401, 429, 503):
            requests = []
            def handler(request):
                requests.append(request)
                return httpx.Response(status, headers={"location": "https://untrusted.invalid/collect"}, text="sensitive provider diagnostic")
            client = original_client(transport=httpx.MockTransport(handler), follow_redirects=False)
            with patch("backend.scene.httpx.AsyncClient", return_value=client):
                with self.assertRaises(SceneError) as raised:
                    asyncio.run(self.store.inspect(state["revision"], state["frame"]["id"], "Check print visibility."))
            self.assertEqual(len(requests), 1)
            self.assertEqual(raised.exception.status_code, 502)
            self.assertNotIn("sensitive", str(raised.exception))
            self.assertIsNone(self.store.snapshot()["inspection"])

    def test_meta_invalid_structured_response_is_not_accepted(self):
        self.store._api_key = "synthetic-test-credential"
        state = self.store.ingest(self.full)
        original_client = httpx.AsyncClient
        responses = [
            {"choices": [{"message": {"content": "not json"}}]},
            {"choices": [{"message": {"content": json.dumps({**review(), "signal": "CLEAR"})}}]},
            {"choices": [{"message": {"content": json.dumps(review()), "refusal": "Cannot inspect"}}]},
        ]
        for value in responses:
            client = original_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=value)))
            with patch("backend.scene.httpx.AsyncClient", return_value=client):
                with self.assertRaises(SceneError):
                    asyncio.run(self.store.inspect(state["revision"], state["frame"]["id"], "Check print visibility."))
            self.assertIsNone(self.store.snapshot()["inspection"])


if __name__ == "__main__":
    unittest.main()
