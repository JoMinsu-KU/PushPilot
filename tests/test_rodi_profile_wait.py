"""Equipment-free pre-listener profile waiting and explicit HELLO diagnostics."""
from __future__ import annotations

import copy
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import serve_rodi_host as host


class Connection:
    def __init__(self, packet=None, *, receive_error=None, close_error=False):
        self.packet = packet
        self.receive_error = receive_error
        self.sendall = Mock()
        self.settimeout = Mock()
        self.close_error = close_error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.close_error:
            raise OSError("Synthetic close failure")
        return False


class SyntheticJournal:
    """New stdlib-only diagnostic fixture; no inherited runtime is loaded."""
    def __init__(self, path):
        path.mkdir(parents=True, exist_ok=False)
        self.stream = (path / "events.jsonl").open("x", encoding="utf-8")

    def event(self, kind, data):
        self.stream.write(json.dumps({"kind": kind, "data": data}, allow_nan=False) + "\n")
        self.stream.flush()

    def close(self):
        self.stream.close()


def fixture_modules(wires):
    """Inject behavior contracts, not a copy or test of the private driver."""
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    def vector(value, size):
        require(type(value) is list and len(value) == size and
                all(type(item) in (int, float) and math.isfinite(item) for item in value),
                "Synthetic finite vector required")
        return value

    def valid(profile, motion):
        require(type(profile) is dict and profile.get("synthetic_reviewed") is True,
                "Synthetic fixture rejects an unreviewed profile")
        if motion:
            require(profile.get("allow_motion") is True and profile.get("site_verified") is True,
                    "Synthetic fixture requires explicit reviewed motion flags")

    def near(actual, expected, tolerance=.5):
        vector(actual, 6)
        vector(expected, 6)
        require(all(abs(a - b) <= tolerance for a, b in zip(actual, expected)), "Synthetic posture mismatch")

    def wire(connection, journal):
        value = Mock()

        def receive(*, seconds):
            if connection.receive_error is not None:
                raise connection.receive_error
            journal.event("synthetic_transport_receive", {"fixture": True})
            return copy.deepcopy(connection.packet)

        value.receive.side_effect = receive
        wires.append(value)
        return value

    def atomic(path, value):
        path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")

    return {
        "policy": SimpleNamespace(SCHEMA="pushpilot.hcr1-pose.experimental-v1",
                                  REVISION="pose-receiver-experimental-v1", require=require,
                                  vector=vector, valid=valid, near=near,
                                  text=lambda value: type(value) is str and 0 < len(value) <= 256),
        "transport": SimpleNamespace(Journal=SyntheticJournal, Wire=Mock(side_effect=wire), Native=Mock(),
                                     strict_json=json.loads, read_stationary=Mock(), wait_endpoint_settled=Mock()),
        "server": SimpleNamespace(exchange=Mock(), atomic_json=atomic, environment_check=Mock(),
                                  legacy_receiver_absent=Mock()),
    }


class ProfileWaitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.wires = []
        self.modules = fixture_modules(self.wires)
        self.old = self.root / "runs" / "historical"
        self.old.mkdir(parents=True)
        (self.old / "command.json").write_text("Never replay or remove this historical request.")
        self.pointer = self.root / "current_session.json"
        self.pointer.write_text('{"path":"historical"}')
        self.packet = {
            "schema": self.modules["policy"].SCHEMA, "type": "hello", "robot_id": "HCR1",
            "revision": self.modules["policy"].REVISION, "build": "poc-persistent-v1",
            "local_motion_enabled": True, "origin": [10, 20, 30, 0, 0, 0],
            "actual_joint": [0] * 6, "actual_speed": [0] * 6,
            "capabilities": ["idle-profile-update-v1"],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def capture(self, connection, peer="192.168.10.10"):
        return host.capture_profile_wait(connection, (peer, 1), self.root, self.modules,
                                         FileNotFoundError("New measured profile is not ready"))

    def assert_no_execution(self, connection):
        connection.sendall.assert_not_called()
        for wire in self.wires:
            wire.send.assert_not_called()
            wire.receive.assert_called_once_with(seconds=3)
        self.modules["server"].exchange.assert_not_called()
        self.modules["transport"].Native.assert_not_called()
        self.assertEqual(self.pointer.read_text(), '{"path":"historical"}')
        self.assertEqual((self.old / "command.json").read_text(), "Never replay or remove this historical request.")
        self.assertEqual(len(list((self.root / "runs").iterdir())), 1)

    def test_valid_hello_is_diagnostic_only_without_begin_or_profile_fabrication(self):
        connection = Connection(self.packet)
        result = self.capture(connection)
        self.assertTrue(result["hello_received"])
        self.assertEqual(result["status"], "waiting_reviewed_profile")
        for field in ("ready", "physical_execution", "begin_sent", "motion_issued", "mailbox_consumed", "automatic_retry"):
            self.assertIs(result[field], False)
        self.assertTrue(result["waiting_for_manual_play"])
        self.assert_no_execution(connection)
        status = json.loads((self.root / "host-status.json").read_text())
        self.assertEqual(status["telemetry_source"], "pendant_hello_unqualified")
        events = list((self.root / "diagnostics").glob("*/events.jsonl"))
        self.assertEqual(len(events), 1)
        self.assertNotIn('"type": "begin"', events[0].read_text())
        self.assertNotIn('"site_verified"', events[0].read_text())

    def test_wrong_peer_is_not_read_or_logged_as_a_hello(self):
        connection = Connection(self.packet)
        result = self.capture(connection, peer="127.0.0.1")
        self.assertFalse(result["hello_received"])
        self.modules["transport"].Wire.assert_not_called()
        self.assertFalse((self.root / "diagnostics").exists())
        self.assert_no_execution(connection)

    def test_invalid_hello_identity_and_nonfinite_values_never_begin(self):
        for key, value in (("build", "unexpected"), ("local_motion_enabled", False),
                           ("origin", [True] * 6), ("actual_joint", [float("nan")] * 6),
                           ("capabilities", ["x"] * 9)):
            with self.subTest(field=key):
                packet = copy.deepcopy(self.packet)
                packet[key] = value
                connection = Connection(packet)
                result = self.capture(connection)
                self.assertFalse(result["hello_received"])
                self.assert_no_execution(connection)

    def test_transport_size_rejection_keeps_hello_diagnostic_only(self):
        # The inherited bounded parser is a separate contract. Inject its
        # rejection here and prove the wrapper never bypasses or retries it.
        connection = Connection(receive_error=ValueError("Synthetic oversized wire message"))
        result = self.capture(connection)
        self.assertFalse(result["hello_received"])
        self.assertEqual(result["diagnostic_error_type"], "ValueError")
        self.assert_no_execution(connection)

    def test_closed_connection_does_not_become_a_session(self):
        connection = Connection(receive_error=ConnectionError("Synthetic closed transport"))
        result = self.capture(connection)
        self.assertFalse(result["hello_received"])
        self.assertEqual(result["diagnostic_error_type"], "ConnectionError")
        self.assert_no_execution(connection)

    def test_journal_failure_preserves_current_receiver_pointer(self):
        connection = Connection(self.packet)
        with patch.object(self.modules["transport"], "Journal", side_effect=OSError("Synthetic full disk")):
            result = self.capture(connection)
        self.assertFalse(result["hello_received"])
        self.assertEqual(result["diagnostic_error_type"], "OSError")
        self.assert_no_execution(connection)

    def test_status_failure_does_not_change_pending_result(self):
        connection = Connection(self.packet)
        with patch.object(self.modules["server"], "atomic_json", side_effect=OSError("Synthetic write error")):
            result = self.capture(connection)
        self.assertTrue(result["hello_received"])
        self.assertEqual(result["status"], "waiting_reviewed_profile")
        self.assert_no_execution(connection)

    def test_final_journal_write_failure_still_closes_the_journal(self):
        connection = Connection(self.packet)
        journal = SimpleNamespace(event=Mock(side_effect=[None, None, OSError("Synthetic full disk")]),
                                  close=Mock())
        with patch.object(self.modules["transport"], "Journal", return_value=journal):
            result = self.capture(connection)
        self.assertTrue(result["hello_received"])
        self.assertEqual(result["diagnostic_error_type"], "OSError")
        journal.close.assert_called_once()
        self.assert_no_execution(connection)

    def serve_connections(self, connections, *, wait_for_profile=True, before_socket=None):
        listener = Mock()
        listener.__enter__ = Mock(return_value=listener)
        listener.__exit__ = Mock(return_value=False)
        listener.accept.side_effect = [*( (connection, ("192.168.10.10", index))
                                         for index, connection in enumerate(connections) ), KeyboardInterrupt]
        fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=Mock())

        def open_listener(*args):
            if before_socket is not None:
                before_socket()
            return listener

        with patch.dict(sys.modules, {"fcntl": fcntl}), \
             patch.object(host.socket, "socket", side_effect=open_listener), \
             patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(KeyboardInterrupt):
                host.serve(self.root, self.root / "new-profile.json", self.modules,
                           wait_for_profile=wait_for_profile)
        listener.bind.assert_called_once_with(("192.168.10.31", 19507))
        return listener

    def assert_wait_has_no_receiver_access(self):
        self.modules["transport"].Native.assert_not_called()
        self.modules["transport"].Wire.assert_not_called()
        self.modules["transport"].read_stationary.assert_not_called()
        self.modules["server"].exchange.assert_not_called()
        self.modules["server"].environment_check.assert_not_called()
        self.assertEqual(self.pointer.read_text(), '{"path":"historical"}')
        self.assertEqual((self.old / "command.json").read_text(), "Never replay or remove this historical request.")

    def test_missing_and_invalid_profiles_are_rechecked_before_any_listener_then_normal_session_runs(self):
        connection = Connection(self.packet)
        sleeps = []

        def wait(seconds):
            self.assertEqual(seconds, 1)
            sleeps.append(seconds)
            status = json.loads((self.root / "host-status.json").read_text())
            self.assertEqual(status["status"], "waiting_reviewed_profile")
            self.assertFalse(status["listening"])
            self.assertFalse(status["waiting_for_manual_play"])
            self.assert_wait_has_no_receiver_access()

        with patch.object(host, "read_profile", side_effect=[FileNotFoundError(), ValueError(), (b"{}", {})]), \
             patch.object(host, "run_session", return_value={"status": "blocked"}) as session, \
             patch.object(host, "capture_profile_wait") as capture, \
             patch.object(host, "_current_pointer", wraps=host._current_pointer) as pointer, \
             patch.object(host.time, "sleep", side_effect=wait):
            def before_socket():
                self.assertEqual(sleeps, [1, 1])
                pointer.assert_not_called()
                session.assert_not_called()
                capture.assert_not_called()
            listener = self.serve_connections([connection], before_socket=before_socket)
        session.assert_called_once_with(connection, ("192.168.10.10", 0), self.root,
                                        self.root / "new-profile.json", self.modules)
        self.assertEqual(listener.accept.call_count, 2)
        capture.assert_not_called()
        self.assert_wait_has_no_receiver_access()

    def test_missing_profile_never_opens_a_port_even_if_a_pendant_would_attempt_play(self):
        listener = Mock()
        listener.accept.side_effect = AssertionError("An unprepared host must not accept a pendant HELLO")
        fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=Mock())
        with patch.dict(sys.modules, {"fcntl": fcntl}), \
             patch.object(host.socket, "socket", return_value=listener) as opened, \
             patch.object(host.time, "sleep", side_effect=KeyboardInterrupt), \
             patch.object(host, "capture_profile_wait") as capture, \
             patch.object(host, "_current_pointer") as pointer, \
             patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(KeyboardInterrupt):
                host.serve(self.root, self.root / "missing-profile.json", self.modules, wait_for_profile=True)
        opened.assert_not_called()
        listener.bind.assert_not_called()
        listener.listen.assert_not_called()
        listener.accept.assert_not_called()
        capture.assert_not_called()
        pointer.assert_not_called()
        self.assert_wait_has_no_receiver_access()

    def test_wait_recovers_from_local_profile_io_errors_with_one_second_polling(self):
        failures = [PermissionError("Synthetic profile unavailable"), OSError("Synthetic read failure")]
        with patch.object(host, "read_profile", side_effect=[*failures, (b"{}", {})]) as read, \
             patch.object(host.time, "sleep") as sleep, \
             patch.object(host.socket, "socket") as opened, \
             patch("sys.stdout", new_callable=io.StringIO):
            host.wait_for_reviewed_profile(self.root, self.root / "new-profile.json", self.modules)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(1), unittest.mock.call(1)])
        opened.assert_not_called()
        self.assert_wait_has_no_receiver_access()

    def test_new_valid_profile_file_starts_the_existing_session_without_hello_diagnostics(self):
        profile = self.root / "new-profile.json"
        profile.write_text("{}")
        reviewed = {"synthetic_reviewed": True, "allow_motion": True, "site_verified": True}

        def prepare_current_profile(seconds):
            self.assertEqual(seconds, 1)
            self.assert_wait_has_no_receiver_access()
            profile.write_text(json.dumps(reviewed))

        connection = Connection(self.packet)
        with patch.object(host.time, "sleep", side_effect=prepare_current_profile) as sleep, \
             patch.object(host, "capture_profile_wait") as capture, \
             patch.object(host, "run_session", return_value={"status": "blocked"}) as session:
            listener = self.serve_connections([connection])
        sleep.assert_called_once_with(1)
        session.assert_called_once_with(connection, ("192.168.10.10", 0), self.root, profile, self.modules)
        capture.assert_not_called()
        self.assertEqual(listener.accept.call_count, 2)
        status = json.loads((self.root / "host-status.json").read_text())
        self.assertEqual(status["status"], "waiting_for_manual_play")
        self.assertTrue(status["listening"])
        self.assertFalse(status["ready"])

    def test_nonwaiting_serve_rejects_invalid_profile_before_opening_listener(self):
        fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=Mock())
        with patch.dict(sys.modules, {"fcntl": fcntl}), \
             patch.object(host.socket, "socket") as opened, \
             patch.object(host, "run_session") as session, \
             patch.object(host.time, "sleep") as sleep:
            with self.assertRaises(ValueError):
                host.serve(self.root, self.root / "missing-profile.json", self.modules)
        opened.assert_not_called()
        session.assert_not_called()
        sleep.assert_not_called()
        self.assert_wait_has_no_receiver_access()

    def test_profile_invalidated_after_listener_precheck_never_reaches_native_or_wire(self):
        profile = self.root / "new-profile.json"
        profile.write_text("{}")
        result = host.run_session(Connection(self.packet), ("192.168.10.10", 1), self.root, profile, self.modules)
        self.assertEqual(result["status"], "blocked")
        self.modules["transport"].Native.assert_not_called()
        self.modules["transport"].Wire.assert_not_called()
        self.modules["server"].exchange.assert_not_called()
        self.assertEqual(self.pointer.read_text(), '{"path":"historical"}')

    def test_unbounded_or_unreviewed_profile_is_rejected(self):
        profile = self.root / "new-profile.json"
        for content in (b"x" * 65537, b"{}", b"{\"x\":1,\"x\":2}"):
            with self.subTest(size=len(content)):
                profile.write_bytes(content)
                with self.assertRaises(ValueError):
                    host.read_profile(profile, self.modules, True)

    def test_symlink_profile_rejected_before_read(self):
        actual = self.root / "profile-target.json"
        actual.write_text("{}")
        linked = self.root / "profile-link.json"
        try:
            linked.symlink_to(actual)
        except (OSError, NotImplementedError):
            self.skipTest("Host account cannot create test symlinks")
        with self.assertRaises(ValueError):
            host.read_profile(linked, self.modules, True)

    def test_symlink_rejection_does_not_require_permission_to_create_a_link(self):
        with patch.object(Path, "is_symlink", return_value=True), \
             patch.object(Path, "open") as opened:
            with self.assertRaises(ValueError):
                host.read_profile(self.root / "profile.json", self.modules, True)
        opened.assert_not_called()

    def test_wait_mode_requires_explicit_network_flags_and_profile_path(self):
        for arguments in (["--profile", "new.json", "--wait-for-profile"],
                          ["--listen", "--motion", "--wait-for-profile"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit), \
                 patch("sys.stderr", new_callable=io.StringIO), patch.object(host, "load_runtime") as load:
                host.main(arguments)
            load.assert_not_called()

    def test_wait_mode_defers_only_startup_profile_check(self):
        with patch.object(host, "load_runtime", return_value={}), \
             patch.object(host, "read_profile") as read, patch.object(host, "serve") as serve:
            result = host.main(["--runtime", str(self.root), "--profile", "fresh.json",
                                "--listen", "--motion", "--wait-for-profile"])
        self.assertEqual(result, 0)
        read.assert_not_called()
        serve.assert_called_once_with(self.root, Path("fresh.json"), {}, wait_for_profile=True)

    def test_real_session_publish_replaces_waiting_status_and_close_is_not_ready(self):
        profile = {"expected_start_tcp_mm_deg": [0] * 6, "expected_start_joint_deg": [0] * 6}

        def exchange(wire, guard, active_profile, motion, report, publish, command, emit, settle):
            publish("idle", "synthetic-session", 1, "synthetic-profile", [0] * 6, [0] * 6,
                    [0] * 6, active_profile, [], [0] * 6)
            current = json.loads((self.root / "host-status.json").read_text())
            self.assertEqual(current["status"], "idle")
            self.assertTrue(current["ready"])
            self.assertTrue(current["receiver_session_active"])
            report["status"] = "synthetic_finished"

        with patch.object(host, "read_profile", return_value=(b"synthetic-profile", profile)), \
             patch.object(self.modules["server"], "environment_check"), \
             patch.object(self.modules["server"], "legacy_receiver_absent"), \
             patch.object(self.modules["server"], "exchange", side_effect=exchange), \
             patch.object(self.modules["transport"], "read_stationary", return_value={"joint": [0] * 6}):
            result = host.run_session(Connection(self.packet), ("192.168.10.10", 1), self.root,
                                      self.root / "synthetic-reviewed-profile.json", self.modules)
        current = json.loads((self.root / "host-status.json").read_text())
        self.assertEqual(current["status"], "synthetic_finished")
        self.assertFalse(current["ready"])
        self.assertFalse(current["receiver_session_active"])
        self.assertFalse(result["ready"])


if __name__ == "__main__":
    unittest.main()
