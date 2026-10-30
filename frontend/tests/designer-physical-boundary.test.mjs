import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

// Vite compiles the real UI components; middleware mode never listens on a network port.
globalThis.window = { matchMedia: () => ({ matches: false }) };
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), configFile: false, server: { middlewareMode: true, watch: null }, appType: 'custom' });
test.after(() => server.close());
const { PhysicalRouteBrowser, PhysicalHistoryBrowser, executionStepLabel, signalGateLabel, physicalSequenceFocus } = await server.ssrLoadModule('/src/WorkspaceUI.tsx');
const telemetry = () => ({
  sequence: Array.from({ length: 31 }, (_, n) => ({ id: `C-step-${n}`, label: `C-step-${n}`, kind: n > 26 ? 'RETURN_HOME' : 'MOVE', detail: `Actual executor receipt ${n}`, status: n < 13 ? 'complete' : n === 13 ? 'current' : 'pending' })),
  history: Array.from({ length: 77 }, (_, n) => ({ id: `actual-${n}`, at: 1793320000 + n, title: `Recorded outcome ${n}`, kind: 'motion', source: 'native', detail: `Original outcome ${n}` })),
  current_step_id: 'C-step-13', distance_mm: null, distance_source: null, review: null, signal_gate_id: null, signal_observed_at: null,
});
test('physical route renders all 31 actual rows and real receipt count without simulator distance', () => {
  const html = renderToStaticMarkup(React.createElement(PhysicalRouteBrowser, { status: { mission_id: 'mission-a', destination: 'VILLA', progress: { completed: 13, total: 31 } }, telemetry: telemetry(), connected: true, map: null }));
  assert.equal((html.match(/class="route-number"/g) ?? []).length, 31);
  assert.match(html, /13 \/ 31/); assert.match(html, /C-step-30/); assert.match(html, /Not measured/);
  assert.doesNotMatch(html, /314|drawing mm|Route page navigation/);
});
test('physical Mission Log preserves all 77 actual records and selected record identity', () => {
  const html = renderToStaticMarkup(React.createElement(PhysicalHistoryBrowser, { telemetry: telemetry(), connected: true }));
  assert.equal((html.match(/Recorded outcome \d+<\/strong>/g) ?? []).length, 77);
  assert.match(html, /Original outcome 76/); assert.match(html, /actual-76/); assert.match(html, /native/);
  assert.doesNotMatch(html, /Timeline page navigation/);
});
test('unavailable telemetry stays unavailable without simulator completion', () => {
  const html = renderToStaticMarkup(React.createElement(PhysicalRouteBrowser, { status: null, telemetry: null, connected: false, map: null }));
  assert.match(html, /Robot telemetry is unavailable/); assert.match(html, /Awaiting execution/);
  assert.doesNotMatch(html, /route-number|Mission complete/);
});
test('display label shortening never changes source IDs', () => {
  const step = { label: 'C-step-26', id: 'C-step-26', kind: 'MOVE' };
  assert.equal(executionStepLabel(step), 'C · Step 26'); assert.equal(step.id, 'C-step-26');
  assert.equal(signalGateLabel('SOUTH_JUNCTION_NORTHBOUND_SIGNAL_WAIT'), 'South Junction');
  const recontact = { label: 'D-fixed-plan-review-20261029T012151991079Z/signal-recontact', id: 'D-fixed-plan-review-20261029T012151991079Z/signal-recontact', kind: 'MOVE' };
  assert.equal(executionStepLabel(recontact), 'Recontact vehicle');
  assert.equal(recontact.id, 'D-fixed-plan-review-20261029T012151991079Z/signal-recontact');
});
test('native dialogs preserve the Stop request while Start remains blocked in Mission Log', () => {
  const source = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.match(source, /kind === 'start' && view === 'Replay'/);
  assert.match(source, /actions=\{robotMission && !robotFinished \? renderStopAction\(\)/);
  assert.match(source, /physicalBusy \|\| physicalUnconfirmed === kind/);
  assert.match(source, /expected_revision: physical.status.revision/);
});

test('held sequence without current ID anchors after the last real completion without changing pending status', () => {
  const data = telemetry();
  data.sequence = data.sequence.map((step, index) => ({ ...step, status: index < 18 ? 'complete' : 'pending' }));
  data.current_step_id = null;
  const before = JSON.stringify(data.sequence);
  assert.equal(physicalSequenceFocus(data.sequence, null), 18);
  assert.equal(physicalSequenceFocus(data.sequence, 'C-step-10'), 10, 'an explicit current step takes priority');
  assert.equal(JSON.stringify(data.sequence), before, 'a display anchor cannot rewrite pending as current');
  const html = renderToStaticMarkup(React.createElement(PhysicalRouteBrowser, { status: { state: 'HOLD', mission_id: 'mission-a', destination: 'VILLA', progress: { completed: 18, total: 31 } }, telemetry: data, connected: true, map: null }));
  assert.match(html, /class="pending focused"/);
  assert.match(html, /pending · C-step-18/);
  assert.equal((html.match(/class="route-number"/g) ?? []).length, 31);
  assert.equal(physicalSequenceFocus(data.sequence.map(step => ({ ...step, status: 'complete' })), null), 30);
  assert.equal(physicalSequenceFocus([], null), -1);
});
