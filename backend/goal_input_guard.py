"""Read only the coordinator's local state before accepting new spoken intent."""
from __future__ import annotations

from backend.voice import VoiceError


async def require_voice_preparation(physical) -> None:
    """Never wait for Native IO, acquire hardware ownership or clear a mission.

    Callers run on the coordinator's event loop. A busy lock is an immediate
    rejection; the short critical section copies local state only. No lock is
    retained during upload, transcription or plan inference.
    """
    if physical is None:
        return  # Simulation-only embedding without a physical coordinator.
    try:
        lock = physical.lock
        if lock.locked():
            raise VoiceError(409, "Robot preparation is changing. Wait for a fresh status before recording a goal.",
                             "VOICE_PHYSICAL_STATUS_REQUIRED")
        async with lock:
            snapshot = physical.snapshot()
            task = getattr(physical, "task", None)
            running = task is not None and not task.done()
        if (not isinstance(snapshot, dict) or type(snapshot.get("enabled")) is not bool
                or "mission_id" not in snapshot or not isinstance(snapshot.get("state"), str)):
            raise ValueError("Physical snapshot is unavailable")
    except VoiceError:
        raise
    except Exception:
        raise VoiceError(409, "Robot preparation cannot be confirmed. Refresh its status before recording a goal.",
                         "VOICE_PHYSICAL_STATUS_REQUIRED") from None
    if (running or snapshot["mission_id"] is not None or snapshot.get("error")
            or snapshot["state"] not in {"READY", "DISABLED"}
            or snapshot["enabled"] and snapshot["state"] != "READY"):
        raise VoiceError(409, "A robot mission is active or requires reconciliation. Complete or retire it before submitting a new spoken goal.",
                         "VOICE_PHYSICAL_MISSION_ACTIVE")
