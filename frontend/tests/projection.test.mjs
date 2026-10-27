import assert from 'node:assert/strict';
import test from 'node:test';
import { projectPoint, directionArrows } from '../src/projection.ts';

test('drawing x-right/y-down coordinates remain correctly oriented in image pixels', () => {
  const matrix = [[3, 0, 170], [0, 2.5, 95], [0, 0, 1]];
  assert.deepEqual(projectPoint([0, 0], matrix), [170, 95]);
  assert.deepEqual(projectPoint([400, 250], matrix), [1370, 720]);
  assert.deepEqual(projectPoint([200, 117], matrix), [770, 387.5]);
});

test('perspective division uses the full board-to-image homography', () => {
  const actual = projectPoint([100, 50], [[2, 0.2, 10], [0.1, 3, 20], [0.001, 0.002, 1]]);
  assert.ok(actual);
  assert.ok(Math.abs(actual[0] - 220 / 1.2) < 1e-9);
  assert.ok(Math.abs(actual[1] - 180 / 1.2) < 1e-9);
});

test('invalid or singular projection does not draw an overlay', () => {
  assert.equal(projectPoint([1, 2], [[1, 0, 0], [0, 1, 0], [0, 0, 0]]), null);
  assert.equal(projectPoint([1, 2], [[NaN, 0, 0], [0, 1, 0], [0, 0, 1]]), null);
  assert.equal(projectPoint([1, 2], [[1, 0], [0, 1]]), null);
});

test('arrows preserve direction through right-angle turns without diagonal corner arrows', () => {
  const arrows = directionArrows([[126, 117], [200, 117], [200, 201], [274, 201]]);
  assert.equal(arrows.length, 3);
  assert.equal(arrows[0].start[1], arrows[0].end[1]);
  assert.ok(arrows[0].end[0] > arrows[0].start[0]);
  assert.equal(arrows[1].start[0], arrows[1].end[0]);
  assert.ok(arrows[1].end[1] > arrows[1].start[1]);
  assert.equal(arrows[2].start[1], arrows[2].end[1]);
  assert.ok(arrows[2].end[0] > arrows[2].start[0]);
  assert.equal(directionArrows([[10, 10], [10, 10]]).length, 0);
});
