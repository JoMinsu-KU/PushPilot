"""Synthetic guarded profile preparation; no hardware, sockets or approvals."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from backend.robot_control.gates import admit
from backend.robot_control.mission_catalog import EvidenceReference, MeasuredPrimitive, MeasuredStage, content_hash
from backend.robot_control.mission_driver import ConfigBackedMissionDriver
from backend.robot_control.legacy import load_runtime
from backend.robot_control.mission_profile import ReviewedProfilePreparer, build_unit_profile, resolve_wrist_descriptor, validate_site_review
from backend.robot_control.taught_executor import ExecutionBlocked, Snapshot
from backend.robot_control.taught_ports import PrivateJournal
from backend.robot_control.wrist_commissioning import propose_wrist_turn
from tools.prepare_local_contact import build_profile


def installation():
    return {"scope": "local_contact_commissioning", "installation_id": "synthetic-current",
        "tcp_id": "synthetic-tcp", "tcp_definition_sha256": "a"*64, "tool_id": "synthetic-tool",
        "payload_kg": .1, "review_reference": "Synthetic old site review; not physical evidence.",
        "qualified": True, "on_site_review": True, "workspace_min_mm": [-30., -30., 99.],
        "workspace_max_mm": [30., 30., 101.], "fixed_tcp_z_mm": 100.,
        "fixed_orientation_deg": [180., 0., 0.], "tcp_clearance_margin_mm": 0.,
        "inflated_keepout_boxes_base_mm": [], "max_step_mm": 20., "max_speed_mm_s": 5.,
        "max_accel_mm_s2": 10., "car_id": "synthetic-car", "surface_id": "synthetic-surface",
        "reported_car_dimensions_mm": [45., 18., 15.], "contact_trials_authorized": True,
        "trial_max_step_mm": 20.}


SOURCE = (0., 0., 100., 180., 0., 0.)
JOINTS = (0., -20., 40., 0., 10., 0.)
# Actual mixed-precision numbers from the stationary inspect_current failure.
# They test representation matching, not physical motion or qualification.
NATIVE_JOINTS = (-85.6, -138.1, -57.9, -74., 90., -150.8)
INSPECTED_JOINTS = (-85.5573356, -138.0590941, -57.9153533,
                    -74.0365389, 89.9933647, -150.8881884)
EVIDENCE = EvidenceReference("SYNTHETIC", "not-real-evidence", "b"*64)


def unit(*, wrist=False):
    points = (SOURCE, (10., 0., *SOURCE[2:]), (20., 0., *SOURCE[2:]), (10., 0., *SOURCE[2:]))
    stages = tuple(MeasuredStage(str(i), phase, a, b, "synthetic-request-"+str(i), EVIDENCE)
        for i, (phase, a, b) in enumerate(zip(("approach", "contact", "withdraw"), points, points[1:])))
    if wrist:
        proposal = propose_wrist_turn(SOURCE, JOINTS, 89.999)
        stages = (MeasuredStage("wrist", "wrist", SOURCE, tuple(proposal["target_pose"]), "synthetic-wrist", EVIDENCE),)
    return MeasuredPrimitive("synthetic-unit", "wrist_edge" if wrist else "coordinate_unit", stages,
        "START", "PARK", "Synthetic bounded outcome.", "PASS", False, (EVIDENCE,), ())


def wrist_descriptor():
    proposal = propose_wrist_turn(SOURCE, JOINTS, 89.999)
    return {"edge_id": "synthetic-directed-edge", "expected_source_joint_deg": proposal["source_joint"],
        "expected_target_joint_deg": proposal["target_joint"], "unloaded": True,
        "rotation_runtime": {"verified": True, "primitive": "moveJoint_wrist", "controller_version": "synthetic",
            "argument_semantics": "Synthetic runtime semantics, never physical qualification.",
            "speed_argument": 5., "accel_argument": 10., "completion_timeout_s": 120.,
            "review_reference": "Synthetic unchanged runtime review; no physical evidence."}}


def wrist_intent():
    literal = wrist_descriptor()
    return {"edge_id": literal["edge_id"], "delta_j6_deg": 89.999,
            "rotation_runtime": literal["rotation_runtime"], "unloaded": True}


def review(measured=None, wrist=None):
    old = installation()
    return {"schema": "pushpilot.current-site-profile-review.v1", "status": "accepted_current_site_experiment",
        "operator_authorization_sha256": "c"*64, "review_reference": "Synthetic operator-reviewed geometry; not physical evidence.",
        "site": {k: old[k] for k in ("tcp_id", "tcp_definition_sha256", "tool_id", "car_id", "surface_id", "payload_kg", "fixed_tcp_z_mm")},
        "workspace_min_mm": [-30., -30., 99.], "workspace_max_mm": [30., 30., 101.],
        "allowed_geometry_sha256": [(measured or unit()).geometry_sha256],
        "max_speed_mm_s": 5., "max_accel_mm_s2": 10., "max_step_mm": 20.,
        "unloaded_wrist_authorized": wrist is not None,
        "wrist_descriptor_sha256s": [content_hash(wrist)] if wrist else []}


class FakeGuardedAPI:
    def __init__(self, wrist=None):
        local = installation()
        profile = build_profile(local, {"actual_pose": list(SOURCE), "actual_joint": list(JOINTS)}, on_site_review=True)
        self.status = {"installation": local, "hold": True, "armed": False, "active_commands": [],
            "receiver": {"actual_pose": list(SOURCE), "actual_joint": list(JOINTS), "session_id": "session",
                "seq": 1, "profile_id": content_hash(profile), "profile": profile,
                "connected": True, "idle": True, "physical_execution": True}}
        self.jobs, self.calls = {}, []
        self.wrist, self.failure, self.after_call = wrist, None, None
        self.inspected_joints, self.target_inspection_joints = None, None
        self.query_validator, self.ik_baseline = None, False

    def __call__(self, path, payload=None):
        self.calls.append((path, deepcopy(payload)))
        if path == "/v1/status":
            return deepcopy(self.status)
        if path == "/v1/installation":
            self.status["installation"] = deepcopy(payload)
            return deepcopy(payload)
        if path == "/v1/commands":
            receiver = self.status["receiver"]
            admit(payload, self.status["installation"], receiver, None, armed=False, held=True,
                  now=1000., require_profile_binding=True)
            if payload["kind"] == "profile_update":
                receiver["profile"] = deepcopy(payload["profile"])
                receiver["profile_id"] = content_hash(payload["profile"])
                self.ik_baseline = False
                data, kind = {}, "profile_applied_verified"
            else:
                if self.query_validator:
                    self.query_validator(receiver["profile"], {
                        "read_only": True, "frame": "base", "pose_type": "tcp",
                        "mode": "current" if payload["kind"] == "inspect_current" else "target",
                        "check_runnable": False, "previous": receiver["actual_pose"],
                        "expected_actual": receiver["actual_pose"], "expected_joint": receiver["actual_joint"],
                        "target": payload.get("target", receiver["actual_pose"])},
                        receiver["actual_pose"], receiver["actual_pose"], receiver["actual_joint"], self.ik_baseline)
                if payload["kind"] == "inspect_current":
                    self.ik_baseline = True
                data = {"status": "ok", "motion_issued": False, "source_pose": receiver["actual_pose"],
                    "source_joint": (self.target_inspection_joints if payload["kind"] == "inspect_ik"
                        and self.target_inspection_joints is not None else
                        self.inspected_joints if self.inspected_joints is not None else receiver["actual_joint"]),
                    "target_fk": payload.get("target", receiver["actual_pose"]),
                    "solution_joint": self.wrist["expected_target_joint_deg"] if self.wrist else list(JOINTS)}
                kind = "ik_result_verified"
            if self.failure == "bad-ik" and payload["kind"] == "inspect_ik":
                data = {**data, "status": "unreachable"}
            if self.failure == "wrong-winding" and payload["kind"] == "inspect_ik":
                data = {**data, "solution_joint": list(JOINTS)}
            receiver["seq"] += 1
            self.jobs[payload["request_id"]] = {"state": "complete", "result": {"robot_receipt": {"kind": kind, "data": deepcopy(data)}}}
            if self.after_call:
                self.after_call(payload)
            if self.failure == "lost-profile-reply" and payload["kind"] == "profile_update":
                raise TimeoutError("Synthetic profile was consumed but reply was lost")
            return {"accepted": True}
        job = deepcopy(self.jobs[path.rsplit("/", 1)[-1]])
        if self.failure == "running":
            return {"state": "running"}
        if self.failure == "outcome-unknown":
            return {"state": "outcome_unknown"}
        return job

    def native(self):
        receiver, local = self.status["receiver"], self.status["installation"]
        return Snapshot(receiver["session_id"], receiver["seq"], receiver["profile_id"], local["installation_id"],
            tuple(receiver["actual_pose"]), tuple(receiver["actual_joint"]), tuple(receiver["actual_pose"]),
            "d"*64, 1000., True, local["scope"], local["tcp_definition_sha256"], local["tool_id"],
            local["car_id"], local["surface_id"], 20.)


class MissionProfileTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.journal = PrivateJournal(self.directory.name)
        self.api = FakeGuardedAPI()
        self.policy_calls = []
        self.receiver_policy = SimpleNamespace(MAX_PROFILE_BYTES=65536,
            valid=lambda profile, physical: self.policy_calls.append((deepcopy(profile), physical)))
        self.stop = False
        self.tick = 0.

    def tearDown(self):
        self.journal.close()
        self.directory.cleanup()

    def stop_check(self):
        if self.stop:
            raise ExecutionBlocked("STOP", "Synthetic stop")

    def monotonic(self):
        self.tick += 20.
        return self.tick

    def preparer(self, native=None):
        return ReviewedProfilePreparer(api=self.api, journal=self.journal, native_snapshot=native or self.api.native,
            receiver_policy=self.receiver_policy, stop_check=self.stop_check, clock=lambda: 1000.,
            monotonic=self.monotonic, sleep=lambda _: None)

    def prepare(self, *, measured=None, supplied_review=None, wrist=None, preparer=None, operation="synthetic-op"):
        measured = measured or unit()
        binding = {key: self.api.status["receiver"][key] for key in ("session_id", "seq", "profile_id")}
        return (preparer or self.preparer()).prepare(measured, supplied_review or review(measured, wrist), binding,
            operation_id=operation, wrist=wrist)

    def commands(self):
        return [payload for path, payload in self.api.calls if path == "/v1/commands"]

    def assert_failed_preparation_remains_held_without_motion(self):
        self.assertTrue(self.api.status["hold"])
        self.assertFalse(self.api.status["armed"])
        self.assertEqual(self.api.status["receiver"]["actual_pose"], list(SOURCE))
        self.assertFalse(any(c["kind"] in {"translate", "rotate"} for c in self.commands()))
        self.assertEqual(self.journal.load()["state"], "PROFILE_PREPARATION_FAILED")
        count = len(self.commands())
        with self.assertRaises(ExecutionBlocked):
            self.preparer()
        self.assertEqual(len(self.commands()), count)

    def mixed_precision_source(self):
        receiver = self.api.status["receiver"]
        receiver["actual_joint"] = list(NATIVE_JOINTS)
        self.api.inspected_joints = list(INSPECTED_JOINTS)
        profile = build_profile(self.api.status["installation"],
            {"actual_pose": list(SOURCE), "actual_joint": list(NATIVE_JOINTS)}, on_site_review=True)
        receiver.update(profile=profile, profile_id=content_hash(profile))

    def test_actual_native_quantization_accepts_stationary_inspection_without_widening_profile(self):
        self.mixed_precision_source()
        result = self.prepare()
        self.assertEqual(result["inspected_source_joint_deg"], list(INSPECTED_JOINTS))
        self.assertEqual(result["profile"]["expected_start_joint_deg"], list(NATIVE_JOINTS))
        self.assertEqual(result["profile"]["tcp_bounds_base_mm"], [-.6, -.6, 99.85, 20.6, .6, 100.15])
        self.assertFalse(result["motion_issued"])
        self.assertTrue(self.api.status["hold"])
        self.assertFalse(self.api.status["armed"])

    def test_actual_native_wrist_resolves_full_precision_and_passes_unchanged_driver_preflight(self):
        measured, intent = unit(wrist=True), wrist_intent()
        self.mixed_precision_source()
        resolved = resolve_wrist_descriptor(measured, review(measured, intent), SOURCE, INSPECTED_JOINTS, intent)
        self.api.wrist = resolved
        result = self.prepare(measured=measured, wrist=intent)
        self.assertEqual(result["wrist"], resolved)
        self.assertEqual(result["wrist"]["expected_source_joint_deg"], list(INSPECTED_JOINTS))
        self.assertEqual(result["wrist"]["expected_target_joint_deg"][:5], list(INSPECTED_JOINTS[:5]))
        self.assertAlmostEqual(result["wrist"]["expected_target_joint_deg"][5], INSPECTED_JOINTS[5]+89.999)
        self.assertEqual(result["profile"]["expected_start_joint_deg"], list(NATIVE_JOINTS))
        self.assertTrue(result["receiver_nineteen_joint_fk_samples_still_required"])
        self.assertFalse(result["exact_joint_path_fk_verified"])
        edge = {**result["profile"]["rotation_edges"][0],
            "source_orientation_deg": list(measured.stages[0].start_base[3:]),
            "target_orientation_deg": list(measured.stages[0].target_base[3:])}
        runtime_hash = content_hash(result["profile"]["rotation_runtime"])
        snapshot = replace(self.api.native(), reviewed_rotation_edges=(edge,), rotation_runtime_sha256=runtime_hash)
        ConfigBackedMissionDriver._validate_wrist(snapshot, measured.stages[0],
            {**result["wrist"], "rotation_runtime_sha256": runtime_hash})

    def test_inspection_beyond_native_register_quantization_is_rejected_before_install(self):
        self.mixed_precision_source()
        self.api.inspected_joints[5] = NATIVE_JOINTS[5]-.10001
        with self.assertRaises(ExecutionBlocked) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "CURRENT_IK_INSPECTION_FAILED")
        self.assertEqual([c["kind"] for c in self.commands()], ["inspect_current"])
        self.assertFalse(any(path == "/v1/installation" for path, _ in self.api.calls))

    def test_full_precision_source_stability_remains_point_zero_five(self):
        self.mixed_precision_source()
        self.api.target_inspection_joints = list(INSPECTED_JOINTS)
        # Both readings fit the same Native register; a real 0.06-degree change
        # between full-precision inspections still fails the tighter check.
        self.api.target_inspection_joints[5] += .06
        with self.assertRaises(ExecutionBlocked):
            self.prepare()
        self.assertEqual([c["kind"] for c in self.commands()], ["inspect_current", "profile_update", "inspect_current", "inspect_ik"])
        self.assert_failed_preparation_remains_held_without_motion()

    def test_full_precision_wrist_target_ik_tolerance_is_not_quantization_allowance(self):
        measured, intent = unit(wrist=True), wrist_intent()
        self.mixed_precision_source()
        self.api.wrist = resolve_wrist_descriptor(measured, review(measured, intent), SOURCE, INSPECTED_JOINTS, intent)
        self.api.wrist["expected_target_joint_deg"][5] += .06
        with self.assertRaises(ValueError):
            self.prepare(measured=measured, wrist=intent)
        self.assert_failed_preparation_remains_held_without_motion()

    def test_explicit_stationary_no_motion_reconciliation_allows_new_operation_only(self):
        self.journal.checkpoint({"state": "RECONCILED_STATIONARY_NO_MOTION",
            "original_failed_operation": "synthetic-prior", "evidence_sha256": "e"*64,
            "automatic_replay": False})
        preparer = self.preparer()
        self.assertEqual(self.api.calls, [])
        result = self.prepare(preparer=preparer, operation="synthetic-new-after-reconciliation")
        self.assertFalse(result["motion_issued"])
        self.assertEqual(self.commands()[0]["kind"], "inspect_current")

    def test_translation_installs_reviewed_profile_then_inspects_every_target_without_motion(self):
        result = self.prepare()
        self.assertEqual([c["kind"] for c in self.commands()], ["inspect_current", "profile_update", "inspect_current", "inspect_ik", "inspect_ik", "inspect_ik"])
        self.assertEqual(result["profile"]["tcp_bounds_base_mm"], [-.6, -.6, 99.85, 20.6, .6, 100.15])
        self.assertEqual(result["profile"]["translation_speed_mm_s"], 5.)
        self.assertEqual(result["profile"]["translation_accel_mm_s2"], 10.)
        self.assertEqual(result["expected_receiver"]["seq"], 7)
        self.assertFalse(result["motion_issued"] or result["vehicle_control_qualified"] or result["board_registration_qualified"])
        self.assertEqual(result["status"]["receiver"]["actual_pose"], list(SOURCE))
        self.assertTrue(self.api.status["hold"])
        self.assertFalse(self.api.status["armed"])
        self.assertEqual(self.journal.load()["state"], "PROFILE_PREPARATION_COMPLETE")
        self.assertEqual(len(self.policy_calls), 1)

    def test_same_source_second_unit_gets_distinct_actual_review_and_installation(self):
        one = self.prepare()
        two = self.prepare(operation="synthetic-next")
        self.assertNotEqual(one["installation"]["installation_id"], two["installation"]["installation_id"])
        self.assertNotEqual(one["installation"]["review_reference"], two["installation"]["review_reference"])
        self.assertEqual(two["expected_receiver"]["seq"], 13)

    def test_real_receiver_query_bounds_and_profile_reset_require_correct_preflight_order(self):
        runtime_path = Path(__file__).resolve().parents[1]/"runtime/robot-control/receiver"
        if not runtime_path.exists():
            self.skipTest("Optional private installed runtime is not distributed.")
        runtime = load_runtime(runtime_path)
        old = self.api.status["installation"]
        old.update(workspace_min_mm=[-1., -1., 99.], workspace_max_mm=[1., 1., 101.])
        old_profile = build_profile(old, {"actual_pose": list(SOURCE), "actual_joint": list(JOINTS)}, on_site_review=True)
        self.api.status["receiver"].update(profile=old_profile, profile_id=content_hash(old_profile))
        target = list(unit().stages[0].target_base)
        # Exercise the actual unchanged receiver guards, not only API admission.
        with self.assertRaisesRegex(ValueError, "Outside TCP bounds"):
            runtime["policy"].inside(old_profile, target)
        self.api.query_validator = runtime["ik"].validate
        result = self.prepare()
        commands = self.commands()
        self.assertEqual([c["kind"] for c in commands],
            ["inspect_current", "profile_update", "inspect_current", "inspect_ik", "inspect_ik", "inspect_ik"])
        for command in commands[2:]:
            self.assertEqual(command["installation_id"], result["installation"]["installation_id"])
            self.assertEqual(command["expected_receiver"]["profile_id"], content_hash(result["profile"]))
        self.assertFalse(result["motion_issued"])
        self.assertTrue(self.api.status["hold"])
        self.assertFalse(self.api.status["armed"])

    def test_post_profile_current_roundtrip_failure_blocks_target_queries(self):
        self.mixed_precision_source()
        def after(payload):
            if payload["kind"] == "profile_update":
                self.api.inspected_joints[5] += .06
        self.api.after_call = after
        with self.assertRaises(ExecutionBlocked) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "APPLIED_PROFILE_CURRENT_IK_FAILED")
        self.assertEqual([c["kind"] for c in self.commands()],
            ["inspect_current", "profile_update", "inspect_current"])
        self.assert_failed_preparation_remains_held_without_motion()

    def test_geometry_site_identity_and_bounds_cannot_be_inferred(self):
        cases = []
        absent = review(); absent["allowed_geometry_sha256"] = ["0"*64]; cases.append(absent)
        wrong = review(); wrong["site"]["tool_id"] = "foreign"; cases.append(wrong)
        bounds = review(); bounds["workspace_max_mm"][0] = 20.; cases.append(bounds)
        limit = review(); limit["max_speed_mm_s"] = 6.; cases.append(limit)
        acceptance = review(); acceptance["status"] = "candidate"; cases.append(acceptance)
        for index, value in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ExecutionBlocked):
                build_unit_profile(unit(), value, self.api.status, self.api.native(), installation_id="synthetic-new")
        self.assertEqual(self.api.calls, [])

    def test_unloaded_wrist_checks_directed_ik_and_preserves_runtime_fk_requirement(self):
        wrist = wrist_descriptor()
        self.api = FakeGuardedAPI(wrist)
        result = self.prepare(measured=unit(wrist=True), wrist=wrist)
        self.assertEqual([c["kind"] for c in self.commands()], ["inspect_current", "profile_update", "inspect_current", "inspect_ik"])
        self.assertTrue(result["receiver_nineteen_joint_fk_samples_still_required"])
        self.assertFalse(result["exact_joint_path_fk_verified"] or result["car_turn_qualified"])
        anchor = result["profile"]["rotation_anchors"][0]
        self.assertEqual(anchor["position_window_mm"], .5)
        self.assertEqual(result["wrist"], wrist)
        self.assertEqual(result["profile"]["rotation_runtime"]["primitive"], "moveJoint_wrist")

    def test_wrong_ik_winding_never_permits_motion_and_loaded_wrist_never_builds(self):
        wrist = wrist_descriptor()
        self.api = FakeGuardedAPI(wrist)
        self.api.failure = "wrong-winding"
        with self.assertRaises(ValueError):
            self.prepare(measured=unit(wrist=True), wrist=wrist)
        self.assert_failed_preparation_remains_held_without_motion()
        loaded = {**wrist, "unloaded": False}
        with self.assertRaises(ExecutionBlocked):
            build_unit_profile(unit(wrist=True), review(unit(wrist=True), loaded), self.api.status,
                               self.api.native(), installation_id="synthetic-new", wrist=loaded)

    def test_semantic_wrist_intent_uses_fresh_joint_baseline_and_measured_target(self):
        intent, measured = wrist_intent(), unit(wrist=True)
        actual = (*JOINTS[:5], 12.)
        resolved = resolve_wrist_descriptor(measured, review(measured, intent), SOURCE, actual, intent)
        self.api = FakeGuardedAPI(resolved)
        self.api.status["receiver"]["actual_joint"] = list(actual)
        old_profile = build_profile(self.api.status["installation"],
            {"actual_pose": list(SOURCE), "actual_joint": list(actual)}, on_site_review=True)
        self.api.status["receiver"].update(profile=old_profile, profile_id=content_hash(old_profile))
        result = self.prepare(measured=measured, wrist=intent)
        self.assertEqual(result["wrist"], resolved)
        self.assertEqual(result["wrist"]["expected_source_joint_deg"], list(actual))
        self.assertAlmostEqual(result["wrist"]["expected_target_joint_deg"][5], 101.999)
        self.assertEqual(result["wrist_intent_sha256"], content_hash(intent))
        self.assertEqual(result["installation"]["orientations"][1]["rxyz_deg"], list(measured.stages[0].target_base[3:]))
        self.assertFalse(result["exact_joint_path_fk_verified"])

    def test_semantic_wrong_direction_unreviewed_intent_and_literal_euler_wrap_are_rejected(self):
        measured, intent = unit(wrist=True), wrist_intent()
        supplied = review(measured, intent)
        wrong = {**intent, "delta_j6_deg": -89.999}
        with self.assertRaises(ExecutionBlocked):
            resolve_wrist_descriptor(measured, supplied, SOURCE, JOINTS, wrong)
        with self.assertRaises(ExecutionBlocked):
            resolve_wrist_descriptor(measured, review(measured, wrong), SOURCE, JOINTS, wrong)
        target = list(measured.stages[0].target_base)
        target[5] += 360
        wrapped = replace(measured, stages=(replace(measured.stages[0], target_base=tuple(target)),))
        with self.assertRaises(ExecutionBlocked):
            resolve_wrist_descriptor(wrapped, review(wrapped, intent), SOURCE, JOINTS, intent)

    def test_semantic_wrist_does_not_wrap_joint_limit_or_accept_wrong_ik_branch(self):
        measured, intent = unit(wrist=True), wrist_intent()
        with self.assertRaises(ValueError):
            resolve_wrist_descriptor(measured, review(measured, intent), SOURCE, (*JOINTS[:5], 300.), intent)
        self.api = FakeGuardedAPI(wrist_descriptor())
        self.api.failure = "wrong-winding"
        with self.assertRaises(ValueError):
            self.prepare(measured=measured, wrist=intent)
        self.assert_failed_preparation_remains_held_without_motion()

    def test_profile_reply_loss_is_not_resent_and_blocks_new_preparer(self):
        self.api.failure = "lost-profile-reply"
        preparer = self.preparer()
        with self.assertRaises(TimeoutError):
            self.prepare(preparer=preparer)
        count = len(self.commands())
        self.assertEqual(sum(c["kind"] == "profile_update" for c in self.commands()), 1)
        with self.assertRaises(ExecutionBlocked):
            self.prepare(preparer=preparer, operation="synthetic-retry")
        with self.assertRaises(ExecutionBlocked):
            self.preparer()
        self.assertEqual(len(self.commands()), count)
        self.assertEqual(self.journal.load()["state"], "PROFILE_PREPARATION_FAILED")

    def test_preparation_identity_is_durable_and_cannot_be_replayed(self):
        self.prepare()
        count = len(self.commands())
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(len(self.commands()), count)

    def test_unknown_query_timeout_and_stop_do_not_install_or_continue(self):
        for failure in ("outcome-unknown", "running", "stop"):
            # Independent temporary journals keep failures terminal per run.
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                journal, original = PrivateJournal(directory), self.journal
                self.journal, self.api, self.stop = journal, FakeGuardedAPI(), False
                if failure == "stop":
                    self.api.after_call = lambda _: setattr(self, "stop", True)
                else:
                    self.api.failure = failure
                try:
                    with self.assertRaises(ExecutionBlocked):
                        self.prepare()
                    self.assertEqual(len(self.commands()), 1)
                    self.assertFalse(any(path == "/v1/installation" for path, _ in self.api.calls))
                finally:
                    journal.close()
                    self.journal, self.stop = original, False

    def test_bad_ik_after_profile_handoff_never_admits_motion_or_replay(self):
        self.api.failure = "bad-ik"
        with self.assertRaises(ExecutionBlocked):
            self.prepare()
        self.assertEqual([c["kind"] for c in self.commands()], ["inspect_current", "profile_update", "inspect_current", "inspect_ik"])
        self.assert_failed_preparation_remains_held_without_motion()

    def test_stale_native_and_existing_active_or_unresolved_receiver_are_rejected(self):
        native = replace(self.api.native(), native_observed_at=990.)
        with self.assertRaises(ExecutionBlocked):
            self.prepare(preparer=self.preparer(native=lambda: native))
        self.assertEqual(self.commands(), [])
        self.assertFalse(any(path == "/v1/installation" for path, _ in self.api.calls))

    def test_existing_active_command_pending_profile_and_reconciliation_block_read_only_query(self):
        cases = ({"active_commands": ["unknown-command"]},
                 {"receiver": {"profile_pending": {"id": "pending"}}},
                 {"receiver": {"reason": "RECEIVER_RECONCILIATION_REQUIRED"}})
        for change in cases:
            with self.subTest(change=change):
                self.api = FakeGuardedAPI()
                for key, value in change.items():
                    if key == "receiver":
                        self.api.status[key].update(value)
                    else:
                        self.api.status[key] = value
                with self.assertRaises(ExecutionBlocked):
                    self.preparer()._idle()
                self.assertEqual(self.commands(), [])

    def test_native_identity_must_match_installed_tool_and_final_handoff(self):
        native = replace(self.api.native(), tool_id="foreign-tool")
        with self.assertRaises(ExecutionBlocked):
            build_unit_profile(unit(), review(), self.api.status, native, installation_id="synthetic-new")
        calls = 0
        def snapshot():
            nonlocal calls
            calls += 1
            value = self.api.native()
            return value if calls == 1 else replace(value, installation_id="stale-installation")
        with self.assertRaises(ExecutionBlocked):
            self.prepare(preparer=self.preparer(native=snapshot))
        self.assertEqual(self.journal.load()["state"], "PROFILE_PREPARATION_FAILED")

    def test_no_profile_mutation_if_exact_native_source_differs(self):
        native = replace(self.api.native(), native_tcp_base=(1., *SOURCE[1:]))
        with self.assertRaises(ExecutionBlocked):
            self.prepare(preparer=self.preparer(native=lambda: native))
        self.assertEqual(self.commands(), [])

    def test_original_keepouts_and_fixed_z_euler_are_preserved(self):
        self.api.status["installation"]["inflated_keepout_boxes_base_mm"] = [[-25., -25., 99., -20., -20., 101.]]
        local, profile = build_unit_profile(unit(), review(), self.api.status, self.api.native(), installation_id="synthetic-new")
        self.assertEqual(profile["inflated_keepout_boxes_base_mm"], self.api.status["installation"]["inflated_keepout_boxes_base_mm"])
        self.assertEqual(local["fixed_tcp_z_mm"], SOURCE[2])
        self.assertEqual(local["fixed_orientation_deg"], list(SOURCE[3:]))


if __name__ == "__main__":
    unittest.main()
