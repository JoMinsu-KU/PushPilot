"""Pure-file completed C4 recovery; no device, provider or motion calls."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.robot_control.completed_native_resume import candidate, recover_before_frame
from backend.robot_control.mission_policy import MissionState, Phase, RouteStep
from backend.robot_control.taught_executor import ExecutionBlocked
from tests.test_mission_policy import plan, primitive


def fixture():
    template = plan()
    def trial(name, source, target, empty=False):
        return replace(primitive(name, source, target, empty=empty), release_mode="site_trial",
            qualified=False, current_site_review_sha256="c"*64)
    steps = tuple(RouteStep("C-step-"+str(i), trial("unit-"+str(i), "START" if i == 1 else "P"+str(i-1),
        "P"+str(i)), "zone", 0., at_goal=i == 6,
        review_mode="expected_outcome" if i == 6 else "intermediate_progress") for i in range(1, 7))
    old = replace(template, destination="VILLA", release_mode="site_trial", steps=steps,
        empty_return=(trial("return", "P6", "START", True),), parking=replace(template.parking, mode="delivery_only"))
    current = replace(old, binding=replace(old.binding, calibration_id="same-view-new-registration"))
    completed = MissionState(old.id, "session", phase=Phase.OBSERVE, step_index=3,
        issued_command_ids=("c1", "c2", "c3", "c4"), action_command_id="c4",
        start_verified=True, last_motion_completed_at_s=201.)
    interrupted = replace(completed, reason="PHYSICAL_STATUS_REQUIRED", reobservations=1)
    receipt = {"command_id": "c4", "primitive_id": "unit-4", "session_id": "session",
        "target_context_id": "P4", "completed_at_s": 201., "native_verified": True, "outcome": "COMPLETED"}
    return old, current, interrupted, completed, receipt


class CandidateTests(unittest.TestCase):
    def test_only_restores_original_c4_observation_and_preserves_command_lineage(self):
        old, current, interrupted, completed, receipt = fixture()
        restored, state = candidate(old, current, interrupted, completed, receipt)
        self.assertEqual(restored.id, old.id)
        self.assertEqual(restored.binding.calibration_id, current.binding.calibration_id)
        self.assertEqual(state.phase, Phase.OBSERVE)
        self.assertEqual(state.step_index, 3)
        self.assertEqual(state.issued_command_ids, completed.issued_command_ids)
        self.assertEqual(state.action_command_id, "c4")
        self.assertEqual(state.reason, "EXPLICIT_NATIVE_REVIEW_RECOVERY")
        self.assertEqual(state.reobservations, 0)
        self.assertIsNone(state.pending_command_id)
        self.assertEqual(interrupted.reason, "PHYSICAL_STATUS_REQUIRED")

    def test_changed_plan_stop_other_phase_or_signal_context_cannot_resume(self):
        old, current, interrupted, completed, receipt = fixture()
        for change in (replace(current, car_max_age_s=current.car_max_age_s+1),
                       replace(current, binding=replace(current.binding, camera_epoch="different")),
                       replace(current, destination="HANOK")):
            with self.assertRaises(ExecutionBlocked):
                candidate(old, change, interrupted, completed, receipt)
        for change in (replace(interrupted, phase=Phase.FAILED), replace(interrupted, step_index=2),
                       replace(interrupted, pending_command_id="not-proven"),
                       replace(interrupted, signal_step_index=0), replace(interrupted, start_verified=False),
                       replace(interrupted, seen_images=("changed-history",))):
            with self.assertRaises(ExecutionBlocked):
                candidate(old, current, change, completed, receipt)
        with self.assertRaises(ExecutionBlocked):
            candidate(old, current, interrupted, completed, receipt, original_error="OPERATOR_STOP")

    def test_inexact_or_unknown_completed_receipt_cannot_recreate_a_command(self):
        args = fixture()
        for fields in ({"native_verified": False}, {"outcome": "UNKNOWN"}, {"command_id": "c5"},
                       {"target_context_id": "P5"}, {"session_id": "foreign"}, {"completed_at_s": 202.}):
            with self.assertRaises(ExecutionBlocked):
                candidate(*args[:-1], {**args[-1], **fields})


class BeforeFrameTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.chain = [{"kind": "mission_primitive_complete", "created_at": 100., "payload": {"receipt": {}}},
            {"kind": "mission_primitive_intent", "created_at": 200., "payload": {"command_id": "c4"}}]

    def capture(self, name, timestamp, image=None):
        image = image or b"\xff\xd8synthetic-original-" + name.encode() + b"\xff\xd9"
        metadata = {"epoch": "same-camera", "frame": {"id": name, "sequence": 42,
            "received_at": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(), "age_ms": 20.,
            "width": 1920, "height": 1080, "sha256": hashlib.sha256(image).hexdigest(),
            "image_url": "/api/v1/live-camera/frames/"+name+"/image"}}
        path = self.root / ("camera-metadata-"+name+".private.json")
        path.write_text(json.dumps(metadata))
        imagepath = self.root / ("camera-original-"+name+".native.jpg")
        imagepath.write_bytes(image)
        return path, imagepath, metadata, image

    def test_unique_original_frame_uses_received_timestamp_and_ignores_mtime(self):
        path, imagepath, metadata, raw = self.capture("before", 175.)
        outside, _, _, _ = self.capture("outside", 149.)
        os.utime(path, (99999., 99999.))
        os.utime(outside, (175., 175.))
        frame, saved, evidence = recover_before_frame(self.root, self.chain, "c4", 150.)
        self.assertEqual(frame.original_jpeg, raw)
        self.assertEqual(frame.captured_at, 175.)
        self.assertEqual(frame.sha256, metadata["frame"]["sha256"])
        self.assertEqual(saved, metadata)
        self.assertFalse(evidence["mtime_used"])
        self.assertEqual(evidence["metadata_path"], str(path))
        self.assertEqual(evidence["image_path"], str(imagepath))
        self.assertFalse(evidence["car_verdict_created"])

    def test_previous_completion_and_dispatch_boundaries_are_both_enforced(self):
        self.capture("too-early", 99.)
        with self.assertRaises(ExecutionBlocked):
            recover_before_frame(self.root, self.chain, "c4", 50.)
        self.capture("after-completion", 101.)
        frame, _, evidence = recover_before_frame(self.root, self.chain, "c4", 50.)
        self.assertEqual(frame.captured_at, 101.)
        self.assertEqual(evidence["lower_capture_time"], 100.)
        with self.assertRaises(ExecutionBlocked):
            recover_before_frame(self.root, self.chain, "c4", 150.)

    def test_ambiguous_capture_or_original_bytes_never_selects_a_best_guess(self):
        self.capture("one", 175.)
        self.capture("two", 180.)
        with self.assertRaises(ExecutionBlocked) as error:
            recover_before_frame(self.root, self.chain, "c4", 150.)
        self.assertEqual(error.exception.code, "NATIVE_RESUME_BEFORE_IMAGE_NOT_UNIQUE")
        (self.root / "camera-metadata-two.private.json").unlink()
        (self.root / "camera-original-one.native.jpg").write_bytes(b"corrupted")
        with self.assertRaises(ExecutionBlocked) as error:
            recover_before_frame(self.root, self.chain, "c4", 150.)
        self.assertEqual(error.exception.code, "NATIVE_RESUME_ORIGINAL_IMAGE_NOT_UNIQUE")

    def test_ambiguous_intent_missing_prior_completion_and_naive_time_reject(self):
        path, _, metadata, _ = self.capture("one", 175.)
        for chain in (self.chain+self.chain[-1:], self.chain[1:]):
            with self.assertRaises(ExecutionBlocked):
                recover_before_frame(self.root, chain, "c4", 150.)
        metadata["frame"]["received_at"] = "2026-11-02T12:00:00"
        path.write_text(json.dumps(metadata))
        with self.assertRaises(ExecutionBlocked):
            recover_before_frame(self.root, self.chain, "c4", 150.)


if __name__ == "__main__":
    unittest.main()
