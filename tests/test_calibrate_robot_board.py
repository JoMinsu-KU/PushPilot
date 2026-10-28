"""Synthetic metrology CLI tests; no equipment or private coordinates."""
from copy import deepcopy
import io
import json
import math
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import calibrate_robot_board as calibrate


class CalibrationCliTests(unittest.TestCase):
    def setUp(self):
        identity = {
            "map_id": "synthetic-map", "map_version": "synthetic-v1", "map_hash": "a" * 64,
            "camera_epoch": "synthetic-camera", "registration_id": "synthetic-registration",
            "tcp_id": "synthetic-tcp", "tcp_definition_sha256": "b" * 64,
            "tool_id": "synthetic-probe", "drawing_axes": "x_right_y_down",
        }

        def point(name, xy):
            return {"measurement_id": name, "drawing_xy_mm": list(xy),
                    "base_xy_mm": [100 + xy[0], 200 - xy[1]],
                    "evidence_reference": "synthetic-capture-" + name, "source": "measured"}

        self.data = {
            "schema": calibrate.INPUT_SCHEMA, "calibration_id": "synthetic-calibration",
            "identity": identity,
            "domain": {"min_x_mm": 0, "min_y_mm": 0, "max_x_mm": 120, "max_y_mm": 100},
            "policy": {"max_fit_residual_mm": .5, "max_check_error_mm": .75},
            "fit_points": [point("p1", (10, 10)), point("p2", (110, 10)), point("p3", (10, 90))],
            "independent_check": point("check", (90, 80)),
        }

    def test_measured_fit_check_report_never_authorizes_or_generates_profile(self):
        result = calibrate.fit_measured_pairs(self.data)
        self.assertTrue(result["independent_check_accepted"])
        self.assertFalse(result["installation_qualified"])
        self.assertFalse(result["route_coverage_qualified"])
        self.assertFalse(result["registration"]["route_coverage_qualified"])
        self.assertFalse(result["motion_issued"])
        self.assertFalse(result["profile_created"])
        self.assertEqual(result["registration"]["identity"], self.data["identity"])
        self.assertNotIn("allow_motion", result["registration"])
        self.assertNotIn("site_verified", result["registration"])

    def test_independent_failure_is_saved_as_failed_not_silently_refitted(self):
        value = deepcopy(self.data)
        value["independent_check"]["base_xy_mm"][0] += 3
        result = calibrate.fit_measured_pairs(value)
        original = calibrate.fit_measured_pairs(self.data)
        self.assertFalse(result["independent_check_accepted"])
        self.assertEqual(result["registration"], original["registration"])

    def test_nominal_or_incomplete_or_reused_evidence_is_rejected(self):
        variants = []
        for source in ("nominal", "meta", "simulation"):
            value = deepcopy(self.data)
            value["fit_points"][0]["source"] = source
            variants.append(value)
        value = deepcopy(self.data)
        del value["independent_check"]
        variants.append(value)
        value = deepcopy(self.data)
        value["independent_check"]["evidence_reference"] = value["fit_points"][0]["evidence_reference"]
        variants.append(value)
        value = deepcopy(self.data)
        value["fit_points"][0]["identity"] = value["identity"]
        variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                calibrate.fit_measured_pairs(value)

    def test_input_is_bounded_and_duplicate_or_nonfinite_json_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for text in ('{"schema":1,"schema":2}', '{"x":NaN}', '{"x":Infinity}', " " * 65537):
                path.write_text(text)
                with self.subTest(text=text[:40]), self.assertRaises(ValueError):
                    calibrate.read_pairs(path)

    def test_new_private_report_is_not_overwritten(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "calibration.json"
            report = calibrate.fit_measured_pairs(self.data)
            calibrate.save_report(path, report)
            self.assertEqual(json.loads(path.read_text()), report)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                calibrate.save_report(path, {"replaced": True})
            self.assertEqual(json.loads(path.read_text()), report)

    def test_cli_returns_failed_check_and_sanitizes_invalid_input(self):
        with TemporaryDirectory() as directory:
            source, target = Path(directory) / "pairs.json", Path(directory) / "result.json"
            value = deepcopy(self.data)
            value["independent_check"]["base_xy_mm"][0] += 3
            source.write_text(json.dumps(value))
            with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                self.assertEqual(calibrate.main(["--pairs", str(source), "--output", str(target)]), 2)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "check_failed")
            source.write_text('{"secret-input-name":NaN}')
            with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                self.assertEqual(calibrate.main(["--pairs", str(source), "--output", str(target)]), 2)
            self.assertNotIn("secret-input-name", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
