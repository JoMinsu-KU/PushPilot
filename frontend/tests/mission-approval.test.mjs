import assert from 'node:assert/strict';
import test from 'node:test';
import { missionApprovalFeedback } from '../src/missionApproval.ts';

const workspace = () => ({ state: 'PLAN_READY', session_id: 'workspace-a', approved: false, plan: { id: 'plan-a', revision: 3 } });
const accepted = () => ({ enabled: true, available: false, state: 'STARTING', mission_id: 'mission-a',
  plan_id: 'plan-a', plan_revision: 3, workspace_session_id: 'workspace-a', error: null, blockers: [],
  robot: { connected: true, stationary: true } });
const feedback = (status, ws = workspace(), connected = true, ready = false, pending = false, uncertain = false) =>
  missionApprovalFeedback(status, ws, connected, ready, pending, uncertain);

test('approval starts as an explicit plan action and pending clicks never invent acceptance', () => {
  const idle = { ...accepted(), mission_id: null, state: 'READY', available: true };
  assert.equal(feedback(idle, workspace(), true, true).phase, 'awaiting');
  assert.equal(feedback(idle, workspace(), true, true).buttonLabel, 'Approve plan');
  assert.equal(feedback(idle, workspace(), true, false, true).phase, 'submitting');
  assert.equal(feedback(idle, workspace(), true, false, false, true).phase, 'unconfirmed');
  assert.equal(feedback(idle), null);
  assert.equal(feedback(null, { ...workspace(), approved: true }), null, 'simulation approval grants no Robot approval');
});

test('only the accepted matching mission shows Approved once, including normal autonomous waits', () => {
  const status = accepted();
  for (const state of ['STARTING', 'RUNNING', 'OBSERVING', 'WAITING_SIGNAL', 'RECONTACTING', 'RETURNING_HOME']) {
    const result = feedback({ ...status, state });
    assert.equal(result.phase, 'approved');
    assert.equal(result.title, 'Approved once');
    assert.equal(result.buttonLabel, 'Approved');
    assert.equal(result.detail, 'After this, PushPilot resumes on its own when the signal and execution conditions allow.');
  }
  assert.equal(feedback(status, workspace(), true, false, true, true).phase, 'approved', 'server acceptance resolves a pending request');
});

test('new plans, sessions and revisions cannot inherit a prior mission approval', () => {
  const status = accepted();
  for (const ws of [null, { ...workspace(), session_id: 'other' },
    { ...workspace(), plan: { id: 'other', revision: 3 } }, { ...workspace(), plan: { id: 'plan-a', revision: 4 } }]) {
    assert.equal(feedback(status, ws), null);
  }
  assert.equal(feedback({ ...status, mission_id: null }), null);
});

test('faults, holds, stale connections and completed runs retain their actual status', () => {
  const status = accepted();
  for (const state of ['HOLD', 'HELD', 'STOPPING', 'FAILED', 'FAULT', 'ERROR', 'CANCELLED', 'COMPLETE', 'COMPLETED', 'READY', 'IDLE', 'RECOVERY_REQUIRED', 'PAUSED', 'NEW_PROTOCOL_PHASE']) {
    assert.equal(feedback({ ...status, state }), null, state);
  }
  for (const update of [{ error: 'ROBOT_NOT_COMPLETE' }, { blockers: ['CURRENT_PROFILE_CHANGED'] },
    { robot: { connected: false, stationary: false } }, { enabled: false }]) {
    assert.equal(feedback({ ...status, ...update }), null);
  }
  assert.equal(feedback(status, workspace(), false), null);
});

test('approval feedback does not mutate the execution or workspace snapshots', () => {
  const status = accepted(), ws = workspace();
  const before = JSON.stringify({ status, ws });
  Object.freeze(status.robot); Object.freeze(status.blockers); Object.freeze(status);
  Object.freeze(ws.plan); Object.freeze(ws);
  feedback(status, ws);
  assert.equal(JSON.stringify({ status, ws }), before);
});
