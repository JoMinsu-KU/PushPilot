"""Read-only Native reacquisition without changing the installed Rodi protocol.

One thread owns both sockets. An individual FC03 acquisition remains bounded
to two seconds; only a pendant already back in its top-level packet loop may
receive an IDLE between failed acquisitions. No command is sent or repeated
here. Invalid measured state and ambiguous wire outcomes remain fatal.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import errno
import math
import time


NETWORK_ERRNOS = frozenset(getattr(errno, name) for name in (
    "ECONNRESET", "ECONNREFUSED", "ETIMEDOUT", "EHOSTUNREACH", "ENETUNREACH",
    "EPIPE", "ENOTCONN", "ECONNABORTED", "ENETDOWN"))

# Only the matching pendant variant extends these two nested packet waits.
# BEGIN, top-level packet reads and actual motion completion retain their bounds.
COMMIT_WAIT_CAPABILITY = "bounded-commit-wait-30s-v2"
PROTECTED_READ_BUDGET_S = 20.


class PrecommitReadTimeout(TimeoutError):
    """Fresh Native verification failed before GO/PROFILE_COMMIT; never replay."""


@contextmanager
def bind_request_lifetime(server, wire):
    """Scope a lifetime adapter to this single-owner private exchange module.

    The inherited preflight still runs first. Its exact accepted request is then
    retained solely for a final fresh() check at the wire boundary, including
    after a long legal-idle acquisition. No inherited source/file is modified.
    The host serializes sessions under its process/file lock; restore even on
    BaseException so neither a later session nor another loader inherits it.
    """
    original = server.preflight_request

    def preflight(command, *args, **kwargs):
        result = original(command, *args, **kwargs)
        wire.bind_request(command, server.fresh)
        return result

    server.preflight_request = preflight
    try:
        yield
    finally:
        server.preflight_request = original
        wire.clear_request()


def read_unavailable(error):
    # Do not swallow disk/journal errors raised from Native.snapshot's logger.
    return (isinstance(error, (TimeoutError, ConnectionError)) or
            isinstance(error, OSError) and error.errno in NETWORK_ERRNOS)


class RecoveryWire:
    """Track when IDLE is legal; all actual I/O stays on the exchange thread.

    The inherited exchange validates each received packet before calling its
    next Native guard. DONE, IK_RESULT and PROFILE_APPLIED acknowledge the old
    sequence; the pendant then increments it before accepting the next IDLE.
    No READY/ENTERING/HELLO state permits an inserted heartbeat.
    """
    def __init__(self, inner, server, *, clock=time.monotonic, require_request=False):
        self.inner, self.server = inner, server
        self.clock = clock
        self.last_activity = clock()
        self.sent = None
        self.idle_header = None
        self.capabilities = frozenset()
        self.protected_phase = None
        self.protected_deadline = None
        self.request = None
        self._fresh = None
        self.sent_at = None
        self.require_request = require_request
        self.last_request_identity = None

    def bind_request(self, command, fresh):
        self.request = copy.deepcopy(command)
        self._fresh = fresh
        self.last_request_identity = {key: command.get(key) for key in
            ("request_id", "session_id", "seq", "profile_id", "command_digest")}

    def clear_request(self):
        self.request = None
        self._fresh = None

    def _check_request(self, packet):
        command = self.request
        if command is None:
            raise RuntimeError("Accepted command lifetime is not bound to this exchange")
        allowed = {"target": ("prepare", "go"), "profile_update": ("profile_prepare", "profile_commit"),
                   "ik_query": ("ik_query",)}.get(command.get("type"), ())
        keys = ("session_id", "seq", "profile_id", "command_digest")
        if packet.get("type") not in allowed or any(packet.get(k) != command.get(k) for k in keys):
            raise ValueError("Command lifetime binding mismatch")
        for key in ("previous", "target", "new_profile_id"):
            if key in command and packet.get(key) != command[key]:
                raise ValueError("Command lifetime geometry mismatch: " + key)
        self._fresh(command)  # Original absolute expiry, never extended on retry.

    def verify_pending_fresh(self):
        if self.request is not None:
            self._fresh(self.request)

    @property
    def can_idle(self):
        return self.idle_header is not None

    def send(self, packet):
        if packet.get("type") in ("prepare", "profile_prepare", "ik_query", "go", "profile_commit"):
            if self.require_request or self._fresh is not None:
                self._check_request(packet)
        self.idle_header = None
        self.protected_phase = None
        self.protected_deadline = None
        self.sent_at = self.clock()
        self.inner.send(packet)
        self.sent = copy.deepcopy(packet)

    def receive(self, seconds=12):
        packet = self.inner.receive(seconds=seconds)
        self.last_activity = self.clock()
        sent = self.sent or {}
        if packet.get("type") == "hello":
            capabilities = packet.get("capabilities")
            if (type(capabilities) is list and len(capabilities) <= 8
                    and all(type(value) is str for value in capabilities)):
                self.capabilities = frozenset(capabilities)
        protected = {"prepare": "ready", "profile_prepare": "profile_ready"}.get(sent.get("type"))
        if (COMMIT_WAIT_CAPABILITY in self.capabilities and protected is not None
                and packet.get("type") == protected
                and all(type(packet.get(key)) is type(sent.get(key)) and packet.get(key) == sent.get(key)
                        for key in ("schema", "robot_id", "session_id", "seq", "profile_id", "execute_motion"))):
            self.protected_phase = "profile_precommit" if protected == "profile_ready" else "motion_precommit"
            # v2 uses up to three legal 10s reads, extending only empty waits.
            # Sending PREPARE precedes that bounded 30s window, so an
            # absolute deadline from that earlier instant is conservative even
            # when a READY reply itself was delayed in transit.
            self.protected_deadline = self.sent_at + PROTECTED_READ_BUDGET_S
        expected = {"begin": "session_ready", "idle": "idle_ok", "go": "done",
                    "ik_query": "ik_result", "profile_commit": "profile_applied"}.get(sent.get("type"))
        if packet.get("type") == expected and expected is not None:
            keys = ("schema", "robot_id", "session_id", "seq", "profile_id", "execute_motion")
            self.idle_header = {key: packet[key] for key in keys}
            if expected != "idle_ok":
                self.idle_header["seq"] += 1
        return packet

    def heartbeat(self, expected):
        if not self.can_idle:
            raise RuntimeError("Native recovery heartbeat is illegal in this wire phase")
        packet = dict(self.idle_header, type="idle")
        self.send(packet)
        reply = self.receive()
        self.server.reply(reply, "idle_ok", packet["session_id"], packet["seq"],
                          packet["profile_id"], packet["execute_motion"], expected)


class NativeRecovery:
    def __init__(self, native, wire, transport, *, owner_check, waiting,
                 clock=time.monotonic, sleep=time.sleep):
        self.native, self.wire, self.transport = native, wire, transport
        self.owner_check, self.waiting = owner_check, waiting
        self.clock, self.sleep = clock, sleep
        self.unavailable = False
        self.failures = 0

    def _unavailable(self, error, expected, phase, *, heartbeat=True, pause_s=.25):
        self.unavailable = True
        self.failures += 1
        # Invalidate dispatch BEFORE sending another liveness packet. This is
        # not an idle publication and does not refresh any measured evidence.
        self.waiting({"reason": "NATIVE_TELEMETRY_UNAVAILABLE", "phase": phase,
                      "error_type": type(error).__name__, "detail": str(error)[:256],
                      "failures": self.failures, "motion_retried": False})
        self.native.log.event("stationary_read_timeout" if isinstance(error, TimeoutError)
                              else "stationary_read_unavailable",
                              {"attempt": self.failures, "reason": str(error)[:256],
                               "motion_retried": False, "consecutive_samples_reset": True,
                               "recovery_phase": phase})
        if heartbeat:
            self.wire.heartbeat(expected)
        self.sleep(pause_s)

    def _protected_stationary(self, expected, programs, motion):
        phase, deadline = self.wire.protected_phase, self.wire.protected_deadline
        valid = 0
        while self.clock() < deadline:
            self.owner_check()
            self.wire.verify_pending_fresh()
            remaining = deadline - self.clock()
            if remaining <= 0:
                break
            try:
                row = self.native.snapshot(timeout_s=min(2., remaining))
            except Exception as error:
                if not read_unavailable(error):
                    raise
                valid = 0
                self._unavailable(error, expected, phase, heartbeat=False,
                    pause_s=min(.25, max(0., deadline-self.clock())))
                continue
            if self.clock() >= deadline:
                break
            self.transport.native_stationary(row, expected, programs, motion)
            self.transport.near(row["pose"], expected, .5)
            self.wire.verify_pending_fresh()
            valid += 1
            if valid == 2:
                self.unavailable = False
                self.native.log.event("native_precommit_verified", {
                    "phase": phase, "budget_s": PROTECTED_READ_BUDGET_S,
                    "capability": COMMIT_WAIT_CAPABILITY, "motion_retried": False})
                return row
            self.sleep(min(.1, max(0., deadline-self.clock())))
        raise PrecommitReadTimeout("NATIVE_PRECOMMIT_VERIFICATION_TIMEOUT:" + phase)

    def stationary(self, expected, programs, motion):
        if not self.wire.can_idle:
            if self.wire.protected_deadline is not None:
                return self._protected_stationary(expected, programs, motion)
            # HELLO/BEGIN and READY/GO are finite protocol handshakes. Inserting
            # IDLE there would invalidate the unchanged pendant program.
            return self.transport.read_stationary(self.native, expected, programs, motion)
        valid = 0
        while True:
            if self.clock()-self.wire.last_activity >= 3:
                self.wire.heartbeat(expected)
                valid = 0
            self.owner_check()
            try:
                row = self.native.snapshot(timeout_s=2)
            except Exception as error:
                if not read_unavailable(error):
                    raise
                valid = 0
                self._unavailable(error, expected, "stationary")
                continue
            self.transport.native_stationary(row, expected, programs, motion)
            self.transport.near(row["pose"], expected, .5)  # literal Euler check
            valid += 1
            if valid == 2:
                self.unavailable = False
                return row
            self.sleep(.1)

    def settled(self, expected, motion):
        if not self.wire.can_idle:
            return self.transport.wait_endpoint_settled(self.native, expected, motion)
        start = self.clock()
        zero_since = None
        samples = 0
        while self.clock()-start < 8:
            if self.clock()-self.wire.last_activity >= 3:
                self.wire.heartbeat(expected)
                # These measurements remain continuous only if Native itself
                # stays valid; liveness never substitutes for a zero sample.
            self.owner_check()
            try:
                row = self.native.snapshot(timeout_s=min(2, 8-(self.clock()-start)))
            except Exception as error:
                if not read_unavailable(error):
                    raise
                zero_since = None
                self._unavailable(error, expected, "endpoint_after_done")
                # No interval across unavailable measurements counts as
                # stationarity. Reacquire the full original two-second proof.
                start = self.clock()
                continue
            samples += 1
            self.transport.native_posture(row, expected, (2,), motion)
            self.transport.near(row["pose"], expected, .5)
            speed = row["speed"]
            if (type(speed) is not list or len(speed) != 6 or
                    any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > .1 for v in speed)):
                raise ValueError("Unexpected motion during endpoint settling")
            now = self.clock()
            if now-start >= 8:
                break
            if all(v == 0 for v in speed):
                if zero_since is None:
                    zero_since = now
                if now-zero_since >= 2:
                    self.transport.native_stationary(row, expected, (2,), motion)
                    self.native.log.event("endpoint_settled", {
                        "samples": samples, "elapsed_s": now-start,
                        "continuous_zero_speed_s": now-zero_since,
                        "read_timeouts": self.failures, "expected": expected, "actual": row})
                    self.unavailable = False
                    return row
            else:
                zero_since = None
            self.sleep(.1)
        raise ValueError("Endpoint did not remain stationary before deadline")
