import assert from 'node:assert/strict';
import test from 'node:test';
import { createLivePollGate, liveDisplaySnapshot, liveFrameAge, liveFrameFresh, liveOverlayAllowed } from '../src/liveCamera.ts';

const map = { id: 'map', version: 'v1', geometry_hash: 'geometry' };
const route = { map_id: 'map', map_version: 'v1', map_hash: 'geometry' };
const makeSnapshot = () => ({
  enabled: true, state: 'live', freshness_limit_ms: 1500, epoch: 'camera-epoch', camera_id: 'camera',
  map_id: 'map', map_version: 'v1', map_hash: 'geometry',
  frame: { id: 'frame-1', width: 1920, height: 1080, age_ms: 125, received_at: '1999-01-01T00:00:00Z' },
  registration: { id: 'registration-1', status: 'locked', homography: [[1, 0, 0], [0, 1, 0], [0, 0, 1]] },
});

test('an explicit lock discards a late pre-lock poll without overriding later server authority', () => {
  const gate = createLivePollGate();
  const preLockRequest = gate.begin();
  const locked = makeSnapshot();
  gate.registrationApplied();
  const candidate = { ...locked, registration: { id: null, status: 'candidate', homography: null } };
  assert.equal(gate.accept(preLockRequest, candidate), null, 'pre-lock fetch or decode must not replace the lock result');
  const afterLockRequest = gate.begin();
  assert.equal(gate.accept(afterLockRequest, locked), locked);

  // An application restart can lose its in-memory lock while the camera epoch stays unchanged.
  const afterRestartRequest = gate.begin();
  const reset = gate.accept(afterRestartRequest, candidate);
  assert.equal(reset, candidate, 'the earlier successful lock is never merged into later responses');
  assert.equal(liveDisplaySnapshot(locked, reset).registration.homography, null,
    'old decoded geometry is hidden before the reset frame finishes decoding');
  assert.equal(liveOverlayAllowed(reset, route, map, true), false);
});

test('a status identity or view change immediately inhibits the previous decoded mapping', () => {
  const decoded = makeSnapshot();
  assert.equal(liveDisplaySnapshot(decoded, makeSnapshot()), decoded);
  for (const latest of [
    { ...makeSnapshot(), epoch: 'new-camera-epoch' },
    { ...makeSnapshot(), map_hash: 'new-map' },
    { ...makeSnapshot(), frame: { ...decoded.frame, width: 1280 } },
    { ...makeSnapshot(), registration: { ...decoded.registration, id: 'registration-2' } },
    { ...makeSnapshot(), registration: { ...decoded.registration, status: 'view_changed' } },
  ]) assert.equal(liveDisplaySnapshot(decoded, latest).registration.homography, null);
});

test('browser request and image decoding delays consume the same frame freshness budget', () => {
  const snapshot = makeSnapshot();
  const requestStartedAt = 100;
  const responseArrivedAt = 1200;
  const imageDecodedAt = 1550;
  assert.equal(liveFrameAge(snapshot, requestStartedAt, responseArrivedAt), 1225);
  assert.equal(liveFrameFresh(snapshot, requestStartedAt, responseArrivedAt), true);
  assert.equal(liveFrameAge(snapshot, requestStartedAt, imageDecodedAt), 1575);
  assert.equal(liveFrameFresh(snapshot, requestStartedAt, imageDecodedAt), false);
});

test('freshness advances after status receipt even when subsequent requests stop', () => {
  const snapshot = makeSnapshot();
  assert.equal(liveFrameAge(snapshot, 100, 475), 500);
  assert.equal(liveFrameFresh(snapshot, 100, 1475), true);
  assert.equal(liveFrameFresh(snapshot, 100, 1476), false);
  assert.equal(liveFrameFresh({ ...snapshot, state: 'stale' }, 100, 101), false);
  assert.equal(liveFrameFresh({ ...snapshot, enabled: false }, 100, 101), false);
  assert.equal(liveFrameFresh({ ...snapshot, frame: null }, 100, 101), false);
  assert.equal(liveFrameAge({ ...snapshot, frame: { age_ms: NaN } }, 0, 1), Infinity);
});

test('occlusion may retain a fresh fixed display mapping; stale and changed views never draw AR', () => {
  for (const status of ['locked', 'locked_partial', 'locked_occluded']) {
    const snapshot = makeSnapshot(); snapshot.registration.status = status;
    assert.equal(liveOverlayAllowed(snapshot, route, map, true), true, status);
    assert.equal(liveOverlayAllowed(snapshot, route, map, false), false, status);
  }
  for (const status of ['unregistered', 'candidate', 'view_changed']) {
    const snapshot = makeSnapshot(); snapshot.registration.status = status;
    assert.equal(liveOverlayAllowed(snapshot, route, map, true), false, status);
  }
});

test('live AR requires exact map identity and geometry across frame and plan', () => {
  for (const key of ['map_id', 'map_version', 'map_hash']) {
    const snapshot = makeSnapshot(); snapshot[key] = 'different';
    assert.equal(liveOverlayAllowed(snapshot, route, map, true), false, key);
    assert.equal(liveOverlayAllowed(makeSnapshot(), { ...route, [key]: 'different' }, map, true), false, key);
  }
  assert.equal(liveOverlayAllowed(makeSnapshot(), null, map, true), false);
  assert.equal(liveOverlayAllowed(makeSnapshot(), route, null, true), false);
});
