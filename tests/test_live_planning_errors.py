"""Camera admission failures stay actionable through the actual goal HTTP route.

Generated fixtures only: no camera helper, provider network or robot is contacted.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.scene import SceneError
from tests import test_live_backend_api as api_fixtures


class LivePlanningErrorTests(unittest.TestCase):
    setUp = api_fixtures.LiveBackendApiTests.setUp
    state = api_fixtures.LiveBackendApiTests.state
    command = api_fixtures.LiveBackendApiTests.command
    plan = api_fixtures.LiveBackendApiTests.plan

    def test_registration_block_rejects_before_muse_and_preserves_detail_event_and_receipt(self):
        self.plan()
        provider_calls = len(self.planner.calls)
        cases = (
            ("LIVE_CAPTURE_REGISTRATION", "A fixed drawing reference without contradictory view evidence is required; no automatic refit was performed."),
            ("LIVE_CAPTURE_UNAVAILABLE", "A fresh native camera frame is required."),
        )
        for code, message in cases:
            with self.subTest(code=code):
                payload = {"request_id": str(uuid4()), "expected_revision": self.state()["revision"],
                           "provider": "meta", "text": "Go to School."}
                with patch.object(self.camera, "capture", side_effect=SceneError(409, message, code)) as capture:
                    response = self.client.post("/api/v1/goals", json=payload)
                    self.assertEqual(response.status_code, 409, response.text)
                    self.assertEqual(response.json(), {"detail": {"code": code, "message": message}})
                    repeated = self.client.post("/api/v1/goals", json=payload)
                    self.assertEqual(repeated.status_code, 409)
                    self.assertEqual(repeated.json(), response.json())
                    self.assertEqual(capture.call_count, 1)
                self.assertEqual(len(self.planner.calls), provider_calls)
                self.assertEqual(self.text_provider.calls, [])
                state = self.state()
                self.assertEqual(state["state"], "IDLE")
                self.assertIsNone(state["plan"])
                self.assertFalse(state["approved"])
                self.assertFalse(state["capabilities"]["robot"])
                self.assertNotIn("planning_pending", state)
                self.assertEqual(state["events"][-1]["kind"], "LIVE_PLANNING_FAILED")
                self.assertEqual(state["events"][-1]["detail"], f"{code}: {message}")

    def test_view_change_after_inference_preserves_binding_failure_without_accepting_plan(self):
        message = "The camera or registered map changed while MUSE was working."
        with patch.object(self.camera, "check_binding", side_effect=SceneError(409, message, "LIVE_CAPTURE_CHANGED")):
            response = self.plan(status=409)
        self.assertEqual(response, {"detail": {"code": "LIVE_CAPTURE_CHANGED", "message": message}})
        self.assertEqual(len(self.planner.calls), 1)
        self.assertEqual(self.text_provider.calls, [])
        self.assertIsNone(self.state()["plan"])
        self.assertFalse(self.state()["approved"])

    def test_workspace_revision_conflict_remains_distinct_and_does_no_camera_or_provider_work(self):
        state = self.state()
        response = self.client.post("/api/v1/goals", json={"request_id": str(uuid4()),
            "expected_revision": state["revision"] + 1, "provider": "meta", "text": "Go to School."})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "Workspace changed. Refresh state before submitting this command."})
        self.assertEqual(self.camera.calls, [])
        self.assertEqual(self.planner.calls, [])
        self.assertEqual(self.text_provider.calls, [])
        self.assertEqual(self.state()["revision"], state["revision"])


if __name__ == "__main__":
    unittest.main()
