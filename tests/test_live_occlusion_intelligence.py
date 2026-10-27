"""MUSE commit guards use real registration checks with generated frames only."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from backend.core import WorkspaceStore
from backend.live_camera import LiveCamera
from backend.live_intelligence import LiveIntelligenceService
from tests import test_live_intelligence as fixtures


class GeneratedLockedCamera(LiveCamera):
    """Feed native synthetic JPEGs to LiveCamera without a poller or HTTP client.

    Only marker observations are controlled by the fixture. Registration,
    coverage, capture eligibility and check_binding use the production methods.
    """

    matrix = [[0.5, 0.0, 64.0], [0.0, 0.5, 48.0], [0.0, 0.0, 1.0]]

    def __init__(self, definition):
        super().__init__("http://127.0.0.1:8895", definition, None, self.candidate)
        self.sequence = 0
        self.missing = ()
        self.marker_shifts = {}
        self._detect = lambda _, **_kwargs: self.markers()
        initial = self.emit()
        self.register(initial["epoch"], initial["frame"]["id"])

    def markers(self):
        known = self._known_corners()
        matrix = np.array(self.matrix, dtype=np.float64)
        markers = [{"id": identifier, "corners": (cv2.perspectiveTransform(
            points.reshape(-1, 1, 2), matrix).reshape(4, 2)
            + self.marker_shifts.get(identifier, (0, 0))).tolist()}
            for identifier, points in known.items() if identifier not in self.missing]
        return {"marker_ids": [marker["id"] for marker in markers], "markers": markers}

    def candidate(self, detection, _width, _height):
        if set(detection["marker_ids"]) != set(self._known_corners()):
            return None
        known = self._known_corners()
        board = np.concatenate([known[marker["id"]] for marker in detection["markers"]])
        pixels = np.concatenate([np.array(marker["corners"], dtype=np.float64)
                                 for marker in detection["markers"]])
        matrix, _ = cv2.findHomography(board, pixels, method=0)
        if matrix is None:
            return None
        projected = cv2.perspectiveTransform(board.reshape(-1, 1, 2), matrix).reshape(-1, 2)
        distances = np.linalg.norm(projected - pixels, axis=1)
        residual = float(np.sqrt(np.mean(distances ** 2)))
        if residual > 3.0 or float(np.max(distances)) > 6.0:
            return None
        return {"homography": matrix.tolist(), "residual_px": round(residual, 4)}

    def emit(self):
        self.sequence += 1
        image = np.full((240, 320, 3), 220, dtype=np.uint8)
        # A generated opaque patch makes this a synthetic occlusion fixture,
        # never a real camera observation or model-accuracy measurement.
        if self.missing:
            cv2.rectangle(image, (0, 0), (319, 45), (35, 35, 35), -1)
        cv2.rectangle(image, (self.sequence % 40 + 1, 200),
                      (self.sequence % 40 + 14, 214), (30, 60, 170), -1)
        success, encoded = cv2.imencode(".jpg", image)
        assert success
        self._accept(encoded.tobytes(), {
            "X-Camera-Epoch": "a" * 32, "X-Camera-Id": "generated-occlusion-fixture",
            "X-Frame-Sequence": str(self.sequence), "X-Frame-Age-Ms": "0",
            "X-Frame-Received-At": datetime.now(timezone.utc).isoformat(),
            "X-Frame-Width": "320", "X-Frame-Height": "240",
        })
        return self.snapshot()

    def capture(self, *, after_sequence=None, not_before=None):
        self.emit()
        return super().capture(after_sequence=after_sequence, not_before=not_before)

    def obscure(self, missing=(10, 11, 12)):
        self.missing = missing
        return self.emit()

    def disagree(self, identifiers=(10, 11), *, checks=1):
        self.missing = ()
        self.marker_shifts = {identifier: (12.0, 0.0) for identifier in identifiers}
        for _ in range(checks):
            result = self.emit()
        return result


class LiveOcclusionIntelligenceTests(unittest.IsolatedAsyncioTestCase):
    # Reuse setup actions without inheriting and rerunning another test class.
    payload = fixtures.LiveIntelligenceTests.payload
    command = fixtures.LiveIntelligenceTests.command
    plan = fixtures.LiveIntelligenceTests.plan
    ready = fixtures.LiveIntelligenceTests.ready
    review = fixtures.LiveIntelligenceTests.review
    stopped = fixtures.LiveIntelligenceTests.stopped

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = WorkspaceStore(str(Path(directory.name) / "workspace.sqlite3"),
                                    provider=fixtures.NeverTextProvider(), map_definition=fixtures.test_map())
        self.addCleanup(self.store.close)
        self.camera = GeneratedLockedCamera(self.store.map_definition)
        self.addCleanup(self.camera.close)
        self.initial_view = self.camera.snapshot()
        self.planner, self.reviewer = fixtures.FakePlanner(), fixtures.FakeReviewer()
        self.service = LiveIntelligenceService(self.store, self.camera,
            planning_provider=self.planner, review_provider=self.reviewer)

    def assert_fixed_view(self, expected_status, verification=None):
        current = self.camera.snapshot()
        self.assertEqual(current["registration"]["status"], expected_status)
        if verification:
            self.assertEqual(current["registration"]["verification"], verification)
        for key in ("epoch", "camera_id", "map_id", "map_version", "map_hash"):
            self.assertEqual(current[key], self.initial_view[key], key)
        for key in ("id", "reference_frame_id", "homography"):
            self.assertEqual(current["registration"][key], self.initial_view["registration"][key], key)
        self.assertIsNone(self.camera._client, "The synthetic fixture must never open a network client.")
        self.assertFalse(current["motion_authority"])

    async def test_one_remaining_marker_during_planning_retains_eligible_fixed_reference(self):
        self.planner.callback = self.camera.obscure
        payload = self.payload(text="School using the west road.")
        response, status = await self.service.plan(payload)
        self.assertEqual(status, 200, response)
        state = self.store.snapshot()
        self.assertEqual(state["state"], "PLAN_READY")
        self.assertEqual(state["plan"]["route"]["node_ids"], fixtures.WEST_ROUTE)
        self.assertFalse(state["approved"])
        self.assertNotIn("planning_pending", state)
        self.assertEqual(len(self.planner.calls), 1, "Occlusion occurs after dispatch, not before capture.")
        self.assert_fixed_view("locked_occluded", "insufficient_visibility")
        self.assertEqual(await self.service.plan(payload), (response, status))
        self.assertEqual(len(self.planner.calls), 1, "An accepted request cannot resend inference.")

    async def test_total_marker_cover_before_planning_sends_unverified_native_frame(self):
        self.camera.obscure((10, 11, 12, 13))
        result = await self.plan()
        self.assertEqual(result["state"], "PLAN_READY")
        metadata = self.planner.calls[0]["context"]["frame"]
        self.assertEqual(metadata["registration"]["verification"], "insufficient_visibility")
        self.assertEqual(metadata["registration"]["homography"], self.initial_view["registration"]["homography"])
        self.assertEqual(self.service.frame(result["plan"]["planning"]["frame"]["id"]),
                         self.planner.calls[0]["image"])
        self.assert_fixed_view("locked_occluded", "insufficient_visibility")

    async def test_total_marker_cover_during_action_review_accepts_model_supported_pass(self):
        await self.ready()
        self.service.advance(self.payload())
        before = self.store.snapshot()
        self.camera.obscure((10, 11, 12, 13))

        async def obscure():
            self.camera.obscure((10, 11, 12, 13))

        self.reviewer.action_callback = obscure
        response, status = await self.service.review_action(self.payload(
            review_id=before["review"]["id"], expected_visual="Check the generated placement fixture."))
        self.assertEqual(status, 200, response)
        self.assertEqual(len(self.reviewer.action_calls), 1)
        current = self.store.snapshot()
        self.assertEqual(current["state"], "READY")
        self.assertEqual(current["review"]["verdict"], "PASS")
        self.assertEqual(current["plan"]["id"], before["plan"]["id"])
        self.assertEqual(self.reviewer.action_calls[0]["after"]["metadata"]["registration"]["verification"],
                         "insufficient_visibility")
        self.assert_fixed_view("locked_occluded", "insufficient_visibility")

    async def test_marker_cover_during_valid_green_judgment_does_not_block_crossing(self):
        before = await self.stopped()
        self.reviewer.signal_output = fixtures.signal_result("GREEN")
        self.camera.obscure()

        async def obscure():
            self.camera.obscure()

        self.reviewer.signal_callback = obscure
        response, status = await self.service.review_signal(self.payload())
        self.assertEqual(status, 200, response)
        self.assertEqual(len(self.reviewer.signal_calls), 1)
        current = self.store.snapshot()
        self.assertEqual(current["state"], "REVIEW_REQUIRED")
        self.assertEqual(current["plan"]["steps"][current["current_step"]]["kind"], "CROSS")
        self.assertEqual(current["stop_receipt"], before["stop_receipt"])
        self.assertEqual(len([event for event in current["events"] if event["kind"] == "CROSSING_ADMITTED"]), 1)
        self.assert_fixed_view("locked_occluded", "insufficient_visibility")

    async def test_vehicle_reobserve_still_holds_when_markers_are_covered(self):
        await self.ready()
        self.service.advance(self.payload())
        before = self.store.snapshot()
        self.camera.obscure((10, 11, 12, 13))
        self.reviewer.action_output = fixtures.action_result("REOBSERVE")
        result = await self.review()
        self.assertEqual(result["state"], "REOBSERVE")
        self.assertEqual(result["current_step"], before["current_step"])
        self.assertEqual(result["review"]["verdict"], "REOBSERVE")
        self.assert_fixed_view("locked_occluded", "insufficient_visibility")

    async def test_unknown_signal_still_keeps_same_stop_when_markers_are_covered(self):
        before = await self.stopped()
        self.camera.obscure((10, 11, 12, 13))
        self.reviewer.signal_output = fixtures.signal_result("UNKNOWN")
        result, status = await self.service.review_signal(self.payload())
        self.assertEqual(status, 200, result)
        self.assertEqual(result["state"], "WAITING_SIGNAL")
        self.assertTrue(result["stopped"])
        self.assertEqual(result["signal"]["color"], "UNKNOWN")
        self.assertEqual(result["stop_receipt"], before["stop_receipt"])
        self.assertFalse(any(event["kind"] == "CROSSING_ADMITTED" for event in result["events"]))
        self.assert_fixed_view("locked_occluded", "insufficient_visibility")

    async def test_visible_marker_disagreement_during_planning_rejects_result(self):
        self.planner.callback = self.camera.disagree
        response, status = await self.service.plan(self.payload(text="School using the west road."))
        self.assertEqual(status, 409, response)
        self.assertEqual(len(self.planner.calls), 1)
        self.assertIsNone(self.store.snapshot()["plan"])
        self.assertFalse(self.store.snapshot()["approved"])
        self.assert_fixed_view("locked_occluded", "marker_disagreement")

    async def test_isolated_noisy_marker_during_planning_keeps_distributed_healthy_support(self):
        self.planner.callback = lambda: self.camera.disagree((10,))
        result = await self.plan()
        self.assertEqual(result["state"], "PLAN_READY")
        self.assertEqual(result["plan"]["route"]["node_ids"], fixtures.WEST_ROUTE)
        self.assertFalse(result["approved"])
        self.assert_fixed_view("locked_partial", "visible_markers")

    async def test_visible_marker_disagreement_during_action_review_rejects_pass(self):
        await self.ready()
        self.service.advance(self.payload())
        before = self.store.snapshot()

        async def disagree():
            self.camera.disagree()

        self.reviewer.action_callback = disagree
        response, status = await self.service.review_action(self.payload(
            review_id=before["review"]["id"], expected_visual="Check the generated placement fixture."))
        self.assertEqual(status, 409, response)
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(self.store.snapshot()["review"]["verdict"], "PENDING")
        self.assert_fixed_view("locked_occluded", "marker_disagreement")

    async def test_visible_marker_disagreement_during_green_keeps_stop(self):
        before = await self.stopped()
        self.reviewer.signal_output = fixtures.signal_result("GREEN")

        async def disagree():
            self.camera.disagree()

        self.reviewer.signal_callback = disagree
        response, status = await self.service.review_signal(self.payload())
        self.assertEqual(status, 409, response)
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(self.store.snapshot()["state"], "WAITING_SIGNAL")
        self.assert_fixed_view("locked_occluded", "marker_disagreement")

    async def test_confirmed_view_change_during_planning_remains_latched_after_cover(self):
        self.planner.callback = lambda: self.camera.disagree((10, 11, 12, 13), checks=3)
        response, status = await self.service.plan(self.payload(text="School using the west road."))
        self.assertEqual(status, 409, response)
        self.assertIsNone(self.store.snapshot()["plan"])
        self.camera.obscure((10, 11, 12, 13))
        current = self.camera.snapshot()
        self.assertEqual(current["registration"]["status"], "view_changed")
        self.assertIsNone(current["registration"]["homography"])
        self.assertEqual(current["registration"]["id"], self.initial_view["registration"]["id"])
        self.assertEqual(self.camera._reference["homography"], self.initial_view["registration"]["homography"])

    async def test_two_distributed_markers_during_planning_preserve_eligible_fixed_view(self):
        self.planner.callback = lambda: self.camera.obscure((10, 12))
        result = await self.plan()
        self.assertEqual(result["state"], "PLAN_READY")
        self.assertEqual(result["plan"]["route"]["node_ids"], fixtures.WEST_ROUTE)
        self.assertFalse(result["approved"])
        self.assert_fixed_view("locked_partial", "visible_markers")
        self.camera.obscure(())
        self.assert_fixed_view("locked", "visible_markers")
