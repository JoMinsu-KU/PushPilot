"""Spatial-only A2 drawing fixtures do not invent camera marker positions."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.map_api import router
from backend.maps import MapDefinition


FIXTURE = Path(__file__).parent / "fixtures" / "harbor-map.json"


def spatial_data():
    """Adapt only the authored software fixture, not the production town model."""
    data = MapDefinition(FIXTURE).data
    data.update(id="spatial-only-a2-test", camera_registration_supported=False, markers=[])
    data["board"].update(width_mm=594, height_mm=420)
    data["page"] = {"width_mm": 594, "height_mm": 420, "board_origin_page_mm": [0, 0]}
    return data


class SpatialOnlyMapTests(unittest.TestCase):
    def test_explicit_spatial_map_preserves_graph_without_any_invented_markers(self):
        definition = MapDefinition.from_data(spatial_data())
        self.assertFalse(definition.camera_registration_supported)
        self.assertEqual(definition.data["markers"], [])
        self.assertEqual(definition.data["marker_dictionary"], "DICT_4X4_50")
        for view in (definition.snapshot(), definition.planning_context(), definition.planning_audit()):
            self.assertFalse(view["camera_registration_supported"])
            self.assertFalse(view["physical_execution_enabled"])
        self.assertEqual(definition.snapshot()["board"]["width_mm"], 594)
        self.assertEqual(definition.snapshot()["board"]["height_mm"], 420)
        route = definition.route_from_nodes("MUSEUM", ["DOCK", "J_WEST", "J_EAST", "MUSEUM"])
        self.assertEqual(route["distance_mm"], 340)
        self.assertEqual(len(definition.planning_context()["directed_edges"]), 12)
        self.assertEqual(definition.data["markers"], [])

    def test_support_flag_is_strict_hash_bound_and_opt_in_preserves_existing_default(self):
        legacy = MapDefinition()
        explicit = legacy.data
        explicit["camera_registration_supported"] = True
        self.assertTrue(legacy.camera_registration_supported)
        self.assertEqual(MapDefinition.from_data(explicit).geometry_hash, legacy.geometry_hash)
        explicit["camera_registration_supported"] = False
        self.assertNotEqual(MapDefinition.from_data(explicit).geometry_hash, legacy.geometry_hash)
        explicit["camera_registration_supported"] = True
        explicit["markers"] = []
        with self.assertRaises(ValueError):
            MapDefinition.from_data(explicit)
        for value in (None, "false", 0, 1, []):
            invalid = spatial_data()
            invalid["camera_registration_supported"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                MapDefinition.from_data(invalid)
        invalid = spatial_data()
        invalid["edges"][0]["length_mm"] = 1
        with self.assertRaises(ValueError):
            MapDefinition.from_data(invalid)
        invalid = spatial_data()
        marker = deepcopy(legacy.data["markers"][0])
        invalid["markers"] = [marker, deepcopy(marker)]
        with self.assertRaises(ValueError):
            MapDefinition.from_data(invalid)

    def test_validation_preview_warns_that_spatial_map_cannot_register_live_camera(self):
        application = FastAPI()
        application.include_router(router)
        with TestClient(application) as client:
            response = client.post("/api/v1/maps/validate", json={"definition": spatial_data()})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result["valid"])
        self.assertFalse(result["installed"])
        self.assertFalse(result["map"]["camera_registration_supported"])
        self.assertTrue(any("spatial-only" in warning and "live camera registration" in warning for warning in result["warnings"]))
        self.assertFalse(result["map"]["physical_execution_enabled"])


if __name__ == "__main__":
    unittest.main()
