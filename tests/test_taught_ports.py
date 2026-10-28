"""Real port contract exercised with fake HTTP, Native and Meta providers only."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import MagicMock

from backend.robot_control.taught_executor import ExecutionBlocked, MotionIntent
from backend.robot_control.taught_ports import (LocalHTTP, NativeObservation, PrivateJournal,
                                               RealTaughtPorts, encoded, loopback_origin, quiet_native_capture)
from tools.prepare_local_contact import build_profile
from tests.test_taught_executor import configuration, pose
from tools.run_taught_executor import load_route


def synthetic_status():
    installation = {"scope": "local_contact_commissioning", "installation_id": "synthetic-installation",
        "tcp_id": "synthetic-tcp", "tcp_definition_sha256": "b"*64, "tool_id": "synthetic-tool", "payload_kg": .1,
        "review_reference": "Synthetic offline actual-site fixture; no physical qualification.", "qualified": True,
        "on_site_review": True, "workspace_min_mm": [-50., -50., 9.], "workspace_max_mm": [150., 50., 11.],
        "fixed_tcp_z_mm": 10., "fixed_orientation_deg": [90., 0., 30.], "tcp_clearance_margin_mm": 0.,
        "inflated_keepout_boxes_base_mm": [], "max_step_mm": 20., "max_speed_mm_s": 3., "max_accel_mm_s2": 5.,
        "car_id": "synthetic-car", "surface_id": "synthetic-paper", "reported_car_dimensions_mm": [45., 18., 15.],
        "contact_trials_authorized": True, "trial_max_step_mm": 20.}
    actual = {"actual_pose": list(pose(0)), "actual_joint": [0.]*6}
    profile = build_profile(installation, actual, on_site_review=True)
    receiver = {"connected": True, "idle": True, "physical_execution": True, "session_id": "synthetic-session",
                "seq": 4, "profile_id": "synthetic-profile", "profile": profile, **actual}
    return {"mode": "physical_commissioning", "hardware_connected": True, "armed": False,
            "hold": True, "active_commands": [], "installation": installation, "receiver": receiver}


class FakeAPI:
    def __init__(self):
        self.status = synthetic_status()
        self.calls, self.command = [], None
        self.post_timeout, self.poll_timeout, self.wrong_target = False, False, False

    def call(self, path, payload=None):
        self.calls.append((path, payload))
        if path == "/v1/status":
            return deepcopy(self.status)
        if path == "/v1/arm":
            self.status.update(armed=True, hold=False)
            return {"armed": True}
        if path == "/v1/hold":
            self.status.update(armed=False, hold=True)
            return {"hold": True}
        if path == "/v1/commands":
            self.command = deepcopy(payload)
            if self.post_timeout:
                raise TimeoutError("Synthetic POST outcome unknown.")
            return {"state": "queued"}
        if path.startswith("/v1/commands/"):
            if self.poll_timeout:
                raise TimeoutError("Synthetic observation timeout; no repost is allowed.")
            command = self.command
            data = {"session_id": command["expected_receiver"]["session_id"], "seq": command["expected_receiver"]["seq"],
                    "request_id": "f"*32, "operation": "translate", "physical_execution": True,
                    "previous": list(pose(0)), "target": [999., *command["target"][1:]] if self.wrong_target else command["target"]}
            return {"id": command["request_id"], "state": "complete", "payload": command,
                    "result": {"robot_receipt": {"kind": "motion_endpoint_verified", "data": data}}}
        raise AssertionError("Unexpected fake API operation")


class FakeCamera:
    def __init__(self, adapter):
        self.raw = b"\xff\xd8original-fixture-pixels\xff\xd9"
        self.metadata = {"state": "live", "epoch": "synthetic-camera", "map_id": adapter.map_id,
            "map_version": adapter.map_version, "map_hash": adapter.map_hash,
            "registration": {"id": "synthetic-view", "status": "locked_occluded", "verification": "insufficient_visibility"},
            "frame": {"id": "f"*32, "image_url": "/api/v1/live-camera/frames/"+"f"*32+"/image",
                      "age_ms": 100, "width": 1920, "height": 1080, "sequence": 10,
                      "received_at": "1970-01-01T00:01:39.900000+00:00", "sha256": hashlib.sha256(self.raw).hexdigest()}}

    def call(self, path, payload=None, *, binary=False):
        return self.raw if binary else deepcopy(self.metadata)


class RealTaughtPortsTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = PrivateJournal(self.root / "evidence")
        self.addCleanup(self.journal.close)
        self.drawing, self.adapter, self.route = configuration()
        self.api, self.camera = FakeAPI(), FakeCamera(self.adapter)
        self.env = self.root / "application.env"
        self.env.write_text("META_API_KEY=synthetic-test-key\n")
        self.provider = MagicMock()
        self.ports = RealTaughtPorts(adapter=self.adapter, journal=self.journal, runtime=self.root / "not-installed",
            token_file=self.root / "not-read-by-fake-api", meta_env_file=self.env, camera_epoch="synthetic-camera",
            registration_id="synthetic-view", expected_visual="Synthetic white car progresses toward the visible destination.",
            api=self.api, camera=self.camera,
            native_capture=lambda: NativeObservation(pose(0), (0.,)*6, 100., "d"*64),
            provider_request=self.provider, clock=lambda: 100.)

    def intent(self):
        return MotionIntent("b3a08226-9cb7-41a1-9dcb-a52ec264353e", "synthetic-plan", 1, "PIZZA", "S",
            {"session_id": "synthetic-session", "seq": 4, "profile_id": "synthetic-profile"}, "synthetic-installation",
            pose(0), pose(10), "a"*64, {"sha256": "e"*64})

    def test_actual_existing_profile_checks_and_native_record_are_used(self):
        snapshot = self.ports.snapshot()
        self.assertEqual(snapshot.tcp_base, pose(0))
        self.assertEqual(snapshot.native_tcp_base, pose(0))
        self.assertEqual(snapshot.configured_stroke_mm, 20)
        self.api.status["receiver"]["profile"]["payload_kg"] = .2
        with self.assertRaises(Exception):
            self.ports.snapshot()

    def test_expected_marker_occlusion_retains_original_jpeg_but_disagreement_blocks(self):
        frame = self.ports.capture()
        self.assertEqual(frame.original_jpeg, self.camera.raw)
        self.assertEqual(frame.sha256, hashlib.sha256(self.camera.raw).hexdigest())
        self.assertTrue(list(self.journal.root.glob("*.native.jpg")))
        self.camera.metadata["registration"]["verification"] = "marker_disagreement"
        with self.assertRaises(ExecutionBlocked):
            self.ports.capture()

    def test_api_uuid_and_wire_id_are_distinct_and_both_preserved(self):
        intent = self.intent()
        result = self.ports.execute_once(intent)
        self.assertEqual(result.request_id, intent.request_id)
        self.assertEqual(result.sequence, 5)
        self.assertEqual(sum(path == "/v1/commands" for path, _ in self.api.calls), 1)
        self.assertEqual(self.api.calls[-1][0], "/v1/hold")
        original = json.loads(next(self.journal.root.glob("robot-result-*.json")).read_bytes())
        self.assertEqual(original["result"]["robot_receipt"]["data"]["request_id"], "f"*32)
        self.assertNotEqual(original["result"]["robot_receipt"]["data"]["request_id"], intent.request_id)

    def test_unknown_post_or_get_timeout_never_reposts_motion(self):
        for mode in ("post_timeout", "poll_timeout"):
            with self.subTest(mode=mode):
                self.api.calls.clear()
                setattr(self.api, mode, True)
                with self.assertRaises(TimeoutError):
                    self.ports.execute_once(self.intent())
                self.assertEqual(sum(path == "/v1/commands" for path, _ in self.api.calls), 1)
                self.assertEqual(self.api.calls[-1][0], "/v1/hold")
                setattr(self.api, mode, False)

    def test_wrong_wire_target_is_not_promoted_to_verified_motion(self):
        self.api.wrong_target = True
        with self.assertRaises(ExecutionBlocked):
            self.ports.execute_once(self.intent())
        self.assertEqual(self.api.calls[-1][0], "/v1/hold")

    def test_real_provider_gets_both_unchanged_originals_and_uncertainty_is_retained(self):
        before = self.ports.capture()
        after = replace(before, id="newer-frame", sequence=11)
        value = {"verdict": "UNCERTAIN", "car_visible": True, "expected_progress": False,
                 "excessive_yaw": False, "arrived": False, "observed": "Synthetic ambiguous movement.",
                 "summary": "Movement not resolved.", "limitations": ["Synthetic imagery."]}
        envelope = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}
        self.provider.return_value = 200, envelope, 900
        result = self.ports.review(self.intent(), before, after, at_goal=True)
        self.assertEqual(result.verdict, "UNCERTAIN")
        self.assertFalse(result.expected_progress or result.arrived)
        payload = self.provider.call_args.args[3]
        self.assertIn("real PushPilot", payload["messages"][0]["content"])
        urls = [item["image_url"]["url"] for item in payload["messages"][1]["content"] if item["type"] == "image_url"]
        import base64
        self.assertEqual([base64.b64decode(url.split(",", 1)[1]) for url in urls], [before.original_jpeg, after.original_jpeg])
        original = json.loads(next(self.journal.root.glob("muse-result-*.json")).read_bytes())
        self.assertEqual(original["provider_envelope"], envelope)

    def test_provider_error_or_malformed_result_never_synthesizes_demo_pass(self):
        before = self.ports.capture()
        self.provider.side_effect = TimeoutError("Synthetic provider timeout.")
        with self.assertRaises(TimeoutError):
            self.ports.review(self.intent(), before, before, at_goal=False)
        self.assertEqual(self.provider.call_count, 1)
        saved = json.loads(next(self.journal.root.glob("muse-failed-*.json")).read_bytes())
        self.assertIsNone(saved["result"])
        self.provider.side_effect = None
        self.provider.return_value = 200, {"choices": [{"finish_reason": "stop", "message": {"content": '{"verdict":"PASS"}'}}]}, 1
        with self.assertRaises(ExecutionBlocked):
            self.ports.review(self.intent(), before, before, at_goal=False)

    def test_local_http_confines_token_to_numeric_loopback_and_no_retry(self):
        for origin in ("http://example.com:8897", "http://127.0.0.1:8897/path", "https://127.0.0.1:8897", "http://user:pass@127.0.0.1:8897"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                loopback_origin(origin)
        token = self.root / "control.token"
        token.write_text("synthetic-control-token-"+"a"*32)
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'{"held":true}'
        client = LocalHTTP("http://127.0.0.1:8897", token, opener=opener)
        self.assertEqual(client.call("/v1/hold", {"reason": "Synthetic local test."}), {"held": True})
        self.assertEqual(opener.open.call_count, 1)
        with self.assertRaises(ValueError):
            client.call("//example.com/steal-token")

    def test_journal_checkpoint_chain_and_missing_checkpoint_force_reconciliation(self):
        self.journal.append("synthetic-event", {"physical_execution": False})
        self.assertEqual(self.journal.load()["state"], "JOURNAL_WITHOUT_CHECKPOINT")
        self.journal.checkpoint({"state": "WAIT_REVIEW", "pending_request_id": "synthetic"})
        self.assertEqual(self.journal.load()["state"], "WAIT_REVIEW")
        self.journal.close()
        reopened = PrivateJournal(self.journal.root)
        self.assertEqual(reopened.index, 1)
        reopened.close()
        path = self.journal.event_path
        path.write_bytes(path.read_bytes().replace(b"synthetic-event", b"tampered-event"))
        with self.assertRaises(ValueError):
            PrivateJournal(self.journal.root)

    def test_quiet_native_reads_distinct_heartbeats_and_never_retries_failed_fc03(self):
        runtime = self.root / "synthetic-runtime"
        run = runtime / "runs" / "synthetic-session-folder"
        run.mkdir(parents=True)
        (runtime / "current_session.json").write_text(json.dumps({"path": run.name}))
        state = {"stage": "idle", "session_id": "synthetic-session", "seq": 4,
                 "profile_id": "synthetic-profile", "updated_monotonic_ns": 0}
        fake_time = [1.5]
        def publish():
            state["updated_monotonic_ns"] = int(fake_time[0])*1_000_000_000
            (run / "state.json").write_text(json.dumps(state))
        publish()
        def sleep(delay):
            fake_time[0] += delay
            publish()
        native = MagicMock()
        row = {"program_before": [0], "program_after": [0], "flags": [1, 1, 0, 0, 0, 0],
               "joint": [0.]*6, "speed": [0.]*6, "pose": list(pose(0))}
        native.snapshot.return_value = row
        modules = {"transport": type("Transport", (), {"Native": lambda unused: native})}
        observed = quiet_native_capture(runtime, self.journal, loader=lambda _: modules,
            monotonic=lambda: fake_time[0], monotonic_ns=lambda: int(fake_time[0]*1e9),
            clock=lambda: 100+fake_time[0], sleep=sleep)
        self.assertEqual(native.snapshot.call_count, 3)
        self.assertEqual(observed.pose, pose(0))
        native.snapshot.reset_mock()
        native.snapshot.side_effect = TimeoutError("Synthetic Native read failure.")
        with self.assertRaises(TimeoutError):
            quiet_native_capture(runtime, self.journal, loader=lambda _: modules,
                monotonic=lambda: fake_time[0], monotonic_ns=lambda: int(fake_time[0]*1e9),
                clock=lambda: 100+fake_time[0], sleep=sleep)
        self.assertEqual(native.snapshot.call_count, 1)
        self.assertTrue(list(self.journal.root.glob("native-failed-*.json")))


class PhysicalRouteBundleTests(TestCase):
    def test_live_meta_intent_requires_distinct_exact_operator_physical_approval(self):
        drawing, _, route = configuration()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            provider = {"id": route.muse_provider_receipt, "source": "meta", "simulation_only": True,
                "motion_authority": False, "input_kind": "live_native_frame_and_graph",
                "provider_result": {"route_nodes": list(route.node_ids), "destination": route.destination,
                                    "requires_clarification": False},
                "map_context": {"map_id": drawing.id, "map_version": drawing.version, "map_hash": drawing.geometry_hash}}
            approval = {"schema": "pushpilot.operator-physical-course-approval.v1", "source": "operator",
                "id": route.approval_receipt, "approved": True, "simulation_approval": False,
                "operator_instruction_reference": "Synthetic human instruction fixture, not a real approval.",
                **{key: getattr(route, key) for key in ("plan_id", "revision", "destination", "node_ids", "map_id", "map_version", "map_hash", "commissioning_without_signals")}}
            def source(name, value):
                path = root / name
                path.write_bytes(encoded(value))
                return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            bundle = {"schema": "pushpilot.physical-approved-route.v1", "route": route.__dict__,
                      "provider_evidence": source("provider.json", provider), "physical_approval": source("approval.json", approval)}
            path = root / "route.json"
            path.write_bytes(encoded(bundle))
            self.assertEqual(load_route(path), route)
            approval["simulation_approval"] = True
            bundle["physical_approval"] = source("approval.json", approval)
            path.write_bytes(encoded(bundle))
            with self.assertRaises(ValueError):
                load_route(path)


if __name__ == "__main__":
    main()
