"""Offline observer bindings and paired-signal product integration.

All frames, provider output, robot receipts and qualifications are synthetic.
No network, camera, control socket, or physical device is accessed.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import hashlib
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest

from backend.physical_mission import PhysicalMissionService
from backend.robot_control.mission_observer import MissionObserver
from backend.robot_control.mission_policy import CorrectionTemplate, MissionPolicy, ParkingTarget, Phase
from backend.robot_control.taught_executor import ExecutionBlocked, Frame
from tests.test_mission_policy import BINDING, after_first, car, context, plan, primitive, signal
from tests.test_mission_vision import observation
from tests.test_mission_measurement import configuration as measurement_configuration, rehash
from backend.robot_control.mission_measurement import canonical_sha256
from tests.test_physical_mission import FakeMeasuredDriver, FakeWorkspace, command_for, event_seen
from tests.test_live_review_provider import frame_fixture


def sha(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


@dataclass(frozen=True)
class FakeFrame:
    sequence: int
    captured_at: float
    epoch: str = BINDING.camera_epoch

    @property
    def original_jpeg(self):
        return f"synthetic-original-{self.sequence}".encode()

    @property
    def sha256(self):
        return hashlib.sha256(self.original_jpeg).hexdigest()

    def metadata(self):
        return {"sequence": self.sequence, "captured_at": self.captured_at,
                "epoch": self.epoch, "sha256": self.sha256, "width": 1920, "height": 1080}


class FakeJournal:
    def __init__(self):
        self.entries = []

    def artifact(self, kind, value):
        self.entries.append((kind, deepcopy(value)))
        return f"synthetic-{len(self.entries)}", sha((kind, len(self.entries)))


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.changes = {}
        self.after_call = None

    def result(self, task):
        return observation(**{"car_zone_id": task["car_zone_id"], "arrived": task["goal_arrival_check"],
                              "red_face": "COVERED", "green_face": "VISIBLE", **self.changes})

    async def observe(self, *, frame, context, before=None):
        self.calls.append(("car", deepcopy({"frame": frame, "context": context, "before": before})))
        result = self.result(context)
        if self.after_call:
            self.after_call()
        return result

    async def observe_signal_pair(self, *, frames, context, before):
        self.calls.append(("signal", deepcopy({"frames": frames, "context": context, "before": before})))
        result = [self.result(context), self.result(context)]
        if self.after_call:
            self.after_call()
        return result


class FakeMeasurement:
    def __init__(self):
        self.calls = []

    def estimate(self, frame, task):
        self.calls.append((frame, deepcopy(task)))
        return {"heading_deg": 90., "heading_uncertainty_deg": 2., "lateral_error_mm": 1.,
            "lateral_uncertainty_mm": .5, "measurement_source": "qualified_estimator",
            "measurement_evidence_sha256": sha(frame.sha256),
            # Measurement output must never overwrite MUSE or identity fields.
            "arrived": True, "within_road": False, "context_id": "foreign-context",
            "tcp": [100, 100, -100], "extra_diagnostic": "synthetic diagnostics retained only in journal"}


class ObserverDriver:
    def __init__(self):
        self.plan = plan(signal=True)
        self.binding = BINDING
        self.before_frame = FakeFrame(1, 90.)
        self.journal = FakeJournal()
        self.last_snapshot = SimpleNamespace(tcp_base=[0., 0., 7.3649, 0., 0., 0.])
        self.frames = []
        self.contexts = []
        self.context_calls = 0
        self.capture_calls = 0
        self.registration_checks = 0
        self.registration_error = False
        self.ports = SimpleNamespace(_camera_status=self.camera_status)
        self.observation_config = {
            "fixed_start": {"zone": "START"},
            "zones": {"STOP": {"target_lane": {"id": "northbound"}}, "GOAL": {}},
            "signal_targets": {"SOUTH_SIGNAL": {"gate_id": "SOUTH_SIGNAL", "camera_epoch": BINDING.camera_epoch,
                "registration_id": BINDING.calibration_id, "description": "Synthetic two-face paper target",
                "placement_evidence_sha256": "a" * 64,
                "pixel_polygon": [[100, 100], [200, 100], [200, 200], [100, 200]]}},
        }

    def prepare_frames(self, *frames, where="RIGHT_WAIT", sequence=2):
        self.frames = list(frames)
        self.contexts = [context(where, frames[0].captured_at - .1, sequence),
                         context(where, frames[-1].captured_at + 2., sequence)]
        self.context_calls = 0

    def context(self):
        value = self.contexts[min(self.context_calls, len(self.contexts) - 1)]
        self.context_calls += 1
        return value

    def capture(self):
        self.capture_calls += 1
        return self.frames.pop(0)

    def camera_status(self):
        self.registration_checks += 1
        if self.registration_error:
            raise ExecutionBlocked("CAMERA_VIEW_CHANGED", "Synthetic registration changed during inference.")


class MissionObserverTests(unittest.TestCase):
    def setUp(self):
        self.provider, self.measurement, self.driver = FakeProvider(), FakeMeasurement(), ObserverDriver()
        self.sleeps = []
        self.observer = MissionObserver(provider=self.provider, measurement=self.measurement, sleep=self.sleeps.append)
        self.state = after_first(MissionPolicy(self.driver.plan))

    def stopped_car(self):
        frame = FakeFrame(10, 100.)
        self.driver.prepare_frames(frame)
        result = self.observer(self.state, self.driver)
        self.assertTrue(result["car"].car_visible)
        return frame

    def signal_pair(self, first=None, second=None):
        self.driver.prepare_frames(first or FakeFrame(20, 110.), second or FakeFrame(21, 110.4))
        return self.observer(replace(self.state, phase=Phase.WAIT_SIGNAL, signal_step_index=0), self.driver)

    def test_two_originals_make_one_provider_call_and_keep_their_capture_times(self):
        reference = self.stopped_car()
        result = self.signal_pair()
        self.assertEqual([kind for kind, _ in self.provider.calls], ["car", "signal"])
        self.assertEqual(self.sleeps, [.35])
        call = self.provider.calls[-1][1]
        self.assertEqual(call["before"]["data"], reference.original_jpeg)
        self.assertEqual([f["metadata"]["sequence"] for f in call["frames"]], [20, 21])
        self.assertEqual([s["signal"].captured_at_s for s in result["samples"]], [110., 110.4])
        self.assertEqual([s["car"].captured_at_s for s in result["samples"]], [110., 110.4])
        self.assertNotEqual(result["samples"][0]["signal"].image_sha256, result["samples"][1]["signal"].image_sha256)
        self.assertTrue(all(sample["signal"].exclusive_green for sample in result["samples"]))
        records = [value for kind, value in self.driver.journal.entries if kind == "mission-observation"]
        self.assertEqual(len(records), 3)
        self.assertTrue(all(record["reference"]["sha256"] == reference.sha256 for record in records[1:]))

    def test_signal_wait_requires_actual_prior_stopped_car_frame(self):
        with self.assertRaises(ExecutionBlocked) as raised:
            self.signal_pair()
        self.assertEqual(raised.exception.code, "STOPPED_CAR_REFERENCE_REQUIRED")
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.driver.journal.entries, [])

    def test_same_original_nonincreasing_time_sequence_or_changed_epoch_rejected_before_provider(self):
        self.stopped_car()
        first = FakeFrame(20, 110.)
        for second in (first, FakeFrame(19, 111.), FakeFrame(21, 110.), FakeFrame(21, 111., "changed")):
            with self.subTest(second=second), self.assertRaises(ExecutionBlocked) as raised:
                self.signal_pair(first, second)
            self.assertEqual(raised.exception.code, "NEW_SIGNAL_FRAMES_REQUIRED")
        self.assertEqual(len(self.provider.calls), 1)

    def test_both_faces_and_cable_mask_transition_return_unknown_without_fake_error(self):
        self.stopped_car()
        variants = ({"red_face": "VISIBLE", "green_face": "VISIBLE"},
                    {"red_face": "UNCERTAIN", "green_face": "VISIBLE"},
                    {"mask_in_transition": True, "occlusion_cause": "HAND"})
        for changes in variants:
            self.provider.changes = changes
            result = self.signal_pair()
            self.assertTrue(all(s["signal"].color == "UNKNOWN" and not s["signal"].exclusive_green for s in result["samples"]))

    def test_native_change_during_inference_discards_observation_authority(self):
        for change in ({"native_sequence": 99}, {"context_id": "OTHER"}, {"stationary": False},
                       {"session_id": "replacement"}, {"pending_command_id": "other-motion"},
                       {"control_fault": "fault"}, {"binding": replace(BINDING, camera_epoch="changed")}):
            with self.subTest(change=change):
                self.driver.prepare_frames(FakeFrame(30, 120.))
                self.provider.after_call = lambda change=change: self.driver.contexts.__setitem__(1,
                    replace(self.driver.contexts[1], **change))
                prior_entries = len(self.driver.journal.entries)
                with self.assertRaises(ExecutionBlocked) as raised:
                    self.observer(self.state, self.driver)
                self.assertEqual(raised.exception.code, "OBSERVATION_CONTEXT_CHANGED")
                self.assertEqual(len(self.driver.journal.entries), prior_entries)

    def test_registration_change_after_inference_discards_result(self):
        self.driver.prepare_frames(FakeFrame(30, 120.))
        self.provider.after_call = lambda: setattr(self.driver, "registration_error", True)
        with self.assertRaises(ExecutionBlocked) as raised:
            self.observer(self.state, self.driver)
        self.assertEqual(raised.exception.code, "CAMERA_VIEW_CHANGED")
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.driver.journal.entries, [])

    def test_unbound_target_is_rejected_without_capture_or_inference(self):
        target = self.driver.observation_config["signal_targets"]["SOUTH_SIGNAL"]
        for change in ({"camera_epoch": "other"}, {"registration_id": "other"},
                       {"gate_id": "foreign"}, {"placement_evidence_sha256": "bad"},
                       {"pixel_polygon": [[0, 0], [1, 1]]}, {"pixel_polygon": [[0, 0], [1, 1], [float("nan"), 2]]}):
            with self.subTest(change=change):
                self.driver.observation_config["signal_targets"]["SOUTH_SIGNAL"] = {**target, **change}
                self.driver.prepare_frames(FakeFrame(30, 120.), FakeFrame(31, 120.4))
                with self.assertRaises(ExecutionBlocked) as raised:
                    self.observer(replace(self.state, phase=Phase.WAIT_SIGNAL), self.driver)
                self.assertEqual(raised.exception.code, "SIGNAL_TARGET_NOT_BOUND")
        self.assertEqual(self.driver.capture_calls, 0)
        self.assertEqual(self.provider.calls, [])

    def test_measurement_is_bound_filtered_and_journaled_without_overwriting_model_facts(self):
        frame = self.stopped_car()
        record = self.observer.last_car_frames[(self.driver.plan.id, "approach")]
        self.assertEqual(record, frame)
        measurement_frame, task = self.measurement.calls[0]
        self.assertEqual(measurement_frame, frame)
        self.assertEqual(task["working_z_mm"], 7.3649)
        self.assertEqual(task["occlusion_frame_sha256"], frame.sha256)
        self.assertEqual(task["target_lane"], {"id": "northbound"})
        self.driver.prepare_frames(FakeFrame(11, 101.))
        result = self.observer(self.state, self.driver)["car"]
        self.assertEqual(result.measurement_source, "qualified_estimator")
        self.assertTrue(result.within_road)
        self.assertFalse(result.arrived)
        self.assertEqual(result.context_id, "RIGHT_WAIT")
        measurements = [value for kind, value in self.driver.journal.entries if kind == "car-measurement"]
        self.assertEqual(len(measurements), 2)
        self.assertIn("extra_diagnostic", measurements[-1]["measurement"])

    def test_occlusion_does_not_call_numeric_estimator_or_create_a_stopped_reference(self):
        self.provider.changes = {"car_visible": False, "occlusion_cause": "HOSE", "within_road": None}
        self.driver.prepare_frames(FakeFrame(30, 120.))
        result = self.observer(self.state, self.driver)
        self.assertFalse(result["car"].measured_heading)
        self.assertEqual(self.measurement.calls, [])
        self.assertEqual(self.observer.last_car_frames, {})

    def test_observation_requires_stationary_robot_before_any_provider_request(self):
        self.driver.prepare_frames(FakeFrame(30, 120.))
        self.driver.contexts[0] = replace(self.driver.contexts[0], stationary=False)
        with self.assertRaises(ExecutionBlocked) as raised:
            self.observer(self.state, self.driver)
        self.assertEqual(raised.exception.code, "OBSERVATION_REQUIRES_STOP")
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.driver.capture_calls, 0)


def readiness_configuration():
    """Complete fictional route/measurement/target deployment; no hardware."""
    adapter = measurement_configuration(accepted=True)
    adapter["car_id"] = BINDING.car_id
    adapter["qualification"]["record"]["configuration_sha256"] = canonical_sha256(
        {key: value for key, value in adapter.items() if key != "qualification"})
    rehash(adapter)
    frame_id = adapter["coordinate_frame_id"]
    target = deepcopy(ObserverDriver().observation_config["signal_targets"]["SOUTH_SIGNAL"])
    target["pixel_polygon"] = [[100, 100], [200, 100], [200, 180], [100, 180]]
    return {"measurement_adapter": adapter, "site_binding": asdict(BINDING),
        "routes": [{"plan": asdict(plan(signal=True))}],
        "contexts": {name: {"pose_base": [x, 0., 7.4, 0., 0., 0.], "tool_clear": name != "LAST_CONTACT"}
                     for name, x in (("START", 0.), ("RIGHT_WAIT", 10.), ("LAST_CONTACT", 11.), ("GOAL_PARK", 20.))},
        "observations": {"fixed_start": {"description": "Synthetic fixed start box."},
            "zones": {"STOP": {"target_lane": {"point_mm": [75., 50.], "heading_deg": 90.,
                                                  "parallel_axis": True, "coordinate_frame_id": frame_id}},
                      "GOAL": {"target_lane": {"point_mm": [75., 50.], "heading_deg": 0.,
                                                  "parallel_axis": True, "coordinate_frame_id": frame_id}}},
            "signal_targets": {"SOUTH_SIGNAL": target}}}


def outcome_configuration():
    config = readiness_configuration()
    source = config["measurement_adapter"]
    config["measurement_adapter"] = {key: source[key] for key in
        ("camera_epoch", "map_sha256", "car_id", "frame_size_px", "coordinate_frame_id", "working_z_mm")}
    config["measurement_adapter"]["kind"] = "muse_outcome"
    config["routes"][0]["plan"]["parking"]["mode"] = "delivery_only"
    config["observations"]["zones"] = {
        "STOP": {"description": "Synthetic northbound car stopped before the crossing."},
        "GOAL": {"description": "Synthetic car in the road directly in front of the named destination."}}
    return config


class OutcomeOnlyObserverTests(unittest.TestCase):
    def observer(self):
        return MissionObserver(provider=FakeProvider(), sleep=lambda _: None)

    def runtime(self):
        driver = ObserverDriver()
        driver.plan = plan(parking=ParkingTarget(0., mode="delivery_only"))
        driver.config = outcome_configuration()
        driver.config["measurement_adapter"]["frame_size_px"] = [96, 64]
        driver.config["measurement_adapter"]["working_z_mm"] = 7.3649
        driver.observation_config = driver.config["observations"]
        state = after_first(MissionPolicy(driver.plan))
        driver.last_contact_outcome = {"command_id": state.action_command_id, "primitive_id": "delivery-unit",
            "expected_visual": "Synthetic contact unit completes delivery to the named goal."}
        data = frame_fixture(20)["data"]
        frame = Frame("synthetic-native", BINDING.camera_epoch, 10, 100., hashlib.sha256(data).hexdigest(), data)
        driver.before_frame = replace(frame, id="synthetic-reference", sequence=1, captured_at=90.)
        driver.prepare_frames(frame, where="GOAL_PARK")
        return driver, state, frame

    def test_explicit_delivery_mode_needs_no_numeric_qualification_or_fake_metric_lane(self):
        observer, config = self.observer(), outcome_configuration()
        result = observer.readiness(config)
        self.assertTrue(result["ready"], result["blockers"])
        self.assertEqual(result["observation_mode"], "muse_outcome")
        self.assertFalse(result["numeric_pose_authority"])
        self.assertIsNone(observer.measurement)
        self.assertEqual(result["validated_destinations"], ["HANOK"])
        self.assertEqual(observer.provider.calls, [])

    def test_muse_mode_discards_cached_numeric_adapter(self):
        observer = self.observer()
        self.assertTrue(observer.readiness(readiness_configuration())["ready"])
        self.assertIsNotNone(observer.measurement)
        self.assertTrue(observer.readiness(outcome_configuration())["ready"])
        self.assertIsNone(observer.measurement)
        self.assertIsNone(observer._measurement_config_sha256)

    def test_all_routes_must_use_delivery_only_and_cannot_declare_numeric_corrections(self):
        for alteration in ("parking", "correction"):
            config = outcome_configuration()
            second = deepcopy(config["routes"][0])
            second["plan"]["destination"] = "VILLA"
            if alteration == "parking":
                second["plan"]["parking"]["mode"] = "parallel_alignment"
            else:
                correction = CorrectionTemplate(primitive("correction", "GOAL_PARK", "GOAL_PARK"),
                    "delivery", "GOAL", (10., 20.), (-3., 3.), -10., 0.)
                second["plan"]["corrections"] = [asdict(correction)]
            config["routes"].append(second)
            result = self.observer().readiness(config)
            self.assertFalse(result["ready"])
            self.assertIn("MUSE_OUTCOME_REQUIRES_DELIVERY_ONLY_WITHOUT_NUMERIC_CORRECTIONS:VILLA", result["blockers"])

    def test_muse_adapter_requires_complete_actual_site_dimensions_and_height(self):
        changes = ({"camera_epoch": "foreign"}, {"map_sha256": "b" * 64}, {"car_id": "foreign"},
                   {"frame_size_px": [0, 200]}, {"frame_size_px": [True, 200]},
                   {"coordinate_frame_id": ""}, {"working_z_mm": float("nan")}, {"working_z_mm": 8.4},
                   {"qualification": {"accepted": True}})
        for change in changes:
            with self.subTest(change=change):
                config = outcome_configuration()
                config["measurement_adapter"].update(change)
                self.assertFalse(self.observer().readiness(config)["ready"])
        for field in tuple(outcome_configuration()["measurement_adapter"]):
            with self.subTest(missing=field):
                config = outcome_configuration()
                del config["measurement_adapter"][field]
                self.assertFalse(self.observer().readiness(config)["ready"])

    def test_qualitative_references_and_signal_binding_remain_required_before_start(self):
        for part in ("zone", "start", "signal", "context"):
            config = outcome_configuration()
            if part == "zone":
                config["observations"]["zones"]["GOAL"] = {"target_lane": {"heading_deg": 0.}}
            elif part == "start":
                config["observations"]["fixed_start"] = {"id": "START"}
            elif part == "signal":
                config["observations"]["signal_targets"] = {}
            else:
                config["contexts"]["GOAL_PARK"]["tool_clear"] = False
            with self.subTest(part=part):
                self.assertFalse(self.observer().readiness(config)["ready"])

    def test_runtime_preserves_provider_facts_and_does_not_call_cached_metric_estimator(self):
        driver, state, frame = self.runtime()
        provider, measurement = FakeProvider(), FakeMeasurement()
        provider.changes = {"heading_matches_expected": False, "expected_progress": False}
        observer = MissionObserver(provider=provider, measurement=measurement, sleep=lambda _: None)
        result = observer(state, driver)
        task = provider.calls[0][1]["context"]
        self.assertEqual(task["parking_mode"], "delivery_only")
        self.assertEqual(task["expected_visual"], driver.last_contact_outcome["expected_visual"])
        self.assertEqual(task["completed_primitive_id"], "delivery-unit")
        self.assertFalse(task["numeric_pose_authority"])
        self.assertEqual(measurement.calls, [])
        self.assertEqual(result["car"].measurement_source, "unmeasured")
        self.assertIsNone(result["car"].heading_deg)
        self.assertFalse(result["car"].heading_matches_expected)
        self.assertTrue(result["car"].arrived)
        self.assertEqual(result["car"].image_sha256, frame.sha256)

    def test_missing_or_foreign_completed_contact_context_is_not_fabricated(self):
        for outcome in (None, {"command_id": "foreign", "primitive_id": "delivery-unit", "expected_visual": "arrive"},
                        {"command_id": "motion-1", "primitive_id": "delivery-unit", "expected_visual": ""}):
            driver, state, _ = self.runtime()
            driver.last_contact_outcome = outcome
            observer = self.observer()
            with self.subTest(outcome=outcome), self.assertRaises(ExecutionBlocked) as raised:
                observer(state, driver)
            self.assertEqual(raised.exception.code, "CONTACT_OUTCOME_CONTEXT_REQUIRED")
            self.assertEqual(observer.provider.calls, [])
            self.assertEqual(driver.capture_calls, 0)

    def test_runtime_source_epoch_resolution_hash_and_height_are_checked(self):
        for mutation in ("epoch", "size", "hash", "height", "plan_mode", "zone"):
            driver, state, frame = self.runtime()
            if mutation == "epoch":
                driver.frames[0] = replace(frame, epoch="foreign")
            elif mutation == "size":
                driver.config["measurement_adapter"]["frame_size_px"] = [1920, 1080]
            elif mutation == "hash":
                driver.frames[0] = replace(frame, sha256="0" * 64)
            elif mutation == "height":
                driver.last_snapshot.tcp_base[2] = 8.5
            elif mutation == "plan_mode":
                driver.plan = replace(driver.plan, parking=ParkingTarget(0.))
            else:
                driver.observation_config["zones"]["GOAL"] = {}
            observer = self.observer()
            with self.subTest(mutation=mutation), self.assertRaises(ExecutionBlocked):
                observer(state, driver)
            self.assertEqual(observer.provider.calls, [])

    def test_config_change_during_inference_discards_result(self):
        driver, state, _ = self.runtime()
        observer = self.observer()
        observer.provider.after_call = lambda: driver.config["measurement_adapter"].update(camera_epoch="changed")
        with self.assertRaises(ExecutionBlocked) as raised:
            observer(state, driver)
        self.assertEqual(raised.exception.code, "MUSE_OUTCOME_BINDING_CHANGED")
        self.assertEqual(driver.journal.entries, [])

    def test_earlier_fail_is_not_relabelled_as_delivery_pass(self):
        driver, state, _ = self.runtime()
        observer = self.observer()
        observer.provider.changes = {"verdict": "FAIL", "arrived": True}
        observed = observer(state, driver)
        self.assertEqual(observed["car"].verdict, "FAIL")
        result = MissionPolicy(driver.plan).decide(state, driver.contexts[-1], car=observed["car"], command_id="return")
        self.assertFalse(result.state.vehicle_delivered)
        self.assertEqual(result.reason, "DELIVERY_REQUIRES_ORIGINAL_PASS")


class ObserverReadinessTests(unittest.TestCase):
    def observer(self):
        return MissionObserver(provider=FakeProvider(), sleep=lambda _: None)

    def test_all_configured_route_zones_targets_and_qualification_are_preflighted(self):
        observer, config = self.observer(), readiness_configuration()
        result = observer.readiness(config)
        self.assertTrue(result["ready"], result["blockers"])
        self.assertEqual(result["validated_destinations"], ["HANOK"])
        self.assertIsNone(result["complete_destination_coverage"])
        self.assertEqual(result["destination_coverage"], "configured_routes_only")
        self.assertEqual(observer.provider.calls, [])

    def test_missing_signal_target_blocks_before_start_not_at_first_red(self):
        config = readiness_configuration()
        config["observations"]["signal_targets"] = {}
        result = self.observer().readiness(config)
        self.assertFalse(result["ready"])
        self.assertIn("SIGNAL_TARGET_NOT_BOUND:SOUTH_SIGNAL", result["blockers"])

    def test_missing_later_goal_lane_or_wrong_frame_is_not_hidden_by_valid_stop_zone(self):
        for change in ({}, {"target_lane": {"point_mm": [75., 50.], "heading_deg": 0.,
                                           "parallel_axis": True, "coordinate_frame_id": "ROBOT_BASE"}}):
            config = readiness_configuration()
            config["observations"]["zones"]["GOAL"] = change
            result = self.observer().readiness(config)
            self.assertFalse(result["ready"])
            self.assertIn("MEASUREMENT_LANE_NOT_BOUND:GOAL", result["blockers"])

    def test_parking_heading_must_share_the_validated_lane_frame(self):
        config = readiness_configuration()
        config["observations"]["zones"]["GOAL"]["target_lane"]["heading_deg"] = 90.
        result = self.observer().readiness(config)
        self.assertIn("MEASUREMENT_HEADING_FRAME_MISMATCH:delivery", result["blockers"])

    def test_every_loaded_route_is_checked_even_after_a_valid_first_route(self):
        config = readiness_configuration()
        second = deepcopy(config["routes"][0])
        second["plan"]["id"] = "synthetic-second-plan"
        second["plan"]["destination"] = "VILLA"
        second["plan"]["steps"][0]["signal_gate"]["id"] = "NORTH_SIGNAL"
        config["routes"].append(second)
        result = self.observer().readiness(config)
        self.assertFalse(result["ready"])
        self.assertIn("SIGNAL_TARGET_NOT_BOUND:NORTH_SIGNAL", result["blockers"])
        self.assertEqual(result["validated_destinations"], ["HANOK"])

    def test_declared_product_destinations_must_all_have_valid_routes(self):
        config = readiness_configuration()
        config["observations"]["required_destinations"] = ["HANOK", "VILLA", "OFFICE"]
        result = self.observer().readiness(config)
        self.assertFalse(result["ready"])
        self.assertFalse(result["complete_destination_coverage"])
        self.assertIn("REQUIRED_DESTINATIONS_MISSING:OFFICE,VILLA", result["blockers"])
        config["observations"]["required_destinations"] = ["HANOK"]
        result = self.observer().readiness(config)
        self.assertTrue(result["ready"])
        self.assertTrue(result["complete_destination_coverage"])

    def test_actual_configured_frame_bounds_and_nonzero_target_polygon_are_required(self):
        for polygon in ([[100, 100], [400, 100], [200, 180]],
                        [[100, 100], [150, 100], [200, 100]],
                        [[100, 100], [150, 120], [float("nan"), 160]]):
            config = readiness_configuration()
            config["observations"]["signal_targets"]["SOUTH_SIGNAL"]["pixel_polygon"] = polygon
            result = self.observer().readiness(config)
            self.assertIn("SIGNAL_TARGET_NOT_BOUND:SOUTH_SIGNAL", result["blockers"])

    def test_right_wait_pose_and_last_contact_pose_must_be_distinct_and_bound(self):
        config = readiness_configuration()
        config["contexts"]["LAST_CONTACT"]["pose_base"] = config["contexts"]["RIGHT_WAIT"]["pose_base"]
        result = self.observer().readiness(config)
        self.assertIn("SIGNAL_WAIT_CONTACT_CONTEXTS_NOT_BOUND:SOUTH_SIGNAL", result["blockers"])

    def test_working_z_and_car_clearance_are_checked_for_each_observation_endpoint(self):
        for changes in ({"tool_clear": False}, {"pose_base": [20., 0., 99., 0., 0., 0.]}):
            config = readiness_configuration()
            config["contexts"]["GOAL_PARK"].update(changes)
            result = self.observer().readiness(config)
            self.assertIn("MEASUREMENT_OBSERVATION_CONTEXT_NOT_BOUND:delivery", result["blockers"])

    def test_malformed_or_unmeasured_wait_contact_contexts_block_without_crashing(self):
        for name, value in (("RIGHT_WAIT", "missing"), ("RIGHT_WAIT", {"tool_clear": True}),
                            ("LAST_CONTACT", {"pose_base": [11., float("nan"), 7.4, 0., 0., 0.]}),
                            ("LAST_CONTACT", {"pose_base": [11., 0., 9.4, 0., 0., 0.]})):
            config = readiness_configuration()
            config["contexts"][name] = value
            result = self.observer().readiness(config)
            self.assertFalse(result["ready"])
            self.assertIn("SIGNAL_WAIT_CONTACT_CONTEXTS_NOT_BOUND:SOUTH_SIGNAL", result["blockers"])

    def test_cached_measurement_cannot_survive_a_changed_camera_configuration(self):
        config, observer = readiness_configuration(), self.observer()
        self.assertTrue(observer.readiness(config)["ready"])
        config["measurement_adapter"]["camera_epoch"] = "changed-camera"
        result = observer.readiness(config)
        self.assertFalse(result["ready"])
        self.assertIsNone(observer.measurement)
        self.assertIn("INDEPENDENT_CAR_MEASUREMENT_QUALIFICATION_REQUIRED", result["blockers"])

    def test_directed_parking_cannot_use_unoriented_axis_adapter(self):
        config = readiness_configuration()
        config["routes"][0]["plan"]["parking"]["parallel_axis"] = False
        result = self.observer().readiness(config)
        self.assertIn("DIRECTED_PARKING_MEASUREMENT_UNAVAILABLE:delivery", result["blockers"])

    def test_invalid_required_destination_declaration_cannot_claim_complete_coverage(self):
        config = readiness_configuration()
        config["observations"]["required_destinations"] = [{"id": "HANOK"}]
        result = self.observer().readiness(config)
        self.assertFalse(result["ready"])
        self.assertIn("REQUIRED_DESTINATION_COVERAGE_INVALID", result["blockers"])



class PairDriver(FakeMeasuredDriver):
    """One synthetic inference returns two independently timestamped originals."""
    def __init__(self):
        super().__init__(plan(signal=True))
        self.pair_calls = []
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.entry_captures = []
        self.recontact_completed_at = None

    def observe(self, state):
        if state.phase not in {Phase.WAIT_SIGNAL, Phase.ENTRY_SIGNAL}:
            return super().observe(state)
        self.pair_calls.append(state.phase)
        if self.block and state.phase == Phase.WAIT_SIGNAL:
            self.entered.set()
            if not self.release.wait(3.):
                raise RuntimeError("Synthetic pair test was not released")
        self.observations += 1
        samples = []
        for index in range(2):
            self.now += .35
            at = context(self.where, self.now, self.seq)
            step = self.plan.steps[state.step_index]
            image = sha((state.phase, self.observations, index))
            samples.append({"car": replace(car(at, state, step=step.id, zone=step.car_zone_id,
                arrived=False, heading_deg=step.expected_heading_deg), image_sha256=image),
                "signal": replace(signal(at), image_sha256=image), "summary": "Synthetic paired green"})
            if state.phase == Phase.ENTRY_SIGNAL:
                self.entry_captures.append(self.now)
        return {**samples[-1], "samples": samples}

    def execute(self, primitive_id, command_id):
        receipt = super().execute(primitive_id, command_id)
        if primitive_id == "recontact":
            # This deliberately expires every signal captured at the wait park.
            self.now += 100.
            self.recontact_completed_at = self.now
            receipt = replace(receipt, completed_at_s=self.now)
        return receipt


class QueuedSignalProductTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.store, self.driver = FakeWorkspace(), PairDriver()
        self.service = PhysicalMissionService(self.store, self.directory.name, driver=self.driver,
            poll_interval_s=.001, clock=lambda: self.driver.now)

    async def asyncTearDown(self):
        self.driver.release.set()
        await self.service.close()
        self.directory.cleanup()

    async def test_two_signal_samples_use_one_inference_and_new_entry_pair_after_recontact(self):
        await self.service.start(command_for(self.service, self.store))
        await asyncio.wait_for(self.service.task, 3.)
        result = self.service.snapshot()
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual(self.driver.pair_calls, [Phase.WAIT_SIGNAL, Phase.ENTRY_SIGNAL])
        self.assertEqual([p for p, _ in self.driver.commands], ["approach-unit", "recontact", "crossing-unit", "return"])
        self.assertEqual(len({command for _, command in self.driver.commands}), 4)
        self.assertTrue(all(timestamp > self.driver.recontact_completed_at for timestamp in self.driver.entry_captures))
        self.assertFalse(result["vision"]["in_flight"])

    async def test_actual_request_status_clears_and_stop_discards_queued_green_authority(self):
        self.driver.block = True
        await self.service.start(command_for(self.service, self.store))
        await event_seen(self.driver.entered)
        active = self.service.snapshot()
        self.assertEqual(active["state"], "WAITING_SIGNAL")
        self.assertTrue(active["vision"]["in_flight"])
        self.assertEqual(active["vision"]["kind"], "signal")
        self.assertEqual(active["stage_label"], "Checking signal · MUSE")
        self.assertIsNotNone(active["vision"]["started_at"])
        await self.service.stop({"request_id": "synthetic-stop-observer", "expected_revision": 0})
        self.driver.release.set()
        await asyncio.wait_for(self.service.task, 3.)
        final = self.service.snapshot()
        self.assertEqual(final["state"], "HOLD")
        self.assertEqual(final["error"], "OPERATOR_STOP")
        self.assertFalse(final["vision"]["in_flight"])
        self.assertEqual([p for p, _ in self.driver.commands], ["approach-unit"])
        self.assertEqual(self.driver.pair_calls, [Phase.WAIT_SIGNAL])


if __name__ == "__main__":
    unittest.main()
