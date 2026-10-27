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
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("A bounded explicit reviewed profile file is required.")
    raw = path.read_bytes()
    profile = modules["transport"].strict_json(raw.decode("utf-8-sig"))
    modules["policy"].valid(profile, motion)
    return raw, profile


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
        journal.event("pose_session_closed", dict(session_id=report.get("session_id"), status=report["status"],
            in_flight=report.get("in_flight"), active_command=report.get("active_command"), errors=report["errors"]))
        journal.event("summary", report)
        journal.close()
        server.atomic_json(path / "summary.json", report)
    return {"status": report["status"], "run": name, "automatic_retry": False,
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


def serve(runtime, profile, modules):
    """One listener, fresh session per manual connection, no automatic motion."""
    import fcntl
    runtime = Path(runtime)
    with (runtime / "receiver-host.lock").open("a+") as ownership:
        fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("192.168.10.31", 19507))
            listener.listen(1)
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
    args = parser.parse_args(argv)
    if args.listen != args.motion:
        parser.error("Network mode requires both --listen and --motion.")
    try:
        modules = load_runtime(args.runtime)
        read_profile(args.profile, modules, args.motion)
        if not args.listen:
            print("OFFLINE_PROFILE_VALID; no network, hardware access or commands")
            return 0
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
