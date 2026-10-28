import assert from 'node:assert/strict';
import test from 'node:test';
import { liveCameraPresentation } from '../src/cameraPresentation.ts';
import { liveDisplaySnapshot, liveOverlayAllowed } from '../src/liveCamera.ts';
import { recordedDisplay } from '../src/boardFocus.ts';

const map = {
  id: 'city', version: 'a3', geometry_hash: 'city-geometry',
  board: { width_mm: 420, height_mm: 297 },
  markers: [10, 11, 12, 13].map(id => ({ id, center_mm: [10, 10], size_mm: 8 })),
};
const route = { map_id: map.id, map_version: map.version, map_hash: map.geometry_hash };
const frame = { id: 'frame-1', width: 1920, height: 1080, age_ms: 50 };
const homography = [[2, 0, 100], [0, 2, 100], [0, 0, 1]];
const snapshot = (status = 'locked', ids = [10, 11, 12, 13], verification = 'visible_markers') => ({
  enabled: true, state: 'live', camera_id: 'camera', epoch: 'epoch', frame,
  ...route, detection: { marker_ids: ids, markers: [] },
  registration: { id: 'fixed-view', status, homography, verification },
});

test('expected covers of one through all four markers keep the main presentation quiet and fixed', () => {
  const complete = snapshot();
  const originalBounds = recordedDisplay(complete, map, true);
  for (const [observed, count] of [
    [complete, 4],
    [snapshot('locked_partial', [11, 12, 13]), 3],
    [snapshot('locked_partial', [10, 13]), 2],
    [snapshot('locked_occluded', [13], 'insufficient_visibility'), 1],
    [snapshot('locked_occluded', [], 'insufficient_visibility'), 0],
    [snapshot(), 4],
  ]) {
    const presentation = liveCameraPresentation(observed, map, true);
    assert.equal(presentation.label, 'Fixed mapping');
    assert.match(presentation.detail, new RegExp(`^${count}/4 markers visible\\.`));
    if (count < 2) assert.match(presentation.detail, /current alignment is unverified/);
    assert.deepEqual(presentation.alerts, [], 'expected visibility changes must not flash a full-width warning');
    assert.equal(liveOverlayAllowed(observed, route, map, true), true);
    assert.deepEqual(recordedDisplay(observed, map, true), originalBounds, 'the same original-pixel board viewport stays fixed');
    assert.equal(observed.registration.homography, homography);
    assert.equal(observed.frame, frame);
  }
});

test('contradictory visible evidence remains prominent while retaining the truthful detected-marker count', () => {
  const observed = snapshot('locked_occluded', [10, 11], 'marker_disagreement');
  const presentation = liveCameraPresentation(observed, map, true);
  assert.equal(presentation.label, 'Alignment conflict');
  assert.match(presentation.detail, /^2\/4 markers visible\. Visible evidence conflicts/);
  assert.deepEqual(presentation.alerts.map(alert => alert.kind), ['marker_disagreement']);
  assert.match(presentation.alerts[0].message, /markers disagree/);
});

test('stale pixels and a newly withdrawn view still show large alerts and cannot draw an old route', () => {
  const complete = snapshot();
  const stale = liveCameraPresentation(complete, map, false);
  assert.deepEqual(stale.alerts.map(alert => alert.kind), ['stale']);
  assert.equal(liveOverlayAllowed(complete, route, map, false), false);
  const changed = liveDisplaySnapshot(complete, snapshot('view_changed'));
  assert.deepEqual(liveCameraPresentation(changed, map, true).alerts.map(alert => alert.kind), ['view_changed']);
  assert.equal(liveOverlayAllowed(changed, route, map, true), false);
  assert.equal(recordedDisplay(changed, map, true).quad, null);
  assert.deepEqual(liveCameraPresentation(changed, map, false).alerts.map(alert => alert.kind), ['view_changed', 'stale']);
});

test('the on-demand diagnostic counts only distinct known markers rather than unrelated detections', () => {
  const presentation = liveCameraPresentation(snapshot('locked_partial', [10, 10, 13, 49]), map, true);
  assert.equal(presentation.label, 'Fixed mapping');
  assert.match(presentation.detail, /^2\/4 markers visible\./);
});
