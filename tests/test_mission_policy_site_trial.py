"""Current-site trials preserve Native, outcome and release-mode boundaries."""
from dataclasses import replace
import unittest

from backend.robot_control.mission_policy import (
    CarObservation, CorrectionTemplate, DecisionKind, MissionPlan, MissionPolicy,
    MotionReceipt, ParkingTarget, Phase, RouteStep, RuntimeContext, SignalGate,
    SiteBinding, StartObservation, TaughtPrimitive,
)


BINDING = SiteBinding("test-installation", "a"*64, "test-registration",
                      "test-tool", "test-car", "test-camera")
REVIEW = "b"*64


def primitive(name, source, target, *, empty=False, trial=True):
    return TaughtPrimitive(name, source, target, "0"*64, qualified=not trial,
        empty_tool=empty, release_mode="site_trial" if trial else "qualified",
        current_site_review_sha256=REVIEW if trial else None)


def plan(*, empty_observation=False, trial=True):
    steps = (RouteStep("clear-traverse", primitive("traverse", "START", "APPROACH", empty=True,trial=trial),
        "START_ZONE", 0., observation_required=empty_observation),
        RouteStep("delivery", primitive("contact-unit", "APPROACH", "WITHDRAWN",trial=trial),
                  "GOAL_ZONE", 0., at_goal=True))
    return MissionPlan("site-mission", "HANOK", BINDING, steps,
        ParkingTarget(0.,mode="delivery_only"),
        (primitive("return", "WITHDRAWN", "START",empty=True,trial=trial),), "START",
        release_mode="site_trial" if trial else "qualified")


def context(where="START", *, now=10., seq=1, **changes):
    return replace(RuntimeContext(now,BINDING,"fresh-session",seq,now,where,True,True),**changes)


def start(at):
    return StartObservation("site-mission",BINDING,"fresh-session",at.native_sequence,
        at.context_id,at.now_s,"c"*64,"d"*64,True,True,True,True)


def receipt(decision, **changes):
    return replace(MotionReceipt(decision.command_id,decision.primitive_id,"fresh-session",
        decision.state.pending_target_context_id,11.,True,"COMPLETED"),**changes)


def initial_dispatch(policy):
    at=context()
    return policy.decide(policy.initial_state("fresh-session"),at,start=start(at),command_id="fresh-command-1")


def after_contact(policy):
    empty=initial_dispatch(policy)
    at_approach=policy.accept_receipt(empty.state,receipt(empty))
    contact=policy.decide(at_approach,context("APPROACH",now=12.,seq=2),command_id="fresh-command-2")
    return policy.accept_receipt(contact.state,receipt(contact,completed_at_s=13.))


def goal_car(state,at,**changes):
    return replace(CarObservation("site-mission","delivery",state.action_command_id,BINDING,
        "fresh-session",at.native_sequence,at.context_id,at.now_s,"e"*64,"f"*64,
        "PASS",True,True,True,True,True,"GOAL_ZONE"),**changes)


class SiteTrialMissionPolicyTests(unittest.TestCase):
    def test_reviewed_site_trial_dispatches_without_claiming_qualification(self):
        configuration=plan()
        self.assertFalse(configuration.steps[0].primitive.qualified)
        self.assertEqual(configuration.steps[0].primitive.current_site_review_sha256,REVIEW)
        result=initial_dispatch(MissionPolicy(configuration))
        self.assertEqual(result.kind,DecisionKind.DISPATCH)
        self.assertEqual(result.primitive_id,"traverse")

    def test_qualified_mode_cannot_execute_site_trial_primitives(self):
        result=initial_dispatch(MissionPolicy(replace(plan(),release_mode="qualified")))
        self.assertEqual(result.kind,DecisionKind.HOLD)
        self.assertEqual(result.state.phase,Phase.FAILED)
        self.assertIn("NOT_QUALIFIED",result.reason)

    def test_trial_mode_does_not_accept_a_different_qualified_release_mode(self):
        result=initial_dispatch(MissionPolicy(replace(plan(trial=False),release_mode="site_trial")))
        self.assertEqual(result.kind,DecisionKind.HOLD)
        self.assertIn("NOT_QUALIFIED",result.reason)

    def test_trial_cannot_set_qualified_true_or_omit_its_review_reference(self):
        p=primitive("trial","one","two")
        for changes in ({"qualified":True},{"current_site_review_sha256":None},
                        {"current_site_review_sha256":"not-a-review-hash"}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                replace(p,**changes)

    def test_site_trial_excludes_parallel_parking_and_numeric_correction_templates(self):
        configuration=plan()
        with self.assertRaises(ValueError):
            replace(configuration,parking=ParkingTarget(0.))
        template=CorrectionTemplate(primitive("correct","WITHDRAWN","WITHDRAWN"),
            "delivery","GOAL_ZONE",(10.,20.),(-1.,1.),-5.,0.)
        with self.assertRaises(ValueError):
            replace(configuration,corrections=(template,))

    def test_only_empty_intermediate_step_can_omit_observation(self):
        configuration=plan()
        self.assertFalse(configuration.steps[0].observation_required)
        with self.assertRaises(ValueError):
            replace(configuration.steps[1],observation_required=False)
        with self.assertRaises(ValueError):
            replace(configuration.steps[0],at_goal=True)
        with self.assertRaises(ValueError):
            replace(configuration.steps[0],observation_required=0)

    def test_signal_stop_cannot_skip_observation_even_when_tool_is_empty(self):
        gate=SignalGate("signal","WAIT","CONTACT",
            primitive("recontact","WAIT","CONTACT",empty=True),
            primitive("release","CONTACT","WAIT",empty=True))
        with self.assertRaises(ValueError):
            RouteStep("stop",primitive("stop-unit","START","WAIT",empty=True),
                "STOP_ZONE",0.,signal_gate=gate,observation_required=False)

    def test_verified_empty_receipt_advances_ready_without_a_muse_decision(self):
        policy=MissionPolicy(plan())
        move=initial_dispatch(policy)
        state=policy.accept_receipt(move.state,receipt(move))
        self.assertEqual(state.phase,Phase.READY)
        self.assertEqual(state.step_index,1)
        self.assertIsNone(state.action_command_id)
        self.assertIsNone(state.pending_command_id)
        # Fresh stationary Native context is still checked before the contact.
        result=policy.decide(state,context("APPROACH",now=12.,seq=2),command_id="fresh-command-2")
        self.assertEqual(result.kind,DecisionKind.DISPATCH)
        self.assertEqual(result.primitive_id,"contact-unit")

    def test_empty_receipt_does_not_skip_unresolved_completion_or_wrong_identity(self):
        policy=MissionPolicy(plan())
        move=initial_dispatch(policy)
        changes=({"native_verified":False},{"outcome":"UNKNOWN"},{"outcome":"FAILED"},
            {"outcome":"REJECTED_BEFORE_DISPATCH"},{"command_id":"other-command"},
            {"primitive_id":"other-primitive"},{"session_id":"old-session"},
            {"target_context_id":"other-target"},{"completed_at_s":9.})
        for change in changes:
            with self.subTest(change=change):
                state=policy.accept_receipt(move.state,receipt(move,**change))
                self.assertEqual(state.phase,Phase.NEEDS_RECONCILIATION)
                self.assertEqual(state.step_index,0)
                result=policy.decide(state,context("APPROACH",now=12.),command_id="retry")
                self.assertEqual(result.kind,DecisionKind.HOLD)

    def test_empty_fast_path_preserves_fresh_native_and_source_context_checks(self):
        policy=MissionPolicy(plan())
        move=initial_dispatch(policy)
        state=policy.accept_receipt(move.state,receipt(move))
        for changes in ({"native_observed_at_s":1.},{"stationary":False},
                        {"pending_command_id":"foreign"},{"control_fault":"fault"},
                        {"session_id":"new-session"},{"context_id":"wrong-source"}):
            with self.subTest(changes=changes):
                at=replace(context("APPROACH",now=12.,seq=2),**changes)
                result=policy.decide(state,at,command_id="fresh-command-2")
                self.assertEqual(result.kind,DecisionKind.HOLD)
                self.assertNotEqual(result.state.phase,Phase.IN_FLIGHT)

    def test_empty_move_still_requires_confirmed_tool_clearance(self):
        policy=MissionPolicy(plan())
        at=context(tool_clear=False)
        result=policy.decide(policy.initial_state("fresh-session"),at,start=start(at),command_id="cmd")
        self.assertEqual(result.kind,DecisionKind.HOLD)
        self.assertEqual(result.reason,"EMPTY_TOOL_CLEARANCE_UNCONFIRMED")

    def test_start_car_observation_is_required_even_for_initial_empty_step(self):
        policy=MissionPolicy(plan())
        result=policy.decide(policy.initial_state("fresh-session"),context(),command_id="cmd")
        self.assertEqual(result.kind,DecisionKind.OBSERVE)
        self.assertEqual(result.reason,"FIXED_START_CAR_PRECONDITION_REQUIRED")
        self.assertFalse(result.state.start_verified)

    def test_contact_completion_still_requires_fresh_muse_before_return(self):
        policy=MissionPolicy(plan())
        state=after_contact(policy)
        self.assertEqual(state.phase,Phase.OBSERVE)
        self.assertEqual(state.action_command_id,"fresh-command-2")
        result=policy.decide(state,context("WITHDRAWN",now=14.,seq=3),command_id="return-cmd")
        self.assertEqual(result.kind,DecisionKind.OBSERVE)
        self.assertEqual(result.reason,"FRESH_BOUND_CAR_OBSERVATION_REQUIRED")
        self.assertFalse(result.state.vehicle_delivered)

    def test_contact_requires_original_pass_and_arrival_even_in_trial_mode(self):
        policy=MissionPolicy(plan())
        state=after_contact(policy)
        at=context("WITHDRAWN",now=14.,seq=3)
        for changes in ({"verdict":"FAIL"},{"verdict":"UNCERTAIN"},{"arrived":False},
                        {"car_visible":False},{"within_road":False},{"action_command_id":"old"}):
            with self.subTest(changes=changes):
                result=policy.decide(state,at,car=goal_car(state,at,**changes),command_id="return-cmd")
                self.assertNotEqual(result.kind,DecisionKind.DISPATCH)
                self.assertFalse(result.state.vehicle_delivered)
        result=policy.decide(state,at,car=goal_car(state,at),command_id="return-cmd")
        self.assertEqual(result.kind,DecisionKind.DISPATCH)
        self.assertEqual(result.primitive_id,"return")
        self.assertTrue(result.state.vehicle_delivered)

    def test_default_observation_remains_required_for_empty_steps(self):
        configuration=plan(empty_observation=True)
        self.assertTrue(RouteStep("default",primitive("move","A","B",empty=True),"zone",0.).observation_required)
        policy=MissionPolicy(configuration)
        move=initial_dispatch(policy)
        state=policy.accept_receipt(move.state,receipt(move))
        self.assertEqual(state.phase,Phase.OBSERVE)
        self.assertEqual(state.step_index,0)
        result=policy.decide(state,context("APPROACH",now=12.,seq=2),command_id="next")
        self.assertEqual(result.kind,DecisionKind.OBSERVE)

    def test_strict_default_release_still_rejects_unqualified_primitives(self):
        configuration=plan(trial=False)
        first=replace(configuration.steps[0],primitive=replace(configuration.steps[0].primitive,qualified=False))
        configuration=replace(configuration,steps=(first,configuration.steps[1]))
        result=initial_dispatch(MissionPolicy(configuration))
        self.assertEqual(result.kind,DecisionKind.HOLD)
        self.assertIn("NOT_QUALIFIED",result.reason)
        self.assertEqual(MissionPlan.__dataclass_fields__["release_mode"].default,"qualified")
        self.assertEqual(ParkingTarget(0.).mode,"parallel_alignment")


if __name__ == "__main__":
    unittest.main()
