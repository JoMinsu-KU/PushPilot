import assert from 'node:assert/strict';
import test from 'node:test';
import { Matrix4, PerspectiveCamera, Vector3 } from 'three';
import { cityPreviewFit, projectCityPreview } from '../src/cityRoutePreview.ts';

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
