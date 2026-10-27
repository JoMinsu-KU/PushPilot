"""Bounded read-only map validation never installs a candidate or contacts hardware."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.map_api import MAX_MAP_BYTES, router
from backend.maps import MapDefinition


FIXTURE = Path(__file__).parent / "fixtures" / "harbor-map.json"


class MapValidationApiTests(unittest.TestCase):
    def setUp(self):
        self.application = FastAPI()
        self.application.include_router(router)
        self.active = MapDefinition()
        self.application.state.map_definition = self.active
        self.client = TestClient(self.application)

    def tearDown(self):
        self.client.close()

    def validate(self, definition):
        return self.client.post("/api/v1/maps/validate", json={"definition": definition})

    def test_replacement_preview_keeps_active_map_and_does_not_read_write_or_contact_services(self):
        candidate = MapDefinition(FIXTURE).data
        before = self.active.snapshot()
        with patch("backend.maps.Path.read_text", side_effect=AssertionError("No candidate file read is needed.")), \
                patch("socket.create_connection", side_effect=AssertionError("No provider or device request is allowed.")), \
                patch("pathlib.Path.write_text", side_effect=AssertionError("No candidate file is persisted.")):
            response = self.validate(candidate)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["valid"])
        self.assertEqual(result["mode"], "preview_only")
        self.assertFalse(result["installed"])
        self.assertFalse(result["equipment_contacted"])
        self.assertEqual(result["map"]["id"], "harbor-replacement-fixture")
        self.assertEqual(result["counts"], {"nodes": 7, "edges": 6, "directed_edges": 12, "destinations": 4, "signal_targets": 0})
        self.assertEqual(result["routing"]["declared_start"], "DOCK")
        self.assertEqual(result["routing"]["unreachable_within_route_limit"], [])
        self.assertIn("--map-path <reviewed-map.json>", result["startup"]["command_template"])
        self.assertTrue(result["startup"]["requires_application_restart"])
        self.assertFalse(result["startup"]["restarts_camera_or_robot"])
        self.assertNotIn("C:/", json.dumps(result))
        self.assertEqual(self.application.state.map_definition.snapshot(), before)
        self.assertIs(self.application.state.map_definition, self.active)

    def test_missing_regions_warn_without_inventing_regions_or_measured_authority(self):
        result = self.validate(self.active.data).json()
        self.assertEqual(result["map"]["geometry_hash"], self.active.geometry_hash)
        self.assertEqual(result["counts"]["signal_targets"], 0)
        self.assertFalse(result["map"]["physical_execution_enabled"])
        self.assertTrue(any("No approach-specific signal targets" in warning for warning in result["warnings"]))

    def test_configured_target_changes_identity_and_is_counted_without_being_installed(self):
        data = self.active.data
        data["signal_targets"] = [{"id": "example-C-from-PIZZA", "junction_id": "C", "approach_from": "PIZZA",
                                   "bounds_mm": [174, 90, 184, 100], "description": "Synthetic test region only."}]
        result = self.validate(data).json()
        self.assertEqual(result["counts"]["signal_targets"], 1)
        self.assertNotEqual(result["map"]["geometry_hash"], self.active.geometry_hash)
        self.assertIsNone(self.active.signal_target("C", "PIZZA"))

    def test_unreachable_destination_returns_failed_preview_without_route_substitution(self):
        data = self.active.data
        data["edges"] = [edge for edge in data["edges"] if "PIZZA" not in (edge["from"], edge["to"])]
        response = self.validate(data)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertFalse(result["valid"])
        self.assertEqual(result["routing"]["unreachable_within_route_limit"], data["destinations"])
        self.assertFalse(result["installed"])

    def test_request_and_definition_shapes_are_strict_and_malformed_fields_do_not_crash(self):
        for payload in ({}, [], {"definition": self.active.data, "install": True}):
            with self.subTest(payload=type(payload).__name__):
                response = self.client.post("/api/v1/maps/validate", json=payload)
                self.assertEqual(response.status_code, 422)
        for data in (None, [], {}, {**self.active.data, "nodes": [None]},
                     {**self.active.data, "edges": [None]}, {**self.active.data, "destinations": [["C"]]},
                     {**self.active.data, "markers": "not-a-list"}):
            with self.subTest(data=data):
                response = self.validate(data)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"]["code"], "MAP_DEFINITION")

    def test_collection_limits_are_checked_before_map_initialization(self):
        for field, count in (("nodes", 501), ("edges", 2001), ("markers", 51), ("building_panels", 501),
                             ("signal_targets", 501), ("destinations", 501)):
            data = self.active.data
            data[field] = [None] * count
            with self.subTest(field=field), patch("backend.map_api.MapDefinition.from_data") as factory:
                response = self.validate(data)
                self.assertEqual(response.status_code, 422)
                factory.assert_not_called()

    def test_page_panels_limits_and_overlapping_directed_roads_must_be_usable_drawing_facts(self):
        mutations = []
        for key, value in (("page", {}), ("page", {"width_mm": 420, "height_mm": 297, "board_origin_page_mm": [-1, 0]}),
                           ("page", {"width_mm": 399, "height_mm": 250, "board_origin_page_mm": [0, 0]}),
                           ("building_panels", [{}]), ("building_panels", [{"id": "A", "bounds_mm": [1, 1, 401, 20]}]),
                           ("limitations", "unqualified"), ("limitations", [None])):
            data = self.active.data
            data[key] = value
            mutations.append(data)
        data = self.active.data
        data["edges"].append({**data["edges"][0], "bidirectional": False})
        mutations.append(data)
        data = self.active.data
        edge = data["edges"][0]
        data["edges"].append({"from": edge["to"], "to": edge["from"], "length_mm": edge["length_mm"], "bidirectional": False})
        mutations.append(data)
        for data in mutations:
            with self.subTest(data=data):
                response = self.validate(data)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"]["code"], "MAP_DEFINITION")

    def test_invalid_json_duplicate_keys_nonfinite_and_content_type_are_rejected(self):
        for body in (b"{", b"null", b'{"definition": {}, "definition": {}}',
                     b'{"definition": {"number": NaN}}', b'{"definition": {"number": 1e999}}',
                     b'{"definition": "\xff"}', b"[" * 2000 + b"]" * 2000):
            with self.subTest(body=body[:50]):
                response = self.client.post("/api/v1/maps/validate", content=body, headers={"content-type": "application/json"})
                self.assertIn(response.status_code, (400, 422))
        response = self.client.post("/api/v1/maps/validate", content=b"{}", headers={"content-type": "text/plain"})
        self.assertEqual(response.status_code, 415)

    def test_declared_and_streamed_body_limits_are_enforced(self):
        for length in (str(MAX_MAP_BYTES + 1), "invalid", "9" * 5000):
            with self.subTest(length=length[:20]):
                response = self.client.post("/api/v1/maps/validate", content=b"{}",
                                            headers={"content-type": "application/json", "content-length": length})
                self.assertEqual(response.status_code, 413)
        response = self.client.post("/api/v1/maps/validate", content=(chunk for chunk in [b" " * 600000, b" " * 600000]),
                                    headers={"content-type": "application/json"})
        self.assertEqual(response.status_code, 413)

    def test_in_memory_factory_isolated_from_its_source_and_rejects_nonobjects(self):
        data = self.active.data
        candidate = MapDefinition.from_data(data)
        data["nodes"][0]["x_mm"] = 0
        self.assertEqual(candidate.geometry_hash, self.active.geometry_hash)
        self.assertEqual(candidate.snapshot()["nodes"][0]["x_mm"], 52)
        for invalid in (None, [], "map.json"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                MapDefinition.from_data(invalid)


if __name__ == "__main__":
    unittest.main()
