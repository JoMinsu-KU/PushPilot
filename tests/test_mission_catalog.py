"""Equipment-free evidence integrity and no-replay catalogue tests."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from backend.robot_control.mission_catalog import (
    EvidenceReference, MeasuredPrimitive, MeasuredStage, PrimitiveQualification,
    RuntimeUnitContext, check_recipe_continuity, compile_coordinate_primitive,
    content_hash, deduplicate_motions, match_measured_recontact, primitive_from_dict,
    verify_journal, measured_subpath, disabled_route_template,
)
from tools.build_measured_mission_catalog import EvidenceStore, file_hash, verify_motion


def pose(x, y=0, yaw=0):
    return (float(x), float(y), 7.4, -180., 0., float(yaw))


def reference():
    return EvidenceReference("synthetic.zip", "result.json", "a"*64, "b"*64)


def stage(phase, x, end, index):
    return MeasuredStage(str(index), phase, pose(x), pose(end), f"historical-{index}", reference())


def primitive():
    return MeasuredPrimitive("measured", "coordinate_unit", (
        stage("approach", 0, 10, 0), stage("contact", 10, 20, 1), stage("withdraw", 20, 15, 2)),
        "PIZZA", "OFFICE_BUILDING", "Actual vehicle progress towards the Office frontage.",
        "PASS", True, (reference(),), ("CURRENT_INSTALLATION_RELEASE_REQUIRED",), True)


def qualification(p):
    return PrimitiveQualification(p.geometry_sha256, "current-installation",
                                  "1"*64, "2"*64, "3"*64, "4"*64, True)


def context():
    return RuntimeUnitContext("current-plan", 3, "current-installation", "current-profile", pose(0))


class CatalogueTests(unittest.TestCase):
    def test_clearance_suffix_preserves_original_direction_and_stage_identity(self):
        p = replace(primitive(), kind="empty_path", stages=(stage("empty", 0, 10, 4), stage("empty", 10, 20, 5)))
        selected = measured_subpath(p, pose(10), pose(20), path_id="return-suffix")
        self.assertEqual(selected.stages, (p.stages[1],))
        self.assertFalse(selected.to_dict()["automatically_executable"])
        with self.assertRaises(ValueError):
            measured_subpath(p, pose(20), pose(10), path_id="invented-reverse")
        with self.assertRaises(ValueError):
            measured_subpath(primitive(), pose(10), pose(20), path_id="loaded")

    def test_route_template_retains_failed_original_and_disables_every_release(self):
        p = replace(primitive(), original_verdict="FAIL", original_arrived=False)
        result = disabled_route_template("VILLA", [{"role": "delivery", "primitive_ids": [p.id]}],
            [{"gap": {"id": "RETURN", "reason": "No executed return source."}}], {p.id:p},
            signal_plan={"qualified": False}, arrival_evidence={"source": "operator_acceptance"})
        self.assertFalse(result["enabled"])
        self.assertEqual(result["route_program"][0]["original_verdict"], "FAIL")
        self.assertIsNone(result["driver_configuration_template"]["routes"][0]["plan"])
        self.assertIsNone(result["driver_configuration_template"]["primitives"][p.id]["qualification"])
        self.assertEqual(result["gaps"][0]["id"], "RETURN")

    def test_reconciled_missing_done_is_a_link_not_a_fabricated_motion(self):
        p = primitive()
        link = {"id": "RECOVERED", "evidence": [asdict(reference())], "original_done_missing": True,
                "new_command_issued": False, "automatically_executable": False,
                "release_blocker": "Current independent release required."}
        result = disabled_route_template("VILLA", [{"role": "delivery", "primitive_ids": [p.id]},
            {"historical_reconciliation":link}], [], {p.id:p}, signal_plan={}, arrival_evidence={})
        self.assertEqual(result["counts"]["route_stages"], 3)
        self.assertEqual(result["route_program"][1]["kind"], "historical_reconciliation")
        self.assertFalse(result["gaps"][0]["historical_geometry_missing"])
        with self.assertRaises(ValueError):
            disabled_route_template("VILLA", [{"historical_reconciliation":{**link,"new_command_issued":True}}],
                [], {p.id:p}, signal_plan={}, arrival_evidence={})

    def test_compiler_generates_new_ids_and_uses_current_bindings(self):
        p = primitive()
        a = compile_coordinate_primitive(p, context(), qualification(p))
        b = compile_coordinate_primitive(p, context(), qualification(p))
        self.assertNotEqual(a.id, b.id)
        self.assertEqual(a.profile_id, "current-profile")
        self.assertEqual(a.installation_id, "current-installation")
        self.assertEqual(a.plan_id, "current-plan")
        self.assertEqual(a.stages[0].start_base, p.stages[0].start_base)
        self.assertFalse(any(s.original_request_id in json.dumps(asdict(a)) for s in p.stages))

    def test_native_source_tolerance_does_not_shift_geometry(self):
        p = primitive()
        actual = replace(context(), current_pose=pose(.08))
        result = compile_coordinate_primitive(p, actual, qualification(p))
        self.assertEqual(result.stages[0].start_base, pose(0))
        with self.assertRaises(ValueError):
            compile_coordinate_primitive(p, replace(actual, current_pose=pose(.101)), qualification(p))
        with self.assertRaises(ValueError):
            replace(actual, source_tolerance=1.)

    def test_missing_or_wrong_qualification_and_failed_outcome_rejected(self):
        p = primitive()
        with self.assertRaises(ValueError):
            compile_coordinate_primitive(p, context(), replace(qualification(p), primitive_geometry_sha256="f"*64))
        with self.assertRaises(ValueError):
            compile_coordinate_primitive(p, context(), replace(qualification(p), installation_id="old-installation"))
        with self.assertRaises(ValueError):
            replace(qualification(p), physical_release_verified=False)
        failed = replace(p, original_verdict="FAIL")
        with self.assertRaises(ValueError):
            compile_coordinate_primitive(failed, context(), qualification(failed))

    def test_contact_and_observation_are_not_conflated(self):
        p = primitive()
        self.assertEqual(p.last_contact_base, pose(20))
        self.assertEqual(p.observation_base, pose(15))
        self.assertFalse(p.to_dict()["automatically_executable"])

    def test_no_geometry_snapping_or_wrapped_euler_comparison(self):
        p = primitive()
        following = replace(p, id="following", stages=(
            replace(p.stages[0], start_base=pose(15, yaw=360), target_base=pose(10, yaw=360)),
            replace(p.stages[1], start_base=pose(10, yaw=360), target_base=pose(20, yaw=360)),
            replace(p.stages[2], start_base=pose(20, yaw=360), target_base=pose(15, yaw=360))))
        gaps = check_recipe_continuity((p, following))
        self.assertEqual(gaps[0]["xyz_gap_mm"], 0.)
        self.assertEqual(gaps[0]["literal_euler_difference_deg"][-1], 360.)
        self.assertFalse(gaps[0]["connector_created"])

    def test_measured_recontact_is_not_a_reversed_withdrawal(self):
        p = primitive()
        withdrawal = MeasuredPrimitive("withdraw", "observation_path", (p.stages[-1],),
            p.source, p.target, p.expected_visual, "PASS", False, p.evidence, p.blockers)
        self.assertIsNone(match_measured_recontact(pose(15), pose(20), (withdrawal,)))
        measured = replace(withdrawal, id="measured-approach", kind="recontact_path",
                           stages=(stage("approach", 15, 20, 3),), original_verdict="FAIL")
        self.assertEqual(match_measured_recontact(pose(15), pose(20), (measured,)), measured)
        # A parent's failed car outcome is retained even if approach endpoints are known.
        self.assertEqual(measured.original_verdict, "FAIL")

    def test_catalogue_roundtrip_and_hash_tamper(self):
        p = primitive()
        self.assertEqual(primitive_from_dict(p.to_dict()), p)
        value = json.loads(json.dumps(p.to_dict()))
        value["stages"][0]["start_base"][0] = .5
        with self.assertRaises(ValueError):
            primitive_from_dict(value)

    def test_discontinuous_or_duplicate_physical_steps_rejected(self):
        p = primitive()
        with self.assertRaises(ValueError):
            replace(p, stages=(p.stages[0], replace(p.stages[1], start_base=pose(11)), p.stages[2]))
        with self.assertRaises(ValueError):
            replace(p, stages=(p.stages[0], replace(p.stages[1], original_request_id="historical-0"), p.stages[2]))

    def test_uuid_dedup_detects_conflicting_physical_identity(self):
        row = {"request_id": "uuid", "session_id": "old", "receiver_endpoint_sequence": 2,
               "kind": "translate", "start_base_mm_deg": list(pose(0)), "end_base_mm_deg": list(pose(1))}
        self.assertEqual(deduplicate_motions([row, row])[1], 1)
        with self.assertRaises(ValueError):
            deduplicate_motions([row, {**row, "session_id": "other"}])

    def test_original_journal_corruption_rejected(self):
        event = {"index": 1, "previous_sha256": "0"*64, "kind": "coordinate_unit_review",
                 "created_at": 1, "payload": {"result": {"verdict": "FAIL"}}}
        original = {**event, "sha256": content_hash(event)}
        raw = json.dumps(original).encode()
        self.assertEqual(verify_journal(raw)[0]["payload"]["result"]["verdict"], "FAIL")
        with self.assertRaises(ValueError):
            verify_journal(raw.replace(b"FAIL", b"PASS"))

    def test_archive_and_member_hashes_checked_without_extracting(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "original.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("original.json", b'{"value":1}')
            store = EvidenceStore([{"path": str(path), "sha256": file_hash(path)}])
            try:
                ref = asdict(store.reference(str(path.resolve()), "original.json"))
                self.assertEqual(store.read_reference(ref), {"value": 1})
                with self.assertRaises(ValueError):
                    store.read_reference({**ref, "sha256": "0"*64})
                with self.assertRaises(ValueError):
                    store.raw(str(path.resolve()), "../outside")
            finally:
                store.close()
            with self.assertRaises(ValueError):
                EvidenceStore([{"path": str(path), "sha256": "0"*64}])


if __name__ == "__main__":
    unittest.main()
