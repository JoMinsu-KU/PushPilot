"""Equipment-free console integration; all robot/HTTP operations are synthetic."""
import asyncio
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import urllib.error
from unittest.mock import patch
from uuid import uuid4

from backend.commissioning_console.adapter import ConsoleAdapter, REVIEWED_FIELDS, _ArchivedVision
from backend.robot_control.taught_executor import ExecutionBlocked
from backend.robot_control.taught_ports import PrivateJournal
import tests.test_site_trial_driver as fixtures


class PassiveHTTP:
    def __init__(self, owner="owner"):
        self.origin = "http://127.0.0.1:8080"
        self.calls = []
        self.status = {"revision": 4, "state": "COMPLETE",
                       "commissioning": {"reserved": True, "owner_id": owner}}
        self.opener = None

    def call(self, path, payload=None, **kwargs):
        if payload is not None:
            raise AssertionError("Synthetic passive HTTP must never submit robot operations.")
        self.calls.append(path)
        return deepcopy(self.status)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        deployment = self.root / "deployment"
        deployment.mkdir()
        self.path, self.config, self.packet, self.review, _ = fixtures.fixture(deployment)
        self.config["ports"].update(token_file=str(self.root / "unused-control.token"),
            meta_env_file=str(self.root / "unused-private.env"), expected_visual="Synthetic controlled unit outcome.")
        self.path.write_text(json.dumps(self.config))
        self.original_bytes = self.path.read_bytes()
        self.product = PassiveHTTP()
        self.robot = PassiveHTTP()
        self.robot.origin = "http://127.0.0.1:8897"
        self._patch("backend.commissioning_console.adapter.LocalHTTP",
            side_effect=lambda origin, *a, **k: self.robot if "8897" in origin else self.product)
        self._patch("backend.commissioning_console.adapter.SiteTrialMissionDriver",
            side_effect=lambda path: fixtures.SiteTrialMissionDriver(path, port_factory=fixtures.SitePorts))
        self._patch("backend.robot_control.site_trial_driver.load_runtime", return_value={
            "policy": SimpleNamespace(MAX_PROFILE_BYTES=65536, valid=lambda *a: None)})
        self._patch("backend.commissioning_console.adapter.MissionObserver", return_value=fixtures.Observer())
        self.adapter = ConsoleAdapter(self.path, owner_id="owner")
        self.addCleanup(self.adapter.close)

    def _patch(self, *args, **kwargs):
        value = patch(*args, **kwargs)
        value.start()
        self.addCleanup(value.stop)

    def acquire(self):
        return self.adapter.acquire(self.root / "sessions" / "owned")

    def step(self):
        return self.adapter.routes()["routes"][0]["steps"][0]

    def edited(self):
        step = self.step()
        stages = deepcopy(step["stages"])
        stages[0]["target_base"][0] = 9.
        stages[1]["start_base"][0] = 9.
        value = {"stages": stages, "expected_visual": step["expected_visual"],
                 "reason": "Synthetic reviewed smaller approach with original normal release."}
        return step, value

    def test_constructor_effective_routes_are_file_only(self):
        exported = self.adapter.routes()
        self.assertEqual(self.robot.calls, [])
        self.assertEqual(self.product.calls, [])
        self.assertIsNone(self.adapter.driver)
        self.assertFalse(Path(self.config["journal_root"]).exists())
        route = exported["routes"][0]
        self.assertEqual((route["code"], route["destination"]), ("B", "OFFICE_BUILDING"))
        self.assertEqual(route["steps"][0]["source_base"], list(fixtures.SOURCE))
        self.assertEqual(route["empty_return"][0]["id"], "return")
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_acquire_requires_exact_broker_owner_before_ports(self):
        self.product.status["commissioning"]["owner_id"] = "other-owner"
        with self.assertRaises(ExecutionBlocked) as error:
            self.acquire()
        self.assertEqual(error.exception.code, "CONSOLE_RESERVATION_REQUIRED")
        self.assertIsNone(self.adapter.driver)
        self.assertFalse((self.root / "sessions").exists())

    def test_acquire_new_journal_native_proof_without_commands(self):
        result = self.acquire()
        self.assertFalse(result["motion_issued"])
        driver = self.adapter.driver
        self.assertEqual(driver.ports.intents, [])
        self.assertTrue(all(payload is None for _, payload in driver.ports.raw.calls))
        self.assertTrue(driver.stop_latch.is_set())
        self.assertEqual(Path(driver.config["journal_root"]), self.root / "sessions" / "owned")
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_real_guarded_driver_executes_only_selected_primitive(self):
        self.acquire()
        result = self.adapter.execute("B", "goal", None, str(uuid4()))
        driver = self.adapter.driver
        self.assertEqual(result["outcome"], "COMPLETED")
        self.assertEqual(result["receipt"]["target_context_id"], "PARK")
        self.assertEqual(len(driver.ports.intents), 3)
        self.assertEqual([list(i.target_base) for i in driver.ports.intents],
                         [s["target_base"] for s in self.packet["primitives"]["push"]["stages"]])
        self.assertEqual(len({i.request_id for i in driver.ports.intents}), 3)
        self.assertEqual(driver.journal.load()["state"], "STATIONARY_COMMAND_COMPLETE")
        self.assertTrue(result["before_artifact_id"])
        image = self.adapter.artifact(result["before_artifact_id"])
        self.assertTrue(image.startswith(b"\xff\xd8"))
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_wrong_source_is_known_before_execution_no_motion(self):
        self.acquire()
        driver = self.adapter.driver
        driver.ports.raw.status["receiver"]["actual_pose"][0] += 1.
        with self.assertRaises(ExecutionBlocked) as error:
            self.adapter.execute("B", "goal", None, str(uuid4()))
        self.assertEqual(error.exception.code, "CONSOLE_EXACT_SOURCE")
        self.assertTrue(error.exception.known_before_execute)
        self.assertEqual(driver.ports.intents, [])
        self.assertFalse(any(payload is not None for _, payload in driver.ports.raw.calls))

    def test_draft_validates_without_io_and_keeps_anchors(self):
        step, value = self.edited()
        candidate = self.adapter.validate_draft(step, value)
        self.assertTrue(candidate["offline_geometry_valid"])
        self.assertFalse(candidate["physical_clearance_verified"])
        self.assertFalse(candidate["ik_verified"])
        self.assertEqual(candidate["required_contact_normal_base_xy"], [1., 0.])
        self.assertNotEqual(candidate["geometry_sha256"], candidate["original_geometry_sha256"])
        self.assertEqual(self.product.calls, [])
        self.assertIsNone(self.adapter.driver)

    def test_draft_rejects_height_final_anchor_large_step_and_missing_backoff(self):
        step, value = self.edited()
        changes = []
        z_change = deepcopy(value)
        for stage in z_change["stages"]:
            stage["start_base"][2] += .1
            stage["target_base"][2] += .1
        changes.append(z_change)
        final_change = deepcopy(value)
        final_change["stages"][-1]["target_base"][0] = 11.
        changes.append(final_change)
        long_step = deepcopy(value)
        long_step["stages"][0]["target_base"][0] = 29.
        long_step["stages"][1]["start_base"][0] = 29.
        changes.append(long_step)
        backoff = deepcopy(value)
        backoff["stages"][1]["target_base"][0] = 19.
        backoff["stages"][2]["start_base"][0] = 19.
        changes.append(backoff)
        for candidate in changes:
            with self.subTest(candidate=candidate):
                with self.assertRaises((ExecutionBlocked, ValueError)):
                    self.adapter.validate_draft(step, candidate)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_candidate_requires_exact_review_and_keeps_original_provenance(self):
        step, value = self.edited()
        draft = self.adapter.validate_draft(step, value)
        self.acquire()
        driver = self.adapter.driver
        original = self.adapter.preview.measured["push"]
        old = original.to_dict()
        with self.assertRaises(ExecutionBlocked) as error:
            self.adapter._candidate(driver, original, draft)
        self.assertEqual(error.exception.code, "CONSOLE_EXPLICIT_DRAFT_REVIEW")
        draft["approval"] = {"approved": True, "reason": value["reason"],
            "geometry_sha256": draft["geometry_sha256"], "reviewed_fields": list(REVIEWED_FIELDS),
            "contact_normal_base_xy": draft["required_contact_normal_base_xy"]}
        candidate, child = self.adapter._candidate(driver, original, draft)
        self.assertEqual(original.to_dict(), old)
        self.assertEqual(candidate.original_verdict, "MISSING")
        self.assertTrue(all(s.original_request_id.startswith("console-derived-geometry-") for s in candidate.stages))
        self.assertIn(candidate.geometry_sha256, child["allowed_geometry_sha256"])
        for key in ("site", "workspace_min_mm", "workspace_max_mm", "max_speed_mm_s", "max_accel_mm_s2", "max_step_mm"):
            self.assertEqual(child[key], driver.profile_review[key])
        self.assertEqual(driver.ports.intents, [])
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_approved_candidate_runs_with_fresh_profile_not_forged_pass(self):
        step, value = self.edited()
        draft = self.adapter.validate_draft(step, value)
        draft.update(approved=True, approval={"approved": True, "reason": value["reason"],
            "geometry_sha256": draft["geometry_sha256"], "reviewed_fields": list(REVIEWED_FIELDS),
            "contact_normal_base_xy": draft["required_contact_normal_base_xy"]})
        self.acquire()
        result = self.adapter.execute("B", "goal", draft, str(uuid4()))
        self.assertEqual(result["outcome"], "COMPLETED")
        self.assertEqual(result["geometry_sha256"], draft["geometry_sha256"])
        self.assertEqual(self.adapter.driver.ports.intents[0].target_base[0], 9.)
        self.assertEqual(self.adapter.preview.measured["push"].original_verdict, "MISSING")
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_stop_after_first_stage_never_advances_or_clears_pending(self):
        self.acquire()
        driver = self.adapter.driver
        driver.ports.after_execute = self.adapter.request_stop
        with self.assertRaises(ExecutionBlocked):
            self.adapter.execute("B", "goal", None, str(uuid4()))
        self.assertEqual(len(driver.ports.intents), 1)
        self.assertIsNotNone(driver.pending_command_id)
        with self.assertRaises(ExecutionBlocked):
            self.adapter.confirm_stationary()
        self.assertEqual(len(driver.ports.intents), 1)

    def test_gate_does_not_accept_missing_stale_or_changed_green(self):
        self.acquire()
        driver = self.adapter.driver
        native = driver._snapshot()
        gate = SimpleNamespace(id="signal", entry_policy="single_departure")
        step = SimpleNamespace(signal_gate=gate)
        plan = SimpleNamespace(steps=(step, SimpleNamespace(signal_gate=None)))
        for proof in (None, {"state": "GREEN_ACCEPTED", "expires_at_s": driver.ports.now() - 1,
                             "native": asdict(native)},
                      {"state": "GREEN_ACCEPTED", "expires_at_s": driver.ports.now() + 10,
                       "native": {**asdict(native), "sequence": native.sequence + 1}}):
            self.adapter._signal_proofs.clear()
            if proof is not None:
                self.adapter._signal_proofs[("D", "signal")] = proof
            with self.assertRaises(ExecutionBlocked) as error:
                self.adapter._check_signal_selection(driver, "D", plan, "signal_recontact", 0, step, native)
            self.assertEqual(error.exception.code, "CONSOLE_SIGNAL_GREEN_REQUIRED")
        with self.assertRaises(ExecutionBlocked):
            self.adapter._check_signal_selection(driver, "D", plan, "route", 1, plan.steps[1], native)
        self.assertEqual(driver.ports.intents, [])

    def test_ack_does_not_clear_a_concurrent_new_stop(self):
        self.acquire()
        driver = self.adapter.driver
        original = driver._snapshot
        def changing():
            actual = original()
            self.adapter.request_stop()
            return actual
        with patch.object(driver, "_snapshot", side_effect=changing):
            with self.assertRaises(ExecutionBlocked) as error:
                self.adapter.confirm_stationary()
        self.assertEqual(error.exception.code, "CONSOLE_STOPPED")
        self.assertTrue(driver.stop_latch.is_set())
        self.assertEqual(driver.ports.intents, [])

    def test_broker_uses_longer_observation_budget_without_retry(self):
        calls = []
        class Reply(io.BytesIO):
            pass
        class Opener:
            def open(self, request, timeout):
                calls.append((request, timeout))
                return Reply(b'{"accepted":true}')
        self.product.opener = Opener()
        self.assertTrue(self.adapter._product_post("/synthetic", {"id": "test"})["accepted"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 30)
        self.assertEqual(calls[0][0].get_header("Origin"), self.product.origin)

    def test_broker_4xx_and_ambiguous_5xx_are_distinguished(self):
        for status, rejected in ((409, True), (500, False)):
            class Opener:
                def open(inner, request, timeout):
                    raise urllib.error.HTTPError(request.full_url, status, "Synthetic failure", {},
                        io.BytesIO(b'{"code":"COMMISSIONING_BUSY","message":"synthetic"}'))
            self.product.opener = Opener()
            with self.subTest(status=status):
                with self.assertRaises(ExecutionBlocked) as error:
                    self.adapter._product_post("/synthetic", {"id": "test"})
                self.assertEqual(error.exception.code, "COMMISSIONING_BUSY")
                self.assertEqual(error.exception.status_code, status)
                self.assertEqual(error.exception.broker_rejected, rejected)

    def test_ready_release_requires_original_start_no_implicit_return(self):
        self.acquire()
        self.assertTrue(self.adapter.ready_to_release()["at_start"])
        self.adapter.execute("B", "goal", None, str(uuid4()))
        with self.assertRaises(ExecutionBlocked) as error:
            self.adapter.ready_to_release()
        self.assertEqual(error.exception.code, "CONSOLE_RELEASE_START_REQUIRED")
        self.assertEqual(len(self.adapter.driver.ports.intents), 3)

    def test_artifact_rejects_arbitrary_paths(self):
        with self.assertRaises(ExecutionBlocked):
            self.adapter.artifact("../../unused-private.env")

    def test_reservation_timeout_preserves_exact_owner_and_request_identity(self):
        sent = []
        def lost(path, payload):
            sent.append(payload)
            raise TimeoutError("Synthetic lost broker response.")
        with patch.object(self.adapter, "_product_post", side_effect=lost):
            request = str(uuid4())
            with self.assertRaises(TimeoutError):
                self.adapter.reserve("attempted-owner", "Synthetic operator handoff.", request_id=request)
        self.assertEqual(self.adapter.owner_id, "attempted-owner")
        self.assertEqual(sent[0]["request_id"], request)


class ArchivedVisionTests(unittest.TestCase):
    def test_actual_provider_body_saved_before_schema_adaptation(self):
        with TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            key = root / "private.env"
            key.write_text("META_API_KEY=synthetic-test-value\n")
            journal = PrivateJournal(root / "journal")
            stack.callback(journal.close)
            # Keep literal provider formatting to verify byte-level SHA evidence.
            envelope = {"choices": [{"finish_reason": "stop", "message": {"content": '{"answer":true}'}}]}
            raw = json.dumps(envelope, indent=2).encode()
            calls = []
            class Reply(io.BytesIO):
                status = 200
            class Opener:
                def open(self, request, timeout):
                    calls.append((request, timeout))
                    return Reply(raw)
            ports = SimpleNamespace(meta_env_file=key, journal=journal, provider_opener=Opener())
            vision = _ArchivedVision(ports)
            result = asyncio.run(vision._request("Synthetic prompt only.", [{"type": "text", "text": "test"}],
                "synthetic_schema", {"type": "object"}, lambda value: value, "synthetic test"))
            self.assertEqual(result, {"answer": True})
            files = list(journal.root.glob("console-muse-raw-response-*.private.json"))
            self.assertEqual(len(files), 1)
            record = json.loads(files[0].read_bytes())
            self.assertEqual(record["raw_body_utf8"].encode(), raw)
            self.assertEqual(record["body_sha256"], hashlib.sha256(raw).hexdigest())
            payload = json.loads(calls[0][0].data)
            self.assertEqual(payload["model"], vision.model)
            self.assertEqual(calls[0][1], 45)
            self.assertNotIn("synthetic-test-value", files[0].read_text())


if __name__ == "__main__":
    unittest.main()
