"""Equipment-free retirement of a held mission at a new precision-bound START."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.robot_control.site_trial_driver import SiteTrialMissionDriver
from backend.robot_control.taught_executor import ExecutionBlocked
from tests.test_site_trial_driver import Observer, SitePorts, fixture


class RetirementPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runtime = patch("backend.robot_control.site_trial_driver.load_runtime", return_value={
            "policy": SimpleNamespace(MAX_PROFILE_BYTES=65536, valid=lambda *args: None)})
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        self.path, self.config, self.packet, self.review, request = fixture(self.root)
        self.config["observations"] = {"signal_targets": {"gate": {
            "registration_id": "registration", "marker_pixel": [1, 2]}}}
        self.path.write_text(json.dumps(self.config))
        self.driver = SiteTrialMissionDriver(self.path, Observer(), port_factory=SitePorts)
        self.addCleanup(self.driver.close)
        self.plan = self.driver.prepare(request)
        self.driver.stop_latch.set()
        self.driver.journal.checkpoint({"state": "RECONCILED_STATIONARY_NO_MOTION",
            "operation_id": "preserved-old-operation", "automatic_replay": False})
        nominal = self.packet["contexts"]["START"]["pose_base"]
        actual = [a+b for a, b in zip(nominal, (.001, -.001, .002, -.001, .001, -.001))]
        self.reference = {"schema": "pushpilot.stationary-start-reference.v1", "session_id": "a"*32,
            "packet_sha256": self.config["packet"]["sha256"],
            "review_sha256": self.config["profile_review"]["sha256"],
            "nominal_start": nominal, "observed_start": actual,
            "native_snapshot": {"session_id": "a"*32, "tcp_base": list(actual),
                "held_disarmed_idle": True, "native_evidence_sha256": "b"*64,
                "native_tcp_base": list(nominal)},
            "review_reference": "Synthetic explicit stationary START precision check.",
            "operator_request": "Synthetic operator retirement request; no device access."}
        self.candidate = deepcopy(self.config)
        self.raw = self.driver.ports.raw
        self.raw.status["installation"]["fixed_tcp_z_mm"] = actual[2]
        self.raw.status["receiver"].update(session_id="a"*32, actual_pose=list(actual))

    def save_candidate(self):
        refpath = self.root / "fresh-start.private.json"
        refpath.write_text(json.dumps(self.reference))
        self.candidate["session_start_reference"] = {
            "path": str(refpath), "sha256": hashlib.sha256(refpath.read_bytes()).hexdigest()}
        self.path.write_text(json.dumps(self.candidate))

    def retire(self):
        return self.driver.retire_at_start(self.plan.id, "Explicit fresh START retirement after an empty return.")

    def assert_preserved_hold(self):
        self.assertEqual(self.driver.currentplan.id, self.plan.id)
        self.assertTrue(self.driver.stop_latch.is_set())
        self.assertEqual(self.driver.binding.calibration_id, "registration")
        self.assertEqual(self.driver.journal.load()["state"], "RECONCILED_STATIONARY_NO_MOTION")
        self.assertEqual(self.driver.profile_review["site"], self.review["site"])

    def test_fresh_exact_start_precision_and_registration_retire_without_commands(self):
        before_files = {k: Path(self.config[k]["path"]).read_bytes() for k in ("packet", "profile_review")}
        self.candidate["ports"]["registration_id"] = "new-display-reference"
        self.candidate["site_binding"]["calibration_id"] = "new-display-reference"
        self.candidate["observations"]["signal_targets"]["gate"]["registration_id"] = "new-display-reference"
        self.save_candidate()
        before_calls = len(self.raw.calls)
        with patch.object(self.driver, "_load", wraps=self.driver._load) as reload_current:
            result = self.retire()
        self.assertEqual(reload_current.call_count, 1)
        self.assertFalse(result["motion_issued"])
        self.assertFalse(result["automatic_resume"])
        self.assertTrue(result["at_start"])
        self.assertIsNone(self.driver.currentplan)
        self.assertEqual(self.driver.binding.calibration_id, "new-display-reference")
        self.assertEqual(self.driver.config["contexts"]["START"]["pose_base"], self.reference["observed_start"])
        self.assertEqual(self.driver.profile_review["site"]["fixed_tcp_z_mm"], self.reference["observed_start"][2])
        self.assertTrue(self.driver.stop_latch.is_set())
        self.assertEqual(self.driver.journal.load()["state"], "MISSION_RETIRED_AT_START")
        self.assertFalse(any(payload is not None for _, payload in self.raw.calls[before_calls:]))
        self.assertEqual(self.driver.ports.intents, [])
        for k, original in before_files.items():
            self.assertEqual(Path(self.config[k]["path"]).read_bytes(), original)
        for key in ("workspace_min_mm", "workspace_max_mm", "max_step_mm", "max_speed_mm_s", "max_accel_mm_s2"):
            self.assertEqual(self.driver.profile_review[key], self.review[key])

    def test_five_mm_shift_and_missing_independent_reference_are_rejected_before_reload(self):
        for mutate in (lambda r: r["observed_start"].__setitem__(0, 5.),
                       lambda r: r["native_snapshot"].update(native_evidence_sha256="")):
            original = deepcopy(self.reference)
            mutate(self.reference)
            self.save_candidate()
            with patch.object(self.driver, "_load", wraps=self.driver._load) as reload_current:
                with self.assertRaises(ExecutionBlocked):
                    self.retire()
                reload_current.assert_not_called()
            self.assert_preserved_hold()
            self.reference = original

    def test_stale_session_and_nearby_but_inexact_source_are_rejected(self):
        self.save_candidate()
        baseline = deepcopy(self.raw.status)
        for mutate in (lambda s: s["receiver"].update(session_id="c"*32),
                       lambda s: s["receiver"]["actual_pose"].__setitem__(0, self.reference["observed_start"][0]+.001)):
            self.raw.status = deepcopy(baseline)
            mutate(self.raw.status)
            with self.assertRaises(ExecutionBlocked) as caught:
                self.retire()
            self.assertEqual(caught.exception.code, "RESET_START_REFERENCE_MISMATCH")
            self.assert_preserved_hold()

    def test_stale_native_and_site_tool_change_preserve_old_mission(self):
        self.save_candidate()
        original_snapshot = self.driver.ports.snapshot
        self.driver.ports.snapshot = lambda: replace(original_snapshot(), native_observed_at=0.)
        with self.assertRaises(ExecutionBlocked):
            self.retire()
        self.assert_preserved_hold()
        self.driver.ports.snapshot = original_snapshot
        self.raw.status["installation"]["tool_id"] = "different-tool"
        with self.assertRaises(ExecutionBlocked) as caught:
            self.retire()
        self.assertEqual(caught.exception.code, "RESET_SITE_CHANGED")
        self.assert_preserved_hold()

    def test_other_limits_geometry_references_and_pixels_cannot_change(self):
        baseline = deepcopy(self.candidate)
        for mutate in (lambda c: c["ports"].update(command_timeout_s=120.),
                       lambda c: c["measurement_adapter"].update(working_z_mm=999.),
                       lambda c: c["packet"].update(sha256="e"*64),
                       lambda c: c["profile_review"].update(path="different-review.json"),
                       lambda c: c["observations"]["signal_targets"]["gate"].update(marker_pixel=[4, 5])):
            self.candidate = deepcopy(baseline)
            mutate(self.candidate)
            self.save_candidate()
            with self.assertRaises(ExecutionBlocked) as caught:
                self.retire()
            self.assertEqual(caught.exception.code, "RESET_CONFIGURATION_CHANGED")
            self.assert_preserved_hold()

    def test_reference_file_tamper_and_unreconciled_failure_do_not_retire(self):
        self.save_candidate()
        Path(self.candidate["session_start_reference"]["path"]).write_text("{}")
        with self.assertRaises(ExecutionBlocked):
            self.retire()
        self.assert_preserved_hold()
        self.save_candidate()
        failure = {"state": "PROFILE_PREPARATION_FAILED", "error_code": "PROFILE_QUERY_OUTCOME_UNRESOLVED"}
        self.driver.journal.checkpoint(failure)
        with self.assertRaises(ExecutionBlocked) as caught:
            self.retire()
        self.assertEqual(caught.exception.code, "RESET_RECONCILIATION_REQUIRED")
        self.assertEqual(self.driver.journal.load(), failure)
        self.assertEqual(self.driver.currentplan.id, self.plan.id)


if __name__ == "__main__":
    unittest.main()
