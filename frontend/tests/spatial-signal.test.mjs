import assert from 'node:assert/strict';
import test from 'node:test';
import { spatialSignalState } from '../src/spatialSignal.ts';

const NOW = 1_800_000_000;
const MAP_HASH = 'a'.repeat(64);

function fixture(phase = 'admitted') {
  return {
    connected: true,
    now: NOW,
    workspace: { session_id: 'session-a', plan: { id: 'plan-a', revision: 3, route: { map_hash: MAP_HASH } } },
    status: {
      schema_version: 'pushpilot.physical.v1', enabled: true, available: true,
      mission_id: 'mission-a', plan_id: 'plan-a', plan_revision: 3, workspace_session_id: 'session-a',
      state: 'WAITING_SIGNAL', error: null, robot: { connected: true, stationary: true },
      signal: { color: 'GREEN', waiting: false, stable_green_frames: 2, required_green_frames: 2 },
      vision: { in_flight: false, kind: null },
      telemetry: { signal_gate_id: 'SOUTH_JUNCTION_NORTHBOUND_SIGNAL_WAIT', signal_observed_at: NOW - 3 },
    },
    snapshot: {
      schema_version: 'pushpilot.physical-display.v1', available: true, feed_fresh: true,
      mission_id: 'mission-a', plan_id: 'plan-a', plan_revision: 3, workspace_session_id: 'session-a', map_hash: MAP_HASH,
      state: 'WAITING_SIGNAL', phase: 'signal_wait', motion_authority: false,
      signal: { phase, green_count: 2, green_required: 2 },
      vehicle: { moving: false, confirmed_contact_stages: 0 },
    },
  };
}

const appearance = f => spatialSignalState(f.status, f.workspace, f.connected, f.snapshot, f.now);

test('only a server-admitted two-frame GREEN enables the Spatial green face', () => {
  assert.equal(appearance(fixture()), 'green-approved');
  for (const phase of ['none', 'waiting', 'confirming']) {
    assert.equal(appearance(fixture(phase)), 'base', `raw GREEN in ${phase} is not an admission`);
  }
  for (const color of ['RED', 'UNKNOWN']) {
    const f = fixture(); f.status.signal.color = color;
    assert.equal(appearance(f), 'base', color);
  }
  for (const patch of [
    { waiting: true }, { stable_green_frames: 0 }, { stable_green_frames: 1 },
    { stable_green_frames: undefined }, { stable_green_frames: 1.5 },
    { required_green_frames: undefined }, { required_green_frames: 0 }, { required_green_frames: 2.5 },
  ]) {
    const f = fixture(); Object.assign(f.status.signal, patch);
    assert.equal(appearance(f), 'base', JSON.stringify(patch));
  }
  const checking = fixture(); checking.status.vision = { in_flight: true, kind: 'signal' };
  assert.equal(appearance(checking), 'base', 'an outstanding signal check does not approve a face');
});

test('admission requires a fresh feed and a valid observation timestamp, without a second UI age limit', () => {
  for (const phase of ['admitted', 'recontacting', 'passed']) {
    for (const observedAt of [NOW + 1, 0, -1, NaN, Infinity, null, undefined]) {
      const f = fixture(phase); f.status.telemetry.signal_observed_at = observedAt;
      assert.equal(appearance(f), 'base', `${phase}: observation ${observedAt}`);
    }
    for (const age of [15, 15.001, 30, 600]) {
      const f = fixture(phase); f.status.telemetry.signal_observed_at = NOW - age;
      assert.equal(appearance(f), 'green-approved', `${phase}: server acceptance survives image age ${age}`);
    }
  }
  for (const now of [NaN, Infinity]) {
    const f = fixture(); f.now = now;
    assert.equal(appearance(f), 'base');
  }
  for (const phase of ['admitted', 'recontacting', 'passed']) {
    for (const fresh of [false, undefined]) {
      const f = fixture(phase); f.snapshot.feed_fresh = fresh;
      assert.equal(appearance(f), 'base', `${phase}, feed freshness ${fresh}`);
    }
  }
});

test('missing, disconnected, disabled, errored or ended evidence stays at the base state', () => {
  const changes = [
    ['status missing', f => { f.status = null; }],
    ['workspace missing', f => { f.workspace = null; }],
    ['plan missing', f => { f.workspace.plan = null; }],
    ['display missing', f => { f.snapshot = null; }],
    ['display unavailable', f => { f.snapshot.available = false; }],
    ['browser disconnected', f => { f.connected = false; }],
    ['robot disconnected', f => { f.status.robot.connected = false; }],
    ['disabled', f => { f.status.enabled = false; }],
    ['error', f => { f.status.error = 'Review unavailable'; }],
    ['gate missing', f => { f.status.telemetry.signal_gate_id = null; }],
    ['observation missing', f => { f.status.telemetry = undefined; }],
  ];
  for (const phase of ['admitted', 'recontacting', 'passed']) {
    for (const [label, change] of changes) {
      const f = fixture(phase); change(f);
      assert.equal(appearance(f), 'base', `${phase}: ${label}`);
    }
    for (const state of ['COMPLETE', 'COMPLETED', 'HOLD', 'HELD', 'STOPPING', 'FAILED', 'FAULT', 'ERROR',
      'CANCELLED', 'DISABLED', 'READY', 'IDLE', 'UNAVAILABLE']) {
      const f = fixture(phase); f.status.state = state;
      assert.equal(appearance(f), 'base', `${phase}: ${state}`);
    }
  }
});

test('another mission, plan, revision, workspace session or map cannot light this card', () => {
  const changes = [
    ['mission', f => { f.snapshot.mission_id = 'old-mission'; }],
    ['missing mission', f => { f.status.mission_id = null; }],
    ['status plan', f => { f.status.plan_id = 'old-plan'; }],
    ['display plan', f => { f.snapshot.plan_id = 'old-plan'; }],
    ['workspace plan', f => { f.workspace.plan.id = 'new-plan'; }],
    ['status revision', f => { f.status.plan_revision++; }],
    ['display revision', f => { f.snapshot.plan_revision++; }],
    ['workspace revision', f => { f.workspace.plan.revision++; }],
    ['status session', f => { f.status.workspace_session_id = 'old-session'; }],
    ['display session', f => { f.snapshot.workspace_session_id = 'old-session'; }],
    ['workspace session', f => { f.workspace.session_id = 'new-session'; }],
    ['display map', f => { f.snapshot.map_hash = 'b'.repeat(64); }],
    ['workspace map', f => { f.workspace.plan.route.map_hash = 'b'.repeat(64); }],
  ];
  for (const phase of ['admitted', 'recontacting', 'passed']) {
    for (const [label, change] of changes) {
      const f = fixture(phase); change(f);
      assert.equal(appearance(f), 'base', `${phase}: ${label}`);
    }
  }
});

test('accepted single-departure approval survives recontact and passage without replay or another wait', () => {
  const freeze = value => {
    if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
    return value;
  };
  for (const phase of ['recontacting', 'passed']) {
    const f = fixture(phase);
    f.status.state = phase === 'recontacting' ? 'RECONTACTING' : 'RUNNING';
    f.status.signal.stable_green_frames = 0;
    f.status.signal.color = 'UNKNOWN';
    f.status.telemetry.signal_observed_at = NOW - 600;
    f.snapshot.signal.green_count = 0;
    const before = structuredClone(f);
    freeze(f);
    assert.equal(appearance(f), 'green-approved', phase);
    assert.equal(appearance(f), 'green-approved', `${phase} repeated render`);
    assert.deepEqual(f, before, 'the display helper cannot mutate movement, waiting or admission records');
    assert.equal(f.status.signal.waiting, false);
    assert.equal(f.snapshot.motion_authority, false);
    assert.equal(f.snapshot.vehicle.moving, false);
    assert.equal(f.snapshot.vehicle.confirmed_contact_stages, 0);
  }
});
