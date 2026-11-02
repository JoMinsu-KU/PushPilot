"""Read-only Native reacquisition without changing the installed Rodi protocol.

One thread owns both sockets. An individual FC03 acquisition remains bounded
to two seconds; only a pendant already back in its top-level packet loop may
receive an IDLE between failed acquisitions. No command is sent or repeated
here. Invalid measured state and ambiguous wire outcomes remain fatal.
"""
from __future__ import annotations

import copy
import errno
import math
import time


NETWORK_ERRNOS = frozenset(getattr(errno, name) for name in (
    "ECONNRESET", "ECONNREFUSED", "ETIMEDOUT", "EHOSTUNREACH", "ENETUNREACH",
    "EPIPE", "ENOTCONN", "ECONNABORTED", "ENETDOWN"))


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
    def __init__(self, inner, server, *, clock=time.monotonic):
        self.inner, self.server = inner, server
        self.clock = clock
        self.last_activity = clock()
        self.sent = None
        self.idle_header = None

    @property
    def can_idle(self):
        return self.idle_header is not None

    def send(self, packet):
        self.idle_header = None
        self.inner.send(packet)
        self.sent = copy.deepcopy(packet)

    def receive(self, seconds=12):
        packet = self.inner.receive(seconds=seconds)
        self.last_activity = self.clock()
        sent = self.sent or {}
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

    def _unavailable(self, error, expected, phase):
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
        self.wire.heartbeat(expected)
        self.sleep(.25)

    def stationary(self, expected, programs, motion):
        if not self.wire.can_idle:
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
