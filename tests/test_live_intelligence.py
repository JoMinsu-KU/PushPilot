"""Native-frame orchestration with generated JPEGs and fake providers only."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from uuid import uuid4

import cv2
import numpy as np

from backend.core import CommandError, WorkspaceStore
from backend.live_intelligence import LiveIntelligenceService
from backend.maps import MapDefinition
from backend.meta import ProviderError
from backend.scene import SceneError
from backend.voice import VoiceService


WEST_ROUTE = ["PIZZA", "W", "SW", "SCHOOL"]


def planning_result():
    return {"destination": "SCHOOL", "summary": "Take the road on the left side of the map through W and SW to School.",
            "route_nodes": list(WEST_ROUTE), "requires_clarification": False,
            "constraints": {"departure": "west", "first_turn": "left", "via_nodes": ["W", "SW"], "avoid_nodes": ["C"]},
            "scene_assessment": {"status": "clear", "detail": "Synthetic test scene and drawing graph only."}}


def action_result(verdict="PASS"):
    return {"verdict": verdict, "observed": "Synthetic test fixture supports this requested visible placement.",
            "summary": "The fixture comparison supports the expected outcome.",
            "limitations": ["Generated JPEGs and simulated receipts; no physical motion is established."]}


def signal_result(color="RED"):
    return {"color": color, "visible": color in {"RED", "GREEN"},
            "summary": "Synthetic paper-signal fixture: " + color + ".",
            "limitations": ["Mock model result, no actual color recognition or physical stopping."]}


def test_map(with_targets=True):
    data = MapDefinition().data
    if with_targets:
        data["signal_targets"] = [
            {"id": "synthetic-W-from-PIZZA", "junction_id": "W", "approach_from": "PIZZA",
             "bounds_mm": [35, 95, 65, 115], "description": "Synthetic fixture only: operator paper signal controlling W from Pizza."},
            {"id": "synthetic-SW-from-W", "junction_id": "SW", "approach_from": "W",
             "bounds_mm": [35, 170, 65, 190], "description": "Synthetic fixture only: operator paper signal controlling SW from W."},
        ]
    return MapDefinition.from_data(data)


class NeverTextProvider:
    def interpret(self, _text):
        raise AssertionError("Live planning must never fall back to text-only goal interpretation.")


class FakeCamera:
    """Model identity/freshness boundaries, not detection quality or hardware."""

    def __init__(self, definition):
        self.map = definition
        self.epoch = "a" * 32
        self.camera_id = "generated-test-camera"
        self.registration_id = "b" * 32
        self.sequence = 0
        self.available = True
        self.locked = True
        self.fresh_after = True
        self.calls = []
        self.frames = {}
        self.before_capture = None

    def capture(self, *, after_sequence=None, not_before=None):
        self.calls.append({"after_sequence": after_sequence, "not_before": not_before, "at": time.monotonic()})
        if self.before_capture:
            self.before_capture()
        if not self.available:
            raise SceneError(409, "Synthetic source stale.", "LIVE_CAPTURE_UNAVAILABLE")
        if not self.locked:
            raise SceneError(409, "Synthetic view changed.", "LIVE_CAPTURE_REGISTRATION")
        if not self.fresh_after and (after_sequence is not None or not_before is not None):
            raise SceneError(409, "Synthetic frame has not advanced after action.", "LIVE_CAPTURE_NOT_NEW")
        self.sequence += 1
        image = np.full((64, 96, 3), 210, dtype=np.uint8)
        cv2.rectangle(image, (self.sequence % 40 + 1, 20), (self.sequence % 40 + 14, 34), (30, 60, 170), -1)
        ok, encoded = cv2.imencode(".jpg", image)
        assert ok
        data = encoded.tobytes()
        metadata = {"id": uuid4().hex, "source": "live", "sequence": self.sequence,
                    "width": 96, "height": 64, "mime_type": "image/jpeg", "sha256": hashlib.sha256(data).hexdigest(),
                    "received_at": datetime.now(timezone.utc).isoformat(), "age_at_selection_ms": 0.0,
                    "camera_id": self.camera_id, "epoch": self.epoch,
                    "map_id": self.map.id, "map_version": self.map.version, "map_hash": self.map.geometry_hash,
                    "timestamp_source": "camera_host_receive", "sensor_exposure_time_known": False,
                    "registration": {"id": self.registration_id, "status": "locked", "homography": [[0.2, 0, 0], [0, 0.2, 0], [0, 0, 1]]},
                    "motion_authority": False}
        self.frames[metadata["id"]] = data
        if after_sequence is not None and self.sequence <= after_sequence:
            raise SceneError(409, "Synthetic frame has not advanced.", "LIVE_CAPTURE_NOT_NEW")
        if not_before is not None and time.monotonic() <= not_before:
            raise SceneError(409, "Synthetic frame predates selection.", "LIVE_CAPTURE_NOT_NEW")
        return {"data": data, "metadata": metadata}

    def check_binding(self, metadata):
        if not self.available or not self.locked:
            raise SceneError(409, "Synthetic camera no longer usable.", "LIVE_CAPTURE_CHANGED")
        expected = {"epoch": self.epoch, "camera_id": self.camera_id, "width": 96, "height": 64,
                    "map_id": self.map.id, "map_version": self.map.version, "map_hash": self.map.geometry_hash}
        if any(metadata[key] != value for key, value in expected.items()) or metadata["registration"]["id"] != self.registration_id:
            raise SceneError(409, "Synthetic camera binding changed.", "LIVE_CAPTURE_CHANGED")


class FakePlanner:
    def __init__(self):
        self.calls = []
        self.result = planning_result()
        self.callback = None
        self.error = None

    def plan(self, text, context, image):
        self.calls.append({"text": text, "context": deepcopy(context), "image": image})
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        return deepcopy(self.result)


class FakeReviewer:
    def __init__(self):
        self.action_calls, self.signal_calls = [], []
        self.action_output = action_result()
        self.signal_output = signal_result()
        self.action_callback = self.signal_callback = None
        self.action_error = self.signal_error = None

    async def action(self, inputs):
        self.action_calls.append(deepcopy(inputs))
        if self.action_callback:
            await self.action_callback()
        if self.action_error:
            raise self.action_error
        return deepcopy(self.action_output)

    async def signal(self, inputs):
        self.signal_calls.append(deepcopy(inputs))
        if self.signal_callback:
            await self.signal_callback()
        if self.signal_error:
            raise self.signal_error
        return deepcopy(self.signal_output)


class LiveIntelligenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "workspace.sqlite3")
        self.store = WorkspaceStore(self.path, provider=NeverTextProvider(), map_definition=test_map())
        self.addCleanup(lambda: self.store.close())
        self.camera = FakeCamera(self.store.map_definition)
        self.planner, self.reviewer = FakePlanner(), FakeReviewer()
        self.service = LiveIntelligenceService(self.store, self.camera,
                                               planning_provider=self.planner, review_provider=self.reviewer)

    def payload(self, **extra):
        return {"request_id": str(uuid4()), "expected_revision": self.store.snapshot()["revision"], **extra}

    def command(self, action, **extra):
        result, status = self.store.execute(action, self.payload(**extra))
        self.assertEqual(status, 200)
        return result

    async def plan(self, **extra):
        result, status = await self.service.plan(self.payload(text="Go to School using the left side of the map.", source="typed", **extra))
        self.assertEqual(status, 200, result)
        return result

    async def ready(self):
        result = await self.plan()
        return self.command("approve", plan_id=result["plan"]["id"], plan_revision=result["plan"]["revision"])

    async def review(self, **extra):
        state = self.store.snapshot()
        payload = self.payload(review_id=state["review"]["id"], expected_visual="Synthetic fixture: verify the depicted placement.", **extra)
        response, status = await self.service.review_action(payload)
        self.assertEqual(status, 200, response)
        return response

    async def stopped(self):
        await self.ready()
        self.service.advance(self.payload())
        await self.review()
        self.service.advance(self.payload())
        result = await self.review()
        self.assertEqual(result["state"], "WAITING_SIGNAL")
        return result

    async def test_exact_west_route_and_native_bytes_are_bound_and_persisted(self):
        state = await self.plan()
        self.assertEqual(state["plan"]["route"]["node_ids"], WEST_ROUTE)
        self.assertEqual(state["plan"]["route"]["directions"]["departure"]["map_direction"], "west")
        self.assertFalse(state["approved"])
        self.assertEqual(state["state"], "PLAN_READY")
        evidence = state["plan"]["planning"]
        self.assertFalse(evidence["motion_authority"])
        self.assertTrue(evidence["simulation_only"])
        self.assertEqual(evidence["input_kind"], "live_native_frame_and_graph")
        self.assertEqual(evidence["frame"]["sha256"], hashlib.sha256(self.planner.calls[0]["image"]).hexdigest())
        self.assertEqual(self.service.frame(evidence["frame"]["id"]), self.planner.calls[0]["image"])
        self.assertEqual(self.planner.calls[0]["image"], self.camera.frames[evidence["frame"]["native_frame_id"]])
        self.assertEqual(self.planner.calls[0]["context"]["map"]["map_hash"], self.store.map_definition.geometry_hash)
        self.assertFalse(state["capabilities"]["robot"])
        self.assertEqual(self.service.operations()["operations"][0]["status"], "accepted")

    async def test_plan_request_is_idempotent_even_after_approval(self):
        payload = self.payload(text="School through the west road.", source="typed")
        first = await self.service.plan(payload)
        state = first[0]
        self.command("approve", plan_id=state["plan"]["id"], plan_revision=state["plan"]["revision"])
        self.assertEqual(await self.service.plan(payload), first)
        self.assertEqual(len(self.planner.calls), 1)
        with self.assertRaises(CommandError):
            await self.service.plan({**payload, "text": "Different query"})

    async def test_failed_replacement_invalidates_older_approval_without_fallback(self):
        await self.plan()
        self.planner.error = ProviderError("private provider diagnostic")
        payload = self.payload(text="School using another route.")
        response, status = await self.service.plan(payload)
        self.assertEqual(status, 502)
        self.assertNotIn("private", json.dumps(response))
        state = self.store.snapshot()
        self.assertEqual(state["state"], "IDLE")
        self.assertIsNone(state["plan"])
        self.assertFalse(state["approved"])
        self.assertEqual(await self.service.plan(payload), (response, status))
        self.assertEqual(len(self.planner.calls), 2)

    async def test_clarification_and_uncertain_scene_never_create_a_route(self):
        self.planner.result.update(destination="UNKNOWN", route_nodes=[], requires_clarification=True,
                                   summary="Clarify whether left means map-left or turn-left.")
        result = await self.plan()
        self.assertIsNone(result["plan"])
        self.assertEqual(result["events"][-1]["kind"], "LIVE_PLAN_CLARIFICATION")
        self.planner.result = planning_result()
        self.planner.result["scene_assessment"]["status"] = "uncertain"
        result = await self.plan()
        self.assertIsNone(result["plan"])
        self.assertEqual(result["state"], "IDLE")

    async def test_disconnected_route_or_constraint_violation_has_no_substitute(self):
        for route, constraints in ((["PIZZA", "SW", "SCHOOL"], None),
                                   (WEST_ROUTE, {"departure": "east", "first_turn": "any", "via_nodes": [], "avoid_nodes": []})):
            self.planner.result = planning_result()
            self.planner.result["route_nodes"] = route
            if constraints:
                self.planner.result["constraints"] = constraints
            result, status = await self.service.plan(self.payload(text="School"))
            self.assertEqual(status, 502)
            self.assertIsNone(self.store.snapshot()["plan"])
        payload = self.payload(text="School", route_constraints={"departure": "east", "first_turn": "any", "via_nodes": [], "avoid_nodes": []})
        self.planner.result = planning_result()
        self.assertEqual((await self.service.plan(payload))[1], 502)

    async def test_camera_and_map_change_while_planning_reject_result(self):
        for callback in (lambda: setattr(self.camera, "epoch", "c" * 32),
                         lambda: setattr(self.camera, "registration_id", "d" * 32),
                         lambda: setattr(self.camera, "available", False)):
            self.camera.available, self.camera.epoch, self.camera.registration_id = True, "a" * 32, "b" * 32
            self.planner.callback = callback
            result, status = await self.service.plan(self.payload(text="School"))
            self.assertEqual(status, 409, result)
            self.assertIsNone(self.store.snapshot()["plan"])
        self.camera.available = True
        self.planner.callback = lambda: setattr(self.store.map_definition, "version", "changed-during-inference")
        self.assertEqual((await self.service.plan(self.payload(text="School")))[1], 409)

    async def test_pending_duplicate_and_operator_cancel_while_provider_runs(self):
        entered, release = threading.Event(), threading.Event()

        def hold():
            entered.set()
            release.wait(3)

        self.planner.callback = hold
        payload = self.payload(text="School")
        pending = asyncio.create_task(self.service.plan(payload))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        try:
            with self.assertRaises(CommandError):
                await self.service.plan(payload)
            self.command("cancel")
        finally:
            release.set()
        result, status = await pending
        self.assertEqual(status, 409, result)
        self.assertEqual(self.store.snapshot()["state"], "CANCELLED")
        self.assertEqual(len(self.planner.calls), 1)

    async def test_task_cancellation_releases_pending_plan_without_replay(self):
        entered, release = threading.Event(), threading.Event()
        self.planner.callback = lambda: (entered.set(), release.wait(3))
        payload = self.payload(text="School")
        pending = asyncio.create_task(self.service.plan(payload))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        pending.cancel()
        try:
            with self.assertRaises(asyncio.CancelledError):
                await pending
        finally:
            release.set()
        self.assertNotIn("planning_pending", self.store.snapshot())
        self.assertIsNone(self.store.snapshot()["plan"])
        response = await self.service.plan(payload)
        self.assertEqual(response[1], 503)
        self.assertEqual(len(self.planner.calls), 1)

    async def test_no_fresh_locked_camera_fails_before_provider(self):
        self.camera.locked = False
        result, status = await self.service.plan(self.payload(text="School"))
        self.assertEqual(status, 409)
        self.assertEqual(self.planner.calls, [])
        self.assertIsNone(self.store.snapshot()["plan"])

    async def test_action_before_after_pair_is_server_bound_and_review_idempotent(self):
        await self.ready()
        payload = self.payload()
        first = self.service.advance(payload)
        self.assertEqual(self.service.advance(payload), first)
        self.assertEqual(first[0]["review"]["verdict"], "PENDING")
        state = self.store.snapshot()
        review_payload = self.payload(review_id=state["review"]["id"], expected_visual="Synthetic placement check.")
        reviewed = await self.service.review_action(review_payload)
        self.assertEqual(reviewed[1], 200, reviewed)
        self.assertEqual(reviewed[0]["state"], "READY")
        self.assertEqual(await self.service.review_action(review_payload), reviewed)
        self.assertEqual(len(self.reviewer.action_calls), 1)
        inputs = self.reviewer.action_calls[0]
        self.assertEqual(inputs["server_action"]["id"], first[0]["action_receipt"]["action_id"])
        self.assertGreater(inputs["after"]["metadata"]["sequence"], inputs["before"]["metadata"]["sequence"])
        self.assertIsNotNone(self.camera.calls[-1]["not_before"])
        for side in ("before", "after"):
            self.assertEqual(self.service.frame(inputs[side]["metadata"]["id"]), inputs[side]["data"])
        evidence = reviewed[0]["review"]["evidence"]
        self.assertFalse(evidence["action_receipt"]["physical_stop_verified"])
        self.assertEqual(evidence["source"], "meta")
        self.assertEqual(evidence["input_kind"], "server_bound_live_pair")

    async def test_action_review_requires_live_advance_and_correct_current_review(self):
        await self.ready()
        self.command("advance")
        with self.assertRaises(CommandError):
            await self.service.review_action(self.payload(review_id=self.store.snapshot()["review"]["id"], expected_visual="Check"))
        self.assertEqual(self.reviewer.action_calls, [])

    async def test_after_frame_must_be_new_before_action_provider_dispatch(self):
        await self.ready()
        self.service.advance(self.payload())
        state = self.store.snapshot()
        self.camera.fresh_after = False
        payload = self.payload(review_id=state["review"]["id"], expected_visual="Check newly captured placement.")
        response, status = await self.service.review_action(payload)
        self.assertEqual(status, 409)
        self.assertEqual(self.reviewer.action_calls, [])
        self.assertEqual(self.store.snapshot(), state)
        captures = len(self.camera.calls)
        self.assertGreater(captures, 3)
        self.assertEqual(await self.service.review_action(payload), (response, status))
        self.assertEqual(len(self.camera.calls), captures)

    async def test_action_pending_duplicates_and_task_cancellation_are_bound(self):
        await self.ready()
        self.service.advance(self.payload())
        entered, release = asyncio.Event(), asyncio.Event()

        async def hold():
            entered.set()
            await release.wait()

        self.reviewer.action_callback = hold
        state = self.store.snapshot()
        payload = self.payload(review_id=state["review"]["id"], expected_visual="Check")
        pending = asyncio.create_task(self.service.review_action(payload))
        await asyncio.wait_for(entered.wait(), 2)
        with self.assertRaises(CommandError):
            await self.service.review_action(payload)
        with self.assertRaises(CommandError):
            await self.service.review_action(self.payload(review_id=state["review"]["id"], expected_visual="Other request"))
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertEqual(self.store.snapshot(), state)
        self.assertEqual((await self.service.review_action(payload))[1], 503)
        self.assertEqual(len(self.reviewer.action_calls), 1)

    async def test_action_review_fail_reobserve_and_new_observation_use_same_before(self):
        await self.ready()
        self.service.advance(self.payload())
        self.reviewer.action_output = action_result("REOBSERVE")
        result = await self.review()
        self.assertEqual(result["state"], "REOBSERVE")
        old_review = result["review"]["id"]
        first_before = self.reviewer.action_calls[-1]["before"]["data"]
        payload = self.payload()
        renewed = self.service.reobserve(payload)
        self.assertEqual(self.service.reobserve(payload), renewed)
        self.assertNotEqual(renewed[0]["review"]["id"], old_review)
        self.reviewer.action_output = action_result("FAIL")
        result = await self.review()
        self.assertEqual(result["state"], "FAULT")
        self.assertFalse(result["approved"])
        self.assertEqual(self.reviewer.action_calls[-1]["before"]["data"], first_before)

    async def test_action_provider_failure_camera_change_and_cancel_do_not_apply_pass(self):
        await self.ready()
        self.service.advance(self.payload())
        before = self.store.snapshot()
        self.reviewer.action_error = RuntimeError("private secret")
        payload = self.payload(review_id=before["review"]["id"], expected_visual="Check")
        response = await self.service.review_action(payload)
        self.assertEqual(response[1], 502)
        self.assertNotIn("private", json.dumps(response))
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(await self.service.review_action(payload), response)
        self.reviewer.action_error = None

        async def change_camera():
            self.camera.registration_id = "changed"

        self.reviewer.action_callback = change_camera
        response = await self.service.review_action(self.payload(review_id=before["review"]["id"], expected_visual="Check"))
        self.assertEqual(response[1], 409)
        self.assertEqual(self.store.snapshot()["review"]["verdict"], "PENDING")
        self.camera.registration_id = "b" * 32

        async def cancel():
            self.command("cancel")

        self.reviewer.action_callback = cancel
        response = await self.service.review_action(self.payload(review_id=before["review"]["id"], expected_visual="Check"))
        self.assertEqual(response[1], 409)
        self.assertEqual(self.store.snapshot()["state"], "CANCELLED")

    async def test_signal_needs_mandatory_accepted_stop_and_explicit_target(self):
        await self.ready()
        with self.assertRaises(CommandError):
            await self.service.review_signal(self.payload())
        self.assertEqual(self.reviewer.signal_calls, [])

    async def test_red_wait_then_new_frame_green_admits_one_simulated_crossing(self):
        stopped = await self.stopped()
        red_payload = self.payload()
        red, status = await self.service.review_signal(red_payload)
        self.assertEqual(status, 200, red)
        self.assertEqual(red["state"], "WAITING_SIGNAL")
        self.assertTrue(red["stopped"])
        self.assertEqual(red["signal"]["color"], "RED")
        self.assertEqual(await self.service.review_signal(red_payload), (red, status))
        self.assertEqual(len(self.reviewer.signal_calls), 1)
        self.reviewer.signal_output = signal_result("GREEN")
        green_payload = self.payload()
        green, status = await self.service.review_signal(green_payload)
        self.assertEqual(status, 200, green)
        self.assertEqual((green["state"], green["plan"]["steps"][green["current_step"]]["kind"]), ("REVIEW_REQUIRED", "CROSS"))
        self.assertEqual(green["stop_receipt"], stopped["stop_receipt"])
        self.assertFalse(green["stop_receipt"]["physical_stop_verified"])
        first, second = self.reviewer.signal_calls
        self.assertNotEqual(first["frame"]["metadata"]["id"], second["frame"]["metadata"]["id"])
        self.assertGreater(second["frame"]["metadata"]["sequence"], first["frame"]["metadata"]["sequence"])
        self.assertEqual(second["signal_target"]["junction_id"], "W")
        self.assertEqual(second["signal_target"]["approach_from"], "PIZZA")
        self.assertEqual(await self.service.review_signal(green_payload), (green, status))
        self.assertEqual(len(self.reviewer.signal_calls), 2)
        self.assertEqual(len([event for event in green["events"] if event["kind"] == "CROSSING_ADMITTED"]), 1)
        await self.review()
        self.assertEqual(self.store.snapshot()["state"], "READY")

    async def test_manual_early_green_is_cleared_by_live_stop_review(self):
        await self.ready()
        with self.assertRaises(CommandError):
            self.command("signal", color="GREEN", junction_id="W")
        # Model a prior/inherited manual value without bypassing its API guard.
        with self.store._lock, self.store._db:
            state = self.store._load()
            state["signal"] = {"color": "GREEN", "source": "simulation", "junction_id": "W", "observed_at": self.store._at()}
            self.store._save(state)
        self.service.advance(self.payload())
        await self.review()
        self.service.advance(self.payload())
        state = await self.review()
        self.assertEqual(state["state"], "WAITING_SIGNAL")
        self.assertEqual(state["signal"]["color"], "UNKNOWN")
        self.assertFalse(any(event["kind"] == "CROSSING_ADMITTED" for event in state["events"]))

    async def test_unknown_and_provider_failure_keep_stopped_without_demo_fallback(self):
        await self.stopped()
        self.reviewer.signal_output = signal_result("UNKNOWN")
        unknown, status = await self.service.review_signal(self.payload())
        self.assertEqual(status, 200, unknown)
        self.assertEqual(unknown["state"], "WAITING_SIGNAL")
        self.reviewer.signal_error = RuntimeError("private provider diagnostic")
        before = self.store.snapshot()
        payload = self.payload()
        response, status = await self.service.review_signal(payload)
        self.assertEqual(status, 502)
        self.assertNotIn("private", json.dumps(response))
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(await self.service.review_signal(payload), (response, status))

    async def test_stale_or_changed_green_is_not_admitted(self):
        await self.stopped()
        self.reviewer.signal_output = signal_result("GREEN")
        self.service.signal_max_age = -1
        response, status = await self.service.review_signal(self.payload())
        self.assertEqual(status, 409)
        self.assertEqual(self.store.snapshot()["state"], "WAITING_SIGNAL")
        self.service.signal_max_age = 30

        async def change():
            self.camera.epoch = "new-camera-epoch"

        self.reviewer.signal_callback = change
        response, status = await self.service.review_signal(self.payload())
        self.assertEqual(status, 409)
        self.assertEqual(self.store.snapshot()["state"], "WAITING_SIGNAL")
        self.assertTrue(self.store.snapshot()["stopped"])

    async def test_missing_target_rejects_before_sending_any_signal_image(self):
        definition = test_map(False)
        self.store.map_definition = definition
        self.camera.map = definition
        await self.stopped()
        with self.assertRaises(CommandError) as raised:
            await self.service.review_signal(self.payload())
        self.assertEqual(raised.exception.status, 422)
        self.assertEqual(self.reviewer.signal_calls, [])
        self.assertEqual(self.store.snapshot()["state"], "WAITING_SIGNAL")

    async def test_signal_pending_duplicate_and_cancel_fail_closed(self):
        await self.stopped()
        entered, release = asyncio.Event(), asyncio.Event()

        async def hold():
            entered.set()
            await release.wait()

        self.reviewer.signal_callback = hold
        payload = self.payload()
        pending = asyncio.create_task(self.service.review_signal(payload))
        await asyncio.wait_for(entered.wait(), 2)
        with self.assertRaises(CommandError):
            await self.service.review_signal(payload)
        with self.assertRaises(CommandError):
            await self.service.review_signal(self.payload())
        self.command("cancel")
        release.set()
        result, status = await pending
        self.assertEqual(status, 409)
        self.assertEqual(self.store.snapshot()["state"], "CANCELLED")

    async def test_malformed_signal_and_missing_stop_receipt_cannot_admit_crossing(self):
        await self.stopped()
        self.reviewer.signal_output = {**signal_result("GREEN"), "visible": False}
        response, status = await self.service.review_signal(self.payload())
        self.assertEqual(status, 502)
        self.assertEqual(self.store.snapshot()["state"], "WAITING_SIGNAL")
        with self.store._lock, self.store._db:
            state = self.store._load()
            state.pop("stop_receipt")
            self.store._save(state)
        with self.assertRaises(CommandError):
            await self.service.review_signal(self.payload())
        self.assertEqual(len(self.reviewer.signal_calls), 1)

    async def test_original_evidence_survives_preview_eviction_and_server_restart(self):
        state = await self.plan()
        metadata = state["plan"]["planning"]["frame"]
        original = self.service.frame(metadata["id"])
        self.camera.frames.clear()
        self.assertEqual(self.service.frame(metadata["id"]), original)
        self.store.close()
        self.store = WorkspaceStore(self.path, provider=NeverTextProvider(), map_definition=self.camera.map)
        reopened = LiveIntelligenceService(self.store, self.camera, planning_provider=self.planner, review_provider=self.reviewer)
        self.assertEqual(reopened.frame(metadata["id"]), original)
        self.assertFalse(reopened.operations()["motion_authority"])
        self.assertFalse(self.store.snapshot()["approved"])

    async def test_restart_invalidates_pending_operation_without_provider_dispatch(self):
        payload = self.payload(text="School")
        with self.store._lock, self.store._db:
            state = self.store._load()
            state["planning_pending"] = {"request_id": payload["request_id"], "source": "meta"}
            self.service._reserve("live-plans", payload, {"test": "pending fixture"})
            self.store._save(state)
        replacement = LiveIntelligenceService(self.store, self.camera, planning_provider=self.planner, review_provider=self.reviewer)
        result, status = await replacement.plan(payload)
        self.assertEqual(status, 409)
        self.assertNotIn("planning_pending", self.store.snapshot())
        self.assertEqual(self.planner.calls, [])
        self.assertEqual(replacement.operations()["operations"][0]["status"], "interrupted")

    async def test_voice_original_and_operator_edited_goal_preserved(self):
        self.service.voice = VoiceService(provider=object())
        state = self.store.snapshot()
        definition = self.store.map_definition
        receipt = {"transcript_id": str(uuid4()), "text": "학교로 가줘.", "audio_source": "recorded_upload"}
        binding = {"session_id": state["session_id"], "workspace_revision": state["revision"],
                   "map": {"id": definition.id, "version": definition.version, "geometry_hash": definition.geometry_hash}}
        self.service.voice.remember_transcript(receipt, binding)
        result, status = await self.service.plan(self.payload(text="학교로 왼쪽 도로를 통해 가줘.", source="voice", transcript_id=receipt["transcript_id"]))
        self.assertEqual(status, 200, result)
        self.assertEqual(result["goal"]["voice_receipt"]["original_text"], "학교로 가줘.")
        self.assertEqual(result["goal"]["voice_receipt"]["confirmed_text"], "학교로 왼쪽 도로를 통해 가줘.")
        self.assertEqual(result["goal"]["source"], "voice")
        self.assertFalse(result["approved"])


if __name__ == "__main__":
    unittest.main()
