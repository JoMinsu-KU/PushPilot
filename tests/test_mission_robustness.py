"""Deterministic adversarial mission checks; synthetic data and no hardware I/O.

The sampling explores accepted sets, not estimates of physical reliability.
All coordinates, measurements, qualification hashes and drivers are fixtures.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import random
from tempfile import TemporaryDirectory
import unittest

from backend.physical_mission import PhysicalMissionService
from backend.robot_control.mission_policy import (
    CorrectionTemplate, DecisionKind, MissionPolicy, ParkingTarget, Phase,
    RouteStep, ViewClearance, angle_error,
)
from tests.test_mission_policy import (
    after_first, car, completed, context, plan, primitive, signal, start,
)
from tests.test_physical_mission import FakeMeasuredDriver, FakeWorkspace, command_for


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def wait_state(configuration=None):
    policy = MissionPolicy(configuration or plan(signal=True))
    state = after_first(policy)
    at = context("RIGHT_WAIT", 100., 2)
    observation = car(at, state, step="approach", zone="STOP", arrived=False, heading_deg=90.)
    decision = policy.decide(state, at, car=observation, signal=signal(at, color="RED"))
    assert decision.state.phase == Phase.WAIT_SIGNAL
    return policy, decision.state


def wait_read(policy, state, now, *, image, color="GREEN", sequence=2, **changes):
    at = context("RIGHT_WAIT", now, sequence)
    observation = car(at, state, step="approach", zone="STOP", arrived=False, heading_deg=90.,
                      image_sha256=digest(f"car-{now}"))
    reading = signal(at, color=color, image_sha256=digest(image), **changes)
    return policy.decide(state, at, car=observation, signal=reading, command_id=f"candidate-{now}")


class ParkingAndCorrectionProperties(unittest.TestCase):
    def test_sampled_heading_interval_must_fit_parking_tolerance(self):
        rng = random.Random(2026102901)
        for index in range(400):
            target = rng.uniform(-180., 180.)
            actual = target + rng.uniform(-240., 240.)
            uncertainty = rng.uniform(0., 12.)
            tolerance = rng.uniform(1., 20.)
            parallel = bool(index % 2)
            policy = MissionPolicy(plan(parking=ParkingTarget(target, tolerance, parallel)))
            state, at = after_first(policy), context("GOAL_PARK", 12., 2)
            decision = policy.decide(state, at, car=car(at, state, heading_deg=actual,
                heading_uncertainty_deg=uncertainty), command_id=f"return-{index}")
            # Independent interval sampling includes both endpoints and any wrap boundary.
            errors = [abs(angle_error(actual - uncertainty + uncertainty * j / 32., target,
                                      parallel_axis=parallel)) for j in range(65)]
            with self.subTest(index=index, heading=actual, uncertainty=uncertainty):
                self.assertEqual(decision.state.vehicle_delivered, max(errors) <= tolerance)
                if decision.state.vehicle_delivered:
                    self.assertEqual(decision.primitive_id, "return")
                else:
                    self.assertNotEqual(decision.kind, DecisionKind.DISPATCH)

    def test_more_measurement_uncertainty_cannot_create_a_parking_acceptance(self):
        rng = random.Random(2026102902)
        for index in range(120):
            configuration = plan(parking=ParkingTarget(rng.uniform(-180., 180.),
                tolerance_deg=rng.uniform(5., 20.), parallel_axis=bool(index % 2)))
            actual = configuration.parking.heading_deg + rng.uniform(-30., 30.)
            policy = MissionPolicy(configuration)
            state, at = after_first(policy), context("GOAL_PARK", 12., 2)
            acceptance = []
            for uncertainty in (0., 1., 3., 7., 15.):
                result = policy.decide(state, at, car=car(at, state, heading_deg=actual,
                    heading_uncertainty_deg=uncertainty), command_id=f"return-{index}")
                acceptance.append(result.state.vehicle_delivered)
            self.assertEqual(acceptance, sorted(acceptance, reverse=True))

    def test_correction_choice_is_order_independent_and_never_uses_better_unqualified_candidate(self):
        rng = random.Random(2026102903)
        for index in range(60):
            yaw, lateral = rng.uniform(23., 34.), rng.uniform(4., 8.)
            safe = CorrectionTemplate(primitive("measured-correction", "GOAL_PARK", "GOAL_PARK"),
                "delivery", "GOAL", (20., 40.), (2., 10.), -10., -2.)
            unqualified = replace(safe, primitive=primitive("apparently-perfect", "GOAL_PARK", "GOAL_PARK", qualified=False),
                                  expected_yaw_change_deg=-yaw, expected_lateral_change_mm=-lateral)
            wrong_source = replace(safe, primitive=primitive("foreign-source", "ELSEWHERE", "GOAL_PARK"))
            wrong_zone = replace(safe, primitive=primitive("foreign-zone", "GOAL_PARK", "GOAL_PARK"), car_zone_id="OTHER")
            harmful = replace(safe, primitive=primitive("wrong-direction", "GOAL_PARK", "GOAL_PARK"), expected_yaw_change_deg=10.)
            candidates = [safe, unqualified, wrong_source, wrong_zone, harmful]
            rng.shuffle(candidates)
            policy = MissionPolicy(plan(corrections=candidates))
            state, at = after_first(policy), context("GOAL_PARK", 12., 2)
            result = policy.decide(state, at, car=car(at, state, heading_deg=yaw,
                lateral_error_mm=lateral, heading_uncertainty_deg=2., lateral_uncertainty_mm=1.),
                command_id=f"correction-{index}")
            self.assertEqual(result.primitive_id, "measured-correction")
            self.assertFalse(result.state.vehicle_delivered)

    def test_uncertainty_crossing_any_correction_boundary_prevents_contact(self):
        template = CorrectionTemplate(primitive("correction", "GOAL_PARK", "GOAL_PARK"),
            "delivery", "GOAL", (20., 35.), (-5., 5.), -10., 0.)
        policy = MissionPolicy(plan(corrections=(template,)))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        cases = ((20., 2., 0., 1.), (35., 2., 0., 1.), (25., 1., -5., 1.), (25., 1., 5., 1.))
        for yaw, yaw_uncertainty, lateral, lateral_uncertainty in cases:
            decision = policy.decide(state, at, car=car(at, state, heading_deg=yaw,
                heading_uncertainty_deg=yaw_uncertainty, lateral_error_mm=lateral,
                lateral_uncertainty_mm=lateral_uncertainty), command_id="unused")
            self.assertNotEqual(decision.kind, DecisionKind.DISPATCH)


class SignalSequenceProperties(unittest.TestCase):
    def test_many_single_greens_interrupted_by_red_unknown_both_or_occlusion_never_recontact(self):
        rng = random.Random(2026102904)
        variants = ({"color": "RED"}, {"color": "UNKNOWN"}, {"exclusive_green": False},
                    {"signal_visible": False}, {"car_visible": False}, {"captured_at_s": 1.})
        for sequence in range(16):
            policy, state = wait_state()
            now = 100.
            for block in range(10):
                now += 1.
                reading = wait_read(policy, state, now, image=(sequence, block, "green"))
                self.assertEqual(reading.kind, DecisionKind.WAIT)
                # A second provider call over the same original never counts twice.
                repeated = wait_read(policy, reading.state, now, image=(sequence, block, "green"))
                self.assertEqual(repeated.kind, DecisionKind.WAIT)
                now += 1.
                interrupted = wait_read(policy, repeated.state, now, image=(sequence, block, "interrupt"),
                                        **rng.choice(variants))
                self.assertEqual(interrupted.kind, DecisionKind.WAIT)
                self.assertEqual(interrupted.state.phase, Phase.WAIT_SIGNAL)
                self.assertEqual(interrupted.state.issued_command_ids, ("motion-1",))
                state = interrupted.state
            first = wait_read(policy, state, now + 1., image=(sequence, "final-first"))
            self.assertEqual(first.kind, DecisionKind.WAIT)
            second = wait_read(policy, first.state, now + 2., image=(sequence, "final-second"))
            self.assertEqual(second.primitive_id, "recontact")
            self.assertNotEqual(second.primitive_id, "crossing-unit")

    def test_each_unsafe_entry_reading_can_only_release_to_selected_wait_not_cross(self):
        variants = ({"color": "RED"}, {"color": "UNKNOWN"}, {"exclusive_green": False},
                    {"signal_visible": False}, {"car_visible": False},
                    {"car_unchanged_since_stop": False}, {"captured_at_s": 1.})
        for changes in variants:
            policy, state = wait_state()
            first = wait_read(policy, state, 101., image="g1")
            recontact = wait_read(policy, first.state, 102., image="g2")
            state = completed(policy, recontact, 120.)
            at = context("LAST_CONTACT", 121., 3, tool_clear=False)
            decision = policy.decide(state, at, signal=signal(at, **changes), command_id="release-only")
            self.assertEqual(decision.primitive_id, "release-to-right")
            state = completed(policy, decision, 122.)
            fresh = wait_read(policy, state, 123., image="one-new-green", sequence=4)
            self.assertEqual(fresh.kind, DecisionKind.WAIT)
            self.assertEqual(fresh.state.phase, Phase.WAIT_SIGNAL)


class PrimitiveQualificationMatrix(unittest.TestCase):
    def test_all_motion_roles_refuse_unqualified_primitives(self):
        cases = 0
        # Route, destination return, corrective contact, visibility clearance.
        for role in ("route", "return", "correction", "clearance"):
            configuration = plan()
            observation_changes = {}
            if role == "route":
                configuration = replace(configuration, steps=(replace(configuration.steps[0],
                    primitive=replace(configuration.steps[0].primitive, qualified=False)),))
            elif role == "return":
                configuration = replace(configuration, empty_return=(replace(configuration.empty_return[0], qualified=False),))
            elif role == "correction":
                configuration = replace(configuration, corrections=(CorrectionTemplate(
                    primitive("unqualified-align", "GOAL_PARK", "GOAL_PARK", qualified=False),
                    "delivery", "GOAL", (18., 32.), (-3., 3.), -12., 0.),))
                observation_changes = {"heading_deg": 25.}
            else:
                configuration = replace(configuration, clearances=(ViewClearance(
                    primitive("unqualified-view", "GOAL_PARK", "LEFT_PARK", empty=True, qualified=False),
                    "delivery", "LEFT", True),))
                observation_changes = {"car_visible": False, "occlusion_cause": "HOSE"}
            policy = MissionPolicy(configuration)
            if role == "route":
                at = context()
                result = policy.decide(policy.initial_state("session"), at, start=start(at), command_id="not-issued")
            else:
                state, at = after_first(policy), context("GOAL_PARK", 12., 2)
                result = policy.decide(state, at, car=car(at, state, **observation_changes), command_id="not-issued")
            with self.subTest(role=role):
                self.assertNotEqual(result.kind, DecisionKind.DISPATCH)
                self.assertNotIn("not-issued", result.state.issued_command_ids)
            cases += 1
        for role in ("recontact", "release", "crossing"):
            policy, waiting = wait_state()
            first = wait_read(policy, waiting, 101., image="one")
            configuration = policy.plan
            gate = configuration.steps[0].signal_gate
            if role == "recontact":
                gate = replace(gate, recontact=replace(gate.recontact, qualified=False))
                configuration = replace(configuration, steps=(replace(configuration.steps[0], signal_gate=gate), configuration.steps[1]))
                result = wait_read(MissionPolicy(configuration), first.state, 102., image="two")
            else:
                recontact = wait_read(policy, first.state, 102., image="two")
                entered = completed(policy, recontact, 103.)
                at = context("LAST_CONTACT", 104., 3, tool_clear=False)
                if role == "release":
                    gate = replace(gate, release_to_wait=replace(gate.release_to_wait, qualified=False))
                    configuration = replace(configuration, steps=(replace(configuration.steps[0], signal_gate=gate), configuration.steps[1]))
                    result = MissionPolicy(configuration).decide(entered, at, signal=signal(at, color="RED"), command_id="not-issued")
                else:
                    configuration = replace(configuration, steps=(configuration.steps[0], replace(configuration.steps[1],
                        primitive=replace(configuration.steps[1].primitive, qualified=False))))
                    policy = MissionPolicy(configuration)
                    green = policy.decide(entered, at, signal=signal(at, image="4"), command_id="not-issued")
                    at = context("LAST_CONTACT", 105., 3, tool_clear=False)
                    result = policy.decide(green.state, at, signal=signal(at, image="5"), command_id="not-issued")
            with self.subTest(role=role):
                self.assertNotEqual(result.kind, DecisionKind.DISPATCH)
                self.assertNotIn("not-issued", result.state.issued_command_ids)
            cases += 1
        # A visible alternative viewpoint must not manufacture a qualified
        # empty return to the primary observation context.
        clearance = ViewClearance(primitive("left-clear", "GOAL_PARK", "LEFT_PARK", empty=True),
            "delivery", "LEFT", True,
            restore=primitive("unqualified-restore", "LEFT_PARK", "GOAL_PARK", empty=True, qualified=False))
        policy = MissionPolicy(plan(clearances=(clearance,)))
        state, at = after_first(policy), context("GOAL_PARK", 12., 2)
        clearing = policy.decide(state, at, car=car(at, state, car_visible=False, occlusion_cause="HOSE"), command_id="clear")
        state = completed(policy, clearing, 13.)
        at = context("LEFT_PARK", 14., 3)
        result = policy.decide(state, at, car=car(at, state, image="4"), command_id="not-issued")
        self.assertNotEqual(result.kind, DecisionKind.DISPATCH)
        self.assertNotIn("not-issued", result.state.issued_command_ids)
        cases += 1
        self.assertEqual(cases, 8)


def five_stage_plan():
    configuration = plan()
    steps = (
        RouteStep("first", primitive("first-unit", "START", "MID_ONE"), "FIRST", 0.),
        RouteStep("second", primitive("second-unit", "MID_ONE", "MID_TWO"), "SECOND", 0.),
        RouteStep("delivery", primitive("delivery-unit", "MID_TWO", "GOAL_PARK"), "GOAL", 0., True),
    )
    returns = (primitive("return-one", "GOAL_PARK", "RETURN_MID", empty=True),
               primitive("return-two", "RETURN_MID", "START", empty=True))
    return replace(configuration, steps=steps, empty_return=returns)


class MultiStageFaultProperties(unittest.IsolatedAsyncioTestCase):
    async def test_failure_at_each_loaded_or_return_stage_never_replays_a_command(self):
        expected = ["first-unit", "second-unit", "delivery-unit", "return-one", "return-two"]
        for fault_at in range(1, 6):
            for failure_kind in ("lost-receipt", "unverified-receipt"):
                with self.subTest(fault_at=fault_at, failure_kind=failure_kind), TemporaryDirectory() as directory:
                    store, driver = FakeWorkspace(), FakeMeasuredDriver(five_stage_plan())
                    original_execute = driver.execute
                    def execute(primitive_id, command_id):
                        receipt = original_execute(primitive_id, command_id)
                        if len(driver.commands) == fault_at:
                            if failure_kind == "lost-receipt":
                                raise ConnectionError("Synthetic receipt lost after actual driver completion")
                            return replace(receipt, native_verified=False)
                        return receipt
                    driver.execute = execute
                    service = PhysicalMissionService(store, directory, driver=driver, poll_interval_s=.001,
                                                     clock=lambda: driver.now)
                    try:
                        request = command_for(service, store)
                        accepted = await service.start(request)
                        await asyncio.wait_for(service.task, 3.)
                        self.assertEqual(service.snapshot()["state"], "HOLD")
                        self.assertEqual([p for p, _ in driver.commands], expected[:fault_at])
                        self.assertEqual(len({identifier for _, identifier in driver.commands}), fault_at)
                        for _ in range(3):
                            self.assertEqual(await service.start(request), accepted)
                            await service.refresh_readiness()
                        self.assertEqual(len(driver.commands), fault_at)
                        self.assertTrue(driver.holds)
                    finally:
                        await service.close()
                    # Persistence is a reconciliation boundary, never a replay queue.
                    reopened_driver = FakeMeasuredDriver(five_stage_plan())
                    reopened = PhysicalMissionService(store, directory, driver=reopened_driver, poll_interval_s=.001)
                    try:
                        state = await reopened.refresh_readiness()
                        self.assertEqual(state["state"], "HOLD")
                        self.assertIsNone(reopened.task)
                        self.assertEqual(reopened_driver.commands, [])
                    finally:
                        await reopened.close()


if __name__ == "__main__":
    unittest.main()
