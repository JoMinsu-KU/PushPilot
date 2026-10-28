"""Opt-in dedicated host for the unchanged persistent Rodi receiver.

The listener survives a failed session and waits for a new manual PLAY. It never
reconnects to the pendant, restores mailboxes or automatically resends motion.
Stopping this host is not a robot stop. HTTP, MUSE and vision run independently.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.robot_control.legacy import DEFAULT_RUNTIME, PrewireRejected, load_runtime


def read_profile(path, modules, motion):
    path = Path(path).absolute()
    if (path.is_symlink() or any(parent.is_symlink() for parent in path.parents) or
            not path.is_file() or path.stat().st_size > 65536):
        raise ValueError("A bounded explicit reviewed profile file is required.")
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("A bounded explicit reviewed profile file is required.")
    profile = modules["transport"].strict_json(raw.decode("utf-8-sig"))
    modules["policy"].valid(profile, motion)
    return raw, profile


def _waiting_profile_result(error=None):
    return {"source": "rodi_host", "status": "waiting_reviewed_profile", "ready": False,
            "listening": False, "receiver_session_active": False,
            "physical_execution": False, "begin_sent": False, "motion_issued": False,
            "mailbox_consumed": False, "automatic_retry": False,
            "waiting_for_manual_play": False, "server_exit_is_robot_stop": False,
            "profile_error_type": type(error).__name__ if error is not None else None}


def _host_status(runtime, modules, value):
    """Best-effort diagnostics never replace a receiver session or its mailbox."""
    try:
        path = Path(runtime) / "host-status.json"
        if not path.is_symlink():
            modules["server"].atomic_json(path, {**value, "updated_monotonic_ns": time.monotonic_ns()})
    except Exception:
        pass


def capture_profile_wait(connection, peer, runtime, modules, profile_error):
    """Explicit diagnostic only: read one HELLO, then close without BEGIN.

    Production profile waiting never calls this helper or opens a listener.
    Keep the historical diagnostic available without presenting a captured
    HELLO as a persistent receiver session. No substitute profile is invented.
    """
    result = _waiting_profile_result(profile_error)
    result["waiting_for_manual_play"] = True
    journal = None
    try:
        g = modules["policy"]
        g.require(peer[0] == "192.168.10.10", "Unexpected pendant peer")
        name = "profile-wait-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        journal = modules["transport"].Journal(Path(runtime) / "diagnostics" / name)
        packet = modules["transport"].Wire(connection, journal).receive(seconds=3)
        g.require(type(packet) is dict, "HELLO object required")
        for key, expected in {"schema": g.SCHEMA, "type": "hello", "robot_id": "HCR1",
                              "revision": g.REVISION, "build": "poc-persistent-v1"}.items():
            g.require(packet.get(key) == expected, "Unexpected HELLO " + key)
        g.require(packet.get("local_motion_enabled") is True, "Installed online receiver flag required")
        for key in ("origin", "actual_joint", "actual_speed"):
            g.vector(packet.get(key), 6)
        capabilities = packet.get("capabilities", [])
        g.require(type(capabilities) is list and len(capabilities) <= 8 and all(g.text(c) for c in capabilities),
                  "Invalid HELLO capabilities")
        result.update(hello_received=True, receiver_build=packet["build"],
                      telemetry_source="pendant_hello_unqualified", run=name)
        journal.event("profile_wait_hello_observed", result)
    except Exception as error:
        result.update(hello_received=False, diagnostic_error_type=type(error).__name__)
    finally:
        if journal is not None:
            try:
                journal.event("profile_wait_closed_without_begin", result)
            except Exception as error:
                result["diagnostic_error_type"] = type(error).__name__
            try:
                journal.close()
            except Exception as error:
                result["diagnostic_error_type"] = type(error).__name__
        _host_status(runtime, modules, result)
    return result


def run_session(connection, peer, runtime, profile_path, modules, motion=True):
    """One existing exchange; catches session errors without repeating commands."""
    server = modules["server"]
    transport = modules["transport"]
    g = modules["policy"]
    name = "session-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    path = Path(runtime) / "runs" / name
    journal = transport.Journal(path)
    report = dict(schema=g.SCHEMA, status="preparing", completed=0, in_flight=None,
                  motion_permission_may_have_been_sent=False, physical_execution=motion, errors=[])
    try:
        g.require(peer[0] == "192.168.10.10", "Unexpected pendant peer")
        raw, profile = read_profile(profile_path, modules, motion)
        report.update(profile=profile, profile_sha256=hashlib.sha256(raw).hexdigest())
        server.environment_check(journal)
        server.legacy_receiver_absent(journal)
        native = transport.Native(journal)

        def guard(expected, programs=(2,)):
            server.legacy_receiver_absent(journal)
            return transport.read_stationary(native, expected, programs, motion)

        # The pendant has already entered its script before opening this socket.
        # The original host's (1, 6) pre-PLAY check ran BEFORE accept(); here the
        # accepted connection must be checked as running program state 2.
        row = guard(profile["expected_start_tcp_mm_deg"], (2,))
        g.near(row["joint"], profile["expected_start_joint_deg"], .5)

        def publish(stage, sid, seq, pid, actual, planned, joints, active_profile, capabilities, actual_joint):
            server.atomic_json(path / "state.json", dict(schema=g.SCHEMA, stage=stage, session_id=sid, seq=seq,
                profile_id=pid, profile=active_profile, actual_pose=actual, planned_pose=planned,
                planned_joint=joints, actual_joint=actual_joint, capabilities=capabilities,
                ik_baseline_verified=report.get("ik_baseline_verified", False),
                rejected_requests=report.get("rejected_requests", 0),
                last_rejected_request=report.get("last_rejected_request"), physical_execution=motion,
                updated_monotonic_ns=time.monotonic_ns()))
            _host_status(runtime, modules, {"source": "rodi_host", "status": stage,
                "ready": stage == "idle", "receiver_session_active": True,
                "physical_execution": motion, "automatic_retry": False,
                "server_exit_is_robot_stop": False})

        server.atomic_json(Path(runtime) / "current_session.json", {"path": name})
        server.exchange(transport.Wire(connection, journal), guard, profile, motion, report, publish,
                        path / "command.json", journal.event,
                        settle=lambda endpoint: transport.wait_endpoint_settled(native, endpoint, motion))
    except Exception as error:
        report["errors"].append(type(error).__name__ + ": " + str(error)[:512])
        report["status"] = ("outcome_unknown_check_pendant" if report["motion_permission_may_have_been_sent"] else
                            "profile_outcome_unknown_no_targets" if report.get("profile_commit_may_have_been_sent") else "blocked")
    except BaseException:
        report["status"] = "outcome_unknown_check_pendant" if report["motion_permission_may_have_been_sent"] else "host_interrupted"
        raise
    finally:
        server.atomic_json(path / "state.json", dict(stage="closed", status=report["status"],
                                                    updated_monotonic_ns=time.monotonic_ns()))
        _host_status(runtime, modules, {"source": "rodi_host", "status": report["status"],
            "ready": False, "receiver_session_active": False, "automatic_retry": False,
            "waiting_for_manual_play": True, "server_exit_is_robot_stop": False})
        journal.event("pose_session_closed", dict(session_id=report.get("session_id"), status=report["status"],
            in_flight=report.get("in_flight"), active_command=report.get("active_command"), errors=report["errors"]))
        journal.event("summary", report)
        journal.close()
        server.atomic_json(path / "summary.json", report)
    return {"status": report["status"], "run": name, "automatic_retry": False,
            "ready": False, "receiver_session_active": False,
            "waiting_for_manual_play": True, "server_exit_is_robot_stop": False}


def _current_pointer(runtime):
    """Best-effort pointer inspection; never opens a historical command file."""
    try:
        path = Path(runtime) / "current_session.json"
        if path.is_symlink() or path.stat().st_size > 65536:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        name = value.get("path")
        if not isinstance(name, str) or not name or Path(name).name != name:
            return None
        return name
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _session_unavailable(runtime, previous_pointer, modules, error):
    """Contain finalization/disk failures without representing them as a robot stop.

    If the connection selected a fresh run, its status may be marked closed. Old
    runs and all pending mailboxes remain untouched. Invalidate only the current
    pointer so a recently cached idle record cannot admit another command.
    Failure to write diagnostic metadata must not terminate the listener.
    """
    runtime = Path(runtime)
    result = {"source": "rodi_host", "status": "outcome_unknown_check_pendant",
              "result_available": False, "error_type": type(error).__name__,
              "automatic_retry": False, "waiting_for_manual_play": True,
              "operator_reconciliation_required": True, "server_exit_is_robot_stop": False}
    current = _current_pointer(runtime)
    atomic = modules["server"].atomic_json
    stamp = time.monotonic_ns()
    try:
        if current is not None and current != previous_pointer:
            runs = runtime / "runs"
            run = runs / current
            if (not runs.is_symlink() and not run.is_symlink() and run.is_dir() and
                    run.resolve().parent == runs.resolve()):
                atomic(run / "state.json", {"source": "rodi_host", "stage": "closed",
                    "status": "outcome_unknown_check_pendant", "updated_monotonic_ns": stamp})
    except Exception:
        pass
    for path, value in (
        (runtime / "current_session.json", {"path": None, "source": "rodi_host",
             "status": "unavailable", "updated_monotonic_ns": stamp}),
        (runtime / "host-status.json", {**result, "updated_monotonic_ns": stamp}),
    ):
        try:
            if not path.is_symlink():
                atomic(path, value)
        except Exception:
            pass
    return result


def wait_for_reviewed_profile(runtime, profile, modules):
    """Poll explicit local configuration before opening any pendant socket.

    A missing or malformed profile must never accept HELLO and strand the
    unchanged pendant without BEGIN. Waiting performs no Native/wire calls or
    session/mailbox reads. KeyboardInterrupt and SystemExit are not contained.
    """
    previous_error_type = None
    while True:
        try:
            read_profile(profile, modules, True)
            return
        except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError, RecursionError) as error:
            _host_status(runtime, modules, _waiting_profile_result(error))
            error_type = type(error).__name__
            if error_type != previous_error_type:
                try:
                    print("RODI_HOST_WAITING_REVIEWED_PROFILE; not listening; prepare the explicit reviewed profile before manual PLAY", flush=True)
                except OSError:
                    pass
                previous_error_type = error_type
            time.sleep(1)


def serve(runtime, profile, modules, *, wait_for_profile=False):
    """One listener, fresh session per manual connection, no automatic motion."""
    import fcntl
    runtime = Path(runtime)
    with (runtime / "receiver-host.lock").open("a+") as ownership:
        fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if wait_for_profile:
            wait_for_reviewed_profile(runtime, profile, modules)
        else:
            read_profile(profile, modules, True)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("192.168.10.31", 19507))
            listener.listen(1)
            _host_status(runtime, modules, {"source": "rodi_host", "status": "waiting_for_manual_play",
                "ready": False, "listening": True, "receiver_session_active": False,
                "begin_sent": False, "motion_issued": False, "mailbox_consumed": False,
                "automatic_retry": False, "waiting_for_manual_play": True,
                "server_exit_is_robot_stop": False})
            print("RODI_HOST_WAITING_FOR_MANUAL_PLAY; no replay; server exit is NOT robot stop", flush=True)
            while True:
                connection, peer = listener.accept()
                previous = _current_pointer(runtime)
                try:
                    with connection:
                        result = run_session(connection, peer, runtime, profile, modules)
                except Exception as error:
                    # Includes Journal creation, exchange finalization and socket
                    # close errors. KeyboardInterrupt/SystemExit still exit.
                    result = _session_unavailable(runtime, previous, modules, error)
                try:
                    print(json.dumps(result), flush=True)
                except OSError:
                    # A closed log pipe must not turn a session exception into a
                    # listener shutdown. No successful persistence is claimed.
                    pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--profile", type=Path, required=True, help="New reviewed local profile; historical profiles are never restored.")
    parser.add_argument("--listen", action="store_true", help="Explicitly bind the GX10 pendant listener.")
    parser.add_argument("--motion", action="store_true", help="Match the installed online script motion flag; does not publish a target.")
    parser.add_argument("--wait-for-profile", action="store_true",
                        help="Wait without opening a pendant listener until the explicit reviewed profile is valid, then use the normal persistent session protocol.")
    args = parser.parse_args(argv)
    if args.listen != args.motion:
        parser.error("Network mode requires both --listen and --motion.")
    if args.wait_for_profile and not args.listen:
        parser.error("--wait-for-profile requires both --listen and --motion.")
    try:
        modules = load_runtime(args.runtime)
        if not args.wait_for_profile:
            read_profile(args.profile, modules, args.motion)
        if not args.listen:
            print("OFFLINE_PROFILE_VALID; no network, hardware access or commands")
            return 0
        if args.wait_for_profile:
            serve(args.runtime, args.profile, modules, wait_for_profile=True)
        else:
            serve(args.runtime, args.profile, modules)
    except KeyboardInterrupt:
        print("RODI_HOST_EXITED; server exit is NOT robot stop", file=sys.stderr)
        return 130
    except (OSError, ValueError, PrewireRejected, ImportError) as error:
        print("RODI_HOST_BLOCKED: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
