"""Verified inherited receiver boundary, with exactly one command publication.

Construction imports reviewed code only. It does not connect, query hardware,
restore a profile, clear a hold, or publish a command. The dedicated host owns
the pendant socket; this boundary communicates through its existing mailbox.
"""
from __future__ import annotations

import builtins
import copy
import hashlib
import json
import math
from pathlib import Path
import threading
import time
from types import ModuleType
from typing import Callable

from .gates import GuardError

SOURCE_MANIFEST = Path(__file__).resolve().parents[2] / "docs/data/robot-runtime-source.json"
DEFAULT_RUNTIME = Path(__file__).resolve().parents[2] / "runtime/robot-control/receiver"
MODULE_NAMES = frozenset(("server", "transport", "policy", "submit_pose", "ik", "wrist", "wrist_plan"))


class PrewireRejected(RuntimeError):
    """No command was published, or receiver explicitly rejected it before wire."""


class OutcomeUnknown(RuntimeError):
    """Publication or completion is uncertain. Never resend automatically."""


NOT_COMMITTED_NATIVE_TIMEOUT_CODES = frozenset({
    "PROFILE_NOT_COMMITTED_NATIVE_TIMEOUT", "MOTION_NOT_COMMITTED_NATIVE_TIMEOUT"})


def _native_wait_detail(value):
    """Expose only the reviewed host's bounded no-retry wait classification."""
    if type(value) is not dict or value.get("motion_retried") is not False:
        raise ValueError("Invalid Native wait metadata")
    reason, phase = value.get("reason"), value.get("phase")
    if type(reason) is not str or type(phase) is not str:
        raise ValueError("Invalid Native wait classification")
    if reason == "NATIVE_TELEMETRY_UNAVAILABLE":
        if (set(value) != {"reason", "phase", "error_type", "detail", "failures", "motion_retried"}
                or phase not in {"stationary", "endpoint_after_done", "profile_precommit", "motion_precommit"}
                or type(value["error_type"]) is not str or not 1 <= len(value["error_type"]) <= 64
                or type(value["detail"]) is not str or len(value["detail"]) > 256
                or type(value["failures"]) is not int or value["failures"] < 1):
            raise ValueError("Invalid Native read wait metadata")
    elif reason == "NATIVE_STATIONARITY_PENDING":
        if (set(value) != {"reason", "phase", "speed", "exact_zero_samples_required", "budget_s",
                           "motion_retried", "speed_tolerance_relaxed"}
                or phase != "stationary" or value["speed_tolerance_relaxed"] is not False
                or type(value["exact_zero_samples_required"]) is not int or value["exact_zero_samples_required"] != 2
                or type(value["budget_s"]) not in (float, int) or value["budget_s"] != 8.
                or type(value["speed"]) is not list or len(value["speed"]) != 6
                or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > .1 for v in value["speed"])
                or not any(v != 0 for v in value["speed"])):
            raise ValueError("Invalid Native stationary wait metadata")
    else:
        raise ValueError("Unknown Native wait reason")
    return {"reason": reason, "phase": phase}


def _not_committed_timeout_code(kind, data, identity):
    """Classify exact host evidence without clearing an unknown-publication latch."""
    phase, code = ({"profile_update": ("profile_precommit", "PROFILE_NOT_COMMITTED_NATIVE_TIMEOUT"),
                   "translate": ("motion_precommit", "MOTION_NOT_COMMITTED_NATIVE_TIMEOUT"),
                   "rotate": ("motion_precommit", "MOTION_NOT_COMMITTED_NATIVE_TIMEOUT")}.get(kind, (None, None)))
    if (phase is not None and all(type(data.get(key)) is type(value) and data.get(key) == value
                                for key, value in identity.items())
            and data.get("phase") == phase and data.get("code") == "NATIVE_PRECOMMIT_VERIFICATION_TIMEOUT"
            and data.get("commit_sent") is False and data.get("motion_sent") is False
            and data.get("fresh_connection_required") is True):
        return code
    return None


class _ConfirmedPrewireRejection(PrewireRejected):
    pass


def source_manifest() -> dict:
    return json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))


def verify_runtime(root: Path) -> dict[str, bytes]:
    """Verify every executable byte before importing any inherited code."""
    original = Path(root).absolute()
    if original.is_symlink() or any(parent.is_symlink() for parent in original.parents):
        raise PrewireRejected("ROBOT_RUNTIME_SYMLINK_UNSUPPORTED")
    root = original.resolve()
    manifest = source_manifest()
    verified = {}
    names = dict(manifest["files"])
    for alias, source in manifest["aliases"].items():
        names[alias] = manifest["files"][source]
    for name, record in names.items():
        if Path(name).name != name:
            raise PrewireRejected("ROBOT_RUNTIME_MANIFEST_PATH_INVALID")
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise PrewireRejected("ROBOT_RUNTIME_NOT_INSTALLED: " + name)
        if path.stat().st_size != record["bytes"]:
            raise PrewireRejected("ROBOT_RUNTIME_HASH_MISMATCH: " + name)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise PrewireRejected("ROBOT_RUNTIME_HASH_MISMATCH: " + name)
        verified[name] = data
    return verified


def load_runtime(root: Path) -> dict[str, ModuleType]:
    """Load the exact source with private import names, avoiding app-global policy imports.

    The custom import hook changes module resolution only, never source bytes or
    receiver behavior. Circular policy/wrist imports retain normal Python semantics.
    No unverified local module, startup script or package initializer is executed.
    """
    verified = verify_runtime(root)
    root = Path(root).resolve()
    modules: dict[str, ModuleType] = {}
    loading: set[str] = set()
    complete: set[str] = set()
    ordinary_import = builtins.__import__

    def private_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name in MODULE_NAMES:
            return load(name)
        return ordinary_import(name, globals, locals, fromlist, level)

    def load(name):
        if name in complete or name in loading:
            return modules[name]
        filename = name + ".py"
        if filename not in verified:
            raise PrewireRejected("ROBOT_RUNTIME_MODULE_UNREVIEWED")
        module = ModuleType("_pushpilot_robot_runtime_" + name)
        module.__file__ = str(root / filename)
        module.__package__ = ""
        module.__dict__["__builtins__"] = dict(vars(builtins), __import__=private_import)
        modules[name] = module
        loading.add(name)
        try:
            exec(compile(verified[filename], str(root / filename), "exec"), module.__dict__)
        finally:
            loading.remove(name)
        complete.add(name)
        return module

    for name in sorted(MODULE_NAMES):
        load(name)
    return modules


class LegacyReceiver:
    TERMINAL = {"inspect_current": "ik_result_verified", "inspect_ik": "ik_result_verified",
                "profile_update": "profile_applied_verified", "translate": "motion_endpoint_verified",
                "rotate": "motion_endpoint_verified"}
    OPERATIONS = {"inspect_current": "inspect-current", "inspect_ik": "inspect-ik",
                  "profile_update": "profile-update", "translate": "translate", "rotate": "rotate"}
    BINDING = ("session_id", "seq", "profile_id")

    def __init__(self, root: Path = DEFAULT_RUNTIME):
        self.root = Path(root).resolve()
        self.modules = load_runtime(root)
        self.submit = self.modules["submit_pose"]
        self.policy = self.modules["policy"]
        self.lock_stream = None
        self._execution_lock = threading.Lock()
        self._uncertain = False

    def open(self):
        if self.lock_stream is not None:
            return self
        try:
            import fcntl
        except ImportError as error:
            raise PrewireRejected("ROBOT_CONTROL_REQUIRES_LINUX_FLOCK") from error
        stream = (self.root / "executor-owner.lock").open("a+")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            stream.close()
            raise PrewireRejected("ROBOT_RECEIVER_ALREADY_OWNED")
        self.lock_stream = stream
        return self

    def close(self):
        if self.lock_stream is not None:
            self.lock_stream.close()
            self.lock_stream = None

    def _state(self):
        def read(path):
            if path.is_symlink() or path.stat().st_size > 65536:
                raise ValueError("Invalid receiver metadata file")
            value = self.modules["transport"].strict_json(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Invalid receiver metadata")
            return value
        name = read(self.root / "current_session.json").get("path")
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise ValueError("Invalid receiver session path")
        runs = self.root / "runs"
        run = runs / name
        if runs.is_symlink() or run.is_symlink() or run.resolve().parent != runs.resolve():
            raise ValueError("Receiver session path escape")
        state = read(run / "state.json")
        return run, state

    def snapshot(self) -> dict:
        result = dict(connected=False, idle=False, session_id=None, seq=None, profile_id=None,
                      actual_pose=None, actual_joint=None, profile=None, physical_execution=False,
                      stage=None, state_age_s=None, native_telemetry_available=False, native_telemetry=None,
                      reason="RECEIVER_NOT_CONNECTED")
        try:
            _, state = self._state()
            if state.get("stage") == "closed":
                result["reason"] = "RECEIVER_CLOSED: " + str(state.get("status", "unknown"))[:128]
                return result
            if state.get("schema") != self.policy.SCHEMA:
                raise ValueError("Wrong receiver protocol")
            session = state.get("session_id")
            seq = state.get("seq")
            profile_id = state.get("profile_id")
            if (not isinstance(session, str) or len(session) != 32 or
                any(c not in "0123456789abcdef" for c in session) or type(seq) is not int or seq < 1 or
                not isinstance(profile_id, str) or len(profile_id) != 64 or
                any(c not in "0123456789abcdef" for c in profile_id)):
                raise ValueError("Invalid receiver identity")
            stamp = state.get("updated_monotonic_ns")
            age_ns = time.monotonic_ns() - stamp if type(stamp) is int else None
            if age_ns is None or not 0 <= age_ns <= 5_000_000_000:
                result["reason"] = "RECEIVER_STATE_STALE"
                return result
            self.policy.vector(state.get("actual_pose"), 6)
            self.policy.vector(state.get("actual_joint"), 6)
            if type(state.get("physical_execution")) is not bool:
                raise ValueError("Invalid receiver mode")
            profile = state.get("profile")
            self.policy.valid(profile, state["physical_execution"])
            if self.policy.digest(profile) != profile_id:
                raise ValueError("Receiver profile digest mismatch")
            self.policy.inside(profile, state["actual_pose"])
            self.policy.inside(profile, state["planned_pose"])
            self.policy.orientation(profile, state["actual_pose"])
            self.policy.orientation(profile, state["planned_pose"])
            stage = state.get("stage")
            if type(stage) is not str or stage not in {"idle", "native_wait", "inspecting_ik", "updating_profile",
                    "validating", "moving", "checking_target", "finished"}:
                raise ValueError("Unknown receiver stage")
            available = state.get("native_telemetry_available", stage != "native_wait")
            if type(available) is not bool:
                raise ValueError("Invalid Native telemetry availability")
            detail = None
            if stage == "native_wait":
                if available or state["physical_execution"] is not True or state.get("status") is not None:
                    raise ValueError("Invalid Native wait state")
                detail = _native_wait_detail(state.get("native_telemetry"))
            elif not available or state.get("native_telemetry") is not None:
                raise ValueError("Inconsistent Native telemetry state")
            result.update(connected=True, idle=stage == "idle", session_id=session,
                          seq=seq, profile_id=profile_id, actual_pose=state["actual_pose"],
                          actual_joint=state["actual_joint"], physical_execution=state["physical_execution"],
                          profile=copy.deepcopy(profile), stage=stage, state_age_s=age_ns / 1_000_000_000,
                          native_telemetry_available=available, native_telemetry=detail,
                          reason=("RECEIVER_NATIVE_WAIT" if stage == "native_wait" else
                                  "RECEIVER_IDLE" if stage == "idle" else "RECEIVER_BUSY"))
            if self._uncertain:
                result["reason"] = "RECEIVER_RECONCILIATION_REQUIRED"
            elif (self.root / "executor-hold.json").exists():
                result["reason"] = "RECEIVER_OPERATOR_HOLD"
            return result
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            return result

    def reconcile(self, expected_receiver: dict) -> dict:
        """Clear only the in-memory ambiguity latch after explicit audited reconciliation.

        The caller must durably record operator inspection before calling this.
        Fresh idle state is checked independently of the old command outcome; it
        does not retroactively mark a physical motion or vehicle result complete.
        No request, profile, pending file or hold is replayed or removed.
        """
        if not self._execution_lock.acquire(blocking=False):
            raise PrewireRejected("ROBOT_COMMAND_ALREADY_EXECUTING")
        try:
            if self.lock_stream is None:
                raise PrewireRejected("ROBOT_OWNER_LOCK_REQUIRED")
            if (not isinstance(expected_receiver, dict) or
                    any(key not in expected_receiver for key in self.BINDING) or
                    type(expected_receiver["seq"]) is not int):
                raise PrewireRejected("RECONCILIATION_BINDING_REQUIRED")
            if (self.root / "executor-hold.json").exists():
                raise PrewireRejected("RECEIVER_OPERATOR_HOLD")
            current = self.snapshot()
            if (not current["connected"] or not current["idle"] or not current["physical_execution"] or
                    any(current.get(key) != expected_receiver[key] for key in self.BINDING)):
                raise PrewireRejected("RECONCILIATION_REQUIRES_FRESH_BOUND_IDLE")
            try:
                run, final = self.submit.session_state()
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                raise PrewireRejected("RECONCILIATION_STATE_UNAVAILABLE") from error
            if (not final.get("physical_execution") or final.get("stage") != "idle" or
                    any(final.get(key) != expected_receiver[key] for key in self.BINDING) or
                    (run / "command.json").exists()):
                raise PrewireRejected("RECONCILIATION_BINDING_CHANGED_OR_COMMAND_PENDING")
            self._uncertain = False
            return {"reconciled": True, **{key: final[key] for key in self.BINDING}, "command_replayed": False}
        finally:
            self._execution_lock.release()

    def execute(self, command: dict, on_event: Callable[[str, dict], None]) -> dict:
        if not self._execution_lock.acquire(blocking=False):
            raise PrewireRejected("ROBOT_COMMAND_ALREADY_EXECUTING")
        try:
            return self._execute(command, on_event)
        finally:
            self._execution_lock.release()

    def _execute(self, command: dict, on_event: Callable[[str, dict], None]) -> dict:
        if self.lock_stream is None:
            raise PrewireRejected("ROBOT_OWNER_LOCK_REQUIRED")
        if self._uncertain:
            raise OutcomeUnknown("ROBOT_RECONCILIATION_REQUIRED_NO_RESEND")
        if (self.root / "executor-hold.json").exists():
            raise PrewireRejected("RECEIVER_OPERATOR_HOLD")
        events = None
        try:
            kind = command["kind"]
            operation = self.OPERATIONS[kind]
            timeout = command.get("timeout_seconds", 180)
            if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 610:
                raise ValueError("Invalid completion deadline")
            expected = command["expected_receiver"]
            if (not isinstance(expected, dict) or any(key not in expected for key in self.BINDING) or
                    type(expected["seq"]) is not int):
                raise ValueError("Expected receiver identity required")
            run, state = self.submit.session_state()
            if not state.get("physical_execution"):
                raise ValueError("Physical receiver not enabled")
            if any(state.get(key) != expected[key] for key in self.BINDING):
                raise ValueError("Receiver binding changed before preparation")
            prepared_run, prepared_state, wire_command = self.submit.prepare(
                operation, command.get("target"), command.get("edge_id"), command.get("profile"), False)
            if prepared_run != run or any(prepared_state.get(key) != expected[key] for key in self.BINDING):
                raise ValueError("Receiver binding changed during preparation")
            events = (run / "events.jsonl").open("r", encoding="utf-8")
            events.seek(0, 2)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
            if events is not None:
                events.close()
            raise PrewireRejected(str(error)) from error
        # Recording intent is a prerequisite. A failure here proves no publication.
        try:
            on_event("publication_intent", {"wire_command": copy.deepcopy(wire_command)})
        except GuardError:
            events.close()
            raise
        except BaseException:
            events.close()
            raise PrewireRejected("COMMAND_INTENT_NOT_RECORDED")
        try:
            # From this point any exception can leave a published command behind.
            self.submit.publish_once(run, prepared_state, wire_command)
            identity = {key: wire_command[key] for key in ("request_id", "session_id", "seq", "profile_id", "command_digest")}
            on_event("published", identity)
            deadline = time.monotonic() + timeout
            partial = ""
            terminal = None
            commit_seen = False
            not_committed_code = None
            last_read_failure = None
            while time.monotonic() < deadline:
                try:
                    partial += events.read()
                    if len(partial) > 1048576:
                        raise OutcomeUnknown("RECEIVER_EVENT_BUFFER_OVERSIZE")
                    while "\n" in partial:
                        line, partial = partial.split("\n", 1)
                        if len(line) > 262144:
                            raise OutcomeUnknown("RECEIVER_EVENT_OVERSIZE")
                        try:
                            event = self.modules["transport"].strict_json(line)
                        except (ValueError, TypeError, RecursionError) as error:
                            raise OutcomeUnknown("RECEIVER_EVENT_LOG_CORRUPT") from error
                        data = event.get("data", {})
                        # Raw wire packets intentionally omit request_id for
                        # target motions. Never overlook a matching GO/commit
                        # merely because it cannot pass the lifecycle filter.
                        if (isinstance(data, dict) and event.get("kind") == "tx_intent"
                                and data.get("type") in {"go", "profile_commit"}
                                and all(data.get(key) == identity[key] for key in
                                        ("session_id", "seq", "profile_id", "command_digest"))):
                            commit_seen = True
                        if not isinstance(data, dict) or data.get("request_id") != wire_command["request_id"]:
                            continue
                        if any(data.get(key) != identity[key] for key in ("session_id", "seq")):
                            raise OutcomeUnknown("RECEIVER_EVENT_BINDING_MISMATCH")
                        event_kind = event.get("kind")
                        if event_kind == "command_rejected_before_wire":
                            on_event("rejected_before_wire", data)
                            raise _ConfirmedPrewireRejection("RECEIVER_REJECTED_BEFORE_WIRE: " + str(data.get("reason")))
                        if data.get("command_digest") != wire_command["command_digest"]:
                            raise OutcomeUnknown("RECEIVER_EVENT_DIGEST_MISMATCH")
                        if event_kind in {"motion_commit_intent", "motion_entering_reported", "motion_done_reported",
                                          "motion_endpoint_verified", "profile_commit_intent", "profile_applied_verified"}:
                            commit_seen = True
                        if event_kind == "command_not_committed":
                            not_committed_code = _not_committed_timeout_code(kind, data, identity)
                        on_event("wire_" + str(event_kind), data)
                        if event_kind == self.TERMINAL[kind]:
                            if kind.startswith("inspect") and (data.get("status") != "ok" or data.get("motion_issued") is not False):
                                raise OutcomeUnknown("RECEIVER_INSPECTION_NOT_VERIFIED")
                            terminal = event
                    if not_committed_code is not None and not commit_seen:
                        # This diagnosis is NOT a prewire rejection or replay
                        # authority. A published command still needs explicit
                        # reconciliation and a fresh receiver connection.
                        raise OutcomeUnknown(not_committed_code)
                    current_run, current = self._state()
                    if current_run != run or current.get("stage") == "closed":
                        raise OutcomeUnknown("RECEIVER_SESSION_CLOSED_OR_REPLACED")
                    if current.get("session_id") != expected["session_id"]:
                        raise OutcomeUnknown("RECEIVER_SESSION_CHANGED")
                    if current.get("stage") == "idle":
                        if terminal is not None:
                            if current.get("seq") != wire_command["seq"] + 1:
                                raise OutcomeUnknown("RECEIVER_SEQUENCE_MISMATCH")
                            expected_pid = wire_command.get("new_profile_id", wire_command["profile_id"])
                            if current.get("profile_id") != expected_pid:
                                raise OutcomeUnknown("RECEIVER_PROFILE_MISMATCH")
                            on_event("verified", terminal)
                            return terminal
                        if current.get("seq", 0) > wire_command["seq"] + 1:
                            raise OutcomeUnknown("RECEIVER_CONCURRENT_COMMAND")
                    last_read_failure = None
                except (OSError, json.JSONDecodeError, UnicodeError) as error:
                    # Only metadata reads are retried; publication never repeats.
                    now = time.monotonic()
                    if last_read_failure is None:
                        last_read_failure = now
                    if now - last_read_failure >= min(2, timeout):
                        raise OutcomeUnknown("RECEIVER_METADATA_UNREADABLE") from error
                time.sleep(.1)
            raise OutcomeUnknown("RECEIVER_COMPLETION_TIMEOUT_NO_RETRY")
        except _ConfirmedPrewireRejection:
            raise
        except BaseException as error:
            self._uncertain = True
            if isinstance(error, OutcomeUnknown):
                raise
            raise OutcomeUnknown("COMMAND_OUTCOME_UNKNOWN_NO_RESEND: " + type(error).__name__) from error
        finally:
            events.close()
