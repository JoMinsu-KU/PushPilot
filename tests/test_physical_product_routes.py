"""Real application/store/map contracts with synthetic motion only; no hardware."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.settings import Settings
from tests.test_mission_policy import plan
from tests.test_physical_mission import FakeMeasuredDriver


MAP = Path(__file__).resolve().parents[1] / "backend/data/seoul-city-a3.json"


class PhysicalProductRouteTests(unittest.TestCase):
    def test_real_application_defaults_to_no_physical_authority(self):
        with TemporaryDirectory() as directory:
            settings = Settings(db_path=str(Path(directory) / "state.sqlite3"), map_path=str(MAP))
            with TestClient(create_app(settings=settings, live_camera_url="")) as client:
                result = client.get("/api/v1/physical/status")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["state"], "DISABLED")
                self.assertFalse(result.json()["available"])

    def test_all_three_current_map_destinations_bind_and_complete_synthetic_return(self):
        for destination in ("OFFICE_BUILDING", "VILLA", "HANOK"):
            with self.subTest(destination=destination), TemporaryDirectory() as directory:
                driver = FakeMeasuredDriver(replace(plan(), destination=destination))
                settings = Settings(db_path=str(Path(directory) / "state.sqlite3"), map_path=str(MAP))
                app = create_app(settings=settings, physical_driver=driver, live_camera_url="")
                with TestClient(app) as client:
                    state = client.get("/api/v1/state").json()
                    response = client.post("/api/v1/goals", json={"request_id": str(uuid4()),
                        "expected_revision": state["revision"], "text": destination,
                        "provider": "demo", "source": "typed"})
                    self.assertEqual(response.status_code, 200, response.text)
                    state = response.json()
                    self.assertEqual(state["goal"]["destination"], destination)
                    # Seed a labelled synthetic planning receipt at the service boundary.
                    # This tests the REAL store/map shape, not MUSE or physical accuracy.
                    with app.state.store._lock, app.state.store._db:
                        stored = app.state.store._load()
                        stored["goal"]["provider"] = "meta"
                        stored["plan"]["planning"] = {"source": "synthetic-test-only"}
                        app.state.store._save(stored)
                    route = state["plan"]["route"]
                    status = client.get("/api/v1/physical/status").json()
                    self.assertEqual(status["capabilities"]["destinations"], [destination])
                    command = {"request_id": str(uuid4()), "expected_revision": status["revision"],
                        "workspace_session_id": state["session_id"], "plan_id": state["plan"]["id"],
                        "plan_revision": state["plan"]["revision"], "destination": destination,
                        "route_nodes": route["node_ids"], "map_id": route["map_id"],
                        "map_version": route["map_version"], "map_hash": route["map_hash"]}
                    app.state.physical.poll_interval_s = .001
                    response = client.post("/api/v1/physical/start", json=command,
                        headers={"origin": "http://testserver"})
                    self.assertEqual(response.status_code, 200, response.text)
                    client.portal.call(asyncio.wait_for, app.state.physical.task, 3.)
                    final = client.get("/api/v1/physical/status").json()
                    self.assertEqual(final["destination"], destination)
                    self.assertEqual(final["state"], "COMPLETE")
                    self.assertTrue(final["car"]["arrived"])
                    self.assertTrue(final["robot"]["at_start"])
                    self.assertEqual([p for p, _ in driver.commands], ["delivery-unit", "return"])


if __name__ == "__main__":
    unittest.main()
