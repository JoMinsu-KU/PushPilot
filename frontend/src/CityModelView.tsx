import { useEffect, useMemo, useRef, useState } from 'react';
import type { TemporaryMap } from '../../contracts/scene';
import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { cityPreviewFit, projectCityPreview, type CityProjection } from './cityRoutePreview';
import { projectRouteDisplay, type RouteDisplay } from './routeProgress';
import { RouteOverlay } from './RouteOverlay';
import type { Point } from './projection';
import './city-model.css';

const MODEL_URL = '/models/private/pushpilot-city.glb';
const MAX_MODEL_BYTES = 32 * 1024 * 1024;
type Preset = 'city' | 'intersection';
type ModelStatus = { kind: 'loading' | 'ready' | 'error' | 'lost'; message: string };
interface ViewRuntime { preset: (preset: Preset) => void }
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

/** Preserve every original mesh transform; optimized copies live in world space. */
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

/** A display-only model. It never estimates a car pose or supplies robot coordinates. */
export function CityModelView({ map, display }: { map: TemporaryMap | null; display: RouteDisplay | null }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const runtimeRef = useRef<ViewRuntime | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [preset, setPreset] = useState<Preset>('city');
  const [status, setStatus] = useState<ModelStatus>({ kind: 'loading', message: 'Loading the supplied city model…' });
  const [projection, setProjection] = useState<CityProjection | null>(null);
  const routePreview = useMemo(() => {
    const fit = cityPreviewFit(map);
    if (!fit || !projection || !display) return null;
    const project = (point: Point) => projectCityPreview(point, fit, projection);
    const projected = projectRouteDisplay(display, project);
    const corners: Point[] = [[fit.left, fit.top], [fit.left + fit.width, fit.top],
      [fit.left + fit.width, fit.top + fit.height], [fit.left, fit.top + fit.height]];
    const boundary = corners.map(project);
    return projected ? { display: projected, boundary: boundary.every((point): point is Point => point !== null) ? boundary : undefined } : null;
  }, [map, display, projection]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let disposed = false, loadValid = true, failed = false, intersecting = true, userViewModified = false, modelReady = false;
    let width = 1, height = 1, frame = 0;
    let activePreset: Preset = 'city';
    let presetCamera: THREE.PerspectiveCamera | null = null;
    let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer, controls: OrbitControls;
    const modelResources = resources();
    const abort = new AbortController();
    const draco = new DRACOLoader().setDecoderPath('/vendor/draco/').setWorkerLimit(2);
    let resizeObserver: ResizeObserver | undefined, intersectionObserver: IntersectionObserver | undefined;
    let loadDeadline: number | undefined;
    setStatus({ kind: 'loading', message: 'Loading the supplied city model…' });
    setPreset('city');
    setProjection(null);

    const active = () => !disposed && !failed && intersecting && !document.hidden;
    const render = () => {
      frame = 0;
      if (!active()) return;
      try {
        const changing = controls.update();
        renderer.render(scene, camera);
        // Share the exact rendered camera, including its lens offset, with the SVG.
        const matrix = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).toArray();
        setProjection(previous => previous?.width === width && previous.height === height
          && previous.matrix.every((value, index) => value === matrix[index]) ? previous : { width, height, matrix });
        if (changing) requestRender();
      } catch {
        failed = true;
        setStatus({ kind: 'error', message: 'The 3D view could not render. Reload the model to try again.' });
      }
    };
    function requestRender() { if (active() && !frame) frame = requestAnimationFrame(render); }
    const pause = () => { if (frame) cancelAnimationFrame(frame); frame = 0; };
    const onInteraction = () => { userViewModified = true; };
    const onVisibility = () => { if (active()) requestRender(); else pause(); };
    const onContextLost = (event: Event) => {
      event.preventDefault(); failed = true; pause();
      setStatus({ kind: 'lost', message: 'The graphics context was interrupted. Reload the 3D view to continue.' });
    };
    const onContextRestored = () => {
      setStatus({ kind: 'error', message: 'Graphics are available again. Reload the model to restore the 3D view.' });
    };
    const viewInsets = () => {
      const styles = getComputedStyle(host);
      const left = Math.max(20, Number.parseFloat(styles.getPropertyValue('--stage-content-left')) || 100);
      const right = width > 760 ? Math.min(width * .37, Number.parseFloat(styles.getPropertyValue('--stage-overlay-width')) || 340) : 25;
      return { left, right, availableWidth: Math.max(width * .48, width - left - right - 32) };
    };
    const applyProjection = () => {
      camera.aspect = width / height;
      const { left, right } = viewInsets();
      // Shift the lens, not the model: the city stays under the existing glass cards.
      camera.setViewOffset(width, height, Math.max(0, (right - left) * .46), 0, width, height);
      camera.updateProjectionMatrix();
    };
    const applyPreset = (next: Preset) => {
      activePreset = next; userViewModified = false;
      const { availableWidth } = viewInsets();
      if (next === 'intersection') {
        controls.target.set(0, 0, 0); camera.position.set(36, 275, 325); camera.fov = 35;
      } else {
        let target = new THREE.Vector3(0, 0, 0), position = new THREE.Vector3(30, 650, 760);
        camera.fov = 33;
        if (presetCamera) {
          position = presetCamera.getWorldPosition(new THREE.Vector3());
          const direction = presetCamera.getWorldDirection(new THREE.Vector3());
          if (direction.y < -.05) target = position.clone().addScaledVector(direction, -position.y / direction.y);
          camera.fov = Math.max(28, Math.min(38, presetCamera.fov));
        }
        const offset = position.clone().sub(target);
        // Frame the 594 × 420 board, never the unrelated 6000-unit ground plane.
        const horizontalFov = 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * availableWidth / height);
        const distance = Math.max(offset.length(), 322 / Math.tan(horizontalFov / 2));
        offset.setLength(distance);
        camera.position.copy(target).add(offset); controls.target.copy(target);
      }
      applyProjection(); controls.update(); requestRender();
    };
    const resize = () => {
      width = Math.max(1, host.clientWidth); height = Math.max(1, host.clientHeight);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      renderer.setSize(width, height, false);
      if (modelReady && !userViewModified) applyPreset(activePreset);
      else applyProjection();
      requestRender();
    };

    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
      renderer.setClearColor('#edf0ee', 0);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.15;
      renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.domElement.className = 'city-model-canvas';
      renderer.domElement.setAttribute('role', 'img');
      renderer.domElement.setAttribute('aria-label', 'Interactive Spatial city preview. The 2D route is illustrative; city alignment is pending.');
      renderer.domElement.addEventListener('webglcontextlost', onContextLost);
      renderer.domElement.addEventListener('webglcontextrestored', onContextRestored);
      host.appendChild(renderer.domElement);
      scene = new THREE.Scene();
      scene.fog = new THREE.Fog('#edf0ee', 1700, 4300);
      camera = new THREE.PerspectiveCamera(33, 1, 1, 7000);
      camera.position.set(30, 650, 760);
      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true; controls.dampingFactor = .09;
      controls.minDistance = 170; controls.maxDistance = 1900;
      controls.minPolarAngle = .12; controls.maxPolarAngle = Math.PI * .465;
      controls.maxTargetRadius = 390;
      controls.enablePan = true; controls.screenSpacePanning = false;
      controls.addEventListener('change', requestRender);
      controls.addEventListener('start', onInteraction);
      scene.add(new THREE.HemisphereLight('#dce9ff', '#84785e', 1.65));
      const sun = new THREE.DirectionalLight('#ffead0', 2.5);
      sun.position.set(-640, 720, 540); sun.castShadow = true;
      sun.shadow.mapSize.set(1024, 1024); sun.shadow.bias = -.0004; sun.shadow.normalBias = .55;
      Object.assign(sun.shadow.camera, { left: -395, right: 395, top: 345, bottom: -345, near: 50, far: 1800 });
      scene.add(sun); scene.add(sun.target);
      resize(); applyPreset('city');
      resizeObserver = new ResizeObserver(resize); resizeObserver.observe(host);
      intersectionObserver = new IntersectionObserver(entries => {
        intersecting = entries.some(entry => entry.isIntersecting); onVisibility();
      }, { threshold: .01 });
      intersectionObserver.observe(host);
      document.addEventListener('visibilitychange', onVisibility);
      runtimeRef.current = { preset: applyPreset };
      const loader = new GLTFLoader().setDRACOLoader(draco);
      loadDeadline = window.setTimeout(() => {
        if (disposed || !loadValid) return;
        loadValid = false; abort.abort(); draco.dispose();
        setStatus({ kind: 'error', message: 'The city model took too long to load. Check the model files and reload.' });
      }, 45_000);
      void (async () => {
        let gltf: GLTF | undefined;
        try {
          const response = await fetch(MODEL_URL, { signal: abort.signal, credentials: 'same-origin' });
          if (!response.ok) throw new Error(response.status === 404
            ? 'The private city model is missing. Install pushpilot-city.glb, then reload.'
            : `The city model request failed (${response.status}). Reload to try again.`);
          const declaredSize = Number(response.headers.get('content-length'));
          if (declaredSize > MAX_MODEL_BYTES) throw new Error('The supplied city model exceeds the supported 32 MB size.');
          const buffer = await response.arrayBuffer();
          if (buffer.byteLength > MAX_MODEL_BYTES) throw new Error('The supplied city model exceeds the supported 32 MB size.');
          if (buffer.byteLength < 20 || new DataView(buffer).getUint32(0, true) !== 0x46546c67) {
            throw new Error('The private city model is missing or invalid. Install pushpilot-city.glb, then reload.');
          }
          if (!loadValid || disposed) return;
          gltf = await loader.parseAsync(buffer, '/models/private/');
          if (failed || !loadValid || disposed) {
            window.clearTimeout(loadDeadline);
            const staleResources = resources(); rememberObject(gltf.scene, staleResources); disposeResources(staleResources); return;
          }
          rememberObject(gltf.scene, modelResources);
          neutralizeBakedSignals(gltf.scene, modelResources);
          softenStagingPlane(gltf.scene, modelResources);
          gltf.scene.updateMatrixWorld(true);
          gltf.scene.traverse(object => {
            if (object instanceof THREE.PerspectiveCamera && (object.name === 'cam_wide' || object.parent?.name === 'cam_wide')) presetCamera = object;
          });
          const optimized = optimizeStaticModel(gltf.scene, modelResources);
          scene.add(gltf.scene, optimized);
          modelReady = true;
          loadValid = false; window.clearTimeout(loadDeadline);
          applyPreset(activePreset);
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
      runtimeRef.current = null;
      document.removeEventListener('visibilitychange', onVisibility);
      resizeObserver?.disconnect(); intersectionObserver?.disconnect();
      if (controls!) { controls.removeEventListener('change', requestRender); controls.removeEventListener('start', onInteraction); controls.dispose(); }
      draco.dispose();
      disposeResources(modelResources);
      if (scene!) {
        scene.traverse(object => { if (object instanceof THREE.DirectionalLight) object.shadow.dispose(); });
        scene.clear();
      }
      if (renderer!) {
        renderer.domElement.removeEventListener('webglcontextlost', onContextLost);
        renderer.domElement.removeEventListener('webglcontextrestored', onContextRestored);
        renderer.renderLists.dispose(); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
      }
    };
  }, [attempt]);

  const selectPreset = (next: Preset) => { runtimeRef.current?.preset(next); setPreset(next); };
  return <div className="city-model-view">
    <div className="city-model-host" ref={hostRef}/>
    {status.kind === 'ready' && routePreview && projection && <svg className="city-route-preview"
      viewBox={`0 0 ${projection.width} ${projection.height}`} role="img" aria-label="Current 2D route preview on the city. Alignment pending; no measured vehicle position.">
      <title>The same selected 2D path, direction, stop lines and simulation progress as Camera. Approximate display fit only.</title>
      <RouteOverlay display={routePreview.display} scale={Math.max(.9, Math.min(1.4, projection.width / 900))} boundary={routePreview.boundary}/>
    </svg>}
    {status.kind !== 'ready' && <div className={`city-model-state city-model-state-${status.kind}`} role={status.kind === 'loading' ? 'status' : 'alert'}>
      {status.kind === 'loading' && <span className="city-model-loading-dot" aria-hidden="true"/>}
      <strong>{status.kind === 'loading' ? 'Opening Spatial' : 'Spatial unavailable'}</strong>
      <span>{status.message}</span>
      {status.kind !== 'loading' && <button type="button" onClick={() => setAttempt(value => value + 1)}>Reload 3D view</button>}
    </div>}
    <div className="city-model-view-controls" aria-label="3D view controls">
      <span className="city-model-concept">3D concept</span>
      <div className="city-model-presets">
        <button type="button" aria-pressed={preset === 'city'} onClick={() => selectPreset('city')} disabled={status.kind !== 'ready'}>City</button>
        <button type="button" aria-pressed={preset === 'intersection'} onClick={() => selectPreset('intersection')} disabled={status.kind !== 'ready'}>Intersection</button>
      </div>
      <button type="button" className="city-model-reset" onClick={() => selectPreset('city')} disabled={status.kind !== 'ready'} aria-label="Reset the 3D city view" title="Reset the 3D city view">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 10a9 9 0 1 1 2.6 8.3M3 4v6h6"/></svg>
      </button>
      <span className="city-model-gesture">Drag to orbit · Pinch to zoom</span>
    </div>
  </div>;
}

export default CityModelView;
