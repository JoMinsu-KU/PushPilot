import assert from 'node:assert/strict';
import test from 'node:test';
import { Box3, Mesh, MeshBasicMaterial, MeshStandardMaterial, Raycaster, Vector3 } from 'three';
import { createCitySignal } from '../src/citySignal.ts';

const materialAppearance = material => ({
  color: material.color.toArray(),
  emissive: material.emissive.toArray(),
  emissiveIntensity: material.emissiveIntensity,
  opacity: material.opacity,
  transparent: material.transparent,
  roughness: material.roughness,
});

function faces(signal) {
  const green = signal.group.getObjectByName('Signal green');
  const red = signal.group.getObjectByName('Signal red');
  assert.ok(green instanceof Mesh && red instanceof Mesh);
  assert.ok(green.material instanceof MeshStandardMaterial && red.material instanceof MeshStandardMaterial);
  return { green, red };
}

test('the default standing card shows green above red without emitting light', () => {
  const signal = createCitySignal();
  const { green, red } = faces(signal);
  signal.group.updateMatrixWorld(true);
  assert.ok(signal.group.visible && green.visible && red.visible);
  assert.equal(green.material, signal.green);
  assert.equal(red.material, signal.red);
  assert.ok(signal.green.color.g > signal.green.color.r);
  assert.ok(signal.red.color.r > signal.red.color.g);
  for (const mesh of [green, red]) {
    assert.equal(mesh.material.opacity, 1);
    assert.equal(mesh.material.transparent, false);
    assert.equal(mesh.material.emissiveIntensity, 0);
    const bounds = new Box3().setFromObject(mesh);
    const size = bounds.getSize(new Vector3());
    assert.ok(size.x > 0 && size.y > 0 && size.z < size.x / 4, 'printed circles have thin, visible geometry');
    assert.ok(mesh.position.z > 0, 'both colors face the south camera');
    const center = mesh.getWorldPosition(new Vector3());
    const ray = new Raycaster(center.clone().add(new Vector3(0, 0, 100)), new Vector3(0, 0, -1));
    const hits = ray.intersectObjects(signal.group.children.filter(object => object instanceof Mesh && object.visible));
    assert.equal(hits[0]?.object, mesh, 'the standing card does not cover either colored face');
  }
  assert.ok(green.position.y > red.position.y);
  assert.deepEqual(signal.group.rotation.toArray().slice(0, 3), [0, 0, 0]);
  assert.equal(signal.glow.visible, false);
  assert.equal(signal.group.userData.signalState, 'base');
});

test('approved green emits only from green and preserves the visible red face', () => {
  const signal = createCitySignal();
  const redBefore = materialAppearance(signal.red);
  signal.setState('green-approved');
  const { green, red } = faces(signal);
  assert.ok(green.visible && red.visible);
  assert.ok(signal.green.emissiveIntensity > 0);
  assert.ok(signal.green.emissive.g > signal.green.emissive.r);
  assert.deepEqual(materialAppearance(signal.red), redBefore);
  assert.equal(signal.red.emissiveIntensity, 0);
  assert.equal(signal.glow.visible, true);
  assert.equal(signal.group.userData.signalState, 'green-approved');
});

test('returning to the base state restores both printed colors and removes glow', () => {
  const signal = createCitySignal();
  const greenBefore = materialAppearance(signal.green);
  const redBefore = materialAppearance(signal.red);
  for (let cycle = 0; cycle < 2; cycle++) {
    signal.setState('green-approved');
    signal.setState('base');
    assert.deepEqual(materialAppearance(signal.green), greenBefore);
    assert.deepEqual(materialAppearance(signal.red), redBefore);
    assert.equal(signal.glow.visible, false);
  }
});

test('the active halo stays parallel to the card and entirely in front of the green lens', () => {
  const signal = createCitySignal('green-approved');
  const { green } = faces(signal);
  signal.group.updateMatrixWorld(true);
  const glow = signal.glow;
  assert.ok(glow instanceof Mesh && glow.visible);
  assert.ok(glow.material instanceof MeshBasicMaterial);
  assert.ok(glow.material.transparent && glow.material.opacity > 0 && glow.material.opacity < 1);
  assert.equal(glow.material.depthWrite, false);
  assert.equal(glow.material.depthTest, true);
  assert.equal(glow.castShadow, false);
  assert.equal(glow.receiveShadow, false);
  assert.equal(glow.castShadow, false, 'a transparent glow must not cast a rectangular shadow');
  assert.equal(glow.receiveShadow, false);

  const cardNormal = new Vector3(0, 0, 1).transformDirection(signal.group.matrixWorld);
  const haloNormal = new Vector3(0, 0, 1).transformDirection(glow.matrixWorld);
  assert.ok(cardNormal.dot(haloNormal) > 1 - 1e-10, 'halo shares the card plane instead of facing the camera');
  const depths = mesh => {
    const vertices = mesh.geometry.getAttribute('position');
    const point = new Vector3();
    const result = [];
    for (let index = 0; index < vertices.count; index++) {
      result.push(point.fromBufferAttribute(vertices, index).applyMatrix4(mesh.matrixWorld).dot(cardNormal));
    }
    return result;
  };
  const haloDepths = depths(glow);
  const lensDepths = depths(green);
  assert.ok(Math.max(...haloDepths) - Math.min(...haloDepths) < 1e-6, 'all halo vertices share one plane');
  assert.ok(Math.min(...haloDepths) > Math.max(...lensDepths) + 1e-3,
    'the whole halo clears the lens front, so an angled camera cannot cut its plane through the lens');
});

test('the entire card and glow stay outside the central crosswalk corridors', () => {
  const signal = createCitySignal();
  signal.setState('green-approved');
  signal.group.updateMatrixWorld(true);
  const bounds = new Box3().setFromObject(signal.group);
  // Audited private city: southeast block begins at x/z 45. South stripes
  // occupy x -42..42, z 47..63; east stripes occupy x 47..63, z -42..42.
  assert.ok(bounds.min.x > 45, 'signal remains east of the north/south road and crosswalk');
  assert.ok(bounds.min.z > 45, 'signal remains south of the east/west road and crosswalk');
  assert.ok(bounds.min.y >= 3, 'signal rests above the southeast grass surface');
  assert.equal(signal.group.userData.coordinateAuthority, 'display_only');
});
