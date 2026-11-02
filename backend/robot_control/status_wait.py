"""Read-only waiting for an explicitly published, fresh Native recovery.

Waiting never supplies stationary evidence. The caller still obtains its normal
fresh independent proof after this helper returns an actual idle publication.
"""
from copy import deepcopy
import math
import time

from .taught_executor import ExecutionBlocked, _require


_WAIT_REASONS = {"NATIVE_TELEMETRY_UNAVAILABLE", "NATIVE_STATIONARITY_PENDING"}
_WAIT_PHASES = {"stationary", "endpoint_after_done", "profile_precommit", "motion_precommit"}
_SCOPES = {"local_base_commissioning", "local_contact_commissioning", "local_contact_turn_commissioning"}


def _held(status):
    if not isinstance(status, dict) or not isinstance(status.get("receiver"), dict):
        return False
    receiver = status["receiver"]
    return (status.get("hold") is True and status.get("armed") is False
            and status.get("active_commands") == [] and receiver.get("connected") is True
            and receiver.get("physical_execution") is True and not receiver.get("profile_pending")
            and receiver.get("reason") not in {"RECEIVER_RECONCILIATION_REQUIRED", "RECEIVER_OPERATOR_HOLD"})


def _fresh(receiver):
    age = receiver.get("state_age_s")
    # LegacyReceiver sets connected=True only after checking the original
    # monotonic stamp. New wait publications must also expose that source age.
    return type(age) in (int, float) and math.isfinite(age) and 0 <= age <= 5


def native_wait_eligible(status):
    if not isinstance(status, dict) or not _held(status):
        return False
    receiver = status.get("receiver", {})
    detail = receiver.get("native_telemetry")
    return (status.get("mode") == "physical_commissioning" and status.get("hardware_connected") is True
            and receiver.get("idle") is False and receiver.get("stage") == "native_wait"
            and receiver.get("native_telemetry_available") is False
            and receiver.get("reason") == "RECEIVER_NATIVE_WAIT" and _fresh(receiver)
            and isinstance(detail, dict) and set(detail) == {"reason", "phase"}
            and detail.get("reason") in _WAIT_REASONS and detail.get("phase") in _WAIT_PHASES
            and (detail["reason"] != "NATIVE_STATIONARITY_PENDING" or detail["phase"] == "stationary"))


def require_idle_status(status):
    receiver = status.get("receiver", {}) if isinstance(status, dict) else {}
    _require(isinstance(status, dict) and _held(status) and receiver.get("idle") is True
             and receiver.get("reason") in (None, "RECEIVER_IDLE")
             and ("stage" not in receiver or receiver["stage"] == "idle")
             and ("native_telemetry_available" not in receiver or receiver["native_telemetry_available"] is True)
             and receiver.get("native_telemetry") is None
             and ("state_age_s" not in receiver or _fresh(receiver)),
             "PHYSICAL_STATUS_REQUIRED", "Require the actual held, disarmed physical service and fresh idle receiver.")
    return status


def stationary_status_binding(status):
    _require(isinstance(status, dict) and isinstance(status.get("receiver"), dict),
             "PHYSICAL_STATUS_REQUIRED", "Require an actual receiver status object.")
    receiver, installation = status.get("receiver", {}), status.get("installation", {})
    vectors = [receiver.get("actual_pose"), receiver.get("actual_joint")]
    _require(isinstance(installation, dict) and installation.get("scope") in _SCOPES
             and isinstance(installation.get("installation_id"), str) and installation["installation_id"]
             and isinstance(receiver.get("profile"), dict)
             and all(isinstance(receiver.get(key), str) and receiver[key] for key in ("session_id", "profile_id"))
             and type(receiver.get("seq")) is int and receiver["seq"] >= 1
             and all(isinstance(v, (list, tuple)) and len(v) == 6
                     and all(type(x) in (int, float) and math.isfinite(x) for x in v) for v in vectors),
             "PHYSICAL_STATUS_REQUIRED", "A Native wait requires the complete current receiver and installation baseline.")
    return deepcopy((receiver["session_id"], receiver["seq"], receiver["profile_id"],
                     tuple(receiver["actual_pose"]), receiver["profile"], installation,
                     tuple(receiver["actual_joint"])))


def require_same_stationary_status(before, after):
    baseline, current = stationary_status_binding(before), stationary_status_binding(after)
    # The existing independent-proof confirmation still handles a one-register
    # joint publication crossing. Never accumulate this allowance across polls.
    _require(baseline[:-1] == current[:-1]
             and all(abs(a-b) <= .100000001 for a, b in zip(baseline[-1], current[-1])),
             "NATIVE_BASELINE_CHANGED", "Receiver identity, pose, profile or installation changed during Native recovery.")


def wait_for_stationary_status(get_status, journal=None, stop_check=None, *, timeout_s=120., poll_s=.2,
                               monotonic=time.monotonic, sleep=time.sleep, validate_status=None,
                               initial_status=None, expected_status=None, on_wait=None):
    """Wait only for fresh explicit Native recovery, issuing GETs and no commands.

    ``None`` is an explicit execution policy to keep waiting while the source
    stays fresh and exactly bound. Readiness callers should use a single read.
    ``validate_status`` may retain the caller's full profile/tool validation;
    profile preparation intentionally validates its handoff separately.
    """
    if (timeout_s is not None and (type(timeout_s) not in (int, float)
            or not math.isfinite(timeout_s) or timeout_s < 0)) or (type(poll_s) not in (int, float)
            or not math.isfinite(poll_s) or not .01 <= poll_s <= 1):
        raise ValueError("Use a nonnegative finite wait or explicit None, and a short polling interval.")
    started, baseline, waiting, last_log = monotonic(), None, False, None
    pending = initial_status
    def log(kind, status, **extra):
        if journal is not None:
            receiver = status.get("receiver", {}) if isinstance(status, dict) else {}
            if not isinstance(receiver, dict):
                receiver = {}
            journal.append(kind, {key: receiver.get(key) for key in ("session_id", "seq", "profile_id")}
                | {"elapsed_s": max(0., monotonic()-started), "timeout_s": timeout_s,
                   "commands_issued": 0, "stationary_evidence_reused": False, **extra})
    status = {}
    try:
        while True:
            if stop_check is not None:
                stop_check()
            status = get_status() if pending is None else pending
            pending = None
            if stop_check is not None:
                stop_check()
            if validate_status is not None:
                validate_status(status)
            _require(isinstance(status, dict) and _held(status), "PHYSICAL_STATUS_REQUIRED",
                     "A Native wait must remain held, disarmed, connected and free of active commands.")
            if expected_status is not None:
                require_same_stationary_status(expected_status, status)
            if baseline is not None:
                require_same_stationary_status(baseline, status)
            if waiting and timeout_s is not None and monotonic()-started >= timeout_s:
                raise ExecutionBlocked("PHYSICAL_STATUS_WAIT_TIMEOUT", "Fresh bound Native recovery did not finish within the configured wait.")
            if status["receiver"].get("idle") is True:
                require_idle_status(status)
                if waiting:
                    log("physical_status_wait_completed", status)
                return status
            _require(native_wait_eligible(status), "PHYSICAL_STATUS_REQUIRED",
                     "Only an explicit fresh Native telemetry recovery may be waited through.")
            if baseline is None:
                stationary_status_binding(status)
                baseline = deepcopy(status)
            if on_wait is not None:
                on_wait()
            if not waiting:
                waiting = True
                log("physical_status_wait_started", status, native_telemetry=status["receiver"]["native_telemetry"])
                last_log = monotonic()
            if timeout_s is not None and monotonic()-started >= timeout_s:
                raise ExecutionBlocked("PHYSICAL_STATUS_WAIT_TIMEOUT", "Fresh bound Native recovery did not finish within the configured wait.")
            if monotonic()-last_log >= 5:
                log("physical_status_wait_progress", status, native_telemetry=status["receiver"]["native_telemetry"])
                last_log = monotonic()
            sleep(poll_s if timeout_s is None else min(poll_s, max(0., timeout_s-(monotonic()-started))))
    except Exception as error:
        if waiting:
            log("physical_status_wait_failed", status, code=getattr(error, "code", type(error).__name__))
        raise
