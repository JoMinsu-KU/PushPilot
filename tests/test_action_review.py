"""Offline recorded-pair review tests using original, code-drawn fixtures only."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient

from backend.action_review import ActionReviewService, MetaActionReviewProvider, PROMPT_VERSION, SCHEMA_VERSION
from backend.app import create_app
from backend.core import CommandError, WorkspaceStore
from backend.maps import MapDefinition
from backend.scene import SceneError, SceneStore
from backend.settings import Settings


def fixture(position=10):
    image = np.full((64, 96, 3), 220, dtype=np.uint8)
    cv2.rectangle(image, (position, 24), (position + 16, 38), (40, 60, 180), -1)
    success, encoded = cv2.imencode(".png", image)
    assert success
    return encoded.tobytes()


def verdict(value="PASS"):
    return {"verdict": value, "observed": "The depicted test object changed position between the recordings.",
            "summary": "The recorded visual expectation is supported.", "limitations": ["Synthetic recordings; no physical motion or freshness is established."]}


class NoGoalProvider:
    def interpret(self, _text):
        raise AssertionError("These tests must not request goal interpretation.")


class ActionReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "workspace.sqlite3")
        self.store = WorkspaceStore(self.path, provider=NoGoalProvider())
        self.addCleanup(lambda: self.store.close())
        self.scene = SceneStore(Path(self.directory.name) / "scene", self.store.map_definition)
        self.calls = []
        self.output = verdict()

        async def provider(inputs):
            self.calls.append(deepcopy(inputs))
            return self.output
        self.provider = provider
        self.service = ActionReviewService(self.store, self.scene, provider=provider)
        self.prepare()
        self.frames()

    def command(self, action, **extra):
        response, status = self.store.execute(action, {"request_id": str(uuid4()), "expected_revision": self.store.snapshot()["revision"], **extra})
        self.assertEqual(status, 200)
        return response

    def prepare(self):
        state = self.command("goals", text="Bakery", provider="demo")
        self.command("approve", plan_id=state["plan"]["id"], plan_revision=state["plan"]["revision"])
        return self.command("advance")

    def frames(self):
        self.before = self.scene.ingest(fixture(), source="recorded")["frame"]
        self.after = self.scene.ingest(fixture(52), captured_at="2026-10-27T12:00:00+09:00")["frame"]

    def payload(self, **extra):
        state, scene = self.store.snapshot(), self.scene.snapshot()
        return {"request_id": str(uuid4()), "expected_revision": state["revision"], "review_id": state["review"]["id"],
                "expected_scene_revision": scene["revision"], "before_frame_id": self.before["id"], "after_frame_id": self.after["id"],
                "expected_visual": "Synthetic evaluation: compare the depicted test object's positions.", **extra}

    async def test_pass_changes_only_simulation_and_persists_bound_evidence(self):
        original = self.store.snapshot()
        self.output = {"result": verdict(), "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}}
        state, status = await self.service.review(self.payload())
        self.assertEqual(status, 200)
        self.assertEqual((state["state"], state["current_step"]), ("READY", 1))
        evidence = state["review"]["evidence"]
        self.assertEqual(evidence["action_id"], original["plan"]["steps"][0]["id"])
        self.assertEqual(evidence["review_id"], original["review"]["id"])
        self.assertEqual(evidence["before"]["captured_at"], None)
        self.assertEqual(evidence["before"]["timestamp_source"], "unknown")
        self.assertEqual(evidence["after"]["timestamp_source"], "operator_provided")
        self.assertEqual(evidence["before"]["source"], "recorded")
        self.assertEqual(evidence["after"]["source"], "uploaded")
        self.assertEqual(evidence["map_version"], self.store.map_definition.version)
        self.assertEqual(evidence["prompt_version"], PROMPT_VERSION)
        self.assertEqual(evidence["schema_version"], SCHEMA_VERSION)
        self.assertEqual(evidence["usage"]["total_tokens"], 130)
        self.assertGreaterEqual(evidence["elapsed_ms"], 0)
        self.assertFalse(evidence["motion_authority"])
        self.assertTrue(evidence["simulation_only"])
        self.assertFalse(state["capabilities"]["robot"])
        self.assertTrue(state["capabilities"]["recorded_action_review"])
        self.assertEqual(state["events"][-1]["record"], evidence)
        self.store.close()
        self.store = WorkspaceStore(self.path, provider=NoGoalProvider())
        self.assertEqual(self.store.snapshot()["events"][-2]["record"], evidence)

    async def test_failed_and_uncertain_reviews_inhibit_continuation(self):
        for output, expected in (("FAIL", "FAULT"), ("UNKNOWN", "REOBSERVE"), ("REOBSERVE", "REOBSERVE")):
            with self.subTest(output=output):
                self.output = verdict(output)
                state, status = await self.service.review(self.payload())
                self.assertEqual(status, 200)
                self.assertEqual(state["state"], expected)
                self.assertEqual(state["current_step"], 0)
                self.assertIsNone(state["review"]["evidence"]["usage"])
                with self.assertRaises(CommandError):
                    self.command("advance")
                if expected == "REOBSERVE":
                    old = state["review"]["id"]
                    state = self.command("reobserve")
                    self.assertNotEqual(state["review"]["id"], old)
                else:
                    self.command("reset")
                    self.prepare()

    async def test_stop_review_needs_local_stop_and_fresh_scoped_green(self):
        await self.service.review(self.payload())
        self.command("advance")
        self.command("signal", color="RED", junction_id="C")
        state, _ = await self.service.review(self.payload())
        self.assertEqual((state["state"], state["current_step"]), ("WAITING_SIGNAL", 1))
        self.assertTrue(state["stopped"])
        self.assertFalse(state["review"]["evidence"]["motion_authority"])
        state = self.command("signal", color="GREEN", junction_id="C")
        self.assertEqual((state["state"], state["current_step"]), ("REVIEW_REQUIRED", 2))
        self.assertEqual(state["review"]["source"], "demo")
        self.assertTrue(any(event.get("record", {}).get("server_action", {}).get("kind") == "STOP" for event in state["events"]))

    async def test_identical_request_replays_original_receipt_without_dispatch(self):
        payload = self.payload()
        first = await self.service.review(payload)
        self.command("advance")
        self.assertEqual(await self.service.review(payload), first)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(CommandError):
            await self.service.review({**payload, "expected_visual": "different"})

    async def test_provider_failure_is_sanitized_idempotent_and_does_not_advance(self):
        async def failure(_inputs):
            self.calls.append(True)
            raise RuntimeError("secret-token and private internal URL")
        self.service = ActionReviewService(self.store, self.scene, provider=failure)
        before = self.store.snapshot()
        payload = self.payload()
        response, status = await self.service.review(payload)
        self.assertEqual(status, 502)
        self.assertNotIn("secret-token", json.dumps(response))
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(await self.service.review(payload), (response, status))
        self.assertEqual(len(self.calls), 1)

    async def test_malformed_schema_and_missing_configuration_fail_closed(self):
        before = self.store.snapshot()
        self.output = {**verdict(), "robot_commands": ["move"]}
        self.assertEqual((await self.service.review(self.payload()))[1], 502)
        self.assertEqual(self.store.snapshot(), before)
        unconfigured = ActionReviewService(self.store, self.scene)
        self.assertEqual((await unconfigured.review(self.payload()))[1], 503)
        self.assertEqual(self.store.snapshot(), before)

    async def test_same_frame_same_bytes_or_wrong_current_after_rejected_without_dispatch(self):
        for command in (self.payload(before_frame_id=self.after["id"]), self.payload(after_frame_id=self.before["id"])):
            with self.assertRaises(SceneError):
                await self.service.review(command)
        self.after = self.scene.ingest(fixture())["frame"]
        with self.assertRaises(SceneError) as raised:
            await self.service.review(self.payload())
        self.assertEqual(raised.exception.code, "PAIR_IDENTICAL")
        self.assertEqual(self.calls, [])

    async def test_missing_map_version_old_frame_and_tampered_image_are_rejected(self):
        metadata_path = self.scene.directory / "frames" / f"{self.before['id']}.json"
        metadata = json.loads(metadata_path.read_text())
        metadata.pop("map_version")
        metadata_path.write_text(json.dumps(metadata))
        with self.assertRaises(SceneError) as raised:
            await self.service.review(self.payload())
        self.assertEqual(raised.exception.code, "FRAME_MAP")
        self.frames()
        path, _ = self.scene.frame_file(self.before["id"])
        path.write_bytes(fixture(30))
        with self.assertRaises(SceneError) as raised:
            await self.service.review(self.payload())
        self.assertEqual(raised.exception.code, "FRAME_INTEGRITY")
        self.assertEqual(self.calls, [])

    async def test_late_response_after_cancel_is_discarded_and_locks_are_free(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(_inputs):
            self.assertFalse(self.store._lock._is_owned())
            self.assertFalse(self.scene._lock._is_owned())
            entered.set()
            await release.wait()
            return verdict()
        self.service = ActionReviewService(self.store, self.scene, provider=delayed)
        payload = self.payload()
        task = asyncio.create_task(self.service.review(payload))
        await entered.wait()
        with self.assertRaises(CommandError):
            await self.service.review(payload)
        with self.assertRaises(CommandError):
            await self.service.review(self.payload())
        cancelled = self.command("cancel")
        release.set()
        response, status = await task
        self.assertEqual(status, 409)
        self.assertEqual(self.store.snapshot(), cancelled)
        self.assertEqual(await self.service.review(payload), (response, status))

    async def test_new_frame_or_reobserve_or_map_replacement_rejects_late_result(self):
        for change in ("frame", "reobserve", "map"):
            with self.subTest(change=change):
                entered, release = asyncio.Event(), asyncio.Event()
                async def delayed(_inputs):
                    entered.set()
                    await release.wait()
                    return verdict()
                self.service = ActionReviewService(self.store, self.scene, provider=delayed)
                task = asyncio.create_task(self.service.review(self.payload()))
                await entered.wait()
                if change == "frame":
                    self.after = self.scene.ingest(fixture(60))["frame"]
                elif change == "reobserve":
                    self.command("reviews", review_id=self.store.snapshot()["review"]["id"], verdict="REOBSERVE")
                    self.command("reobserve")
                else:
                    self.store.map_definition.version = "replaced-version"
                current = self.store.snapshot()
                release.set()
                self.assertEqual((await task)[1], 409)
                self.assertEqual(self.store.snapshot(), current)

    async def test_absolute_timeout_releases_reservation_without_state_change(self):
        async def slow(_inputs):
            await asyncio.Event().wait()
        service = ActionReviewService(self.store, self.scene, provider=slow, timeout_seconds=0.02)
        before = self.store.snapshot()
        self.assertEqual((await service.review(self.payload()))[1], 502)
        self.assertEqual(self.store.snapshot(), before)

    async def test_interrupted_reservation_cannot_be_redispatched_after_restart(self):
        payload = self.payload()
        self.service._prepare(payload, self.service._digest(payload))
        self.store.close()
        self.store = WorkspaceStore(self.path, provider=NoGoalProvider())
        service = ActionReviewService(self.store, self.scene, provider=self.provider)
        response, status = await service.review(payload)
        self.assertEqual(status, 409)
        self.assertIn("interrupted", response["detail"])
        self.assertEqual(self.calls, [])


class ActionReviewApiTests(unittest.TestCase):
    def test_http_command_injection_validation_and_private_frame_lookup(self):
        calls = []
        async def provider(inputs):
            calls.append(inputs)
            return verdict("REOBSERVE")
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Settings(db_path=str(Path(directory) / "state.sqlite3")), provider=NoGoalProvider(), action_review_provider=provider)
            with TestClient(app) as client:
                def command(endpoint, **extra):
                    return client.post("/api/v1/" + endpoint, json={"request_id": str(uuid4()), "expected_revision": client.get("/api/v1/state").json()["revision"], **extra})
                goal = command("goals", text="Bakery", provider="demo").json()
                command("approve", plan_id=goal["plan"]["id"], plan_revision=goal["plan"]["revision"])
                state = command("advance").json()
                before = client.post("/api/v1/scene/frames", files={"file": ("before.png", fixture(), "image/png")}).json()["frame"]
                scene = client.post("/api/v1/scene/frames", files={"file": ("after.png", fixture(52), "image/png")}).json()
                values = {"review_id": state["review"]["id"], "expected_scene_revision": scene["revision"], "before_frame_id": before["id"],
                          "after_frame_id": scene["frame"]["id"], "expected_visual": "Compare these synthetic fixtures."}
                for changed in ({"expected_scene_revision": True}, {"before_frame_id": "../../private"}, {"robot_command": "move"}):
                    self.assertEqual(command("action-reviews", **{**values, **changed}).status_code, 422)
                response = command("action-reviews", **values)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["state"], "REOBSERVE")
                self.assertEqual(len(calls), 1)
                self.assertEqual(client.get(before["image_url"]).content, fixture())


class ActionReviewProviderTests(unittest.IsolatedAsyncioTestCase):
    def inputs(self):
        return {"before": {"data": b"before", "mime": "image/png", "metadata": {"source": "recorded"}},
                "after": {"data": b"after", "mime": "image/png", "metadata": {"source": "uploaded"}},
                "expected_visual": "Synthetic comparison", "server_action": {"kind": "STOP"}, "map": {"map_id": "test"}}

    async def call(self, envelope, status=200):
        requests = []
        real_client = httpx.AsyncClient
        def respond(request):
            requests.append(request)
            return httpx.Response(status, json=envelope)
        with patch("backend.action_review.httpx.AsyncClient", side_effect=lambda **options: real_client(transport=httpx.MockTransport(respond), **options)):
            result = await MetaActionReviewProvider("test-only-key")(self.inputs())
        return result, requests

    async def test_two_images_strict_schema_versions_and_reported_usage(self):
        result, requests = await self.call({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(verdict())}}], "usage": {"prompt_tokens": 50, "total_tokens": 70}})
        self.assertEqual(result["usage"], {"prompt_tokens": 50, "completion_tokens": None, "total_tokens": 70})
        payload = json.loads(requests[0].content)
        self.assertEqual(str(requests[0].url), "https://api.meta.ai/v1/chat/completions")
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        images = [item for item in payload["messages"][1]["content"] if item["type"] == "image_url"]
        self.assertEqual(len(images), 2)
        self.assertIn("YmVmb3Jl", images[0]["image_url"]["url"])
        self.assertIn("YWZ0ZXI=", images[1]["image_url"]["url"])
        self.assertIn("still-image pair cannot prove a robot is stopped", payload["messages"][0]["content"])

    async def test_refusal_truncation_invalid_content_http_failure_are_sanitized(self):
        for envelope, status in (({"choices": [{"finish_reason": "length", "message": {"content": json.dumps(verdict())}}]}, 200),
                                 ({"choices": [{"finish_reason": "stop", "message": {"refusal": "private detail"}}]}, 200),
                                 ({"choices": [{"finish_reason": "stop", "message": {"content": "private invalid"}}]}, 200),
                                 ({"private": "secret upstream"}, 401)):
            with self.subTest(envelope=envelope):
                with self.assertRaises(SceneError) as raised:
                    await self.call(envelope, status)
                self.assertNotIn("private", str(raised.exception))
                self.assertNotIn("secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
