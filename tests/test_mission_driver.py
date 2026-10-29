"""Synthetic equipment-free tests of the config-backed physical port adapter."""
from dataclasses import asdict, replace
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.robot_control.coordinate_units import CoordinateBinding
from backend.robot_control.mission_catalog import (EvidenceReference, MeasuredPrimitive, MeasuredStage,
    PrimitiveQualification, content_hash)
from backend.robot_control.mission_driver import ConfigBackedMissionDriver, _StopAwareAPI
from backend.robot_control.mission_policy import (MissionPlan, ParkingTarget, RouteStep, SiteBinding, TaughtPrimitive)
from backend.robot_control.taught_executor import ExecutionBlocked, Frame, MotionReceipt, Snapshot
from tools.prepare_local_contact import build_profile


def pose(x, y=0, yaw=0):
    return (float(x), float(y), 7.4, -180., 0., float(yaw))


def binding():
    return CoordinateBinding("map", "v1", "a"*64, "b"*64, "tool", "car", "surface")


def deployment_status():
    from tests.test_taught_ports import synthetic_status
    status = synthetic_status()
    installation = status["installation"]
    installation.update(installation_id="site", tool_id="tool", car_id="car", surface_id="surface",
        workspace_min_mm=[-50., -50., 6.4], workspace_max_mm=[150., 50., 8.4],
        fixed_tcp_z_mm=7.4, fixed_orientation_deg=list(pose(0)[3:]))
    receiver = status["receiver"]
    receiver.update(actual_pose=list(pose(0)), actual_joint=[0.]*6,
                    session_id="new-session", seq=1, profile_id="new-profile")
    receiver["profile"] = build_profile(installation, {k:receiver[k] for k in ("actual_pose", "actual_joint")},
                                        on_site_review=True)
    return status


class SyntheticPorts:
    def __init__(self, **kwargs):
        self.adapter, self.journal = kwargs["adapter"], kwargs["journal"]
        self.intents, self.holds = [], []
        self.seq, self.pose, self.clock = 1, pose(0), 100.
        self.after_execute = None
        self.native_error = False
        self.frame_count = 0
        self.status = deployment_status()

    def now(self):
        return self.clock

    def _status(self):
        result = deepcopy(self.status)
        result["receiver"].update(actual_pose=list(self.pose), seq=self.seq)
        return result

    def snapshot(self):
        native = tuple((v+.5 if self.native_error and i == 0 else v) for i, v in enumerate(self.pose))
        return Snapshot("new-session", self.seq, "new-profile", "site", self.pose, (0.,)*6,
            native, "c"*64, self.clock, True, "local_contact_commissioning", "b"*64,
            "tool", "car", "surface", 20.)

    def capture(self):
        self.frame_count += 1
        raw = b"\xff\xd8original" + bytes([self.frame_count]) + b"\xff\xd9"
        return Frame(str(self.frame_count), "camera", self.frame_count, self.clock,
                     hashlib.sha256(raw).hexdigest(), raw)

    def hold(self, reason):
        self.holds.append(reason)

    def execute_once(self, intent):
        self.intents.append(intent)
        self.pose, self.seq = intent.target_base, self.seq + 1
        self.clock += 1
        if self.after_execute:
            self.after_execute()
        return MotionReceipt(intent.request_id, "new-session", self.seq, "new-profile", "site", True,
                             self.pose, "d"*64)


class SyntheticObserver:
    def __call__(self, state, driver):
        return {"summary": "synthetic"}

    def readiness(self, config):
        ready = config["measurement_adapter"].get("kind") == "synthetic_test_only"
        return {"ready": ready, "blockers": [] if ready else ["SYNTHETIC_MEASUREMENT_UNAVAILABLE"]}


def fixture(directory):
    ref = EvidenceReference("synthetic-source", "motion.json", "e"*64)
    def stage(i, phase, start, target):
        return MeasuredStage(str(i), phase, pose(start), pose(target), "historical-"+str(i), ref)
    p = MeasuredPrimitive("measured-contact", "coordinate_unit", (
        stage(1, "approach", 0, 10), stage(2, "contact", 10, 20), stage(3, "withdraw", 20, 15)),
        "PIZZA", "OFFICE_BUILDING", "Vehicle progresses towards the measured Office destination.",
        "PASS", True, (ref,), ("SYNTHETIC_TEST_ONLY",), True)
    ret = MeasuredPrimitive("measured-return", "empty_path", (stage(4, "empty", 15, 0),),
        "OFFICE_BUILDING", "START", "Empty tool returns along its separately measured corridor.",
        "MISSING", False, (ref,), ("SYNTHETIC_TEST_ONLY",))
    catalog = {"primitives": [p.to_dict()], "empty_paths": [ret.to_dict()]}
    cat_path = directory / "catalogue.private.json"
    cat_path.write_text(json.dumps(catalog))
    q = PrimitiveQualification(p.geometry_sha256, "site", "1"*64, "2"*64, "3"*64, "4"*64, True)
    qr = replace(q, primitive_geometry_sha256=ret.geometry_sha256)
    push = TaughtPrimitive("push", "START", "PARK", content_hash(asdict(q)), True)
    back = TaughtPrimitive("return", "PARK", "START", content_hash(asdict(qr)), True, True)
    site = SiteBinding("site", "a"*64, "registration", "tool", "car", "camera")
    plan = MissionPlan("template", "OFFICE_BUILDING", site,
        (RouteStep("goal", push, "office", 0., True),), ParkingTarget(0.), (back,), "START")
    workspace = {"destination": "OFFICE_BUILDING", "route_nodes": ["PIZZA", "OFFICE_BUILDING"],
                 "map_id": "map", "map_version": "v1", "map_hash": "a"*64}
    status = deployment_status()
    coverage = {"schema": "pushpilot.mission-profile-coverage.v1", "status": "accepted",
        "profile_sha256": content_hash(status["receiver"]["profile"]),
        "installation_sha256": content_hash(status["installation"]),
        "primitive_geometry_sha256": {"push":p.geometry_sha256, "return":ret.geometry_sha256},
        "clearance_review_sha256": "5"*64, "kinematic_review_sha256": "6"*64}
    config = {"schema": "pushpilot.physical-mission-driver.v1", "enabled": True,
        "site_binding": asdict(site), "coordinate_binding": asdict(binding()),
        "ports": {"camera_epoch": "camera", "registration_id": "registration", "native_observation_source": "host_journal"},
        "journal_root": str(directory / "journal"),
        "catalogue": {"path": str(cat_path), "sha256": hashlib.sha256(cat_path.read_bytes()).hexdigest()},
        "contexts": {"START": {"pose_base": list(pose(0)), "tool_clear": False},
                     "PARK": {"pose_base": list(pose(15)), "tool_clear": True}},
        "primitives": {"push": {"catalogue_id": p.id, "source_context_id": "START", "target_context_id": "PARK",
            "qualification": asdict(q), "qualification_sha256": push.qualification_sha256},
            "return": {"catalogue_id": ret.id, "source_context_id": "PARK", "target_context_id": "START",
                "qualification": asdict(qr), "qualification_sha256": back.qualification_sha256}},
        "routes": [{"workspace_binding": workspace, "plan": asdict(plan)}],
        "profile_coverage": {"record": coverage, "reference_sha256": content_hash(coverage)},
        "measurement_adapter": {"kind": "synthetic_test_only"}}
    path = directory / "driver.private.json"
    path.write_text(json.dumps(config))
    request = {**workspace, "workspace_session_id": "workspace", "plan_id": "approved-plan", "plan_revision": 2}
    return path, config, request


class DriverTests(unittest.TestCase):
    def make_driver(self, directory, *, edit=None):
        path, config, request = fixture(directory)
        if edit:
            edit(config)
            path.write_text(json.dumps(config))
        driver = ConfigBackedMissionDriver(path, SyntheticObserver(), port_factory=SyntheticPorts)
        self.addCleanup(driver.close)
        return driver, request

    def test_real_shape_configuration_and_exact_route_selection(self):
        with TemporaryDirectory() as temporary:
            driver, request = self.make_driver(Path(temporary))
            self.assertTrue(driver.readiness()["ready"])
            with self.assertRaises(ExecutionBlocked):
                driver.prepare({**request, "destination": "HANOK"})
            plan = driver.prepare(request)
            self.assertNotEqual(plan.id, "template")
            self.assertEqual(driver.context().context_id, "START")
            self.assertEqual(driver.ports.intents, [])
            driver.close()

    def test_coordinate_unit_and_separate_empty_return_use_new_commands(self):
        with TemporaryDirectory() as temporary:
            driver, request = self.make_driver(Path(temporary))
            driver.prepare(request)
            done = driver.execute("push", "new-logical-command")
            self.assertEqual(done.outcome, "COMPLETED")
            self.assertEqual(done.target_context_id, "PARK")
            self.assertEqual([i.target_base for i in driver.ports.intents], [pose(10), pose(20), pose(15)])
            self.assertEqual(len({i.request_id for i in driver.ports.intents}), 3)
            self.assertTrue(all(i.expected_receiver["profile_id"] == "new-profile" for i in driver.ports.intents))
            before = driver.before_frame
            driver.execute("return", "another-new-command")
            self.assertEqual(driver.context().context_id, "START")
            self.assertIs(driver.before_frame, before)
            driver.close()

    def test_stop_after_first_endpoint_never_dispatches_next_stage(self):
        with TemporaryDirectory() as temporary:
            driver, request = self.make_driver(Path(temporary))
            driver.prepare(request)
            driver.ports.after_execute = lambda: driver.hold("User Stop")
            with self.assertRaises(ExecutionBlocked):
                driver.execute("push", "new-command")
            self.assertEqual(len(driver.ports.intents), 1)
            self.assertTrue(driver.stop_latch.is_set())
            with self.assertRaises(ExecutionBlocked):
                driver.execute("push", "new-command-2")
            self.assertEqual(len(driver.ports.intents), 1)
            driver.close()

    def test_native_disagreement_holds_without_replay(self):
        with TemporaryDirectory() as temporary:
            driver, request = self.make_driver(Path(temporary))
            driver.prepare(request)
            driver.ports.after_execute = lambda: setattr(driver.ports, "native_error", True)
            with self.assertRaises(ExecutionBlocked):
                driver.execute("push", "native-failure")
            self.assertEqual(len(driver.ports.intents), 1)
            self.assertEqual(driver.pending_command_id, "native-failure")
            driver.close()

    def test_duplicate_logical_command_is_not_replayed_after_return(self):
        with TemporaryDirectory() as temporary:
            driver, request = self.make_driver(Path(temporary))
            driver.prepare(request)
            driver.execute("push", "same-command")
            driver.execute("return", "return-command")
            self.assertEqual(len(driver.ports.intents), 4)
            with self.assertRaises(ExecutionBlocked):
                driver.execute("push", "same-command")
            self.assertEqual(len(driver.ports.intents), 4)
            driver.close()

    def test_disabled_candidate_and_missing_measurement_never_open_ports(self):
        with TemporaryDirectory() as temporary:
            driver, _ = self.make_driver(Path(temporary), edit=lambda config:config.update(enabled=False))
            self.assertFalse(driver.readiness()["ready"])
            self.assertIsNone(driver.ports)
        with TemporaryDirectory() as temporary:
            driver, _ = self.make_driver(Path(temporary), edit=lambda config:config.update(measurement_adapter={"qualified": False}))
            self.assertFalse(driver.readiness()["ready"])
            self.assertIsNone(driver.ports)

    def test_current_xy_tolerance_retains_targets_but_z_change_is_rejected(self):
        with TemporaryDirectory() as temporary:
            driver, request = self.make_driver(Path(temporary))
            driver.readiness()
            driver.ports.pose = pose(.02)
            driver.prepare(request)
            driver.execute("push", "small-telemetry-offset")
            self.assertEqual(driver.ports.intents[0].start_base, pose(.02))
            self.assertEqual(driver.ports.intents[0].target_base, pose(10))
            driver.close()
        with TemporaryDirectory() as temporary:
            driver, request = self.make_driver(Path(temporary))
            driver.readiness()
            driver.ports.pose = (0., 0., 7.42, -180., 0., 0.)
            driver.prepare(request)
            with self.assertRaises(ExecutionBlocked):
                driver.execute("push", "z-changed")
            self.assertEqual(driver.ports.intents, [])
            driver.close()

    def test_stop_latch_rechecked_at_final_arm_and_post_boundary(self):
        import threading
        class API:
            def __init__(self): self.paths = []
            def call(self, path, *args, **kwargs): self.paths.append(path)
        api, latch = API(), threading.Event()
        guard = _StopAwareAPI(api, latch)
        guard.call("/v1/arm", {})
        latch.set()
        with self.assertRaises(ExecutionBlocked):
            guard.call("/v1/commands", {})
        guard.call("/v1/hold", {})
        self.assertEqual(api.paths, ["/v1/arm", "/v1/hold"])

    def test_configuration_flag_cannot_replace_executable_measurement_adapter(self):
        with TemporaryDirectory() as temporary:
            driver, _ = self.make_driver(Path(temporary))
            driver.observer_callback = lambda state, driver: {"summary": "no numeric estimator"}
            result = driver.readiness()
            self.assertFalse(result["ready"])
            self.assertIn("EXECUTABLE_MEASUREMENT_ADAPTER_REQUIRED", result["reasons"])
            self.assertIsNone(driver.ports)

    def test_concurrent_stop_during_prepare_cannot_be_cleared(self):
        with TemporaryDirectory() as temporary:
            driver, request = self.make_driver(Path(temporary))
            driver.readiness()
            original = driver.ports.snapshot
            def snapshot():
                driver.hold("Concurrent user Stop")
                return original()
            driver.ports.snapshot = snapshot
            with self.assertRaises(ExecutionBlocked):
                driver.prepare(request)
            self.assertTrue(driver.stop_latch.is_set())
            self.assertEqual(driver.ports.intents, [])
            driver.close()

    def test_contact_geometry_cannot_be_labelled_empty_tool(self):
        with TemporaryDirectory() as temporary:
            def edit(config):
                config["routes"][0]["plan"]["steps"][0]["primitive"]["empty_tool"] = True
            driver, _ = self.make_driver(Path(temporary), edit=edit)
            self.assertFalse(driver.readiness()["ready"])
            self.assertIn("contact trajectory", driver.readiness()["detail"])
            self.assertIsNone(driver.ports)

    def test_wrist_admission_preserves_directed_joint_and_literal_pose_edge(self):
        from types import SimpleNamespace
        ref = EvidenceReference("synthetic-source", "wrist.json", "e"*64)
        stage = MeasuredStage("wrist", "wrist", pose(0), pose(0, yaw=90), "old-wrist", ref)
        wrist = {"edge_id": "east-north", "expected_source_joint_deg": [0.]*6,
                 "expected_target_joint_deg": [0., 0., 0., 0., 0., -90.],
                 "rotation_runtime_sha256": "f"*64}
        edge = {"id": wrist["edge_id"], "expected_source_joint_deg": [0.]*6,
                "expected_target_joint_deg": wrist["expected_target_joint_deg"],
                "source_orientation_deg": pose(0)[3:], "target_orientation_deg": pose(0, yaw=90)[3:]}
        snapshot = SimpleNamespace(reviewed_rotation_edges=(edge,), rotation_runtime_sha256="f"*64,
                                   joints_deg=(0.,)*6, tcp_base=pose(0))
        ConfigBackedMissionDriver._validate_wrist(snapshot, stage, wrist)
        with self.assertRaises(ExecutionBlocked):
            ConfigBackedMissionDriver._validate_wrist(snapshot, stage,
                {**wrist, "expected_target_joint_deg": [0., 0., 0., 0., 0., 90.]})
        with self.assertRaises(ExecutionBlocked):
            ConfigBackedMissionDriver._validate_wrist(snapshot,
                replace(stage, target_base=pose(0, yaw=-270)), wrist)
        snapshot.joints_deg = (0., 0., 0., 0., 0., 2.)
        with self.assertRaises(ExecutionBlocked):
            ConfigBackedMissionDriver._validate_wrist(snapshot, stage, wrist)

    def test_current_profile_change_is_detected_in_context_before_motion(self):
        with TemporaryDirectory() as temporary:
            driver, request = self.make_driver(Path(temporary))
            driver.prepare(request)
            driver.ports.status["receiver"]["profile"]["max_translation_mm"] = 2.
            with self.assertRaises(ExecutionBlocked) as raised:
                driver.context()
            self.assertEqual(raised.exception.code, "CURRENT_PROFILE_NOT_REVIEWED")
            self.assertEqual(driver.ports.intents, [])
            driver.close()

    def test_bound_profile_review_does_not_skip_pure_whole_route_admission(self):
        with TemporaryDirectory() as temporary:
            small = deployment_status()
            small["receiver"]["profile"]["max_translation_mm"] = 2.
            def edit(config):
                coverage = config["profile_coverage"]
                coverage["record"]["profile_sha256"] = content_hash(small["receiver"]["profile"])
                coverage["reference_sha256"] = content_hash(coverage["record"])
            driver, _ = self.make_driver(Path(temporary), edit=edit)
            driver._ensure_ports()
            driver.ports.status = small
            result = driver.readiness()
            self.assertFalse(result["ready"])
            self.assertIn("PROFILE_ROUTE_COVERAGE_FAILED", result["reasons"])
            self.assertEqual(driver.ports.intents, [])
            driver.close()

    def test_missing_profile_coverage_is_unavailable_without_opening_ports(self):
        with TemporaryDirectory() as temporary:
            driver, _ = self.make_driver(Path(temporary), edit=lambda config: config.pop("profile_coverage"))
            self.assertFalse(driver.readiness()["ready"])
            self.assertIsNone(driver.ports)

    def test_stop_during_final_profile_check_prevents_arm(self):
        import threading
        class API:
            def __init__(self): self.paths = []
            def call(self, path, *args, **kwargs): self.paths.append(path); return {}
        api, latch = API(), threading.Event()
        guard = _StopAwareAPI(api, latch, lambda status: latch.set())
        with self.assertRaises(ExecutionBlocked):
            guard.call("/v1/arm", {})
        self.assertEqual(api.paths, ["/v1/status"])


if __name__ == "__main__":
    unittest.main()
