import assert from 'node:assert/strict';
import test from 'node:test';
import { createRouteDisplay, currentSignalJunction, projectRouteDisplay, routeLabelLayout, signalDisplay } from '../src/routeProgress.ts';
import { projectPoint } from '../src/projection.ts';

const now = Date.parse('2026-10-27T09:00:00Z');
function fixture() {
  const map = { id: 'replacement-print', version: 'new-layout.2', geometry_hash: 'replacement-hash',
    nodes: [{ id: 'DEPOT' }, { id: 'JUNCTION-42' }, { id: 'MUSEUM' }] };
  const route = { map_id: map.id, map_version: map.version, map_hash: map.geometry_hash,
    start: 'DEPOT', destination: 'MUSEUM', points_mm: [[0, 0], [50, 0], [50, 50]], distance_mm: 100,
    visualization: { schema_version: 'pushpilot.route-display.v1', source: 'drawing_only', segments: [
      { id: 'approach', kind: 'push', from_node_id: 'DEPOT', to_node_id: 'JUNCTION-42', junction_id: 'JUNCTION-42', points_mm: [[0, 0], [40, 0]], length_mm: 40 },
      { id: 'crossing', kind: 'crossing', from_node_id: 'JUNCTION-42', to_node_id: 'JUNCTION-42', junction_id: 'JUNCTION-42', points_mm: [[40, 0], [50, 0], [50, 10]], length_mm: 20 },
      { id: 'arrival', kind: 'push', from_node_id: 'JUNCTION-42', to_node_id: 'MUSEUM', junction_id: null, points_mm: [[50, 10], [50, 50]], length_mm: 40 },
    ], junctions: [{ node_id: 'JUNCTION-42', label: 'North junction', center_mm: [50, 0], stop_point_mm: [40, 0], stop_line_mm: [[40, -5], [40, 5]], exit_point_mm: [50, 10], approach_segment_id: 'approach', crossing_segment_id: 'crossing' }] } };
  const steps = [
    { id: '0', kind: 'PUSH', node_id: 'JUNCTION-42', route_segment_id: 'approach', status: 'pending', label: 'Approach North junction' },
    { id: '1', kind: 'STOP', node_id: 'JUNCTION-42', status: 'pending', label: 'Stop' },
    { id: '2', kind: 'CROSS', node_id: 'JUNCTION-42', route_segment_id: 'crossing', status: 'pending', label: 'Cross' },
    { id: '3', kind: 'PUSH', node_id: 'MUSEUM', route_segment_id: 'arrival', status: 'pending', label: 'Approach Museum' },
    { id: '4', kind: 'VERIFY', node_id: 'MUSEUM', status: 'pending', label: 'Verify Museum' },
  ];
  const workspace = { mode: 'simulation', state: 'PLAN_READY', approved: false, stopped: false, current_step: 0, plan: { route, steps },
    signal: { source: 'simulation', junction_id: 'JUNCTION-42', color: 'GREEN', observed_at: new Date(now - 1000).toISOString(), freshness_limit_ms: 30_000 } };
  return { map, route, workspace, steps };
}
function at(f, index, state = 'READY') {
  f.workspace.current_step = index; f.workspace.state = state; f.workspace.approved = true;
  f.steps.forEach((step, n) => step.status = n < index ? 'complete' : n === index ? 'current' : 'pending');
  return createRouteDisplay(f.route, f.map, f.workspace, now);
}

test('arbitrary replacement map uses supplied route segments without hardcoded place IDs', () => {
  const f = fixture(), display = at(f, 0);
  assert.equal(display.detailed, true);
  assert.equal(display.source, 'Simulation progress');
  assert.deepEqual(display.segments.map(segment => segment.phase), ['current', 'upcoming', 'upcoming']);
  assert.equal(display.junctions[0].label, 'North junction');
});

test('unapproved plans remain wholly planned even if inconsistent stored statuses say complete', () => {
  const f = fixture(); f.steps[0].status = 'complete';
  const display = createRouteDisplay(f.route, f.map, f.workspace, now);
  assert.equal(display.source, 'Planned route');
  assert.equal(display.awaitingApproval, true);
  assert.ok(display.segments.every(segment => segment.phase === 'planned'));
});

test('cancelling an unapproved pending plan does not invent executed or faulted progress', () => {
  const f = fixture(); f.workspace.state = 'CANCELLED';
  const display = createRouteDisplay(f.route, f.map, f.workspace, now);
  assert.equal(display.source, 'Planned route');
  assert.equal(display.awaitingApproval, false);
  assert.equal(display.currentLabel, 'Plan cancelled · no execution');
  assert.ok(display.segments.every(segment => segment.phase === 'planned'));
  assert.ok(display.junctions.every(junction => !junction.active));
  f.workspace.state = 'READY'; f.workspace.approved = true;
  assert.equal(createRouteDisplay(f.route, f.map, f.workspace, now).segments[0].phase, 'upcoming');
});

test('completed segment requires accepted supervisor review; action receipt alone is pending review', () => {
  const f = fixture(), pending = at(f, 0, 'REVIEW_REQUIRED');
  assert.equal(pending.segments[0].phase, 'review'); assert.equal(pending.completed, 0);
  const accepted = at(f, 1);
  assert.equal(accepted.segments[0].phase, 'complete'); assert.equal(accepted.completed, 1);
});

test('green before mandatory stopping does not admit or highlight a crossing', () => {
  const f = fixture(), display = at(f, 1);
  assert.equal(display.junctions[0].status, 'Mandatory stop');
  assert.equal(display.segments[1].phase, 'upcoming');
  const review = at(f, 1, 'REVIEW_REQUIRED');
  assert.equal(review.junctions[0].status, 'Stop · review pending');
  assert.equal(review.segments[1].phase, 'upcoming');
});

test('red at verified stop remains waiting; green cannot itself advance display progress', () => {
  const f = fixture(); f.workspace.signal.color = 'RED';
  let display = at(f, 1, 'WAITING_SIGNAL'); f.steps[1].status = 'complete';
  display = createRouteDisplay(f.route, f.map, f.workspace, now);
  assert.equal(display.junctions[0].status, 'Red · waiting'); assert.equal(display.segments[1].phase, 'waiting');
  f.workspace.signal.color = 'GREEN'; display = createRouteDisplay(f.route, f.map, f.workspace, now);
  assert.equal(display.junctions[0].status, 'Green · awaiting admission');
  assert.equal(display.segments[1].phase, 'waiting');
});

test('missing, wrong-junction, stale, future and unsupported-source signals cannot display a usable color', () => {
  for (const change of [{ observed_at: null }, { junction_id: 'OTHER' }, { observed_at: new Date(now + 1).toISOString() }, { freshness_limit_ms: undefined }, { source: 'meta' }]) {
    const f = fixture(); Object.assign(f.workspace.signal, change);
    assert.equal(signalDisplay(f.workspace, 'JUNCTION-42', now), 'unknown');
  }
  const f = fixture(); f.workspace.signal.observed_at = new Date(now - 30_001).toISOString();
  assert.equal(signalDisplay(f.workspace, 'JUNCTION-42', now), 'stale');
  const display = at(f, 1, 'WAITING_SIGNAL');
  assert.equal(display.junctions[0].status, 'Signal stale · waiting');
});

test('signal scope follows the current approach/stop/crossing and clears at arrival or termination', () => {
  const f = fixture();
  for (const index of [0, 1, 2]) { at(f, index); assert.equal(currentSignalJunction(f.workspace), 'JUNCTION-42'); }
  for (const index of [3, 4]) { at(f, index); assert.equal(currentSignalJunction(f.workspace), null); }
  at(f, 1, 'CANCELLED'); assert.equal(currentSignalJunction(f.workspace), null);
  assert.equal(currentSignalJunction(null), null);
});

test('admitted crossing stays active during later red and cannot be rolled back by display color', () => {
  const f = fixture(); f.workspace.signal.color = 'RED';
  const display = at(f, 2, 'REVIEW_REQUIRED');
  assert.equal(display.segments[1].phase, 'review');
  assert.equal(display.junctions[0].status, 'Crossing · review pending');
  assert.notEqual(display.segments[1].phase, 'waiting');
});

test('reobserve and faults retain reviewed history and do not declare current motion complete', () => {
  const f = fixture(); const reobserve = at(f, 2, 'REOBSERVE');
  assert.equal(reobserve.segments[0].phase, 'complete'); assert.equal(reobserve.segments[1].phase, 'review');
  const fault = at(f, 2, 'FAULT'); f.workspace.approved = false;
  assert.equal(fault.segments[1].phase, 'fault'); assert.equal(fault.completed, 1);
});

test('completion comes from reviewed steps and supervisor terminal state, without estimating car pose', () => {
  const f = fixture(); at(f, 4, 'COMPLETED'); f.steps[4].status = 'complete'; f.workspace.approved = false;
  const display = createRouteDisplay(f.route, f.map, f.workspace, now);
  assert.ok(display.segments.every(segment => segment.phase === 'complete'));
  assert.equal(display.currentLabel, 'Route reviewed'); assert.equal('car_pose' in display, false);
});

test('legacy and malformed visualization use full planned route rather than guessed step offsets', () => {
  for (const mutate of [f => delete f.route.visualization, f => f.route.visualization.segments[0].length_mm = -1,
    f => f.route.visualization.segments[1].points_mm[0] = [41, 0], f => f.steps[2].route_segment_id = 'missing',
    f => f.route.visualization.junctions[0] = null, f => f.route.visualization.segments[0].points_mm[0][0] = NaN]) {
    const f = fixture(); at(f, 2); mutate(f);
    const display = createRouteDisplay(f.route, f.map, f.workspace, now);
    assert.equal(display.detailed, false); assert.equal(display.segments[0].phase, 'planned');
    assert.equal(display.awaitingApproval, false);
  }
});

test('malformed step nodes and approach junction bindings cannot color a different drawing segment', () => {
  for (const mutate of [f => f.steps[0].node_id = 'MUSEUM', f => f.steps[2].node_id = 'DEPOT',
    f => f.route.visualization.segments[0].junction_id = 'MUSEUM']) {
    const f = fixture(); at(f, 2); mutate(f);
    assert.equal(createRouteDisplay(f.route, f.map, f.workspace, now).detailed, false);
  }
});

test('changed map identity/version/hash suppresses route; a different workspace route cannot color history', () => {
  for (const key of ['id', 'version', 'geometry_hash']) {
    const f = fixture(); f.map[key] = 'changed';
    assert.equal(createRouteDisplay(f.route, f.map, f.workspace, now), null);
  }
  const f = fixture(); at(f, 2); f.workspace.plan.route = structuredClone(f.route);
  assert.equal(createRouteDisplay(f.route, f.map, f.workspace, now).detailed, false);
});

test('path, crossing, stop line and label anchors share exactly the same homography', () => {
  const f = fixture(), display = at(f, 1), matrix = [[2, .1, 200], [.2, 3, 80], [.001, 0, 1]];
  const project = point => projectPoint(point, matrix);
  const original = structuredClone(display), actual = projectRouteDisplay(display, project);
  assert.deepEqual(actual.segments[1].points_mm, display.segments[1].points_mm.map(project));
  assert.deepEqual(actual.junctions[0].stop_line_mm, display.junctions[0].stop_line_mm.map(project));
  assert.deepEqual(actual.junctions[0].stop_point_mm, project(display.junctions[0].stop_point_mm));
  assert.deepEqual(display, original);
  assert.equal(projectRouteDisplay(display, () => null), null);
});

test('zero-length adjacent-junction approach remains valid and makes no invented movement', () => {
  const f = fixture(); const first = f.route.visualization.segments[0];
  first.points_mm = [[40, 0], [40, 0]]; first.length_mm = 0; f.route.points_mm[0] = [40, 0];
  const display = at(f, 0);
  assert.equal(display.detailed, true); assert.equal(display.segments[0].length_mm, 0);
});

test('long junction labels are truncated within the projected board near every edge', () => {
  const status = 'C · Red · waiting';
  assert.equal(routeLabelLayout([100, 100], status, 1, [[0, 0], [600, 0], [600, 300], [0, 300]]).text, status);
  const boundary = [[20, 0], [220, 20], [200, 140], [0, 120]];
  for (const anchor of [[30, 10], [210, 30], [190, 130], [10, 110]]) {
    const layout = routeLabelLayout(anchor, 'A very long junction label '.repeat(4), 1, boundary);
    assert.ok(layout); assert.ok(layout.text.endsWith('…')); assert.ok(layout.text.length < 100);
    const corners = [[layout.x, layout.y], [layout.x + layout.width, layout.y], [layout.x + layout.width, layout.y + layout.height], [layout.x, layout.y + layout.height]];
    for (const corner of corners) for (let i = 0; i < boundary.length; i++) {
      const first = boundary[i], last = boundary[(i + 1) % boundary.length];
      assert.ok((last[0] - first[0]) * (corner[1] - first[1]) - (last[1] - first[1]) * (corner[0] - first[0]) >= -1e-6);
    }
  }
  assert.equal(routeLabelLayout([0, 0], 'Status', 1, [[0, 0], [10, 0], [10, 8], [0, 8]]), null);
});
