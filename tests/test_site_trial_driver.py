"""Equipment-free current-site driver integration with actual admission guards."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from backend.robot_control.coordinate_units import CoordinateBinding
from backend.robot_control.mission_catalog import content_hash
from backend.robot_control.mission_policy import SiteBinding, MissionPolicy, Phase, DecisionKind
from backend.robot_control.mission_profile import resolve_wrist_descriptor
from backend.robot_control.site_trial_driver import SiteTrialMissionDriver, packet_primitive
from backend.robot_control.taught_executor import ExecutionBlocked, Frame, MotionReceipt
from backend.robot_control.taught_ports import PrivateJournal
from tests.test_mission_profile import FakeGuardedAPI, SOURCE, JOINTS, installation, review, unit, wrist_intent, wrist_descriptor
from backend.robot_control.wrist_commissioning import propose_wrist_turn


class SiteAPI(FakeGuardedAPI):
    def call(self, path, payload=None):
        return self(path, payload)

    def __call__(self, path, payload=None):
        if path in {"/v1/arm", "/v1/hold"}:
            self.calls.append((path, deepcopy(payload)))
            return {}
        if path == "/v1/commands" and payload["kind"] in {"translate", "rotate"}:
            from backend.robot_control.gates import admit
            receiver = self.status["receiver"]
            admit(payload, self.status["installation"], receiver, None, armed=True, held=False,
                  now=1000., require_profile_binding=True)
            self.calls.append((path, deepcopy(payload)))
            receiver["actual_pose"] = list(payload["target"])
            receiver["seq"] += 1
            if payload["kind"] == "rotate":
                edge = next(e for e in receiver["profile"]["rotation_edges"] if e["id"] == payload["edge_id"])
                receiver["actual_joint"] = list(edge["expected_target_joint_deg"])
            return {}
        return super().__call__(path, payload)


class SitePorts:
    created = 0

    def __init__(self, **kwargs):
        type(self).created += 1
        self.adapter, self.journal = kwargs["adapter"], kwargs["journal"]
        self.raw = SiteAPI()
        self.api = self.raw
        self.intents, self.holds, self.frame_count = [], [], 0
        self.after_execute = None

    def now(self):
        return time.time()

    def _status(self):
        return self.api.call("/v1/status")

    def _camera_status(self):
        return {"ready": True}

    def snapshot(self):
        value = self.raw.native()
        profile = self.raw.status["receiver"]["profile"]
        orientations = {row["id"]: row["rxyz_deg"] for row in profile.get("orientations", ())}
        edges = tuple({**edge, "source_orientation_deg": orientations[edge["from"]],
            "target_orientation_deg": orientations[edge["to"]]} for edge in profile.get("rotation_edges", ()))
        return replace(value, native_observed_at=self.now(),
            reviewed_rotation_edges=edges,
            rotation_runtime_sha256=content_hash(profile["rotation_runtime"]) if "rotation_runtime" in profile else None)

    def capture(self):
        self.frame_count += 1
        jpeg = b"\xff\xd8synthetic" + str(self.frame_count).encode() + b"\xff\xd9"
        return Frame(str(self.frame_count), "camera", self.frame_count, self.now(), hashlib.sha256(jpeg).hexdigest(), jpeg)

    def hold(self, reason):
        self.holds.append(reason)
        self.api.call("/v1/hold", {"reason": reason})

    def execute_once(self, intent):
        self.intents.append(intent)
        command = {"request_id": intent.request_id, "kind": intent.kind, "purpose": intent.purpose,
            "installation_id": intent.installation_id, "expected_receiver": intent.expected_receiver,
            "target": list(intent.target_base), "expected_visual": intent.expected_visual}
        if intent.edge_id:
            command["edge_id"] = intent.edge_id
        self.api.call("/v1/arm", {})
        self.api.call("/v1/commands", command)
        receiver = self.raw.status["receiver"]
        if self.after_execute:
            self.after_execute()
        return MotionReceipt(intent.request_id, receiver["session_id"], receiver["seq"], receiver["profile_id"],
            self.raw.status["installation"]["installation_id"], True, tuple(receiver["actual_pose"]), "d"*64)


class Observer:
    def readiness(self, config):
        return {"ready": True, "blockers": []}

    def __call__(self, state, driver):
        return {"summary": "Synthetic observation only."}


def fixture(directory):
    measured = unit()
    rows = {"push": {"id": "push", "kind": "coordinate_unit", "source_context_id": "START",
        "target_context_id": "PARK", "expected_visual": measured.expected_visual, "empty_tool": False,
        "contact_travel_limit_mm": 20., "stages": [{"id": s.id, "phase": s.phase,
            "start_base": list(s.start_base), "target_base": list(s.target_base)} for s in measured.stages]},
        "return": {"id": "return", "kind": "empty_path", "source_context_id": "PARK", "target_context_id": "START",
            "expected_visual": "The car remains stationary during the empty return.", "empty_tool": True,
            "stages": [{"id": "back", "phase": "empty", "start_base": list(measured.stages[-1].target_base),
                        "target_base": list(SOURCE)}]}}
    packet = {"schema": "pushpilot.current-site-delivery-packet.v1", "repeatability_qualified": False,
        "contexts": {"START": {"pose_base": list(SOURCE), "tool_clear": False},
                     "PARK": {"pose_base": list(measured.stages[-1].target_base), "tool_clear": True}},
        "primitives": rows, "routes": {"B": {"destination": "OFFICE_BUILDING", "blockers": [],
            "steps": [{"id": "goal", "primitive_id": "push", "car_zone_id": "office", "expected_heading_deg": 0., "at_goal": True}],
            "empty_return": ["return"], "start_context_id": "START",
            "parking": {"heading_deg": 0., "mode": "delivery_only"}}}}
    path = directory / "packet.private.json"
    path.write_text(json.dumps(packet))
    reference = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    supplied = review()
    supplied["allowed_geometry_sha256"] = [packet_primitive(row, reference).geometry_sha256 for row in rows.values()]
    reviewpath = directory / "review.private.json"
    reviewpath.write_text(json.dumps(supplied))
    physical = installation()
    site = SiteBinding("logical-site", "b"*64, "registration", physical["tool_id"], physical["car_id"], "camera")
    coordinate = CoordinateBinding("map", "v1", "b"*64, physical["tcp_definition_sha256"],
                                   physical["tool_id"], physical["car_id"], physical["surface_id"])
    workspace = {"destination": "OFFICE_BUILDING", "route_nodes": ["PIZZA", "OFFICE_BUILDING"],
        "map_id": "map", "map_version": "v1", "map_hash": "b"*64}
    config = {"schema": "pushpilot.site-trial-driver.v1", "enabled": True,
        "site_binding": asdict(site), "coordinate_binding": asdict(coordinate),
        "ports": {"native_observation_source": "host_journal", "camera_epoch": "camera", "registration_id": "registration",
                  "runtime": "synthetic-never-loaded"}, "journal_root": str(directory / "journal"),
        "packet": reference, "profile_review": {"path": str(reviewpath), "sha256": hashlib.sha256(reviewpath.read_bytes()).hexdigest()},
        "workspace_bindings": {"B": workspace}, "measurement_adapter": {"kind": "synthetic-test-only"},
        "observations": {}, "wrist_intents": {}}
    configpath = directory / "driver.private.json"
    configpath.write_text(json.dumps(config))
    request = {**workspace, "workspace_session_id": "workspace", "plan_id": "approved", "plan_revision": 1}
    return configpath, config, packet, supplied, request


def save_artifact(reference, data):
    path = Path(reference["path"])
    path.write_text(json.dumps(data))
    reference["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


class SiteTrialTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runtime = patch("backend.robot_control.site_trial_driver.load_runtime", return_value={
            "policy": SimpleNamespace(MAX_PROFILE_BYTES=65536, valid=lambda *args: None)})
        self.runtime.start()
        self.addCleanup(self.runtime.stop)

    def driver(self, *, edit=None):
        path, config, packet, supplied, request = fixture(self.root)
        if edit:
            edit(config, packet, supplied)
            save_artifact(config["packet"], packet)
            save_artifact(config["profile_review"], supplied)
            path.write_text(json.dumps(config))
        driver = SiteTrialMissionDriver(path, Observer(), port_factory=SitePorts)
        self.addCleanup(driver.close)
        return driver, request

    def test_prepares_each_exact_unit_and_separates_actual_from_logical_installation(self):
        driver, request = self.driver()
        self.assertTrue(driver.readiness()["ready"], driver.readiness())
        plan = driver.prepare(request)
        self.assertEqual(plan.release_mode, "site_trial")
        self.assertFalse(plan.steps[0].primitive.qualified)
        first = driver.execute("push", "push-command")
        first_installation = driver.actual_installation_id
        self.assertEqual(first.outcome, "COMPLETED")
        self.assertNotEqual(first_installation, driver.binding.installation_id)
        driver.execute("return", "return-command")
        self.assertNotEqual(first_installation, driver.actual_installation_id)
        self.assertEqual(driver.context().binding.installation_id, "logical-site")
        self.assertEqual(driver.context().context_id, "START")
        commands = [v for p, v in driver.raw_api.calls if p == "/v1/commands"]
        self.assertEqual(sum(c["kind"] == "profile_update" for c in commands), 2)
        self.assertEqual(len(driver.ports.intents), 4)
        self.assertTrue(all(i.installation_id.startswith("mission-unit-") for i in driver.ports.intents))

    def test_duplicate_command_does_not_even_prepare_another_profile(self):
        driver, request = self.driver()
        driver.prepare(request)
        driver.execute("push", "same-command")
        driver.execute("return", "return-command")
        count = len(driver.raw_api.calls)
        with self.assertRaises(ExecutionBlocked):
            driver.execute("push", "same-command")
        self.assertFalse(any(p in {"/v1/commands", "/v1/installation", "/v1/arm"}
                             for p, _ in driver.raw_api.calls[count:]))

    def test_profile_failure_cannot_be_bypassed_by_new_start(self):
        driver, request = self.driver()
        driver.prepare(request)
        driver.raw_api.failure = "bad-ik"
        with self.assertRaises(ExecutionBlocked):
            driver.execute("push", "bad-profile")
        self.assertEqual(driver.ports.intents, [])
        self.assertFalse(driver.readiness()["ready"])
        with self.assertRaises(ExecutionBlocked):
            driver.prepare(request)

    def test_stop_during_preparation_prevents_installation_and_motion(self):
        driver, request = self.driver()
        driver.prepare(request)
        driver.raw_api.after_call = lambda _: driver.hold("Synthetic stop during query")
        with self.assertRaises(ExecutionBlocked):
            driver.execute("push", "stopped-profile")
        self.assertEqual(driver.ports.intents, [])
        self.assertFalse(any(p == "/v1/installation" for p, _ in driver.raw_api.calls))

    def test_stop_after_motion_blocks_next_stage_and_restart(self):
        driver, request = self.driver()
        driver.prepare(request)
        driver.ports.after_execute = lambda: driver.hold("Synthetic stop after endpoint")
        with self.assertRaises(ExecutionBlocked):
            driver.execute("push", "stop-motion")
        self.assertEqual(len(driver.ports.intents), 1)
        path = driver.config_file
        driver.close()
        restarted = SiteTrialMissionDriver(path, Observer(), port_factory=SitePorts)
        self.addCleanup(restarted.close)
        self.assertFalse(restarted.readiness()["ready"])
        self.assertIsNone(restarted.ports)
        self.assertIn("SITE_TRIAL_RECONCILIATION_REQUIRED", restarted.readiness()["reasons"])

    def test_failed_port_initialization_never_leaves_a_bypassable_partial_driver(self):
        driver, _ = self.driver()
        with patch("backend.robot_control.site_trial_driver.load_runtime", side_effect=ValueError("Synthetic missing runtime")):
            self.assertFalse(driver.readiness()["ready"])
            self.assertIsNone(driver.ports)
            self.assertIsNone(driver.journal)
            self.assertFalse(driver.readiness()["ready"])

    def test_external_profile_change_and_pending_receiver_inhibit_readiness(self):
        driver, request = self.driver()
        driver.prepare(request)
        driver.raw_api.status["receiver"]["profile"]["max_translation_mm"] = 1.
        self.assertFalse(driver.readiness()["ready"])
        with self.assertRaises(ExecutionBlocked):
            driver.execute("push", "changed-profile")
        self.assertEqual(driver.ports.intents, [])

    def test_site_context_map_empty_labels_and_runtime_hash_mismatch_reject_before_ports(self):
        cases = [lambda c,p,r: c["coordinate_binding"].update(surface_id="other"),
                 lambda c,p,r: p["contexts"]["PARK"]["pose_base"].__setitem__(0, 11.),
                 lambda c,p,r: c["workspace_bindings"]["B"].update(map_hash="e"*64),
                 lambda c,p,r: p["primitives"]["push"].update(empty_tool=True),
                 lambda c,p,r: r.update(allowed_geometry_sha256=["f"*64]),
                 lambda c,p,r: p.update(blockers=["UNRESOLVED_LITERAL_SOURCE_CONTEXT_JOIN"])]
        for i, edit in enumerate(cases):
            with self.subTest(case=i):
                driver, _ = self.driver(edit=edit)
                ready = driver.readiness()
                self.assertFalse(ready["ready"])
                self.assertIn("PHYSICAL_CONFIGURATION_INVALID", ready["reasons"], ready)
                self.assertIsNone(driver.ports)

    def test_wrong_route_never_opens_profile_or_motion_commands(self):
        driver, request = self.driver()
        with self.assertRaises(ExecutionBlocked):
            driver.prepare({**request, "destination": "HANOK"})
        self.assertFalse(any(p in {"/v1/commands", "/v1/installation"} for p, _ in driver.raw_api.calls))

    def test_semantic_wrist_preparation_binds_actual_profile_edges_for_driver_dispatch(self):
        def edit(config, packet, supplied):
            target = propose_wrist_turn(SOURCE, JOINTS, 89.999)["target_pose"]
            packet["contexts"]["START"]["tool_clear"] = True
            packet["contexts"]["NORTH_START"] = {"pose_base": target, "tool_clear": True}
            packet["contexts"]["PARK"]["pose_base"][3:] = target[3:]
            for row in packet["primitives"].values():
                for stage in row["stages"]:
                    stage["start_base"][3:] = target[3:]
                    stage["target_base"][3:] = target[3:]
            packet["primitives"]["push"]["source_context_id"] = "NORTH_START"
            packet["primitives"]["return"]["target_context_id"] = "NORTH_START"
            packet["primitives"]["wrist"] = {"id": "wrist", "kind": "wrist_edge", "source_context_id": "START",
                "target_context_id": "NORTH_START", "empty_tool": True,
                "expected_visual": "The car remains unchanged during the unloaded wrist reorientation.",
                "stages": [{"id": "wrist", "phase": "wrist", "start_base": list(SOURCE), "target_base": target}]}
            packet["primitives"]["restore"] = {"id": "restore", "kind": "wrist_edge", "source_context_id": "NORTH_START",
                "target_context_id": "START", "empty_tool": True,
                "expected_visual": "The delivered car remains unchanged during unloaded restoration.",
                "stages": [{"id": "restore", "phase": "wrist", "start_base": target, "target_base": list(SOURCE)}]}
            packet["routes"]["B"]["steps"].insert(0, {"id": "rotate", "primitive_id": "wrist", "car_zone_id": "start",
                "expected_heading_deg": 0., "at_goal": False})
            packet["routes"]["B"]["empty_return"].append("restore")
            config["wrist_intents"] = {"wrist": wrist_intent(), "restore": {**wrist_intent(), "edge_id": "restore", "delta_j6_deg": -89.999}}
            supplied["unloaded_wrist_authorized"] = True
            supplied["wrist_descriptor_sha256s"] = [content_hash(v) for v in config["wrist_intents"].values()]
            supplied["allowed_geometry_sha256"] = [packet_primitive(row, config["packet"]).geometry_sha256
                for row in packet["primitives"].values()]
        driver, request = self.driver(edit=edit)
        plan = driver.prepare(request)
        driver.raw_api.wrist = wrist_descriptor()
        self.assertFalse(plan.steps[0].observation_required)
        result = driver.execute("wrist", "fresh-wrist")
        self.assertEqual(result.outcome, "COMPLETED")
        self.assertEqual(driver.context().context_id, "NORTH_START")
        intent = driver.ports.intents[0]
        self.assertEqual(intent.kind, "rotate")
        self.assertEqual(intent.expected_source_joint_deg, JOINTS)
        self.assertEqual(intent.rotation_runtime_sha256, content_hash(driver.raw_api.status["receiver"]["profile"]["rotation_runtime"]))
        self.assertEqual(driver.config["primitives"]["wrist"]["wrist"]["edge_id"], wrist_intent()["edge_id"])

    def test_complete_deployment_reload_before_first_start_preserves_stop_and_rechecks_hashes(self):
        driver, request = self.driver()
        self.assertTrue(driver.readiness()["ready"])
        old_api = driver.raw_api
        config = json.loads(driver.config_file.read_bytes())
        config["site_binding"]["calibration_id"] = "updated-registration"
        config["ports"]["registration_id"] = "updated-registration"
        driver.config_file.write_text(json.dumps(config))
        self.assertTrue(driver.readiness()["ready"])
        self.assertEqual(driver.binding.calibration_id, "updated-registration")
        self.assertIsNot(driver.raw_api, old_api)
        self.assertTrue(driver.stop_latch.is_set())
        self.assertIsNone(driver.currentplan)
        self.assertFalse(any(path in {"/v1/hold", "/v1/arm", "/v1/commands"} for path, _ in old_api.calls))
        # An invalid referenced file hash disables the next attempted reload.
        config["packet"]["sha256"] = "0"*64
        driver.config_file.write_text(json.dumps(config))
        self.assertFalse(driver.readiness()["ready"])
        self.assertIsNone(driver.ports)
        self.assertIn("artifact changed", driver._configuration_error)

    def test_return_wrist_chain_uses_clear_posture_contexts_without_assuming_initial_start_clear(self):
        def edit(config, packet, supplied):
            east_park = packet["contexts"]["PARK"]["pose_base"]
            north_park = propose_wrist_turn(east_park, JOINTS, 89.999)["target_pose"]
            north_start = [*SOURCE[:3], *north_park[3:]]
            packet["contexts"].update(NORTH_PARK={"pose_base": north_park, "tool_clear": True},
                                      NORTH_START={"pose_base": north_start, "tool_clear": True})
            packet["primitives"]["return"].update(source_context_id="NORTH_PARK", target_context_id="NORTH_START")
            packet["primitives"]["return"]["stages"][0].update(start_base=north_park, target_base=north_start)
            for pid, source, target, first, last in (
                    ("return-turn", "PARK", "NORTH_PARK", east_park, north_park),
                    ("restore", "NORTH_START", "START", north_start, list(SOURCE))):
                packet["primitives"][pid] = {"id": pid, "kind": "wrist_edge", "source_context_id": source,
                    "target_context_id": target, "empty_tool": True,
                    "expected_visual": "The delivered car remains at its destination during unloaded orientation restoration.",
                    "stages": [{"id": pid, "phase": "wrist", "start_base": first, "target_base": last}]}
            packet["routes"]["B"]["empty_return"] = ["return-turn", "return", "restore"]
            config["wrist_intents"] = {"return-turn": wrist_intent(),
                "restore": {**wrist_intent(), "edge_id": "restore", "delta_j6_deg": -89.999}}
            supplied["unloaded_wrist_authorized"] = True
            supplied["wrist_descriptor_sha256s"] = [content_hash(v) for v in config["wrist_intents"].values()]
            supplied["allowed_geometry_sha256"] = [packet_primitive(row, config["packet"]).geometry_sha256
                for row in packet["primitives"].values()]
        driver, request = self.driver(edit=edit)
        plan = driver.prepare(request)
        self.assertFalse(driver.context().tool_clear)
        driver.execute("push", "delivery-before-return")
        policy = MissionPolicy(plan)
        state = replace(policy.initial_state(driver.context().session_id), phase=Phase.RETURNING,
                        start_verified=True, vehicle_delivered=True)
        for number, primitive in enumerate(plan.empty_return):
            context = driver.context()
            self.assertTrue(context.tool_clear)
            decision = policy.decide(state, context, command_id="return-test-" + str(number))
            self.assertEqual(decision.kind, DecisionKind.DISPATCH, decision.reason)
            if primitive.id in driver.config["wrist_intents"]:
                snapshot = driver._snapshot()
                driver.raw_api.wrist = resolve_wrist_descriptor(driver.measured[primitive.id], driver.profile_review,
                    snapshot.tcp_base, snapshot.joints_deg, driver.config["wrist_intents"][primitive.id])
            receipt = driver.execute(decision.primitive_id, decision.command_id)
            state = policy.accept_receipt(decision.state, receipt)
        context = driver.context()
        self.assertEqual(context.context_id, "START")
        self.assertFalse(context.tool_clear)
        self.assertEqual(policy.decide(state, context).kind, DecisionKind.COMPLETE)
        self.assertFalse(driver.config["contexts"]["START"]["tool_clear"])

    def test_active_or_stopped_plan_and_unresolved_journal_cannot_be_replaced_by_reload(self):
        driver, request = self.driver()
        driver.prepare(request)
        original_binding = driver.binding
        config = json.loads(driver.config_file.read_bytes())
        config["site_binding"]["calibration_id"] = "must-not-load"
        config["ports"]["registration_id"] = "must-not-load"
        driver.config_file.write_text(json.dumps(config))
        driver.readiness()
        self.assertEqual(driver.binding, original_binding)
        driver.hold("Synthetic user HOLD")
        driver.readiness()
        self.assertEqual(driver.binding, original_binding)
        self.assertTrue(driver.stop_latch.is_set())
        driver.journal.checkpoint({"state": "DISPATCH_UNRESOLVED", "automatic_replay": False})
        driver.close()
        restarted = SiteTrialMissionDriver(driver.config_file, Observer(), port_factory=SitePorts)
        self.addCleanup(restarted.close)
        config["site_binding"]["calibration_id"] = "another-updated-registration"
        config["ports"]["registration_id"] = "another-updated-registration"
        driver.config_file.write_text(json.dumps(config))
        result = restarted.readiness()
        self.assertFalse(result["ready"])
        self.assertIn("SITE_TRIAL_RECONCILIATION_REQUIRED", result["reasons"])
        self.assertEqual(restarted.binding.calibration_id, "must-not-load")
        self.assertIsNone(restarted.ports)

    def test_explicit_no_motion_reconciliation_permits_config_reload_without_replay(self):
        driver, request = self.driver()
        self.assertTrue(driver.readiness()["ready"])
        driver.journal.checkpoint({"state": "RECONCILED_STATIONARY_NO_MOTION",
            "original_failed_operation": "synthetic-inspection-only-failure",
            "evidence_sha256": "e"*64, "automatic_replay": False})
        old_api = driver.raw_api
        config = json.loads(driver.config_file.read_bytes())
        config["site_binding"]["calibration_id"] = "reconciled-registration"
        config["ports"]["registration_id"] = "reconciled-registration"
        driver.config_file.write_text(json.dumps(config))
        self.assertTrue(driver.readiness()["ready"])
        self.assertEqual(driver.binding.calibration_id, "reconciled-registration")
        self.assertTrue(driver.stop_latch.is_set())
        self.assertIsNone(driver.currentplan)
        for api in (old_api, driver.raw_api):
            self.assertFalse(any(path in {"/v1/arm", "/v1/commands"} for path, _ in api.calls))
        self.assertEqual(driver.journal.load()["state"], "RECONCILED_STATIONARY_NO_MOTION")


if __name__ == "__main__":
    unittest.main()
