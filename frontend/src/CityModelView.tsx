import { useEffect, useMemo, useRef, useState } from 'react';
import type { TemporaryMap } from '../../contracts/scene';
import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { cityDisplayFit, cityPreviewLabel, cityPreviewWorld, projectCityPreview, type CityDisplayManifest, type CityPreviewFit, type CityProjection } from './cityRoutePreview';
import { assetSha256 } from './assetIntegrity';
import { physicalCarTrack, updatePhysicalCarMotion, type PhysicalDisplaySnapshot, type PhysicalCarTrack } from './physicalDisplay';
import { pathLength, pointAlong, SIMULATED_CAR_MM, SIMULATED_CAR_SCALE, SIMULATED_PUSH_SPEED_MM_S, simulatedCarTrack, type CarTrack } from './simulatedCar';
import { projectRouteDisplay, type RouteDisplay } from './routeProgress';
import { RouteOverlay } from './RouteOverlay';
import type { Point } from './projection';
import './city-model.css';

const MODEL_URL = '/models/private/pushpilot-city-clean-roads.glb';
const MAX_MODEL_BYTES = 32 * 1024 * 1024;
// Same cameras as the toy 3D viewer (Blender renders), in glTF axes; hfov = 2 atan(18 / lens).
// Only the home view is exposed (reset button); the others are kept for the reference viewer's presets.
const lens = (mm: number) => 2 * Math.atan(18 / mm);
type Vec3 = [number, number, number];
const VIEWS = [
  { id: 'iso', label: 'Overview', position: [430, 430, 470], target: [-6, 0, -4], hfov: lens(42) },
  { id: 'wide', label: 'From the south', position: [0, 470, 520], target: [0, 0, -18], hfov: lens(38) },
  { id: 'top', label: 'Top down', position: [0, 1500, 0.01], target: [0, 0, 0], hfov: 2 * Math.atan(300 / 1500) },
  { id: 'map', label: 'Map view', position: [0, 1182, 915.5], target: [0, 0, -8], hfov: 2 * Math.atan(302 / 1500) },
  { id: 'junction', label: 'Junction', position: [-70, 70, 150], target: [0, 8, 5], hfov: lens(30) },
  { id: 'nw', label: 'Convenience store · Villa', position: [-150, 80, 10], target: [-128, 10, -85], hfov: lens(34) },
  { id: 'ne', label: 'Cafe · Hanok Stay', position: [150, 80, 10], target: [128, 10, -85], hfov: lens(34) },
  { id: 'se', label: 'Office · Beauty salon', position: [150, 95, 200], target: [128, 14, 85], hfov: lens(34) },
  { id: 'tower', label: 'Namsan Tower', position: [70, 40, -110], target: [0, 24, -196], hfov: lens(40) },
] as const satisfies readonly { id: string; label: string; position: Vec3; target: Vec3; hfov: number }[];
type ViewId = typeof VIEWS[number]['id'];
const HOME_VIEW: ViewId = 'wide';
const NAMES: Record<string, string> = {
  store: 'Convenience store', villa: 'Villa', cafe: 'Cafe', hanok: 'Hanok Stay', pizza: 'Pizza shop', pond: 'Pond park', office: 'Office', beauty: 'Beauty salon',
  borders: 'Border (Namsan · buildings · shops · river)', roads: 'Roads · crosswalks', simulated_car: 'Car · execution estimate',
};
// Map place labels whose building model is named differently.
const BUILDING_ALIASES: Record<string, string> = { 'Office Building': 'office' };
const PICK_TOLERANCE_PX = 6, PICK_VISIBLE_MS = 1800, VIEW_TRANSITION_MS = 900;
const CAR_MASK_ID = 'city-car-occlusion';
// The SVG is drawn in screen pixels here: junction labels (6.8 units × scale) render at 13 px.
const ROUTE_LABEL_SCALE = 13 / 6.8;
const SCENERY = new Set(['roads', 'borders']);
const CORNER_MARKER_MATERIALS = new Set(['toy_FFFFFF', 'toy_111111']);
const isCornerMarker = (mesh: THREE.Mesh) => mesh.parent?.name === 'roads'
  && (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).some(material => CORNER_MARKER_MATERIALS.has(material.name));
const pickName = (name: string) => NAMES[name] ?? (/^trees_/.test(name) ? 'Trees' : /^block_/.test(name) ? 'Block (sidewalk · grass · streetlights)' : name);
type ModelStatus = { kind: 'loading' | 'ready' | 'error' | 'lost'; message: string };
interface ViewRuntime { go: (view: ViewId, animate: boolean) => void; relayout: () => void; syncCar: (animate: boolean) => void }
interface Resources {
  geometry: Set<THREE.BufferGeometry>; materials: Set<THREE.Material>; textures: Set<THREE.Texture>;
  images: Set<ImageBitmap>; instances: Set<THREE.InstancedMesh>;
}
const resources = (): Resources => ({ geometry: new Set(), materials: new Set(), textures: new Set(), images: new Set(), instances: new Set() });

function rememberTexture(value: unknown, owner: Resources) {
  if (!(value instanceof THREE.Texture)) return;
  owner.textures.add(value);
  const images: unknown[] = Array.isArray(value.source?.data) ? value.source.data : [value.source?.data];
  for (const image of images) {
    if (typeof ImageBitmap !== 'undefined' && image instanceof ImageBitmap) owner.images.add(image);
  }
}
function rememberObject(root: THREE.Object3D, owner: Resources) {
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    owner.geometry.add(object.geometry);
    if (object instanceof THREE.InstancedMesh) owner.instances.add(object);
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      owner.materials.add(material);
      for (const value of Object.values(material)) rememberTexture(value, owner);
    }
  });
}
function disposeResources(owner: Resources) {
  owner.instances.forEach(instance => instance.dispose());
  owner.geometry.forEach(geometry => geometry.dispose());
  owner.materials.forEach(material => material.dispose());
  owner.textures.forEach(texture => texture.dispose());
  owner.images.forEach(image => image.close());
  owner.geometry.clear(); owner.materials.clear(); owner.textures.clear(); owner.images.clear(); owner.instances.clear();
}

/** Baked red/green emissions are artwork, not a reviewed live signal observation. */
function neutralizeBakedSignals(root: THREE.Group, owner: Resources) {
  const replacements = new Map<THREE.Material, THREE.Material>();
  const replace = (material: THREE.Material) => {
    if (!/^sig_[GR](?:\.|$)/.test(material.name) || !(material instanceof THREE.MeshStandardMaterial)) return material;
    const existing = replacements.get(material);
    if (existing) return existing;
    const neutral = material.clone();
    neutral.color.set('#263136'); neutral.emissive.set('#000000'); neutral.emissiveIntensity = 0;
    neutral.name = `${material.name} · unobserved`;
    replacements.set(material, neutral); owner.materials.add(neutral);
    return neutral;
  };
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    object.material = Array.isArray(object.material) ? object.material.map(replace) : replace(object.material);
  });
}

/** The export's oversized staging plane is a display surface, not city artwork. */
function softenStagingPlane(root: THREE.Group, owner: Resources) {
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh) || object.name !== 'Plane') return;
    const tabletop = new THREE.MeshStandardMaterial({ color: '#e9edeb', roughness: 1, metalness: 0 });
    tabletop.name = 'Neutral display tabletop';
    owner.materials.add(tabletop);
    object.material = tabletop;
  });
}

/**
 * Preserve every original mesh transform; optimized copies live in world space.
 * Not used for the toy city: batching drops the named node hierarchy that building picking relies on.
 */
function optimizeStaticModel(root: THREE.Group, owner: Resources): THREE.Group {
  const optimized = new THREE.Group();
  optimized.name = 'City static rendering batches';
  root.updateMatrixWorld(true);
  const candidates: THREE.Mesh<THREE.BufferGeometry, THREE.Material>[] = [];
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    object.castShadow = true; object.receiveShadow = true;
    if (object instanceof THREE.SkinnedMesh || object instanceof THREE.InstancedMesh || object.children.length
      || Array.isArray(object.material) || object.morphTargetInfluences?.length || object.matrixWorld.determinant() <= 0) return;
    candidates.push(object as THREE.Mesh<THREE.BufferGeometry, THREE.Material>);
  });
  const plantGroups = new Map<string, typeof candidates>();
  for (const mesh of candidates) {
    if (mesh.material.alphaTest <= 0 || mesh.material.transparent) continue;
    const key = `${mesh.geometry.uuid}/${mesh.material.uuid}`;
    const group = plantGroups.get(key) ?? [];
    group.push(mesh); plantGroups.set(key, group);
  }
  const instanced = new Set<THREE.Mesh>();
  for (const group of plantGroups.values()) {
    if (group.length < 8) continue;
    const instances = new THREE.InstancedMesh(group[0].geometry, group[0].material, group.length);
    instances.name = 'Instanced city planting';
    group.forEach((mesh, index) => { instances.setMatrixAt(index, mesh.matrixWorld); instanced.add(mesh); });
    instances.instanceMatrix.needsUpdate = true;
    instances.computeBoundingSphere();
    instances.castShadow = false; instances.receiveShadow = true;
    owner.instances.add(instances);
    optimized.add(instances);
    group.forEach(mesh => mesh.removeFromParent());
  }
  const staticGroups = new Map<string, typeof candidates>();
  for (const mesh of candidates) {
    if (instanced.has(mesh) || mesh.material.transparent || mesh.material.alphaTest > 0 || mesh.geometry.groups.length > 1
      || mesh.geometry.drawRange.start !== 0 || Number.isFinite(mesh.geometry.drawRange.count)
      || Object.keys(mesh.geometry.morphAttributes).length) continue;
    const attributes = Object.entries(mesh.geometry.attributes).map(([name, attribute]) =>
      `${name}:${attribute.itemSize}:${attribute.normalized}:${attribute.array.constructor.name}`).sort().join('|');
    const key = `${mesh.material.uuid}/${Boolean(mesh.geometry.index)}/${attributes}`;
    const group = staticGroups.get(key) ?? [];
    group.push(mesh); staticGroups.set(key, group);
  }
  for (const group of staticGroups.values()) {
    if (group.length < 2 || group.reduce((count, mesh) => count + mesh.geometry.getAttribute('position').count, 0) > 1_000_000) continue;
    const copies: THREE.BufferGeometry[] = [];
    try {
      for (const mesh of group) copies.push(mesh.geometry.clone().applyMatrix4(mesh.matrixWorld));
      const merged = mergeGeometries(copies, false);
      if (!merged) continue;
      owner.geometry.add(merged);
      const batch = new THREE.Mesh(merged, group[0].material);
      batch.name = 'Static city material batch';
      batch.castShadow = true; batch.receiveShadow = true;
      optimized.add(batch);
      group.forEach(mesh => mesh.removeFromParent());
    } finally { copies.forEach(copy => copy.dispose()); }
  }
  return optimized;
}

/**
 * White wheel-less hatchback, the same model as the demo video's `makeCar()` (pushpilot-video/world.js): a side
 * profile extruded across the width with rounded edges, matte like a 3D print. Drawing millimetres, front +X,
 * underside at y 0. Authored at the video's 76 × 32 × 28.5 mm, then scaled to the real car's ~18 mm body width.
 */
function createSimulatedCar(): THREE.Group {
  const profile = new THREE.Shape();
  profile.moveTo(-34, 2); profile.lineTo(34, 2); profile.quadraticCurveTo(35.5, 2, 35.5, 7); profile.lineTo(34.5, 12.5);
  profile.quadraticCurveTo(26, 14.5, 17, 15.5); profile.lineTo(8, 24); profile.quadraticCurveTo(-6, 25.5, -19, 24);
  profile.lineTo(-29, 15.5); profile.lineTo(-34.5, 13.5); profile.quadraticCurveTo(-35.5, 4, -34, 2);
  const extrude = (bevelSegments: number, curveSegments: number) => new THREE.ExtrudeGeometry(profile,
    { depth: 26, bevelEnabled: true, bevelThickness: 3, bevelSize: 2.5, bevelSegments, curveSegments })
    .translate(0, .5, -13).scale(SIMULATED_CAR_SCALE, SIMULATED_CAR_SCALE, SIMULATED_CAR_SCALE);
  const geometry = extrude(4, 10);
  geometry.computeBoundingBox();
  const box = geometry.boundingBox!, extent = new THREE.Vector3(); box.getSize(extent);
  const sizing = new THREE.Vector3(SIMULATED_CAR_MM.length / extent.x, SIMULATED_CAR_MM.height / extent.y, SIMULATED_CAR_MM.width / extent.z);
  geometry.translate(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2).scale(sizing.x, sizing.y, sizing.z);
  const paint = new THREE.MeshStandardMaterial({ color: '#f7f6f2', roughness: .7, metalness: 0 });
  paint.name = 'Display car body';
  const body = new THREE.Mesh(geometry, paint);
  body.castShadow = true; body.receiveShadow = true;
  const car = new THREE.Group();
  car.name = 'simulated_car';
  car.add(body);
  // A coarser copy of the same solid (same outer extent) whose projected triangles form the route cut-out.
  const outline = extrude(1, 3).translate(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2).scale(sizing.x, sizing.y, sizing.z);
  car.userData.silhouette = Float32Array.from(outline.getAttribute('position').array);
  outline.dispose();
  return car;
}

/** A display-only model. It never estimates a car pose or supplies robot coordinates. */
export function CityModelView({ map, display, names, insetRight = 0, physicalDisplay = null, physicalMode = false }: { map: TemporaryMap | null; display: RouteDisplay | null; names?: { start: string; goal: string }; insetRight?: number; physicalDisplay?: PhysicalDisplaySnapshot | null; physicalMode?: boolean }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const runtimeRef = useRef<ViewRuntime | null>(null);
  const insetRef = useRef(insetRight);
  const pickAnchorRef = useRef<HTMLDivElement>(null);
  const carMaskRef = useRef<SVGPathElement>(null);
  const namesRef = useRef(names);
  const overlayRef = useRef<SVGSVGElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [picked, setPicked] = useState<{ name: string; key: number; visible: boolean } | null>(null);
  // Reset view is offered only after the operator has rotated, panned or zoomed away from the home view.
  const [viewChanged, setViewChanged] = useState(false);
  const [status, setStatus] = useState<ModelStatus>({ kind: 'loading', message: 'Loading the supplied city model…' });
  const [projection, setProjection] = useState<CityProjection | null>(null);
  const [manifest, setManifest] = useState<CityDisplayManifest | null>(null);
  const [verifiedModelHash, setVerifiedModelHash] = useState<string | null>(null);
  const fit = useMemo(() => cityDisplayFit(map, manifest, verifiedModelHash), [map, manifest, verifiedModelHash]);
  const carTrack = useMemo(() => physicalMode ? physicalCarTrack(map, display, physicalDisplay) : simulatedCarTrack(map, display), [map, display, physicalDisplay, physicalMode]);
  const carRef = useRef<{ fit: CityPreviewFit | null; track: CarTrack | PhysicalCarTrack | null; physical: boolean; fresh: boolean }>({ fit, track: carTrack, physical: physicalMode, fresh: physicalDisplay?.feed_fresh !== false });
  const routeLabel = cityPreviewLabel(fit);
  const routePreview = useMemo(() => {
    if (!fit || !projection || !display) return null;
    const project = (point: Point) => projectCityPreview(point, fit, projection);
    const projected = projectRouteDisplay(display, project);
    const corners: Point[] = [[fit.left, fit.top], [fit.left + fit.width, fit.top],
      [fit.left + fit.width, fit.top + fit.height], [fit.left, fit.top + fit.height]];
    const boundary = corners.map(project);
    return projected ? { display: projected, boundary: boundary.every((point): point is Point => point !== null) ? boundary : undefined } : null;
  }, [fit, display, projection]);

  useEffect(() => {
    if (!picked?.visible) return;
    const timer = window.setTimeout(() => setPicked(current => current && { ...current, visible: false }), PICK_VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [picked]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let disposed = false, loadValid = true, failed = false, intersecting = true;
    let width = 1, height = 1, frame = 0;
    let hfov: number = VIEWS[0].hfov;
    let tween: { from: { position: THREE.Vector3; target: THREE.Vector3; hfov: number };
      to: { position: THREE.Vector3; target: THREE.Vector3; hfov: number }; start: number } | null = null;
    let city: THREE.Group | null = null;
    // The picked object; its name bubble follows the top of it as the camera (or the car) moves.
    let pickObject: THREE.Object3D | null = null;
    const pickBox = new THREE.Box3(), pickPoint = new THREE.Vector3();
    // Display distance advances only to confirmed contact receipt positions; the renderer has no command authority.
    const car = createSimulatedCar();
    const silhouette: Float32Array = car.userData.silhouette, corner = new THREE.Vector3();
    let carKey: string | null = null, carDistance = 0;
    let carTween: { from: number; to: number; start: number; duration: number } | null = null;
    const pickable: THREE.Mesh[] = [];
    let pointerDown: [number, number] | null = null;
    let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer, controls: OrbitControls;
    const modelResources = resources();
    const abort = new AbortController();
    const draco = new DRACOLoader().setDecoderPath('/vendor/draco/').setWorkerLimit(2);
    const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
    let resizeObserver: ResizeObserver | undefined, intersectionObserver: IntersectionObserver | undefined;
    let loadDeadline: number | undefined;
    setStatus({ kind: 'loading', message: 'Loading the supplied city model…' });
    setPicked(null);
    setViewChanged(false);
    setProjection(null); setManifest(null); setVerifiedModelHash(null);

    const active = () => !disposed && !failed && intersecting && !document.hidden;
    // The horizontal field of view spans the part of the canvas the mission panel leaves visible, and a lens
    // offset centres the view there. The canvas, picking and route overlay still use the full canvas.
    const applyFov = () => {
      const inset = Math.min(Math.max(0, insetRef.current), width * .5);
      const visible = width - inset;
      camera.aspect = (width + inset) / height;
      camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(hfov / 2) / (visible / height)));
      if (inset > 0) camera.setViewOffset(width + inset, height, inset, 0, width, height);
      else camera.clearViewOffset();
      camera.updateProjectionMatrix();
    };
    const render = () => {
      frame = 0;
      if (!active()) return;
      try {
        if (tween) {
          const k = Math.min(1, (performance.now() - tween.start) / VIEW_TRANSITION_MS);
          const e = k < .5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
          camera.position.lerpVectors(tween.from.position, tween.to.position, e);
          controls.target.lerpVectors(tween.from.target, tween.to.target, e);
          hfov = tween.from.hfov + (tween.to.hfov - tween.from.hfov) * e; applyFov();
          if (k === 1) tween = null;
        }
        if (carTween) {
          const k = Math.min(1, (performance.now() - carTween.start) / carTween.duration);
          const e = k < .5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
          carDistance = carTween.from + (carTween.to - carTween.from) * e;
          if (k === 1) carTween = null;
        }
        placeCar(Boolean(carTween));
        const changing = controls.update();
        renderer.render(scene, camera);
        const bubble = pickAnchorRef.current;
        if (bubble && pickObject) {
          pickBox.setFromObject(pickObject);
          const point = pickPoint.set((pickBox.min.x + pickBox.max.x) / 2, pickBox.max.y, (pickBox.min.z + pickBox.max.z) / 2).project(camera);
          bubble.style.transform = `translate(${(point.x + 1) / 2 * width}px, ${(1 - point.y) / 2 * height}px)`;
          bubble.style.visibility = point.z < 1 ? 'visible' : 'hidden';
        }
        // The route overlay is drawn above the canvas; cut it exactly where the car's silhouette covers it, as the
        // union of the car's projected triangles (each written with the same winding so nonzero fill unites them).
        const toScreen = (vector: THREE.Vector3) => [(vector.x + 1) / 2 * width, (1 - vector.y) / 2 * height] as const;
        const mask = carMaskRef.current;
        if (mask) {
          let d = '';
          for (let index = 0; car.visible && index < silhouette.length; index += 9) {
            const points = [0, 3, 6].map(offset => toScreen(corner.set(silhouette[index + offset], silhouette[index + offset + 1], silhouette[index + offset + 2]).applyMatrix4(car.matrixWorld).project(camera)));
            const [a, b, c] = points;
            const area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
            if (Math.abs(area) < .01) continue;
            const [p, q] = area > 0 ? [b, c] : [c, b];
            d += `M${a[0].toFixed(1)} ${a[1].toFixed(1)}L${p[0].toFixed(1)} ${p[1].toFixed(1)}L${q[0].toFixed(1)} ${q[1].toFixed(1)}Z`;
          }
          mask.setAttribute('d', d);
        }
        // The car covers the destination dot once its front reaches the route end.
        const goalDot = overlayRef.current?.querySelector<SVGGElement>('[data-endpoint-dot="goal"]');
        if (goalDot) {
          const route = carRef.current.track;
          const arrived = car.visible && route && carDistance + SIMULATED_CAR_MM.length / 2 >= pathLength(route.path) - .5;
          goalDot.style.opacity = arrived ? '0' : '';
        }
        // Start and destination tags name places, so each floats above its building rather than the route end.
        const track = carRef.current.track, placeFit = carRef.current.fit;
        for (const [tone, at] of [['start', track?.path[0]], ['goal', track?.path.at(-1)]] as const) {
          const lift = overlayRef.current?.querySelector(`[data-endpoint-lift="${tone}"]`);
          if (!lift) continue;
          const label = namesRef.current?.[tone];
          const world = at && placeFit && cityPreviewWorld(at, placeFit);
          const building = label ? city?.children.find(child => NAMES[child.name] === label || BUILDING_ALIASES[label] === child.name) : undefined;
          let shift = '';
          if (world && building) {
            pickBox.setFromObject(building);
            const [sx, sy] = toScreen(corner.set(...world).project(camera));
            const [bx, by] = toScreen(corner.set((pickBox.min.x + pickBox.max.x) / 2, pickBox.max.y, (pickBox.min.z + pickBox.max.z) / 2).project(camera));
            shift = `translate(${(bx - sx).toFixed(1)} ${(by - sy).toFixed(1)})`;
          }
          lift.setAttribute('transform', shift);
        }
        // Share the exact rendered camera with the SVG route overlay.
        const matrix = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).toArray();
        setProjection(previous => previous?.width === width && previous.height === height
          && previous.matrix.every((value, index) => value === matrix[index]) ? previous : { width, height, matrix });
        if (changing || tween || carTween) requestRender();
      } catch {
        failed = true;
        setStatus({ kind: 'error', message: 'The 3D view could not render. Reload the model to try again.' });
      }
    };
    function requestRender() { if (active() && !frame) frame = requestAnimationFrame(render); }
    // Pose from the simulated distance along the drawn route; while moving, look a little ahead to round corners.
    function placeCar(moving: boolean) {
      const { fit: currentFit, track } = carRef.current;
      const pose = track && pointAlong(track.path, carDistance);
      const world = pose && currentFit && cityPreviewWorld(pose.at, currentFit);
      const step = pose && currentFit && cityPreviewWorld([pose.at[0] + 1, pose.at[1]], currentFit);
      const scale = world && step ? step[0] - world[0] : 0;
      if (!track || !pose || !world || !Number.isFinite(scale) || scale <= 0) { car.visible = false; return; }
      let [dx, dy] = pose.heading;
      if (moving) {
        const behind = pointAlong(track.path, carDistance - 10).at, ahead = pointAlong(track.path, carDistance + 10).at;
        const length = Math.hypot(ahead[0] - behind[0], ahead[1] - behind[1]);
        if (length > 1e-6) [dx, dy] = [(ahead[0] - behind[0]) / length, (ahead[1] - behind[1]) / length];
      }
      car.visible = true;
      car.scale.setScalar(scale);
      car.position.set(world[0], world[1], world[2]);
      // Drawing +y points down the page, which is +z in the model.
      car.rotation.y = Math.atan2(-dy, dx);
      car.updateMatrixWorld();
    }
    const syncCar = (animate: boolean) => {
      const { track, physical, fresh } = carRef.current;
      if (!track) { carKey = null; carTween = null; requestRender(); return; }
      if (physical) {
        const next = updatePhysicalCarMotion({ key: carKey, distance: carDistance, tween: carTween }, track as PhysicalCarTrack, performance.now(),
          { animate, fresh, reduced: Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) });
        carKey = next.key; carDistance = next.distance; carTween = next.tween;
        requestRender(); return;
      }
      const target = track.distance_mm;
      const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      const mayAnimate = !physical || ('animate' in track && track.animate);
      if (track.key !== carKey || !animate || reduced || !mayAnimate || target < carDistance - .01) {
        // Non-contact phases, reconnects and route changes never run a delayed trip animation.
        carKey = track.key; carTween = null; carDistance = target;
      } else if (Math.abs(target - (carTween?.to ?? carDistance)) > .01) {
        carTween = { from: carDistance, to: target, start: performance.now(),
          duration: physical ? 650 : (target - carDistance) / SIMULATED_PUSH_SPEED_MM_S * 1000 };
      }
      requestRender();
    };
    const pause = () => { if (frame) cancelAnimationFrame(frame); frame = 0; };
    // Reset view follows the camera itself: it shows only once the view has actually been rotated, panned or zoomed
    // away from the home view, not for a tap, a pick or a layout change.
    const home = VIEWS.find(item => item.id === HOME_VIEW)!;
    const homePosition = new THREE.Vector3(...home.position), homeTarget = new THREE.Vector3(...home.target);
    const onInteraction = () => { tween = null; };
    const onInteractionEnd = () => {};
    const onControlsChange = () => {
      if (!tween) setViewChanged(camera.position.distanceTo(homePosition) > 2 || controls.target.distanceTo(homeTarget) > 2);
      requestRender();
    };
    const onVisibility = () => { if (active()) requestRender(); else pause(); };
    const onContextLost = (event: Event) => {
      event.preventDefault(); failed = true; pause();
      setStatus({ kind: 'lost', message: 'The graphics context was interrupted. Reload the 3D view to continue.' });
    };
    const onContextRestored = () => {
      setStatus({ kind: 'error', message: 'Graphics are available again. Reload the model to restore the 3D view.' });
    };
    const go = (id: ViewId, animate: boolean) => {
      if (id === HOME_VIEW) setViewChanged(false);
      const next = VIEWS.find(item => item.id === id);
      if (!next) return;
      const to = { position: new THREE.Vector3(...next.position), target: new THREE.Vector3(...next.target), hfov: next.hfov };
      if (animate) {
        tween = { from: { position: camera.position.clone(), target: controls.target.clone(), hfov }, to, start: performance.now() };
      } else {
        tween = null;
        camera.position.copy(to.position); controls.target.copy(to.target); hfov = to.hfov; applyFov();
      }
      requestRender();
    };
    const resize = () => {
      width = Math.max(1, host.clientWidth); height = Math.max(1, host.clientHeight);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      renderer.setSize(width, height, false);
      applyFov(); requestRender();
    };
    const onPointerDown = (event: PointerEvent) => { pointerDown = [event.clientX, event.clientY]; };
    // A tap (not a drag) names the building under the pointer.
    const onPointerUp = (event: PointerEvent) => {
      const start = pointerDown; pointerDown = null;
      if (!start || !city || Math.hypot(event.clientX - start[0], event.clientY - start[1]) > PICK_TOLERANCE_PX) return;
      const bounds = renderer.domElement.getBoundingClientRect();
      if (bounds.width <= 0 || bounds.height <= 0) return;
      pointer.set((event.clientX - bounds.left) / bounds.width * 2 - 1, -(event.clientY - bounds.top) / bounds.height * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(pickable, false)[0];
      if (!hit) return;
      let object: THREE.Object3D = hit.object;
      while (object.parent && object.parent !== scene && !(object.name in NAMES) && !/^(block|trees)_/.test(object.name)) object = object.parent;
      // Roads, crosswalks, sidewalk blocks and the border are scenery, not places: no name bubble for them.
      if (SCENERY.has(object.name) || /^block_/.test(object.name)) { setPicked(current => current && { ...current, visible: false }); return; }
      pickObject = object;
      setPicked(previous => ({ name: pickName(object.name), key: (previous?.key ?? 0) + 1, visible: true }));
      requestRender();
    };

    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
      renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.domElement.className = 'city-model-canvas';
      renderer.domElement.setAttribute('role', 'img');
      renderer.domElement.setAttribute('aria-label', 'Interactive Spatial city view. Route correspondence is display only; no measured vehicle position.');
      renderer.domElement.addEventListener('webglcontextlost', onContextLost);
      renderer.domElement.addEventListener('webglcontextrestored', onContextRestored);
      renderer.domElement.addEventListener('pointerdown', onPointerDown);
      renderer.domElement.addEventListener('pointerup', onPointerUp);
      host.appendChild(renderer.domElement);
      scene = new THREE.Scene();
      scene.background = new THREE.Color('#D8E6F7');
      camera = new THREE.PerspectiveCamera(30, 1, 1, 6000);
      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true; controls.maxPolarAngle = Math.PI * .49;
      controls.minDistance = 25; controls.maxDistance = 1800;
      controls.addEventListener('change', onControlsChange);
      controls.addEventListener('start', onInteraction);
      controls.addEventListener('end', onInteractionEnd);
      // Light-blue sky fill and a warm south-west sun, matching the Cycles renders.
      scene.add(new THREE.HemisphereLight('#E4EEFB', '#B9C2D6', 1.55));
      const sun = new THREE.DirectionalLight('#FFF6EA', 2.1);
      sun.position.set(-.326, .788, .522).multiplyScalar(900); sun.castShadow = true;
      sun.shadow.mapSize.set(1024, 1024); sun.shadow.bias = -.0003; sun.shadow.normalBias = .4; sun.shadow.radius = 3;
      Object.assign(sun.shadow.camera, { left: -380, right: 380, top: 300, bottom: -300, near: 200, far: 1800 });
      scene.add(sun); scene.add(sun.target);
      rememberObject(car, modelResources);
      car.traverse(object => { if (object instanceof THREE.Mesh) pickable.push(object); });
      scene.add(car);
      syncCar(false);
      resize(); go(HOME_VIEW, false);
      resizeObserver = new ResizeObserver(resize); resizeObserver.observe(host);
      intersectionObserver = new IntersectionObserver(entries => {
        intersecting = entries.some(entry => entry.isIntersecting); onVisibility();
      }, { threshold: .01 });
      intersectionObserver.observe(host);
      document.addEventListener('visibilitychange', onVisibility);
      runtimeRef.current = { go, relayout: () => { applyFov(); requestRender(); }, syncCar };
      const loader = new GLTFLoader().setDRACOLoader(draco);
      loadDeadline = window.setTimeout(() => {
        if (disposed || !loadValid) return;
        loadValid = false; abort.abort(); draco.dispose();
        setStatus({ kind: 'error', message: 'The city model took too long to load. Check the model files and reload.' });
      }, 45_000);
      void (async () => {
        let gltf: GLTF | undefined;
        try {
          const manifestResponse = await fetch('/models/city-display.json', { signal: abort.signal, credentials: 'same-origin', cache: 'no-store' });
          if (!manifestResponse.ok) throw new Error('The display model manifest is unavailable.');
          const declaredManifest = await manifestResponse.json() as CityDisplayManifest;
          if (declaredManifest.schema_version !== 'pushpilot.city-display.v1' || declaredManifest.coordinate_authority !== 'display_only'
            || declaredManifest.model?.url !== MODEL_URL || !/^[0-9a-f]{64}$/.test(declaredManifest.model?.sha256 ?? '')) {
            throw new Error('The display model manifest is invalid.');
          }
          const response = await fetch(MODEL_URL, { signal: abort.signal, credentials: 'same-origin' });
          if (!response.ok) throw new Error(response.status === 404
            ? 'The display city model is missing. Restore the reviewed display asset, then reload.'
            : `The city model request failed (${response.status}). Reload to try again.`);
          const declaredSize = Number(response.headers.get('content-length'));
          if (declaredSize > MAX_MODEL_BYTES) throw new Error('The supplied city model exceeds the supported 32 MB size.');
          const buffer = await response.arrayBuffer();
          if (buffer.byteLength > MAX_MODEL_BYTES) throw new Error('The supplied city model exceeds the supported 32 MB size.');
          if (buffer.byteLength < 20 || new DataView(buffer).getUint32(0, true) !== 0x46546c67) {
            throw new Error('The display city model is missing or invalid. Restore the reviewed display asset, then reload.');
          }
          const actualHash = await assetSha256(buffer);
          if (actualHash !== declaredManifest.model.sha256) throw new Error('The city model does not match its reviewed display manifest.');
          if (!loadValid || disposed) return;
          setManifest(declaredManifest); setVerifiedModelHash(actualHash);
          gltf = await loader.parseAsync(buffer, '/models/private/');
          if (failed || !loadValid || disposed) {
            window.clearTimeout(loadDeadline);
            const staleResources = resources(); rememberObject(gltf.scene, staleResources); disposeResources(staleResources); return;
          }
          rememberObject(gltf.scene, modelResources);
          neutralizeBakedSignals(gltf.scene, modelResources);
          softenStagingPlane(gltf.scene, modelResources);
          gltf.scene.traverse(object => {
            if (!(object instanceof THREE.Mesh)) return;
            // The registration markers in the board corners are for the camera, not the toy-city view.
            if (isCornerMarker(object)) { object.visible = false; return; }
            object.castShadow = true; object.receiveShadow = true;
            for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
              if (material instanceof THREE.MeshStandardMaterial && material.emissiveIntensity > 1) {
                material.emissiveIntensity = Math.min(material.emissiveIntensity, 1.2);
              }
            }
            pickable.push(object);
          });
          // Original meshes and materials are kept as authored: batching would drop the named nodes used for picking.
          city = gltf.scene;
          scene.add(city);
          loadValid = false; window.clearTimeout(loadDeadline);
          setStatus({ kind: 'ready', message: '' }); requestRender();
        } catch (error) {
          if (disposed || !loadValid) return;
          loadValid = false; window.clearTimeout(loadDeadline);
          if (gltf) rememberObject(gltf.scene, modelResources);
          setStatus({ kind: 'error', message: error instanceof Error ? error.message : 'The city model could not load. Reload to try again.' });
        }
      })();
    } catch {
      failed = true;
      setStatus({ kind: 'error', message: 'This browser could not start the 3D view. Enable WebGL or try another supported browser.' });
    }

    return () => {
      disposed = true; loadValid = false; abort.abort(); window.clearTimeout(loadDeadline); pause();
      runtimeRef.current = null; tween = null; carTween = null; city = null; pickObject = null; pickable.length = 0;
      document.removeEventListener('visibilitychange', onVisibility);
      resizeObserver?.disconnect(); intersectionObserver?.disconnect();
      if (controls!) { controls.removeEventListener('change', onControlsChange); controls.removeEventListener('start', onInteraction); controls.removeEventListener('end', onInteractionEnd); controls.dispose(); }
      draco.dispose();
      disposeResources(modelResources);
      if (scene!) {
        scene.traverse(object => { if (object instanceof THREE.DirectionalLight) object.shadow.dispose(); });
        scene.clear();
      }
      if (renderer!) {
        renderer.domElement.removeEventListener('webglcontextlost', onContextLost);
        renderer.domElement.removeEventListener('webglcontextrestored', onContextRestored);
        renderer.domElement.removeEventListener('pointerdown', onPointerDown);
        renderer.domElement.removeEventListener('pointerup', onPointerUp);
        renderer.renderLists.dispose(); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
      }
    };
  }, [attempt]);

  useEffect(() => { insetRef.current = insetRight; runtimeRef.current?.relayout(); }, [insetRight]);
  useEffect(() => { carRef.current = { fit, track: carTrack, physical: physicalMode, fresh: physicalDisplay?.feed_fresh !== false }; runtimeRef.current?.syncCar(true); }, [fit, carTrack, physicalMode, physicalDisplay?.feed_fresh]);
  useEffect(() => { namesRef.current = names; runtimeRef.current?.relayout(); }, [names]);
  // The cut-out polygon is written by the render loop; draw once more when the overlay mounts.
  const hasOverlay = Boolean(routePreview);
  useEffect(() => { if (hasOverlay) runtimeRef.current?.relayout(); }, [hasOverlay]);
  const resetView = () => runtimeRef.current?.go(HOME_VIEW, true);
  return <div className="city-model-view">
    <div className="city-model-host" ref={hostRef}/>
    {status.kind === 'ready' && routePreview && projection && <svg ref={overlayRef} className="city-route-preview"
      viewBox={`0 0 ${projection.width} ${projection.height}`} role="img" aria-label={`${routeLabel}. No measured vehicle position.`}>
      <title>{routeLabel}. The same selected path, direction and stop lines as Camera. Vehicle illustration follows confirmed contact progress only. No camera-to-robot calibration.</title>
      <defs><mask id={CAR_MASK_ID} maskUnits="userSpaceOnUse" x="0" y="0" width={projection.width} height={projection.height}>
        <rect width={projection.width} height={projection.height} fill="#fff"/><path ref={carMaskRef} fill="#000" stroke="#000" strokeWidth="1.5" strokeLinejoin="round"/>
      </mask></defs>
      <RouteOverlay display={routePreview.display} scale={Math.max(.9, Math.min(1.4, projection.width / 900))} labelScale={ROUTE_LABEL_SCALE} boundary={routePreview.boundary} names={names} occlusionMask={CAR_MASK_ID}/>
    </svg>}
    <div className="city-model-pick-anchor" ref={pickAnchorRef} role="status" aria-live="polite">
      {picked && <div key={picked.key} className="city-model-pick" data-visible={picked.visible ? 'true' : 'false'}>{picked.name}</div>}
    </div>
    {status.kind !== 'ready' && <div className={`city-model-state city-model-state-${status.kind}`} role={status.kind === 'loading' ? 'status' : 'alert'}>
      {status.kind === 'loading' && <span className="city-model-loading-dot" aria-hidden="true"/>}
      <strong>{status.kind === 'loading' ? 'Opening Spatial' : 'Spatial unavailable'}</strong>
      <span>{status.message}</span>
      {status.kind !== 'loading' && <button type="button" onClick={() => setAttempt(value => value + 1)}>Reload 3D view</button>}
    </div>}
    {status.kind === 'ready' && <div className="city-display-caption" title={routeLabel}>{physicalMode ? physicalDisplay?.feed_fresh === false ? 'Execution estimate · paused' : carTrack ? 'Execution estimate' : 'Vehicle estimate unavailable' : 'Simulation preview'}<span>Display only</span></div>}
    <div className="city-model-view-controls" role="group" aria-label="3D view controls">
      {status.kind === 'ready' && viewChanged && <button type="button" className="city-model-reset" onClick={resetView} aria-label="Reset the 3D city view to the front view">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 10a9 9 0 1 1 2.6 8.3M3 4v6h6"/></svg>
        <span>Reset view</span>
      </button>}
    </div>
  </div>;
}

export default CityModelView;
