"""Nominal A3 city drawing, independent from historical Little Town geometry."""
from __future__ import annotations

import math
from pathlib import Path
import unittest

from backend.core import WorkspaceStore
from backend.maps import DEFAULT_MAP, MapDefinition


CITY_MAP = Path(__file__).resolve().parents[1] / "backend" / "data" / "seoul-city-a3.json"
SOURCE_HASH = "87c06c120864965ad85fb4653e375058db28307db40af47ef4c00d29b8368003"


class CityA3MapTests(unittest.TestCase):
    def setUp(self):
        self.definition = MapDefinition(CITY_MAP)
        self.data = self.definition.data

    def test_replacement_is_separate_nominal_a3_and_preserves_legacy_default(self):
        self.assertEqual(self.definition.id, "seoul-city-a3")
        self.assertEqual(self.data["source"]["sha256"], SOURCE_HASH)
        self.assertEqual(self.data["source"]["image_size_px"], [2400, 1697])
        self.assertEqual(self.data["page"], {"width_mm": 420, "height_mm": 297,
                                             "board_origin_page_mm": [0, 0]})
        self.assertEqual([self.data["board"]["width_mm"], self.data["board"]["height_mm"]], [420, 297])
        self.assertTrue(self.data["temporary"])
        self.assertFalse(self.data["physical_execution_enabled"])
        self.assertEqual(DEFAULT_MAP.name, "little-town-temporary.json")
        legacy = MapDefinition()
        self.assertEqual(legacy.id, "little-town-temporary")
        self.assertNotEqual(self.definition.geometry_hash, legacy.geometry_hash)
        self.assertEqual([legacy.data["board"]["width_mm"], legacy.data["board"]["height_mm"]], [400, 250])

    def test_declared_markers_convert_exact_source_centers_without_old_offset(self):
        centers = {10: [72.25, 54], 11: [2326.75, 54],
                   12: [2326.75, 1642], 13: [72.25, 1642]}
        self.assertEqual(self.data["marker_dictionary"], "DICT_4X4_50")
        self.assertTrue(self.definition.camera_registration_supported)
        self.assertEqual({row["id"] for row in self.data["markers"]}, set(centers))
        for marker in self.data["markers"]:
            expected = centers[marker["id"]]
            self.assertAlmostEqual(marker["center_mm"][0], expected[0] * 420 / 2400, places=8)
            self.assertAlmostEqual(marker["center_mm"][1], expected[1] * 297 / 1697, places=8)
            self.assertEqual(marker["size_mm"], 8.356)
            self.assertTrue(0 < marker["center_mm"][0] < 420)
            self.assertTrue(0 < marker["center_mm"][1] < 297)

    def test_building_names_and_panels_match_user_reference(self):
        expected = {"VILLA": [347, 349, 1018, 667], "HANOK": [1381, 349, 2050, 667],
                    "PIZZA": [347, 1030, 1018, 1348], "OFFICE_BUILDING": [1381, 1030, 2050, 1348]}
        self.assertEqual(self.data["start"], "PIZZA")
        self.assertEqual(set(self.data["destinations"]), {"VILLA", "HANOK", "OFFICE_BUILDING"})
        self.assertEqual({row["id"]: row["label"] for row in self.data["nodes"] if row["kind"] == "destination"},
                         {"PIZZA": "Pizza", "VILLA": "Villa", "HANOK": "Hanok", "OFFICE_BUILDING": "Office Building"})
        self.assertEqual(self.definition.node_label("C"), "Main Junction")
        for panel in self.data["building_panels"]:
            pixels = expected[panel["id"]]
            for index, value in enumerate(panel["bounds_mm"]):
                self.assertAlmostEqual(value, pixels[index] * ([420 / 2400, 297 / 1697][index % 2]), places=8)
        self.assertFalse({"BAKERY", "BOOKSTORE", "SCHOOL"} & {row["id"] for row in self.data["nodes"]})

    def test_all_directed_routes_depart_east_and_visit_main_junction_first(self):
        graph = {row["id"]: [] for row in self.data["nodes"]}
        for edge in self.data["edges"]:
            graph[edge["from"]].append(edge["to"])
            if edge["bidirectional"]:
                graph[edge["to"]].append(edge["from"])
        self.assertEqual(graph["PIZZA"], ["C"])
        self.assertIn("PIZZA", graph["W"])
        seen_destinations = set()

        def visit(path):
            if path[-1] in self.data["destinations"]:
                seen_destinations.add(path[-1])
                route = self.definition.route_from_nodes(path[-1], path)
                self.assertEqual(route["node_ids"][:2], ["PIZZA", "C"])
                self.assertEqual(route["directions"]["departure"]["map_direction"], "east")
                self.assertEqual(route["junction_ids"][0], "C")
                self.assertFalse(route["physical_execution_enabled"])
            for neighbor in graph[path[-1]]:
                if neighbor not in path:
                    visit([*path, neighbor])

        visit(["PIZZA"])
        self.assertEqual(seen_destinations, set(self.data["destinations"]))
        self.assertEqual(self.definition.planning_audit()["status"], "passed")

    def test_default_and_selected_route_segments_stay_continuous_on_roads(self):
        alternatives = {
            "VILLA": ["PIZZA", "C", "S", "SW", "W", "NW", "VILLA"],
            "HANOK": ["PIZZA", "C", "OFFICE_BUILDING", "E", "NE", "HANOK"],
            "OFFICE_BUILDING": ["PIZZA", "C", "N", "HANOK", "NE", "E", "OFFICE_BUILDING"],
        }
        for destination in self.data["destinations"]:
            for route in (self.definition.route(destination),
                          self.definition.route_from_nodes(destination, alternatives[destination])):
                segments = route["visualization"]["segments"]
                self.assertEqual(segments[0]["points_mm"][0], route["points_mm"][0])
                self.assertEqual(segments[-1]["points_mm"][-1], route["points_mm"][-1])
                self.assertAlmostEqual(sum(row["length_mm"] for row in segments), route["distance_mm"])
                for first, second in zip(segments, segments[1:]):
                    self.assertEqual(first["points_mm"][-1], second["points_mm"][0])
                steps = WorkspaceStore._route_steps(route)
                self.assertEqual([row["route_segment_id"] for row in steps if row["kind"] in {"PUSH", "CROSS"}],
                                 [row["id"] for row in segments])
                for segment in segments:
                    for first, second in zip(segment["points_mm"], segment["points_mm"][1:]):
                        self.assertTrue(math.isclose(first[0], second[0]) or math.isclose(first[1], second[1]))
                        midpoint = [(a + b) / 2 for a, b in zip(first, second)]
                        self.assertFalse(any(panel["bounds_mm"][0] < midpoint[0] < panel["bounds_mm"][2]
                                             and panel["bounds_mm"][1] < midpoint[1] < panel["bounds_mm"][3]
                                             for panel in self.data["building_panels"]))

    def test_signal_regions_and_physical_qualification_are_not_inferred(self):
        self.assertEqual(self.data["signal_targets"], [])
        self.assertIsNone(self.definition.signal_target("C", "PIZZA"))
        self.assertIn("not a measured installation", self.data["source"]["adaptation"])
        for public in (self.definition.snapshot(), self.definition.planning_context(), self.definition.planning_audit()):
            self.assertFalse(public["physical_execution_enabled"])
        self.assertFalse(self.definition.planning_context()["declared_start"]["measured_pose"])
        self.assertFalse(self.definition.planning_audit()["equipment_contacted"])

    def test_main_junction_display_stops_before_crosswalk_at_yellow_line(self):
        center = next(row for row in self.data["nodes"] if row["id"] == "C")
        self.assertEqual(center["junction_size_mm"], 99)
        self.assertEqual(center["road_width_mm"], 63.525)
        self.assertEqual(self.data["board"]["junction_size_mm"], 42)
        self.assertEqual(self.data["board"]["road_width_mm"], 42.175)
        for destination in self.data["destinations"]:
            route = self.definition.route(destination)
            main = route["visualization"]["junctions"][0]
            self.assertEqual(main["node_id"], "C")
            self.assertAlmostEqual(main["stop_point_mm"][0], 160.4125)
            self.assertEqual(main["stop_point_mm"][1], center["y_mm"])
            self.assertAlmostEqual(math.dist(*main["stop_line_mm"]), 63.525)
            self.assertAlmostEqual(main["stop_point_mm"][0], 917 * 420 / 2400, delta=0.1)
            # The west crosswalk begins at source x945; its drawing stop remains outside it.
            self.assertLess(main["stop_point_mm"][0], 945 * 420 / 2400)
        data = self.definition.data
        c = next(row for row in data["nodes"] if row["id"] == "C")
        c["junction_size_mm"] = 98
        self.assertNotEqual(MapDefinition.from_data(data).geometry_hash, self.definition.geometry_hash)

    def test_spatial_correspondence_uses_matching_road_envelopes_only_for_display(self):
        preview = self.data["spatial_preview"]
        self.assertEqual(preview["schema_version"], "pushpilot.spatial-preview.v1")
        self.assertEqual(preview["model_id"], "pushpilot-seoul-city-web-clean-roads")
        self.assertEqual(preview["model_sha256"], "f5fb0b2524d6bee45f5b939f121b29d5eac274ea34e670895dada3a2b70b39d7")
        self.assertEqual(preview["drawing_rect_mm"], [39.6375, 40.3408956982911, 379.925, 257.6216853270477])
        self.assertEqual(preview["model_rect_xz"], [-236, -149, 236, 149])
        self.assertEqual(preview["elevation"], 2)
        self.assertEqual(preview["alignment"], "drawing_correspondence")
        self.assertEqual(preview["coordinate_authority"], "display_only")
        x0, y0, x1, y1 = preview["drawing_rect_mm"]
        # JSON road coordinates are rounded; allow only their sub-nanometre representation error.
        for node in self.data["nodes"]:
            self.assertTrue(x0 - 1e-8 <= node["x_mm"] <= x1 + 1e-8)
            self.assertTrue(y0 - 1e-8 <= node["y_mm"] <= y1 + 1e-8)
        # A changed presentation correspondence must not silently reuse old plan/reference identities.
        adjusted = self.definition.data
        adjusted["spatial_preview"]["elevation"] = 3
        self.assertNotEqual(MapDefinition.from_data(adjusted).geometry_hash, self.definition.geometry_hash)


if __name__ == "__main__":
    unittest.main()
