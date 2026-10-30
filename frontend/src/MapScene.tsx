import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState } from 'react';
import type { MapRoute, SceneSnapshot, TemporaryMap } from '../../contracts/scene';
import type { LiveCameraSnapshot } from '../../contracts/live-camera';
import type { WorkspaceSnapshot } from '../../contracts/workspace';
import { Icon } from './Icons';
import { projectPoint, type Point } from './projection';
import { createRouteDisplay, projectRouteDisplay, type RouteDisplay } from './routeProgress';
import { RouteOverlay } from './RouteOverlay';
import { nodeLabel } from './mapMetadata';
import { CityViewBoundary } from './CityViewBoundary';
import { recordedDisplay } from './boardFocus';
import { createLivePollGate, liveDisplaySnapshot, liveFrameAge, liveFrameFresh, liveOverlayAllowed } from './liveCamera';
import { liveCameraPresentation } from './cameraPresentation';
import { decodeLiveFrame, fetchLiveSnapshot, previewRetryDelay } from './liveCameraTransport';
import { CameraNavigation } from './CameraNavigation';
import type { PhysicalDisplaySnapshot } from './physicalDisplay';
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

function polygon(points: Point[]) { return points.map(point => point.join(',')).join(' '); }

function CameraFrame({ scene, route, map, focused, display, names, live = false, fresh = true, resetToken = 0 }: { scene: SceneSnapshot | LiveCameraSnapshot; route: MapRoute | null; map: TemporaryMap | null; focused: boolean; display: RouteDisplay | null; names?: { start: string; goal: string }; live?: boolean; fresh?: boolean; resetToken?: number }) {
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
  const livePresentation = live ? liveCameraPresentation(scene as LiveCameraSnapshot, map, fresh) : null;
  const { viewport, quad } = recordedDisplay(scene, map, focused);
  // Live frame IDs advance continuously; only a changed view identity resets navigation.
  const navigationIdentity = [live ? 'live' : 'recorded', 'epoch' in scene ? scene.epoch : frame.id,
    frame.width, frame.height, scene.map_id, scene.map_version, scene.map_hash, scene.registration.id, focused].join('|');
  return <div className="recorded-frame-wrap">
    <CameraNavigation key={navigationIdentity} resetToken={resetToken}>
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
      <RouteOverlay display={projectedDisplay} scale={scale} boundary={routeBoundary} names={names}/>
      </g>
    </svg>
    </CameraNavigation>
    {livePresentation ? livePresentation.alerts.map(alert => <div key={alert.kind} className={`overlay-inhibition${alert.kind === 'view_changed' ? '' : ' live-warning'}`}><Icon name={alert.kind === 'view_changed' ? 'shield' : 'clock'} size={17}/>{alert.message}</div>)
      : scene.registration.status === 'view_changed' && <div className="overlay-inhibition"><Icon name="shield" size={17}/>View changed. The previous overlay is hidden.</div>}
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
    let activeRequest: AbortController | null = null;
    let wakeRequested = false;
    let failures = 0;
    const tick = window.setInterval(() => setClock(performance.now()), 250);
    const poll = async () => {
      if (cancelled || activeRequest) return;
      const controller = new AbortController();
      activeRequest = controller;
      let delay = 125;
      const generation = pollGate.current.begin();
      const receivedAt = performance.now();
      try {
        const snapshot = await fetchLiveSnapshot(controller.signal);
        if (cancelled || controller.signal.aborted || !pollGate.current.accept(generation, snapshot)) return;
        setStatus(snapshot);
        delay = snapshot.enabled ? 125 : 2000;
        if (snapshot.frame) {
          if (!liveFrameFresh(snapshot, receivedAt, performance.now())) throw new Error('Camera frame is stale.');
          const currentView = displayed.current;
          if (currentView?.snapshot.frame?.id !== snapshot.frame.id || currentView.snapshot.epoch !== snapshot.epoch) {
            await decodeLiveFrame(snapshot.frame, controller.signal);
          }
          if (cancelled || controller.signal.aborted || !pollGate.current.accept(generation, snapshot)) return;
          if (!liveFrameFresh(snapshot, receivedAt, performance.now())) throw new Error('Decoded camera frame is stale.');
          const next = { snapshot, receivedAt };
          displayed.current = next;
          setDecoded(next);
        }
        failures = 0;
        // Target one poll per 125 ms, including transport and decode time.
        if (snapshot.enabled) delay = Math.max(0, 125 - (performance.now() - receivedAt));
      } catch {
        // Keep the previous decoded image; its monotonic age will mark it stale.
        delay = previewRetryDelay(++failures);
      } finally {
        activeRequest = null;
        if (wakeRequested) { delay = 0; wakeRequested = false; }
        if (!cancelled) timer = window.setTimeout(() => void poll(), delay);
      }
    };
    const wake = () => {
      if (document.visibilityState !== 'visible' || cancelled) return;
      // Safari may suspend a pending fetch/decode while the tablet sleeps.
      setClock(performance.now());
      window.clearTimeout(timer);
      if (activeRequest) { wakeRequested = true; activeRequest.abort(); }
      else void poll();
    };
    document.addEventListener('visibilitychange', wake);
    void poll();
    return () => {
      cancelled = true; activeRequest?.abort(); window.clearTimeout(timer); window.clearInterval(tick);
      document.removeEventListener('visibilitychange', wake);
    };
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

export function MapScene({ workspace, physicalLabel, physicalDisplay, readOnly = false, onSnapshot, onPreviewSource, onMapSnapshot, onLiveCamera, sceneInsetRight = 0, openToolsRequest = 0, presentation = 'panel' }: {
  workspace: WorkspaceSnapshot | null; physicalLabel?: string; physicalDisplay?: PhysicalDisplaySnapshot | null; readOnly?: boolean; onSnapshot: (snapshot: SceneSnapshot) => void; onPreviewSource?: (label: string) => void; onMapSnapshot?: (map: TemporaryMap) => void;
  onLiveCamera?: (connected: boolean) => void; sceneInsetRight?: number; openToolsRequest?: number; presentation?: 'panel' | 'stage';
}) {
  const [map, setMap] = useState<TemporaryMap | null>(null);
  const [scene, setScene] = useState<SceneSnapshot | null>(null);
  const [view, setView] = useState<'camera' | 'spatial'>('camera');
  // Centre empty states in the area left of the open mission panel, matching the 3D view offset.
  const emptyInset = sceneInsetRight > 0 ? { paddingRight: 24 + sceneInsetRight } : undefined;
  const [cameraSource, setCameraSource] = useState<'auto' | 'live' | 'recorded'>('auto');
  const [lockingLive, setLockingLive] = useState(false);
  const live = useLiveCamera();
  const [expanded, setExpanded] = useState(false);
  const [toolTab, setToolTab] = useState<'image' | 'registration' | 'muse' | 'result' | 'evidence'>('image');
  const [focused, setFocused] = useState(true);
  const [cameraResetToken, setCameraResetToken] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<'upload' | 'registration' | 'inspection' | null>(null);
  const [capturedAt, setCapturedAt] = useState('');
  const [expected, setExpected] = useState('Inspect the selected temporary map. Report visible places, car visibility and signal color. Do not infer physical motion.');
  const fileInput = useRef<HTMLInputElement>(null);
  const toolsDialog = useRef<HTMLDialogElement>(null);
  const lastToolsRequest = useRef(0);
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
  useEffect(() => {
    if (openToolsRequest <= lastToolsRequest.current) return;
    lastToolsRequest.current = openToolsRequest;
    // Consume a blocked request rather than reopening an old modal after the mission ends.
    if (readOnly || busy) return;
    setToolTab('image'); setExpanded(true);
  }, [openToolsRequest, readOnly, busy]);
  useEffect(() => {
    const dialog = toolsDialog.current;
    if (!dialog) return;
    // A native modal makes every external control inert, including the robot Stop button.
    if (readOnly) {
      if (dialog.open) dialog.close();
      if (expanded) setExpanded(false);
      return;
    }
    if (expanded && !dialog.open) dialog.showModal();
    if (!expanded && dialog.open) dialog.close();
  }, [expanded, readOnly]);

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
  // Simulator step progress never colors a physical robot route.
  const routeDisplay = createRouteDisplay(route, map, physicalLabel ? null : workspace);
  const boundPhysicalDisplay = physicalDisplay && workspace?.plan && physicalDisplay.plan_id === workspace.plan.id
    && physicalDisplay.plan_revision === workspace.plan.revision && physicalDisplay.workspace_session_id === workspace.session_id
    && physicalDisplay.map_hash === route?.map_hash ? physicalDisplay : null;
  const routeNames = route ? { start: nodeLabel(map, route.start), goal: nodeLabel(map, route.destination) } : undefined;
  const status = scene?.registration.status ?? 'unregistered';
  const markerCount = scene?.detection.marker_ids.filter(id => map?.markers.some(marker => marker.id === id)).length ?? 0;
  const canLock = ['candidate', 'view_changed'].includes(status) && markerCount === 4 && !active && !readOnly && !busy;
  const inspection = scene?.inspection;
  const currentInspection = inspection?.frame_id === scene?.frame?.id ? inspection : null;

  const openTools = (tab: typeof toolTab) => { if (readOnly || busy) return; setToolTab(tab); setExpanded(true); };
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
  const livePresentation = liveCameraPresentation(changedLiveScene, map, liveFresh);
  const liveStatusLabel = !usingLive || liveFresh ? 'Live' : liveScene?.frame ? 'Reconnecting' : live.status?.state === 'unavailable' ? 'Offline' : 'Connecting';
  const liveStatusDetail = liveScene?.frame
    ? `${liveFresh ? 'Live camera' : 'Camera reconnecting'} · ${Number.isFinite(liveAge) ? `${(liveAge / 1000).toFixed(1)} s` : 'age unknown'} · ${hasBoardMask ? 'Board focus' : 'Full frame'} · ${livePresentation.label}`
    : 'Waiting for a fresh camera image';
  const previewSourceLabel = view === 'spatial' ? 'Spatial city preview' : usingLive
    ? liveScene?.frame ? liveFresh ? 'Live camera' : 'Live camera · stale' : 'Live camera · connecting'
    : scene?.frame ? scene.frame.source === 'recorded' ? 'Recorded image' : 'Uploaded image' : 'No image';
  useEffect(() => { onPreviewSource?.(previewSourceLabel); }, [onPreviewSource, previewSourceLabel]);
  useEffect(() => { onLiveCamera?.(Boolean(liveFresh && live.status?.state === 'live')); }, [onLiveCamera, liveFresh, live.status?.state]);

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
        <button className={view === 'spatial' ? 'selected' : ''} aria-label="Spatial map" aria-pressed={view === 'spatial'} onClick={() => setView('spatial')}><Icon name="route" size={15}/>Spatial</button>
      </div>
      {view === 'camera' && liveAvailable && <div className="scene-view-toggle scene-camera-source" role="group" aria-label="Camera source"><button className={`${usingLive ? 'selected ' : ''}${liveFresh ? 'live-source' : 'stale-source'}`} aria-label={`Live camera${usingLive ? ` · ${liveFresh ? 'connected' : liveStatusLabel.toLowerCase()}` : ''}`} aria-pressed={usingLive} title={liveStatusDetail} onClick={() => setCameraSource('live')}><span className="scene-live-dot" aria-hidden="true"/>{liveStatusLabel}</button><button className={!usingLive ? 'selected' : ''} aria-pressed={!usingLive} title={scene?.frame ? `${scene.frame.source === 'recorded' ? 'Recorded' : 'Uploaded'} image · ${scene.frame.width} × ${scene.frame.height}` : 'Recorded image'} onClick={() => setCameraSource('recorded')}>Recorded</button></div>}
      {view === 'camera' && !liveAvailable && scene?.frame && <span className="scene-recorded-source">{scene.frame.source === 'recorded' ? 'Recorded' : 'Uploaded'} image</span>}
      {view === 'camera' && cameraScene?.frame && <button className="scene-focus-toggle" disabled={!canBoardFocus} aria-pressed={hasBoardMask} onClick={() => setFocused(value => !value)}>{hasBoardMask ? 'Board focus' : 'Full frame'}<Icon name="eye" size={14}/></button>}
      {/* With no image, the empty state's `Choose a recorded frame` is the one entry point to the same tools. */}
      {view === 'camera' && cameraScene?.frame && <button className="scene-tools-toggle" disabled={readOnly || Boolean(busy)} aria-label="Image tools" aria-haspopup="dialog" aria-expanded={expanded} onClick={() => openTools('image')}><Icon name="settings" size={16}/><span>Image tools</span></button>}
      {view === 'camera' && cameraScene?.frame && <button className="scene-fit-toggle" aria-label="Fit camera view" title="Fit the original camera view" onClick={() => setCameraResetToken(value => value + 1)}><Icon name="refresh" size={16}/></button>}
      {view === 'camera' && usingLive && (resumeAvailable || ['candidate', 'view_changed'].includes(liveScene?.registration.status ?? '')) && <button className="scene-lock-view" disabled={!(resumeAvailable ? canResumeLive : canLockLive)} onClick={() => void lockLiveView(resumeAvailable)}><Icon name="check" size={14}/>{lockingLive ? 'Checking…' : resumeAvailable ? 'Resume fixed view' : 'Lock live view'}</button>}
    </div>
    {(error || mismatchedRoute) && <div className="scene-error" role="alert"><Icon name="shield" size={16}/><span>{error || 'Map geometry changed. Create a new plan to display its route.'}</span><button onClick={() => { setError(''); void refresh(true); void refreshMap(); }} aria-label="Refresh scene state"><Icon name="refresh" size={15}/></button></div>}
    <div className="scene-visual">
      {view === 'spatial' ? <Suspense fallback={<div className="no-recorded-frame" role="status" style={emptyInset}><h2>Opening Spatial…</h2></div>}><CityViewBoundary onReturn={() => setView('camera')}><CityModelView map={map} display={routeDisplay} names={routeNames} insetRight={sceneInsetRight} physicalDisplay={boundPhysicalDisplay} physicalMode={Boolean(physicalLabel)}/></CityViewBoundary></Suspense> : cameraScene?.frame ? <CameraFrame scene={cameraScene} route={route} map={map} focused={focused} display={routeDisplay} names={routeNames} live={usingLive} fresh={liveFresh} resetToken={cameraResetToken}/> : <div className="no-recorded-frame" style={emptyInset}><Icon name="camera" size={32}/><h2>{usingLive ? 'Connecting to the camera…' : 'Bring your workspace into view.'}</h2><p>{usingLive ? live.status?.last_error || 'Waiting for the first decoded live image. Recorded images remain available.' : 'Load a recorded image for marker detection and scene inspection.'}</p><button disabled={readOnly || Boolean(busy)} onClick={() => usingLive ? setCameraSource('recorded') : openTools('image')}><Icon name={usingLive ? 'camera' : 'upload'} size={16}/>{usingLive ? 'View recorded image' : 'Choose a recorded frame'}</button><small>{usingLive ? 'Live preview has no motion authority.' : 'No live camera is connected.'}</small></div>}
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
        {toolTab === 'registration' && <div className="scene-registration-page"><span className={`registration-badge ${status}`}><span/>{registrationLabels[status]}</span><dl className="scene-facts"><div><dt>Detected markers</dt><dd>{markerCount} / 4</dd></div><div><dt>Reprojection residual</dt><dd>{scene?.registration.residual_px != null ? `${scene.registration.residual_px.toFixed(2)} px` : 'Not available'}</dd></div><div><dt>Map</dt><dd>{map ? `${map.title} · ${map.version}` : 'Loading…'}</dd></div><div><dt>Authority</dt><dd>Test overlay only</dd></div></dl><TextPages text={scene?.registration.message || 'Load a recorded frame with all four markers to prepare a test overlay.'} pageSize={250}/><button className="scene-dialog-primary" disabled={!canLock} onClick={() => void sceneCommand('registration')}><Icon name="check" size={16}/>{busy === 'registration' ? 'Locking…' : status === 'view_changed' ? 'Lock new test view' : 'Lock test view'}</button></div>}
        {toolTab === 'muse' && <div className="scene-muse-page"><ExpectedPrompt value={expected} disabled={readOnly || Boolean(busy)} onChange={setExpected}/><div className="scene-inspect-actions"><button className="scene-dialog-primary" disabled={readOnly || Boolean(busy) || !scene?.frame || !scene.capabilities.muse_configured || !expected.trim()} onClick={() => void sceneCommand('inspection').then(accepted => { if (accepted) setToolTab('result'); })}><Icon name="spark" size={16}/>{busy === 'inspection' ? 'MUSE is inspecting…' : 'Inspect image with MUSE'}</button><span>{scene?.capabilities.muse_configured ? 'Actual Meta API · explicit request' : 'Meta image inspection not configured'}</span></div></div>}
        {toolTab === 'result' && <section className="scene-result-page" aria-label="MUSE scene inspection result">{currentInspection ? <><div className="scene-result-heading"><Icon name="spark" size={18}/><h3>Scene inspection</h3><span className={`scene-verdict ${currentInspection.verdict.toLowerCase()}`}>{currentInspection.verdict}</span></div><TextPages text={currentInspection.summary}/><div className="scene-result-metrics"><div><span>Places</span><strong>{currentInspection.visible_places.length} visible</strong></div><div><span>Car</span><strong>{currentInspection.car_visible ? 'Model reports visible' : 'Not confirmed'}</strong></div><div><span>Signal</span><strong>{currentInspection.signal}</strong></div></div><button className="scene-evidence-link" onClick={() => setToolTab('evidence')}>Inspection evidence<Icon name="arrow" size={15}/></button></> : <div className="scene-empty-result"><Icon name="eye" size={28}/><h3>No inspection for this frame</h3><p>Send an explicit MUSE request from the MUSE tab.</p></div>}</section>}
        {toolTab === 'evidence' && <div className="scene-evidence-page">{currentInspection ? <><h3>Image evidence</h3><TextPages pageSize={320} text={`Visible places: ${currentInspection.visible_places.join(', ') || 'None confirmed'}\nCar: ${currentInspection.car_visible ? 'Visible according to the model' : 'Not confirmed visible'}\nImage signal: ${currentInspection.signal} · model report only\nExpected: ${currentInspection.expected}\nLimitations: ${currentInspection.limitations.join(' · ') || 'None reported'}\nModel: ${currentInspection.model}\nInspected: ${new Date(currentInspection.created_at).toLocaleString('en-US')}\nFrame: ${currentInspection.frame_id}\nInspection: ${currentInspection.id}`}/></> : <TextPages text="No scene inspection evidence is attached to the current recorded frame."/>}</div>}
      </div>
      {error && <div className="scene-dialog-error" role="alert"><TextPages text={error} pageSize={110}/></div>}
      <footer className="scene-dialog-footer"><Icon name="shield" size={14}/><span>Scene inspection cannot approve an action or advance the mission.</span></footer>
    </dialog>
  </div>;
}
