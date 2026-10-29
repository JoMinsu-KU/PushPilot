"""Equipment-free phase, unknown-outcome and no-replay regression tests."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.robot_control.coordinate_units import CoordinateBinding, CoordinateStage, CoordinateUnit, CoordinateUnitExecutor, CoordinateUnitReview
from backend.robot_control.taught_executor import ExecutionBlocked
from tests.test_taught_executor import SyntheticPorts, configuration, pose, right_signal_target
from tools.run_coordinate_unit import load_unit, main, unit_geometry


def unit():
    return CoordinateUnit("synthetic-unit", "plan", 1, "PIZZA", "OFFICE_BUILDING",
        "synthetic-installation", "synthetic-profile", (
            CoordinateStage("approach", "approach", pose(0), pose(10), "a"*64),
            CoordinateStage("push", "contact", pose(10), pose(20), "b"*64),
            CoordinateStage("disengage", "withdraw", pose(20), pose(15), "c"*64),
            CoordinateStage("observe", "withdraw", pose(15), pose(15, 10), "d"*64),
        ), "Car moves toward the visibly identified Office frontage.", at_goal=True)


class Ports(SyntheticPorts):
    def validate_signal_observation_target(self, target):
        if (target.camera_epoch, target.registration_id) != ("synthetic-camera-epoch", "synthetic-view"):
            raise ExecutionBlocked("SIGNAL_OBSERVATION_VIEW", "Synthetic mismatched signal view.")

    def __init__(self):
        super().__init__()
        self.unit_reviews, self.capture_at = [], []
        self.fail_motion_at, self.fail_capture_at = None, None
        self.fail_native_at, self.change_during_capture = None, False
        self.car_footprint, self.heading_matches_expected = "WITHIN_ROAD", True

    def capture(self):
        self.capture_at.append(len(self.motions))
        if len(self.capture_at) == self.fail_capture_at:
            raise TimeoutError("Synthetic camera failure.")
        frame = super().capture()
        if self.change_during_capture:
            self.sequence += 1
        return frame

    def execute_once(self, intent):
        if len(self.motions)+1 == self.fail_motion_at:
            self.motion_exception = True
        return super().execute_once(intent)

    def snapshot(self):
        if len(self.motions) == self.fail_native_at:
            raise TimeoutError("Synthetic post-command Native unavailable.")
        return super().snapshot()

    def review_coordinate_unit(self, unit, completed, before, after):
        self.unit_reviews.append((unit, completed, before, after))
        if self.muse_raises:
            raise TimeoutError("Synthetic MUSE timeout.")
        if self.change_during_muse:
            self.sequence += 1
        return CoordinateUnitReview(unit.id, "synthetic-provider", before.sha256, after.sha256,
            self.review_verdict, self.visible, self.expected_progress, self.excessive_yaw,
            True, "Synthetic whole-unit outcome only.", car_footprint=self.car_footprint,
            heading_matches_expected=self.heading_matches_expected,
            signal_region_visible=self.signal_visible, signal_occlusion_cause=self.signal_occlusion_cause)


class CoordinateUnitTests(unittest.TestCase):
    def setUp(self):
        self.adapter = configuration()[1]
        self.ports = Ports()
        self.executor = CoordinateUnitExecutor(unit(), self.adapter, self.ports)

    def test_coordinates_then_withdraw_then_one_review(self):
        # Existing per-action review is deliberately unusable. Only the final
        # whole-unit review may run; covered intermediate images are not needed.
        self.ports.muse_raises = False
        self.ports.review = lambda *args, **kwargs: self.fail("No per-stage model gate allowed.")
        result = self.executor.run()
        self.assertEqual(result["state"], "ACCEPTED")
        self.assertTrue(result["vehicle_arrival_verified"])
        self.assertTrue(result["empty_tool_return_required"])
        self.assertEqual(self.ports.load_checkpoint()["vehicle_arrival_verified"], True)
        self.assertEqual(self.ports.load_checkpoint()["review_provider_receipt"], "synthetic-provider")
        self.assertFalse(result["automatic_next_unit"])
        self.assertEqual(self.ports.capture_at, [0, 4])
        self.assertEqual(len(self.ports.unit_reviews), 1)
        self.assertEqual(len(self.ports.motions), 4)

        self.assertEqual([row["stage"]["phase"] for row in self.ports.unit_reviews[0][1]],
                         ["approach", "contact", "withdraw", "withdraw"])
        self.assertEqual(len({m.request_id for m in self.ports.motions}), 4)
        self.assertTrue(all(m.before_frame == {} for m in self.ports.motions))
        self.assertTrue(all(s["state"] == "DISPATCH_UNRESOLVED" for s in self.ports.pre_dispatch_states))
        with self.assertRaises(ExecutionBlocked):
            self.executor.run()
        self.assertEqual(len(self.ports.motions), 4)

    def test_current_site_binding_needs_no_fake_qualified_road(self):
        binding = CoordinateBinding(self.adapter.map_id, self.adapter.map_version, self.adapter.map_hash,
            self.adapter.tcp_definition_sha256, self.adapter.tool_id, self.adapter.car_id, self.adapter.surface_id)
        executor = CoordinateUnitExecutor(unit(), binding, self.ports)
        self.assertEqual(executor.run()["state"], "ACCEPTED")
        self.assertEqual(binding.observation_clearances, ())

    def test_muse_timeout_is_read_only_recoverable(self):
        self.ports.muse_raises = True
        with self.assertRaises(TimeoutError):
            self.executor.run()
        self.assertEqual(self.executor.state, "WAIT_REVIEW")
        self.ports.muse_raises = False
        self.executor.reobserve()
        self.assertEqual(len(self.ports.motions), 4)
        self.assertEqual(self.ports.capture_at, [0, 4, 4])

    def test_final_camera_failure_does_not_repeat_push(self):
        self.ports.fail_capture_at = 2
        with self.assertRaises(TimeoutError):
            self.executor.run()
        self.assertEqual(self.executor.state, "WAIT_REVIEW")
        self.ports.fail_capture_at = None
        self.executor.reobserve()
        self.assertEqual(len(self.ports.motions), 4)

    def test_unknown_contact_stops_before_withdrawal(self):
        self.ports.fail_motion_at = 2
        with self.assertRaises(TimeoutError):
            self.executor.run()
        self.assertEqual(self.executor.state, "NEEDS_RECONCILIATION")
        self.assertEqual(len(self.ports.motions), 2)
        self.assertEqual(len(self.ports.unit_reviews), 0)
        with self.assertRaises(ExecutionBlocked):
            self.executor.reobserve()

    def test_native_failure_stops_after_known_receipt(self):
        self.ports.fail_native_at = 2
        with self.assertRaises(TimeoutError):
            self.executor.run()
        self.assertEqual(self.executor.state, "NEEDS_RECONCILIATION")
        self.assertEqual(len(self.ports.motions), 2)

    def test_restart_never_continues(self):
        self.executor.run()
        self.assertTrue(self.ports.load_checkpoint()["vehicle_arrival_verified"])
        restarted = CoordinateUnitExecutor(unit(), self.adapter, self.ports)
        self.assertEqual(restarted.state, "NEEDS_RECONCILIATION")
        with self.assertRaises(ExecutionBlocked):
            restarted.run()
        self.assertEqual(len(self.ports.motions), 4)

    def test_progress_review_does_not_persist_final_arrival(self):
        executor = CoordinateUnitExecutor(replace(unit(), at_goal=False), self.adapter, self.ports)
        self.assertEqual(executor.run()["state"], "ACCEPTED")
        self.assertFalse(self.ports.load_checkpoint()["vehicle_arrival_verified"])
        self.assertEqual(self.ports.load_checkpoint()["review_provider_receipt"], "synthetic-provider")

    def test_joint_view_waits_for_signal_without_repeating_contact(self):
        target = replace(right_signal_target(), junction_id="OFFICE_BUILDING")
        executor = CoordinateUnitExecutor(replace(unit(), required_signal_observation=target), self.adapter, self.ports)
        self.assertEqual(executor.run()["state"], "WAIT_REVIEW")
        self.assertEqual(len(self.ports.motions), 4)
        self.assertEqual(self.ports.capture_at, [0, 4])
        self.assertFalse(self.ports.load_checkpoint()["vehicle_arrival_verified"])
        self.assertEqual(self.ports.load_checkpoint()["required_signal_observation_id"], target.id)
        self.ports.signal_visible = True
        self.assertEqual(executor.reobserve()["state"], "ACCEPTED")
        self.assertTrue(self.ports.load_checkpoint()["signal_region_visible"])
        self.assertEqual(len(self.ports.motions), 4)

    def test_joint_view_binding_is_checked_before_motion(self):
        target = replace(right_signal_target(), junction_id="OFFICE_BUILDING", registration_id="changed-view")
        executor = CoordinateUnitExecutor(replace(unit(), required_signal_observation=target), self.adapter, self.ports)
        with self.assertRaises(ExecutionBlocked):
            executor.run()
        self.assertEqual(self.ports.motions, [])
        with self.assertRaises(ValueError):
            replace(unit(), required_signal_observation=replace(target, approach_from="OTHER"))

    def test_uncertain_or_drifted_outcome_never_advances(self):
        for values in ({"review_verdict": "UNCERTAIN"}, {"visible": False},
                       {"expected_progress": False}, {"excessive_yaw": True},
                       {"car_footprint": "OVERLAPS_ISLAND"}, {"car_footprint": "UNCERTAIN"},
                       {"heading_matches_expected": False}):
            with self.subTest(values=values):
                ports = Ports()
                for key, value in values.items():
                    setattr(ports, key, value)
                executor = CoordinateUnitExecutor(unit(), self.adapter, ports)
                result = executor.run()
                self.assertEqual(result["state"], "WAIT_REVIEW")
                self.assertFalse(result["vehicle_arrival_verified"])
                self.assertFalse(ports.load_checkpoint()["vehicle_arrival_verified"])
                self.assertEqual(len(ports.motions), 4)

    def test_receiver_changes_during_review_require_reconciliation(self):
        self.ports.change_during_muse = True
        with self.assertRaises(ExecutionBlocked):
            self.executor.run()
        self.assertEqual(self.executor.state, "NEEDS_RECONCILIATION")
        self.assertFalse(self.ports.load_checkpoint()["vehicle_arrival_verified"])

    def test_receiver_change_during_initial_capture_prevents_motion(self):
        self.ports.change_during_capture = True
        with self.assertRaises(ExecutionBlocked):
            self.executor.run()
        self.assertEqual(len(self.ports.motions), 0)

    def test_installed_step_limit_cannot_be_expanded(self):
        self.ports.stroke_limit = 5
        with self.assertRaises(ExecutionBlocked):
            self.executor.run()
        self.assertEqual(len(self.ports.motions), 0)
        failures = [payload for kind, payload in self.ports.events if kind == "coordinate_unit_interrupted"]
        self.assertEqual(failures[-1]["error_code"], "UNIT_STAGE_LIMIT")

    def test_cli_preserves_primary_guard_code_when_hold_also_fails(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from unittest.mock import MagicMock, patch
        journal, ports, executor = MagicMock(), MagicMock(), MagicMock()
        executor.run.side_effect = ExecutionBlocked("NATIVE_BASELINE_CHANGED", "Synthetic private diagnostic.")
        ports.hold.side_effect = TimeoutError("Synthetic private hold endpoint.")
        with TemporaryDirectory() as folder, redirect_stderr(StringIO()) as error_output, \
                patch("tools.run_coordinate_unit.load_unit", return_value=(self.adapter, unit())), \
                patch("tools.run_coordinate_unit.read_json", return_value={}), \
                patch("tools.run_coordinate_unit.PrivateJournal", return_value=journal), \
                patch("tools.run_coordinate_unit.RealTaughtPorts", return_value=ports), \
                patch("tools.run_coordinate_unit.CoordinateUnitExecutor", return_value=executor):
            self.assertEqual(main(["--unit-file", "synthetic.json", "--config-file", "synthetic-config.json",
                                   "--output-dir", folder, "--execute"]), 3)
        failure = json.loads(error_output.getvalue())
        self.assertEqual(failure["error_code"], "NATIVE_BASELINE_CHANGED")
        self.assertEqual(failure["hold_error_type"], "TimeoutError")
        self.assertNotIn("private", error_output.getvalue())
        self.assertFalse(failure["automatic_replay"])

    def test_reject_discontinuity_missing_withdrawal_and_double_contact(self):
        original = unit()
        for stages in (original.stages[:2],
                       (replace(original.stages[0], phase="contact"), *original.stages[1:]),
                       (replace(original.stages[0], target_base=pose(9)), *original.stages[1:]),
                       (*original.stages[1:], original.stages[0])):
            with self.assertRaises(ValueError):
                replace(original, stages=stages)

    def test_explicit_site_review_binds_geometry_and_offline_loader_opens_no_ports(self):
        from unittest.mock import patch
        with TemporaryDirectory() as folder:
            root = Path(folder)
            binding = CoordinateBinding(self.adapter.map_id, self.adapter.map_version, self.adapter.map_hash,
                self.adapter.tcp_definition_sha256, self.adapter.tool_id, self.adapter.car_id, self.adapter.surface_id)
            review = {"schema": "pushpilot.operator-coordinate-unit-review.v1", "source": "operator",
                      "on_site_review": True, "experimental_contact_authorized": True,
                      "operator_instruction_reference": "Synthetic fixture, no actual authority.",
                      "binding": asdict(binding), "unit_geometry": unit_geometry(unit())}
            raw = json.dumps(review).encode()
            (root/"review.json").write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            proposed = replace(unit(), stages=tuple(replace(s, review_sha256=digest) for s in unit().stages))
            bundle = {"schema": "pushpilot.experimental-coordinate-unit.v1", "binding": asdict(binding),
                      "unit": asdict(proposed), "site_review": {"path": "review.json", "sha256": digest}}
            path = root/"unit.json"
            path.write_text(json.dumps(bundle))
            self.assertEqual(load_unit(path)[1], proposed)
            with patch("tools.run_coordinate_unit.RealTaughtPorts", side_effect=AssertionError("No offline IO")):
                self.assertEqual(main(["--unit-file", str(path)]), 0)
            bundle["unit"]["expected_visual"] = "Changed outcome must not reuse an earlier site review."
            path.write_text(json.dumps(bundle))
            with self.assertRaises(ValueError):
                load_unit(path)

    def test_joint_target_bundle_requires_original_matching_placement_record(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            binding = CoordinateBinding(self.adapter.map_id, self.adapter.map_version, self.adapter.map_hash,
                self.adapter.tcp_definition_sha256, self.adapter.tool_id, self.adapter.car_id, self.adapter.surface_id)
            target = replace(right_signal_target(), junction_id="OFFICE_BUILDING")
            metadata = {k: v for k, v in asdict(target).items() if k != "target_evidence_sha256"}
            raw = json.dumps({"schema": "pushpilot.signal-observation-target.v1", "visibility_only": True,
                              "signal_color_qualified": False, "target": metadata}).encode()
            (root/"target.json").write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            target = replace(target, target_evidence_sha256=digest)
            planned = replace(unit(), required_signal_observation=target)
            review = {"schema": "pushpilot.operator-coordinate-unit-review.v1", "source": "operator",
                      "on_site_review": True, "experimental_contact_authorized": True,
                      "operator_instruction_reference": "Synthetic reviewed placement; no actual hardware qualification.",
                      "binding": asdict(binding), "unit_geometry": unit_geometry(planned)}
            raw = json.dumps(review).encode()
            (root/"review.json").write_bytes(raw)
            review_hash = hashlib.sha256(raw).hexdigest()
            planned = replace(planned, stages=tuple(replace(s, review_sha256=review_hash) for s in planned.stages))
            bundle = {"schema": "pushpilot.experimental-coordinate-unit.v1", "binding": asdict(binding),
                      "unit": asdict(planned), "site_review": {"path": "review.json", "sha256": review_hash},
                      "signal_target_evidence": {"path": "target.json", "sha256": digest}}
            path = root/"unit.json"
            path.write_text(json.dumps(bundle))
            self.assertEqual(load_unit(path)[1], planned)
            bundle.pop("signal_target_evidence")
            path.write_text(json.dumps(bundle))
            with self.assertRaises(ValueError):
                load_unit(path)
            bundle["signal_target_evidence"] = {"path": "target.json", "sha256": digest}
            (root/"target.json").write_text("{}"); path.write_text(json.dumps(bundle))
            with self.assertRaises(ValueError):
                load_unit(path)


if __name__ == "__main__":
    unittest.main()
