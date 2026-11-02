"""Equipment-free faults for one-owner Native/Rodi liveness and evidence.

These synthetic contracts exercise the public wrapper only. They do not load
the private receiver, open sockets, or establish physical qualification.
"""
from collections import deque
from copy import deepcopy
import errno
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from backend.robot_control.host_resilience import (
    COMMIT_WAIT_CAPABILITY, NativeRecovery, PrecommitReadTimeout, RecoveryWire,
    bind_request_lifetime, read_unavailable,
)
from backend.robot_control.taught_executor import ExecutionBlocked
from backend.robot_control.taught_ports import prove_host_journal_cycle


POSE = [10., 20., 10., 90., 0., 30.]
HEADER = {'schema': 'pushpilot.hcr1-pose.experimental-v1', 'robot_id': 'HCR1',
          'session_id': 'a' * 32, 'seq': 7, 'profile_id': 'b' * 64, 'execute_motion': True}


def native_row(**changes):
    value = {'program_before': [2], 'program_after': [2], 'flags': [1, 1, 0, 0, 0, 0],
             'joint': [0.] * 6, 'speed': [0.] * 6, 'pose': list(POSE)}
    value.update(deepcopy(changes))
    return value


class Clock:
    def __init__(self):
        self.value = 1.

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds

    def ns(self):
        return round(self.value * 1e9)


class Journal:
    def __init__(self, clock):
        self.clock, self.rows = clock, []

    def event(self, kind, data):
        self.clock.sleep(.00001)
        self.rows.append({'monotonic_ns': self.clock.ns(), 'kind': kind, 'data': deepcopy(data)})


class InnerWire:
    def __init__(self, journal):
        self.journal = journal
        self.sent, self.responses = [], deque()

    def send(self, packet):
        self.sent.append(deepcopy(packet))
        self.journal.event('tx_intent', packet)

    def receive(self, seconds=12):
        if self.responses:
            packet = self.responses.popleft()
            if isinstance(packet, BaseException):
                raise packet
        else:
            sent = self.sent[-1]
            kind = {'begin': 'session_ready', 'idle': 'idle_ok', 'prepare': 'ready',
                    'go': 'done', 'ik_query': 'ik_result', 'profile_prepare': 'profile_ready',
                    'profile_commit': 'profile_applied', 'finish': 'finished'}[sent['type']]
            packet = {key: sent[key] for key in HEADER}
            packet.update(type=kind, actual_pose=list(POSE), actual_joint=[0.] * 6,
                          actual_speed=[0.] * 6)
            if kind == 'profile_applied':
                packet['profile_id'] = sent['new_profile_id']
        self.journal.event('rx', packet)
        return deepcopy(packet)


class Native:
    def __init__(self, journal, clock, actions=(), *, default_delay=.01, fallback=None):
        self.log, self.clock = journal, clock
        self.actions, self.calls = deque(actions), []
        self.default_delay = default_delay
        self.fallback = native_row() if fallback is None else fallback

    def snapshot(self, *, timeout_s):
        self.calls.append(timeout_s)
        action = self.actions.popleft() if self.actions else self.fallback
        delay, value = action if isinstance(action, tuple) else (self.default_delay, action)
        self.clock.sleep(delay)
        if isinstance(value, BaseException):
            raise value
        row = deepcopy(value)
        self.log.event('native_readonly', row)
        return row


def near(actual, expected, tolerance):
    if len(actual) != len(expected) or any(abs(a-b) > tolerance for a, b in zip(actual, expected)):
        raise ValueError('Synthetic literal pose disagreement')


def posture(row, expected, programs, motion):
    if row['program_before'] != row['program_after'] or row['program_after'][0] not in programs:
        raise ValueError('Synthetic program state fault')
    if row['flags'] != [1, 1, 0, 0, 0, 0]:
        raise ValueError('Synthetic hardware flag fault')
    near(row['pose'], expected, .5)


def stationary(row, expected, programs, motion):
    posture(row, expected, programs, motion)
    if row['speed'] != [0.] * 6:
        raise ValueError('Synthetic nonzero speed fault')


def reply(packet, kind, sid, seq, pid, motion, expected):
    values = {**HEADER, 'type': kind, 'session_id': sid, 'seq': seq,
              'profile_id': pid, 'execute_motion': motion}
    if any(type(packet.get(key)) is not type(value) or packet.get(key) != value
           for key, value in values.items()):
        raise ValueError('Synthetic bound wire reply mismatch')
    near(packet['actual_pose'], expected, .3)
    near(packet['actual_speed'], [0.] * 6, .1)


class Harness:
    def __init__(self, actions=(), *, default_delay=.01, fallback=None):
        self.clock = Clock()
        self.journal = Journal(self.clock)
        self.inner = InnerWire(self.journal)
        self.wire = RecoveryWire(self.inner, SimpleNamespace(reply=reply), clock=self.clock)
        self.native = Native(self.journal, self.clock, actions, default_delay=default_delay, fallback=fallback)
        self.transport = SimpleNamespace(native_stationary=stationary, native_posture=posture, near=near,
            read_stationary=Mock(return_value={'original': 'stationary'}),
            wait_endpoint_settled=Mock(return_value={'original': 'settled'}))
        self.waiting_calls = []

        def owner_check():
            self.journal.event('control_owner_check', {'listening': False})

        def waiting(data):
            self.waiting_calls.append((self.clock.ns(), deepcopy(data)))

        self.recovery = NativeRecovery(self.native, self.wire, self.transport,
            owner_check=owner_check, waiting=waiting, clock=self.clock, sleep=self.clock.sleep)

    def idle(self):
        self.wire.send({**HEADER, 'type': 'idle'})
        packet = self.wire.receive()
        reply(packet, 'idle_ok', HEADER['session_id'], HEADER['seq'], HEADER['profile_id'], True, POSE)


class RecoveryFaultClassificationTests(unittest.TestCase):
    def test_only_read_network_faults_are_recoverable(self):
        for error in (TimeoutError('read deadline'), ConnectionResetError('peer reset'),
                      OSError(errno.EHOSTUNREACH, 'host unreachable'),
                      OSError(errno.ECONNREFUSED, 'read server unavailable')):
            with self.subTest(error=error):
                self.assertTrue(read_unavailable(error))
        for error in (OSError(errno.ENOSPC, 'journal full'), OSError(errno.EIO, 'journal failed'),
                      PermissionError(errno.EACCES, 'journal forbidden'), OSError(errno.EBADF, 'closed log'),
                      ValueError('invalid Modbus body'), RuntimeError('unexpected interpreter failure')):
            with self.subTest(error=error):
                self.assertFalse(read_unavailable(error))


class RecoveryWirePhaseTests(unittest.TestCase):
    def test_top_level_idle_keeps_same_identity(self):
        h = Harness()
        h.idle()
        h.wire.heartbeat(POSE)
        self.assertEqual([row['type'] for row in h.inner.sent], ['idle', 'idle'])
        self.assertTrue(all(row['seq'] == 7 and row['profile_id'] == HEADER['profile_id'] for row in h.inner.sent))

    def test_session_ready_uses_sequence_one_for_first_idle(self):
        h = Harness()
        h.wire.send({**HEADER, 'type': 'begin', 'seq': 0})
        h.wire.receive()
        self.assertTrue(h.wire.can_idle)
        h.wire.heartbeat(POSE)
        self.assertEqual(h.inner.sent[-1]['seq'], 1)

    def test_ready_profile_ready_and_entering_never_permit_idle(self):
        for kind in ('prepare', 'profile_prepare', 'go'):
            with self.subTest(kind=kind):
                h = Harness()
                h.idle()
                h.wire.send({**HEADER, 'type': kind})
                if kind == 'go':
                    h.inner.responses.append({**HEADER, 'type': 'entering'})
                h.wire.receive()
                self.assertFalse(h.wire.can_idle)
                with self.assertRaises(RuntimeError):
                    h.wire.heartbeat(POSE)
                self.assertEqual(h.inner.sent[-1]['type'], kind)

    def test_completed_readonly_inspection_advances_sequence_once(self):
        h = Harness()
        h.wire.send({**HEADER, 'type': 'ik_query'})
        h.wire.receive()
        h.wire.heartbeat(POSE)
        h.wire.heartbeat(POSE)
        self.assertEqual([p['seq'] for p in h.inner.sent if p['type'] == 'idle'], [8, 8])

    def test_applied_profile_heartbeat_binds_new_profile_and_next_sequence(self):
        h = Harness()
        h.wire.send({**HEADER, 'type': 'profile_commit', 'new_profile_id': 'c' * 64})
        h.wire.receive()
        h.wire.heartbeat(POSE)
        self.assertEqual((h.inner.sent[-1]['seq'], h.inner.sent[-1]['profile_id']), (8, 'c' * 64))

    def test_wire_disconnect_after_go_is_propagated_without_resending(self):
        h = Harness()
        h.wire.send({**HEADER, 'type': 'go'})
        h.inner.responses.append(ConnectionError('Synthetic unknown motion outcome'))
        with self.assertRaises(ConnectionError):
            h.wire.receive()
        self.assertFalse(h.wire.can_idle)
        self.assertEqual([p['type'] for p in h.inner.sent], ['go'])

    def test_invalid_idle_reply_is_fatal_without_another_send(self):
        h = Harness()
        h.idle()
        h.inner.responses.append({**HEADER, 'seq': 999, 'type': 'idle_ok',
                                  'actual_pose': list(POSE), 'actual_speed': [0.] * 6})
        with self.assertRaises(ValueError):
            h.wire.heartbeat(POSE)
        self.assertEqual(len(h.inner.sent), 2)


class StationaryReacquisitionTests(unittest.TestCase):
    def test_three_plus_failed_reads_keep_idle_alive_without_motion_or_sequence_change(self):
        h = Harness([(2., TimeoutError('deadline')) for _ in range(4)] + [native_row(), native_row()])
        h.idle()
        result = h.recovery.stationary(POSE, (2,), True)
        self.assertEqual(result, native_row())
        self.assertEqual(len(h.native.calls), 6)
        self.assertEqual(len(h.waiting_calls), 4)
        self.assertFalse(h.recovery.unavailable)
        self.assertTrue(all(p['type'] == 'idle' and p['seq'] == 7 for p in h.inner.sent))
        self.assertTrue(all(0 < budget <= 2 for budget in h.native.calls))
        idle_times = [r['monotonic_ns'] for r in h.journal.rows if r['kind'] == 'tx_intent']
        self.assertTrue(all((b-a)/1e9 < 5 for a, b in zip(idle_times, idle_times[1:])))
        for waiting_time, _ in h.waiting_calls:
            self.assertTrue(any(r['kind'] == 'tx_intent' and r['monotonic_ns'] > waiting_time
                                for r in h.journal.rows))

    def test_success_before_timeout_does_not_count_toward_recovered_pair(self):
        h = Harness([native_row(), (2., TimeoutError('lost read')), native_row(), native_row()])
        h.idle()
        h.recovery.stationary(POSE, (2,), True)
        self.assertEqual(len(h.native.calls), 4)
        last_idle_ok = max(i for i, r in enumerate(h.journal.rows)
                           if r['kind'] == 'rx' and r['data']['type'] == 'idle_ok')
        self.assertEqual(sum(r['kind'] == 'native_readonly' for r in h.journal.rows[last_idle_ok+1:]), 2)

    def test_periodic_legal_idle_resets_pair_when_prior_activity_was_old(self):
        h = Harness([(1.8, native_row()), native_row(), native_row()])
        h.idle()
        h.clock.sleep(1.5)
        h.recovery.stationary(POSE, (2,), True)
        self.assertEqual(len(h.native.calls), 3)
        self.assertEqual(len(h.inner.sent), 2)

    def test_read_error_during_unsafe_phase_uses_original_bounded_guard(self):
        h = Harness([(2., TimeoutError('must not be called'))])
        h.wire.send({**HEADER, 'type': 'prepare'})
        h.wire.receive()
        self.assertEqual(h.recovery.stationary(POSE, (2,), True), {'original': 'stationary'})
        h.transport.read_stationary.assert_called_once_with(h.native, POSE, (2,), True)
        self.assertEqual(h.native.calls, [])
        self.assertEqual(h.waiting_calls, [])

    def test_bad_program_flags_speed_pose_and_journal_failures_do_not_recover(self):
        cases = [native_row(program_after=[4]), native_row(flags=[1, 1, 1, 0, 0, 0]),
                 native_row(speed=[.1, 0., 0., 0., 0., 0.]), native_row(pose=[10.6, *POSE[1:]]),
                 OSError(errno.ENOSPC, 'Synthetic journal disk full')]
        for case in cases:
            with self.subTest(case=case):
                h = Harness([case])
                h.idle()
                with self.assertRaises((ValueError, OSError)):
                    h.recovery.stationary(POSE, (2,), True)
                self.assertEqual(len(h.inner.sent), 1)
                self.assertEqual(h.waiting_calls, [])

    def test_network_reset_is_reacquired_without_any_nonidle_send(self):
        h = Harness([ConnectionResetError('read socket reset'), native_row(), native_row()])
        h.idle()
        h.recovery.stationary(POSE, (2,), True)
        self.assertEqual(h.waiting_calls[0][1]['error_type'], 'ConnectionResetError')
        self.assertTrue(all(p['type'] == 'idle' for p in h.inner.sent))

    def test_recovered_cycle_preserves_existing_host_journal_proof(self):
        h = Harness([native_row(), (2., TimeoutError('one fresh read lost')), native_row(), native_row()])
        h.idle()
        h.recovery.stationary(POSE, (2,), True)
        h.clock.sleep(1.)
        state = {key: HEADER[key] for key in ('schema', 'session_id', 'seq', 'profile_id')}
        state.update(stage='idle', physical_execution=True, updated_monotonic_ns=h.clock.ns(),
                     actual_pose=list(POSE), planned_pose=list(POSE), actual_joint=[0.] * 6)
        raw = b''.join(json.dumps(row).encode() + b'\n' for row in h.journal.rows)
        proof = prove_host_journal_cycle(state, raw, now_monotonic_ns=h.clock.ns()+1,
            expected_receiver={key: HEADER[key] for key in ('session_id', 'seq', 'profile_id')},
            publication_after_ns=999_000_000)
        self.assertEqual(len(proof['native_rows']), 2)
        self.assertEqual(proof['source_sample_monotonic_ns'], h.journal.rows[-1]['monotonic_ns'])
        changed = {**state, 'stage': 'native_wait'}
        with self.assertRaises(ExecutionBlocked):
            prove_host_journal_cycle(changed, raw, now_monotonic_ns=h.clock.ns()+1)


class EndpointReacquisitionTests(unittest.TestCase):
    def done(self, h):
        h.wire.send({**HEADER, 'type': 'go'})
        result = h.wire.receive()
        reply(result, 'done', HEADER['session_id'], 7, HEADER['profile_id'], True, POSE)

    def test_done_recovery_uses_next_sequence_and_never_resends_go(self):
        h = Harness([(2., TimeoutError('endpoint read unavailable'))], default_delay=.2)
        self.done(h)
        h.recovery.settled(POSE, True)
        self.assertEqual(sum(p['type'] == 'go' for p in h.inner.sent), 1)
        self.assertTrue(all(p['seq'] == 8 for p in h.inner.sent if p['type'] == 'idle'))
        evidence = [r for r in h.journal.rows if r['kind'] == 'endpoint_settled']
        self.assertEqual(len(evidence), 1)
        self.assertGreaterEqual(evidence[0]['data']['continuous_zero_speed_s'], 2.)
        self.assertFalse(any(r['kind'] == 'motion_endpoint_verified' for r in h.journal.rows))

    def test_timeout_discards_earlier_zero_interval(self):
        h = Harness([(.5, native_row()), (2., TimeoutError('gap'))], default_delay=.2)
        self.done(h)
        h.recovery.settled(POSE, True)
        timeout = next(r for r in h.journal.rows if r['kind'] == 'stationary_read_timeout')
        after = next(r for r in h.journal.rows if r['kind'] == 'native_readonly'
                     and r['monotonic_ns'] > timeout['monotonic_ns'])
        settled = next(r for r in h.journal.rows if r['kind'] == 'endpoint_settled')
        self.assertGreaterEqual((settled['monotonic_ns']-after['monotonic_ns'])/1e9, 2.)

    def test_quantized_nonzero_speed_resets_continuous_zero_interval(self):
        h = Harness([(.5, native_row()), (.5, native_row(speed=[.1, 0., 0., 0., 0., 0.]))], default_delay=.2)
        self.done(h)
        h.recovery.settled(POSE, True)
        nonzero = next(r for r in h.journal.rows if r['kind'] == 'native_readonly' and r['data']['speed'][0])
        settled = next(r for r in h.journal.rows if r['kind'] == 'endpoint_settled')
        self.assertGreater((settled['monotonic_ns']-nonzero['monotonic_ns'])/1e9, 2.)

    def test_persistent_nonzero_speed_keeps_original_eight_second_failure(self):
        h = Harness(default_delay=.2, fallback=native_row(speed=[.1, 0., 0., 0., 0., 0.]))
        self.done(h)
        with self.assertRaisesRegex(ValueError, 'Endpoint did not remain stationary'):
            h.recovery.settled(POSE, True)
        self.assertFalse(any(r['kind'] == 'endpoint_settled' for r in h.journal.rows))
        self.assertEqual(h.waiting_calls, [])

    def test_bad_measured_motion_or_nan_is_not_a_read_retry(self):
        for speed in ([.2, 0., 0., 0., 0., 0.], [float('nan'), 0., 0., 0., 0., 0.]):
            with self.subTest(speed=speed):
                h = Harness([native_row(speed=speed)])
                self.done(h)
                with self.assertRaisesRegex(ValueError, 'Unexpected motion'):
                    h.recovery.settled(POSE, True)
                self.assertEqual(h.waiting_calls, [])

    def test_settling_unsafe_phase_delegates_without_sending_idle(self):
        h = Harness()
        h.wire.send({**HEADER, 'type': 'go'})
        h.inner.responses.append({**HEADER, 'type': 'entering'})
        h.wire.receive()
        self.assertEqual(h.recovery.settled(POSE, True), {'original': 'settled'})
        h.transport.wait_endpoint_settled.assert_called_once_with(h.native, POSE, True)
        self.assertEqual(len(h.inner.sent), 1)


class ProtectedCommitWaitTests(unittest.TestCase):
    def ready(self, h, kind='profile_prepare', *, capability=True):
        h.inner.responses.append({'type': 'hello', 'capabilities':
                                  [COMMIT_WAIT_CAPABILITY] if capability else []})
        h.wire.receive()
        h.wire.send({**HEADER, 'type': kind})
        h.wire.receive()

    def test_negotiated_profile_and_motion_wait_recover_after_four_timeouts(self):
        for kind in ('profile_prepare', 'prepare'):
            with self.subTest(kind=kind):
                h = Harness([(2., TimeoutError('late Native'))] * 4 + [native_row(), native_row()])
                self.ready(h, kind)
                self.assertEqual(h.recovery.stationary(POSE, (2,), True), native_row())
                self.assertEqual(len(h.native.calls), 6)
                self.assertFalse(h.recovery.unavailable)
                self.assertEqual([p['type'] for p in h.inner.sent], [kind])
                self.assertTrue(all(0 < n <= 2 for n in h.native.calls))
                self.assertTrue(all('precommit' in c[1]['phase'] for c in h.waiting_calls))

    def test_deadline_is_absolute_and_timeout_never_sends_idle_or_commit(self):
        h = Harness([(2., TimeoutError('continuous outage'))] * 20)
        self.ready(h)
        deadline = h.wire.protected_deadline
        with self.assertRaisesRegex(PrecommitReadTimeout, 'profile_precommit'):
            h.recovery.stationary(POSE, (2,), True)
        self.assertLessEqual(h.clock(), deadline + .001)
        self.assertTrue(h.recovery.unavailable)
        self.assertEqual([p['type'] for p in h.inner.sent], ['profile_prepare'])

    def test_timeout_invalidates_previous_success(self):
        h = Harness([native_row(), (2., TimeoutError('gap')), native_row(), native_row()])
        self.ready(h)
        h.recovery.stationary(POSE, (2,), True)
        self.assertEqual(len(h.native.calls), 4)

    def test_old_or_wrong_capability_retains_original_bounded_guard(self):
        for capability in ([], ['bounded-commit-wait-60s-v1'], ['bounded-commit-wait-30s-v1']):
            h = Harness()
            h.inner.responses.append({'type': 'hello', 'capabilities': capability})
            h.wire.receive()
            h.wire.send({**HEADER, 'type': 'profile_prepare'})
            h.wire.receive()
            self.assertEqual(h.recovery.stationary(POSE, (2,), True), {'original': 'stationary'})
            self.assertEqual(h.native.calls, [])

    def test_capability_does_not_extend_begin_or_entering(self):
        for kind, response in [('begin', 'hello_invalid'), ('go', 'entering')]:
            h = Harness()
            h.inner.responses.append({'type': 'hello', 'capabilities': [COMMIT_WAIT_CAPABILITY]})
            h.wire.receive()
            h.wire.send({**HEADER, 'type': kind})
            h.inner.responses.append({**HEADER, 'type': response})
            h.wire.receive()
            h.recovery.stationary(POSE, (2,), True)
            h.transport.read_stationary.assert_called_once()
            self.assertIsNone(h.wire.protected_deadline)

    def test_wrong_ready_identity_cannot_negotiate_extended_wait(self):
        h = Harness()
        h.inner.responses.append({'type': 'hello', 'capabilities': [COMMIT_WAIT_CAPABILITY]})
        h.wire.receive()
        h.wire.send({**HEADER, 'type': 'prepare'})
        h.inner.responses.append({**HEADER, 'type': 'ready', 'seq': 999})
        h.wire.receive()
        self.assertIsNone(h.wire.protected_deadline)

    def test_delayed_ready_consumes_budget_from_prepare_send(self):
        h = Harness()
        h.inner.responses.append({'type': 'hello', 'capabilities': [COMMIT_WAIT_CAPABILITY]})
        h.wire.receive()
        h.wire.send({**HEADER, 'type': 'prepare'})
        sent_at = h.wire.sent_at
        h.clock.sleep(9.)
        h.wire.receive()
        self.assertAlmostEqual(h.wire.protected_deadline, sent_at + 20.)

    def test_owner_or_native_delay_past_deadline_cannot_authorize(self):
        h = Harness([(20.1, native_row()), native_row()])
        self.ready(h)
        with self.assertRaises(PrecommitReadTimeout):
            h.recovery.stationary(POSE, (2,), True)
        self.assertEqual(len(h.native.calls), 1)

    def test_invalid_measured_state_and_journal_failure_are_not_retryable(self):
        for action in (native_row(flags=[1, 1, 1, 0, 0, 0]),
                       native_row(speed=[.1, 0, 0, 0, 0, 0]),
                       native_row(pose=[11., *POSE[1:]]),
                       ValueError('malformed Modbus'), OSError(errno.ENOSPC, 'journal full')):
            h = Harness([action])
            self.ready(h)
            with self.assertRaises((ValueError, OSError)):
                h.recovery.stationary(POSE, (2,), True)
            self.assertEqual(len(h.native.calls), 1)
            self.assertEqual(h.waiting_calls, [])


class RequestLifetimeBoundaryTests(unittest.TestCase):
    def request(self, h, **changes):
        command = {**HEADER, 'type': 'target', 'request_id': 'd' * 32,
                   'command_digest': 'e' * 64, 'previous': list(POSE), 'target': list(POSE),
                   'expires_monotonic_ns': h.clock.ns() + 30_000_000_000}
        command.update(changes)
        return command

    def fresh(self, h):
        def check(command):
            if h.clock.ns() >= command['expires_monotonic_ns']:
                raise ValueError('Expired command')
        return check

    def packet(self, command, kind):
        return {k: deepcopy(v) for k, v in {**command, 'type': kind}.items()
                if k != 'expires_monotonic_ns'}

    def test_production_wire_requires_accepted_lifetime(self):
        h = Harness()
        h.wire.require_request = True
        with self.assertRaisesRegex(RuntimeError, 'lifetime'):
            h.wire.send({**HEADER, 'type': 'prepare'})
        self.assertEqual(h.inner.sent, [])

    def test_original_expiry_checked_again_after_guard_before_prepare(self):
        h = Harness()
        command = self.request(h)
        h.wire.bind_request(command, self.fresh(h))
        command['expires_monotonic_ns'] += 999_000_000_000  # Caller mutation cannot extend it.
        h.clock.sleep(30.)
        with self.assertRaisesRegex(ValueError, 'Expired'):
            h.wire.send(self.packet(command, 'prepare'))
        self.assertEqual(h.inner.sent, [])

    def test_original_expiry_checked_before_go_and_profile_commit(self):
        for request_kind, prepare, commit in [('target', 'prepare', 'go'),
                ('profile_update', 'profile_prepare', 'profile_commit')]:
            h = Harness()
            command = self.request(h, type=request_kind)
            h.wire.bind_request(command, self.fresh(h))
            h.wire.send(self.packet(command, prepare))
            h.wire.receive()
            h.clock.sleep(31.)
            with self.assertRaisesRegex(ValueError, 'Expired'):
                h.wire.send(self.packet(command, commit))
            self.assertEqual([p['type'] for p in h.inner.sent], [prepare])

    def test_protected_recovery_does_not_refresh_original_command(self):
        h = Harness([(2., TimeoutError('retry'))] * 4)
        command = self.request(h, expires_monotonic_ns=h.clock.ns() + 5_000_000_000)
        h.wire.bind_request(command, self.fresh(h))
        h.wire.capabilities = frozenset([COMMIT_WAIT_CAPABILITY])
        h.wire.send(self.packet(command, 'prepare'))
        h.wire.receive()
        with self.assertRaisesRegex(ValueError, 'Expired'):
            h.recovery.stationary(POSE, (2,), True)
        self.assertEqual([p['type'] for p in h.inner.sent], ['prepare'])

    def test_identity_and_geometry_cannot_borrow_another_lifetime(self):
        for change in ({'seq': 99}, {'command_digest': 'f' * 64}, {'type': 'profile_commit'},
                       {'target': [99., *POSE[1:]]}):
            h = Harness()
            command = self.request(h)
            h.wire.bind_request(command, self.fresh(h))
            with self.assertRaises(ValueError):
                h.wire.send({**self.packet(command, 'prepare'), **change})
            self.assertEqual(h.inner.sent, [])

    def test_scoped_adapter_restores_and_clears_on_base_exception(self):
        h = Harness()
        original = Mock()
        server = SimpleNamespace(preflight_request=original, fresh=self.fresh(h))
        command = self.request(h)
        with self.assertRaises(KeyboardInterrupt):
            with bind_request_lifetime(server, h.wire):
                server.preflight_request(command, 'reviewed arguments')
                self.assertEqual(h.wire.request, command)
                raise KeyboardInterrupt()
        original.assert_called_once_with(command, 'reviewed arguments')
        self.assertIs(server.preflight_request, original)
        self.assertIsNone(h.wire.request)
        self.assertIsNone(Harness().wire.request)

    def test_rejected_original_preflight_never_binds_request(self):
        h = Harness()
        server = SimpleNamespace(preflight_request=Mock(side_effect=ValueError('rejected')),
                                 fresh=self.fresh(h))
        with bind_request_lifetime(server, h.wire):
            with self.assertRaises(ValueError):
                server.preflight_request(self.request(h))
            self.assertIsNone(h.wire.request)


if __name__ == '__main__':
    unittest.main()
