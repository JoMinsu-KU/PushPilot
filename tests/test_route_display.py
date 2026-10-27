"""Map replacement and drawing-only execution-display bindings, without hardware."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core import WorkspaceStore
from backend.maps import MapDefinition
from backend.meta import MetaGoalProvider, ProviderError
from backend.settings import Settings


FIXTURE = Path(__file__).parent / "fixtures" / "harbor-map.json"


class OfflineProvider:
    def interpret(self, _text):
        raise AssertionError("This test does not contact MUSE.")


class RouteDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def changed(self, data):
        path = self.root / f"map-{uuid4()}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return MapDefinition(path)

    @staticmethod
    def command(store, action, **extra):
        result, status = store.execute(action, {"request_id": str(uuid4()), "expected_revision": store.snapshot()["revision"], **extra})
        if status != 200:
            raise AssertionError(result)
        return result

    def test_split_geometry_is_continuous_complete_and_bound_to_steps(self):
        for definition in (MapDefinition(), MapDefinition(FIXTURE)):
            for destination in definition.data["destinations"]:
                route = definition.route(destination)
                display = route["visualization"]
                segments = display["segments"]
                self.assertEqual(display["source"], "drawing_only")
                self.assertEqual(segments[0]["points_mm"][0], route["points_mm"][0])
                self.assertEqual(segments[-1]["points_mm"][-1], route["points_mm"][-1])
                self.assertAlmostEqual(sum(segment["length_mm"] for segment in segments), route["distance_mm"])
                for before, after in zip(segments, segments[1:]):
                    self.assertEqual(before["points_mm"][-1], after["points_mm"][0])
                steps = WorkspaceStore._route_steps(route)
                bindings = [step["route_segment_id"] for step in steps if step["kind"] in {"PUSH", "CROSS"}]
                self.assertEqual(bindings, [segment["id"] for segment in segments])
                self.assertEqual(len(bindings), len(set(bindings)))
                self.assertTrue(all("route_segment_id" not in step for step in steps if step["kind"] in {"STOP", "VERIFY"}))
                by_id = {segment["id"]: segment for segment in segments}
                for junction in display["junctions"]:
                    approach, crossing = by_id[junction["approach_segment_id"]], by_id[junction["crossing_segment_id"]]
                    self.assertEqual(approach["points_mm"][-1], junction["stop_point_mm"])
                    self.assertEqual(crossing["points_mm"], [junction["stop_point_mm"], junction["center_mm"], junction["exit_point_mm"]])
                    line = junction["stop_line_mm"]
                    self.assertAlmostEqual(math.dist(*line), definition.data["board"]["road_width_mm"])

    def test_default_bakery_split_stops_before_both_intersections(self):
        route = MapDefinition().route("BAKERY")
        segments = route["visualization"]["segments"]
        self.assertEqual([segment["points_mm"] for segment in segments], [
            [[126, 117], [181, 117]], [[181, 117], [200, 117], [200, 136]],
            [[200, 136], [200, 182]], [[200, 182], [200, 201], [219, 201]],
            [[219, 201], [274, 201]]])
        self.assertEqual([segment["length_mm"] for segment in segments], [55, 38, 46, 38, 55])

    def test_short_adjacent_edges_do_not_reverse_or_overrun_display_segments(self):
        definition = MapDefinition(FIXTURE)
        data = definition.data
        for node in data["nodes"]:
            if node["id"] in {"J_EAST", "MUSEUM"}:
                node["x_mm"] = 84
        data["edges"][1]["length_mm"] = 4
        data["edges"][4]["length_mm"] = 276
        route = self.changed(data).route("MUSEUM")
        segments = route["visualization"]["segments"]
        self.assertEqual(segments[2]["points_mm"], [[82, 140], [82, 140]])
        self.assertEqual(segments[2]["length_mm"], 0)
        self.assertEqual(len(WorkspaceStore._route_steps(route)), 8)
        self.assertAlmostEqual(sum(segment["length_mm"] for segment in segments), 204)

    def test_metadata_does_not_invalidate_calibration_or_default_east_hash(self):
        definition = MapDefinition()
        data = definition.data
        data["nodes"][0].update(label="A new display label", aliases=["new label"])
        data["start_heading"] = "east"
        self.assertEqual(self.changed(data).geometry_hash, definition.geometry_hash)
        data["start_heading"] = "north"
        self.assertNotEqual(self.changed(data).geometry_hash, definition.geometry_hash)

    def test_segment_identity_is_stable_but_changes_with_map_identity_or_topology(self):
        definition = MapDefinition()
        first = definition.route("BAKERY")["visualization"]["segments"][0]["id"]
        self.assertEqual(first, definition.route("BAKERY")["visualization"]["segments"][0]["id"])
        self.assertNotEqual(first, definition.route("SCHOOL")["visualization"]["segments"][0]["id"])
        data = definition.data
        data["version"] = "new-print"
        self.assertNotEqual(first, self.changed(data).route("BAKERY")["visualization"]["segments"][0]["id"])

    def test_replacement_map_drives_aliases_start_heading_plan_and_signal_scope(self):
        definition = MapDefinition(FIXTURE)
        self.assertEqual(definition.route("MUSEUM")["node_ids"], ["DOCK", "J_WEST", "J_EAST", "MUSEUM"])
        with_store = WorkspaceStore(":memory:", provider=OfflineProvider(), map_definition=definition, signal_ttl_seconds=12)
        try:
            plan = self.command(with_store, "goals", text="Push to the gallery", provider="demo")
            self.assertEqual(plan["goal"]["destination"], "MUSEUM")
            self.assertIn("DOCK", plan["goal"]["summary"])
            self.assertNotIn("PIZZA", plan["goal"]["summary"])
            self.assertEqual(plan["signal"]["freshness_limit_ms"], 12000)
            plan = self.command(with_store, "approve", plan_id=plan["plan"]["id"], plan_revision=plan["plan"]["revision"])
            step = self.command(with_store, "advance")
            self.command(with_store, "reviews", review_id=step["review"]["id"], verdict="PASS")
            step = self.command(with_store, "advance")
            waiting = self.command(with_store, "reviews", review_id=step["review"]["id"], verdict="PASS")
            self.assertEqual(waiting["state"], "WAITING_SIGNAL")
            self.assertEqual(waiting["plan"]["steps"][waiting["current_step"]]["node_id"], "J_WEST")
            admitted = self.command(with_store, "signal", color="GREEN", junction_id="J_WEST")
            self.assertEqual(admitted["state"], "REVIEW_REQUIRED")
            self.assertEqual(admitted["current_step"], 2)
        finally:
            with_store.close()

    def test_old_prepared_plan_is_not_rewritten_with_new_visualization(self):
        path = str(self.root / "workspace.sqlite3")
        store = WorkspaceStore(path, provider=OfflineProvider())
        plan = self.command(store, "goals", text="bakery", provider="demo")
        store.close()
        with sqlite3.connect(path) as connection:
            state = json.loads(connection.execute("SELECT value FROM workspace WHERE id=1").fetchone()[0])
            del state["plan"]["route"]["visualization"]
            for step in state["plan"]["steps"]:
                step.pop("route_segment_id", None)
            connection.execute("UPDATE workspace SET value=? WHERE id=1", (json.dumps(state),))
        connection.close()
        store = WorkspaceStore(path, provider=OfflineProvider())
        try:
            restored = store.snapshot()
            self.assertEqual(restored["plan"]["id"], plan["plan"]["id"])
            self.assertNotIn("visualization", restored["plan"]["route"])
            self.assertTrue(all("route_segment_id" not in step for step in restored["plan"]["steps"]))
        finally:
            store.close()

    def test_invalid_heading_and_unbounded_aliases_are_rejected(self):
        for key, value in (("start_heading", "diagonal"), ("start_heading", None)):
            data = MapDefinition(FIXTURE).data
            data[key] = value
            with self.assertRaises(ValueError):
                self.changed(data)
        data = MapDefinition(FIXTURE).data
        data["nodes"][0]["aliases"] = ["alias"] * 21
        with self.assertRaises(ValueError):
            self.changed(data)

    def test_meta_schema_and_prompt_are_scoped_to_replacement_map(self):
        definition = MapDefinition(FIXTURE)
        answer = {"destination": "MUSEUM", "summary": "Push from Dock to City Museum.", "requires_clarification": False}
        with patch("backend.meta.httpx.Client") as factory:
            post = factory.return_value.__enter__.return_value.post
            post.return_value = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})
            self.assertEqual(MetaGoalProvider("test-only", definition).interpret("gallery"), answer)
            body = post.call_args.kwargs["json"]
            self.assertEqual(body["response_format"]["json_schema"]["schema"]["properties"]["destination"]["enum"], ["MUSEUM", "GARDEN", "MARKET", "CLINIC", "UNKNOWN"])
            prompt = body["messages"][0]["content"]
            self.assertIn('"start": {"id": "DOCK"', prompt)
            self.assertIn('"aliases": ["gallery"]', prompt)
            self.assertNotIn("x_mm", prompt)
            self.assertNotIn("PIZZA", prompt)
            post.return_value = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({**answer, "destination": "BAKERY"})}}]})
            with self.assertRaises(ProviderError):
                MetaGoalProvider("test-only", definition).interpret("bakery")

    def test_api_wires_same_replacement_map_to_provider_planner_and_scene(self):
        settings = Settings(db_path=":memory:", map_path=str(FIXTURE), meta_api_key="test-only")
        answer = {"destination": "GARDEN", "summary": "Push from Dock to Garden.", "requires_clarification": False}
        with TestClient(create_app(settings=settings, live_camera_url="")) as client:
            temporary_map = client.get("/api/v1/map").json()
            scene = client.get("/api/v1/scene").json()
            self.assertEqual(temporary_map["board"]["width_mm"], 600)
            self.assertEqual(temporary_map["start_heading"], "north")
            self.assertEqual(scene["map_hash"], temporary_map["geometry_hash"])
            with patch("backend.meta.httpx.Client") as factory:
                post = factory.return_value.__enter__.return_value.post
                post.return_value = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})
                response = client.post("/api/v1/goals", json={"request_id": str(uuid4()), "expected_revision": 0,
                                      "text": "Push to the park", "provider": "meta"})
                self.assertEqual(response.status_code, 200)
                plan = response.json()["plan"]
                self.assertEqual(plan["route"]["node_ids"], ["DOCK", "J_WEST", "GARDEN"])
                self.assertEqual(plan["route"]["map_hash"], temporary_map["geometry_hash"])
                self.assertEqual(plan["steps"][0]["route_segment_id"], plan["route"]["visualization"]["segments"][0]["id"])
                enum = post.call_args.kwargs["json"]["response_format"]["json_schema"]["schema"]["properties"]["destination"]["enum"]
                self.assertEqual(enum[:-1], temporary_map["destinations"])


if __name__ == "__main__":
    unittest.main()
