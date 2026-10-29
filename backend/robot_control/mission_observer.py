"""MUSE/measurement binding at stationary contexts; never a tip visual servo."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import math
import re
import time

from .mission_policy import CarObservation, Phase, SignalObservation, StartObservation
from .mission_vision import MetaMissionVision, PROMPT_VERSION, exclusive_signal
from .taught_executor import ExecutionBlocked


def _image(frame):
    return {"data": frame.original_jpeg, "metadata": frame.metadata()}


class MissionObserver:
    def __init__(self, api_key="", *, provider=None, measurement=None, sleep=time.sleep):
        self.provider = provider or MetaMissionVision(api_key)
        self.configured = bool(api_key) or provider is not None
        self.measurement = measurement
        self.sleep = sleep
        self.stop_frames = {}
        self.last_car_frames = {}
        self._measurement_config_sha256 = None
        if isinstance(getattr(measurement, "config", None), dict):
            from .mission_measurement import canonical_sha256
            self._measurement_config_sha256 = canonical_sha256(measurement.config)

    def readiness(self, config):
        blockers = []
        if not self.configured:
            blockers.append("MUSE_NOT_CONFIGURED")
        adapter = config.get("measurement_adapter") if isinstance(config, dict) else None
        try:
            from .mission_measurement import QualifiedCarMeasurement, canonical_sha256
            configured_sha = canonical_sha256(adapter)
            if self.measurement is None or configured_sha != self._measurement_config_sha256:
                # Reusing an old accepted object after configuration changes
                # would silently bypass its exact ROI/calibration bindings.
                self.measurement = None
                self.measurement = QualifiedCarMeasurement(adapter)
                self._measurement_config_sha256 = configured_sha
        except (ImportError, ValueError, KeyError, TypeError, OSError):
            blockers.append("INDEPENDENT_CAR_MEASUREMENT_QUALIFICATION_REQUIRED")
        if self.measurement is not None:
            readiness = self.measurement.readiness()
            if readiness.get("available") is not True:
                blockers.extend(readiness.get("blockers") or ["INDEPENDENT_CAR_MEASUREMENT_QUALIFICATION_REQUIRED"])
        observations = (config.get("observations") or {}) if isinstance(config, dict) else {}
        if not isinstance(observations, dict):
            observations = {}
        if not isinstance(observations.get("fixed_start"), dict) or not observations["fixed_start"] or not observations.get("zones"):
            blockers.append("FIXED_START_AND_CAR_ZONE_REFERENCES_REQUIRED")
        declared = observations.get("required_destinations")
        required = []
        if declared is not None:
            if (not isinstance(declared, list) or not declared
                    or any(not isinstance(value, str) or not value for value in declared)
                    or len(set(declared)) != len(declared)):
                blockers.append("REQUIRED_DESTINATION_COVERAGE_INVALID")
            else:
                required = declared
        destinations = self._preflight_routes(config, observations, adapter, blockers)
        missing = sorted(set(required) - set(destinations))
        if missing:
            blockers.append("REQUIRED_DESTINATIONS_MISSING:" + ",".join(missing))
        return {"ready": not blockers, "blockers": list(dict.fromkeys(blockers)),
                "validated_destinations": destinations, "required_destinations": list(required),
                "complete_destination_coverage": not missing if required else None,
                "destination_coverage": "declared_product_destinations" if required else "configured_routes_only"}

    @classmethod
    def _preflight_routes(cls, config, observations, adapter, blockers):
        """No route may discover its missing signal/measurement setup mid-run."""
        from .mission_driver import plan_from_dict
        from .mission_policy import SiteBinding
        routes = config.get("routes") if isinstance(config, dict) else None
        if not isinstance(routes, list) or not routes:
            blockers.append("OBSERVATION_ROUTES_REQUIRED")
            return []
        try:
            binding = SiteBinding(**config["site_binding"])
            frame_size = tuple(adapter["frame_size_px"])
            frame_id = adapter["coordinate_frame_id"]
            working_z = adapter["working_z_mm"]
            if (adapter["camera_epoch"] != binding.camera_epoch or adapter["map_sha256"] != binding.map_sha256
                    or adapter["car_id"] != binding.car_id):
                blockers.append("MEASUREMENT_SITE_BINDING_MISMATCH")
        except (KeyError, TypeError, ValueError):
            blockers.append("MEASUREMENT_SITE_BINDING_REQUIRED")
            return []
        zones, targets = observations.get("zones"), observations.get("signal_targets", {})
        contexts = config.get("contexts", {})
        if not isinstance(zones, dict) or not isinstance(targets, dict) or not isinstance(contexts, dict):
            blockers.append("OBSERVATION_ZONE_SIGNAL_CONTEXT_FORMAT")
            return []
        destinations = []
        for index, entry in enumerate(routes):
            before = len(blockers)
            try:
                plan = plan_from_dict(entry["plan"])
                if plan.binding != binding:
                    raise ValueError("Foreign route binding")
            except (KeyError, TypeError, ValueError, AttributeError):
                blockers.append(f"OBSERVATION_ROUTE_INVALID:{index}")
                continue
            for step in plan.steps:
                zone = zones.get(step.car_zone_id)
                lane = zone.get("target_lane") if isinstance(zone, dict) else None
                lane_valid = cls._valid_lane(lane, frame_id)
                if not lane_valid:
                    blockers.append("MEASUREMENT_LANE_NOT_BOUND:" + step.car_zone_id)
                else:
                    expected = plan.parking.heading_deg if step.at_goal else step.expected_heading_deg
                    if abs((lane["heading_deg"] - expected + 90.) % 180. - 90.) > .01:
                        blockers.append("MEASUREMENT_HEADING_FRAME_MISMATCH:" + step.id)
                if step.at_goal and not plan.parking.parallel_axis:
                    blockers.append("DIRECTED_PARKING_MEASUREMENT_UNAVAILABLE:" + step.id)
                observed_context = contexts.get(step.primitive.target_context_id)
                if not cls._valid_context(observed_context, working_z, clear=True):
                    blockers.append("MEASUREMENT_OBSERVATION_CONTEXT_NOT_BOUND:" + step.id)
                gate = step.signal_gate
                if gate:
                    if step.at_goal or step is plan.steps[-1]:
                        blockers.append("SIGNAL_GATE_REQUIRES_FOLLOWING_CROSSING:" + gate.id)
                    if not cls._valid_target_binding(targets.get(gate.id), gate, binding, frame_size):
                        blockers.append("SIGNAL_TARGET_NOT_BOUND:" + gate.id)
                    wait = contexts.get(gate.right_wait_context_id)
                    contact = contexts.get(gate.last_contact_context_id)
                    if (not cls._valid_context(wait, working_z, clear=True)
                            or not cls._valid_context(contact, working_z)
                            or tuple(wait["pose_base"]) == tuple(contact["pose_base"])):
                        blockers.append("SIGNAL_WAIT_CONTACT_CONTEXTS_NOT_BOUND:" + gate.id)
            if len(blockers) == before:
                destinations.append(plan.destination)
        return sorted(set(destinations))

    @staticmethod
    def _finite(value):
        return type(value) in (int, float) and math.isfinite(value)

    @classmethod
    def _valid_context(cls, context, working_z, clear=False):
        if not isinstance(context, dict):
            return False
        pose = context.get("pose_base")
        return (isinstance(pose, (list, tuple)) and len(pose) == 6
                and all(cls._finite(value) for value in pose) and cls._finite(working_z)
                and abs(pose[2] - working_z) <= .1
                and (not clear or context.get("tool_clear") is True))

    @classmethod
    def _valid_lane(cls, lane, frame_id):
        return (isinstance(lane, dict) and lane.get("coordinate_frame_id") == frame_id
                and lane.get("parallel_axis") is True and cls._finite(lane.get("heading_deg"))
                and -180 <= lane["heading_deg"] <= 180
                and isinstance(lane.get("point_mm"), (list, tuple)) and len(lane["point_mm"]) == 2
                and all(cls._finite(value) for value in lane["point_mm"]))

    @staticmethod
    def _same_stop(a, b):
        return ((a.binding, a.session_id, a.native_sequence, a.context_id) ==
                (b.binding, b.session_id, b.native_sequence, b.context_id)
                and a.stationary and b.stationary and not a.control_fault and not b.control_fault
                and a.pending_command_id is None and b.pending_command_id is None)

    def __call__(self, state, driver):
        before_context = driver.context()
        if not before_context.stationary or before_context.control_fault:
            raise ExecutionBlocked("OBSERVATION_REQUIRES_STOP", "Observe only a verified stationary context.")
        plan = driver.plan
        at_signal = state.phase in {Phase.WAIT_SIGNAL, Phase.ENTRY_SIGNAL}
        index = state.signal_step_index if state.phase == Phase.ENTRY_SIGNAL else state.step_index
        step = plan.steps[index]
        configuration = driver.observation_config
        target = None
        if at_signal:
            target = (configuration.get("signal_targets") or {}).get(step.signal_gate.id)
            if not self._valid_target(target, step.signal_gate, driver):
                raise ExecutionBlocked("SIGNAL_TARGET_NOT_BOUND", "Configure the actual two-face paper signal in this fixed camera view.")
        task = {"prompt_version": PROMPT_VERSION, "mission_id": plan.id, "phase": state.phase,
            "site_binding": asdict(plan.binding), "stationary_context": asdict(before_context),
            "car_zone_id": step.car_zone_id, "car_zone": configuration["zones"].get(step.car_zone_id),
            "expected_heading_deg": step.expected_heading_deg, "goal_arrival_check": step.at_goal,
            "fixed_start": configuration["fixed_start"], "signal_target": target,
            "action_command_id": state.action_command_id, "physical_stop_verified_separately": True}
        current = driver.capture()
        stop_key = (plan.id, step.id)
        if at_signal:
            reference = self.stop_frames.get(stop_key)
            if reference is None:
                reference = self.last_car_frames.get(stop_key)
                if reference is None:
                    raise ExecutionBlocked("STOPPED_CAR_REFERENCE_REQUIRED", "Signal waiting needs the actual post-withdrawal stopped car reference.")
                self.stop_frames[stop_key] = reference
            self.sleep(.35)
            second = driver.capture()
            frames = (current, second)
            if (current.epoch != second.epoch or current.sequence >= second.sequence
                    or current.captured_at >= second.captured_at or current.sha256 == second.sha256):
                raise ExecutionBlocked("NEW_SIGNAL_FRAMES_REQUIRED", "Wait for two distinct original camera frames.")
            results = asyncio.run(self.provider.observe_signal_pair(frames=tuple(_image(f) for f in frames),
                                                                   context=task, before=_image(reference)))
        else:
            reference = driver.before_frame
            frames = (current,)
            results = [asyncio.run(self.provider.observe(frame=_image(current), context=task,
                                     before=_image(reference) if reference is not None else None))]
        after_context = driver.context()
        if not self._same_stop(before_context, after_context):
            raise ExecutionBlocked("OBSERVATION_CONTEXT_CHANGED", "Robot context changed during inference; discard authority.")
        driver.ports._camera_status()  # Fixed registration must also remain valid after inference.
        samples = []
        for frame, result in zip(frames, results, strict=True):
            _, receipt_sha = driver.journal.artifact("mission-observation", {"task": task,
                "frame": frame.metadata(), "reference": reference.metadata() if reference else None,
                "result": result, "native_before": asdict(before_context), "native_after": asdict(after_context)})
            common = {"binding": plan.binding, "session_id": after_context.session_id,
                "native_sequence": after_context.native_sequence, "context_id": after_context.context_id,
                "captured_at_s": frame.captured_at, "image_sha256": frame.sha256,
                "provider_receipt_sha256": receipt_sha}
            numeric = {}
            if self.measurement is not None and result["car_visible"] and result["occlusion_cause"] == "NONE":
                zone = configuration["zones"].get(step.car_zone_id) or {}
                measured = self.measurement.estimate(frame, {**task, "map_sha256": plan.binding.map_sha256,
                    "car_id": plan.binding.car_id, "working_z_mm": driver.last_snapshot.tcp_base[2],
                    "occlusion_clear": True, "occlusion_frame_sha256": frame.sha256,
                    "target_lane": zone.get("target_lane")})
                driver.journal.artifact("car-measurement", {"frame": frame.metadata(), "measurement": measured})
                numeric = {key: value for key, value in measured.items() if key in {
                    "heading_deg", "heading_uncertainty_deg", "lateral_error_mm", "lateral_uncertainty_mm",
                    "measurement_evidence_sha256", "measurement_source"}}
            car = CarObservation(mission_id=plan.id, step_id=step.id,
                action_command_id=state.action_command_id or "fixed-start-observation", **common,
                verdict=result["verdict"], car_visible=result["car_visible"], within_road=result["within_road"],
                expected_progress=result["expected_progress"], heading_matches_expected=result["heading_matches_expected"],
                arrived=result["arrived"], car_zone_id=result["car_zone_id"], occlusion_cause=result["occlusion_cause"],
                signal_visible=exclusive_signal(result)[1], **numeric)
            sample = {"car": car, "signal": None, "start": None, "summary": result["summary"]}
            if not state.start_verified:
                sample["start"] = StartObservation(mission_id=plan.id, **common, car_visible=result["car_visible"],
                    at_fixed_start=result["at_fixed_start"], heading_matches_start=result["heading_matches_expected"],
                    within_road=result["within_road"] is True)
            if at_signal:
                color, visible = exclusive_signal(result)
                sample["signal"] = SignalObservation(gate_id=step.signal_gate.id, **common, color=color,
                    car_visible=result["car_visible"], signal_visible=visible,
                    car_unchanged_since_stop=result["car_unchanged_since_stop"], exclusive_green=color == "GREEN")
            elif result["car_visible"] and result["within_road"] is True:
                self.last_car_frames[stop_key] = frame
            samples.append(sample)
        return {**samples[-1], "samples": samples} if at_signal else samples[0]

    @staticmethod
    def _valid_target(target, gate, driver):
        config = getattr(driver, "config", None) or {}
        size = (config.get("measurement_adapter") or {}).get("frame_size_px", (1920, 1080))
        return MissionObserver._valid_target_binding(target, gate, driver.binding, size)

    @staticmethod
    def _valid_target_binding(target, gate, binding, frame_size):
        if not isinstance(target, dict):
            return False
        polygon = target.get("pixel_polygon")
        if not (isinstance(frame_size, (list, tuple)) and len(frame_size) == 2
                and all(type(value) is int and value > 0 for value in frame_size)):
            return False
        valid = (target.get("gate_id") == gate.id and target.get("camera_epoch") == binding.camera_epoch
                and target.get("registration_id") == binding.calibration_id
                and isinstance(target.get("description"), str) and 1 <= len(target["description"]) <= 1000
                and re.fullmatch(r"[a-f0-9]{64}", str(target.get("placement_evidence_sha256", ""))) is not None
                and isinstance(polygon, list) and 3 <= len(polygon) <= 8
                and all(isinstance(p, list) and len(p) == 2 and all(MissionObserver._finite(v) for v in p)
                        and 0 <= p[0] < frame_size[0] and 0 <= p[1] < frame_size[1] for p in polygon))
        if not valid:
            return False
        area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))) / 2
        return area >= 1.
