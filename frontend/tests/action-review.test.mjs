import assert from 'node:assert/strict';
import test from 'node:test';
import { pairReadiness, recordedCaptureLabel, selectRecordedFrame } from '../src/recordedReview.ts';

function fixture() {
  const frame = { id: 'before', image_url: '/before', sha256: 'before-bytes', width: 1920, height: 1080, source: 'recorded', captured_at: null, timestamp_source: 'unknown' };
  const scene = { map_id: 'town', map_version: '1', map_hash: 'geometry-1', revision: 5, frame: { ...frame, id: 'after', sha256: 'after-bytes' } };
  const workspace = { state: 'REVIEW_REQUIRED', capabilities: { muse_configured: true, recorded_action_review: true }, review: { id: 'review-1', verdict: 'PENDING' }, plan: { route: { map_id: 'town', map_version: '1', map_hash: 'geometry-1' } } };
  return { workspace, scene, before: { frame, map_id: 'town', map_version: '1', map_hash: 'geometry-1' }, expected: 'The car visibly reaches the stop line.', online: true, pending: false };
}

test('recorded pair is ready only for a pending configured action review', () => {
  const input = fixture();
  assert.equal(pairReadiness(input).ready, true);
  assert.equal(pairReadiness({ ...input, workspace: { ...input.workspace, state: 'READY' } }).ready, false);
  assert.equal(pairReadiness({ ...input, workspace: { ...input.workspace, review: { verdict: 'PASS' } } }).ready, false);
  assert.equal(pairReadiness({ ...input, workspace: { ...input.workspace, capabilities: { muse_configured: false } } }).ready, false);
  assert.equal(pairReadiness({ ...input, online: false }).ready, false);
});

test('new IDs do not make duplicated image bytes a before/after comparison', () => {
  const input = fixture();
  const sameId = { ...input.scene, frame: { ...input.scene.frame, id: input.before.frame.id } };
  const sameBytes = { ...input.scene, frame: { ...input.scene.frame, sha256: input.before.frame.sha256 } };
  assert.equal(pairReadiness({ ...input, scene: sameId }).ready, false);
  assert.match(pairReadiness({ ...input, scene: sameBytes }).reason, /identical image bytes/);
});

test('replacement map and stale plan selections are refused before submission', () => {
  const input = fixture();
  assert.equal(pairReadiness({ ...input, scene: { ...input.scene, map_hash: 'new-print' } }).ready, false);
  assert.equal(pairReadiness({ ...input, before: { ...input.before, map_id: 'another-map' } }).ready, false);
  assert.equal(pairReadiness({ ...input, before: { ...input.before, map_version: '0' } }).ready, false);
  assert.equal(pairReadiness({ ...input, workspace: { ...input.workspace, plan: { route: { map_id: 'town', map_hash: 'old-geometry' } } } }).ready, false);
});

test('missing pair, blank expectation and provider pending remain explicit', () => {
  const input = fixture();
  assert.equal(pairReadiness({ ...input, before: null }).ready, false);
  assert.equal(pairReadiness({ ...input, scene: { ...input.scene, frame: null } }).ready, false);
  assert.equal(pairReadiness({ ...input, expected: '  ' }).ready, false);
  assert.equal(pairReadiness({ ...input, expected: 'x'.repeat(1001) }).ready, false);
  assert.match(pairReadiness({ ...input, pending: true }).reason, /still end the simulation/);
});

test('pinning retains immutable image identity without inventing capture time', () => {
  const input = fixture();
  const selected = selectRecordedFrame(input.scene);
  assert.equal(selected.frame.id, 'after');
  assert.equal(selected.map_hash, 'geometry-1');
  assert.equal(selectRecordedFrame(null), null);
  assert.equal(recordedCaptureLabel(selected.frame), 'Capture time unknown');
  assert.equal(recordedCaptureLabel({ captured_at: 'not-a-date', timestamp_source: 'operator_provided' }), 'Capture time unknown');
});
