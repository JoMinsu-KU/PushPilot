"""Offline physical coordinator tests with synthetic coordinates and IO only."""
from dataclasses import replace
import hashlib
from pathlib import Path
import unittest

from backend.maps import MapDefinition
from backend.robot_control.taught_executor import (
    ApprovedRoute, ExecutionBlocked, Frame, MeasuredRoad, MeasuredTransition, MeasuredTransitionAction, MotionReceipt,
    Snapshot, TaughtAdapter, TaughtExecutor, VehicleReview, compile_taught_route,
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
        self.review_verdict, self.visible, self.excessive_yaw = "PASS", True, False
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
            self.review_verdict, self.visible, True, self.excessive_yaw,
            at_goal if self.force_arrived is None else self.force_arrived, "Synthetic original-pair result.")

    def hold(self, reason):
        self.holds.append(reason)

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


if __name__ == "__main__":
    unittest.main()
