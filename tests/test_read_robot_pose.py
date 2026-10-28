"""Equipment-free tests of current-coordinate acquisition, not the private driver."""
from __future__ import annotations

import copy
import io
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import read_robot_pose as reader


def snapshot():
    """Synthetic values are not real robot coordinates or a reviewed profile."""
    return {"program_before": [6], "program_after": [6], "flags": [1, 1, 0, 0, 0, 0],
            "pose": [10, 20, 30, 0, 0, 0], "joint": [0] * 6, "speed": [0] * 6}


class NativeCoordinateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.native = Mock()
        self.native.snapshot.side_effect = [snapshot(), snapshot(), snapshot()]
        self.factory = Mock(return_value=self.native)
        self.transport = SimpleNamespace(Native=self.factory)
        self.loader = Mock(return_value={"transport": self.transport})
        self.sleep = Mock()

    def tearDown(self):
        self.temp.cleanup()

    def capture(self, **kwargs):
        return reader.collect(self.root / "verified-runtime", self.root / "private", runtime_loader=self.loader,
                              sleep=self.sleep, **kwargs)

    def test_reads_only_native_and_writes_private_fresh_evidence(self):
        record, path = self.capture(label="pizza-start")
        self.assertTrue(record["accepted_teaching_point"])
        self.assertEqual(record["source"], "native_fc03_readonly")
        self.assertEqual(len(record["samples"]), 3)
        self.assertEqual(json.loads(path.read_text()), record)
        self.loader.assert_called_once_with(self.root / "verified-runtime")
        self.assertEqual(self.native.method_calls, [("snapshot", (), {"timeout_s": 2})] * 3)
        self.assertEqual(self.sleep.call_count, 2)
        self.assertFalse(record["motion_issued"])
        for forbidden in ("profile", "allow_motion", "site_verified", "session_id", "planned_pose"):
            self.assertNotIn(forbidden, record)
        self.assertFalse((self.root / "verified-runtime").exists())
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_runtime_verification_failure_never_constructs_native(self):
        self.loader.side_effect = RuntimeError("Secret password, old coordinates, private path")
        record, path = self.capture()
        self.factory.assert_not_called()
        self.assertFalse(record["accepted_teaching_point"])
        self.assertEqual(record["error_type"], "RuntimeError")
        self.assertNotIn("Secret", path.read_text())
        self.assertEqual(record["samples"], [])

    def test_timeout_ends_series_without_retry_or_old_sample_substitution(self):
        self.native.snapshot.side_effect = [snapshot(), TimeoutError("Credentials must not be logged"), snapshot()]
        record, path = self.capture()
        self.assertEqual(self.native.snapshot.call_count, 2)
        self.assertEqual(len(record["samples"]), 1)
        self.assertFalse(record["accepted_teaching_point"])
        self.assertEqual(record["reason"], "NATIVE_ACQUISITION_FAILED")
        self.assertNotIn("Credentials", path.read_text())

    def test_nonzero_quantized_speed_retains_diagnostic_not_teaching(self):
        row = snapshot()
        row["speed"][0] = .1
        self.native.snapshot.side_effect = [snapshot(), row, snapshot()]
        record, path = self.capture()
        self.assertFalse(record["accepted_teaching_point"])
        self.assertEqual(record["acquisition_status"], "diagnostic")
        self.assertEqual(record["reason"], "NONZERO_QUANTIZED_JOINT_SPEED")
        self.assertEqual(json.loads(path.read_text())["samples"][1]["snapshot"]["speed"][0], .1)

    def test_pairwise_drift_cannot_hide_by_comparison_only_to_middle(self):
        rows = [snapshot(), snapshot(), snapshot()]
        rows[0]["pose"][0] -= .2
        rows[2]["pose"][0] += .2
        self.native.snapshot.side_effect = rows
        record, _ = self.capture()
        self.assertEqual(record["reason"], "COORDINATES_CHANGED_DURING_CAPTURE")

    def test_exact_native_quantization_drift_is_accepted(self):
        rows = [snapshot(), snapshot(), snapshot()]
        rows[1]["pose"][0] += .1
        rows[2]["joint"][4] += .2
        self.native.snapshot.side_effect = rows
        record, _ = self.capture()
        self.assertTrue(record["accepted_teaching_point"])

    def test_orientation_wrap_does_not_fabricate_a_large_rotation(self):
        rows = [snapshot(), snapshot(), snapshot()]
        rows[0]["pose"][3] = 179.9
        rows[1]["pose"][3] = -180
        rows[2]["pose"][3] = -179.9
        self.native.snapshot.side_effect = rows
        record, _ = self.capture()
        self.assertTrue(record["accepted_teaching_point"])

    def test_program_flags_and_state_change_are_diagnostics(self):
        for change, expected in (
            ({"program_after": [2]}, "PROGRAM_STATE_CHANGED_DURING_CAPTURE"),
            ({"program_before": [4], "program_after": [4]}, "PROGRAM_STATE_CHANGED_DURING_CAPTURE"),
            ({"flags": [1, 1, 0, 0, 1, 0]}, "ROBOT_FLAGS_CHANGED_DURING_CAPTURE"),
        ):
            with self.subTest(change=change):
                row = snapshot()
                row.update(change)
                self.native.snapshot.side_effect = [snapshot(), row, snapshot()]
                record, _ = self.capture()
                self.assertFalse(record["accepted_teaching_point"])
                self.assertEqual(record["reason"], expected)

    def test_consistently_ineligible_flags_stay_diagnostic(self):
        row = snapshot()
        row["flags"] = [0, 1, 0, 0, 0, 0]
        self.native.snapshot.side_effect = [copy.deepcopy(row) for _ in range(3)]
        record, _ = self.capture()
        self.assertEqual(record["reason"], "ROBOT_FLAGS_REQUIRE_INSPECTION")

    def test_stopped_program_zero_can_record_coordinates_without_inferred_readiness(self):
        row = snapshot()
        row.update(program_before=[0], program_after=[0])
        self.native.snapshot.side_effect = [copy.deepcopy(row) for _ in range(3)]
        record, _ = self.capture()
        self.assertTrue(record["accepted_teaching_point"])
        self.assertEqual(record["samples"][0]["snapshot"]["program_after"], [0])
        self.assertIn("no program-state readiness", record["program_state_scope"])

    def test_invalid_numbers_vectors_registers_fail_without_serializing_nan(self):
        for key, value in (("pose", [math.nan] * 6), ("joint", [True] * 6),
                           ("speed", [0] * 5), ("flags", [1, 1, 0, 0, 0, -1]),
                           ("program_before", [True]), ("pose", [10001] * 6)):
            with self.subTest(key=key, value=value):
                row = snapshot()
                row[key] = value
                self.native.snapshot.side_effect = [row]
                record, path = self.capture()
                self.assertFalse(record["accepted_teaching_point"])
                self.assertEqual(record["samples"], [])
                self.assertEqual(json.loads(path.read_text())["reason"], "NATIVE_ACQUISITION_FAILED")

    def test_one_sample_is_a_fresh_diagnostic_not_stationary_teaching(self):
        record, _ = self.capture(samples=1)
        self.assertFalse(record["accepted_teaching_point"])
        self.assertEqual(record["reason"], "AT_LEAST_TWO_FRESH_SAMPLES_REQUIRED")
        self.assertEqual(len(record["samples"]), 1)

    def test_ten_samples_is_bounded_and_each_capture_has_unique_evidence(self):
        self.native.snapshot.side_effect = [snapshot() for _ in range(20)]
        first, path = self.capture(samples=10)
        second, second_path = self.capture(samples=10)
        self.assertTrue(first["accepted_teaching_point"])
        self.assertEqual(len(second["samples"]), 10)
        self.assertNotEqual(path, second_path)

    def test_invalid_labels_and_sample_counts_never_load_or_write(self):
        for kwargs in ({"label": "../escape"}, {"label": "\nsecret"}, {"label": "x" * 65},
                       {"samples": 0}, {"samples": 11}, {"samples": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.capture(**kwargs)
        self.loader.assert_not_called()
        self.assertFalse((self.root / "private").exists())

    def test_existing_receiver_metadata_and_mailbox_are_never_touched(self):
        runtime = self.root / "verified-runtime"
        runtime.mkdir()
        for name in ("current_session.json", "command.json", "host-status.json", "executor-hold.json"):
            (runtime / name).write_text("Historical sentinel; never consume")
        self.capture()
        for path in runtime.iterdir():
            self.assertEqual(path.read_text(), "Historical sentinel; never consume")

    def test_cli_prints_only_compact_private_readback(self):
        record, path = self.capture()
        with patch.object(reader, "collect", return_value=(record, path)), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(reader.main(["--label", "pizza-start"]), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value["tcp_mm_deg"], snapshot()["pose"])
        self.assertEqual(value["joint_deg"], snapshot()["joint"])
        self.assertFalse(value["motion_issued"])
        self.assertNotIn("samples", value)

    def test_cli_error_does_not_echo_exception_details(self):
        with patch.object(reader, "collect", side_effect=OSError("Password is private")), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(reader.main([]), 2)
        self.assertNotIn("Password", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["error_type"], "OSError")

    @unittest.skipIf(os.name == "nt", "Windows local symlink privilege is not assumed")
    def test_symlink_output_is_rejected_before_runtime_load(self):
        target = self.root / "outside"
        target.mkdir()
        link = self.root / "private"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.capture()
        self.loader.assert_not_called()
        self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
