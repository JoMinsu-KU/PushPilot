import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parsePhysicalStatus, physicalAvailable, physicalModeLabel, physicalProgress, physicalReviewLabel, physicalRouteContext, physicalTelemetry, physicalDeliveryDetail, physicalDeliveryLabel, physicalDestinationBlocker, physicalDetail, physicalFinished, physicalMatchesPlan, physicalParkingEnabled, physicalRunning, physicalSignalLabel, physicalStartCommand, physicalTitle, physicalVisionActive } from '../src/physicalMission.ts';

function status(overrides = {}) {
  return { schema_version: 'pushpilot.physical.v1', enabled: true, available: true, state: 'IDLE', revision: 4,
    mission_id: null, destination: null, stage_label: '', progress: { completed: 0, total: 0 },
    robot: { connected: true, stationary: true }, car: { arrived: false, aligned: false, heading_error_deg: null },
    signal: { color: 'UNKNOWN', waiting: false }, returning_home: false, error: null, blockers: [],
    capabilities: { autonomous: true, destinations: ['OFFICE_BUILDING', 'VILLA', 'HANOK'] }, ...overrides };
}
function workspace() {
  return { schema_version: 'pushpilot.workspace.v1', session_id: 'session-a', revision: 9, state: 'PLAN_READY', mode: 'simulation',
    goal: { provider: 'meta', destination: 'HANOK' }, plan: { id: 'plan-a', revision: 2, planning: { source: 'meta' },
      route: { map_id: 'city-a3', map_version: 'final.2', map_hash: 'exact-map-hash', destination: 'HANOK', node_ids: ['PIZZA', 'SOUTH', 'NORTH', 'HANOK'] } } };
}

test('physical start binds the exact MUSE plan and drawing route without sending robot coordinates', () => {
  const w = workspace(), result = physicalStartCommand(w, status(), 'request-1');
  assert.deepEqual(result, { request_id: 'request-1', expected_revision: 4, workspace_session_id: 'session-a', plan_id: 'plan-a', plan_revision: 2,
    destination: 'HANOK', route_nodes: ['PIZZA', 'SOUTH', 'NORTH', 'HANOK'], map_id: 'city-a3', map_version: 'final.2', map_hash: 'exact-map-hash' });
  result.route_nodes.pop();
  assert.equal(w.plan.route.node_ids.length, 4);
});

test('B Office, C Villa and D Hanok keep their exact selected-map routes and identities in physical start', () => {
  const map = JSON.parse(readFileSync(new URL('../../backend/data/seoul-city-a3.json', import.meta.url), 'utf8'));
  const routes = [
    ['B', 'OFFICE_BUILDING', ['PIZZA', 'S', 'OFFICE_BUILDING']],
    ['C', 'VILLA', ['PIZZA', 'S', 'C', 'VILLA']],
    ['D', 'HANOK', ['PIZZA', 'S', 'C', 'HANOK']],
  ];
  assert.deepEqual(new Set(routes.map(([, destination]) => destination)), new Set(map.destinations));
  for (const [taughtPoint, destination, nodeIds] of routes) {
    for (let i = 1; i < nodeIds.length; i += 1) {
      assert.ok(map.edges.some(edge => edge.from === nodeIds[i - 1] && edge.to === nodeIds[i]
        || edge.bidirectional && edge.to === nodeIds[i - 1] && edge.from === nodeIds[i]), `${taughtPoint}: drawing edge is present`);
    }
    const w = workspace();
    w.goal.destination = destination;
    w.plan.id = `muse-plan-${taughtPoint}`;
    w.plan.route = { ...w.plan.route, map_id: map.id, map_version: map.version,
      map_hash: `server-bound-${taughtPoint}-map-hash`, destination, node_ids: nodeIds };
    const result = physicalStartCommand(w, status(), `request-${taughtPoint}`);
    assert.deepEqual(result, { request_id: `request-${taughtPoint}`, expected_revision: 4,
      workspace_session_id: w.session_id, plan_id: w.plan.id, plan_revision: w.plan.revision,
      destination, route_nodes: nodeIds, map_id: map.id, map_version: map.version,
      map_hash: `server-bound-${taughtPoint}-map-hash` });
    assert.notEqual(result.route_nodes, nodeIds, 'submitted route cannot mutate the displayed plan');
  }
});

test('missing, empty or unlisted server destinations cannot start, even when the robot is ready', () => {
  for (const capabilities of [{ autonomous: true }, { destinations: [] }, { destinations: ['OFFICE_BUILDING', 'VILLA'] }]) {
    const s = parsePhysicalStatus(status({ capabilities }));
    assert.equal(physicalAvailable(s), true, 'service availability does not grant destination authority');
    assert.ok(physicalDestinationBlocker(s, 'HANOK'));
    assert.throws(() => physicalStartCommand(workspace(), s, 'r'), /destinations|installed robot routes/);
  }
  assert.equal(physicalDestinationBlocker(status(), 'HANOK'), null);
  assert.equal(physicalDestinationBlocker(status(), 'hanok'), 'hanok is not available in the installed robot routes.');
  assert.equal(physicalDestinationBlocker(status({ capabilities: { destinations: ['HANOK'] } }), 'OFFICE_BUILDING', 'Office Building'),
    'Office Building is not available in the installed robot routes.');
  assert.match(physicalDestinationBlocker(status({ capabilities: {} }), 'HANOK'), /not confirmed/);
});

test('destination capability parsing accepts a distinct ID list and rejects malformed authority', () => {
  for (const destinations of [true, 'HANOK', [true], [''], [' HANOK'], ['HANOK '], ['HANOK', 'HANOK'], null]) {
    assert.throws(() => parsePhysicalStatus(status({ capabilities: { destinations } })));
  }
  assert.throws(() => parsePhysicalStatus(status({ capabilities: { unsupported_array: ['HANOK'] } })));
  assert.deepEqual(parsePhysicalStatus(status({ capabilities: { destinations: [] } })).capabilities.destinations, []);
  assert.deepEqual(parsePhysicalStatus(status({ capabilities: {} })).capabilities, {}, 'old status remains readable, not startable');
});

test('demo, unbound plans, moving robots and mismatched destinations cannot start physical missions', () => {
  for (const mutate of [w => w.goal.provider = 'demo', w => w.plan.planning = undefined, w => w.state = 'READY', w => w.goal.destination = 'VILLA', w => w.plan.route.node_ids.pop()]) {
    const w = workspace(); mutate(w);
    assert.throws(() => physicalStartCommand(w, status(), 'r'));
  }
  for (const s of [status({ enabled: false }), status({ available: false }), status({ robot: { connected: false, stationary: true } }), status({ robot: { connected: true, stationary: false } }), status({ state: 'WAITING_SIGNAL', mission_id: 'm' })]) {
    assert.throws(() => physicalStartCommand(workspace(), s, 'r'));
  }
});

test('missing or malformed status never becomes physical authority', () => {
  assert.deepEqual(parsePhysicalStatus(status()), status());
  for (const p of [null, {}, { mode: 'physical' }, status({ revision: -1 }), status({ progress: { completed: 3, total: 2 } }),
    status({ signal: { color: 'GREEN', waiting: 'false' } }), status({ robot: {} }), status({ capabilities: { ready: 'true' } }),
    status({ car: { arrived: true, aligned: true, heading_error_deg: Number.NaN } })]) assert.throws(() => parsePhysicalStatus(p));
  assert.equal(physicalAvailable(status({ enabled: false })), false);
  assert.equal(physicalAvailable(status({ available: false })), false);
});

test('signal waiting, recontact, correction, alignment and return remain automatic active phases', () => {
  for (const state of ['WAITING_SIGNAL', 'RECONTACTING', 'CORRECTING', 'ALIGNING', 'RETURNING_HOME', 'HOLD', 'NEW_EXECUTOR_PHASE']) {
    assert.equal(physicalRunning(status({ mission_id: 'm', state })), true);
  }
  assert.match(physicalDetail(status({ state: 'WAITING_SIGNAL' }), true), /automatic continuation/);
  assert.equal(physicalTitle(status({ state: 'ALIGNING' }), true), 'Aligning at destination');
  assert.equal(physicalTitle(status({ returning_home: true }), true), 'Returning to start');
});

test('arrival does not invent alignment or robot home, and lost status cannot show confirmed completion', () => {
  const s = status({ state: 'COMPLETE', mission_id: 'm', capabilities: { parking_alignment: true }, car: { arrived: true, aligned: false, heading_error_deg: null } });
  assert.equal(physicalFinished(s), true);
  assert.equal(physicalRunning(s), false);
  assert.match(physicalDetail(s, true), /reported separately/);
  assert.equal(physicalTitle(s, false), 'Robot status unavailable');
  assert.match(physicalDetail(s, false), /not confirmed/);
});

test('delivery-first completion reports arrival without requiring or inventing parking alignment', () => {
  for (const capabilities of [{}, { parking_alignment: false }]) {
    const s = parsePhysicalStatus(status({ state: 'COMPLETE', mission_id: 'm', capabilities,
      car: { arrived: true, aligned: false, heading_error_deg: 18 } }));
    assert.equal(physicalParkingEnabled(s), false);
    assert.match(physicalDetail(s, true), /^Car delivered\./);
    assert.doesNotMatch(physicalDetail(s, true), /aligned|parking/);
    assert.equal(physicalDeliveryLabel(s, true), 'Arrival confirmed');
    assert.doesNotMatch(physicalDeliveryDetail(s, true), /alignment/);
    assert.equal(s.car.aligned, false, 'presentation must not manufacture an alignment result');
    assert.equal(s.robot.at_start, undefined, 'arrival does not imply automatic return already finished');
    assert.equal(physicalDeliveryLabel(s, false), 'Status unavailable');
  }
  const incomplete = status({ state: 'COMPLETE', car: { arrived: false, aligned: false, heading_error_deg: null } });
  assert.match(physicalDetail(incomplete, true), /arrival is not confirmed/);
});

test('parking is opt-in while actual return and correction states remain observable', () => {
  const s = status({ capabilities: { parking_alignment: true }, car: { arrived: true, aligned: false, heading_error_deg: 18 } });
  assert.equal(physicalParkingEnabled(s), true);
  assert.equal(physicalDeliveryDetail(s, true), 'Parking alignment not yet confirmed');
  assert.equal(physicalDeliveryLabel({ ...s, car: { ...s.car, aligned: true } }, true), 'Parked and aligned');
  const delivery = { ...s, capabilities: { parking_alignment: false }, state: 'RETURNING_HOME', returning_home: true };
  assert.equal(physicalDeliveryLabel(delivery, true), 'Returning to start');
  assert.equal(physicalDeliveryLabel({ ...delivery, state: 'HOLD' }, true), 'Arrival confirmed');
  assert.equal(physicalDeliveryLabel({ ...delivery, state: 'ALIGNING', returning_home: false }, true), 'Aligning the car');
  assert.throws(() => parsePhysicalStatus(status({ capabilities: { parking_alignment: 'false' } })));
});

test('a previous physical result is shown only for its exact session and plan revision', () => {
  const w = workspace();
  const s = status({ mission_id: 'm', state: 'COMPLETE', plan_id: 'plan-a', plan_revision: 2, workspace_session_id: 'session-a' });
  assert.equal(physicalMatchesPlan(s, w), true);
  for (const change of [{ plan_id: 'other' }, { plan_revision: 3 }, { workspace_session_id: 'session-b' }, { plan_id: undefined }]) {
    assert.equal(physicalMatchesPlan({ ...s, ...change }, w), false);
  }
});

test('terminal hold and server blockers retain their actual reasons', () => {
  assert.equal(physicalDetail(status({ state: 'HOLD', error: 'Parking correction made no progress.' }), true), 'Parking correction made no progress.');
  assert.equal(physicalDetail(status({ available: false, blockers: ['A qualified signal target is required.'] }), true), 'A qualified signal target is required.');
});

test('MUSE visual activity only runs for the actual current request kind and a connected service', () => {
  const s = status({ state: 'WAITING_SIGNAL', vision: { in_flight: true, kind: 'signal', started_at: 1, last_result_at: null, summary: null } });
  assert.equal(physicalVisionActive(s, true, 'signal'), true);
  assert.equal(physicalVisionActive(s, true, 'car'), false);
  assert.equal(physicalVisionActive(s, false, 'signal'), false);
  assert.equal(physicalVisionActive({ ...s, vision: { ...s.vision, in_flight: false } }, true, 'signal'), false);
  assert.equal(physicalSignalLabel(s, true), 'Checking signal · MUSE');
});

test('green confirmation uses server observations without implying crossing permission from color alone', () => {
  const s = status({ state: 'WAITING_SIGNAL', signal: { color: 'GREEN', waiting: true, stable_green_frames: 1, required_green_frames: 2 } });
  assert.equal(physicalSignalLabel(s, true), 'Confirming green (1/2)');
  s.signal.stable_green_frames = 2;
  assert.equal(physicalSignalLabel(s, true), 'Green confirmed');
  s.state = 'RECONTACTING';
  assert.equal(physicalSignalLabel(s, true), 'Recontacting');
  assert.equal(physicalSignalLabel(status({ signal: { color: 'RED', waiting: true } }), true), 'Red · Waiting');
  assert.equal(physicalSignalLabel(s, false), 'Status unavailable');
});

function telemetry(overrides = {}) {
  return { sequence: [
    { id: 'push-b', label: 'Push toward Office', kind: 'push', status: 'complete', detail: 'Native executor receipt recorded.' },
    { id: 'clear-b', label: 'Clear the camera view', kind: 'observe_clear', status: 'current', detail: 'Moving the empty tool.' },
    { id: 'return-b', label: 'Return to start', kind: 'return', status: 'pending', detail: 'Not dispatched.' },
  ], current_step_id: 'clear-b', history: [{ id: 'receipt-1', at: 1793200000, kind: 'PRIMITIVE_RECEIPT', title: 'Push completed', detail: 'Receipt native-123.', source: 'executor' }],
    review: { verdict: 'ARRIVED', summary: 'Vehicle visible at the destination.', observed_at: 1793200001, source: 'meta', frame_ids: ['native-before', 'native-after'] },
    signal_gate_id: null, signal_observed_at: null, distance_mm: null, distance_source: null, ...overrides };
}

test('physical telemetry never borrows simulator progress, reviews or history', () => {
  const w = workspace();
  Object.assign(w, { current_step: 99, events: [{ title: 'Fake arrival' }], review: { verdict: 'PASS' } });
  const s = status({ mission_id: 'm', state: 'RUNNING', progress: { completed: 1, total: 3 }, telemetry: telemetry() });
  const actual = physicalTelemetry(parsePhysicalStatus(s), w, true);
  assert.equal(actual, s.telemetry);
  assert.deepEqual(physicalProgress(s, actual), { completed: 1, total: 3 });
  assert.equal(actual.history[0].title, 'Push completed');
  assert.equal(physicalReviewLabel(s, actual, true), 'ARRIVED');
  assert.deepEqual(physicalRouteContext(actual).steps.map(step => step.status), ['complete', 'current', 'pending']);
  const missing = { ...s, telemetry: undefined };
  assert.equal(physicalTelemetry(missing, w, true), null);
  assert.equal(physicalProgress(missing, null), null);
  assert.equal(physicalReviewLabel(missing, null, true), 'No robot review');
  assert.deepEqual(physicalRouteContext(null), { start: 0, steps: [] });
});

test('disconnected, previous and unbound physical telemetry cannot appear as current results', () => {
  const s = status({ mission_id: 'old-m', state: 'COMPLETE', plan_id: 'plan-a', plan_revision: 2,
    workspace_session_id: 'session-a', telemetry: telemetry(), progress: { completed: 3, total: 3 } });
  assert.equal(physicalTelemetry(s, workspace(), true), s.telemetry);
  assert.equal(physicalTelemetry(s, workspace(), false), null);
  assert.equal(physicalTelemetry({ ...s, plan_revision: 1 }, workspace(), true), null);
  assert.equal(physicalTelemetry({ ...s, workspace_session_id: 'old' }, workspace(), true), null);
  assert.equal(physicalTelemetry({ ...s, mission_id: null }, workspace(), true), null);
  assert.equal(physicalReviewLabel(s, null, false), 'Review unavailable');
});

test('telemetry rejects inferred distance, malformed receipts and fabricated review sources', () => {
  assert.deepEqual(parsePhysicalStatus(status({ telemetry: telemetry() })).telemetry, telemetry());
  assert.equal(parsePhysicalStatus(status({ telemetry: telemetry({ distance_mm: 42.3, distance_source: 'native_tcp' }) })).telemetry.distance_mm, 42.3);
  for (const t of [null, {}, telemetry({ distance_mm: 500, distance_source: 'drawing' }), telemetry({ distance_mm: 500, distance_source: null }),
    telemetry({ distance_mm: -1, distance_source: 'native_tcp' }), telemetry({ current_step_id: 'not-in-sequence' }),
    telemetry({ sequence: [{ ...telemetry().sequence[0], status: 'estimated' }] }),
    telemetry({ history: [{ ...telemetry().history[0], at: Number.NaN }] }),
    telemetry({ review: { ...telemetry().review, source: 'demo' } }), telemetry({ review: { ...telemetry().review, observed_at: 'now' } })]) {
    assert.throws(() => parsePhysicalStatus(status({ telemetry: t })));
  }
});

test('actual inference activity is distinct from the last recorded review and signal wait', () => {
  const s = status({ mission_id: 'm', state: 'WAITING_SIGNAL', telemetry: telemetry(),
    vision: { in_flight: false, kind: 'signal', started_at: null, last_result_at: 1793200001, summary: 'Previous result' } });
  assert.equal(physicalReviewLabel(s, s.telemetry, true), 'ARRIVED');
  assert.equal(physicalVisionActive(s, true, 'signal'), false);
  s.vision.in_flight = true;
  assert.equal(physicalReviewLabel(s, s.telemetry, true), 'Checking signal · MUSE');
  s.vision.kind = 'car';
  assert.equal(physicalReviewLabel(s, s.telemetry, true), 'Checking car · MUSE');
  assert.equal(physicalReviewLabel(s, null, false), 'Review unavailable');
});

test('current-site testing is explicitly labeled and grants no route capability', () => {
  const s = parsePhysicalStatus(status({ available: false, capabilities: { release_mode: 'site_trial', destinations: [] } }));
  assert.equal(physicalModeLabel(s), 'Robot · current-site test');
  assert.throws(() => physicalStartCommand(workspace(), s, 'r'));
  assert.equal(physicalModeLabel(status({ capabilities: { release_mode: 'qualified' } })), 'Robot');
  assert.throws(() => parsePhysicalStatus(status({ capabilities: { release_mode: 'pretend_ready' } })));
});
