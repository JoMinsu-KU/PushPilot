"""Temporary drawing routing and independent junction admission gates."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from backend.core import CommandError, WorkspaceStore
from backend.maps import MapDefinition


class NeverProvider:
    def interpret(self, _text):
        raise AssertionError("Temporary-map tests must not contact a provider.")


class TemporaryMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.map = MapDefinition()
        self.path = str(self.root / "workspace.sqlite3")
        self.store = WorkspaceStore(self.path, provider=NeverProvider(), map_definition=self.map)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def command(self, action, **extra):
        response, status = self.store.execute(action, {"request_id": str(uuid4()), "expected_revision": self.store.snapshot()["revision"], **extra})
        self.assertEqual(status, 200)
        return response

    def review(self, verdict="PASS"):
        return self.command("reviews", review_id=self.store.snapshot()["review"]["id"], verdict=verdict)

    def prepare(self, destination="BAKERY"):
        state = self.command("goals", text=f"Push to {destination}", provider="demo")
        return self.command("approve", plan_id=state["plan"]["id"], plan_revision=state["plan"]["revision"])

    def first_stop(self):
        self.prepare()
        self.command("advance")
        self.review()
        self.command("advance")
        return self.review()

    def changed_map(self):
        data = self.map.data
        data["board"]["road_width_mm"] += 1
        path = self.root / "changed-map.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return MapDefinition(path)

    def test_expected_east_facing_shortest_routes_and_distances(self):
        for destination, nodes, length in (
            ("BAKERY", ["PIZZA", "C", "S", "BAKERY"], 232),
            ("BOOKSTORE", ["PIZZA", "C", "BOOKSTORE"], 148),
            ("SCHOOL", ["PIZZA", "C", "S", "SCHOOL"], 232),
        ):
            with self.subTest(destination=destination):
                route = self.map.route(destination)
                self.assertEqual(route["node_ids"], nodes)
                self.assertEqual(route["distance_mm"], length)
                self.assertFalse(route["physical_execution_enabled"])
                self.assertEqual(route["map_hash"], self.map.geometry_hash)

    def test_unsupported_destination_and_start_are_not_routes(self):
        for destination in ("PIZZA", "HOSPITAL", ""):
            with self.assertRaises(ValueError):
                self.map.route(destination)

    def test_geometry_hash_ignores_display_metadata_but_detects_geometry_change(self):
        data = self.map.data
        data["title"] = "Another display title"
        data["source"]["adaptation"] = "Changed documentation only"
        data["nodes"].reverse()
        data["edges"].reverse()
        path = self.root / "reordered-map.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(MapDefinition(path).geometry_hash, self.map.geometry_hash)
        self.assertNotEqual(self.changed_map().geometry_hash, self.map.geometry_hash)

    def test_bad_edge_geometry_and_duplicate_marker_are_rejected(self):
        for mutation in ("length", "marker"):
            data = self.map.data
            if mutation == "length":
                data["edges"][0]["length_mm"] = 1
            else:
                data["markers"][1]["id"] = data["markers"][0]["id"]
            path = self.root / f"invalid-{mutation}.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                MapDefinition(path)

    def test_marker_dictionary_and_ids_match_the_installed_detector(self):
        for mutation in ("dictionary", "negative_id", "out_of_dictionary_id"):
            data = self.map.data
            if mutation == "dictionary":
                data["marker_dictionary"] = "DICT_6X6_250"
            else:
                data["markers"][0]["id"] = -1 if mutation == "negative_id" else 50
            path = self.root / f"invalid-{mutation}.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                MapDefinition(path)

    def test_route_steps_include_turns_and_a_stop_at_every_junction(self):
        bakery = self.command("goals", text="빵집으로", provider="demo")
        steps = bakery["plan"]["steps"]
        self.assertEqual(len(steps), 8)
        self.assertEqual([step["node_id"] for step in steps if step["kind"] == "STOP"], ["C", "S"])
        self.assertIn("right", steps[2]["description"])
        self.assertIn("left", steps[5]["description"])
        school = self.command("goals", text="학교로", provider="demo")
        self.assertIn("right", school["plan"]["steps"][5]["description"])
        bookstore = self.command("goals", text="서점으로", provider="demo")
        self.assertEqual(len(bookstore["plan"]["steps"]), 5)
        self.assertIn("straight", bookstore["plan"]["steps"][2]["description"])

    def test_prior_junction_green_and_stop_cannot_authorize_next_junction(self):
        self.first_stop()
        crossed = self.command("signal", color="GREEN", junction_id="C")
        self.assertEqual(crossed["current_step"], 2)
        state = self.review()
        self.assertFalse(state["stopped"])
        self.assertEqual(state["signal"]["color"], "UNKNOWN")
        self.command("advance")
        self.review()
        self.command("advance")
        state = self.review()
        self.assertEqual(state["state"], "WAITING_SIGNAL")
        self.assertEqual(state["plan"]["steps"][state["current_step"]]["node_id"], "S")
        with self.assertRaises(CommandError):
            self.command("signal", color="GREEN", junction_id="C")
        self.assertEqual(self.command("signal", color="RED", junction_id="S")["state"], "WAITING_SIGNAL")
        state = self.command("signal", color="GREEN", junction_id="S")
        self.assertEqual(state["current_step"], 5)
        self.assertEqual(state["state"], "REVIEW_REQUIRED")
        self.assertEqual(sum(event["kind"] == "CROSSING_ADMITTED" for event in state["events"]), 2)

    def test_green_before_second_stop_still_requires_stop_and_review(self):
        self.first_stop()
        self.command("signal", color="GREEN")
        self.review()
        self.command("signal", color="GREEN", junction_id="S")
        self.command("advance")
        self.review()
        state = self.command("advance")
        self.assertEqual(state["current_step"], 4)
        self.assertTrue(state["stopped"])
        self.assertEqual(state["state"], "REVIEW_REQUIRED")
        self.assertEqual(sum(event["kind"] == "CROSSING_ADMITTED" for event in state["events"]), 1)
        self.assertEqual(self.review()["current_step"], 5)

    def test_map_change_invalidates_approval_and_advance(self):
        state = self.command("goals", text="bakery", provider="demo")
        self.store.map_definition = self.changed_map()
        with self.assertRaises(CommandError):
            self.command("approve", plan_id=state["plan"]["id"], plan_revision=state["plan"]["revision"])
        self.store.map_definition = self.map
        self.command("approve", plan_id=state["plan"]["id"], plan_revision=state["plan"]["revision"])
        self.store.map_definition = self.changed_map()
        with self.assertRaises(CommandError):
            self.command("advance")

    def test_map_change_while_waiting_inhibits_automatic_crossing(self):
        self.first_stop()
        self.store.map_definition = self.changed_map()
        with self.assertRaises(CommandError):
            self.command("signal", color="GREEN")
        self.assertEqual(self.store.snapshot()["state"], "WAITING_SIGNAL")

    def test_legacy_unmapped_plan_cannot_survive_as_an_approvable_plan(self):
        self.command("goals", text="bakery", provider="demo")
        self.store.close()
        with sqlite3.connect(self.path) as connection:
            state = json.loads(connection.execute("SELECT value FROM workspace WHERE id=1").fetchone()[0])
            del state["plan"]["route"]
            connection.execute("UPDATE workspace SET value=? WHERE id=1", (json.dumps(state),))
        connection.close()
        self.store = WorkspaceStore(self.path, provider=NeverProvider(), map_definition=self.map)
        state = self.store.snapshot()
        self.assertEqual(state["state"], "IDLE")
        self.assertIsNone(state["plan"])
        self.assertEqual(state["events"][-1]["kind"], "PLAN_INVALIDATED")

    def test_changed_map_after_restart_discards_prepared_plan(self):
        self.command("goals", text="bakery", provider="demo")
        self.store.close()
        self.store = WorkspaceStore(self.path, provider=NeverProvider(), map_definition=self.changed_map())
        self.assertEqual(self.store.snapshot()["state"], "IDLE")
        self.assertIsNone(self.store.snapshot()["plan"])


if __name__ == "__main__":
    unittest.main()
