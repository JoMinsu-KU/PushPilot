"""No-motion reconstruction of the exact completed C4 Native-read interruption.

The caller verifies the original service error, immutable journal chain,
terminal robot receipt, fresh endpoint and camera identity. This module never
advances C4, creates a command, or supplies a car verdict; fresh MUSE review
must still make the normal policy select C5.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

from .mission_policy import Phase
from .mission_resume import require
from .taught_executor import Frame


def candidate(old_plan, current_plan, interrupted, completed, receipt, *, original_error="PHYSICAL_STATUS_REQUIRED"):
    old = asdict(old_plan)
    new = asdict(replace(current_plan, id=old_plan.id))
    permitted = deepcopy(old)
    permitted["binding"]["calibration_id"] = new["binding"]["calibration_id"]
    require(new == permitted, "NATIVE_RESUME_PLAN_CHANGED")
    require(original_error == "PHYSICAL_STATUS_REQUIRED"
            and old_plan.destination == "VILLA" and old_plan.release_mode == "site_trial"
            and interrupted.mission_id == completed.mission_id == old_plan.id
            and interrupted.phase == completed.phase == Phase.OBSERVE
            and interrupted.step_index == completed.step_index == 3
            and len(current_plan.steps) > 4, "NATIVE_RESUME_NOT_COMPLETED_C4")
    step, following = current_plan.steps[3:5]
    require(step.id == "C-step-4" and following.id == "C-step-5"
            and step.review_mode == "intermediate_progress" and step.observation_required
            and not step.at_goal and not step.primitive.empty_tool and step.signal_gate is None
            and interrupted.start_verified and not interrupted.vehicle_delivered
            and interrupted.signal_step_index is None and interrupted.admitted_signal_step_index is None
            and interrupted.green_expires_at_s is None and interrupted.green_expirations == 0
            and not interrupted.green_image_sha256s and interrupted.green_last_captured_at_s == 0.,
            "NATIVE_RESUME_CONTEXT_NOT_SUPPORTED")
    require(all(v == asdict(completed)[k] for k, v in asdict(interrupted).items()
                if k not in {"reason", "reobservations"})
            and all(getattr(interrupted, k) is None for k in ("pending_command_id", "pending_primitive_id",
                "pending_target_context_id", "pending_role", "pending_since_s", "resume_phase")),
            "NATIVE_RESUME_STATE_CHANGED")
    require(type(receipt) is dict
            and set(receipt) == {"command_id", "primitive_id", "session_id", "target_context_id",
                                "completed_at_s", "native_verified", "outcome"}
            and receipt["native_verified"] is True and receipt["outcome"] == "COMPLETED"
            and receipt["primitive_id"] == step.primitive.id
            and bool(interrupted.issued_command_ids)
            and receipt["command_id"] == interrupted.action_command_id == interrupted.issued_command_ids[-1]
            and receipt["target_context_id"] == step.primitive.target_context_id
            and receipt["session_id"] == interrupted.session_id
            and type(receipt["completed_at_s"]) in (int, float) and math.isfinite(receipt["completed_at_s"])
            and receipt["completed_at_s"] == interrupted.last_motion_completed_at_s,
            "NATIVE_RESUME_RECEIPT_MISMATCH")
    require(following.primitive.source_context_id == step.primitive.target_context_id,
            "NATIVE_RESUME_NEXT_SOURCE_MISMATCH")
    return replace(current_plan, id=old_plan.id), replace(interrupted, phase=Phase.OBSERVE,
        reobservations=0, reason="EXPLICIT_NATIVE_REVIEW_RECOVERY")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def recover_before_frame(root, chain, command_id, lower_capture_time):
    """Recover exactly one original capture in the bounded C4 execution window.

    ``chain`` must already have passed ``mission_resume.read_chain``. Original
    camera ``frame.received_at`` supplies the reconstructed capture timestamp;
    file mtime never selects a source or refreshes its age. The caller checks
    epoch/map/reference continuity independently before using this Frame.
    """
    root = Path(root)
    require(not root.is_symlink() and root.is_dir() and isinstance(command_id, str) and command_id
            and _number(lower_capture_time), "NATIVE_RESUME_CAPTURE_INTERVAL_INVALID")
    intents = [(i, r) for i, r in enumerate(chain) if r.get("kind") == "mission_primitive_intent"
               and r.get("payload", {}).get("command_id") == command_id]
    require(len(intents) == 1, "NATIVE_RESUME_CAPTURE_INTERVAL_INVALID")
    position, intent = intents[0]
    previous = [r for r in chain[:position] if r.get("kind") == "mission_primitive_complete"]
    require(previous and _number(previous[-1].get("created_at")) and _number(intent.get("created_at")),
            "NATIVE_RESUME_CAPTURE_INTERVAL_INVALID")
    lower = max(lower_capture_time, previous[-1]["created_at"])
    upper = intent["created_at"]
    require(lower < upper, "NATIVE_RESUME_CAPTURE_INTERVAL_INVALID")
    matches = []
    for path in root.glob("camera-metadata-*.private.json"):
        require(not path.is_symlink() and path.stat().st_size <= 65536, "NATIVE_RESUME_CAMERA_METADATA_INVALID")
        try:
            metadata = json.loads(path.read_bytes())
            source = metadata["frame"]
            received = datetime.fromisoformat(source["received_at"].replace("Z", "+00:00"))
            require(received.tzinfo is not None, "NATIVE_RESUME_CAMERA_METADATA_INVALID")
            captured_at = received.timestamp()
            if not lower < captured_at < upper:
                continue
            require(isinstance(source["id"], str) and bool(source["id"])
                    and isinstance(metadata["epoch"], str) and bool(metadata["epoch"])
                    and type(source["sequence"]) is int and source["sequence"] >= 1
                    and isinstance(source["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
                    and source["image_url"] == "/api/v1/live-camera/frames/" + source["id"] + "/image"
                    and type(source["width"]) is int and source["width"] > 0
                    and type(source["height"]) is int and source["height"] > 0,
                    "NATIVE_RESUME_CAMERA_METADATA_INVALID")
            matches.append((path, metadata, captured_at))
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
            require(False, "NATIVE_RESUME_CAMERA_METADATA_INVALID")
    require(len(matches) == 1, "NATIVE_RESUME_BEFORE_IMAGE_NOT_UNIQUE")
    metadata_path, metadata, captured_at = matches[0]
    source = metadata["frame"]
    images = []
    for path in root.glob("camera-original-*.native.jpg"):
        require(not path.is_symlink(), "NATIVE_RESUME_ORIGINAL_IMAGE_INVALID")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() == source["sha256"]:
            require(raw.startswith(b"\xff\xd8") and raw.endswith(b"\xff\xd9"), "NATIVE_RESUME_ORIGINAL_IMAGE_INVALID")
            images.append((path, raw))
    require(len(images) == 1, "NATIVE_RESUME_ORIGINAL_IMAGE_NOT_UNIQUE")
    image_path, raw = images[0]
    frame = Frame(source["id"], metadata["epoch"], source["sequence"], captured_at, source["sha256"], raw)
    evidence = {"command_id": command_id, "lower_capture_time": lower, "dispatch_lower_bound": lower_capture_time,
        "previous_primitive_complete_time": previous[-1]["created_at"], "primitive_intent_time": upper,
        "metadata_path": str(metadata_path), "metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        "image_path": str(image_path), "image_sha256": source["sha256"],
        "frame": frame.metadata(), "capture_time_source": "original_frame.received_at",
        "capture_time_reconstructed": True, "mtime_used": False,
        "metadata_candidates_in_interval": 1, "matching_original_images": 1,
        "original_bytes_preserved": True, "motion_issued": False, "car_verdict_created": False}
    return frame, metadata, evidence
