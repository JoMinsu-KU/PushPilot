"""Map-bound drawing correspondences never become robot or camera calibration."""
from __future__ import annotations

from copy import deepcopy
import unittest

from backend.maps import MapDefinition


MODEL_HASH = "f5fb0b2524d6bee45f5b939f121b29d5eac274ea34e670895dada3a2b70b39d7"


def drawing_data():
    data = MapDefinition().data
    data["spatial_preview"] = {
        "schema_version": "pushpilot.spatial-preview.v1",
        "model_id": "pushpilot-seoul-city-web-clean-roads", "model_sha256": MODEL_HASH,
        "drawing_rect_mm": [0, 0, 400, 250], "model_rect_xz": [-297, -210, 297, 210],
        "elevation": 2, "alignment": "drawing_correspondence", "coordinate_authority": "display_only",
    }
    return data


class SpatialPreviewMetadataTests(unittest.TestCase):
    def test_legacy_hash_and_snapshot_remain_unchanged_without_optional_correspondence(self):
        definition = MapDefinition()
        self.assertEqual(definition.geometry_hash, "731a6b31f524daf1226781e4cf96b56ef0c1ee7141e2817ed709f94db5399161")
        self.assertNotIn("spatial_preview", definition.snapshot())

    def test_map_identity_binds_every_display_correspondence_change_and_snapshot_is_private_copy(self):
        data = drawing_data()
        definition = MapDefinition.from_data(data)
        self.assertFalse(definition.snapshot()["physical_execution_enabled"])
        self.assertEqual(definition.snapshot()["spatial_preview"], data["spatial_preview"])
        self.assertNotEqual(definition.geometry_hash, MapDefinition().geometry_hash)
        for key, replacement in (("elevation", 3), ("model_sha256", "0" * 64),
                                 ("model_id", "another-reviewed-model"), ("model_rect_xz", [-236, -149, 236, 149])):
            changed = deepcopy(data)
            changed["spatial_preview"][key] = replacement
            with self.subTest(key=key):
                self.assertNotEqual(MapDefinition.from_data(changed).geometry_hash, definition.geometry_hash)
        public = definition.snapshot()
        public["spatial_preview"]["drawing_rect_mm"][0] = -999
        self.assertEqual(definition.snapshot()["spatial_preview"]["drawing_rect_mm"][0], 0)

    def test_malformed_nonfinite_extra_and_authoritative_metadata_are_rejected(self):
        for replacement in (None, [], {}, "display"):
            data = drawing_data()
            data["spatial_preview"] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                MapDefinition.from_data(data)
        changes = [
            ("schema_version", "future"), ("alignment", "robot_registered"),
            ("coordinate_authority", "robot"), ("model_sha256", "A" * 64),
            ("model_sha256", "short"), ("model_id", " "), ("model_id", "x" * 101),
            ("drawing_rect_mm", [0, 0, 0, 250]), ("drawing_rect_mm", [-1, 0, 400, 250]),
            ("drawing_rect_mm", [0, 0, 401, 250]), ("drawing_rect_mm", [0, 0, float("nan"), 250]),
            ("drawing_rect_mm", [False, 0, 400, 250]), ("model_rect_xz", [0, -210, 0, 210]),
            ("model_rect_xz", [-297, -210, float("inf"), 210]),
            ("model_rect_xz", [-297, -210, 1_000_001, 210]),
            ("elevation", float("inf")), ("elevation", True), ("elevation", -1), ("elevation", 1001),
            ("unexpected_robot_transform", [1, 2, 3]),
        ]
        for key, value in changes:
            data = drawing_data()
            data["spatial_preview"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                MapDefinition.from_data(data)

    def test_correspondence_covers_complete_graph_with_only_roundoff_tolerance(self):
        data = drawing_data()
        data["spatial_preview"]["drawing_rect_mm"] = [52 + 1e-10, 33, 348, 201]
        self.assertIsInstance(MapDefinition.from_data(data), MapDefinition)
        data["spatial_preview"]["drawing_rect_mm"][0] = 52.001
        with self.assertRaisesRegex(ValueError, "complete map graph"):
            MapDefinition.from_data(data)

    def test_per_junction_drawing_override_changes_only_that_stop_region_and_map_identity(self):
        legacy = MapDefinition()
        original = legacy.route_from_nodes("BOOKSTORE", ["PIZZA", "C", "BOOKSTORE"])["visualization"]["junctions"][0]
        data = legacy.data
        center = next(node for node in data["nodes"] if node["id"] == "C")
        center.update(junction_size_mm=60, road_width_mm=20)
        definition = MapDefinition.from_data(data)
        junction = definition.route_from_nodes("BOOKSTORE", ["PIZZA", "C", "BOOKSTORE"])["visualization"]["junctions"][0]
        self.assertNotEqual(definition.geometry_hash, legacy.geometry_hash)
        self.assertEqual(original["stop_point_mm"], [181, 117])
        self.assertEqual(junction["stop_point_mm"], [170, 117])
        self.assertEqual(junction["exit_point_mm"], [230, 117])
        self.assertEqual(junction["stop_line_mm"], [[170, 107], [170, 127]])
        self.assertEqual(definition.snapshot()["nodes"], data["nodes"])
        for key in ("junction_size_mm", "road_width_mm"):
            for value in (None, False, 0, -1, float("nan"), float("inf"), 251):
                invalid = legacy.data
                next(node for node in invalid["nodes"] if node["id"] == "C")[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    MapDefinition.from_data(invalid)
            invalid = legacy.data
            next(node for node in invalid["nodes"] if node["id"] == "PIZZA")[key] = 20
            with self.assertRaises(ValueError):
                MapDefinition.from_data(invalid)

    def test_short_destination_edge_can_touch_stop_region_without_reversing_route(self):
        data = MapDefinition().data
        next(node for node in data["nodes"] if node["id"] == "PIZZA")["x_mm"] = 190
        next(node for node in data["nodes"] if node["id"] == "C")["junction_size_mm"] = 60
        next(edge for edge in data["edges"] if edge["from"] == "W" and edge["to"] == "PIZZA")["length_mm"] = 138
        next(edge for edge in data["edges"] if edge["from"] == "PIZZA" and edge["to"] == "C")["length_mm"] = 10
        route = MapDefinition.from_data(data).route_from_nodes("BOOKSTORE", ["PIZZA", "C", "BOOKSTORE"])
        segments = route["visualization"]["segments"]
        self.assertEqual(segments[0]["points_mm"], [[190, 117], [190, 117]])
        self.assertEqual(segments[1]["points_mm"], [[190, 117], [200, 117], [230, 117]])
        self.assertEqual(sum(segment["length_mm"] for segment in segments), 84)


if __name__ == "__main__":
    unittest.main()
