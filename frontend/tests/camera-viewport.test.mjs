import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_CAMERA_VIEWPORT, MIN_CAMERA_ZOOM, MAX_CAMERA_ZOOM,
  normalizeCameraViewport, zoomCameraViewport, panCameraViewport, pinchCameraViewport,
} from '../src/cameraViewport.ts';

const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-12, `${actual} differs from ${expected}`);
const sourcePoint = (view, point) => [(point[0] - view.panX) / view.zoom, (point[1] - view.panY) / view.zoom];
const bounded = view => {
  assert.ok(view.zoom >= MIN_CAMERA_ZOOM && view.zoom <= MAX_CAMERA_ZOOM);
  for (const value of [view.panX, view.panY]) {
    assert.ok(Number.isFinite(value));
    assert.ok(Math.abs(value) <= view.zoom / 2 + 0.25);
  }
};

test('the initial viewport is centered and supports both zooming out and zooming in', () => {
  assert.deepEqual(DEFAULT_CAMERA_VIEWPORT, { zoom: 1, panX: 0, panY: 0 });
  assert.equal(MIN_CAMERA_ZOOM, 0.5);
  assert.equal(MAX_CAMERA_ZOOM, 4);
  assert.deepEqual(zoomCameraViewport(DEFAULT_CAMERA_VIEWPORT, 0.5), { zoom: 0.5, panX: 0, panY: 0 });
  assert.deepEqual(zoomCameraViewport(DEFAULT_CAMERA_VIEWPORT, 4), { zoom: 4, panX: 0, panY: 0 });
});

test('pointer-centered zoom preserves the image and route source position under the pointer', () => {
  const start = { zoom: 1.2, panX: 0.1, panY: -0.15 }, pointer = [0.3, -0.25];
  const before = sourcePoint(start, pointer);
  const after = sourcePoint(zoomCameraViewport(start, 2.3, pointer), pointer);
  close(after[0], before[0]);
  close(after[1], before[1]);
});

test('zoom limits use the effective clamped scale when preserving the pointer anchor', () => {
  const start = { zoom: 2, panX: 0.1, panY: -0.1 }, pointer = [0.2, 0.1];
  for (const [requested, expected] of [[100, 4], [-100, 0.5]]) {
    const next = zoomCameraViewport(start, requested, pointer);
    assert.equal(next.zoom, expected);
    const before = sourcePoint(start, pointer), after = sourcePoint(next, pointer);
    close(after[0], before[0]);
    close(after[1], before[1]);
  }
});

test('unclamped zoom around one anchor can be reversed without camera drift', () => {
  const start = { zoom: 1.4, panX: 0.1, panY: -0.2 }, pointer = [-0.2, 0.25];
  const back = zoomCameraViewport(zoomCameraViewport(start, 2.4, pointer), start.zoom, pointer);
  close(back.zoom, start.zoom);
  close(back.panX, start.panX);
  close(back.panY, start.panY);
});

test('panning uses full viewport fractions rather than scaled image fractions', () => {
  for (const zoom of [0.5, 1, 4]) {
    const next = panCameraViewport({ zoom, panX: 0.1, panY: -0.1 }, 0.2, -0.15);
    close(next.panX, 0.3);
    close(next.panY, -0.25);
    assert.equal(next.zoom, zoom);
  }
});

test('zooming out and panning up can expose board content underneath the lower HUD', () => {
  const smaller = zoomCameraViewport(DEFAULT_CAMERA_VIEWPORT, 0.5);
  const lifted = panCameraViewport(smaller, 0, -0.2);
  const sourceBottom = 0.5;
  close(lifted.panY + sourceBottom * lifted.zoom, 0.05);
  assert.ok(lifted.panY + sourceBottom * lifted.zoom < sourceBottom);
  bounded(lifted);
});

test('extreme panning is limited and the minimum zoom plane remains recoverable', () => {
  const moved = panCameraViewport({ zoom: 0.5, panX: 0, panY: 0 }, Number.MAX_VALUE, -Number.MAX_VALUE);
  assert.deepEqual(moved, { zoom: 0.5, panX: 0.5, panY: -0.5 });
  const recovered = panCameraViewport(moved, -0.5, 0.5);
  assert.deepEqual(recovered, { zoom: 0.5, panX: 0, panY: 0 });
});

test('a pinch combines zoom and midpoint travel around the same source point', () => {
  const start = { zoom: 1.2, panX: 0.1, panY: -0.1 };
  const oldMidpoint = [-0.1, 0.2], newMidpoint = [0.15, 0.05];
  const next = pinchCameraViewport(start, oldMidpoint, newMidpoint, 1.5);
  close(next.zoom, 1.8);
  const before = sourcePoint(start, oldMidpoint), after = sourcePoint(next, newMidpoint);
  close(after[0], before[0]);
  close(after[1], before[1]);
});

test('pinch midpoint tracking remains correct when the requested zoom is clamped', () => {
  for (const ratio of [0.001, 1000]) {
    const start = { zoom: 2, panX: 0.1, panY: -0.1 };
    const oldMidpoint = [0.2, -0.2], newMidpoint = [0.3, -0.1];
    const next = pinchCameraViewport(start, oldMidpoint, newMidpoint, ratio);
    assert.equal(next.zoom, ratio < 1 ? MIN_CAMERA_ZOOM : MAX_CAMERA_ZOOM);
    const before = sourcePoint(start, oldMidpoint), after = sourcePoint(next, newMidpoint);
    close(after[0], before[0]);
    close(after[1], before[1]);
  }
});

test('malformed viewport fields normalize to finite defaults and bounded translations', () => {
  for (const input of [null, undefined, false, 'invalid', {}, { zoom: NaN, panX: Infinity, panY: -Infinity }]) {
    assert.deepEqual(normalizeCameraViewport(input), DEFAULT_CAMERA_VIEWPORT);
  }
  assert.deepEqual(normalizeCameraViewport({ zoom: 10, panX: 50, panY: -50 }), { zoom: 4, panX: 2.25, panY: -2.25 });
  assert.deepEqual(normalizeCameraViewport({ zoom: -10, panX: 50, panY: -50 }), { zoom: 0.5, panX: 0.5, panY: -0.5 });
});

test('nonfinite or malformed gesture events safely leave the normalized viewport unchanged', () => {
  const start = { zoom: 1.2, panX: 0.1, panY: -0.1 };
  for (const value of [NaN, Infinity, -Infinity]) {
    assert.deepEqual(zoomCameraViewport(start, value), start);
    assert.deepEqual(zoomCameraViewport(start, 2, [value, 0]), start);
    assert.deepEqual(panCameraViewport(start, value, 0), start);
    assert.deepEqual(panCameraViewport(start, 0, value), start);
    assert.deepEqual(pinchCameraViewport(start, [0, 0], [0, 0], value), start);
    assert.deepEqual(pinchCameraViewport(start, [0, value], [0, 0], 2), start);
    assert.deepEqual(pinchCameraViewport(start, [0, 0], [value, 0], 2), start);
  }
  for (const ratio of [0, -1]) assert.deepEqual(pinchCameraViewport(start, [0, 0], [0, 0], ratio), start);
  for (const anchor of [null, [], [0], [0, 0, 0], ['0', 0]]) assert.deepEqual(zoomCameraViewport(start, 2, anchor), start);
});

test('extreme finite gesture values never generate an infinite transform', () => {
  const large = Number.MAX_VALUE;
  for (const next of [
    zoomCameraViewport(DEFAULT_CAMERA_VIEWPORT, large, [large, -large]),
    panCameraViewport(DEFAULT_CAMERA_VIEWPORT, large, -large),
    pinchCameraViewport(DEFAULT_CAMERA_VIEWPORT, [large, -large], [-large, large], large),
    pinchCameraViewport(DEFAULT_CAMERA_VIEWPORT, [large, -large], [-large, large], Number.MIN_VALUE),
  ]) bounded(next);
});

test('all operations leave frozen view and pointer inputs untouched and return independent objects', () => {
  const start = Object.freeze({ zoom: 1, panX: 0.1, panY: -0.1 });
  const point = Object.freeze([0.2, 0.15]);
  const results = [
    normalizeCameraViewport(start), zoomCameraViewport(start, 2, point),
    panCameraViewport(start, 0.1, 0.1), pinchCameraViewport(start, point, point, 2),
  ];
  for (const result of results) assert.notEqual(result, start);
  assert.deepEqual(start, { zoom: 1, panX: 0.1, panY: -0.1 });
  assert.deepEqual(point, [0.2, 0.15]);
});
