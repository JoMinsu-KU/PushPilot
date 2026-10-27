"""Explicit model-selected graph paths and reviewed signal-region metadata."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest

from backend.maps import MapDefinition


FIXTURE = Path(__file__).parent / "fixtures" / "harbor-map.json"


class PlanningRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.map = MapDefinition()

    def tearDown(self):
        self.temp.cleanup()

    def changed(self, data):
        path = self.root / "map.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return MapDefinition(path)

    @staticmethod
    def constraints(**values):
        return {"departure": "any", "first_turn": "any", "via_nodes": [], "avoid_nodes": [], **values}

    def test_planning_context_enumerates_directed_topology_without_pose_or_metric_targets(self):
        context = self.map.planning_context()
        self.assertEqual(context["map_hash"], self.map.geometry_hash)
        self.assertEqual(context["map_id"], self.map.id)
        self.assertEqual(context["map_version"], self.map.version)
        self.assertEqual(context["destinations"], ["BAKERY", "BOOKSTORE", "SCHOOL"])
        self.assertEqual(context["max_route_nodes"], 64)
        self.assertFalse(context["physical_execution_enabled"])
        self.assertFalse(context["declared_start"]["measured_pose"])
        self.assertFalse(context["declared_start"]["departure_restricted_to_configured_heading"])
        self.assertEqual(context["declared_start"]["node_id"], "PIZZA")
        self.assertEqual(context["orientation"]["turn_reference"], "incoming_path_direction")
        edges = {(edge["from"], edge["to"]): edge["map_direction"] for edge in context["directed_edges"]}
        self.assertEqual(len(edges), 32)
        self.assertEqual(edges["PIZZA", "W"], "west")
        self.assertEqual(edges["W", "PIZZA"], "east")
        nodes = {node["id"]: node for node in context["nodes"]}
        self.assertEqual(nodes["SCHOOL"]["label"], "School")
        self.assertIn("학교", nodes["SCHOOL"]["aliases"])
        self.assertLess(nodes["W"]["drawing_position"]["column"], nodes["PIZZA"]["drawing_position"]["column"])
        self.assertLess(nodes["NW"]["drawing_position"]["row"], nodes["W"]["drawing_position"]["row"])
        serialized = json.dumps(context)
        for excluded in ("x_mm", "y_mm", "length_mm", "points_mm", "BASE", "TCP"):
            self.assertNotIn(excluded, serialized)
        context["nodes"][0]["aliases"].append("edited")
        self.assertNotIn("edited", json.dumps(self.map.planning_context()))

    def test_exact_west_route_compiles_without_changing_legacy_east_demo(self):
        west = self.map.route_from_nodes("SCHOOL", ["PIZZA", "W", "SW", "SCHOOL"])
        self.assertEqual(west["node_ids"], ["PIZZA", "W", "SW", "SCHOOL"])
        self.assertEqual(west["distance_mm"], 232)
        self.assertEqual(west["points_mm"], [[126, 117], [52, 117], [52, 201], [126, 201]])
        self.assertEqual(west["junction_ids"], ["W", "SW"])
        self.assertFalse(west["physical_execution_enabled"])
        self.assertEqual(west["directions"]["departure"]["map_direction"], "west")
        self.assertEqual([item["turn"] for item in west["directions"]["maneuvers"]], ["left", "left"])
        self.assertEqual(self.map.route("SCHOOL")["node_ids"], ["PIZZA", "C", "S", "SCHOOL"])
        segments = west["visualization"]["segments"]
        self.assertAlmostEqual(sum(item["length_mm"] for item in segments), west["distance_mm"])
        self.assertEqual(segments[0]["points_mm"][0], west["points_mm"][0])
        self.assertEqual(segments[-1]["points_mm"][-1], west["points_mm"][-1])
        for before, after in zip(segments, segments[1:]):
            self.assertEqual(before["points_mm"][-1], after["points_mm"][0])

    def test_longer_route_is_preserved_and_model_prose_cannot_change_turns(self):
        nodes = ["PIZZA", "C", "N", "NW", "W", "SW", "SCHOOL"]
        route = self.map.route_from_nodes("SCHOOL", nodes)
        self.assertEqual(route["node_ids"], nodes)
        self.assertEqual(route["distance_mm"], 548)
        self.assertEqual([item["turn"] for item in route["directions"]["maneuvers"]], ["left", "left", "left", "straight", "left"])
        self.assertTrue(all(item["requires_stop"] for item in route["directions"]["maneuvers"]))
        self.assertIn("Turn left at C", route["directions"]["maneuvers"][0]["description"])
        self.assertEqual(len(route["visualization"]["junctions"]), 5)

    def test_route_rejects_unknown_unconnected_cyclic_truncated_or_post_arrival_paths(self):
        invalid = [
            [], ["PIZZA"], ["W", "SW", "SCHOOL"], ["PIZZA", "W", "SW"],
            ["PIZZA", "SW", "SCHOOL"], ["PIZZA", "W", "PIZZA", "C", "S", "SCHOOL"],
            ["PIZZA", "W", "SW", "SCHOOL", "S"], ["PIZZA", "UNKNOWN", "SCHOOL"],
            ["PIZZA", {"id": "W"}, "SCHOOL"], ["PIZZA", None, "SCHOOL"],
            ("PIZZA", "W", "SW", "SCHOOL"), "PIZZA,W,SW,SCHOOL",
        ]
        for nodes in invalid:
            with self.subTest(nodes=nodes), self.assertRaises(ValueError):
                self.map.route_from_nodes("SCHOOL", nodes)
        for destination in ("UNKNOWN", "PIZZA", None, ["SCHOOL"]):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.map.route_from_nodes(destination, ["PIZZA", "W", "SW", "SCHOOL"])

    def test_one_way_road_is_not_silently_reversed(self):
        data = self.map.data
        data["edges"][5]["bidirectional"] = False  # W -> PIZZA only.
        definition = self.changed(data)
        edges = {(edge["from"], edge["to"]) for edge in definition.planning_context()["directed_edges"]}
        self.assertNotIn(("PIZZA", "W"), edges)
        self.assertIn(("W", "PIZZA"), edges)
        with self.assertRaises(ValueError):
            definition.route_from_nodes("SCHOOL", ["PIZZA", "W", "SW", "SCHOOL"])
        self.assertEqual(definition.route_from_nodes("SCHOOL", ["PIZZA", "C", "S", "SCHOOL"])["distance_mm"], 232)

    def test_constraints_bind_departure_first_junction_and_ordered_via_nodes(self):
        route = self.map.route_from_nodes("SCHOOL", ["PIZZA", "W", "SW", "SCHOOL"])
        constraints = self.constraints(departure="west", first_turn="left", via_nodes=["W", "SW"], avoid_nodes=["C"])
        result = self.map.validate_route_constraints(route, constraints)
        self.assertEqual(result, constraints)
        result["via_nodes"].append("C")
        self.assertEqual(constraints["via_nodes"], ["W", "SW"])
        for values in ({"departure": "east"}, {"first_turn": "right"}, {"first_turn": "straight"},
                       {"via_nodes": ["SW", "W"]}, {"via_nodes": ["C"]}, {"avoid_nodes": ["W"]},
                       {"via_nodes": ["W"], "avoid_nodes": ["W"]}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.map.validate_route_constraints(route, self.constraints(**values))

    def test_constraints_reject_malformed_or_unknown_interpretations_and_map_changes(self):
        route = self.map.route_from_nodes("SCHOOL", ["PIZZA", "W", "SW", "SCHOOL"])
        for constraints in (None, {}, {**self.constraints(), "extra": True},
                            self.constraints(departure="left"), self.constraints(first_turn="west"),
                            self.constraints(departure=[]), self.constraints(first_turn=None),
                            self.constraints(via_nodes="W"), self.constraints(via_nodes=["W", "W"]),
                            self.constraints(avoid_nodes=["MISSING"]), self.constraints(avoid_nodes=[{}])):
            with self.subTest(constraints=constraints), self.assertRaises(ValueError):
                self.map.validate_route_constraints(route, constraints)
        for field in ("map_id", "map_version", "map_hash"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.map.validate_route_constraints({**route, field: "changed"}, self.constraints())

    def test_replacement_map_uses_its_own_graph_labels_and_heading(self):
        definition = MapDefinition(FIXTURE)
        context = definition.planning_context()
        self.assertEqual(context["declared_start"]["node_id"], "DOCK")
        self.assertEqual(context["declared_start"]["configured_heading"], "north")
        self.assertNotIn("PIZZA", json.dumps(context))
        route = definition.route_from_nodes("MUSEUM", ["DOCK", "J_WEST", "J_EAST", "MUSEUM"])
        self.assertEqual(route["distance_mm"], 340)
        self.assertIn("West junction", route["directions"]["maneuvers"][0]["description"])
        self.assertEqual([item["turn"] for item in route["directions"]["maneuvers"]], ["right", "left"])
        definition.validate_route_constraints(route, self.constraints(departure="north", first_turn="right"))

    def test_first_junction_straight_is_distinct_from_first_later_turn(self):
        route = self.map.route_from_nodes("SCHOOL", ["PIZZA", "C", "BOOKSTORE", "E", "SE", "BAKERY", "S", "SCHOOL"])
        self.assertEqual(route["directions"]["maneuvers"][0]["turn"], "straight")
        self.map.validate_route_constraints(route, self.constraints(first_turn="straight"))
        with self.assertRaises(ValueError):
            self.map.validate_route_constraints(route, self.constraints(first_turn="right"))

    def test_route_node_count_is_bounded_before_any_path_search(self):
        with self.assertRaises(ValueError):
            self.map.route_from_nodes("SCHOOL", ["PIZZA"] * 65)


class SignalTargetTests(unittest.TestCase):
    setUp = PlanningRouteTests.setUp
    tearDown = PlanningRouteTests.tearDown
    changed = PlanningRouteTests.changed

    def configured_data(self):
        data = self.map.data
        data["signal_targets"] = [
            {"id": "C-from-PIZZA", "junction_id": "C", "approach_from": "PIZZA",
             "bounds_mm": [174, 90, 184, 100], "description": "Paper signal for the Pizza approach to C."},
            {"id": "S-from-C", "junction_id": "S", "approach_from": "C",
             "bounds_mm": [174, 174, 184, 184], "description": "Paper signal for the C approach to S."},
        ]
        return data

    def test_absent_targets_are_not_inferred_and_empty_metadata_preserves_hash(self):
        self.assertIsNone(self.map.signal_target("C", "PIZZA"))
        self.assertEqual(self.map.snapshot()["signal_targets"], [])
        data = self.map.data
        data["signal_targets"] = []
        self.assertEqual(self.changed(data).geometry_hash, self.map.geometry_hash)

    def test_target_is_approach_specific_copied_and_included_in_map_identity(self):
        data = self.configured_data()
        definition = self.changed(data)
        self.assertNotEqual(definition.geometry_hash, self.map.geometry_hash)
        self.assertEqual(definition.signal_target("C", "PIZZA"), data["signal_targets"][0])
        self.assertIsNone(definition.signal_target("C", "N"))
        self.assertIsNone(definition.signal_target("S", "PIZZA"))
        target = definition.signal_target("C", "PIZZA")
        target["bounds_mm"][0] = 0
        self.assertEqual(definition.signal_target("C", "PIZZA")["bounds_mm"][0], 174)
        data["signal_targets"].reverse()
        self.assertEqual(self.changed(data).geometry_hash, definition.geometry_hash)
        data["signal_targets"][0]["bounds_mm"][0] += 1
        self.assertNotEqual(self.changed(data).geometry_hash, definition.geometry_hash)

    def test_invalid_ambiguous_or_unbound_signal_regions_are_rejected(self):
        mutations = [None, {}, [None], [{"id": "missing"}]]
        for key, value in (("id", ""), ("id", 1), ("junction_id", "PIZZA"), ("junction_id", "UNKNOWN"),
                           ("approach_from", "SW"), ("approach_from", "C"), ("approach_from", []),
                           ("description", ""), ("description", "x" * 501),
                           ("bounds_mm", [0, 0, 0, 10]), ("bounds_mm", [0, 0, 401, 10]),
                           ("bounds_mm", [0, -1, 10, 10]), ("bounds_mm", [0, 0, 10, 251]),
                           ("bounds_mm", [0, 0, math.nan, 10]), ("bounds_mm", [0, 0, True, 10]),
                           ("bounds_mm", [0, 0, 10]), ("bounds_mm", "0,0,10,10")):
            targets = deepcopy(self.configured_data()["signal_targets"])
            targets[0][key] = value
            mutations.append(targets)
        for targets in mutations:
            data = self.map.data
            data["signal_targets"] = targets
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                self.changed(data)
        for duplicate in ("id", "approach"):
            data = self.configured_data()
            if duplicate == "id":
                data["signal_targets"][1]["id"] = data["signal_targets"][0]["id"]
            else:
                data["signal_targets"][1].update(junction_id="C", approach_from="PIZZA")
            with self.subTest(duplicate=duplicate), self.assertRaises(ValueError):
                self.changed(data)

    def test_signal_target_requires_the_road_direction_into_the_junction(self):
        data = self.configured_data()
        data["edges"][6].update({"from": "C", "to": "PIZZA", "bidirectional": False})
        with self.assertRaises(ValueError):
            self.changed(data)


if __name__ == "__main__":
    unittest.main()
