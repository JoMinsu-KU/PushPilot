"""Equipment-free regression checks for the inherited runtime boundary."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.robot_control import legacy
from backend.robot_control.gates import GuardError
from tools import install_robot_runtime
from tools import serve_rodi_host


SID = "a" * 32
PID = "b" * 64
RID = "c" * 32
DIGEST = "d" * 64


class RuntimeFixture:
    def __init__(self, directory):
        self.package = Path(directory) / "handoff"
        self.destination = Path(directory) / "runtime"
        self.source = self.package / "current/deployed/robot/hcr1-pose-receiver"
        self.source.mkdir(parents=True)
        policy = ('import wrist\nimport hashlib\nimport json\nSCHEMA = "pushpilot.hcr1-pose.experimental-v1"\n'
            'def vector(value, size):\n    if not isinstance(value, list) or len(value) != size: raise ValueError("Invalid vector")\n'
            'def valid(profile, motion=False):\n    if not isinstance(profile, dict) or profile.get("fixture") is not True: raise ValueError("Invalid profile")\n'
            'def digest(profile):\n    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()\n'
            'def inside(profile, pose):\n    vector(pose, 6)\n'
            'def orientation(profile, pose):\n    vector(pose, 6)\n    return "fixture"\n')
        sources = {name + ".py": (policy if name == "policy" else
                   'import policy\n' if name in ("wrist", "ik") else
                   'import json\nstrict_json = json.loads\n' if name == "transport" else "REVIEWED = True\n").encode()
                   for name in legacy.MODULE_NAMES}
        sources["hcr1_pose_receiver.stable-v1-online.script"] = b"// fixture only, never executed\n"
        self.manifest = dict(source_directory="current/deployed/robot/hcr1-pose-receiver", build="fixture",
            files={name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sources.items()},
            aliases={"hcr1_pose_receiver.script": "hcr1_pose_receiver.stable-v1-online.script"})
        for name, data in sources.items():
            (self.source / name).write_bytes(data)
        self.manifest_path = Path(directory) / "manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest))


class RuntimeInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = RuntimeFixture(self.temporary.name)
        self.manifest_patch = patch.object(legacy, "SOURCE_MANIFEST", self.fixture.manifest_path)
        self.manifest_patch.start()

    def tearDown(self):
        self.manifest_patch.stop()
        self.temporary.cleanup()

    def install(self):
        return install_robot_runtime.install(self.fixture.package, self.fixture.destination)

    def test_only_fixed_sources_are_copied_without_operating_state(self):
        for name in ("pose-profile.pending.json", "current_session.json", "command.json", "extra.py"):
            (self.fixture.source / name).write_text("private historical content")
        (self.fixture.source / "runs").mkdir()
        result = self.install()
        self.assertEqual(set(result["files"]), set(self.fixture.manifest["files"]) | {"hcr1_pose_receiver.script"})
        self.assertEqual(set(path.name for path in self.fixture.destination.iterdir()), set(result["files"]))
        self.assertFalse(result["scripts_executed"])
        self.assertFalse(result["commands_replayed"])

    def test_changed_input_fails_before_any_destination_write(self):
        (self.fixture.source / "policy.py").write_text("unreviewed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.install()
        self.assertFalse(self.fixture.destination.exists())

    def test_canonical_script_alias_is_exact_installed_online_script(self):
        self.install()
        self.assertEqual((self.fixture.destination / "hcr1_pose_receiver.script").read_bytes(),
                         (self.fixture.destination / "hcr1_pose_receiver.stable-v1-online.script").read_bytes())

    def test_installer_does_not_modify_active_runtime(self):
        self.install()
        (self.fixture.destination / "current_session.json").write_text('{"path":"old"}')
        with self.assertRaisesRegex(ValueError, "operating runtime"):
            self.install()

    def test_every_hash_is_verified_before_any_import(self):
        self.install()
        (self.fixture.destination / "wrist.py").write_text("raise RuntimeError('unreviewed')")
        with self.assertRaises(legacy.PrewireRejected):
            legacy.LegacyReceiver(self.fixture.destination)

    def test_runtime_imports_are_private_and_do_not_load_package_startup(self):
        self.install()
        (self.fixture.destination / "__init__.py").write_text("raise RuntimeError('must not execute')")
        previous = sys.modules.get("policy")
        receiver = legacy.LegacyReceiver(self.fixture.destination)
        self.assertIs(receiver.modules["wrist"].policy, receiver.policy)
        self.assertIs(sys.modules.get("policy"), previous)
        self.assertIsNone(receiver.lock_stream)

    def test_open_acquires_owner_without_requiring_receiver_connection(self):
        self.install()
        receiver = legacy.LegacyReceiver(self.fixture.destination)
        fake_fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=Mock())
        with patch.dict(sys.modules, {"fcntl": fake_fcntl}), patch.object(receiver, "snapshot", side_effect=AssertionError):
            receiver.open()
            self.assertIsNotNone(receiver.lock_stream)
            receiver.close()
        fake_fcntl.flock.assert_called_once()
        self.assertIsNone(receiver.lock_stream)

    def test_open_conflicting_owner_is_a_prewire_rejection(self):
        self.install()
        receiver = legacy.LegacyReceiver(self.fixture.destination)
        fake_fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=Mock(side_effect=BlockingIOError))
        with patch.dict(sys.modules, {"fcntl": fake_fcntl}), self.assertRaises(legacy.PrewireRejected):
            receiver.open()
        self.assertIsNone(receiver.lock_stream)

    def test_snapshot_missing_or_closed_is_status_not_exception(self):
        self.install()
        receiver = legacy.LegacyReceiver(self.fixture.destination)
        self.assertFalse(receiver.snapshot()["connected"])
        run = self.fixture.destination / "runs/session-test"
        run.mkdir(parents=True)
        (self.fixture.destination / "current_session.json").write_text('{"path":"session-test"}')
        (run / "state.json").write_text('{"stage":"closed","status":"outcome_unknown_check_pendant"}')
        self.assertIn("outcome_unknown", receiver.snapshot()["reason"])

    def test_snapshot_rejects_pointer_escape(self):
        self.install()
        receiver = legacy.LegacyReceiver(self.fixture.destination)
        (self.fixture.destination / "current_session.json").write_text('{"path":"../other"}')
        self.assertFalse(receiver.snapshot()["connected"])

    def fresh_receiver(self):
        self.install()
        receiver = legacy.LegacyReceiver(self.fixture.destination)
        run = self.fixture.destination / "runs/session-test"
        run.mkdir(parents=True)
        (self.fixture.destination / "current_session.json").write_text('{"path":"session-test"}')
        profile = {"fixture": True, "tcp_id": "reviewed-test-tcp"}
        state = dict(stage="idle", schema=receiver.policy.SCHEMA, session_id=SID, seq=7,
                     profile_id=receiver.policy.digest(profile), profile=profile,
                     updated_monotonic_ns=time.monotonic_ns(), physical_execution=True,
                     actual_pose=[0] * 6, actual_joint=[0] * 6, planned_pose=[0] * 6)
        (run / "state.json").write_text(json.dumps(state))
        return receiver, run, state

    def test_snapshot_exposes_only_validated_profile_for_admission(self):
        receiver, run, state = self.fresh_receiver()
        snapshot = receiver.snapshot()
        self.assertTrue(snapshot["connected"])
        self.assertEqual(snapshot["profile"], state["profile"])
        snapshot["profile"]["tcp_id"] = "browser mutation"
        self.assertEqual(receiver.snapshot()["profile"]["tcp_id"], "reviewed-test-tcp")

    def test_snapshot_with_invalid_or_stale_profile_does_not_expose_authority(self):
        receiver, run, state = self.fresh_receiver()
        state["profile"]["tcp_id"] = "changed without digest"
        (run / "state.json").write_text(json.dumps(state))
        result = receiver.snapshot()
        self.assertFalse(result["connected"])
        self.assertIsNone(result["profile"])
        state["profile_id"] = receiver.policy.digest(state["profile"])
        state["updated_monotonic_ns"] = time.monotonic_ns() - 6_000_000_000
        (run / "state.json").write_text(json.dumps(state))
        self.assertEqual(receiver.snapshot()["reason"], "RECEIVER_STATE_STALE")
        self.assertIsNone(receiver.snapshot()["profile"])

    def test_reconciliation_clears_only_latch_after_fresh_exact_idle(self):
        receiver, run, state = self.fresh_receiver()
        receiver._uncertain = True
        receiver.lock_stream = object()
        receiver.submit.session_state = Mock(return_value=(run, state))
        receiver.submit.publish_once = Mock()
        expected = {key: state[key] for key in receiver.BINDING}
        result = receiver.reconcile(expected)
        self.assertTrue(result["reconciled"])
        self.assertFalse(result["command_replayed"])
        self.assertFalse(receiver._uncertain)
        receiver.submit.publish_once.assert_not_called()

    def test_reconciliation_rejects_changed_busy_stale_and_pending_states(self):
        receiver, run, state = self.fresh_receiver()
        receiver._uncertain = True
        receiver.lock_stream = object()
        receiver.submit.session_state = Mock(return_value=(run, state))
        expected = {key: state[key] for key in receiver.BINDING}
        wrong = dict(expected, seq=expected["seq"] - 1)
        with self.assertRaises(legacy.PrewireRejected):
            receiver.reconcile(wrong)
        for changes in ({"stage": "moving"}, {"updated_monotonic_ns": time.monotonic_ns() - 6_000_000_000}):
            (run / "state.json").write_text(json.dumps(dict(state, **changes)))
            with self.assertRaises(legacy.PrewireRejected):
                receiver.reconcile(expected)
            self.assertTrue(receiver._uncertain)
        (run / "state.json").write_text(json.dumps(state))
        (run / "command.json").write_text("pending historical command")
        with self.assertRaises(legacy.PrewireRejected):
            receiver.reconcile(expected)
        self.assertTrue(receiver._uncertain)
        self.assertTrue((run / "command.json").exists())


class FakeSubmit:
    def __init__(self, run, callback=None):
        self.run = run
        self.callback = callback
        self.publications = 0
        self.state = dict(session_id=SID, seq=7, profile_id=PID, physical_execution=True, stage="idle")
        self.write_state()

    def write_state(self):
        (self.run / "state.json").write_text(json.dumps(self.state))

    def session_state(self):
        return self.run, copy.deepcopy(self.state)

    def prepare(self, operation, target, edge_id, profile, check_runnable):
        wire = dict(session_id=SID, seq=7, profile_id=PID, request_id=RID, command_digest=DIGEST)
        if operation == "profile-update":
            wire["new_profile_id"] = "e" * 64
        return self.run, copy.deepcopy(self.state), wire

    def event(self, kind, **values):
        data = dict(session_id=SID, seq=7, request_id=RID, command_digest=DIGEST, **values)
        with (self.run / "events.jsonl").open("a") as stream:
            stream.write(json.dumps({"kind": kind, "data": data}) + "\n")

    def publish_once(self, run, state, wire):
        self.publications += 1
        if self.callback is not None:
            return self.callback(self, wire)
        self.event("motion_endpoint_verified")
        self.state["seq"] += 1
        self.write_state()


class ReceiverPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run = self.root / "runs/session-test"
        self.run.mkdir(parents=True)
        (self.root / "current_session.json").write_text('{"path":"session-test"}')
        (self.run / "events.jsonl").write_text("")
        self.receiver = object.__new__(legacy.LegacyReceiver)
        self.receiver.root = self.root
        self.receiver.lock_stream = object()
        self.receiver._execution_lock = threading.Lock()
        self.receiver._uncertain = False
        self.receiver.modules = {"transport": SimpleNamespace(strict_json=json.loads)}
        self.receiver.submit = FakeSubmit(self.run)
        self.command = dict(kind="translate", target=[0] * 6,
            expected_receiver={"session_id": SID, "seq": 7, "profile_id": PID}, timeout_seconds=.02)
        self.events = []
        self.sleep_patch = patch.object(legacy.time, "sleep", return_value=None)
        self.sleep_patch.start()

    def tearDown(self):
        self.sleep_patch.stop()
        self.temporary.cleanup()

    def execute(self, callback=None):
        return self.receiver.execute(self.command, callback or (lambda kind, data: self.events.append((kind, data))))

    def test_matching_endpoint_and_next_idle_verify_one_publication(self):
        result = self.execute()
        self.assertEqual(result["kind"], "motion_endpoint_verified")
        self.assertEqual(self.receiver.submit.publications, 1)
        self.assertEqual([item[0] for item in self.events],
                         ["publication_intent", "published", "wire_motion_endpoint_verified", "verified"])

    def test_missing_owner_or_changed_binding_cannot_publish(self):
        self.receiver.lock_stream = None
        with self.assertRaises(legacy.PrewireRejected):
            self.execute()
        self.receiver.lock_stream = object()
        self.command["expected_receiver"]["seq"] = 6
        with self.assertRaises(legacy.PrewireRejected):
            self.execute()
        self.assertEqual(self.receiver.submit.publications, 0)

    def test_failed_durable_intent_never_publishes(self):
        with self.assertRaisesRegex(legacy.PrewireRejected, "INTENT_NOT_RECORDED"):
            self.execute(lambda *_: (_ for _ in ()).throw(OSError("disk")))
        self.assertEqual(self.receiver.submit.publications, 0)
        self.assertFalse(self.receiver._uncertain)

    def test_retryable_guard_error_before_publication_preserves_wait_state(self):
        error = GuardError("WAIT_OBSERVATION", "Car temporarily obscured", True)
        with self.assertRaises(GuardError) as caught:
            self.execute(lambda *_: (_ for _ in ()).throw(error))
        self.assertIs(caught.exception, error)
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(self.receiver.submit.publications, 0)
        self.assertFalse(self.receiver._uncertain)

    def test_guard_error_after_publication_is_still_unknown(self):
        def fail(kind, data):
            if kind == "published":
                raise GuardError("WAIT_OBSERVATION", "Too late to retry a command", True)
        with self.assertRaises(legacy.OutcomeUnknown):
            self.execute(fail)
        self.assertTrue(self.receiver._uncertain)
        self.assertEqual(self.receiver.submit.publications, 1)

    def test_publish_exception_is_unknown_and_cannot_resend(self):
        def fail(submit, wire):
            submit.event("motion_endpoint_verified")
            raise OSError("link outcome unknown")
        self.receiver.submit.callback = fail
        with self.assertRaises(legacy.OutcomeUnknown):
            self.execute()
        with self.assertRaises(legacy.OutcomeUnknown):
            self.execute()
        self.assertEqual(self.receiver.submit.publications, 1)

    def test_done_alone_and_old_historical_receipts_never_complete(self):
        self.receiver.submit.event("motion_endpoint_verified")
        def done(submit, wire):
            submit.event("motion_done_reported")
            submit.state["seq"] += 1
            submit.write_state()
        self.receiver.submit.callback = done
        with self.assertRaisesRegex(legacy.OutcomeUnknown, "TIMEOUT"):
            self.execute()
        self.assertEqual(self.receiver.submit.publications, 1)

    def test_closed_receiver_and_changed_session_are_unknown(self):
        def closed(submit, wire):
            submit.state["stage"] = "closed"
            submit.write_state()
        self.receiver.submit.callback = closed
        with self.assertRaisesRegex(legacy.OutcomeUnknown, "CLOSED"):
            self.execute()

    def test_mismatched_terminal_digest_is_unknown(self):
        def mismatch(submit, wire):
            with (self.run / "events.jsonl").open("a") as stream:
                stream.write(json.dumps({"kind": "motion_endpoint_verified", "data":
                    dict(session_id=SID, seq=7, request_id=RID, command_digest="wrong")}) + "\n")
        self.receiver.submit.callback = mismatch
        with self.assertRaisesRegex(legacy.OutcomeUnknown, "DIGEST"):
            self.execute()

    def test_explicit_receiver_rejection_preserves_connection_without_retry(self):
        self.receiver.submit.callback = lambda submit, wire: submit.event("command_rejected_before_wire", reason="invalid input")
        with self.assertRaises(legacy.PrewireRejected):
            self.execute()
        self.assertFalse(self.receiver._uncertain)
        self.assertEqual(self.receiver.submit.publications, 1)

    def test_temporary_metadata_read_failure_does_not_resubmit(self):
        original = self.receiver._state
        count = [0]
        def read():
            count[0] += 1
            if count[0] == 1:
                raise OSError("read")
            return original()
        with patch.object(self.receiver, "_state", side_effect=read):
            self.execute()
        self.assertEqual(self.receiver.submit.publications, 1)

    def test_profile_update_requires_new_profile_acknowledgement(self):
        self.command["kind"] = "profile_update"
        def applied(submit, wire):
            submit.event("profile_applied_verified")
            submit.state.update(seq=8, profile_id=wire["new_profile_id"])
            submit.write_state()
        self.receiver.submit.callback = applied
        self.assertEqual(self.execute()["kind"], "profile_applied_verified")

    def test_callback_failure_after_publication_latches_unknown(self):
        def journal(kind, data):
            if kind == "published":
                raise OSError("disk")
        with self.assertRaises(legacy.OutcomeUnknown):
            self.execute(journal)
        self.assertTrue(self.receiver._uncertain)

    def test_corrupt_complete_event_is_not_silently_skipped(self):
        def corrupt(submit, wire):
            with (self.run / "events.jsonl").open("a") as stream:
                stream.write("{broken}\n")
            submit.event("motion_endpoint_verified")
            submit.state["seq"] = 8
            submit.write_state()
        self.receiver.submit.callback = corrupt
        with self.assertRaisesRegex(legacy.OutcomeUnknown, "LOG_CORRUPT"):
            self.execute()

    def test_concurrent_execution_cannot_publish(self):
        self.receiver._execution_lock.acquire()
        try:
            with self.assertRaises(legacy.PrewireRejected):
                self.execute()
        finally:
            self.receiver._execution_lock.release()
        self.assertEqual(self.receiver.submit.publications, 0)


class HostCliTests(unittest.TestCase):
    def test_network_requires_explicit_motion_and_listen_flags(self):
        with self.assertRaises(SystemExit), patch("sys.stderr", new_callable=io.StringIO), patch.object(serve_rodi_host, "load_runtime") as load:
            serve_rodi_host.main(["--profile", "new.local.json", "--listen"])
        load.assert_not_called()

    def test_no_profile_is_restored_by_default(self):
        with self.assertRaises(SystemExit), patch("sys.stderr", new_callable=io.StringIO), patch.object(serve_rodi_host, "load_runtime") as load:
            serve_rodi_host.main([])
        load.assert_not_called()

    def test_default_validation_does_not_open_listener(self):
        with patch.object(serve_rodi_host, "load_runtime", return_value={}), \
             patch.object(serve_rodi_host, "read_profile", return_value=(b"{}", {})), \
             patch.object(serve_rodi_host, "serve") as server:
            self.assertEqual(serve_rodi_host.main(["--profile", "new.local.json"]), 0)
        server.assert_not_called()


class HostSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        class Journal:
            def __init__(self, path):
                path.mkdir(parents=True)
            def event(self, kind, data):
                pass
            def close(self):
                pass
        def atomic(path, value):
            path.write_text(json.dumps(value))
        self.exchange = Mock()
        self.native = Mock()
        self.policy = SimpleNamespace(SCHEMA="fixture", require=lambda ok, message: None if ok else (_ for _ in ()).throw(ValueError(message)),
                                      near=Mock())
        self.server = SimpleNamespace(environment_check=Mock(), legacy_receiver_absent=Mock(),
                                     atomic_json=atomic, exchange=self.exchange)
        self.modules = {"server": self.server, "policy": self.policy,
                        "transport": SimpleNamespace(Journal=Journal, Native=self.native,
                            read_stationary=Mock(return_value={"joint": [0] * 6}),
                            Wire=Mock(), wait_endpoint_settled=Mock())}
        self.profile = patch.object(serve_rodi_host, "read_profile", return_value=(b"fixture", {
            "expected_start_tcp_mm_deg": [0] * 6, "expected_start_joint_deg": [0] * 6}))
        self.profile.start()

    def tearDown(self):
        self.profile.stop()
        self.temporary.cleanup()

    def run_session(self, peer="192.168.10.10"):
        return serve_rodi_host.run_session(object(), (peer, 12345), self.root, "new.local.json", self.modules)

    def test_failed_go_session_is_archived_and_new_connection_gets_empty_session(self):
        def fail(wire, guard, profile, motion, report, publish, command, emit, settle):
            self.assertFalse(command.exists())
            report["motion_permission_may_have_been_sent"] = True
            raise ConnectionError("disconnected after GO")
        self.exchange.side_effect = fail
        first = self.run_session()
        second = self.run_session()
        self.assertEqual(first["status"], "outcome_unknown_check_pendant")
        self.assertFalse(first["automatic_retry"])
        self.assertNotEqual(first["run"], second["run"])
        self.assertEqual(len(list((self.root / "runs").iterdir())), 2)
        self.assertEqual(self.exchange.call_count, 2)
        self.assertFalse(any((self.root / "runs").rglob("command.json")))

    def test_wrong_peer_never_queries_native_or_enters_exchange(self):
        result = self.run_session("127.0.0.1")
        self.assertEqual(result["status"], "blocked")
        self.native.assert_not_called()
        self.exchange.assert_not_called()

    def test_accepted_pendant_is_checked_in_running_program_state(self):
        self.run_session()
        self.modules["transport"].read_stationary.assert_called_once_with(
            self.native.return_value, [0] * 6, (2,), True)

    def test_listener_remains_available_after_a_failed_session_without_outbound_reconnect(self):
        fake_fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=Mock())
        listener = Mock()
        listener.__enter__ = Mock(return_value=listener)
        listener.__exit__ = Mock(return_value=False)
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        listener.accept.side_effect = [(connection, ("192.168.10.10", 1)), KeyboardInterrupt]
        with patch.dict(sys.modules, {"fcntl": fake_fcntl}), \
             patch.object(serve_rodi_host.socket, "socket", return_value=listener), \
             patch.object(serve_rodi_host, "run_session", return_value={"status": "blocked"}) as session, \
             patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(KeyboardInterrupt):
                serve_rodi_host.serve(self.root, "new.local.json", self.modules)
        listener.bind.assert_called_once_with(("192.168.10.31", 19507))
        self.assertEqual(listener.accept.call_count, 2)
        session.assert_called_once()

    def test_disk_finalize_exception_does_not_kill_next_manual_connection(self):
        runs = self.root / "runs"
        old_run = runs / "historical"
        old_run.mkdir(parents=True)
        (old_run / "state.json").write_text("historical evidence")
        (old_run / "command.json").write_text("do not replay or remove")
        (self.root / "current_session.json").write_text('{"path":"historical"}')
        fake_fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=Mock())
        listener = Mock()
        listener.__enter__ = Mock(return_value=listener)
        listener.__exit__ = Mock(return_value=False)
        def connection():
            value = Mock()
            value.__enter__ = Mock(return_value=value)
            value.__exit__ = Mock(return_value=False)
            return value
        first, second = connection(), connection()
        listener.accept.side_effect = [(first, ("192.168.10.10", 1)),
                                       (second, ("192.168.10.10", 2)), KeyboardInterrupt]
        def failed_then_new(connection, peer, runtime, profile, modules):
            if connection is first:
                new_run = runs / "this-connection"
                new_run.mkdir()
                (new_run / "command.json").write_text("uncertain pending command")
                (self.root / "current_session.json").write_text('{"path":"this-connection"}')
                raise OSError("disk finalization failed")
            # The second attempt is a new manual connection, not a replay.
            self.assertIsNone(json.loads((self.root / "current_session.json").read_text())["path"])
            return {"source": "rodi_host", "status": "waiting_for_manual_play"}
        with patch.dict(sys.modules, {"fcntl": fake_fcntl}), \
             patch.object(serve_rodi_host.socket, "socket", return_value=listener), \
             patch.object(serve_rodi_host, "run_session", side_effect=failed_then_new) as session, \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            with self.assertRaises(KeyboardInterrupt):
                serve_rodi_host.serve(self.root, "new.local.json", self.modules)
        self.assertEqual(session.call_count, 2)
        self.assertEqual(listener.accept.call_count, 3)
        self.assertEqual((old_run / "state.json").read_text(), "historical evidence")
        self.assertEqual((old_run / "command.json").read_text(), "do not replay or remove")
        self.assertEqual((runs / "this-connection/command.json").read_text(), "uncertain pending command")
        closed = json.loads((runs / "this-connection/state.json").read_text())
        self.assertEqual(closed["status"], "outcome_unknown_check_pendant")
        status = json.loads((self.root / "host-status.json").read_text())
        self.assertEqual(status["source"], "rodi_host")
        self.assertFalse(status["automatic_retry"])
        self.assertFalse(status["server_exit_is_robot_stop"])
        self.assertIn("outcome_unknown_check_pendant", output.getvalue())

    def test_diagnostic_write_failure_still_returns_unknown_status(self):
        self.server.atomic_json = Mock(side_effect=OSError("disk unavailable"))
        result = serve_rodi_host._session_unavailable(self.root, None, self.modules, OSError("initial journal"))
        self.assertEqual(result["status"], "outcome_unknown_check_pendant")
        self.assertFalse(result["result_available"])


if __name__ == "__main__":
    unittest.main()
