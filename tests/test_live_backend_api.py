"""Root ASGI wiring for native-image planning, voice receipts and live reviews.

All images, audio and provider outputs are synthetic fixtures. No microphone,
camera helper, upstream provider or robot is contacted by these tests.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.meta import ProviderError
from backend.settings import Settings
from tests.test_live_intelligence import (FakeCamera, FakePlanner, FakeReviewer,
    WEST_ROUTE, action_result, signal_result, test_map)
from tests.test_voice import StubVoice, wav


class ApiCamera(FakeCamera):
    def __init__(self, url, definition, *_helpers):
        super().__init__(definition)
        self.url = url
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def close(self):
        self.closed = True

    def snapshot(self):
        return {"state": "live" if self.available else "unavailable", "enabled": bool(self.url),
                "camera_id": self.camera_id, "epoch": self.epoch, "motion_authority": False}


class TextProvider:
    def __init__(self):
        self.calls = []

    def interpret(self, text):
        self.calls.append(text)
        return {"destination": "SCHOOL", "summary": "Symbolic test route to School.", "requires_clarification": False}


class LiveBackendApiTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.definition = test_map()
        map_path = self.root / "synthetic-map.json"
        map_path.write_text(json.dumps(self.definition.data), encoding="utf-8")
        self.planner, self.reviewer = FakePlanner(), FakeReviewer()
        self.text_provider, self.voice_provider = TextProvider(), StubVoice()
        camera_patch = patch("backend.app.LiveCamera", side_effect=ApiCamera)
        camera_patch.start()
        self.addCleanup(camera_patch.stop)
        network_patch = patch("socket.create_connection", side_effect=AssertionError("This API test must never contact a network service."))
        network_patch.start()
        self.addCleanup(network_patch.stop)
        settings = Settings(db_path=str(self.root / "workspace.sqlite3"), map_path=str(map_path), meta_api_key="offline-test-credential")
        self.app = create_app(settings, provider=self.text_provider, planning_provider=self.planner,
                              live_review_provider=self.reviewer, voice_provider=self.voice_provider,
                              automatic_signal_watch=False,
                              live_camera_url="http://127.0.0.1:8895")
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.camera = self.app.state.live_camera

    def state(self):
        response = self.client.get("/api/v1/state")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def command(self, path, *, status=200, **fields):
        response = self.client.post(path, json={"request_id": str(uuid4()), "expected_revision": self.state()["revision"], **fields})
        self.assertEqual(response.status_code, status, response.text[:1600])
        return response.json()

    def plan(self, *, path="/api/v1/goals", **fields):
        return self.command(path, provider="meta", text="Go to School using the road on the left side of the map.", **fields)

    def ready(self):
        state = self.plan()
        return self.command("/api/v1/approve", plan_id=state["plan"]["id"], plan_revision=state["plan"]["revision"])

    def review(self, *, verdict="PASS"):
        self.reviewer.action_output = action_result(verdict)
        return self.command("/api/v1/live-actions/reviews", review_id=self.state()["review"]["id"],
                            expected_visual="Synthetic fixture: verify the depicted action outcome.")

    def upload_voice(self):
        revision = self.state()["revision"]
        response = self.client.post("/api/v1/voice/transcriptions",
            files={"file": ("generated-tone.wav", wav(), "audio/wav")},
            data={"expected_revision": str(revision), "capture_id": str(uuid4()),
                  "audio_source": "recorded_upload", "language": "ko"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def stopped_via_run(self):
        self.ready()
        self.command("/api/v1/live-actions/run")
        result = self.command("/api/v1/live-actions/run")
        self.assertEqual(result["state"], "WAITING_SIGNAL")
        return result

    def test_meta_goal_uses_camera_frame_and_exact_model_path_for_existing_ar_contract(self):
        state = self.plan()
        self.assertEqual(state["state"], "PLAN_READY")
        self.assertFalse(state["approved"])
        self.assertEqual(self.text_provider.calls, [])
        self.assertEqual(len(self.planner.calls), 1)
        route = state["plan"]["route"]
        self.assertEqual(route["node_ids"], WEST_ROUTE)
        self.assertEqual(route["junction_ids"], ["W", "SW"])
        self.assertEqual(route["directions"]["departure"]["map_direction"], "west")
        self.assertEqual(route["visualization"]["schema_version"], "pushpilot.route-display.v1")
        self.assertEqual(route["visualization"]["source"], "drawing_only")
        moving = [step["route_segment_id"] for step in state["plan"]["steps"] if step["kind"] in {"PUSH", "CROSS"}]
        self.assertEqual(moving, [segment["id"] for segment in route["visualization"]["segments"]])
        frame = state["plan"]["planning"]["frame"]
        self.assertEqual(frame["sha256"], hashlib.sha256(self.planner.calls[0]["image"]).hexdigest())
        self.assertEqual(self.planner.calls[0]["context"]["map"]["map_hash"], route["map_hash"])
        self.assertEqual(self.planner.calls[0]["image"], self.camera.frames[frame["native_frame_id"]])
        self.assertFalse(frame["sensor_exposure_time_known"])
        self.assertFalse(state["capabilities"]["robot"])

    def test_explicit_symbolic_meta_mode_preserves_legacy_path_and_calls_no_camera(self):
        state = self.command("/api/v1/goals", provider="meta", planning_mode="symbolic", text="Go to School.")
        self.assertEqual(state["plan"]["route"]["node_ids"], ["PIZZA", "C", "S", "SCHOOL"])
        self.assertNotIn("planning", state["plan"])
        self.assertEqual(self.text_provider.calls, ["Go to School."])
        self.assertEqual(self.planner.calls, [])
        self.assertEqual(self.camera.calls, [])

    def test_changed_camera_epoch_or_registration_blocks_new_approval_without_new_work(self):
        state = self.plan()
        original_epoch, original_registration = self.camera.epoch, self.camera.registration_id
        captures = len(self.camera.calls)
        frames = dict(self.camera.frames)
        for field, value in (("epoch", "c" * 32), ("registration_id", "d" * 32)):
            self.camera.epoch, self.camera.registration_id = original_epoch, original_registration
            setattr(self.camera, field, value)
            with self.subTest(field=field):
                self.command("/api/v1/approve", status=409, plan_id=state["plan"]["id"],
                             plan_revision=state["plan"]["revision"])
                current = self.state()
                self.assertEqual(current["revision"], state["revision"])
                self.assertEqual(current["state"], "PLAN_READY")
                self.assertFalse(current["approved"])
                self.assertEqual(len(self.camera.calls), captures)
                self.assertEqual(self.camera.frames, frames)
                self.assertEqual(self.reviewer.action_calls, [])

    def test_original_approval_retry_after_view_change_returns_receipt_without_new_work(self):
        state = self.plan()
        payload = {"request_id": str(uuid4()), "expected_revision": state["revision"],
                   "plan_id": state["plan"]["id"], "plan_revision": state["plan"]["revision"]}
        first = self.client.post("/api/v1/approve", json=payload)
        self.assertEqual(first.status_code, 200, first.text[:1600])
        receipt = first.json()
        self.assertTrue(receipt["approved"])
        captures = len(self.camera.calls)
        frames = dict(self.camera.frames)
        self.camera.epoch, self.camera.registration_id = "c" * 32, "d" * 32
        retried = self.client.post("/api/v1/approve", json=payload)
        self.assertEqual(retried.status_code, 200, retried.text[:1600])
        self.assertEqual(retried.json(), receipt)
        self.assertEqual(self.state()["revision"], receipt["revision"])
        self.assertEqual(len(self.camera.calls), captures)
        self.assertEqual(self.camera.frames, frames)
        self.assertEqual(self.reviewer.action_calls, [])
        self.assertEqual(len(self.planner.calls), 1)

    def test_next_live_advance_after_view_change_refuses_before_frames_or_actions(self):
        state = self.ready()
        original_epoch, original_registration = self.camera.epoch, self.camera.registration_id
        captures = len(self.camera.calls)
        frames = dict(self.camera.frames)
        for field, value in (("epoch", "c" * 32), ("registration_id", "d" * 32)):
            self.camera.epoch, self.camera.registration_id = original_epoch, original_registration
            setattr(self.camera, field, value)
            for path in ("/api/v1/advance", "/api/v1/live-actions/advance"):
                with self.subTest(field=field, path=path):
                    self.command(path, status=409)
                    current = self.state()
                    self.assertEqual(current["revision"], state["revision"])
                    self.assertEqual(current["state"], "READY")
                    self.assertEqual(current["current_step"], 0)
                    self.assertNotIn("action_receipt", current)
                    self.assertEqual(len(self.camera.calls), captures)
                    self.assertEqual(self.camera.frames, frames)
                    self.assertEqual(self.reviewer.action_calls, [])
                    self.assertFalse(any(event["kind"] == "SIMULATED_ACTION_COMPLETED" for event in current["events"]))

    def test_explicit_live_endpoint_defaults_to_meta_and_rejects_demo(self):
        state = self.command("/api/v1/plans/live", text="Take the map-left road to School.")
        self.assertEqual(state["goal"]["provider"], "meta")
        self.assertEqual(state["plan"]["route"]["node_ids"], WEST_ROUTE)
        self.command("/api/v1/plans/live", status=422, provider="demo", text="School.")
        self.assertEqual(len(self.planner.calls), 1)
        self.assertEqual(self.text_provider.calls, [])

    def test_stale_camera_and_failed_provider_never_fall_back_to_symbolic_or_demo(self):
        self.camera.available = False
        self.command("/api/v1/goals", status=409, provider="meta", text="School.")
        self.assertEqual(self.planner.calls, [])
        self.assertEqual(self.text_provider.calls, [])
        self.assertIsNone(self.state()["plan"])
        self.camera.available = True
        self.planner.error = ProviderError("private provider diagnostic")
        response = self.command("/api/v1/goals", status=502, provider="meta", text="School.")
        self.assertNotIn("private", json.dumps(response))
        self.assertIsNone(self.state()["plan"])
        self.assertFalse(self.state()["approved"])
        self.assertEqual(self.text_provider.calls, [])
        operations = self.client.get("/api/v1/live-intelligence/operations").json()["operations"]
        self.assertEqual([row["status"] for row in operations], ["rejected", "rejected"])

    def test_voice_transcript_candidate_requires_confirmation_and_is_bound_to_live_meta_plan(self):
        before = self.state()
        transcript = self.upload_voice()
        self.assertEqual(self.state(), before)
        self.assertFalse(transcript["mission_submitted"])
        self.assertFalse(transcript["audio_retained"])
        self.assertTrue(transcript["requires_confirmation"])
        receipt_url = "/api/v1/voice/transcriptions/" + transcript["transcript_id"]
        self.assertEqual(self.client.get(receipt_url).status_code, 200)
        confirmed = "Go to School using the road on the left side of the map."
        state = self.command("/api/v1/goals", text=confirmed, provider="meta", source="voice",
                             transcript_id=transcript["transcript_id"])
        self.assertEqual(state["goal"]["source"], "voice")
        self.assertEqual(state["goal"]["text"], confirmed)
        self.assertEqual(state["goal"]["voice_receipt"]["original_text"], "피자집에서 학교로 가줘.")
        self.assertEqual(state["goal"]["voice_receipt"]["confirmed_text"], confirmed)
        self.assertEqual(state["goal"]["voice_receipt"]["audio_source"], "recorded_upload")
        self.assertEqual(state["plan"]["route"]["node_ids"], WEST_ROUTE)
        self.assertEqual(self.text_provider.calls, [])
        self.assertEqual(len(self.voice_provider.calls), 1)
        self.assertEqual(len(self.planner.calls), 1)
        self.assertEqual(self.client.get(receipt_url).status_code, 409)

    def test_unconfirmed_or_demo_sourced_voice_cannot_be_submitted_as_a_goal(self):
        for values in ({"provider": "meta"}, {"provider": "demo"}):
            self.command("/api/v1/goals", status=422, text="School.", source="voice", **values)
        self.assertIsNone(self.state()["goal"])
        self.assertEqual(self.planner.calls, [])
        self.assertEqual(self.text_provider.calls, [])

    def test_live_action_and_reobserve_routes_keep_the_original_server_capture(self):
        self.ready()
        first = self.command("/api/v1/advance")  # Existing frontend advance must enter the live path.
        original_review_id = first["review"]["id"]
        self.assertEqual(first["state"], "REVIEW_REQUIRED")
        self.assertFalse(first["action_receipt"]["physical_stop_verified"])
        self.command("/api/v1/reviews", status=409, review_id=original_review_id, verdict="PASS")
        uncertain = self.review(verdict="REOBSERVE")
        self.assertEqual(uncertain["state"], "REOBSERVE")
        first_before = deepcopy(self.reviewer.action_calls[0]["before"])
        renewed = self.command("/api/v1/live-actions/reobserve")
        self.assertNotEqual(renewed["review"]["id"], original_review_id)
        self.assertEqual(renewed["state"], "REVIEW_REQUIRED")
        accepted = self.review()
        self.assertEqual(accepted["state"], "READY")
        second = self.reviewer.action_calls[1]
        self.assertEqual(second["before"], first_before)
        self.assertGreater(second["after"]["metadata"]["sequence"], first_before["metadata"]["sequence"])
        self.assertEqual(second["server_action"]["id"], first["action_receipt"]["action_id"])
        self.assertEqual(accepted["review"]["evidence"]["input_kind"], "server_bound_live_pair")

    def test_signal_route_observes_only_after_stop_and_manual_green_cannot_bypass(self):
        self.ready()
        self.command("/api/v1/live-signals/reviews", status=409)
        self.command("/api/v1/live-actions/advance")
        self.review()
        stopped = self.command("/api/v1/live-actions/advance")
        self.assertEqual(stopped["action_receipt"]["kind"], "STOP")
        waiting = self.review()
        self.assertEqual(waiting["state"], "WAITING_SIGNAL")
        self.assertTrue(waiting["stopped"])
        self.command("/api/v1/signal", status=409, color="GREEN", junction_id="W")
        red = self.command("/api/v1/live-signals/reviews")
        self.assertEqual(red["state"], "WAITING_SIGNAL")
        self.assertEqual(red["signal"]["source"], "meta")
        self.assertEqual(red["signal"]["color"], "RED")
        self.reviewer.signal_output = signal_result("GREEN")
        green = self.command("/api/v1/live-signals/reviews")
        self.assertEqual(green["state"], "REVIEW_REQUIRED")
        self.assertEqual(green["plan"]["steps"][green["current_step"]]["kind"], "CROSS")
        self.assertEqual(len(self.reviewer.signal_calls), 2)
        self.assertEqual(self.reviewer.signal_calls[0]["signal_target"]["approach_from"], "PIZZA")
        self.assertFalse(green["signal"]["evidence"]["motion_authority"])

    def test_existing_reobserve_alias_preserves_live_action_capture_binding(self):
        self.ready()
        self.command("/api/v1/advance")
        self.review(verdict="REOBSERVE")
        original_before = deepcopy(self.reviewer.action_calls[0]["before"])
        renewed = self.command("/api/v1/reobserve")
        self.assertEqual(renewed["state"], "REVIEW_REQUIRED")
        accepted = self.review()
        self.assertEqual(accepted["state"], "READY")
        self.assertEqual(self.reviewer.action_calls[1]["before"], original_before)

    def test_run_performs_one_action_with_automatic_live_pair_review_and_is_idempotent(self):
        self.ready()
        payload = {"request_id": str(uuid4()), "expected_revision": self.state()["revision"]}
        response = self.client.post("/api/v1/live-actions/run", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["state"], "READY")
        self.assertEqual(result["current_step"], 1)
        self.assertEqual(result["review"]["source"], "meta")
        self.assertEqual(result["review"]["verdict"], "PASS")
        self.assertEqual(len(self.reviewer.action_calls), 1)
        inputs = self.reviewer.action_calls[0]
        self.assertGreater(inputs["after"]["metadata"]["sequence"], inputs["before"]["metadata"]["sequence"])
        self.assertEqual(inputs["server_action"]["drawing_geometry"]["segment"]["id"], inputs["server_action"]["route_segment_id"])
        self.assertEqual(inputs["map"]["graph"]["map_hash"], self.definition.geometry_hash)
        self.assertEqual(inputs["map"]["projected_after"]["pixel_frame_id"], inputs["after"]["metadata"]["id"])
        self.assertFalse(inputs["map"]["projected_after"]["measured_car_pose"])
        self.assertEqual(self.client.post("/api/v1/live-actions/run", json=payload).json(), result)
        self.assertEqual(len(self.reviewer.action_calls), 1)
        self.assertEqual(sum(event["kind"] == "SIMULATED_ACTION_COMPLETED" for event in self.state()["events"]), 1)

    def test_run_after_reobserve_keeps_original_before_and_executes_no_second_action(self):
        self.ready()
        self.reviewer.action_output = action_result("REOBSERVE")
        uncertain = self.command("/api/v1/live-actions/run")
        self.assertEqual(uncertain["state"], "REOBSERVE")
        original_receipt = deepcopy(uncertain["action_receipt"])
        original_before = deepcopy(self.reviewer.action_calls[0]["before"])
        self.reviewer.action_output = action_result("PASS")
        accepted = self.command("/api/v1/live-actions/run")
        self.assertEqual(accepted["state"], "READY")
        self.assertEqual(accepted["action_receipt"], original_receipt)
        self.assertEqual(self.reviewer.action_calls[1]["before"], original_before)
        self.assertEqual(sum(event["kind"] == "SIMULATED_ACTION_COMPLETED" for event in accepted["events"]), 1)

    def test_signal_wait_red_then_green_uses_new_frames_and_replay_sends_no_more_requests(self):
        self.stopped_via_run()
        colors = iter(["RED", "GREEN"])

        async def next_color():
            self.reviewer.signal_output = signal_result(next(colors))

        self.reviewer.signal_callback = next_color
        payload = {"request_id": str(uuid4()), "expected_revision": self.state()["revision"],
                   "max_attempts": 3, "interval_seconds": 0.5}
        response = self.client.post("/api/v1/live-signals/wait", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["state"], "REVIEW_REQUIRED")
        self.assertEqual(result["plan"]["steps"][result["current_step"]]["kind"], "CROSS")
        self.assertEqual(result["signal"]["color"], "GREEN")
        self.assertEqual(len(self.reviewer.signal_calls), 2)
        frames = [call["frame"]["metadata"] for call in self.reviewer.signal_calls]
        self.assertNotEqual(frames[0]["id"], frames[1]["id"])
        self.assertGreater(frames[1]["sequence"], frames[0]["sequence"])
        self.assertEqual(self.client.post("/api/v1/live-signals/wait", json=payload).json(), result)
        self.assertEqual(len(self.reviewer.signal_calls), 2)
        self.assertEqual(sum(event["kind"] == "CROSSING_ADMITTED" for event in self.state()["events"]), 1)

    def test_signal_wait_unknown_stays_stopped_after_three_distinct_observations(self):
        self.stopped_via_run()
        self.reviewer.signal_output = signal_result("UNKNOWN")
        payload = {"request_id": str(uuid4()), "expected_revision": self.state()["revision"],
                   "max_attempts": 3, "interval_seconds": 0.5}
        response = self.client.post("/api/v1/live-signals/wait", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["state"], "WAITING_SIGNAL")
        self.assertTrue(result["stopped"])
        self.assertEqual(result["signal"]["color"], "UNKNOWN")
        self.assertEqual(len(self.reviewer.signal_calls), 3)
        identities = [call["frame"]["metadata"]["id"] for call in self.reviewer.signal_calls]
        self.assertEqual(len(set(identities)), 3)
        self.assertEqual(sum(event["kind"] == "CROSSING_ADMITTED" for event in result["events"]), 0)
        self.assertEqual(self.client.post("/api/v1/live-signals/wait", json=payload).json(), result)
        self.assertEqual(len(self.reviewer.signal_calls), 3)

    def test_operator_cancellation_during_wait_prevents_further_signal_queries(self):
        self.stopped_via_run()
        observed = threading.Event()

        async def note_observation():
            observed.set()

        self.reviewer.signal_callback = note_observation
        payload = {"request_id": str(uuid4()), "expected_revision": self.state()["revision"],
                   "max_attempts": 3, "interval_seconds": 0.5}
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(self.client.post, "/api/v1/live-signals/wait", json=payload)
            self.assertTrue(observed.wait(1), "The first synthetic observation should start promptly.")
            deadline = time.monotonic() + 1
            while self.state()["signal"]["color"] != "RED" and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertEqual(self.state()["signal"]["color"], "RED")
            cancelled = self.command("/api/v1/cancel")
            self.assertEqual(cancelled["state"], "CANCELLED")
            response = pending.result(timeout=3)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(len(self.reviewer.signal_calls), 1)
        self.assertEqual(self.state()["state"], "CANCELLED")
        self.assertFalse(self.state()["approved"])

    def test_signal_wait_rejects_unbounded_or_mistyped_controls_before_observation(self):
        self.stopped_via_run()
        for fields in ({"max_attempts": 0}, {"max_attempts": 4}, {"max_attempts": True},
                       {"interval_seconds": 0.49}, {"interval_seconds": 10.1}, {"interval_seconds": True}):
            self.command("/api/v1/live-signals/wait", status=422, **fields)
        self.assertEqual(self.reviewer.signal_calls, [])

    def test_signal_watch_start_status_and_stop_routes_preserve_stopped_approval(self):
        self.stopped_via_run()
        entered, release = threading.Event(), threading.Event()

        async def hold_judgment():
            entered.set()
            await asyncio.to_thread(release.wait, 2)

        self.reviewer.signal_callback = hold_judgment
        initial = self.client.get("/api/v1/live-signals/watch")
        self.assertEqual(initial.status_code, 200)
        self.assertFalse(initial.json()["motion_authority"])
        self.assertIsNone(initial.json()["signal_watch"])
        try:
            started = self.command("/api/v1/live-signals/watch", max_attempts=2,
                                   interval_seconds=0.5, max_duration_seconds=5.0)
            self.assertEqual(started["signal_watch"]["status"], "running")
            self.assertTrue(entered.wait(1), "A new synthetic judgment should begin after watch start.")
            running = self.client.get("/api/v1/live-signals/watch").json()
            self.assertEqual(running["signal_watch"]["status"], "running")
            self.assertEqual(running["signal_watch"]["attempts"], 1)
            stopped = self.command("/api/v1/live-signals/watch/stop")
            self.assertEqual(stopped["signal_watch"]["status"], "cancelled")
            self.assertEqual(stopped["state"], "WAITING_SIGNAL")
            self.assertTrue(stopped["stopped"])
            self.assertTrue(stopped["approved"])
            self.assertEqual(len(self.reviewer.signal_calls), 1)
            final = self.client.get("/api/v1/live-signals/watch").json()
            self.assertEqual(final["signal_watch"]["status"], "cancelled")
            self.assertEqual(sum(event["kind"] == "CROSSING_ADMITTED" for event in self.state()["events"]), 0)
        finally:
            release.set()
            if (self.state().get("signal_watch") or {}).get("status") == "running":
                self.command("/api/v1/live-signals/watch/stop")

    def test_enabled_automatic_watch_starts_after_stop_review_and_observes_red_without_reapproval(self):
        ready = self.ready()
        self.app.state.automatic_signal_watch = True
        entered, release = threading.Event(), threading.Event()

        async def hold_judgment():
            entered.set()
            await asyncio.to_thread(release.wait, 2)

        self.reviewer.signal_callback = hold_judgment
        try:
            pushed = self.command("/api/v1/live-actions/run")
            self.assertEqual(pushed["state"], "READY")
            stopped = self.command("/api/v1/live-actions/run")
            self.assertEqual(stopped["state"], "WAITING_SIGNAL")
            self.assertEqual(stopped["signal_watch"]["status"], "running")
            self.assertTrue(entered.wait(1), "Accepted STOP review should automatically start a new signal judgment.")
            release.set()
            deadline = time.monotonic() + 1
            current = self.state()
            while current["signal"]["color"] != "RED" and time.monotonic() < deadline:
                time.sleep(0.005)
                current = self.state()
            self.assertEqual(current["signal"]["color"], "RED")
            self.assertEqual(current["signal"]["source"], "meta")
            self.assertEqual(current["state"], "WAITING_SIGNAL")
            self.assertTrue(current["approved"])
            self.assertTrue(current["stopped"])
            self.assertEqual(current["plan"]["id"], ready["plan"]["id"])
            self.assertEqual(sum(event["kind"] == "PLAN_APPROVED" for event in current["events"]), 1)
            self.assertEqual(sum(event["kind"] == "CROSSING_ADMITTED" for event in current["events"]), 0)
            self.assertGreaterEqual(len(self.reviewer.signal_calls), 1)
            self.assertEqual(self.reviewer.signal_calls[0]["server_stop"]["plan_id"], ready["plan"]["id"])
        finally:
            release.set()
            if (self.state().get("signal_watch") or {}).get("status") == "running":
                self.command("/api/v1/live-signals/watch/stop")

    def test_evidence_operations_map_and_voice_routers_are_registered_without_hidden_fallback(self):
        status = self.client.get("/api/v1/voice")
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["backend_implemented"])
        self.assertFalse(status.json()["microphone_connected"])
        self.assertFalse(status.json()["provider_access_verified"])
        current_map = self.client.get("/api/v1/map").json()
        validation = self.client.post("/api/v1/maps/validate", json={"definition": self.definition.data})
        self.assertEqual(validation.status_code, 200)
        self.assertFalse(validation.json()["installed"])
        self.assertEqual(validation.json()["map"]["geometry_hash"], current_map["geometry_hash"])
        state = self.plan()
        evidence = state["plan"]["planning"]
        image = self.client.get(evidence["frame"]["image_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["content-type"], "image/jpeg")
        self.assertEqual(image.headers["cache-control"], "no-store")
        self.assertEqual(image.content, self.planner.calls[0]["image"])
        operations = self.client.get("/api/v1/live-intelligence/operations")
        self.assertEqual(operations.status_code, 200)
        self.assertFalse(operations.json()["motion_authority"])
        operation = operations.json()["operations"][0]
        self.assertEqual(operation["id"], evidence["request_id"])
        self.assertEqual(operation["status"], "accepted")
        self.assertEqual(operation["binding"]["frame"]["sha256"], evidence["frame"]["sha256"])
        absent = self.client.get("/api/v1/live-evidence/frames/" + "0" * 32 + "/image")
        self.assertEqual(absent.status_code, 404)
        self.assertEqual(absent.json()["detail"]["code"], "LIVE_EVIDENCE_NOT_FOUND")
        self.assertEqual(self.client.get("/api/v1/unknown-feature").status_code, 404)
        self.assertEqual(self.text_provider.calls, [])


if __name__ == "__main__":
    unittest.main()
