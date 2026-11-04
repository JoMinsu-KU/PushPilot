// Tests for reviewed site-trial primitive titles.
// Offline node:test; labels never guess across recipes.
import assert from 'node:assert/strict';
import test from 'node:test';
import { executionStepLabel } from '../src/executionLabels.ts';

function row(id, label = 'C-step-1', kind = 'route') {
  return { id, label, kind, status: 'pending', detail: 'Awaiting robot execution' };
}

test('reviewed primitive identity supplies action intent rather than an inferred numbered-step action', () => {
  assert.equal(executionStepLabel(row('B-delivery-group-1', 'B-step-1')), 'Leave Pizza shop');
  assert.equal(executionStepLabel(row('B-delivery-group-6', 'B-step-6')), 'Deliver at Office Building');
  assert.equal(executionStepLabel(row('D-fixed-plan-review-20261029T040356680813Z', 'C-step-9')), 'Begin the left turn');
  assert.equal(executionStepLabel(row('C-west-course-review-20261028T231958806301Z', 'C-step-26')), 'Deliver at Villa');
  assert.equal(executionStepLabel(row('D-fixed-plan-review-20261029T055617515443Z', 'D-step-22')), 'Deliver at Hanok');
  assert.equal(executionStepLabel(row('new-replacement-recipe', 'C-step-9')), 'C-step-9');
});

test('unloaded reposition and wrist rows remain distinct from vehicle contact actions', () => {
  assert.equal(executionStepLabel(row('empty:ba9c623a-6537-42c6-abaf-cc7a7154ab4b')), 'Reposition the gripper');
  assert.equal(executionStepLabel(row('C-upper-unloaded-WEST', 'C-step-18')), 'Orient the gripper for Villa');
  assert.equal(executionStepLabel(row('NEW-D-biased-nine-point-nine-extension/unloaded-prefix', 'D-step-16-empty')), 'Reposition the gripper');
  assert.equal(executionStepLabel(row('NEW-D-biased-nine-point-nine-extension/contact-unit', 'D-step-16')), 'Advance into the junction');
});

test('actual runtime signal recontact and post-green push get distinct titles without inventing a wait row', () => {
  const recontact = 'D-fixed-plan-review-20261029T012151991079Z/signal-recontact';
  assert.equal(executionStepLabel(row(recontact, recontact, 'signal_recontact')), 'Recontact the car');
  assert.equal(executionStepLabel(row(`${recontact}:8dfed780d46b44609f78a0f117c4b9c2`, recontact, 'signal_recontact')), 'Recontact the car');
  assert.equal(executionStepLabel(row(`${recontact}:8dfed780-d46b-4460-9f78-a0f117c4b9c2`)), 'Recontact the car');
  assert.equal(executionStepLabel(row(`${recontact}:unrecognized-suffix`, 'Server label')), 'Server label');
  assert.equal(executionStepLabel(row('D-fixed-plan-review-20261029T012151991079Z/after-signal-recontact', 'C-step-14')), 'Move forward after green');
  assert.equal(executionStepLabel(row('D-fixed-plan-review-20261029T041620314128Z', 'C-step-13')), 'Approach the signal stop');
});

test('server return kinds are honored and unknown custom labels remain intact', () => {
  for (const kind of ['return', 'return_home', 'RETURN_HOME']) {
    assert.equal(executionStepLabel(row('C/empty-return-after/C-step-26/bounded-1', 'Raw return', kind)), 'Return to start');
  }
  assert.equal(executionStepLabel(row('unfamiliar-wrist:8dfed780d46b44609f78a0f117c4b9c2', 'Inspect new route')), 'Inspect new route');
  assert.equal(executionStepLabel(row('toString', 'Server label')), 'Server label');
});

test('display labels preserve every telemetry row, identity, status, receipt detail and source object', () => {
  const steps = [
    row('D-fixed-plan-review-20261029T034234981825Z'),
    { ...row('C-upper-unloaded-WEST'), status: 'current', detail: 'Robot command in progress' },
    { ...row('C-west-course-review-20261028T231958806301Z'), status: 'held', detail: 'Completion not confirmed' },
  ];
  const original = structuredClone(steps);
  for (const step of steps) Object.freeze(step);
  Object.freeze(steps);
  const titles = steps.map(executionStepLabel);
  assert.deepEqual(titles, ['Leave Pizza shop', 'Orient the gripper for Villa', 'Deliver at Villa']);
  assert.equal(titles.length, original.length);
  assert.deepEqual(steps, original);
});
