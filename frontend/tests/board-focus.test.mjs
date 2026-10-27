import assert from 'node:assert/strict';
import test from 'node:test';
import { recordedDisplay } from '../src/boardFocus.ts';

const map = {
  id: 'little-town-temporary', version: '2026-10-27.1', geometry_hash: 'current-geometry',
  board: { width_mm: 400, height_mm: 250 },
  markers: [
    { center_mm: [8, -10], size_mm: 12 }, { center_mm: [392, -10], size_mm: 12 },
    { center_mm: [392, 260], size_mm: 12 }, { center_mm: [8, 260], size_mm: 12 },
  ],
};
function scene(matrix = [[3, 0, 200], [0, 2.5, 150], [0, 0, 1]]) {
  return {
    map_id: map.id, map_version: map.version, map_hash: map.geometry_hash,
    frame: { width: 1920, height: 1080, image_url: '/immutable-frame.jpg' },
    registration: { status: 'locked', homography: matrix },
    detection: { markers: [{ id: 10, corners: [[11, 12], [13, 14], [15, 16], [17, 18]] }] },
  };
}
const full = { viewport: [0, 0, 1920, 1080], quad: null };
function near(actual, expected) { assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`); }

test('full frame is retained when focus is off, map absent or frame absent', () => {
  assert.deepEqual(recordedDisplay(scene(), map, false), full);
  assert.deepEqual(recordedDisplay(scene(), null, true), full);
  assert.deepEqual(recordedDisplay({ ...scene(), frame: null }, map, true), { viewport: [0, 0, 1, 1], quad: null });
});

test('candidate, unlocked and changed views cannot mask the frame; locked partial may retain its mapping', () => {
  for (const status of ['unregistered', 'partial', 'candidate', 'view_changed']) {
    const input = scene(); input.registration.status = status;
    assert.deepEqual(recordedDisplay(input, map, true), full, status);
  }
  for (const status of ['locked_partial', 'locked_occluded']) {
    const input = scene(); input.registration.status = status;
    assert.ok(recordedDisplay(input, map, true).quad);
  }
});

test('map identity, version and geometry must all match', () => {
  for (const key of ['map_id', 'map_version', 'map_hash']) {
    const input = scene(); input[key] = 'different';
    assert.deepEqual(recordedDisplay(input, map, true), full, key);
  }
});

test('mask includes working board, marker outer edges and exactly 3 mm of paper padding', () => {
  const result = recordedDisplay(scene(), map, true);
  assert.deepEqual(result.quad, [[191, 102.5], [1409, 102.5], [1409, 822.5], [191, 822.5]]);
  // Padded board-space corners are [-3,-19], [403,-19], [403,269], [-3,269].
  const fitMargin = 1218 * .012;
  near(result.viewport[0], 191 - fitMargin);
  near(result.viewport[1], 102.5 - fitMargin);
  near(result.viewport[2], 1218 + fitMargin * 2);
  near(result.viewport[3], 720 + fitMargin * 2);
});

test('full projective division applies to every mask corner without changing native pixel data', () => {
  const matrix = [[3, .1, 200], [.05, 2.5, 150], [.0003, .0001, 1]];
  const input = scene(matrix), before = structuredClone(input), mapBefore = structuredClone(map);
  const result = recordedDisplay(input, map, true);
  assert.ok(result.quad);
  for (const [index, [x, y]] of [[-3, -19], [403, -19], [403, 269], [-3, 269]].entries()) {
    const denominator = .0003 * x + .0001 * y + 1;
    near(result.quad[index][0], (3 * x + .1 * y + 200) / denominator);
    near(result.quad[index][1], (.05 * x + 2.5 * y + 150) / denominator);
  }
  assert.deepEqual(input, before);
  assert.deepEqual(map, mapBefore);
});

test('display viewport is clamped to the source image while projected corners remain unmodified', () => {
  const input = scene([[6, 0, -100], [0, 5, -100], [0, 0, 1]]);
  const result = recordedDisplay(input, map, true);
  assert.deepEqual(result.viewport, [0, 0, 1920, 1080]);
  assert.deepEqual(result.quad, [[-118, -195], [2318, -195], [2318, 1245], [-118, 1245]]);
});

test('missing, nonfinite, malformed and degenerate matrices display the full frame', () => {
  for (const matrix of [null, {}, [[1, 0], [0, 1]], [[1, 0, 0], null, [0, 0, 1]], [[NaN, 0, 0], [0, 1, 0], [0, 0, 1]],
    [[1, 0, 0], [0, Infinity, 0], [0, 0, 1]], [[1, 0, 0], [2, 0, 0], [0, 0, 1]],
    [[1, 0, 0], [0, 1, 0], [0, 0, 0]], [[.001, 0, 200], [0, .001, 150], [0, 0, 1]]]) {
    assert.deepEqual(recordedDisplay(scene(matrix), map, true), full);
  }
});

test('a projective horizon through the board cannot produce a self-crossing mask', () => {
  assert.deepEqual(recordedDisplay(scene([[3, 0, 200], [0, 2.5, 150], [.01, 0, -2]]), map, true), full);
});

test('entirely off-image projections and invalid geometry cannot mask the frame', () => {
  assert.deepEqual(recordedDisplay(scene([[3, 0, 5000], [0, 2.5, 5000], [0, 0, 1]]), map, true), full);
  assert.deepEqual(recordedDisplay(scene(), { ...map, board: { width_mm: NaN, height_mm: 250 } }, true), full);
  assert.deepEqual(recordedDisplay(scene(), { ...map, markers: [{ center_mm: [8, -10], size_mm: -12 }] }, true), full);
});
