import assert from 'node:assert/strict';
import test from 'node:test';
import { Matrix4, PerspectiveCamera, Vector3 } from 'three';
import { CITY_MODEL_ID, CITY_MODEL_SHA256, cityPreviewFit, cityPreviewLabel, projectCityPreview } from '../src/cityRoutePreview.ts';
import { createRouteDisplay, projectRouteDisplay } from '../src/routeProgress.ts';
import { projectPoint } from '../src/projection.ts';

const map = { nodes: [{ x_mm: 126, y_mm: 33 }, { x_mm: 200, y_mm: 117 }, { x_mm: 274, y_mm: 201 }] };
function view(x = 30) {
  const camera = new PerspectiveCamera(35, 1.5, 1, 7000);
  camera.position.set(x, 650, 760); camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
  return { width: 1200, height: 800,
    matrix: new Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).toArray(), camera };
}
const close = (a, b) => a.forEach((value, index) => assert.ok(Math.abs(value - b[index]) < 1e-7));

test('the complete graph determines the fit, independent of selected route or place names', () => {
  assert.deepEqual(cityPreviewFit(map), { left: 126, top: 33, width: 148, height: 168 });
  const replacement = { nodes: map.nodes.map(node => ({ x_mm: node.x_mm * 2 + 80, y_mm: node.y_mm * 3 - 20 })) };
  const camera = view();
  close(projectCityPreview([200, 117], cityPreviewFit(map), camera),
    projectCityPreview([480, 331], cityPreviewFit(replacement), camera));
});

test('preview uses the exact Three camera projection and follows orbit changes', () => {
  const fit = cityPreviewFit(map), first = view(), orbit = view(-500);
  const corner = projectCityPreview([126, 201], fit, first);
  const expected = new Vector3(-236, 2, 149).project(first.camera);
  close(corner, [(expected.x + 1) * 600, (1 - expected.y) * 400]);
  assert.notDeepEqual(corner, projectCityPreview([126, 201], fit, orbit));
});

test('invalid or degenerate replacement graphs cannot create a preview', () => {
  assert.equal(cityPreviewFit(null), null);
  assert.equal(cityPreviewFit({ nodes: [] }), null);
  assert.equal(cityPreviewFit({ nodes: [{ x_mm: 1, y_mm: 1 }] }), null);
  assert.equal(cityPreviewFit({ nodes: [{ x_mm: NaN, y_mm: 1 }] }), null);
});

test('a point behind the camera or outside its depth range is withheld', () => {
  const fit = cityPreviewFit(map), camera = view();
  camera.camera.lookAt(0, 1000, 1600); camera.camera.updateMatrixWorld();
  camera.matrix = new Matrix4().multiplyMatrices(camera.camera.projectionMatrix, camera.camera.matrixWorldInverse).toArray();
  assert.equal(projectCityPreview([200, 117], fit, camera), null);
  assert.equal(projectCityPreview([200, 117], fit, { ...view(), matrix: Array(16).fill(0) }), null);
  assert.equal(projectCityPreview([200, 117], fit, { ...view(), width: 0 }), null);
  assert.equal(projectCityPreview([Infinity, 117], fit, view()), null);
});

function city() {
  return { id: 'seoul-city-a3', version: 'new-print.1', geometry_hash: 'new-map-hash',
    board: { width_mm: 420, height_mm: 297 },
    nodes: [{ id: 'PIZZA', x_mm: 100, y_mm: 148.5 }, { id: 'C', x_mm: 210, y_mm: 148.5 },
      { id: 'N', x_mm: 210, y_mm: 40.340895698 }, { id: 'HANOK', x_mm: 300, y_mm: 40.340895698 }],
    spatial_preview: { schema_version: 'pushpilot.spatial-preview.v1', model_id: CITY_MODEL_ID, model_sha256: CITY_MODEL_SHA256,
      drawing_rect_mm: [39.6375, 40.3408956982911, 379.925, 257.6216853270477],
      model_rect_xz: [-236, -149, 236, 149], elevation: 2, alignment: 'drawing_correspondence', coordinate_authority: 'display_only' } };
}

test('drawing correspondence fits the authored road envelope, independent of a selected path', () => {
  const data = city(), fit = cityPreviewFit(data), camera = view();
  assert.equal(cityPreviewLabel(fit), 'Drawing-aligned route · display only');
  assert.equal(cityPreviewLabel(cityPreviewFit(map)), '2D route preview · alignment pending');
  const [left, top, right, bottom] = data.spatial_preview.drawing_rect_mm;
  for (const [point, world] of [[[left, top], [-236, 2, -149]], [[right, bottom], [236, 2, 149]],
    [[(left + right) / 2, (top + bottom) / 2], [0, 2, 0]]]) {
    const expected = new Vector3(...world).project(camera.camera);
    close(projectCityPreview(point, fit, camera), [(expected.x + 1) * 600, (1 - expected.y) * 400]);
  }
  const moreNodes = structuredClone(data); moreNodes.nodes.push({ id: 'OTHER', x_mm: 350, y_mm: 250 });
  assert.deepEqual(cityPreviewFit(moreNodes), fit);
});

test('mismatched model identity or malformed explicit metadata withholds the route instead of using legacy fit', () => {
  const changes = [
    ['model_id', 'another-model'], ['model_sha256', '0'.repeat(64)], ['model_sha256', CITY_MODEL_SHA256.toUpperCase()],
    ['schema_version', 'other'], ['coordinate_authority', 'robot'], ['alignment', 'registered'],
    ['elevation', NaN], ['elevation', true], ['elevation', -1], ['elevation', 1001],
    ['model_rect_xz', [-236, -149, Infinity, 149]], ['model_rect_xz', [0, -149, 0, 149]],
    ['model_rect_xz', [-236, -149, 1_000_001, 149]], ['drawing_rect_mm', [-1, 0, 420, 297]],
    ['drawing_rect_mm', [0, 0, 421, 297]], ['drawing_rect_mm', [0, 0, NaN, 297]],
    ['drawing_rect_mm', [101, 0, 420, 297]], ['unexpected_robot_transform', [1, 2, 3]],
  ];
  for (const [key, value] of changes) {
    const data = city(); data.spatial_preview[key] = value;
    assert.equal(cityPreviewFit(data), null, key);
  }
  for (const value of [null, {}, [], 'display']) {
    const data = city(); data.spatial_preview = value;
    assert.equal(cityPreviewFit(data), null);
  }
  assert.equal(cityPreviewLabel(null), 'Route correspondence unavailable');
  assert.equal(cityPreviewFit(city(), { id: CITY_MODEL_ID, sha256: '0'.repeat(64) }), null);
});

test('Camera and Spatial retain the same canonical route point order and drawing progress metadata', () => {
  const data = city(), points = data.nodes.map(node => [node.x_mm, node.y_mm]);
  const route = { map_id: data.id, map_version: data.version, map_hash: data.geometry_hash,
    start: 'PIZZA', destination: 'HANOK', node_ids: data.nodes.map(node => node.id), points_mm: points, distance_mm: 300, junction_ids: ['C', 'N'] };
  const display = createRouteDisplay(route, data, null), fit = cityPreviewFit(data), camera = view();
  display.segments[0].phase = 'review';
  display.junctions = [{ node_id: 'C', label: 'Main Junction', center_mm: points[1], stop_point_mm: [200, 148.5],
    stop_line_mm: [[200, 138.5], [200, 158.5]], exit_point_mm: [210, 138.5],
    approach_segment_id: 'approach', crossing_segment_id: 'crossing', phase: 'waiting', status: 'Red · waiting', active: true }];
  const original = structuredClone(display);
  const homography = [[2.1, .2, 100], [.1, 1.6, 50], [.0002, .0003, 1]];
  const cameraDisplay = projectRouteDisplay(display, point => projectPoint(point, homography));
  const spatialDisplay = projectRouteDisplay(display, point => projectCityPreview(point, fit, camera));
  assert.deepEqual(display, original, 'both views preserve the supervisor-derived source');
  assert.deepEqual(cameraDisplay.points, points.map(point => projectPoint(point, homography)));
  assert.deepEqual(spatialDisplay.points, points.map(point => projectCityPreview(point, fit, camera)));
  for (const projected of [cameraDisplay, spatialDisplay]) {
    assert.deepEqual(projected.segments.map(segment => [segment.id, segment.phase]), display.segments.map(segment => [segment.id, segment.phase]));
    assert.deepEqual(projected.junctions.map(junction => [junction.node_id, junction.phase, junction.status]), [['C', 'waiting', 'Red · waiting']]);
  }
  assert.equal(createRouteDisplay(route, { ...data, geometry_hash: 'old-print' }, null), null);
});
