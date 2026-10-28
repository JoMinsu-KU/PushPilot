"""Offline physical coordinator tests with synthetic coordinates and IO only."""
from dataclasses import replace
import hashlib
import math
from pathlib import Path
import unittest

from backend.maps import MapDefinition
from backend.robot_control.taught_executor import (
    ApprovedRoute, ClearanceReview, ExecutionBlocked, Frame, MeasuredRoad, MeasuredObservationClearance,
    MeasuredTransition, MeasuredTransitionAction, MotionReceipt,
    SignalObservationTarget, Snapshot, TaughtAdapter, TaughtExecutor, VehicleReview, compile_taught_route,
)


DRAWING = Path(__file__).resolve().parents[1] / "backend/data/seoul-city-a3.json"
FIXED = (10., 90., 0., 30.)


def pose(x, y=0):
    return (float(x), float(y), *FIXED)


def configuration():
    drawing = MapDefinition(DRAWING)
    roads = (
        MeasuredRoad("PIZZA", "S", pose(0), pose(20), "1"*64, "synthetic-face", 20.),
        MeasuredRoad("S", "OFFICE_BUILDING", pose(20), pose(40), "2"*64, "synthetic-face", 20.),
        MeasuredRoad("S", "C", pose(20), pose(20, 20), "3"*64, "synthetic-face", 10.),
        MeasuredRoad("C", "HANOK", pose(20, 20), pose(40, 20), "4"*64, "synthetic-face", 10.),
    )
    adapter = TaughtAdapter(drawing.id, drawing.version, drawing.geometry_hash, "a"*64,
                           "b"*64, "synthetic-tool", "synthetic-car", "synthetic-paper", roads)
    route = ApprovedRoute("synthetic-approved-plan", 3, "OFFICE_BUILDING",
                          ("PIZZA", "S", "OFFICE_BUILDING"), drawing.id, drawing.version,
                          drawing.geometry_hash, "actual-provider-receipt-format-fixture",
                          "operator-approval-fixture", True)
    return drawing, adapter, route


class SyntheticPorts:
    def __init__(self):
        self.time = 100.
        self.sequence, self.image_sequence = 1, 0
        self.tcp = pose(0)
        self.events, self.motions, self.holds = [], [], []
        self.checkpoint = None
        self.review_calls = []
        self.clearance_calls = []
        self.clearance_verdict, self.clearance_visible = "PASS", True
        self.clearance_unchanged, self.clearance_recontact = True, True
        self.clearance_provider_timeout = False
        self.review_verdict, self.visible, self.excessive_yaw = "PASS", True, False
        self.expected_progress = True
        self.occlusion_cause = "UNKNOWN"
        self.signal_visible, self.signal_occlusion_cause = False, "UNKNOWN"
        self.clearance_signal_visible = False
        self.force_arrived = None
        self.changed_receipt, self.motion_exception = False, False
        self.endpoint_error = 0
        self.muse_raises, self.change_during_muse = False, False
        self.bad_frame_hash, self.reuse_frame = False, False
        self.stroke_limit, self.qualification_scope = 20., "local_contact_commissioning"
        self.joints, self.reviewed_edges, self.runtime_hash = (0.,)*6, (), None
        self.pre_dispatch_states = []
        self.fail_post_native_once = False

    def now(self):
        return self.time

    def snapshot(self):
        if self.fail_post_native_once and self.motions:
            self.fail_post_native_once = False
            raise TimeoutError("Synthetic supplemental Native read failed after a known verified receipt.")
        return Snapshot("synthetic-session", self.sequence, "synthetic-profile", "synthetic-installation",
            self.tcp, self.joints, tuple(round(x, 1) for x in self.tcp),
            hashlib.sha256(str(self.time).encode()).hexdigest(), self.time,
            True, self.qualification_scope, "b"*64, "synthetic-tool", "synthetic-car", "synthetic-paper",
            self.stroke_limit, self.reviewed_edges, self.runtime_hash)

    def capture(self):
        if self.reuse_frame and self.image_sequence:
            return self.last_frame
        self.time += .01
        self.image_sequence += 1
        raw = b"\xff\xd8synthetic-test-pixels-" + str(self.image_sequence).encode() + b"\xff\xd9"
        result = Frame(str(self.image_sequence), "synthetic-camera-epoch", self.image_sequence,
                       self.time, "0"*64 if self.bad_frame_hash else hashlib.sha256(raw).hexdigest(), raw)
        self.last_frame = result
        return result

    def execute_once(self, intent):
        self.motions.append(intent)
        self.pre_dispatch_states.append(dict(self.checkpoint))
        if self.motion_exception:
            raise TimeoutError("Synthetic timeout: the actual motion outcome is unresolved.")
        self.sequence += 1
        self.tcp = (intent.target_base[0]+self.endpoint_error, *intent.target_base[1:])
        if intent.expected_target_joint_deg is not None:
            self.joints = intent.expected_target_joint_deg
        return MotionReceipt("wrong-request" if self.changed_receipt else intent.request_id,
            "synthetic-session", self.sequence, "synthetic-profile", "synthetic-installation",
            True, intent.target_base, "c"*64)

    def review(self, intent, before, after, *, at_goal):
        self.review_calls.append((intent.request_id, before.sha256, after.sha256, at_goal))
        self.time += 9.  # A provider round trip must refresh robot state afterwards.
        if self.muse_raises:
            raise TimeoutError("Synthetic provider timeout.")
        if self.change_during_muse:
            self.sequence += 1
        return VehicleReview(intent.request_id, "synthetic-provider-receipt", before.sha256, after.sha256,
            self.review_verdict, self.visible, self.expected_progress, self.excessive_yaw,
            at_goal if self.force_arrived is None else self.force_arrived, "Synthetic original-pair result.",
            self.occlusion_cause, self.signal_visible, self.signal_occlusion_cause)

    def hold(self, reason):
        self.holds.append(reason)

    def review_clearance(self, original, withdrawal, original_before, withdrawal_before, clear_after, *, path_evidence=()):
        self.clearance_calls.append((original.request_id, withdrawal.request_id,
                                    original_before.sha256, withdrawal_before.sha256, clear_after.sha256))
        self.clearance_path_evidence = tuple(path_evidence)
        if self.clearance_provider_timeout:
            raise TimeoutError("Synthetic clearance sequence provider timeout.")
        return ClearanceReview(withdrawal.request_id, original.request_id, "synthetic-clearance-provider",
            (original_before.sha256, withdrawal_before.sha256, clear_after.sha256), self.clearance_verdict,
            self.clearance_visible, True, self.clearance_unchanged, self.clearance_recontact,
            "Synthetic clear-view sequence result; not physical qualification.", self.clearance_signal_visible)

    def append_event(self, kind, payload):
        self.events.append((kind, payload))

    def save_checkpoint(self, value):
        self.checkpoint = dict(value)

    def load_checkpoint(self):
        return self.checkpoint


class TaughtExecutorTests(unittest.TestCase):
    def setUp(self):
        self.drawing, self.adapter, self.route = configuration()
        self.ports = SyntheticPorts()

    def executor(self, **kwargs):
        return TaughtExecutor(self.route, self.adapter, self.drawing, self.ports, **kwargs)

    def test_exact_muse_canonical_path_and_reviewed_adapter_not_map_xy(self):
        roads = compile_taught_route(self.route, self.adapter, self.drawing)
        self.assertEqual([(r.source, r.target) for r in roads], [("PIZZA", "S"), ("S", "OFFICE_BUILDING")])
        self.assertEqual(roads[-1].end_base, pose(40))
        self.assertNotEqual(roads[-1].end_base[:2], tuple(self.drawing.route("OFFICE_BUILDING")["points_mm"][-1]))
        for changed in (replace(self.route, map_hash="9"*64),
                        replace(self.route, map_version="superseded")):
            with self.subTest(changed=changed), self.assertRaisesRegex(ExecutionBlocked, "graph revision"):
                compile_taught_route(changed, self.adapter, self.drawing)
        with self.assertRaises(ValueError):
            compile_taught_route(replace(self.route, node_ids=("PIZZA", "OFFICE_BUILDING")), self.adapter, self.drawing)

    def test_unmeasured_direction_change_and_missing_road_fail_before_motion(self):
        turning = replace(self.route, destination="HANOK", node_ids=("PIZZA", "S", "C", "HANOK"))
        with self.assertRaises(ExecutionBlocked) as error:
            compile_taught_route(turning, self.adapter, self.drawing)
        self.assertEqual(error.exception.code, "CONTACT_TURN_REQUIRED")
        with self.assertRaises(ExecutionBlocked) as error:
            compile_taught_route(self.route, replace(self.adapter, roads=self.adapter.roads[:1]), self.drawing)
        self.assertEqual(error.exception.code, "ROAD_UNQUALIFIED")
        self.assertFalse(self.ports.motions)

    def test_commissioning_signal_exclusion_cannot_become_production_signal_mission(self):
        with self.assertRaises(ExecutionBlocked) as error:
            compile_taught_route(replace(self.route, commissioning_without_signals=False), self.adapter, self.drawing)
        self.assertEqual(error.exception.code, "SIGNAL_RUNTIME_REQUIRED")

    def test_one_bounded_stroke_has_durable_intent_native_receipt_and_one_review(self):
        executor = self.executor(stroke_mm=10)
        result = executor.advance()
        self.assertEqual(result["state"], "READY")
        self.assertFalse(result["vehicle_arrival_verified"])
        self.assertEqual(len(self.ports.motions), 1)
        intent = self.ports.motions[0]
        self.assertEqual(intent.purpose, "contact_trial")
        self.assertEqual(intent.target_base, pose(10))
        self.assertEqual(intent.target_base[2:], intent.start_base[2:])
        self.assertEqual(self.ports.pre_dispatch_states[0]["state"], "DISPATCH_UNRESOLVED")
        self.assertEqual(self.ports.pre_dispatch_states[0]["pending_request_id"], intent.request_id)
        self.assertEqual(len(self.ports.review_calls), 1)
        self.assertEqual([kind for kind, _ in self.ports.events],
                         ["motion_intent", "robot_receipt", "robot_endpoint", "vehicle_review_input", "vehicle_review"])

    def test_per_installation_and_empirical_stroke_limits_cannot_be_bypassed(self):
        self.ports.stroke_limit = 5
        executor = self.executor(stroke_mm=20)
        executor.advance()
        self.assertEqual(self.ports.motions[0].target_base, pose(5))
        ports = SyntheticPorts()
        roads = tuple(replace(road, qualified_stroke_mm=4) for road in self.adapter.roads)
        executor = TaughtExecutor(self.route, replace(self.adapter, roads=roads), self.drawing, ports, stroke_mm=20)
        executor.advance()
        self.assertEqual(ports.motions[0].target_base, pose(4))

    def test_occlusion_reobservation_does_not_repeat_move_or_replace_before_image(self):
        self.ports.review_verdict, self.ports.visible = "UNCERTAIN", False
        executor = self.executor()
        self.assertEqual(executor.advance()["state"], "WAIT_REVIEW")
        first_before = self.ports.review_calls[0][1]
        self.ports.review_verdict, self.ports.visible = "PASS", True
        self.assertEqual(executor.reobserve()["state"], "READY")
        self.assertEqual(len(self.ports.motions), 1)
        self.assertEqual(self.ports.review_calls[1][1], first_before)
        self.assertNotEqual(self.ports.review_calls[1][2], self.ports.review_calls[0][2])

    def test_provider_timeout_preserves_robot_completion_and_allows_review_only(self):
        self.ports.muse_raises = True
        executor = self.executor()
        with self.assertRaises(TimeoutError):
            executor.advance()
        self.assertEqual(executor.state, "WAIT_REVIEW")
        self.ports.muse_raises = False
        executor.reobserve()
        self.assertEqual(len(self.ports.motions), 1)

    def test_unknown_motion_timeout_receipt_mismatch_and_native_error_never_retry(self):
        for field in ("motion_exception", "changed_receipt", "endpoint_error"):
            with self.subTest(field=field):
                ports = SyntheticPorts()
                setattr(ports, field, .3 if field == "endpoint_error" else True)
                executor = TaughtExecutor(self.route, self.adapter, self.drawing, ports)
                with self.assertRaises((ExecutionBlocked, TimeoutError)):
                    executor.advance()
                self.assertEqual(executor.state, "WAIT_ENDPOINT_CONFIRMATION" if field == "endpoint_error" else "DISPATCH_UNRESOLVED")
                with self.assertRaises(ExecutionBlocked):
                    executor.advance()
                with self.assertRaises(ExecutionBlocked):
                    executor.reobserve()
                self.assertEqual(len(ports.motions), 1)
                self.assertFalse(ports.review_calls)
                self.assertTrue(ports.holds)

    def test_known_receipt_native_timeout_recovers_readonly_without_a_second_dispatch(self):
        self.ports.fail_post_native_once = True
        executor = self.executor()
        with self.assertRaises(TimeoutError):
            executor.advance()
        self.assertEqual(executor.state, "WAIT_ENDPOINT_CONFIRMATION")
        self.assertIsNotNone(executor.pending[2])
        self.assertEqual(self.ports.checkpoint["pending_request_id"], self.ports.motions[0].request_id)
        self.assertFalse(self.ports.review_calls)
        self.assertEqual(executor.recheck_endpoint()["state"], "READY")
        self.assertEqual(len(self.ports.motions), 1)
        self.assertEqual(len(self.ports.review_calls), 1)

    def test_restart_never_restores_pending_actions_or_resumes_completed_route(self):
        for stored in ({"state": "DISPATCH_UNRESOLVED", "pending_request_id": "old"},
                       {"state": "READY"}, {"state": "WAIT_HUMAN_RESET"}):
            with self.subTest(stored=stored):
                ports = SyntheticPorts()
                ports.checkpoint = stored
                executor = TaughtExecutor(self.route, self.adapter, self.drawing, ports)
                self.assertEqual(executor.state, "NEEDS_RECONCILIATION")
                with self.assertRaises(ExecutionBlocked):
                    executor.advance()
                self.assertFalse(ports.motions)

    def test_off_corridor_fixed_height_or_scope_change_stops_before_dispatch(self):
        for tcp, scope in ((pose(0, 1.1), "local_contact_commissioning"),
                           ((0., 0., 10.2, 90., 0., 30.), "local_contact_commissioning"),
                           (pose(0), "planar_teaching")):
            with self.subTest(tcp=tcp, scope=scope):
                ports = SyntheticPorts()
                ports.tcp, ports.qualification_scope = tcp, scope
                executor = TaughtExecutor(self.route, self.adapter, self.drawing, ports)
                with self.assertRaises(ExecutionBlocked):
                    executor.advance()
                self.assertFalse(ports.motions)

    def test_bad_or_repeated_original_frame_cannot_advance_vehicle_state(self):
        self.ports.bad_frame_hash = True
        executor = self.executor()
        with self.assertRaises(ExecutionBlocked):
            executor.advance()
        self.assertFalse(self.ports.motions)
        self.ports = SyntheticPorts()
        self.ports.reuse_frame = True
        executor = self.executor()
        with self.assertRaises(ExecutionBlocked):
            executor.advance()
        self.assertEqual(executor.state, "WAIT_REVIEW")
        self.assertFalse(self.ports.review_calls)

    def test_robot_state_change_during_muse_does_not_authorize_next_motion(self):
        self.ports.change_during_muse = True
        executor = self.executor()
        with self.assertRaises(ExecutionBlocked):
            executor.advance()
        self.assertEqual(executor.state, "WAIT_REVIEW")
        with self.assertRaises(ExecutionBlocked):
            executor.advance()
        self.assertEqual(len(self.ports.motions), 1)

    def test_manual_move_within_road_is_not_silently_treated_as_car_progress(self):
        executor = self.executor()
        executor.advance()
        self.ports.tcp = pose(15)
        with self.assertRaises(ExecutionBlocked) as error:
            executor.advance()
        self.assertEqual(error.exception.code, "BASELINE_CHANGED")
        self.assertEqual(len(self.ports.motions), 1)

    def test_new_course_cannot_start_halfway_along_taught_road(self):
        self.ports.tcp = pose(10)
        executor = self.executor()
        with self.assertRaises(ExecutionBlocked) as error:
            executor.advance()
        self.assertEqual(error.exception.code, "START_NOT_AT_ANCHOR")
        self.assertFalse(self.ports.motions)

    def test_robot_endpoint_alone_never_completes_goal_and_arrival_requires_reset(self):
        executor = self.executor(stroke_mm=20)
        self.assertEqual(executor.advance()["state"], "READY")
        self.ports.force_arrived = False
        self.assertEqual(executor.advance()["state"], "WAIT_REVIEW")
        self.assertEqual(self.ports.tcp, pose(40))
        with self.assertRaises(ExecutionBlocked):
            executor.advance()
        self.ports.force_arrived = True
        result = executor.reobserve()
        self.assertEqual(result["state"], "WAIT_HUMAN_RESET")
        self.assertTrue(result["vehicle_arrival_verified"] and result["human_reset_required"])
        with self.assertRaises(ExecutionBlocked):
            executor.advance()
        self.assertEqual(len(self.ports.motions), 2)


def mixed_configuration():
    drawing, adapter, old_route = configuration()
    rotated = (*FIXED[:3], 120.)
    def turned(x, y):
        return (float(x), float(y), *rotated)
    zero, ninety = (0.,)*6, (0., 0., 0., 0., 0., 90.)
    actions_s = (
        MeasuredTransitionAction("s-wrist", "rotate", pose(20), turned(20, 0), "5"*64,
            "The free pusher wrist reorients while the physical car stays stationary.", "synthetic-s-edge", zero, ninety, "f"*64),
        MeasuredTransitionAction("s-contact", "translate", turned(20, 0), turned(20, 2), "6"*64,
            "The physical car turns toward the connector and aligns with the outgoing road."),
    )
    actions_c = (
        MeasuredTransitionAction("c-wrist", "rotate", turned(20, 20), pose(20, 20), "7"*64,
            "The free pusher wrist reorients while the physical car stays stationary.", "synthetic-c-edge", ninety, zero, "f"*64),
        MeasuredTransitionAction("c-contact", "translate", pose(20, 20), pose(22, 20), "8"*64,
            "The physical car turns toward Hanok and aligns with the outgoing road."),
    )
    transitions = (
        MeasuredTransition("synthetic-s-turn", ("PIZZA", "S"), ("S", "C"), "9"*64, actions_s),
        MeasuredTransition("synthetic-c-turn", ("S", "C"), ("C", "HANOK"), "0"*64, actions_c),
    )
    roads = (adapter.roads[0], MeasuredRoad("S", "C", turned(20, 2), turned(20, 20), "3"*64, "synthetic-face", 20.),
             MeasuredRoad("C", "HANOK", pose(22, 20), pose(40, 20), "4"*64, "synthetic-face", 20.))
    route = replace(old_route, destination="HANOK", node_ids=("PIZZA", "S", "C", "HANOK"))
    adapter = replace(adapter, roads=roads, transitions=transitions)
    edges = tuple({"id": action.edge_id, "expected_source_joint_deg": action.expected_source_joint_deg,
                   "expected_target_joint_deg": action.expected_target_joint_deg,
                   "source_orientation_deg": action.start_base[3:], "target_orientation_deg": action.end_base[3:]}
                  for actions in (actions_s, actions_c) for action in actions if action.kind == "rotate")
    return drawing, adapter, route, edges


class MeasuredTransitionExecutorTests(unittest.TestCase):
    def setUp(self):
        self.drawing, self.adapter, self.route, edges = mixed_configuration()
        self.ports = SyntheticPorts()
        self.ports.qualification_scope = "local_contact_turn_commissioning"
        self.ports.reviewed_edges, self.ports.runtime_hash = edges, "f"*64
        self.executor = TaughtExecutor(self.route, self.adapter, self.drawing, self.ports, stroke_mm=20)

    def test_mixed_course_runs_one_measured_action_and_one_visual_review_per_call(self):
        for index in range(7):
            result = self.executor.advance()
            self.assertEqual(len(self.ports.motions), index+1)
            self.assertEqual(len(self.ports.review_calls), index+1)
        self.assertEqual(result["state"], "WAIT_HUMAN_RESET")
        self.assertEqual([x.kind for x in self.ports.motions],
                         ["translate", "rotate", "translate", "translate", "rotate", "translate", "translate"])
        self.assertTrue(all(x.purpose == "contact_turn_trial" for x in self.ports.motions))
        self.assertTrue(all(x.start_base[2] == x.target_base[2] == FIXED[0] for x in self.ports.motions))
        for intent in (self.ports.motions[1], self.ports.motions[4]):
            self.assertEqual(intent.start_base[:3], intent.target_base[:3])
            self.assertTrue(intent.edge_id and intent.transition_action_id and intent.expected_visual)
        self.assertEqual(self.ports.motions[3].target_base[3:], (90., 0., 120.))
        self.assertEqual(self.ports.motions[-1].target_base[3:], FIXED[1:])

    def test_uncertain_rotation_reobserves_stationary_car_without_repeating_wrist_action(self):
        self.executor.advance()
        self.ports.review_verdict = "UNCERTAIN"
        self.assertEqual(self.executor.advance()["state"], "WAIT_REVIEW")
        self.assertEqual(len(self.ports.motions), 2)
        self.ports.review_verdict = "PASS"
        self.assertEqual(self.executor.reobserve()["state"], "READY")
        self.assertEqual(len(self.ports.motions), 2)
        self.executor.advance()
        self.assertEqual(self.ports.motions[-1].transition_action_id, "s-contact")

    def test_missing_turn_scope_edge_runtime_or_source_joints_stops_before_rotation(self):
        for alteration in ("scope", "edge", "runtime", "joints"):
            with self.subTest(alteration=alteration):
                ports = SyntheticPorts()
                ports.qualification_scope = "local_contact_turn_commissioning"
                ports.reviewed_edges, ports.runtime_hash = self.ports.reviewed_edges, "f"*64
                executor = TaughtExecutor(self.route, self.adapter, self.drawing, ports, stroke_mm=20)
                executor.advance()
                if alteration == "scope":
                    ports.qualification_scope = "local_contact_commissioning"
                elif alteration == "edge":
                    ports.reviewed_edges = ()
                elif alteration == "runtime":
                    ports.runtime_hash = "e"*64
                else:
                    ports.joints = (0., 0., 0., 0., 0., 1.)
                with self.assertRaises(ExecutionBlocked):
                    executor.advance()
                self.assertEqual(len(ports.motions), 1)

    def test_unknown_rotation_outcome_never_advances_or_repeats_transition(self):
        self.executor.advance()
        self.ports.motion_exception = True
        with self.assertRaises(TimeoutError):
            self.executor.advance()
        self.assertEqual(self.executor.state, "DISPATCH_UNRESOLVED")
        with self.assertRaises(ExecutionBlocked):
            self.executor.recheck_endpoint()
        self.assertEqual(len(self.ports.motions), 2)

    def test_transition_must_match_exact_approach_exit_and_contact_anchors(self):
        turn = self.adapter.transitions[0]
        wrong_pair = replace(turn, incoming=("VILLA", "S"))
        with self.assertRaises(ExecutionBlocked):
            compile_taught_route(self.route, replace(self.adapter, transitions=(wrong_pair, self.adapter.transitions[1])), self.drawing)
        wrong_start = replace(turn.actions[0], start_base=pose(19), end_base=(19., 0., *turn.actions[0].end_base[2:]))
        wrong_contact = replace(turn.actions[1], start_base=wrong_start.end_base)
        bad_turn = replace(turn, actions=(wrong_start, wrong_contact))
        with self.assertRaises(ExecutionBlocked) as error:
            compile_taught_route(self.route, replace(self.adapter, transitions=(bad_turn, self.adapter.transitions[1])), self.drawing)
        self.assertEqual(error.exception.code, "TRANSITION_ANCHOR")

    def test_measured_wrist_direction_uses_joint_edge_and_preserves_literal_euler_branch(self):
        source = (0., 0., 10., -179.8, .1, 30.)
        target = (0., 0., 10., 179.9, .12, 35.)
        action = MeasuredTransitionAction("literal-branch", "rotate", source, target, "1"*64,
            "The free wrist makes the separately measured short turn while the car stays stationary.",
            "measured-positive-five", (0.,)*6, (0., 0., 0., 0., 0., 5.), "f"*64)
        self.assertEqual(action.end_base, target)
        self.assertEqual(action.expected_target_joint_deg[5]-action.expected_source_joint_deg[5], 5.)
        self.assertEqual(action.start_base[:3], action.end_base[:3])


def clearance_policy(junction="S", incoming=("PIZZA", "S"), contact=None, *, recontact=True):
    contact = pose(20) if contact is None else contact
    end = (contact[0], contact[1]+5., *contact[2:]) if junction == "S" else (contact[0]+5., *contact[1:])
    withdrawal = MeasuredTransitionAction("synthetic-side-observation", "translate", contact, end, "b"*64,
        "The physical pusher moves to its measured side observation pose while the car remains stationary.")
    returned = MeasuredTransitionAction("synthetic-reviewed-recontact", "translate", end, contact, "c"*64,
        "The physical pusher returns along its independently measured clear recontact path; the car remains stationary.") if recontact else None
    return MeasuredObservationClearance("synthetic-clearance-"+junction, junction, incoming, contact, "a"*64, withdrawal, returned)


def right_signal_target(*, camera_epoch="synthetic-camera-epoch", registration_id="synthetic-view"):
    return SignalObservationTarget("synthetic-right-signal", "S", "PIZZA",
        "Synthetic right-side paper signal region; placement metadata only, no physical signal qualification.",
        camera_epoch, registration_id, (1200, 300, 1400, 550), "e"*64)


class ObservationClearanceExecutorTests(unittest.TestCase):
    def setUp(self):
        self.drawing, self.adapter, self.route = configuration()
        self.adapter = replace(self.adapter, observation_clearances=(clearance_policy(),))
        self.ports = SyntheticPorts()
        self.executor = TaughtExecutor(self.route, self.adapter, self.drawing, self.ports, stroke_mm=20)

    def trigger(self):
        self.ports.review_verdict, self.ports.visible = "UNCERTAIN", False
        self.ports.occlusion_cause = "TOOL"
        result = self.executor.advance()
        self.assertEqual(result["state"], "CLEARANCE_READY")
        self.assertEqual(len(self.ports.motions), 1)
        return self.ports.motions[0]

    def test_first_junction_occlusion_automatically_selects_one_measured_side_path_then_fresh_sequence(self):
        original = self.trigger()
        result = self.executor.advance()
        self.assertEqual(result["state"], "WAIT_RECONTACT")
        self.assertEqual(len(self.ports.motions), 2)
        withdrawal = self.ports.motions[-1]
        self.assertEqual(withdrawal.start_base, pose(20))
        self.assertEqual(withdrawal.target_base, pose(20, 5))
        self.assertEqual(withdrawal.target_base[2:], withdrawal.start_base[2:])
        self.assertEqual(withdrawal.observation_clearance_id, "synthetic-clearance-S")
        self.assertEqual(len(self.ports.clearance_calls), 1)
        self.assertEqual(self.ports.clearance_calls[0][:2], (original.request_id, withdrawal.request_id))
        self.assertEqual(len(set(self.ports.clearance_calls[0][2:])), 3)
        self.assertEqual(result["observation_clearance"]["contact_pose"], list(pose(20)))
        self.assertTrue(result["observation_clearance"]["recontact_eligible"])
        self.assertEqual(self.executor.index, 0)  # Original route progress is not invented while withdrawn.
        with self.assertRaises(ExecutionBlocked):
            self.executor.advance()
        self.assertEqual(len(self.ports.motions), 2)  # No blind or automatic return.

    def test_provider_uncertainty_or_timeout_reobserves_without_repeating_withdrawal(self):
        self.trigger()
        self.ports.clearance_provider_timeout = True
        with self.assertRaises(TimeoutError):
            self.executor.advance()
        self.assertEqual(self.executor.state, "WAIT_CLEARANCE_REVIEW")
        self.ports.clearance_provider_timeout = False
        self.ports.clearance_verdict, self.ports.clearance_visible = "UNCERTAIN", False
        self.assertEqual(self.executor.reobserve()["state"], "WAIT_CLEARANCE_REVIEW")
        self.ports.clearance_verdict, self.ports.clearance_visible = "PASS", True
        self.assertEqual(self.executor.reobserve()["state"], "WAIT_RECONTACT")
        self.assertEqual(len(self.ports.motions), 2)
        self.assertEqual(len(self.ports.clearance_calls), 3)

    def test_ambiguous_withdrawal_never_returns_or_repeats_after_replay_request(self):
        self.trigger()
        self.ports.motion_exception = True
        with self.assertRaises(TimeoutError):
            self.executor.advance()
        self.assertEqual(self.executor.state, "DISPATCH_UNRESOLVED")
        for operation in (self.executor.advance, self.executor.reobserve, self.executor.recheck_endpoint):
            with self.assertRaises(ExecutionBlocked):
                operation()
        self.assertEqual(len(self.ports.motions), 2)
        self.assertFalse(self.ports.clearance_calls)

    def test_verified_withdrawal_then_native_timeout_recovers_readonly_before_sequence_review(self):
        self.trigger()
        execute = self.ports.execute_once
        def withdraw_then_fail_extra_read(intent):
            receipt = execute(intent)
            self.ports.fail_post_native_once = True
            return receipt
        self.ports.execute_once = withdraw_then_fail_extra_read
        with self.assertRaises(TimeoutError):
            self.executor.advance()
        self.assertEqual(self.executor.state, "WAIT_ENDPOINT_CONFIRMATION")
        self.assertIsNotNone(self.executor.pending[2])
        self.assertFalse(self.ports.clearance_calls)
        self.assertEqual(self.executor.recheck_endpoint()["state"], "WAIT_RECONTACT")
        self.assertEqual(len(self.ports.motions), 2)
        self.assertEqual(len(self.ports.clearance_calls), 1)

    def test_clearance_requires_a_newer_after_frame_and_reobserves_without_new_motion(self):
        self.trigger()
        execute = self.ports.execute_once
        def withdraw_then_reuse_frame(intent):
            receipt = execute(intent)
            self.ports.reuse_frame = True
            return receipt
        self.ports.execute_once = withdraw_then_reuse_frame
        with self.assertRaises(ExecutionBlocked):
            self.executor.advance()
        self.assertEqual(self.executor.state, "WAIT_CLEARANCE_REVIEW")
        self.assertFalse(self.ports.clearance_calls)
        self.ports.reuse_frame = False
        self.assertEqual(self.executor.reobserve()["state"], "WAIT_RECONTACT")
        self.assertEqual(len(self.ports.motions), 2)

    def test_changed_contact_or_insufficient_current_limit_blocks_withdrawal(self):
        self.trigger()
        self.ports.tcp = pose(20.1)
        with self.assertRaises(ExecutionBlocked):
            self.executor.advance()
        self.assertEqual(len(self.ports.motions), 1)
        self.ports.tcp = pose(20)
        self.ports.stroke_limit = 4.
        with self.assertRaises(ExecutionBlocked):
            self.executor.advance()
        self.assertEqual(len(self.ports.motions), 1)

    def test_clear_view_without_stationarity_or_measured_recontact_never_grants_recontact(self):
        self.trigger()
        self.ports.clearance_unchanged = False
        result = self.executor.advance()
        self.assertFalse(result["observation_clearance"]["recontact_eligible"])
        ports = SyntheticPorts()
        adapter = replace(self.adapter, observation_clearances=(clearance_policy(recontact=False),))
        executor = TaughtExecutor(self.route, adapter, self.drawing, ports, stroke_mm=20)
        ports.review_verdict, ports.visible = "UNCERTAIN", False
        ports.occlusion_cause = "TOOL"
        executor.advance()
        self.assertFalse(executor.advance()["observation_clearance"]["recontact_eligible"])

    def test_no_policy_or_nonfirst_junction_or_fail_review_never_triggers(self):
        self.ports.review_verdict = "FAIL"
        self.assertEqual(self.executor.advance()["state"], "NEEDS_RECONCILIATION")
        self.assertEqual(len(self.ports.motions), 1)
        drawing, adapter, route, edges = mixed_configuration()
        contact_c = adapter.roads[1].end_base
        adapter = replace(adapter, observation_clearances=(clearance_policy("C", ("S", "C"), contact_c),))
        ports = SyntheticPorts()
        ports.qualification_scope, ports.reviewed_edges, ports.runtime_hash = "local_contact_turn_commissioning", edges, "f"*64
        executor = TaughtExecutor(route, adapter, drawing, ports, stroke_mm=20)
        for _ in range(3):
            executor.advance()
        ports.review_verdict, ports.visible = "UNCERTAIN", False
        self.assertEqual(executor.advance()["state"], "WAIT_REVIEW")
        self.assertIsNone(executor.clearance_context)

    def test_forward_only_path_cannot_masquerade_as_observation_clearance(self):
        policy = clearance_policy()
        forward = replace(policy.withdrawal, end_base=pose(25))
        changed = replace(policy, withdrawal=forward, withdrawal_actions=(forward,), recontact=None)
        with self.assertRaises(ExecutionBlocked):
            compile_taught_route(self.route, replace(self.adapter, observation_clearances=(changed,)), self.drawing)

    def test_generic_uncertainty_non_tool_missing_car_and_pass_without_progress_do_not_trigger(self):
        for verdict, visible, cause, progress in (("UNCERTAIN", True, "UNKNOWN", False),
                ("UNCERTAIN", False, "OTHER", False), ("PASS", True, "TOOL", False)):
            with self.subTest(verdict=verdict, visible=visible, cause=cause):
                ports = SyntheticPorts()
                ports.review_verdict, ports.visible, ports.occlusion_cause, ports.expected_progress = verdict, visible, cause, progress
                executor = TaughtExecutor(self.route, self.adapter, self.drawing, ports, stroke_mm=20)
                self.assertEqual(executor.advance()["state"], "WAIT_REVIEW")
                self.assertIsNone(executor.clearance_context)
                self.assertEqual(len(ports.motions), 1)


class RightSignalObservationTests(unittest.TestCase):
    def setUp(self):
        self.drawing, adapter, self.route = configuration()
        self.policy = replace(clearance_policy(), required_signal_observation=right_signal_target())
        self.adapter = replace(adapter, observation_clearances=(self.policy,))
        self.ports = SyntheticPorts()
        self.executor = TaughtExecutor(self.route, self.adapter, self.drawing, self.ports, stroke_mm=20)

    def test_visible_car_and_passed_progress_still_clear_for_tool_covered_right_signal(self):
        self.ports.signal_occlusion_cause = "TOOL"
        self.assertEqual(self.executor.advance()["state"], "CLEARANCE_READY")
        self.assertTrue(self.ports.visible)
        self.assertEqual(self.ports.review_verdict, "PASS")
        result = self.executor.advance()
        self.assertEqual(result["state"], "WAIT_CLEARANCE_REVIEW")
        self.assertFalse(result["observation_clearance"]["recontact_eligible"])
        self.assertFalse(result["observation_clearance"]["signal_region_visible"])
        self.assertEqual(result["observation_clearance"]["required_signal_observation_id"], self.policy.required_signal_observation.id)
        self.ports.clearance_signal_visible = True
        result = self.executor.reobserve()
        self.assertEqual(result["state"], "WAIT_RECONTACT")
        self.assertTrue(result["observation_clearance"]["recontact_eligible"])
        self.assertEqual(len(self.ports.motions), 2)  # Visibility recheck never withdraws or returns again.

    def test_unknown_or_other_signal_visibility_does_not_guess_a_side_move(self):
        for cause in ("UNKNOWN", "OTHER"):
            ports = SyntheticPorts()
            ports.signal_occlusion_cause = cause
            executor = TaughtExecutor(self.route, self.adapter, self.drawing, ports, stroke_mm=20)
            with self.subTest(cause=cause):
                self.assertEqual(executor.advance()["state"], "WAIT_REVIEW")
                self.assertIsNone(executor.clearance_context)
                ports.signal_visible = True
                self.assertEqual(executor.reobserve()["state"], "READY")
                self.assertEqual(len(ports.motions), 1)

    def test_hidden_signal_during_approach_does_not_deadlock_before_observation_anchor(self):
        for cause, endpoint_state in (("TOOL", "CLEARANCE_READY"), ("UNKNOWN", "WAIT_REVIEW")):
            ports = SyntheticPorts()
            ports.signal_occlusion_cause = cause
            executor = TaughtExecutor(self.route, self.adapter, self.drawing, ports, stroke_mm=10)
            with self.subTest(cause=cause):
                self.assertEqual(executor.advance()["state"], "READY")
                self.assertEqual(ports.tcp, pose(10))
                self.assertIsNone(executor.clearance_context)
                self.assertEqual(executor.advance()["state"], endpoint_state)
                self.assertEqual(ports.tcp, pose(20))
                self.assertEqual(len(ports.motions), 2)

    def test_changed_camera_target_blocks_withdrawal_and_mismatched_approach_is_rejected(self):
        wrong_view = replace(self.policy, required_signal_observation=right_signal_target(camera_epoch="different-view"))
        executor = TaughtExecutor(self.route, replace(self.adapter, observation_clearances=(wrong_view,)), self.drawing,
                                 self.ports, stroke_mm=20)
        self.ports.signal_occlusion_cause = "TOOL"
        self.assertEqual(executor.advance()["state"], "CLEARANCE_READY")
        with self.assertRaisesRegex(ExecutionBlocked, "another camera epoch"):
            executor.advance()
        self.assertEqual(len(self.ports.motions), 1)
        with self.assertRaises(ValueError):
            replace(self.policy, required_signal_observation=replace(right_signal_target(), approach_from="C"))
        with self.assertRaises(ValueError):
            replace(right_signal_target(), target_evidence_sha256="missing-evidence")

    def test_qualified_left_rear_path_is_direction_neutral_and_exposes_both_targets(self):
        drawing, adapter, route, edges = mixed_configuration()
        contact = adapter.transitions[0].actions[-1].end_base
        first = (contact[0]-10., contact[1]-3., *contact[2:])
        last = (contact[0]-20., contact[1]-6., *contact[2:])
        actions = (
            MeasuredTransitionAction("synthetic-left-rear-1", "translate", contact, first, "a"*64,
                "The tool follows a measured left/rear segment to expose both car and right-side signal region."),
            MeasuredTransitionAction("synthetic-left-rear-2", "translate", first, last, "b"*64,
                "The tool completes the measured left/rear view path while the car stays stationary."),
        )
        policy = MeasuredObservationClearance("synthetic-left-rear-policy", "S", ("PIZZA", "S"), contact, "c"*64,
            withdrawal_actions=actions, transition_id=adapter.transitions[0].id, transition_action_id="s-contact",
            required_signal_observation=right_signal_target())
        ports = SyntheticPorts()
        ports.qualification_scope, ports.reviewed_edges, ports.runtime_hash = "local_contact_turn_commissioning", edges, "f"*64
        ports.signal_visible = True  # No clearance before the bound action endpoint.
        executor = TaughtExecutor(route, replace(adapter, observation_clearances=(policy,)), drawing, ports, stroke_mm=20)
        executor.advance(); executor.advance()
        ports.signal_visible, ports.signal_occlusion_cause = False, "TOOL"
        self.assertEqual(executor.advance()["state"], "CLEARANCE_READY")
        self.assertEqual(executor.advance()["state"], "CLEARANCE_READY")
        ports.clearance_signal_visible = True
        self.assertEqual(executor.advance()["state"], "WAIT_RECONTACT")
        self.assertEqual(ports.motions[-1].target_base, last)
        self.assertTrue(all(intent.target_base[0] < intent.start_base[0] and intent.target_base[1] < intent.start_base[1]
                            for intent in ports.motions[-2:]))
        self.assertEqual(len(ports.clearance_path_evidence), 2)

    def test_independently_qualified_pure_rear_path_is_allowed_without_east_bias(self):
        contact = self.policy.contact_pose
        rear = replace(self.policy.withdrawal, end_base=(contact[0]-5., *contact[1:]))
        policy = replace(self.policy, withdrawal=rear, withdrawal_actions=(rear,), recontact=None)
        compile_taught_route(self.route, replace(self.adapter, observation_clearances=(policy,)), self.drawing)
        ports = SyntheticPorts()
        ports.signal_occlusion_cause, ports.clearance_signal_visible = "TOOL", True
        executor = TaughtExecutor(self.route, replace(self.adapter, observation_clearances=(policy,)), self.drawing, ports, stroke_mm=20)
        self.assertEqual(executor.advance()["state"], "CLEARANCE_READY")
        self.assertEqual(executor.advance()["state"], "WAIT_RECONTACT")
        self.assertEqual(ports.motions[-1].target_base, rear.end_base)

    def test_joint_branch_change_during_review_cannot_authorize_clearance_or_recontact(self):
        for phase in ("original", "clearance"):
            ports = SyntheticPorts()
            ports.signal_occlusion_cause, ports.clearance_signal_visible = "TOOL", True
            executor = TaughtExecutor(self.route, self.adapter, self.drawing, ports, stroke_mm=20)
            method = ports.review if phase == "original" else ports.review_clearance
            def change_joint_branch(*args, **kwargs):
                result = method(*args, **kwargs)
                ports.joints = (0., 0., 0., 0., 0., 1.)
                return result
            if phase == "original":
                ports.review = change_joint_branch
            else:
                ports.review_clearance = change_joint_branch
                self.assertEqual(executor.advance()["state"], "CLEARANCE_READY")
            with self.subTest(phase=phase), self.assertRaises(ExecutionBlocked):
                executor.advance()
            self.assertEqual(executor.state, "NEEDS_RECONCILIATION")
            self.assertEqual(len(ports.motions), 1 if phase == "original" else 2)
            if executor.clearance_context is not None:
                self.assertFalse(executor.clearance_context["recontact_eligible"])
            with self.assertRaises(ExecutionBlocked):
                executor.reobserve()


class TransitionMultiPathObservationTests(unittest.TestCase):
    def setUp(self):
        self.drawing, adapter, self.route, edges = mixed_configuration()
        contact = adapter.transitions[0].actions[-1].end_base
        first_end, last_end = (contact[0]+12.5, *contact[1:]), (contact[0]+25., *contact[1:])
        actions = (
            MeasuredTransitionAction("synthetic-east-observation-1", "translate", contact, first_end, "a"*64,
                "The tool moves along the first measured side-withdrawal segment; the car should remain stationary."),
            MeasuredTransitionAction("synthetic-east-observation-2", "translate", first_end, last_end, "b"*64,
                "The tool completes the second measured side-withdrawal segment to expose the stationary car."),
        )
        policy = MeasuredObservationClearance("synthetic-transition-side-view", "S", ("PIZZA", "S"), contact, "c"*64,
            withdrawal_actions=actions, transition_id="synthetic-s-turn", transition_action_id="s-contact")
        self.adapter = replace(adapter, observation_clearances=(policy,))
        self.ports = SyntheticPorts()
        self.ports.qualification_scope, self.ports.reviewed_edges, self.ports.runtime_hash = "local_contact_turn_commissioning", edges, "f"*64
        self.executor = TaughtExecutor(self.route, self.adapter, self.drawing, self.ports, stroke_mm=20)

    def trigger(self):
        self.executor.advance()
        self.executor.advance()
        self.ports.review_verdict, self.ports.visible, self.ports.occlusion_cause = "UNCERTAIN", True, "TOOL"
        self.assertEqual(self.executor.advance()["state"], "CLEARANCE_READY")
        self.assertEqual(self.ports.motions[-1].transition_action_id, "s-contact")

    def test_registry_ids_cannot_alias_different_junctions_or_policy_targets(self):
        first, second = self.adapter.transitions
        with self.assertRaises(ValueError):
            replace(self.adapter, transitions=(first, replace(second, id=first.id)))
        targeted = self.adapter.observation_clearances[0]
        road_endpoint = clearance_policy()
        with self.assertRaises(ValueError):
            replace(self.adapter, observation_clearances=(targeted, replace(road_endpoint, id=targeted.id)))

    def test_exact_first_transition_action_has_two_bounded_steps_and_whole_path_review(self):
        self.trigger()
        self.assertEqual(self.executor.advance()["state"], "CLEARANCE_READY")
        first_before = self.executor.clearance_context["path_before"]
        self.assertEqual(len(self.ports.motions), 4)
        self.assertFalse(self.ports.clearance_calls)
        result = self.executor.advance()
        self.assertEqual(result["state"], "WAIT_RECONTACT")
        first, second = self.ports.motions[-2:]
        self.assertEqual([math.dist(intent.start_base[:2], intent.target_base[:2]) for intent in (first, second)], [12.5, 12.5])
        self.assertEqual(first.target_base, second.start_base)
        self.assertEqual(second.target_base[0]-first.start_base[0], 25.)
        self.assertEqual(second.observation_junction_id, "S")
        self.assertEqual(second.target, "C")  # Spanning transition labels cannot supply junction identity.
        self.assertEqual(len(self.ports.clearance_calls), 1)
        self.assertEqual(self.ports.clearance_calls[0][3], first_before.sha256)
        self.assertNotEqual(first_before.sha256, self.executor.pending[1].sha256)
        self.assertEqual(len(self.ports.clearance_path_evidence), 2)
        self.assertEqual(result["observation_clearance"]["completed_withdrawal_request_ids"], [first.request_id, second.request_id])

    def test_readonly_first_endpoint_recovery_cannot_dispatch_second_step(self):
        self.trigger()
        execute = self.ports.execute_once
        def known_then_missing_native(intent):
            receipt = execute(intent)
            self.ports.fail_post_native_once = True
            return receipt
        self.ports.execute_once = known_then_missing_native
        with self.assertRaises(TimeoutError):
            self.executor.advance()
        self.assertEqual(self.executor.state, "WAIT_ENDPOINT_CONFIRMATION")
        self.assertEqual(len(self.ports.motions), 4)
        self.assertEqual(self.executor.recheck_endpoint()["state"], "CLEARANCE_READY")
        self.assertEqual(len(self.ports.motions), 4)
        self.assertFalse(self.ports.clearance_calls)
        self.assertEqual(self.executor.clearance_context["withdrawal_index"], 1)

    def test_failed_first_path_endpoint_event_recovers_bookkeeping_without_skipping_second_step(self):
        self.trigger()
        append = self.ports.append_event
        fail_once = [True]
        def endpoint_write_failure(kind, payload):
            if kind == "observation_path_endpoint" and fail_once[0]:
                fail_once[0] = False
                raise OSError("Synthetic pre-write endpoint bookkeeping failure.")
            return append(kind, payload)
        self.ports.append_event = endpoint_write_failure
        with self.assertRaises(OSError):
            self.executor.advance()
        self.assertEqual(self.executor.state, "WAIT_CLEARANCE_REVIEW")
        self.assertEqual(self.executor.clearance_context["withdrawal_index"], 0)
        self.assertEqual(self.executor.clearance_context["path_records"], [])
        self.assertEqual(self.executor.reobserve()["state"], "CLEARANCE_READY")
        self.assertEqual(len(self.ports.motions), 4)
        self.assertEqual(len(self.executor.clearance_context["path_records"]), 1)
        self.assertFalse(self.ports.clearance_calls)

    def test_fresh_frame_reobservation_after_first_endpoint_cannot_move_to_second_step(self):
        self.trigger()
        execute = self.ports.execute_once
        def known_then_missing_frame(intent):
            receipt = execute(intent)
            self.ports.reuse_frame = True
            return receipt
        self.ports.execute_once = known_then_missing_frame
        with self.assertRaises(ExecutionBlocked):
            self.executor.advance()
        self.assertEqual(self.executor.state, "WAIT_CLEARANCE_REVIEW")
        self.ports.reuse_frame = False
        self.assertEqual(self.executor.reobserve()["state"], "CLEARANCE_READY")
        self.assertEqual(len(self.ports.motions), 4)
        self.assertFalse(self.ports.clearance_calls)

    def test_ambiguous_second_step_preserves_first_receipt_and_never_replays_or_returns(self):
        self.trigger()
        self.executor.advance()
        first_before = self.executor.clearance_context["path_before"]
        first_records = list(self.executor.clearance_context["path_records"])
        self.ports.motion_exception = True
        with self.assertRaises(TimeoutError):
            self.executor.advance()
        self.assertEqual(self.executor.state, "DISPATCH_UNRESOLVED")
        self.assertEqual(self.executor.clearance_context["path_records"], first_records)
        self.assertEqual(self.executor.clearance_context["path_before"], first_before)
        for callback in (self.executor.advance, self.executor.reobserve, self.executor.recheck_endpoint):
            with self.assertRaises(ExecutionBlocked):
                callback()
        self.assertEqual(len(self.ports.motions), 5)

    def test_provider_reobservation_keeps_entire_two_step_path_and_first_before(self):
        self.trigger()
        self.executor.advance()
        first_before = self.executor.clearance_context["path_before"]
        self.ports.clearance_provider_timeout = True
        with self.assertRaises(TimeoutError):
            self.executor.advance()
        self.assertEqual(self.executor.state, "WAIT_CLEARANCE_REVIEW")
        self.assertEqual(len(self.executor.clearance_context["path_records"]), 2)
        self.ports.clearance_provider_timeout = False
        self.assertEqual(self.executor.reobserve()["state"], "WAIT_RECONTACT")
        self.assertEqual(len(self.ports.motions), 5)
        self.assertEqual(self.ports.clearance_calls[-1][3], first_before.sha256)
        self.assertEqual(len(self.ports.clearance_path_evidence), 2)

    def test_wrist_action_target_requires_explicit_contact_direction_and_exact_target_id(self):
        policy = self.adapter.observation_clearances[0]
        wrong = replace(policy, transition_action_id="missing-action")
        with self.assertRaises(ExecutionBlocked):
            compile_taught_route(self.route, replace(self.adapter, observation_clearances=(wrong,)), self.drawing)
        wrist = self.adapter.transitions[0].actions[0]
        end = (wrist.end_base[0]+5., *wrist.end_base[1:])
        action = MeasuredTransitionAction("synthetic-wrist-view", "translate", wrist.end_base, end, "a"*64,
            "The pusher moves along its measured side-view path; the car is expected to remain stationary.")
        selected = MeasuredObservationClearance("synthetic-wrist-policy", "S", ("PIZZA", "S"), wrist.end_base, "b"*64,
            withdrawal_actions=(action,), transition_id="synthetic-s-turn", transition_action_id="s-wrist")
        with self.assertRaises(ExecutionBlocked):
            compile_taught_route(self.route, replace(self.adapter, observation_clearances=(selected,)), self.drawing)
        compile_taught_route(self.route, replace(self.adapter, observation_clearances=(replace(selected, contact_direction_base_xy=(0., 1.)),)), self.drawing)


if __name__ == "__main__":
    unittest.main()
