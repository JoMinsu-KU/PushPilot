"""Real port contract exercised with fake HTTP, Native and Meta providers only."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from backend.robot_control.taught_executor import ExecutionBlocked, MotionIntent
from backend.robot_control.taught_ports import (LocalHTTP, NativeObservation, PrivateJournal,
                                               RealTaughtPorts, encoded, loopback_origin, quiet_native_capture,
                                               prove_host_journal_cycle, host_journal_native_capture)
from tools.prepare_local_contact import build_profile
from tools.prepare_contact_turn import build_profile as build_turn_profile
from tests.test_taught_executor import clearance_policy, configuration, pose, right_signal_target
from tools.run_taught_executor import load_adapter, load_route


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
                    "request_id": "f"*32, "operation": command["kind"], "physical_execution": True,
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

    def test_explicit_host_source_uses_bound_journal_evidence_without_quiet_native_query(self):
        self.ports.native_capture = None
        self.ports.native_observation_source = "host_journal"
        result = NativeObservation(pose(0), (0.,)*6, 100., "d"*64)
        with patch("backend.robot_control.taught_ports.host_journal_native_capture", return_value=result) as host:
            with patch("backend.robot_control.taught_ports.quiet_native_capture", side_effect=AssertionError("No supplementary query allowed")):
                self.ports.snapshot()
        self.assertEqual(host.call_args.kwargs["expected_receiver"],
                         {"session_id": "synthetic-session", "seq": 4, "profile_id": "synthetic-profile"})

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

    def turn_scope(self):
        local = self.api.status["installation"]
        local.update(scope="local_contact_turn_commissioning", contact_turn_trials_authorized=True,
            max_rotation_increment_deg=5.,
            orientations=[{"id": "first", "rxyz_deg": [90., 0., 30.]}, {"id": "next", "rxyz_deg": [90., 0., 35.]}],
            rotation_anchors=[{"id": "synthetic-anchor", "xyz_base_mm": list(pose(0)[:3]), "site_verified": True,
                "review_reference": "Synthetic full swept gripper review, not actual evidence.", "position_window_mm": .5,
                "max_in_place_correction_mm": .1, "window_and_correction_reviewed": True}],
            rotation_edges=[{"id": "synthetic-edge", "from": "first", "to": "next", "anchor_id": "synthetic-anchor",
                "site_verified": True, "review_reference": "Synthetic directed wrist-edge review, not actual evidence.",
                "expected_source_joint_deg": [0.]*6, "expected_target_joint_deg": [0.]*5+[5.],
                "wrist_only": True, "joint_path_reviewed": True}],
            rotation_runtime={"verified": True, "primitive": "moveJoint_wrist", "controller_version": "synthetic-only",
                "argument_semantics": "Synthetic test degree units, not physical runtime evidence.", "speed_argument": 3.,
                "accel_argument": 5., "completion_timeout_s": 60., "review_reference": "Synthetic runtime-only fixture review."})
        receiver = self.api.status["receiver"]
        receiver["profile"] = build_turn_profile(local, {key: receiver[key] for key in ("actual_pose", "actual_joint")}, on_site_review=True)
        return replace(self.intent(), kind="rotate", purpose="contact_turn_trial", edge_id="synthetic-edge",
            target_base=(*pose(0)[:3], 90., 0., 35.), expected_source_joint_deg=(0.,)*6,
            expected_target_joint_deg=(0., 0., 0., 0., 0., 5.),
            rotation_runtime_sha256=hashlib.sha256(encoded(receiver["profile"]["rotation_runtime"])).hexdigest(),
            expected_visual="The free wrist rotates while the physical white car remains stationary.")

    def test_contact_turn_rotate_posts_exact_edge_scope_runtime_and_visual_context(self):
        intent = self.turn_scope()
        snapshot = self.ports.snapshot()
        self.assertEqual(snapshot.scope, "local_contact_turn_commissioning")
        self.assertEqual(snapshot.rotation_runtime_sha256, intent.rotation_runtime_sha256)
        self.assertEqual(snapshot.reviewed_rotation_edges[0]["target_orientation_deg"], [90., 0., 35.])
        receipt = self.ports.execute_once(intent)
        self.assertEqual(receipt.target_base, intent.target_base)
        command = self.api.command
        self.assertEqual((command["kind"], command["purpose"], command["edge_id"]),
                         ("rotate", "contact_turn_trial", "synthetic-edge"))
        self.assertEqual(command["expected_visual"], intent.expected_visual)
        self.assertEqual(sum(path == "/v1/commands" for path, _ in self.api.calls), 1)

    def test_contact_turn_wrong_runtime_edge_or_source_joints_never_posts(self):
        intent = self.turn_scope()
        for changed in (replace(intent, rotation_runtime_sha256="e"*64),
                        replace(intent, edge_id="unmeasured-edge"),
                        replace(intent, expected_source_joint_deg=(0., 0., 0., 0., 0., 1.))):
            with self.subTest(changed=changed), self.assertRaises(ExecutionBlocked):
                self.ports.execute_once(changed)
        self.assertFalse(any(path == "/v1/commands" for path, _ in self.api.calls))

    def test_real_provider_gets_both_unchanged_originals_and_uncertainty_is_retained(self):
        before = self.ports.capture()
        after = replace(before, id="newer-frame", sequence=11)
        value = {"verdict": "UNCERTAIN", "occlusion_cause": "UNKNOWN", "car_visible": True, "expected_progress": False,
                 "signal_region_visible": False, "signal_occlusion_cause": "UNKNOWN",
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

    def test_clearance_review_sends_three_originals_and_separates_visibility_from_stationarity(self):
        before = self.ports.capture()
        covered_bytes, clear_bytes = b"\xff\xd8covered-original\xff\xd9", b"\xff\xd8clear-original\xff\xd9"
        covered = replace(before, id="covered", sequence=11, original_jpeg=covered_bytes,
                          sha256=hashlib.sha256(covered_bytes).hexdigest())
        clear = replace(before, id="clear", sequence=12, original_jpeg=clear_bytes,
                        sha256=hashlib.sha256(clear_bytes).hexdigest())
        withdrawal = replace(self.intent(), request_id="synthetic-clearance-uuid", observation_clearance_id="synthetic-side-policy",
                             expected_visual="Only the physical tool withdraws sideways; inspect the stationary car.")
        value = {"verdict": "PASS", "car_visible": True, "original_action_supported": True,
                 "car_unchanged_during_withdrawal": False, "recontact_eligible": False, "signal_region_visible": False,
                 "observed": "The car is now readable, but earlier occlusion prevents a stationarity comparison.",
                 "summary": "Visible car; recontact remains unverified.", "limitations": ["Earlier contact view was occluded."]}
        envelope = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}
        self.provider.return_value = 200, envelope, 1000
        result = self.ports.review_clearance(self.intent(), withdrawal, before, covered, clear)
        self.assertTrue(result.car_visible)
        self.assertFalse(result.car_unchanged_during_withdrawal or result.recontact_eligible)
        self.assertEqual(result.original_request_id, self.intent().request_id)
        payload = self.provider.call_args.args[3]
        import base64
        images = [item["image_url"]["url"] for item in payload["messages"][1]["content"] if item["type"] == "image_url"]
        self.assertEqual([base64.b64decode(value.split(",", 1)[1]) for value in images],
                         [before.original_jpeg, covered_bytes, clear_bytes])
        saved = json.loads(next(self.journal.root.glob("clearance-muse-result-*.json")).read_bytes())
        self.assertEqual(saved["provider_envelope"], envelope)
        self.assertEqual(saved["context"]["automatic_return"], False)

    def test_pair_and_clearance_use_bound_right_target_for_visibility_only(self):
        target = right_signal_target(camera_epoch="synthetic-camera")
        policy = replace(clearance_policy(), required_signal_observation=target)
        self.ports.adapter = replace(self.adapter, observation_clearances=(policy,))
        before = self.ports.capture()
        after = replace(before, id="newer-frame", sequence=11)
        pair = {"verdict": "PASS", "occlusion_cause": "NONE", "car_visible": True, "expected_progress": True,
                "excessive_yaw": False, "arrived": False, "signal_region_visible": False, "signal_occlusion_cause": "TOOL",
                "observed": "Synthetic car motion is readable, while the tool covers the specified right-side region.",
                "summary": "Car readable; right-side region covered.", "limitations": ["Synthetic imagery only."]}
        self.provider.return_value = 200, {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(pair)}}]}, 900
        result = self.ports.review(self.intent(), before, after, at_goal=False)
        self.assertEqual((result.signal_region_visible, result.signal_occlusion_cause), (False, "TOOL"))
        context = json.loads(self.provider.call_args.args[3]["messages"][1]["content"][0]["text"])
        self.assertEqual(context["required_signal_observation"], json.loads(encoded(asdict(target))))
        self.assertTrue(context["signal_visibility_only"])
        clearance = {"verdict": "PASS", "car_visible": True, "original_action_supported": True,
                     "car_unchanged_during_withdrawal": True, "recontact_eligible": True, "signal_region_visible": True,
                     "observed": "The synthetic car and configured right-side region are readable.",
                     "summary": "Both observation targets readable; no signal colour or permission assessed.", "limitations": []}
        self.provider.return_value = 200, {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(clearance)}}]}, 900
        withdrawal = replace(self.intent(), observation_clearance_id=policy.id, observation_junction_id="S")
        result = self.ports.review_clearance(self.intent(), withdrawal, before, before, after)
        self.assertTrue(result.signal_region_visible)
        payload = self.provider.call_args.args[3]
        self.assertIn("visibility ONLY", payload["messages"][0]["content"])
        self.assertNotIn("signal_color", payload["response_format"]["json_schema"]["schema"]["properties"])
        self.assertNotIn("crossing_permission", payload["response_format"]["json_schema"]["schema"]["properties"])

    def test_unconfigured_signal_cannot_be_claimed_visible_by_provider(self):
        before = self.ports.capture()
        value = {"verdict": "PASS", "car_visible": True, "original_action_supported": True,
                 "car_unchanged_during_withdrawal": True, "recontact_eligible": True, "signal_region_visible": True,
                 "observed": "Synthetic unsupported target claim.", "summary": "Unbound visibility is not accepted.", "limitations": []}
        self.provider.return_value = 200, {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}, 1
        with self.assertRaises(ExecutionBlocked):
            self.ports.review_clearance(self.intent(), self.intent(), before, before, before)
        self.assertFalse(list(self.journal.root.glob("clearance-muse-result-*.json")))

    def test_signal_view_mismatch_is_rejected_before_any_io(self):
        policy = replace(clearance_policy(), required_signal_observation=right_signal_target(camera_epoch="different-camera"))
        api, camera = MagicMock(), MagicMock()
        with self.assertRaisesRegex(ValueError, "actual fixed camera"):
            RealTaughtPorts(adapter=replace(self.adapter, observation_clearances=(policy,)), journal=self.journal,
                runtime=self.root, token_file=self.root/"unused", meta_env_file=self.env,
                camera_epoch="synthetic-camera", registration_id="synthetic-view", expected_visual="Synthetic target fixture only.",
                api=api, camera=camera, provider_request=self.provider)
        self.assertFalse(api.mock_calls or camera.mock_calls or self.provider.mock_calls)

    def test_clearance_provider_failure_is_saved_without_recontact_or_demo_pass(self):
        before = self.ports.capture()
        withdrawal = replace(self.intent(), observation_clearance_id="synthetic-side-policy")
        self.provider.side_effect = TimeoutError("Synthetic three-frame provider timeout.")
        with self.assertRaises(TimeoutError):
            self.ports.review_clearance(self.intent(), withdrawal, before, before, before)
        self.assertEqual(self.provider.call_count, 1)
        record = json.loads(next(self.journal.root.glob("clearance-muse-failed-*.json")).read_bytes())
        self.assertIsNone(record["result"])
        self.assertFalse(self.api.command)

    def test_failed_clearance_finish_or_content_retains_full_original_provider_response(self):
        before = self.ports.capture()
        withdrawal = replace(self.intent(), observation_clearance_id="synthetic-side-policy")
        envelopes = [
            {"id": "synthetic-truncated", "choices": [{"finish_reason": "length", "message": {"content": '{"partial":"original'}}],
             "usage": {"completion_tokens": 650}},
            {"id": "synthetic-malformed", "choices": [{"finish_reason": "stop", "message": {"content": "not valid JSON"}}]},
        ]
        for envelope in envelopes:
            self.provider.return_value = 200, envelope, 1234
            with self.subTest(envelope=envelope), self.assertRaises((ExecutionBlocked, ValueError)):
                self.ports.review_clearance(self.intent(), withdrawal, before, before, before)
        records = [json.loads(path.read_bytes()) for path in self.journal.root.glob("clearance-muse-response-*.json")]
        self.assertEqual(len(records), 2)
        for envelope in envelopes:
            self.assertTrue(any(record["provider_envelope"] == envelope and record["http_status"] == 200
                                and record["latency_ms"] == 1234 for record in records))
        self.assertFalse(list(self.journal.root.glob("clearance-muse-result-*.json")))

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
    def test_private_signal_target_requires_original_exact_view_and_region_record(self):
        drawing, adapter, _ = configuration()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            def source(name, value):
                path = root/name
                path.write_bytes(encoded(value))
                return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            primitive = source("synthetic-primitive.json", {"fixture": "Offline synthetic primitive only; no hardware qualification."})
            target = right_signal_target()
            metadata = {key: value for key, value in asdict(target).items() if key != "target_evidence_sha256"}
            target_source = source("synthetic-signal-target.json", {"schema": "pushpilot.signal-observation-target.v1",
                "visibility_only": True, "signal_color_qualified": False, "target": metadata})
            target = replace(target, target_evidence_sha256=target_source["sha256"])
            policy = clearance_policy()
            action = replace(policy.withdrawal, qualification_sha256=primitive["sha256"])
            policy = replace(policy, qualification_sha256=primitive["sha256"], withdrawal=action, withdrawal_actions=(action,),
                             recontact=None, required_signal_observation=target)
            review = source("synthetic-review.json", {"schema": "pushpilot.taught-course-qualification.v1",
                "scope": "fixed_pose_contact_corridor", "qualification": "accepted", "physical_execution": True,
                "map_identity": {"id": drawing.id, "version": drawing.version, "hash": drawing.geometry_hash},
                "fixture": "Synthetic loader input, not a real physical qualification."})
            adapter = replace(adapter, review_sha256=review["sha256"],
                roads=tuple(replace(road, qualification_sha256=primitive["sha256"]) for road in adapter.roads),
                observation_clearances=(policy,))
            bundle = {"schema": "pushpilot.taught-physical-adapter.v1", "adapter": asdict(adapter),
                      "qualification_evidence": [primitive, review, target_source]}
            path = root/"synthetic-adapter.json"
            path.write_bytes(encoded(bundle))
            self.assertEqual(load_adapter(path), adapter)
            bundle["qualification_evidence"] = [primitive, review]
            path.write_bytes(encoded(bundle))
            with self.assertRaisesRegex(ValueError, "original actual review"):
                load_adapter(path)
            bundle["qualification_evidence"].append(target_source)
            bundle["adapter"]["observation_clearances"][0]["required_signal_observation"]["image_bounds_px"] = [1200, 300, 1450, 550]
            path.write_bytes(encoded(bundle))
            with self.assertRaisesRegex(ValueError, "exact visibility region"):
                load_adapter(path)

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


def host_cycle_fixture():
    identity = {"session_id": "synthetic-session", "seq": 7, "profile_id": "synthetic-profile"}
    header = {**identity, "schema": "pushpilot.hcr1-pose.experimental-v1", "robot_id": "HCR1", "execute_motion": True}
    state = {**identity, "schema": header["schema"], "stage": "idle", "physical_execution": True,
             "updated_monotonic_ns": 2_130_000_000, "actual_pose": list(pose(0)), "planned_pose": list(pose(0)),
             "actual_joint": [0.]*6, "planned_joint": [99.]*6}
    native = {"program_before": [2], "program_after": [2], "flags": [1, 1, 0, 0, 0, 0],
              "joint": [0.]*6, "speed": [0.]*6, "pose": list(pose(0))}
    rows = [
        {"monotonic_ns": 1_010_000_000, "kind": "tx_intent", "data": {**header, "type": "idle"}},
        {"monotonic_ns": 1_020_000_000, "kind": "rx", "data": {**header, "type": "idle_ok"}},
        {"monotonic_ns": 1_025_000_000, "kind": "control_owner_check", "data": {"listening": False}},
        {"monotonic_ns": 1_030_000_000, "kind": "native_readonly", "data": deepcopy(native)},
        {"monotonic_ns": 1_130_000_000, "kind": "native_readonly", "data": deepcopy(native)},
    ]
    return identity, state, rows


def journal_bytes(rows):
    return b"".join(encoded(row)+b"\n" for row in rows)


class HostJournalNativeProofTests(TestCase):
    def prove(self, state, rows, **kwargs):
        return prove_host_journal_cycle(state, journal_bytes(rows), now_monotonic_ns=2_200_000_000,
                                        publication_after_ns=1_000_000_000, **kwargs)

    def test_completed_host_guard_rows_are_actual_measurements_not_planned_joints(self):
        identity, state, rows = host_cycle_fixture()
        proof = self.prove(state, rows, expected_receiver=identity)
        self.assertEqual(proof["pose"], state["actual_pose"])
        self.assertEqual(proof["joint"], [0.]*6)
        self.assertNotEqual(proof["joint"], state["planned_joint"])
        self.assertEqual(proof["source_sample_monotonic_ns"], 1_130_000_000)
        self.assertEqual(proof["source_journal_sha256"], hashlib.sha256(journal_bytes(rows)).hexdigest())
        self.assertEqual(proof["extra_fc03_queries"], 0)

    def test_timeout_resets_pair_and_needs_two_new_native_rows_before_publication(self):
        _, state, rows = host_cycle_fixture()
        timeout = {"monotonic_ns": 1_050_000_000, "kind": "stationary_read_timeout",
                   "data": {"consecutive_samples_reset": True, "motion_retried": False}}
        incomplete = rows[:4]+[timeout]+rows[4:]
        with self.assertRaises(ExecutionBlocked):
            self.prove(state, incomplete)
        fresh = deepcopy(rows[-1])
        fresh["monotonic_ns"] = 1_230_000_000
        proof = self.prove(state, incomplete+[fresh])
        self.assertEqual([row["monotonic_ns"] for row in proof["native_rows"]], [1_130_000_000, 1_230_000_000])
        self.assertEqual(proof["timeout_reset_events"], [timeout])

    def test_stale_incomplete_mismatched_conflicting_or_invalid_cycles_fail(self):
        identity, baseline, original = host_cycle_fixture()
        scenarios = []
        state = deepcopy(baseline); state["actual_joint"][5] = .1; scenarios.append((state, deepcopy(original)))
        state = deepcopy(baseline); state["planned_pose"][0] = .100002; scenarios.append((state, deepcopy(original)))
        state = deepcopy(baseline); state["stage"] = "running"; scenarios.append((state, deepcopy(original)))
        state = deepcopy(baseline); state["updated_monotonic_ns"] = 1_000_000_000; scenarios.append((state, deepcopy(original)))
        state = deepcopy(baseline); state["seq"] += 1; scenarios.append((state, deepcopy(original)))
        scenarios.append((deepcopy(baseline), deepcopy(original[1:])))
        scenarios.append((deepcopy(baseline), deepcopy(original[:-1])))
        for index, key, value in ((0, "type", "target"), (0, "execute_motion", False), (1, "profile_id", "changed"),
                                  (1, "robot_id", "OTHER"), (4, "flags", [1, 1, 0, 0, 0, 1]),
                                  (4, "program_before", [1]), (4, "program_after", [1]),
                                  (4, "speed", [0., 0., 0., 0., 0., .1])):
            rows = deepcopy(original); rows[index]["data"][key] = value; scenarios.append((deepcopy(baseline), rows))
        for kind, data in (("stationary_read_timeout", {}), ("pose_session_closed", {}),
                           ("tx_intent", {**original[0]["data"], "type": "target"})):
            rows = deepcopy(original)+[{"monotonic_ns": 2_150_000_000, "kind": kind, "data": data}]
            scenarios.append((deepcopy(baseline), rows))
        for index, (state, rows) in enumerate(scenarios):
            with self.subTest(index=index), self.assertRaises(ExecutionBlocked):
                self.prove(state, rows, expected_receiver=identity)

    def test_incomplete_next_idle_is_allowed_only_without_conflicting_new_measurement(self):
        _, state, rows = host_cycle_fixture()
        later = deepcopy(rows[:2])
        later[0]["monotonic_ns"], later[1]["monotonic_ns"] = 2_135_000_000, 2_140_000_000
        self.prove(state, rows+later)
        native = deepcopy(rows[-1]); native["monotonic_ns"] = 2_150_000_000
        native["data"]["pose"][0] = .2
        with self.assertRaises(ExecutionBlocked):
            self.prove(state, rows+later+[native])

    def test_file_capture_waits_for_new_publication_archives_exact_bytes_and_opens_no_native(self):
        identity, state, rows = host_cycle_fixture()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            runtime, output = root/"synthetic-runtime", root/"evidence"
            run = runtime/"runs"/"synthetic-current"
            run.mkdir(parents=True)
            (runtime/"current_session.json").write_bytes(encoded({"path": run.name}))
            old = {**state, "updated_monotonic_ns": 1_000_000_000}
            (run/"state.json").write_bytes(encoded(old))
            raw = journal_bytes(rows)
            (run/"events.jsonl").write_bytes(raw)
            fake_now = [2.2]
            def sleep(delay):
                fake_now[0] += delay
                (run/"state.json").write_bytes(encoded(state))
            journal = PrivateJournal(output)
            try:
                verifier = MagicMock(return_value={"server.py": b"synthetic verified source bytes"})
                observed = host_journal_native_capture(runtime, journal, expected_receiver=identity,
                    verifier=verifier, clock=lambda: 100., monotonic=lambda: fake_now[0],
                    monotonic_ns=lambda: int(fake_now[0]*1e9), sleep=sleep)
                self.assertEqual(observed.pose, pose(0))
                self.assertLess(observed.observed_at, 99.)
                verifier.assert_called_once_with(runtime)
                record = json.loads(next(output.glob("host-native-*.json")).read_bytes())
                import base64
                self.assertEqual(base64.b64decode(record["source_journal_bytes_base64"]), raw)
                self.assertEqual(record["source_journal_sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(record["extra_fc03_queries"], 0)
                (run/"command.json").write_bytes(b"{}")
                with self.assertRaises(ExecutionBlocked):
                    host_journal_native_capture(runtime, journal, verifier=verifier, max_wait_s=0,
                        publication_after_ns=1_000_000_000, monotonic=lambda: fake_now[0],
                        monotonic_ns=lambda: int(fake_now[0]*1e9))
            finally:
                journal.close()


if __name__ == "__main__":
    main()
