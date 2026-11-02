import * as THREE from 'three';

export type CitySignalState = 'base' | 'green-approved';

/** Display coordinates only: beside the east end of the south crosswalk. */
export const CITY_SIGNAL_POSITION = [57, 3.02, 65] as const;

function roundedCard(width: number, height: number, radius: number, depth: number) {
  const shape = new THREE.Shape();
  const x = -width / 2, y = -height / 2;
  shape.moveTo(x + radius, y);
  shape.lineTo(x + width - radius, y);
  shape.quadraticCurveTo(x + width, y, x + width, y + radius);
  shape.lineTo(x + width, y + height - radius);
  shape.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  shape.lineTo(x + radius, y + height);
  shape.quadraticCurveTo(x, y + height, x, y + height - radius);
  shape.lineTo(x, y + radius);
  shape.quadraticCurveTo(x, y, x + radius, y);
  return new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, curveSegments: 6 });
}

/** Small radial glow; no post-processing, external texture or extra scene light. */
function haloTexture() {
  const size = 64, bytes = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const radius = Math.hypot((x + .5) / size * 2 - 1, (y + .5) / size * 2 - 1);
    const offset = (y * size + x) * 4;
    bytes.set([255, 255, 255, Math.round(Math.max(0, Math.exp(-radius * radius * 5) - Math.exp(-5)) * 105)], offset);
  }
  const texture = new THREE.DataTexture(bytes, size, size, THREE.RGBAFormat);
  texture.needsUpdate = true;
  return texture;
}

/** Two printed colors remain visible. Only an explicitly approved green emits light. */
export function createCitySignal(initialState: CitySignalState = 'base') {
  const group = new THREE.Group();
  group.name = 'city_signal_preview';
  group.position.set(...CITY_SIGNAL_POSITION);
  group.userData.coordinateAuthority = 'display_only';

  const paper = new THREE.MeshStandardMaterial({ color: '#eeeee8', roughness: .95 });
  const black = new THREE.MeshStandardMaterial({ color: '#20272a', roughness: .83 });
  const bezel = new THREE.MeshStandardMaterial({ color: '#101a1c', roughness: .85 });
  const green = new THREE.MeshStandardMaterial({ color: '#159c69', roughness: .54, emissive: '#16bd65', emissiveIntensity: 0 });
  const red = new THREE.MeshStandardMaterial({ color: '#dc483b', roughness: .65, emissive: '#000000', emissiveIntensity: 0 });
  green.name = 'Signal green face'; red.name = 'Signal red face';

  const edge = new THREE.Mesh(roundedCard(14.4, 34.4, 1.1, .65), paper);
  edge.position.set(0, 17.6, -.45);
  const face = new THREE.Mesh(roundedCard(13.5, 33.5, .8, .2), black);
  face.position.set(0, 17.6, .22);
  const foot = new THREE.Mesh(new THREE.BoxGeometry(10.5, .55, 5), paper);
  foot.position.set(0, .28, -1.2);
  group.add(edge, face, foot);

  for (const [name, height, material] of [['green', 25, green], ['red', 10.4, red]] as const) {
    const ring = new THREE.Mesh(new THREE.CylinderGeometry(4.95, 4.95, .3, 40), bezel);
    ring.rotation.x = Math.PI / 2; ring.position.set(0, height, .52);
    const lens = new THREE.Mesh(new THREE.SphereGeometry(4.45, 40, 20), material);
    lens.name = `Signal ${name}`;
    lens.scale.z = .08; lens.position.set(0, height, .64);
    group.add(ring, lens);
  }

  const glowMaterial = new THREE.MeshBasicMaterial({ map: haloTexture(), color: '#46ec8e', transparent: true, opacity: .38,
    depthWrite: false, depthTest: true, blending: THREE.AdditiveBlending, toneMapped: false });
  // Keep the halo parallel to the card so an orbit cannot cut a billboard through the lens.
  const glow = new THREE.Mesh(new THREE.PlaneGeometry(17, 17), glowMaterial);
  glow.name = 'Approved green glow';
  glow.position.set(0, 25, 1.2);
  group.add(glow);
  group.traverse(object => {
    if (object instanceof THREE.Mesh && object !== glow) { object.castShadow = true; object.receiveShadow = true; }
  });

  const setState = (state: CitySignalState) => {
    const approved = state === 'green-approved';
    green.color.set(approved ? '#1ba966' : '#159c69');
    green.emissiveIntensity = approved ? .8 : 0;
    red.emissiveIntensity = 0;
    glow.visible = approved;
    group.userData.signalState = approved ? 'green-approved' : 'base';
  };
  setState(initialState);
  return { group, setState, green, red, glow };
}
