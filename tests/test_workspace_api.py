"""HTTP contract checks using injected settings; never load the real .env."""
from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.meta import MetaGoalProvider, ProviderError
from backend.settings import Settings
import httpx


class OfflineProvider:
    def interpret(self, _text):
        raise ProviderError("Offline test provider.")


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = Settings(db_path=str(self.root / "workspace.sqlite3"), frontend_dist=str(self.root / "dist"))
        self.app = create_app(settings=self.settings, provider=OfflineProvider())
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def command(self, endpoint, **extra):
        revision = self.client.get("/api/v1/state").json()["revision"]
        return self.client.post(f"/api/v1/{endpoint}", json={"request_id": str(uuid4()), "expected_revision": revision, **extra})

    def test_health_and_state_report_simulation_without_credentials(self):
        self.assertEqual(self.client.get("/api/health").json()["hardware_connected"], False)
        response = self.client.get("/api/v1/state")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.json()["schema_version"], "pushpilot.workspace.v1")
        self.assertFalse(response.json()["capabilities"]["muse_configured"])

    def test_input_validation_rejects_non_uuid_bad_revision_and_unknown_fields(self):
        for payload in (
            {"request_id": "not-a-uuid", "expected_revision": 0},
            {"request_id": str(uuid4()), "expected_revision": True},
            {"request_id": str(uuid4()), "expected_revision": -1},
            {"request_id": str(uuid4()), "expected_revision": 0, "robot_command": "move"},
        ):
            self.assertEqual(self.client.post("/api/v1/reset", json=payload).status_code, 422)

    def test_symbolic_goal_and_approval_contract(self):
        response = self.command("goals", text="베이커리로 보내줘", provider="demo", source="typed")
        self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertEqual(state["goal"]["destination"], "BAKERY")
        self.assertEqual([step["kind"] for step in state["plan"]["steps"]], ["PUSH", "STOP", "CROSS", "PUSH", "STOP", "CROSS", "PUSH", "VERIFY"])
        self.assertEqual(state["plan"]["route"]["node_ids"], ["PIZZA", "C", "S", "BAKERY"])
        approved = self.command("approve", plan_id=state["plan"]["id"], plan_revision=state["plan"]["revision"])
        self.assertEqual(approved.json()["state"], "READY")
        self.assertEqual(self.command("advance").json()["review"]["source"], "demo")

    def test_temporary_map_and_scene_routes_are_available_without_hardware(self):
        response = self.client.get("/api/v1/map")
        self.assertEqual(response.status_code, 200)
        temporary_map = response.json()
        self.assertTrue(temporary_map["temporary"])
        self.assertFalse(temporary_map["physical_execution_enabled"])
        self.assertEqual(set(temporary_map["destinations"]), {"BAKERY", "BOOKSTORE", "SCHOOL"})
        scene = self.client.get("/api/v1/scene").json()
        self.assertEqual(scene["map_hash"], temporary_map["geometry_hash"])
        self.assertIsNone(scene["frame"])
        self.assertFalse(scene["capabilities"]["robot"])
        self.assertFalse(scene["capabilities"]["live_camera"])

    def test_stale_request_and_reused_id_are_http409(self):
        payload = {"request_id": str(uuid4()), "expected_revision": 0, "text": "bakery", "provider": "demo"}
        first = self.client.post("/api/v1/goals", json=payload)
        self.assertEqual(self.client.post("/api/v1/goals", json=payload).json(), first.json())
        self.assertEqual(self.client.post("/api/v1/goals", json={**payload, "text": "new bakery"}).status_code, 409)
        self.assertEqual(self.client.post("/api/v1/reset", json={"request_id": str(uuid4()), "expected_revision": 0}).status_code, 409)

    def test_failed_actual_provider_never_returns_scripted_goal(self):
        response = self.command("goals", text="bakery", provider="meta")
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(self.client.get("/api/v1/state").json()["plan"])

    def test_voice_source_is_rejected_until_transcription_is_implemented(self):
        response = self.command("goals", text="bakery", provider="demo", source="voice")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/v1/state").json()["state"], "IDLE")

    def test_unknown_api_does_not_fall_through_to_frontend(self):
        self.root.joinpath("dist").mkdir()
        self.root.joinpath("dist", "index.html").write_text("<html>Operator workspace</html>", encoding="utf-8")
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/api/v1/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertEqual(self.client.get("/api").status_code, 404)
        self.assertEqual(self.client.get("/missing.js").status_code, 404)
        self.assertEqual(self.client.get("/workspace").status_code, 200)

    def test_frontend_path_cannot_read_outside_the_build_directory(self):
        self.root.joinpath("dist").mkdir()
        self.root.joinpath("private.txt").write_text("PRIVATE_TEST_VALUE", encoding="utf-8")
        response = self.client.get("/%2e%2e/private.txt")
        self.assertNotIn("PRIVATE_TEST_VALUE", response.text)
        self.assertEqual(response.status_code, 404)

    def test_creating_app_does_not_read_environment_or_initialize_files(self):
        with patch.object(Settings, "from_environment", side_effect=AssertionError("Import-time credential access")):
            application = create_app()
            self.assertIsNotNone(application)


class MetaAdapterTests(unittest.TestCase):
    def test_unconfigured_provider_rejects_without_network(self):
        with self.assertRaises(ProviderError):
            MetaGoalProvider("").interpret("bakery")

    def test_strict_schema_request_is_bounded_and_validated(self):
        answer = {"destination": "BAKERY", "summary": "Push to symbolic BAKERY.", "requires_clarification": False}
        response = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})
        with patch("backend.meta.httpx.Client") as factory:
            factory.return_value.__enter__.return_value.post.return_value = response
            result = MetaGoalProvider("unit-test-key").interpret("bakery")
        self.assertEqual(result, answer)
        kwargs = factory.call_args.kwargs
        self.assertFalse(kwargs["follow_redirects"])
        self.assertEqual(kwargs["timeout"].connect, 5.0)
        self.assertEqual(kwargs["timeout"].read, 20.0)
        call = factory.return_value.__enter__.return_value.post.call_args
        self.assertEqual(call.args[0], "https://api.meta.ai/v1/chat/completions")
        body = call.kwargs["json"]
        self.assertEqual(body["model"], "muse-spark-1.3")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        schema = body["response_format"]["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertFalse(schema["schema"]["additionalProperties"])
        self.assertEqual(set(schema["schema"]["required"]), {"destination", "summary", "requires_clarification"})

    def test_provider_http_failure_does_not_expose_upstream_content(self):
        response = httpx.Response(401, text="unit-test-key private upstream details")
        with patch("backend.meta.httpx.Client") as factory:
            factory.return_value.__enter__.return_value.post.return_value = response
            with self.assertRaises(ProviderError) as failure:
                MetaGoalProvider("unit-test-key").interpret("bakery")
        self.assertNotIn("unit-test-key", str(failure.exception))
        self.assertNotIn("private upstream", str(failure.exception))

    def test_provider_timeout_is_sanitized(self):
        with patch("backend.meta.httpx.Client") as factory:
            factory.return_value.__enter__.return_value.post.side_effect = httpx.ReadTimeout("unit-test-key")
            with self.assertRaises(ProviderError) as failure:
                MetaGoalProvider("unit-test-key").interpret("bakery")
        self.assertNotIn("unit-test-key", str(failure.exception))

    def test_malformed_or_inconsistent_provider_result_is_rejected(self):
        contents = ["not-json", json.dumps({"destination": "HOSPITAL", "summary": "Other target.", "requires_clarification": False}),
                    json.dumps({"destination": "UNKNOWN", "summary": "Unclear.", "requires_clarification": False})]
        for content in contents:
            with self.subTest(content=content), patch("backend.meta.httpx.Client") as factory:
                factory.return_value.__enter__.return_value.post.return_value = httpx.Response(
                    200, json={"choices": [{"message": {"content": content}}]})
                with self.assertRaises(ProviderError):
                    MetaGoalProvider("unit-test-key").interpret("bakery")


if __name__ == "__main__":
    unittest.main()
