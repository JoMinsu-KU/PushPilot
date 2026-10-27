import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState } from 'react';
import type { MapRoute, SceneSnapshot, TemporaryMap } from '../../contracts/scene';
import type { LiveCameraSnapshot } from '../../contracts/live-camera';
import type { WorkspaceSnapshot } from '../../contracts/workspace';
import { Icon } from './Icons';
import { projectPoint, type Point } from './projection';
import { createRouteDisplay, projectRouteDisplay, type RouteDisplay } from './routeProgress';
import { RouteLegend, RouteOverlay } from './RouteOverlay';
import { CityViewBoundary } from './CityViewBoundary';
import { nodeLabel } from './mapMetadata';
import { recordedDisplay } from './boardFocus';
import { createLivePollGate, liveDisplaySnapshot, liveFrameAge, liveFrameFresh, liveOverlayAllowed } from './liveCamera';
import './map-scene.css';

const CityModelView = lazy(() => import('./CityModelView'));

const MAX_FRAME_BYTES = 8 * 1024 * 1024;
const usableRegistration = new Set(['locked', 'locked_partial']);
const registrationLabels: Record<SceneSnapshot['registration']['status'], string> = {
  unregistered: 'Unregistered', partial: 'Partial markers', candidate: 'Candidate overlay',
  locked: 'Test view locked', locked_partial: 'Locked · partial view', view_changed: 'View changed · overlay hidden',
};

function responseMessage(payload: unknown): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = payload.detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message;
  }
  return 'The scene request failed. Refresh the frame state and try again.';
}

function captureLabel(frame: NonNullable<SceneSnapshot['frame']>) {
  if (!frame.captured_at || frame.timestamp_source === 'unknown') return 'Capture time unknown';
  return `Captured ${new Date(frame.captured_at).toLocaleString('en-US')}`;
}

// The same affine projection is used for the drawing, route and destination pins.
// Building heights and facade details are illustrative, never measured obstacles.
function architecturalPoint(x: number, y: number, z = 0): Point {
  return [240 + .94 * x - .7 * y, 35 + .29 * x + .54 * y - z];
}
function polygon(points: Point[]) { return points.map(point => point.join(',')).join(' '); }

function BuildingVolume({ bounds, name, selected, index }: { bounds: [number, number, number, number]; name: string; selected: boolean; index: number }) {
  const [left, top, right, bottom] = bounds;
  const x0 = left + 7, y0 = top + 8, x1 = right - 7, y1 = bottom - 7;
  const height = index === 2 ? 24 : index === 1 ? 20 : 18;
  const p = architecturalPoint;
  const roof = [p(x0, y0, height), p(x1, y0, height), p(x1, y1, height), p(x0, y1, height)];
  const sign = p((x0 + x1) / 2, y1, height / 2);
  const unit = (x: number, y: number, width: number, depth: number) => <g>
    <polygon points={polygon([p(x, y, height + 3), p(x + width, y, height + 3), p(x + width, y + depth, height + 3), p(x, y + depth, height + 3)])} fill="#eeeFEB" stroke="#b9bdb8" strokeWidth=".45"/>
    <polygon points={polygon([p(x, y + depth, height), p(x + width, y + depth, height), p(x + width, y + depth, height + 3), p(x, y + depth, height + 3)])} fill="#d2d5cf" stroke="#b9bdb8" strokeWidth=".4"/>
    {[2, 4, 6].map(offset => <line key={offset} x1={p(x + offset, y + 1, height + 3)[0]} y1={p(x + offset, y + 1, height + 3)[1]} x2={p(x + offset, y + depth - 1, height + 3)[0]} y2={p(x + offset, y + depth - 1, height + 3)[1]} stroke="#b4b9b3" strokeWidth=".45"/>)}
  </g>;
  return <g className="architectural-building">
    <polygon points={polygon([p(x0 + 8, y0 + 9), p(x1 + 9, y0 + 9), p(x1 + 9, y1 + 9), p(x0 + 8, y1 + 9)])} fill="#b6bbb4" opacity=".16"/>
    <polygon points={polygon([p(x0, y1), p(x1, y1), p(x1, y1, height), p(x0, y1, height)])} fill="#e8e8e1" stroke="#aeb4ad" strokeWidth=".55"/>
    <polygon points={polygon([p(x1, y0), p(x1, y1), p(x1, y1, height), p(x1, y0, height)])} fill="#d9ddd6" stroke="#aeb4ad" strokeWidth=".55"/>
    {Array.from({ length: 10 }, (_, number) => {
      const x = x0 + 4 + number * (x1 - x0 - 10) / 10;
      return <polygon key={number} points={polygon([p(x, y1, 3), p(x + 6, y1, 3), p(x + 6, y1, height - 6), p(x, y1, height - 6)])} fill={number % 3 === 0 ? '#c2cfcb' : '#d6dfd9'} stroke="#aeb9b1" strokeWidth=".35"/>;
    })}
    {[0, 1, 2, 3].map(number => {
      const y = y0 + 4 + number * 7;
      return <polygon key={number} points={polygon([p(x1, y, 4), p(x1, y + 4, 4), p(x1, y + 4, height - 5), p(x1, y, height - 5)])} fill="#c4d0c8" stroke="#a9b4ac" strokeWidth=".35"/>;
    })}
    <polygon points={polygon(roof)} fill="#f8f8f3" stroke="#aeb4ad" strokeWidth=".65"/>
    <polygon points={polygon([p(x0 + 2, y0 + 2, height), p(x1 - 2, y0 + 2, height), p(x1 - 2, y1 - 2, height), p(x0 + 2, y1 - 2, height)])} fill="none" stroke="#d9dcd5" strokeWidth=".55"/>
    {[1, 2, 3].map(number => <line key={number} x1={p(x0 + number * (x1 - x0) / 4, y0 + 2, height)[0]} y1={p(x0 + number * (x1 - x0) / 4, y0 + 2, height)[1]} x2={p(x0 + number * (x1 - x0) / 4, y1 - 2, height)[0]} y2={p(x0 + number * (x1 - x0) / 4, y1 - 2, height)[1]} stroke="#e2e4de" strokeWidth=".4"/>)}
    {unit(x0 + 9, y0 + 8, 12, 8)}{unit(x0 + 26, y0 + 8, 12, 8)}
    <polygon points={polygon([p(x1 - 28, y0 + 7, height + .3), p(x1 - 9, y0 + 7, height + .3), p(x1 - 9, y1 - 6, height + .3), p(x1 - 28, y1 - 6, height + .3)])} fill="#dae3df" stroke="#b9c5bd" strokeWidth=".45"/>
    <text x={sign[0]} y={sign[1] - 1} textAnchor="middle" fontSize="4.8" letterSpacing=".6" fill="#5e685e" paintOrder="stroke" stroke="#f4f5ef" strokeWidth="1.5">{name}</text>
    {selected && <line x1={p(x0, y1, height)[0]} y1={p(x0, y1, height)[1]} x2={p(x1, y1, height)[0]} y2={p(x1, y1, height)[1]} stroke="#da744e" strokeWidth="1.1"/>}
  </g>;
}

function SpatialMap({ map, route, display }: { map: TemporaryMap; route: MapRoute | null; display: RouteDisplay | null }) {
  const id = useId().replace(/:/g, '');
  const byId = new Map(map.nodes.map(node => [node.id, node]));
  const validRoute = route?.map_hash === map.geometry_hash && route.map_id === map.id && route.map_version === map.version ? route : null;
  const width = map.board.width_mm, height = map.board.height_mm;
  const p = architecturalPoint;
  const projectedDisplay = display ? projectRouteDisplay(display, ([x, y]) => p(x, y)) : null;
  const extent = [p(0, 0), p(width, 0), p(width, height), p(0, height)];
  const minX = Math.min(...extent.map(point => point[0])) - 45, minY = Math.min(...extent.map(point => point[1])) - 55;
  const viewBox = [minX, minY, Math.max(...extent.map(point => point[0])) - minX + 45, Math.max(...extent.map(point => point[1])) - minY + 55];
  const destination = validRoute ? byId.get(validRoute.destination) : null;
  const destinationPoint = destination ? p(destination.x_mm, destination.y_mm) : null;
  return <div className="spatial-map-wrap">
    <svg className="spatial-map" viewBox={viewBox.join(' ')} preserveAspectRatio="xMidYMid meet" role="img"
      aria-label={`Illustrative architectural view of ${map.title}; temporary road geometry${validRoute ? ` with route from ${validRoute.start} to ${validRoute.destination}` : ''}; building volumes are not a physical scan`}>
      <defs><radialGradient id={`${id}-ground-shadow`}><stop stopColor="#a2a99f" stopOpacity=".22"/><stop offset="1" stopColor="#a2a99f" stopOpacity="0"/></radialGradient></defs>
      <ellipse cx="340" cy="218" rx="290" ry="111" fill={`url(#${id}-ground-shadow)`}/>
      <polygon points={polygon([p(0, height), p(width, height), p(width, height, -5), p(0, height, -5)])} fill="#dadfd6" stroke="#c1c9bd" strokeWidth=".4"/>
      <polygon points={polygon([p(width, 0), p(width, height), p(width, height, -5), p(width, 0, -5)])} fill="#d1d8cd" stroke="#c1c9bd" strokeWidth=".4"/>
      <polygon points={polygon([p(0, 0), p(width, 0), p(width, height), p(0, height)])} fill="#f0f1eb" stroke="#c6cec1" strokeWidth=".7"/>
      <g transform="matrix(.94 .29 -.7 .54 240 35)">
        {Array.from({ length: Math.floor(width / 20) + 1 }, (_, index) => <line key={`x${index}`} x1={index * 20} y1="0" x2={index * 20} y2={height} stroke="#d9ddd3" strokeWidth=".35"/>)}
        {Array.from({ length: Math.floor(height / 20) + 1 }, (_, index) => <line key={`y${index}`} x1="0" y1={index * 20} x2={width} y2={index * 20} stroke="#d9ddd3" strokeWidth=".35"/>)}
        {map.edges.map(edge => {
          const from = byId.get(edge.from), to = byId.get(edge.to);
          return from && to ? <line key={`${edge.from}-${edge.to}`} x1={from.x_mm} y1={from.y_mm} x2={to.x_mm} y2={to.y_mm} stroke="#daddd4" strokeWidth={map.board.road_width_mm + 2} strokeLinecap="square"/> : null;
        })}
        {map.edges.map(edge => {
          const from = byId.get(edge.from), to = byId.get(edge.to);
          return from && to ? <g key={`${edge.from}-${edge.to}`}><line x1={from.x_mm} y1={from.y_mm} x2={to.x_mm} y2={to.y_mm} stroke="#fcfcf8" strokeWidth={map.board.road_width_mm} strokeLinecap="square"/><line x1={from.x_mm} y1={from.y_mm} x2={to.x_mm} y2={to.y_mm} stroke="#ccd0c6" strokeWidth=".7" strokeDasharray="4 5"/></g> : null;
        })}
        {map.building_panels.map(panel => <rect key={panel.id} x={panel.bounds_mm[0]} y={panel.bounds_mm[1]} width={panel.bounds_mm[2] - panel.bounds_mm[0]} height={panel.bounds_mm[3] - panel.bounds_mm[1]} fill="#e4e9dd" stroke="#c8d0c0" strokeWidth=".6"/>)}
        {map.markers.map(marker => <rect key={marker.id} x={marker.center_mm[0] - 4} y={marker.center_mm[1] - 4} width="8" height="8" fill="#fbfcf8" stroke="#aeb9a7" strokeWidth=".65"/>)}
      </g>
      {map.building_panels.map((panel, index) => <BuildingVolume key={panel.id} bounds={panel.bounds_mm} name={nodeLabel(map, panel.id)} selected={panel.id === validRoute?.destination} index={index}/>)}
      {map.nodes.filter(node => node.kind === 'junction').map(node => {
        const point = p(node.x_mm, node.y_mm);
        return <text key={node.id} x={point[0]} y={point[1] + 2} textAnchor="middle" fill="#9ca696" fontSize="5">{node.id}</text>;
      })}
      <RouteOverlay display={projectedDisplay} scale={.8} boundary={extent}/>
      {destinationPoint && <g className="architectural-destination">
        <path d={`M${destinationPoint[0]} ${destinationPoint[1] - 4}v-17`} stroke="#7b8d75" strokeWidth=".7"/>
        <rect x={destinationPoint[0] - 31} y={destinationPoint[1] - 37} width="62" height="19" rx="7" fill="#ffffffed" stroke="#d0d9ca" strokeWidth=".6"/>
        <circle cx={destinationPoint[0] - 21} cy={destinationPoint[1] - 27.5} r="2" fill="#81a078"/>
        <text x={destinationPoint[0] + 3} y={destinationPoint[1] - 25.4} textAnchor="middle" fontSize="5.8" fill="#56634e">{nodeLabel(map, validRoute?.destination)}</text>
      </g>}
      <g stroke="#a9b3a2" strokeWidth=".5"><line x1={p(0, height + 16)[0]} y1={p(0, height + 16)[1]} x2={p(width, height + 16)[0]} y2={p(width, height + 16)[1]}/><line x1={p(0, height + 11)[0]} y1={p(0, height + 11)[1]} x2={p(0, height + 21)[0]} y2={p(0, height + 21)[1]}/><line x1={p(width, height + 11)[0]} y1={p(width, height + 11)[1]} x2={p(width, height + 21)[0]} y2={p(width, height + 21)[1]}/></g>
      <text x={p(width / 2, height + 30)[0]} y={p(width / 2, height + 30)[1]} fontSize="5.8" fill="#9aa592" textAnchor="middle" letterSpacing=".5">{width} mm · drawing coordinates</text>
    </svg>
  </div>;
}

function CameraFrame({ scene, route, map, focused, display, live = false, fresh = true }: { scene: SceneSnapshot | LiveCameraSnapshot; route: MapRoute | null; map: TemporaryMap | null; focused: boolean; display: RouteDisplay | null; live?: boolean; fresh?: boolean }) {
  const id = useId().replace(/:/g, '');
  const frame = scene.frame!;
  const matrix = scene.registration.homography;
  const matchesMap = Boolean(map && route && route.map_hash === map.geometry_hash && route.map_id === map.id && route.map_version === map.version
    && scene.map_hash === map.geometry_hash && scene.map_id === map.id && scene.map_version === map.version);
  const overlayAllowed = live ? liveOverlayAllowed(scene as LiveCameraSnapshot, route, map, fresh)
    : matchesMap && usableRegistration.has(scene.registration.status) && Boolean(matrix);
  const projectedDisplay = overlayAllowed && display ? projectRouteDisplay(display, point => projectPoint(point, matrix!)) : null;
  const boundary = overlayAllowed && map ? ([[0, 0], [map.board.width_mm, 0], [map.board.width_mm, map.board.height_mm], [0, map.board.height_mm]] as Point[])
    .map(point => projectPoint(point, matrix!)) : [];
  const routeBoundary = boundary.every((point): point is Point => point !== null) ? boundary : undefined;
  const scale = frame.width / 530;
  const candidate = scene.registration.status === 'candidate';
  const { viewport, quad } = recordedDisplay(scene, map, focused);
  return <div className="recorded-frame-wrap">
    <svg className="recorded-frame" viewBox={viewport.join(' ')} preserveAspectRatio="xMidYMid meet"
      style={{ aspectRatio: `${viewport[2]} / ${viewport[3]}`, maxWidth: `${viewport[2]}px`, maxHeight: `${viewport[3]}px` }} role="img"
      aria-label={`${live ? 'Live' : 'Recorded'} workspace image${live && !fresh ? ' · stale' : ''}${projectedDisplay ? ' with test-only route overlay' : ''}`}>
      {quad && <defs><clipPath id={`${id}-board-mask`}><polygon points={polygon(quad)}/></clipPath></defs>}
      {quad && <polygon className="recorded-board-edge" points={polygon(quad)} fill="#fff" stroke="#fff" strokeWidth={scale * 1.2}/>}
      <g clipPath={quad ? `url(#${id}-board-mask)` : undefined}>
      <image href={frame.image_url} x="0" y="0" width={frame.width} height={frame.height} preserveAspectRatio="xMidYMid meet"/>
      {scene.detection.markers.map(marker => <g key={marker.id}>
        <polygon points={marker.corners.map(point => point.join(',')).join(' ')} fill="none" stroke="#f3cb79" strokeWidth={1.2 * scale}/>
        {marker.corners[0] && <text x={marker.corners[0][0]} y={marker.corners[0][1] - 4 * scale}
          fill="#ffe4a5" stroke="#102333" strokeWidth={.35 * scale} paintOrder="stroke" fontSize={7 * scale}>{marker.id}</text>}
      </g>)}
      <RouteOverlay display={projectedDisplay} scale={scale} boundary={routeBoundary}/>
      </g>
    </svg>
    {scene.registration.status === 'view_changed' && <div className="overlay-inhibition"><Icon name="shield" size={17}/>View changed. The previous overlay is hidden.</div>}
    {live && !fresh ? <div className="overlay-inhibition live-warning"><Icon name="clock" size={17}/>STALE · Last decoded image. Route overlay is hidden.</div>
      : scene.registration.status === 'locked_occluded' ? <div className="overlay-inhibition partial live-warning"><Icon name="eye" size={17}/>Markers obscured · fixed mapping retained; view stability is unconfirmed.</div>
      : scene.registration.status === 'locked_partial' && <div className={`overlay-inhibition partial ${live ? 'live-warning' : ''}`}><Icon name="eye" size={17}/>Some markers are obscured. The locked test mapping is retained.</div>}
    {matchesMap && !overlayAllowed && scene.registration.status !== 'view_changed' && (!live || fresh) && <div className="overlay-note">{candidate ? `Lock the ${live ? 'live' : 'test'} view to project the planned route.` : 'Route overlay requires a valid locked test registration.'}</div>}
  </div>;
}

interface DecodedLiveView { snapshot: LiveCameraSnapshot; receivedAt: number }

/** Decode first, then replace image and geometry together. Recorded evidence is untouched. */
function useLiveCamera() {
  const [status, setStatus] = useState<LiveCameraSnapshot | null>(null);
  const [decoded, setDecoded] = useState<DecodedLiveView | null>(null);
  const [clock, setClock] = useState(() => performance.now());
  const displayed = useRef<DecodedLiveView | null>(null);
  const pollGate = useRef(createLivePollGate());
  const applyRegistration = useCallback((snapshot: LiveCameraSnapshot) => {
    pollGate.current.registrationApplied();
    setStatus(snapshot);
  }, []);
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const controller = new AbortController();
    const tick = window.setInterval(() => setClock(performance.now()), 250);
    const poll = async () => {
      let delay = 1000;
      const generation = pollGate.current.begin();
      const receivedAt = performance.now();
      try {
        const response = await fetch('/api/v1/live-camera', { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error('Live camera status is unavailable.');
        const snapshot = await response.json() as LiveCameraSnapshot;
        if (snapshot.schema_version !== 'pushpilot.live-camera.v1' || cancelled || !pollGate.current.accept(generation, snapshot)) return;
        setStatus(snapshot);
        delay = snapshot.enabled ? 125 : 2000;
        if (snapshot.frame) {
          const currentView = displayed.current;
          if (currentView?.snapshot.frame?.id !== snapshot.frame.id || currentView.snapshot.epoch !== snapshot.epoch) {
            const image = new Image();
            image.src = snapshot.frame.image_url;
            let timeout: number | undefined;
            try {
              await Promise.race([image.decode(), new Promise<never>((_, reject) => {
                timeout = window.setTimeout(() => reject(new Error('Live image decode timed out.')), 1250);
              })]);
              if (image.naturalWidth !== snapshot.frame.width || image.naturalHeight !== snapshot.frame.height) {
                throw new Error('Live image dimensions do not match its frame geometry.');
              }
            } finally { window.clearTimeout(timeout); }
          }
          if (cancelled || !pollGate.current.accept(generation, snapshot)) return;
          const next = { snapshot, receivedAt };
          displayed.current = next;
          setDecoded(next);
        }
      } catch {
        // Keep the previous decoded image; its monotonic age will mark it stale.
      } finally {
        if (!cancelled) timer = window.setTimeout(() => void poll(), delay);
      }
    };
    void poll();
    return () => { cancelled = true; controller.abort(); window.clearTimeout(timer); window.clearInterval(tick); };
  }, []);
  return { status, decoded, clock, applyRegistration };
}

function sceneTextPages(text: string, limit: number, lineLimit = 6): string[] {
  const pages: string[] = [];
  let offset = 0;
  while (offset < text.length) {
    let end = Math.min(offset + limit, text.length);
    let lines = 0;
    for (let position = offset; position < end; position++) {
      if (text[position] === '\n' && ++lines === lineLimit) { end = position + 1; break; }
    }
    if (end === offset + limit && end < text.length) {
      const boundary = text.lastIndexOf(' ', end - 1);
      if (boundary > offset + limit * .65) end = boundary + 1;
    }
    pages.push(text.slice(offset, end)); offset = end;
  }
  return pages.length ? pages : [''];
}

function TextPages({ text, pageSize = 160 }: { text: string; pageSize?: number }) {
  const [page, setPage] = useState(0);
  const pages = sceneTextPages(text, pageSize);
  const count = pages.length;
  const currentPage = Math.min(page, count - 1);
  useEffect(() => setPage(0), [text, pageSize]);
  return <div className="scene-text-pages"><p>{pages[currentPage]}</p>
    {count > 1 && <div className="scene-pagination"><button disabled={currentPage === 0} onClick={() => setPage(value => Math.max(0, value - 1))} aria-label="Previous text page">Previous</button><span>{currentPage + 1} / {count}</span><button disabled={currentPage === count - 1} onClick={() => setPage(value => value + 1)} aria-label="Next text page">Next</button></div>}
  </div>;
}

function ExpectedPrompt({ value, disabled, onChange }: { value: string; disabled: boolean; onChange: (value: string) => void }) {
  const [pages, setPages] = useState(() => sceneTextPages(value, 200, 4));
  const [page, setPage] = useState(0);
  const currentPage = Math.min(page, pages.length - 1);
  useEffect(() => {
    if (value !== pages.join('')) { setPages(sceneTextPages(value, 200, 4)); setPage(0); }
  }, [value, pages]);
  const update = (text: string) => {
    const available = 1000 - (value.length - pages[currentPage].length);
    const replacement = sceneTextPages(text.slice(0, available), 200, 4);
    const next = [...pages.slice(0, currentPage), ...replacement, ...pages.slice(currentPage + 1)];
    setPages(next); setPage(currentPage + replacement.length - 1); onChange(next.join(''));
  };
  return <div className="scene-prompt-editor"><label className="scene-field">Expected scene or action outcome<textarea value={pages[currentPage]} maxLength={1000 - (value.length - pages[currentPage].length)} rows={5} disabled={disabled} onChange={event => update(event.target.value)}/></label><div className="scene-pagination"><button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button><span>Prompt {currentPage + 1} / {pages.length} · {value.length}/1000</span><button disabled={currentPage === pages.length - 1} onClick={() => setPage(currentPage + 1)}>Next</button><button disabled={disabled || !pages.at(-1) || value.length >= 1000} onClick={() => { setPages([...pages, '']); setPage(pages.length); }}>Add page</button></div></div>;
}

export function MapScene({ workspace, readOnly = false, onSnapshot, onPreviewSource, onMapSnapshot, openToolsRequest = 0, presentation = 'panel' }: {
  workspace: WorkspaceSnapshot | null; readOnly?: boolean; onSnapshot: (snapshot: SceneSnapshot) => void; onPreviewSource?: (label: string) => void; onMapSnapshot?: (map: TemporaryMap) => void; openToolsRequest?: number; presentation?: 'panel' | 'stage';
}) {
  const [map, setMap] = useState<TemporaryMap | null>(null);
  const [scene, setScene] = useState<SceneSnapshot | null>(null);
  const [view, setView] = useState<'camera' | 'spatial' | 'city'>('camera');
  const [cameraSource, setCameraSource] = useState<'auto' | 'live' | 'recorded'>('auto');
  const [lockingLive, setLockingLive] = useState(false);
  const live = useLiveCamera();
  const [expanded, setExpanded] = useState(false);
  const [toolTab, setToolTab] = useState<'image' | 'registration' | 'muse' | 'result' | 'evidence'>('image');
  const [focused, setFocused] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<'upload' | 'registration' | 'inspection' | null>(null);
  const [capturedAt, setCapturedAt] = useState('');
  const [expected, setExpected] = useState('Inspect the selected temporary map. Report visible places, car visibility and signal color. Do not infer physical motion.');
  const fileInput = useRef<HTMLInputElement>(null);
  const toolsDialog = useRef<HTMLDialogElement>(null);
  const current = useRef<SceneSnapshot | null>(null);
  const currentExpectation = workspace?.plan?.steps[workspace.current_step]?.description;
  const active = Boolean(workspace?.approved && !['COMPLETED', 'CANCELLED', 'FAULT', 'RECOVERY_REQUIRED'].includes(workspace.state));
  const accept = useCallback((snapshot: SceneSnapshot) => {
    if (snapshot.schema_version !== 'pushpilot.scene.v1') throw new Error('Unsupported scene snapshot version.');
    if (current.current && current.current.revision > snapshot.revision) return;
    current.current = snapshot;
    setScene(snapshot);
    onSnapshot(snapshot);
  }, [onSnapshot]);
  const refresh = useCallback(async (reportFailure = false) => {
    try {
      const response = await fetch('/api/v1/scene', { cache: 'no-store' });
      if (!response.ok) throw new Error('Recorded-image inspection is not available from this backend yet.');
      accept(await response.json() as SceneSnapshot);
    } catch (err) { if (reportFailure) setError(err instanceof Error ? err.message : 'The scene service is unavailable.'); }
  }, [accept]);
  const refreshMap = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/map', { cache: 'no-store' });
      if (!response.ok) throw new Error('The temporary map service is unavailable.');
      const data = await response.json() as TemporaryMap;
      if (data.schema_version !== 'pushpilot.temporary-map.v1') throw new Error('Unsupported temporary map version.');
      setMap(data);
    } catch (err) { setError(err instanceof Error ? err.message : 'The map could not be loaded.'); }
  }, []);
  useEffect(() => {
    void refreshMap();
    void refresh(true);
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [refresh, refreshMap]);
  useEffect(() => { if (map) onMapSnapshot?.(map); }, [map, onMapSnapshot]);
  useEffect(() => { if (currentExpectation) setExpected(currentExpectation); }, [currentExpectation]);
  useEffect(() => { if (openToolsRequest > 0) { setToolTab('image'); setExpanded(true); } }, [openToolsRequest]);
  useEffect(() => {
    const dialog = toolsDialog.current;
    if (!dialog) return;
    if (expanded && !dialog.open) dialog.showModal();
    if (!expanded && dialog.open) dialog.close();
  }, [expanded]);

  async function sceneCommand(kind: 'registration' | 'inspection') {
    const snapshot = current.current;
    if (!snapshot?.frame || busy || readOnly) return;
    setBusy(kind); setError('');
    try {
      const response = await fetch(`/api/v1/scene/${kind === 'inspection' ? 'reviews' : 'registration'}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: snapshot.revision, frame_id: snapshot.frame.id, ...(kind === 'inspection' ? { expected } : {}) }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        if (response.status === 409) await refresh();
        throw new Error(responseMessage(payload));
      }
      accept(payload as SceneSnapshot);
      return true;
    } catch (err) { setError(err instanceof Error ? err.message : 'The scene request failed.'); return false; }
    finally { setBusy(null); }
  }

  async function upload(file: File | undefined) {
    if (!file || busy || readOnly) return;
    if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > MAX_FRAME_BYTES) {
      setError('Choose a JPEG or PNG image no larger than 8 MiB.');
      return;
    }
    setBusy('upload'); setError('');
    try {
      const data = new FormData(); data.set('file', file);
      if (capturedAt) data.set('captured_at', new Date(capturedAt).toISOString());
      const response = await fetch('/api/v1/scene/frames', { method: 'POST', body: data });
      const payload: unknown = await response.json();
      if (!response.ok) throw new Error(responseMessage(payload));
      accept(payload as SceneSnapshot);
      setView('camera');
      setCameraSource('recorded');
    } catch (err) { setError(err instanceof Error ? err.message : 'The image upload failed.'); }
    finally { setBusy(null); if (fileInput.current) fileInput.current.value = ''; }
  }

  const route = workspace?.plan?.route ?? null;
  const routeDisplay = createRouteDisplay(route, map, workspace);
  const status = scene?.registration.status ?? 'unregistered';
  const markerCount = scene?.detection.marker_ids.filter(id => map?.markers.some(marker => marker.id === id)).length ?? 0;
  const canLock = ['candidate', 'view_changed'].includes(status) && markerCount === 4 && !active && !readOnly && !busy;
  const inspection = scene?.inspection;
  const currentInspection = inspection?.frame_id === scene?.frame?.id ? inspection : null;

  const openTools = (tab: typeof toolTab) => { setToolTab(tab); setExpanded(true); };
  const mismatchedRoute = Boolean(route && map && (route.map_hash !== map.geometry_hash || route.map_id !== map.id || route.map_version !== map.version));
  const liveAvailable = Boolean(live.status?.enabled || live.decoded);
  const usingLive = cameraSource === 'live' || (cameraSource === 'auto' && liveAvailable);
  const liveScene = live.decoded?.snapshot ?? null;
  // Inhibit withdrawn or changed registration before the next JPEG finishes decoding.
  const changedLiveScene = liveDisplaySnapshot(liveScene, live.status);
  const cameraScene = usingLive ? changedLiveScene : scene;
  const liveAge = liveFrameAge(liveScene, live.decoded?.receivedAt ?? 0, live.clock);
  const liveFresh = Boolean(live.decoded && liveFrameFresh(liveScene, live.decoded.receivedAt, live.clock)
    && live.status?.state === 'live' && live.status.epoch === liveScene?.epoch);
  const canBoardFocus = Boolean(cameraScene?.frame && recordedDisplay(cameraScene, map, true).quad);
  const hasBoardMask = Boolean(cameraScene?.frame && recordedDisplay(cameraScene, map, focused).quad);
  const liveMarkerCount = liveScene?.detection.marker_ids.filter(id => map?.markers.some(marker => marker.id === id)).length ?? 0;
  const canLockLive = Boolean(usingLive && liveScene?.frame && liveFresh && liveMarkerCount === 4
    && ['candidate', 'view_changed'].includes(liveScene.registration.status) && !active && !readOnly && !lockingLive);
  const resumeAvailable = Boolean(live.status?.saved_reference_available && changedLiveScene?.registration.status === 'unregistered');
  const canResumeLive = Boolean(usingLive && liveScene?.frame && liveFresh && resumeAvailable && !active && !readOnly && !lockingLive);
  const liveRegistrationLabel = changedLiveScene?.registration.status === 'locked_occluded' ? 'Mapping retained · markers obscured'
    : changedLiveScene?.registration.status === 'locked_partial' ? 'Mapping retained · partial markers'
    : changedLiveScene?.registration.status === 'locked' ? 'Fixed test mapping'
    : changedLiveScene?.registration.status === 'view_changed' ? 'View changed · AR hidden' : 'Live view is not locked';
  const previewSourceLabel = view === 'city' ? '3D city model' : view === 'spatial' ? 'Illustrative spatial view' : usingLive
    ? liveScene?.frame ? liveFresh ? 'Live camera' : 'Live camera · stale' : 'Live camera · connecting'
    : scene?.frame ? scene.frame.source === 'recorded' ? 'Recorded image' : 'Uploaded image' : 'No image';
  useEffect(() => { onPreviewSource?.(previewSourceLabel); }, [onPreviewSource, previewSourceLabel]);

  async function lockLiveView(resume = false) {
    if (!(resume ? canResumeLive : canLockLive) || !liveScene?.frame) return;
    setLockingLive(true); setError('');
    try {
      const response = await fetch(`/api/v1/live-camera/registration${resume ? '/resume' : ''}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(resume ? { epoch: liveScene.epoch } : { epoch: liveScene.epoch, frame_id: liveScene.frame.id }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) throw new Error(responseMessage(payload));
      live.applyRegistration(payload as LiveCameraSnapshot);
    } catch (err) { setError(err instanceof Error ? err.message : 'The live view could not be locked.'); }
    finally { setLockingLive(false); }
  }

  return <div className={`map-scene-component map-scene-${presentation}`}>
    <div className="map-scene-controls">
      <div className="scene-view-toggle" role="group" aria-label="Scene view">
        <button className={view === 'camera' ? 'selected' : ''} aria-label="Camera frame" aria-pressed={view === 'camera'} onClick={() => setView('camera')}><Icon name="camera" size={15}/>Camera</button>
        <button className={view === 'spatial' ? 'selected' : ''} aria-label="Spatial map" aria-pressed={view === 'spatial'} onClick={() => setView('spatial')}><Icon name="route" size={15}/>2D Map</button>
        <button className={view === 'city' ? 'selected' : ''} aria-label="Spatial 3D" aria-pressed={view === 'city'} onClick={() => setView('city')}><Icon name="home" size={15}/>3D City</button>
      </div>
      {view === 'camera' && liveAvailable && <div className="scene-view-toggle scene-camera-source" role="group" aria-label="Camera source"><button className={usingLive ? 'selected' : ''} aria-pressed={usingLive} onClick={() => setCameraSource('live')}>Live</button><button className={!usingLive ? 'selected' : ''} aria-pressed={!usingLive} onClick={() => setCameraSource('recorded')}>Recorded</button></div>}
      {view === 'camera' && cameraScene?.frame && <button className="scene-focus-toggle" disabled={!canBoardFocus} aria-pressed={hasBoardMask} onClick={() => setFocused(value => !value)} title={hasBoardMask ? 'Display mask only. Original camera pixels and the fixed mapping stay unchanged.' : 'Full frame. Board focus requires a valid locked test mapping.'}>{hasBoardMask ? 'Board focus' : 'Full frame'}<Icon name="eye" size={14}/></button>}
      {view !== 'city' && <button className="scene-tools-toggle" aria-label="Image tools" aria-haspopup="dialog" aria-expanded={expanded} onClick={() => openTools('image')}><Icon name="settings" size={16}/><span>Image tools</span></button>}
    </div>
    {view !== 'city' && <RouteLegend display={routeDisplay}/>}
    {view !== 'city' && (error || mismatchedRoute) && <div className="scene-error" role="alert"><Icon name="shield" size={16}/><span>{error || 'Map geometry changed. Create a new plan to display its route.'}</span><button onClick={() => { setError(''); void refresh(true); void refreshMap(); }} aria-label="Refresh scene state"><Icon name="refresh" size={15}/></button></div>}
    <div className="scene-visual">
      {view === 'city' ? <Suspense fallback={<div className="no-recorded-frame" role="status"><h2>Opening Spatial 3D…</h2></div>}><CityViewBoundary onReturn={() => setView('camera')}><CityModelView/></CityViewBoundary></Suspense> : view === 'spatial' ? map ? <SpatialMap map={map} route={route} display={routeDisplay}/> : <div className="no-recorded-frame"><Icon name="route" size={32}/><h2>Loading temporary geometry…</h2></div> : cameraScene?.frame ? <CameraFrame scene={cameraScene} route={route} map={map} focused={focused} display={routeDisplay} live={usingLive} fresh={liveFresh}/> : <div className="no-recorded-frame"><Icon name="camera" size={32}/><h2>{usingLive ? 'Connecting to the camera…' : 'Bring your workspace into view.'}</h2><p>{usingLive ? live.status?.last_error || 'Waiting for the first decoded live image. Recorded images remain available.' : 'Load a recorded image for marker detection and scene inspection.'}</p><button disabled={readOnly || Boolean(busy)} onClick={() => usingLive ? setCameraSource('recorded') : openTools('image')}><Icon name={usingLive ? 'camera' : 'upload'} size={16}/>{usingLive ? 'View recorded image' : 'Choose a recorded frame'}</button><button className="spatial-preview-link" onClick={() => setView('spatial')}>Explore the illustrative spatial view<Icon name="arrow" size={15}/></button><small>{usingLive ? 'Live preview has no motion authority.' : 'No live camera is connected.'}</small></div>}
    </div>
    <div className={`scene-source-plate ${usingLive && view === 'camera' ? liveFresh ? 'live-source' : 'stale-source' : ''}`}>
      <span className="scene-source-dot"/>
      <div><strong>{view === 'city' ? '3D city model' : view === 'spatial' ? 'Illustrative spatial view' : usingLive ? liveScene?.frame ? `Live camera${liveFresh ? '' : ' · STALE'} · ${Number.isFinite(liveAge) ? `${(liveAge / 1000).toFixed(1)} s` : 'age unknown'}` : 'Live camera · connecting' : scene?.frame ? `${scene.frame.source === 'recorded' ? 'Recorded' : 'Uploaded'} camera frame` : 'Camera not connected'}</strong><span>{view === 'city' ? 'Display only · routes use the 2D map' : view === 'spatial' ? 'Temporary geometry · no physical scan' : usingLive ? `${hasBoardMask ? 'Board focus' : 'Full frame'} · ${liveRegistrationLabel}` : hasBoardMask ? 'Board focus · background masked' : scene?.frame ? `${scene.frame.width} × ${scene.frame.height} · full frame` : 'Load a recorded image to inspect the scene'}</span></div>
      {view === 'city' ? <span className="live-motion-note"><Icon name="eye" size={14}/>Model only</span> : usingLive && view === 'camera' && (resumeAvailable || ['candidate', 'view_changed'].includes(liveScene?.registration.status ?? ''))
        ? <button className="live-lock-button" disabled={!(resumeAvailable ? canResumeLive : canLockLive)} onClick={() => void lockLiveView(resumeAvailable)} title={resumeAvailable ? 'Explicitly reuse the saved fixed display mapping after server validation. No refit.' : active ? 'Lock a live view during mission preparation.' : 'Explicitly lock the current live camera-to-board test mapping.'}><Icon name="check" size={14}/>{lockingLive ? 'Checking…' : resumeAvailable ? 'Resume fixed view' : 'Lock live view'}</button>
        : usingLive && view === 'camera' ? <span className="live-motion-note" title="Live preview and its test mapping have no robot motion authority."><Icon name="shield" size={14}/>Preview only</span>
          : <button onClick={() => openTools('registration')} aria-label="View recorded scene registration details" title="Recorded image registration"><Icon name="shield" size={15}/></button>}
    </div>
    <dialog ref={toolsDialog} className="scene-tools-dialog" aria-label="Recorded image tools" onClose={() => setExpanded(false)} onCancel={() => setExpanded(false)} onClick={event => { const bounds = event.currentTarget.getBoundingClientRect(); if (event.target === event.currentTarget && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) setExpanded(false); }}>
      <input ref={fileInput} type="file" accept="image/jpeg,image/png" className="hidden-file-input" aria-label="Recorded JPEG or PNG frame" disabled={readOnly || Boolean(busy)} onChange={event => void upload(event.target.files?.[0])}/>
      <header className="scene-dialog-heading"><div><span>SCENE EVIDENCE</span><h2>Recorded image tools</h2></div><button onClick={() => setExpanded(false)} aria-label="Close image tools"><Icon name="close" size={19}/></button></header>
      <nav className="scene-dialog-tabs" role="tablist" aria-label="Image tool sections">{(['image', 'registration', 'muse', 'result', 'evidence'] as const).map(tab => <button key={tab} role="tab" aria-selected={toolTab === tab} className={toolTab === tab ? 'selected' : ''} onClick={() => setToolTab(tab)}>{tab === 'muse' ? 'MUSE' : tab[0].toUpperCase() + tab.slice(1)}</button>)}</nav>
      <div className="scene-dialog-body" role="tabpanel" aria-label={`${toolTab} tools`}>
        {toolTab === 'image' && <div className="scene-image-page">
          <div className="scene-image-preview">{scene?.frame ? <img src={scene.frame.image_url} alt="Current immutable recorded frame"/> : <Icon name="camera" size={32}/>}<span>{scene?.frame ? `${scene.frame.width} × ${scene.frame.height} · ${scene.frame.source}` : 'No image loaded'}</span></div>
          <div className="scene-image-fields"><label className="scene-field">Capture time <span>Optional · local time</span><input type="datetime-local" value={capturedAt} disabled={readOnly || Boolean(busy)} onChange={event => setCapturedAt(event.target.value)}/></label><button className="scene-dialog-primary" disabled={readOnly || Boolean(busy)} onClick={() => fileInput.current?.click()}><Icon name="upload" size={16}/>{busy === 'upload' ? 'Uploading…' : 'Upload recorded frame'}</button><p>JPEG or PNG · up to 8 MiB / 12 megapixels. An omitted capture time stays unknown.</p></div>
          <div className="scene-dialog-note"><Icon name="clock" size={15}/>{scene?.frame ? captureLabel(scene.frame) : 'A received image never establishes live-camera freshness.'}</div>
        </div>}
        {toolTab === 'registration' && <div className="scene-registration-page"><span className={`registration-badge ${status}`}><span/>{registrationLabels[status]}</span><dl className="scene-facts"><div><dt>Detected markers</dt><dd>{markerCount} / 4</dd></div><div><dt>Reprojection residual</dt><dd>{scene?.registration.residual_px != null ? `${scene.registration.residual_px.toFixed(2)} px` : 'Not available'}</dd></div><div><dt>Map</dt><dd>{map ? `${map.title} · ${map.version}` : 'Loading…'}</dd></div><div><dt>Authority</dt><dd>Test overlay only</dd></div></dl><TextPages text={scene?.registration.message || 'Load a recorded frame with all four markers to prepare a test overlay.'} pageSize={250}/><button className="scene-dialog-primary" disabled={!canLock} onClick={() => void sceneCommand('registration')} title={active ? 'Lock the test view during mission preparation.' : 'Explicitly lock this temporary camera-to-board test overlay.'}><Icon name="check" size={16}/>{busy === 'registration' ? 'Locking…' : status === 'view_changed' ? 'Lock new test view' : 'Lock test view'}</button></div>}
        {toolTab === 'muse' && <div className="scene-muse-page"><ExpectedPrompt value={expected} disabled={readOnly || Boolean(busy)} onChange={setExpected}/><div className="scene-inspect-actions"><button className="scene-dialog-primary" disabled={readOnly || Boolean(busy) || !scene?.frame || !scene.capabilities.muse_configured || !expected.trim()} onClick={() => void sceneCommand('inspection').then(accepted => { if (accepted) setToolTab('result'); })}><Icon name="spark" size={16}/>{busy === 'inspection' ? 'MUSE is inspecting…' : 'Inspect image with MUSE'}</button><span>{scene?.capabilities.muse_configured ? 'Actual Meta API · explicit request' : 'Meta image inspection not configured'}</span></div></div>}
        {toolTab === 'result' && <section className="scene-result-page" aria-label="MUSE scene inspection result">{currentInspection ? <><div className="scene-result-heading"><Icon name="spark" size={18}/><h3>Scene inspection</h3><span className={`scene-verdict ${currentInspection.verdict.toLowerCase()}`}>{currentInspection.verdict}</span></div><TextPages text={currentInspection.summary}/><div className="scene-result-metrics"><div><span>Places</span><strong>{currentInspection.visible_places.length} visible</strong></div><div><span>Car</span><strong>{currentInspection.car_visible ? 'Model reports visible' : 'Not confirmed'}</strong></div><div><span>Signal</span><strong>{currentInspection.signal}</strong></div></div><button className="scene-evidence-link" onClick={() => setToolTab('evidence')}>Inspection evidence<Icon name="arrow" size={15}/></button></> : <div className="scene-empty-result"><Icon name="eye" size={28}/><h3>No inspection for this frame</h3><p>Send an explicit MUSE request from the MUSE tab.</p></div>}</section>}
        {toolTab === 'evidence' && <div className="scene-evidence-page">{currentInspection ? <><h3>Image evidence</h3><TextPages pageSize={320} text={`Visible places: ${currentInspection.visible_places.join(', ') || 'None confirmed'}\nCar: ${currentInspection.car_visible ? 'Visible according to the model' : 'Not confirmed visible'}\nImage signal: ${currentInspection.signal} · model report only\nExpected: ${currentInspection.expected}\nLimitations: ${currentInspection.limitations.join(' · ') || 'None reported'}\nModel: ${currentInspection.model}\nInspected: ${new Date(currentInspection.created_at).toLocaleString('en-US')}\nFrame: ${currentInspection.frame_id}\nInspection: ${currentInspection.id}`}/></> : <TextPages text="No scene inspection evidence is attached to the current recorded frame."/>}</div>}
      </div>
      {error && <div className="scene-dialog-error" role="alert"><TextPages text={error} pageSize={110}/></div>}
      <footer className="scene-dialog-footer"><Icon name="shield" size={14}/><span>Scene inspection cannot approve an action or advance the mission.</span></footer>
    </dialog>
  </div>;
}
