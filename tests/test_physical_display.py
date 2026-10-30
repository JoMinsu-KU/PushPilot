"""Display-only evidence projection: no device, inference, DB or control calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.physical_display import BoundedJournalTail, PhysicalDisplayService, _encoded
from backend.physical_display_api import router


class DisplayFixture:
    def __init__(self, directory):
        self.root = Path(directory)
        self.now = 1000.
        self.rows, self.previous = 0, "0" * 64
        self.path = self.root / "events.private.jsonl"
        self.path.write_bytes(b"")
        self.status = {"enabled": True, "state": "MOVING", "mission_id": "mission-one",
            "plan_id": "plan-one", "plan_revision": 4, "workspace_session_id": "workspace-one",
            "destination": "VILLA", "error": None, "signal": {"waiting": False,
                "stable_green_frames": 0, "required_green_frames": 2},
            "vision": {"in_flight": False}, "car": {"arrived": False},
            "telemetry": {"sequence": []}}
        self.map_data = {"nodes": [{"id": "START", "x_mm": 0, "y_mm": 10},
            {"id": "S", "x_mm": 10, "y_mm": 10}, {"id": "C", "x_mm": 10, "y_mm": 0},
            {"id": "VILLA", "x_mm": 0, "y_mm": 0}]}
        self.packet = {"routes": {"C": {"destination": "VILLA", "steps": []}}, "primitives": {}}
        for index, heading in enumerate((0., -90., 180., -90.), 1):
            pid = "unit-" + str(index)
            self.packet["routes"]["C"]["steps"].append({"id": "step-" + str(index),
                "primitive_id": pid, "expected_heading_deg": heading})
            self.packet["primitives"][pid] = {"id": pid, "stages": [
                {"id": pid + "-approach", "phase": "approach"},
                {"id": pid + "-contact", "phase": "contact"},
                {"id": pid + "-withdraw", "phase": "withdraw"}]}
        self.write_config()
        self.service = PhysicalDisplayService(self.root / "config.json", physical_snapshot=lambda: deepcopy(self.status),
            map_data=self.map_data, map_hash="a" * 64, clock=lambda: self.now)

    def write_config(self):
        raw = _encoded(self.packet)
        (self.root / "packet.json").write_bytes(raw)
        cfg = {"enabled": True, "packet": {"path": "packet.json", "sha256": hashlib.sha256(raw).hexdigest()},
            "journal_root": str(self.root), "workspace_bindings": {"C": {"map_hash": "a" * 64,
                "route_nodes": ["START", "S", "C", "VILLA"]}}}
        (self.root / "config.json").write_bytes(_encoded(cfg))

    def append(self, kind, payload, *, partial=False):
        self.rows += 1
        row = {"index": self.rows, "previous_sha256": self.previous, "created_at": self.now,
               "kind": kind, "payload": payload}
        self.previous = hashlib.sha256(_encoded(row)).hexdigest()
        data = _encoded({**row, "sha256": self.previous}) + (b"" if partial else b"\n")
        with self.path.open("ab") as stream:
            stream.write(data)

    def stage(self, primitive="unit-1", index=1, *, mission=None, revision=None):
        command = "command-" + primitive
        self.append("mission_primitive_intent", {"primitive_id": primitive, "command_id": command})
        stage = self.packet["primitives"][primitive]["stages"][index]
        self.append("mission_stage_intent", {"command_id": command, "stage_index": index,
            "stage_id": stage["id"], "phase": stage["phase"], "intent": {
                "request_id": command + "-request", "plan_id": mission or self.status["mission_id"],
                "revision": revision if revision is not None else self.status["plan_revision"],
                "expected_receiver": {"seq": 10, "session_id": "receiver-one"}}})

    def endpoint(self, primitive="unit-1", index=1, *, confirmed=True):
        command = "command-" + primitive
        self.append("mission_stage_endpoint", {"command_id": command, "stage_index": index,
            "receipt": {"request_id": command + "-request", "endpoint_verified": confirmed,
                "sequence": 11, "session_id": "receiver-one"},
            "native_after": {"sequence": 11, "session_id": "receiver-one", "held_disarmed_idle": True}})

    def collect(self):
        self.service.collect()
        return self.service.snapshot()


class PhysicalDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = DisplayFixture(self.temp.name)

    def test_intent_is_pending_not_moving(self):
        self.f.stage()
        result = self.f.collect()
        self.assertTrue(result["available"])
        self.assertEqual(result["phase"], "pending")
        self.assertFalse(result["vehicle"]["moving"])
        self.assertEqual(result["vehicle"]["confirmed_contact_stages"], 0)

    def test_exact_native_endpoint_advances_contact_only(self):
        self.f.stage()
        self.f.endpoint()
        result = self.f.collect()
        self.assertEqual(result["phase"], "contact")
        self.assertTrue(result["vehicle"]["moving"])
        self.assertEqual(result["vehicle"]["route_leg_index"], 0)
        self.assertEqual(result["vehicle"]["leg_fraction"], 1.)
        self.assertFalse(result["motion_authority"])
        self.f.now += 2
        self.assertFalse(self.f.collect()["vehicle"]["moving"])

    def test_approach_withdraw_and_return_keep_car_fixed(self):
        self.f.stage()
        self.f.endpoint()
        first = self.f.collect()["vehicle"]["route_fraction"]
        for phase, index in (("approach", 0), ("withdraw", 2)):
            self.f.stage(index=index)
            self.f.endpoint(index=index)
            result = self.f.collect()
            self.assertEqual(result["phase"], phase)
            self.assertFalse(result["vehicle"]["moving"])
            self.assertEqual(result["vehicle"]["route_fraction"], first)
        self.f.status.update(state="RETURNING_HOME", returning_home=True)
        self.assertEqual(self.f.collect()["vehicle"]["route_fraction"], first)

    def test_wrong_endpoint_or_intent_binding_never_animates(self):
        self.f.stage(mission="old-mission")
        self.f.endpoint()
        self.assertFalse(self.f.collect()["available"])
        self.f.stage(revision=3)
        self.f.endpoint()
        self.assertFalse(self.f.collect()["available"])
        self.f.stage()
        self.f.endpoint(confirmed=False)
        self.assertEqual(self.f.collect()["vehicle"]["confirmed_contact_stages"], 0)

    def test_missing_tail_binding_freezes_until_current_intent(self):
        self.f.append("mission_primitive_complete", {"receipt": {"primitive_id": "unit-1"}})
        self.assertEqual(self.f.collect()["reason"], "DISPLAY_MISSION_BINDING_PENDING")
        self.f.stage()
        self.assertTrue(self.f.collect()["available"])

    def test_partial_line_does_not_count_until_newline(self):
        self.f.stage()
        self.f.collect()
        self.f.append("mission_stage_endpoint", {"command_id": "not-relevant", "stage_index": 1}, partial=True)
        result = self.f.collect()
        self.assertEqual(result["stage_status"], "intent")
        with self.f.path.open("ab") as stream:
            stream.write(b"\n")
        self.assertTrue(self.f.collect()["available"])

    def test_duplicate_or_out_of_order_journal_fails_display_only(self):
        self.f.stage()
        self.f.collect()
        before = deepcopy(self.f.status)
        duplicate = self.f.path.read_bytes().splitlines()[-1]
        with self.f.path.open("ab") as stream:
            stream.write(duplicate + b"\n")
        self.assertFalse(self.f.collect()["available"])
        self.assertFalse(self.f.collect()["available"])
        self.assertEqual(self.f.status, before)

    def test_truncation_drops_prior_receipts(self):
        self.f.stage()
        self.f.endpoint()
        self.f.collect()
        self.f.path.write_bytes(b"")
        result = self.f.collect()
        self.assertFalse(result["available"])
        self.assertIsNone(result["vehicle"]["route_fraction"])

    def test_invalid_complete_json_line_remains_unavailable(self):
        self.f.stage()
        self.f.collect()
        with self.f.path.open("ab") as stream:
            stream.write(b"invalid-json\n")
        self.assertFalse(self.f.collect()["available"])
        self.assertFalse(self.f.collect()["available"])

    def test_new_mission_cannot_reuse_old_evidence(self):
        self.f.stage()
        self.f.endpoint()
        self.f.collect()
        self.f.status["mission_id"] = "mission-two"
        result = self.f.collect()
        self.assertFalse(result["available"])
        self.assertEqual(result["mission_id"], "mission-two")
        self.f.stage()
        self.assertTrue(self.f.collect()["available"])
        self.assertEqual(self.f.collect()["vehicle"]["confirmed_contact_stages"], 0)

    def test_completed_units_bootstrap_contact_progress_without_replay(self):
        self.f.stage(primitive="unit-2")
        self.f.status["telemetry"]["sequence"] = [{"id": "unit-1", "kind": "route", "status": "complete"}]
        result = self.f.collect()
        self.assertEqual(result["vehicle"]["confirmed_contact_stages"], 1)
        self.assertFalse(result["vehicle"]["moving"])

    def test_heading_correction_does_not_regress_route_leg(self):
        for number in range(1, 5):
            self.f.stage(primitive="unit-" + str(number))
            self.f.endpoint(primitive="unit-" + str(number))
        result = self.f.collect()
        self.assertEqual(result["vehicle"]["route_leg_index"], 2)
        self.assertEqual(result["vehicle"]["heading"], "WEST")

    def test_arrival_and_home_return_leave_car_at_destination(self):
        self.f.stage()
        self.f.status.update(state="RETURNING_HOME", returning_home=True)
        self.f.status["car"]["arrived"] = True
        result = self.f.collect()
        self.assertEqual(result["vehicle"]["route_fraction"], 1.)
        self.assertFalse(result["vehicle"]["moving"])

    def test_signal_after_recontact_is_passed_even_green_count_reset(self):
        self.f.stage()
        self.f.status["signal"].update(waiting=True, stable_green_frames=1)
        self.assertEqual(self.f.collect()["signal"]["phase"], "confirming")
        self.f.status["signal"].update(waiting=False, stable_green_frames=0)
        self.f.status["state"] = "RECONTACTING"
        self.assertEqual(self.f.collect()["signal"]["phase"], "recontacting")
        self.f.status["state"] = "MOVING"
        self.f.status["telemetry"]["sequence"] = [{"id": "rc", "kind": "recontact", "status": "complete"}]
        self.assertEqual(self.f.collect()["signal"]["phase"], "passed")

    def test_hold_and_provider_review_freeze(self):
        self.f.stage()
        self.f.endpoint()
        for state, phase in (("HOLD", "hold"), ("OBSERVING", "muse_review"), ("WAITING_SIGNAL", "signal_wait")):
            self.f.status["state"] = state
            self.f.status["signal"]["waiting"] = state == "WAITING_SIGNAL"
            result = self.f.collect()
            self.assertEqual(result["phase"], phase)
            self.assertFalse(result["vehicle"]["moving"])

    def test_packet_mismatch_is_isolated_and_cache_has_no_private_geometry(self):
        self.f.stage()
        result = self.f.collect()
        public = json.dumps(result)
        for secret in (str(self.f.root), "target_base", "start_base", "token", "profile_id"):
            self.assertNotIn(secret, public)
        (self.f.root / "packet.json").write_bytes(b"{}")
        self.f.service._config_stamp = None
        self.assertEqual(self.f.collect()["reason"], "DISPLAY_PACKET_MISMATCH")

    def test_disabled_and_missing_source_never_mutate_physical(self):
        before = deepcopy(self.f.status)
        self.f.service.config_path = None
        self.assertEqual(self.f.collect()["reason"], "PHYSICAL_DISPLAY_DISABLED")
        self.assertEqual(self.f.status, before)

    def test_file_reads_never_create_or_change_source_artifacts(self):
        self.f.stage()
        self.f.endpoint()
        before = {p.name: p.read_bytes() for p in self.f.root.iterdir()}
        self.f.collect()
        after = {p.name: p.read_bytes() for p in self.f.root.iterdir()}
        self.assertEqual(after, before)
        # No executor, socket, inference or durable owner implementation import.
        import ast
        import backend.physical_display as module
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imported += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
        self.assertFalse(any(name.startswith(("backend", "socket", "httpx", "urllib")) for name in imported))

    def test_oversized_input_and_corrupt_map_binding_fail_only_display(self):
        self.f.service.config_path.write_bytes(b" " * 1_000_001)
        self.assertFalse(self.f.collect()["available"])
        self.f.write_config()
        self.f.service.map_hash = "b" * 64
        self.assertEqual(self.f.collect()["reason"], "DISPLAY_MAP_MISMATCH")

    def test_snapshot_exception_does_not_escape_collector(self):
        self.f.service.physical_snapshot = lambda: (_ for _ in ()).throw(RuntimeError("snapshot unavailable"))
        self.f.collect()
        self.assertFalse(self.f.service.snapshot()["available"])

    def test_producer_epoch_is_stable_per_collector_and_changes_on_recreation(self):
        self.f.stage()
        epoch = self.f.collect()["producer_epoch"]
        self.assertEqual(self.f.collect()["producer_epoch"], epoch)
        other = PhysicalDisplayService(None, physical_snapshot=lambda: self.f.status,
            map_data=self.f.map_data, map_hash="a" * 64)
        self.assertNotEqual(other.snapshot()["producer_epoch"], epoch)

    def test_get_is_cached_and_no_post_route_exists(self):
        app = FastAPI()
        app.state.physical_display = self.f.service
        app.include_router(router)
        with TestClient(app) as client, patch.object(self.f.service, "collect", side_effect=AssertionError("GET performed IO")):
            self.assertEqual(client.get("/api/v1/physical/display").status_code, 200)
            self.assertEqual(client.post("/api/v1/physical/display").status_code, 405)
            with patch.object(self.f.service, "snapshot", side_effect=ValueError("broken cache")):
                self.assertFalse(client.get("/api/v1/physical/display").json()["available"])


class LifecycleIsolationTests(unittest.TestCase):
    def test_broken_display_constructor_start_and_close_do_not_break_physical(self):
        class Physical:
            def __init__(self, *args, **kwargs):
                self.status = {"unchanged": True}
                self.calls = []
            async def refresh_readiness(self): self.calls.append("readiness")
            def start_monitor(self): self.calls.append("monitor")
            def snapshot(self): return deepcopy(self.status)
            async def close(self): self.calls.append("close")

        class BrokenDisplay:
            def __init__(self, *args, **kwargs): pass
            def start(self): raise ValueError("display start failure")
            def close(self): raise ValueError("display close failure")

        class BrokenCloseDisplay(BrokenDisplay):
            def start(self): pass
            def snapshot(self): raise ValueError("cache unavailable")

        for implementation in (BrokenDisplay, BrokenCloseDisplay,
                lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("constructor failure"))):
            with self.subTest(implementation=implementation), patch("backend.app.PhysicalMissionService", Physical), \
                    patch("backend.app.PhysicalDisplayService", implementation):
                app = create_app(db_path=":memory:", live_camera_url="")
                with TestClient(app) as client:
                    physical = app.state.physical
                    self.assertEqual(client.get("/api/v1/physical/status").json(), {"unchanged": True})
                    self.assertFalse(client.get("/api/v1/physical/display").json()["available"])
                    self.assertEqual(physical.calls, ["readiness", "monitor"])
                self.assertEqual(physical.calls, ["readiness", "monitor", "close"])


if __name__ == "__main__":
    unittest.main()
