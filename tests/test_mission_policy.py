"""Equipment-free mission tests: no recorded robot data creates authority."""
from dataclasses import FrozenInstanceError, replace
import unittest

from backend.robot_control.mission_policy import (
    CarObservation, CorrectionTemplate, DecisionKind, MissionPlan, MissionPolicy,
    MotionReceipt, ParkingTarget, Phase, RouteStep, RuntimeContext, SignalGate,
    SignalObservation, SiteBinding, StartObservation, TaughtPrimitive, ViewClearance,
    angle_error,
)


BINDING = SiteBinding("synthetic-installation", "a" * 64, "synthetic-calibration",
                      "synthetic-tool", "synthetic-car", "synthetic-camera")


def primitive(name, source, target, *, empty=False, qualified=True):
    return TaughtPrimitive(name, source, target, "b" * 64, qualified, empty)


def plan(*, signal=False, corrections=(), clearances=(), parking=None):
    steps = (RouteStep("delivery", primitive("delivery-unit", "START", "GOAL_PARK"), "GOAL", 0., True),)
    if signal:
        gate = SignalGate("SOUTH_SIGNAL", "RIGHT_WAIT", "LAST_CONTACT",
                         primitive("recontact", "RIGHT_WAIT", "LAST_CONTACT"),
                         primitive("release-to-right", "LAST_CONTACT", "RIGHT_WAIT", empty=True))
        steps = (RouteStep("approach", primitive("approach-unit", "START", "RIGHT_WAIT"), "STOP", 90., signal_gate=gate),
                 RouteStep("delivery", primitive("crossing-unit", "LAST_CONTACT", "GOAL_PARK"), "GOAL", 0., True))
    return MissionPlan("synthetic-mission", "HANOK", BINDING, steps, parking or ParkingTarget(0.),
                       (primitive("return", "GOAL_PARK", "START", empty=True),), "START",
                       corrections=corrections, clearances=clearances)


def context(where="START", now=10., seq=1, **changes):
    value = RuntimeContext(now, BINDING, "session", seq, now, where, True, True)
    return replace(value, **changes)


def start(at):
    return StartObservation("synthetic-mission", BINDING, "session", at.native_sequence,
                            at.context_id, at.now_s, "c" * 64, "d" * 64, True, True, True, True)


def car(at, state, *, step="delivery", zone="GOAL", image="e", **changes):
    value = CarObservation("synthetic-mission", step, state.action_command_id, BINDING,
        "session", at.native_sequence, at.context_id, at.now_s, image * 64, "f" * 64,
        "PASS", True, True, True, True, True, zone,
        heading_deg=0., heading_uncertainty_deg=2., lateral_error_mm=0., lateral_uncertainty_mm=1.,
        measurement_source="qualified_estimator", measurement_evidence_sha256="1" * 64)
    return replace(value, **changes)


def signal(at, *, color="GREEN", image="2", **changes):
    value = SignalObservation("SOUTH_SIGNAL", BINDING, "session", at.native_sequence,
        at.context_id, at.now_s, image * 64, "3" * 64, color, True, True, True,
        exclusive_green=color == "GREEN")
    return replace(value, **changes)


def completed(policy, decision, at=11.):
    return policy.accept_receipt(decision.state, MotionReceipt(decision.command_id,
        decision.primitive_id, "session", decision.state.pending_target_context_id, at, True, "COMPLETED"))


def after_first(policy):
    at = context()
    dispatch = policy.decide(policy.initial_state("session"), at, start=start(at), command_id="motion-1")
    assert dispatch.kind == DecisionKind.DISPATCH
    return completed(policy, dispatch)


class MissionPolicyTests(unittest.TestCase):
    def test_contracts_are_immutable_and_inputs_reject_nan(self):
        with self.assertRaises(FrozenInstanceError):
            BINDING.tool_id = "other"
        with self.assertRaises(ValueError):
            replace(plan().parking, tolerance_deg=float("nan"))
        with self.assertRaises(ValueError):
            context(now=float("nan"))

    def test_initial_start_observation_required_once_then_coordinate_execution(self):
        policy = MissionPolicy(plan())
        state = policy.initial_state("session")
        decision = policy.decide(state, context(), command_id="motion-1")
        self.assertEqual(decision.kind, DecisionKind.OBSERVE)
        self.assertEqual(decision.state.phase, Phase.READY)
        dispatch = policy.decide(decision.state, context(), start=start(context()), command_id="motion-1")
        self.assertEqual(dispatch.kind, DecisionKind.DISPATCH)
        self.assertTrue(dispatch.state.start_verified)
        # The policy does not ask for tool/car images in the motion itself.
        waiting = policy.decide(dispatch.state, context(stationary=False), command_id="unused")
        self.assertEqual(waiting.reason, "AWAIT_EXACT_COMMAND_RECEIPT")

    def test_unqualified_primitive_cannot_be_promoted_by_observation(self):
        configuration = plan()
        configuration = replace(configuration, steps=(replace(configuration.steps[0],
            primitive=replace(configuration.steps[0].primitive, qualified=False)),))
        policy = MissionPolicy(configuration)
        decision = policy.decide(policy.initial_state("session"), context(), start=start(context()), command_id="m")
        self.assertEqual(decision.state.phase, Phase.FAILED)
        self.assertIn("NOT_QUALIFIED", decision.reason)

    def test_qualitative_arrival_does_not_claim_measured_parallel_parking(self):
        policy = MissionPolicy(plan())
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        observation = car(at, state, heading_deg=None, heading_uncertainty_deg=None,
                          measurement_source="unmeasured", measurement_evidence_sha256=None)
        decision = policy.decide(state, at, car=observation, command_id="return")
        self.assertEqual(decision.kind, DecisionKind.OBSERVE)
        self.assertFalse(decision.state.vehicle_delivered)

    def test_delivery_only_accepts_unmeasured_goal_and_returns_empty_tool(self):
        policy = MissionPolicy(plan(parking=ParkingTarget(0., lateral_tolerance_mm=3., mode="delivery_only")))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        observation = car(at, state, heading_deg=None, heading_uncertainty_deg=None,
                          lateral_error_mm=None, lateral_uncertainty_mm=None,
                          heading_matches_expected=False, expected_progress=False,
                          measurement_source="unmeasured", measurement_evidence_sha256=None)
        decision = policy.decide(state, at, car=observation, command_id="return-1")
        self.assertEqual(decision.primitive_id, "return")
        self.assertEqual(decision.state.pending_role, "RETURN")
        self.assertTrue(decision.state.vehicle_delivered)
        # Arrival does not certify an angle, lateral error, or parallel parking.
        self.assertFalse(observation.measured_heading)
        self.assertFalse(observation.measured_lateral)
        returned = completed(policy, decision, 14.)
        result = policy.decide(returned, context("START", 15., 3))
        self.assertEqual(result.kind, DecisionKind.COMPLETE)

    def test_delivery_only_does_not_dispatch_final_alignment_even_when_measured_skewed(self):
        template = CorrectionTemplate(primitive("align", "GOAL_PARK", "GOAL_PARK"),
            "delivery", "GOAL", (18., 32.), (-3., 3.), -12., 0., True)
        policy = MissionPolicy(plan(parking=ParkingTarget(0., mode="delivery_only"), corrections=(template,)))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        result = policy.decide(state, at, car=car(at, state, heading_deg=25.), command_id="return-1")
        self.assertEqual(result.primitive_id, "return")
        self.assertEqual(result.state.correction_count, 0)

    def test_delivery_only_requires_original_pass_and_arrival(self):
        policy = MissionPolicy(plan(parking=ParkingTarget(0., mode="delivery_only")))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        for changes, reason in (({"verdict": "FAIL"}, "DELIVERY_REQUIRES_ORIGINAL_PASS"),
                                ({"verdict": "UNCERTAIN"}, "MUSE_UNCERTAIN"),
                                ({"arrived": False}, "GOAL_ARRIVAL_UNCONFIRMED")):
            with self.subTest(changes=changes):
                result = policy.decide(state, at, car=car(at, state, **changes), command_id="return-1")
                self.assertEqual(result.kind, DecisionKind.OBSERVE)
                self.assertEqual(result.reason, reason)
                self.assertFalse(result.state.vehicle_delivered)

    def test_delivery_only_preserves_visibility_road_zone_and_source_checks(self):
        policy = MissionPolicy(plan(parking=ParkingTarget(0., mode="delivery_only")))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        for changes in ({"car_visible": False}, {"occlusion_cause": "HOSE"},
                        {"within_road": False}, {"within_road": None}, {"car_zone_id": "OTHER"},
                        {"captured_at_s": 9.}, {"captured_at_s": 13.},
                        {"native_sequence": 99}, {"action_command_id": "foreign"},
                        {"binding": replace(BINDING, camera_epoch="moved")}):
            with self.subTest(changes=changes):
                result = policy.decide(state, at, car=car(at, state, **changes), command_id="return-1")
                self.assertNotEqual(result.kind, DecisionKind.DISPATCH)
                self.assertFalse(result.state.vehicle_delivered)

    def test_delivery_only_preserves_stationary_native_and_withdrawal_checks(self):
        policy = MissionPolicy(plan(parking=ParkingTarget(0., mode="delivery_only")))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        for changes in ({"stationary": False}, {"tool_clear": False},
                        {"native_observed_at_s": 1.}, {"pending_command_id": "foreign"},
                        {"control_fault": "FAULT"}, {"session_id": "different"}):
            with self.subTest(changes=changes):
                result = policy.decide(state, replace(at, **changes), car=car(at, state), command_id="return-1")
                self.assertEqual(result.kind, DecisionKind.HOLD)
                self.assertFalse(result.state.vehicle_delivered)

    def test_delivery_only_preserves_intermediate_drift_checks(self):
        policy = MissionPolicy(plan(signal=True, parking=ParkingTarget(0., mode="delivery_only")))
        state, at = after_first(policy), context("RIGHT_WAIT", 12., 2)
        observation = car(at, state, step="approach", zone="STOP", arrived=True,
                          heading_matches_expected=False, heading_deg=None, heading_uncertainty_deg=None,
                          measurement_source="unmeasured", measurement_evidence_sha256=None)
        result = policy.decide(state, at, car=observation, command_id="next")
        self.assertEqual(result.reason, "MEASURED_CORRECTION_PRECONDITIONS_REQUIRED")
        self.assertEqual(result.kind, DecisionKind.OBSERVE)
        self.assertFalse(result.state.vehicle_delivered)

    def test_delivery_only_preserves_qualified_intermediate_correction_selection(self):
        template = CorrectionTemplate(primitive("route-correct", "RIGHT_WAIT", "RIGHT_WAIT"),
            "approach", "STOP", (18., 32.), (-3., 3.), -12., 0.)
        policy = MissionPolicy(plan(signal=True, corrections=(template,),
                                    parking=ParkingTarget(0., mode="delivery_only")))
        state, at = after_first(policy), context("RIGHT_WAIT", 12., 2)
        observation = car(at, state, step="approach", zone="STOP", arrived=False, heading_deg=115.)
        result = policy.decide(state, at, car=observation, command_id="correct-1")
        self.assertEqual(result.primitive_id, "route-correct")
        self.assertEqual(result.state.pending_role, "CORRECTION")
        self.assertFalse(result.state.vehicle_delivered)

    def test_delivery_only_preserves_red_signal_gate_with_unmeasured_car(self):
        policy = MissionPolicy(plan(signal=True, parking=ParkingTarget(0., mode="delivery_only")))
        state, at = after_first(policy), context("RIGHT_WAIT", 12., 2)
        observation = car(at, state, step="approach", zone="STOP", arrived=False,
                          heading_deg=None, heading_uncertainty_deg=None,
                          measurement_source="unmeasured", measurement_evidence_sha256=None)
        result = policy.decide(state, at, car=observation, signal=signal(at, color="RED"), command_id="next")
        self.assertEqual(result.kind, DecisionKind.WAIT)
        self.assertEqual(result.state.phase, Phase.WAIT_SIGNAL)
        self.assertFalse(result.state.vehicle_delivered)

    def test_delivery_only_cannot_bypass_unqualified_empty_return(self):
        configuration = plan(parking=ParkingTarget(0., mode="delivery_only"))
        configuration = replace(configuration, empty_return=(replace(configuration.empty_return[0], qualified=False),))
        policy = MissionPolicy(configuration)
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        result = policy.decide(state, at, car=car(at, state), command_id="return-1")
        self.assertEqual(result.kind, DecisionKind.HOLD)
        self.assertTrue(result.state.vehicle_delivered)
        self.assertNotEqual(result.state.phase, Phase.COMPLETE)
        self.assertIn("NOT_QUALIFIED", result.reason)

    def test_completion_mode_is_explicit_and_defaults_to_parallel_alignment(self):
        self.assertEqual(ParkingTarget(0.).mode, "parallel_alignment")
        with self.assertRaises(ValueError):
            ParkingTarget(0., mode="any_arrival")

    def test_muse_numeric_guess_is_not_a_qualified_heading_estimator(self):
        policy = MissionPolicy(plan())
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        decision = policy.decide(state, at, car=car(at, state, measurement_source="muse_estimate"), command_id="return")
        self.assertEqual(decision.reason, "MEASURED_PARKING_HEADING_REQUIRED")

    def test_uncertainty_is_included_in_parking_tolerance(self):
        policy = MissionPolicy(plan())
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        decision = policy.decide(state, at, car=car(at, state, heading_deg=14., heading_uncertainty_deg=2.), command_id="m")
        self.assertFalse(decision.state.vehicle_delivered)
        self.assertEqual(decision.reason, "NO_QUALIFIED_CORRECTION_FOR_OBSERVED_STATE")

    def test_parallel_axis_accepts_opposite_nose_and_returns_tool_only(self):
        policy = MissionPolicy(plan())
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        decision = policy.decide(state, at, car=car(at, state, heading_deg=179.), command_id="return-1")
        self.assertEqual(decision.primitive_id, "return")
        self.assertTrue(decision.state.vehicle_delivered)
        self.assertEqual(decision.state.pending_role, "RETURN")
        state = completed(policy, decision, 14.)
        done = policy.decide(state, context("START", 15., 3))
        self.assertEqual(done.kind, DecisionKind.COMPLETE)
        self.assertEqual(done.state.phase, Phase.COMPLETE)

    def test_directed_parking_rejects_wrong_nose_even_when_parallel(self):
        policy = MissionPolicy(plan(parking=ParkingTarget(0., parallel_axis=False)))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        result = policy.decide(state, at, car=car(at, state, heading_deg=179.), command_id="m")
        self.assertFalse(result.state.vehicle_delivered)

    def test_lateral_parking_tolerance_requires_qualified_lateral_measurement(self):
        policy = MissionPolicy(plan(parking=ParkingTarget(0., lateral_tolerance_mm=3.)))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        result = policy.decide(state, at, car=car(at, state, lateral_error_mm=None), command_id="m")
        self.assertEqual(result.reason, "MEASURED_PARKING_LATERAL_REQUIRED")

    def test_finite_corrective_template_with_observation_envelope(self):
        template = CorrectionTemplate(primitive("align", "GOAL_PARK", "GOAL_PARK"),
            "delivery", "GOAL", (18., 32.), (-3., 3.), -12., 0., True)
        policy = MissionPolicy(plan(corrections=(template,)))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        decision = policy.decide(state, at, car=car(at, state, heading_deg=25.), command_id="align-1")
        self.assertEqual(decision.primitive_id, "align")
        self.assertEqual(decision.state.pending_role, "PARKING")
        state = completed(policy, decision, 13.)
        at = context("GOAL_PARK", 14., 3)
        result = policy.decide(state, at, car=car(at, state, heading_deg=10., image="4"), command_id="return-1")
        self.assertTrue(result.state.vehicle_delivered)

    def test_uncertainty_must_fit_inside_correction_envelope(self):
        template = CorrectionTemplate(primitive("align", "GOAL_PARK", "GOAL_PARK"),
            "delivery", "GOAL", (18., 25.), (-3., 3.), -12., 0.)
        policy = MissionPolicy(plan(corrections=(template,)))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        result = policy.decide(state, at, car=car(at, state, heading_deg=25.), command_id="align-1")
        self.assertEqual(result.reason, "NO_QUALIFIED_CORRECTION_FOR_OBSERVED_STATE")

    def test_nonimproving_corrections_terminate_without_unbounded_retry(self):
        template = CorrectionTemplate(primitive("align", "GOAL_PARK", "GOAL_PARK"),
            "delivery", "GOAL", (18., 32.), (-3., 3.), -12., 0.)
        policy = MissionPolicy(plan(corrections=(template,)))
        state = after_first(policy)
        for index, digest in enumerate(("4", "5", "6")):
            at = context("GOAL_PARK", 12. + index * 3, index + 2)
            result = policy.decide(state, at, car=car(at, state, heading_deg=25., image=digest), command_id=f"align-{index}")
            if index < 2:
                self.assertEqual(result.kind, DecisionKind.DISPATCH)
                state = completed(policy, result, at.now_s + 1.)
            else:
                self.assertEqual(result.reason, "CORRECTIONS_NOT_IMPROVING")

    def test_car_outside_road_never_admits_a_correction(self):
        policy = MissionPolicy(plan())
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        result = policy.decide(state, at, car=car(at, state, within_road=False), command_id="m")
        self.assertEqual(result.reason, "CAR_OUTSIDE_QUALIFIED_ROAD")

    def test_qualified_left_clearance_is_automatic_for_general_hose_occlusion(self):
        clearance = ViewClearance(primitive("left-clear", "GOAL_PARK", "LEFT_PARK", empty=True),
                                  "delivery", "LEFT", True)
        policy = MissionPolicy(plan(clearances=(clearance,)))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        result = policy.decide(state, at, car=car(at, state, car_visible=False, occlusion_cause="HOSE"), command_id="clear-1")
        self.assertEqual(result.primitive_id, "left-clear")
        updated = completed(policy, result, 13.)
        self.assertEqual(updated.phase, Phase.OBSERVE)
        self.assertEqual(updated.action_command_id, "motion-1")
        self.assertEqual(updated.used_clearances, ("left-clear",))

    def test_alternative_view_restores_reviewed_source_before_empty_return(self):
        clearance = ViewClearance(primitive("left-clear", "GOAL_PARK", "LEFT_PARK", empty=True),
            "delivery", "LEFT", True,
            restore=primitive("restore-view", "LEFT_PARK", "GOAL_PARK", empty=True))
        policy = MissionPolicy(plan(clearances=(clearance,)))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        cleared = policy.decide(state, at, car=car(at, state, car_visible=False, occlusion_cause="HOSE"), command_id="clear-1")
        state = completed(policy, cleared, 13.)
        at = context("LEFT_PARK", 14., 3)
        restored = policy.decide(state, at, car=car(at, state, image="4"), command_id="restore-1")
        self.assertTrue(restored.state.vehicle_delivered)
        self.assertEqual(restored.primitive_id, "restore-view")
        state = completed(policy, restored, 15.)
        self.assertEqual(state.phase, Phase.RETURNING)
        returned = policy.decide(state, context("GOAL_PARK", 16., 4), command_id="return-1")
        self.assertEqual(returned.primitive_id, "return")

    def test_uncertainty_reobservation_budget_never_replays_contact(self):
        policy = MissionPolicy(plan())
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        for digest in ("4", "5", "6", "7"):
            result = policy.decide(state, at, car=car(at, state, image=digest, verdict="UNCERTAIN"), command_id="unused")
            self.assertNotEqual(result.kind, DecisionKind.DISPATCH)
            state = result.state
        self.assertEqual(state.phase, Phase.FAILED)

    def test_duplicate_frame_is_not_new_reobservation(self):
        policy = MissionPolicy(plan())
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        observation = car(at, state, verdict="UNCERTAIN")
        first = policy.decide(state, at, car=observation)
        second = policy.decide(first.state, at, car=observation)
        self.assertEqual(second.reason, "NEW_ORIGINAL_FRAME_REQUIRED")

    def test_stale_car_wrong_source_or_future_frame_never_advances(self):
        policy = MissionPolicy(plan())
        state, at = after_first(policy), context("GOAL_PARK", 50., 2)
        for changes in ({"captured_at_s": 12.}, {"captured_at_s": 51.},
                        {"action_command_id": "other"}, {"native_sequence": 100}):
            with self.subTest(changes=changes):
                result = policy.decide(state, at, car=car(at, state, **changes), command_id="m")
                self.assertEqual(result.reason, "FRESH_BOUND_CAR_OBSERVATION_REQUIRED")

    def test_unknown_motion_is_terminal_and_restart_does_not_replay(self):
        policy = MissionPolicy(plan())
        decision = policy.decide(policy.initial_state("session"), context(), start=start(context()), command_id="m")
        unresolved = policy.accept_receipt(decision.state, MotionReceipt("m", "delivery-unit", "session", "GOAL_PARK", 11., False, "UNKNOWN"))
        self.assertEqual(unresolved.phase, Phase.NEEDS_RECONCILIATION)
        result = policy.decide(unresolved, context(), start=start(context()), command_id="m2")
        self.assertEqual(result.kind, DecisionKind.HOLD)
        self.assertEqual(policy.restart(decision.state).phase, Phase.NEEDS_RECONCILIATION)

    def test_foreign_native_or_command_receipt_cannot_advance(self):
        policy = MissionPolicy(plan())
        dispatch = policy.decide(policy.initial_state("session"), context(), start=start(context()), command_id="m")
        for changes in ({"command_id": "other"}, {"session_id": "old"},
                        {"target_context_id": "elsewhere"}, {"completed_at_s": 1.}, {"native_verified": False}):
            with self.subTest(changes=changes):
                receipt = replace(MotionReceipt("m", "delivery-unit", "session", "GOAL_PARK", 11., True, "COMPLETED"), **changes)
                self.assertEqual(policy.accept_receipt(dispatch.state, receipt).phase, Phase.NEEDS_RECONCILIATION)

    def test_runtime_changes_stop_before_next_dispatch(self):
        policy = MissionPolicy(plan())
        state = after_first(policy)
        for changes in ({"session_id": "other"}, {"stationary": False},
                        {"pending_command_id": "foreign"}, {"native_observed_at_s": 1.},
                        {"binding": replace(BINDING, camera_epoch="moved")}):
            with self.subTest(changes=changes):
                result = policy.decide(state, context("GOAL_PARK", 12., 2, **changes))
                self.assertEqual(result.state.phase, Phase.NEEDS_RECONCILIATION)

    def test_duplicate_command_id_is_rejected_even_after_motion_completed(self):
        policy = MissionPolicy(plan())
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        result = policy.decide(state, at, car=car(at, state), command_id="motion-1")
        self.assertEqual(result.reason, "NEW_DURABLE_COMMAND_ID_REQUIRED")

    def _wait_at_signal(self):
        policy = MissionPolicy(plan(signal=True))
        state, at = after_first(policy), context("RIGHT_WAIT", 12., 2)
        observation = car(at, state, step="approach", zone="STOP", arrived=False, heading_deg=90.)
        decision = policy.decide(state, at, car=observation, signal=signal(at, color="RED"))
        self.assertEqual(decision.state.phase, Phase.WAIT_SIGNAL)
        return policy, decision.state, at, observation

    def test_red_unknown_both_colors_hand_and_stale_wait_without_fault(self):
        policy, state, at, observation = self._wait_at_signal()
        for changes in ({"color": "RED"}, {"color": "UNKNOWN"}, {"exclusive_green": False},
                        {"signal_visible": False}, {"car_visible": False}, {"captured_at_s": 0.}):
            with self.subTest(changes=changes):
                result = policy.decide(state, at, car=observation, signal=signal(at, **changes), command_id="m")
                self.assertEqual(result.kind, DecisionKind.WAIT)
                self.assertEqual(result.state.phase, Phase.WAIT_SIGNAL)

    def test_green_requires_two_distinct_fresh_frames_then_explicit_recontact(self):
        policy, state, at, observation = self._wait_at_signal()
        first = policy.decide(state, at, car=observation, signal=signal(at), command_id="m")
        self.assertEqual(first.reason, "WAIT_SECOND_EXCLUSIVE_GREEN_FRAME")
        duplicate = policy.decide(first.state, at, car=observation, signal=signal(at), command_id="m")
        self.assertEqual(duplicate.kind, DecisionKind.WAIT)
        at2 = context("RIGHT_WAIT", 13., 2)
        ready = policy.decide(duplicate.state, at2, car=replace(observation, captured_at_s=13.),
                              signal=signal(at2, image="4"), command_id="recontact-1")
        self.assertEqual(ready.primitive_id, "recontact")
        self.assertEqual(ready.state.pending_target_context_id, "LAST_CONTACT")

    def _at_last_contact(self):
        policy, state, at, observation = self._wait_at_signal()
        first = policy.decide(state, at, car=observation, signal=signal(at), command_id="m")
        at2 = context("RIGHT_WAIT", 13., 2)
        second = policy.decide(first.state, at2, car=replace(observation, captured_at_s=13.),
                               signal=signal(at2, image="4"), command_id="recontact-1")
        # A long qualified recontact does not reuse the pre-motion green.
        return policy, completed(policy, second, 60.), context("LAST_CONTACT", 61., 3, tool_clear=False)

    def test_recontact_requires_new_signal_before_crossing(self):
        policy, state, at = self._at_last_contact()
        self.assertEqual(state.phase, Phase.ENTRY_SIGNAL)
        waiting = policy.decide(state, at, command_id="cross-1")
        self.assertEqual(waiting.reason, "ENTRY_READ_FRESH_SIGNAL")
        first = policy.decide(waiting.state, at, signal=signal(at, image="5"), command_id="cross-1")
        self.assertEqual(first.kind, DecisionKind.WAIT)
        at2 = context("LAST_CONTACT", 62., 3, tool_clear=False)
        second = policy.decide(first.state, at2, signal=signal(at2, image="6"), command_id="cross-1")
        self.assertEqual(second.primitive_id, "crossing-unit")

    def test_red_after_recontact_uses_reviewed_release_to_right_not_crossing(self):
        policy, state, at = self._at_last_contact()
        decision = policy.decide(state, at, signal=signal(at, color="RED"), command_id="release-1")
        self.assertEqual(decision.primitive_id, "release-to-right")
        back = completed(policy, decision, 63.)
        self.assertEqual(back.phase, Phase.WAIT_SIGNAL)
        self.assertEqual(back.step_index, 0)

    def test_signal_at_foreign_park_cannot_release_wait(self):
        policy, state, at, observation = self._wait_at_signal()
        decision = policy.decide(state, replace(at, context_id="LEFT_PARK"), car=observation, signal=signal(at))
        self.assertEqual(decision.state.phase, Phase.NEEDS_RECONCILIATION)

    def test_signal_car_movement_invalidates_fixed_recontact(self):
        policy, state, at, observation = self._wait_at_signal()
        decision = policy.decide(state, at, car=observation,
                                 signal=signal(at, car_unchanged_since_stop=False), command_id="m")
        self.assertEqual(decision.reason, "CAR_MOVED_DURING_SIGNAL_WAIT")

    def test_green_candidate_is_reset_by_red_frame(self):
        policy, state, at, observation = self._wait_at_signal()
        first = policy.decide(state, at, car=observation, signal=signal(at))
        red = policy.decide(first.state, at, car=observation, signal=signal(at, color="RED", image="4"))
        at2 = context("RIGHT_WAIT", 13., 2)
        green = policy.decide(red.state, at2, car=replace(observation, captured_at_s=13.), signal=signal(at2, image="5"))
        self.assertEqual(green.reason, "WAIT_SECOND_EXCLUSIVE_GREEN_FRAME")

    def test_source_timestamps_are_not_replaced_by_provider_return_time(self):
        policy, state, at, observation = self._wait_at_signal()
        late = context("RIGHT_WAIT", 40., 2)
        result = policy.decide(state, late, car=replace(observation, captured_at_s=40.), signal=signal(at))
        self.assertEqual(result.reason, "WAIT_FRESH_BOUND_SIGNAL")

    def test_second_green_cannot_count_expired_first_frame(self):
        policy, state, at, observation = self._wait_at_signal()
        first = policy.decide(state, at, car=observation, signal=signal(at))
        late = context("RIGHT_WAIT", 30., 2)
        second = policy.decide(first.state, late, car=replace(observation, captured_at_s=30.),
                               signal=signal(late, image="4"), command_id="m")
        self.assertEqual(second.reason, "WAIT_SECOND_EXCLUSIVE_GREEN_FRAME")
        self.assertEqual(len(second.state.green_image_sha256s), 1)

    def test_only_an_explicit_release_primitive_may_leave_last_contact(self):
        policy, state, at = self._at_last_contact()
        configuration = policy.plan
        gate = configuration.steps[0].signal_gate
        gate = replace(gate, release_to_wait=replace(gate.release_to_wait, qualified=False))
        policy = MissionPolicy(replace(configuration, steps=(replace(configuration.steps[0], signal_gate=gate), configuration.steps[1])))
        result = policy.decide(state, at, signal=signal(at, color="RED"), command_id="release")
        self.assertEqual(result.state.phase, Phase.FAILED)
        self.assertIn("NOT_QUALIFIED", result.reason)

    def test_parallel_error_is_continuous_at_180_boundary(self):
        self.assertAlmostEqual(angle_error(-179., 179.), 2.)
        self.assertAlmostEqual(angle_error(178., 0., parallel_axis=True), -2.)


if __name__ == "__main__":
    unittest.main()
