import { useCallback, useEffect, useId, useRef, useState } from 'react';
import type { MapRoute, SceneSnapshot, TemporaryMap } from '../../contracts/scene';
import type { WorkspaceSnapshot } from '../../contracts/workspace';
import { Icon } from './Icons';
import { directionArrows, projectPoint, type Point } from './projection';
import './map-scene.css';

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

function RouteStroke({ points, id, scale = 1, candidate = false }: { points: Point[]; id: string; scale?: number; candidate?: boolean }) {
  if (points.length < 2) return null;
  const color = candidate ? '#ffbf66' : '#13d5ff';
  return <g className="map-route-layer">
    <defs>
      <marker id={id} viewBox="0 0 12 12" markerWidth={10 * scale} markerHeight={10 * scale}
        refX="9" refY="6" orient="auto" markerUnits="userSpaceOnUse">
        <path d="m3 2 6 4-6 4" fill="none" stroke={candidate ? '#ffe5ba' : '#e3fbff'} strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"/>
      </marker>
    </defs>
    <polyline points={points.map(point => point.join(',')).join(' ')} fill="none" stroke={color}
      strokeWidth={10 * scale} opacity=".16" strokeLinecap="round" strokeLinejoin="round"/>
    <polyline points={points.map(point => point.join(',')).join(' ')} fill="none" stroke={color}
      strokeWidth={3.2 * scale} strokeLinecap="round" strokeLinejoin="round"/>
    {directionArrows(points).map((arrow, index) => <path key={index}
      d={`M${arrow.start.join(',')} L${arrow.end.join(',')}`} fill="none" stroke={color}
      strokeWidth={2.2 * scale} markerEnd={`url(#${id})`}/>) }
    <circle cx={points[0][0]} cy={points[0][1]} r={4.5 * scale} fill="#092b40" stroke={color} strokeWidth={2 * scale}/>
    <circle cx={points.at(-1)![0]} cy={points.at(-1)![1]} r={6.5 * scale} fill="#075443" stroke="#64ffe0" strokeWidth={2 * scale}/>
    <circle cx={points.at(-1)![0]} cy={points.at(-1)![1]} r={2 * scale} fill="#b9fff0"/>
  </g>;
}

function SpatialMap({ map, route }: { map: TemporaryMap; route: MapRoute | null }) {
  const id = useId().replace(/:/g, '');
  const byId = new Map(map.nodes.map(node => [node.id, node]));
  const validRoute = route?.map_hash === map.geometry_hash ? route : null;
  return <div className="spatial-map-wrap">
    <svg className="spatial-map" viewBox={`-18 -29 ${map.board.width_mm + 36} ${map.board.height_mm + 58}`}
      role="img" aria-label={`Temporary ${map.title} road geometry${validRoute ? ` with route from ${validRoute.start} to ${validRoute.destination}` : ''}`}>
      <defs>
        <linearGradient id={`${id}-board`} x2="1" y2="1"><stop stopColor="#122b3d"/><stop offset="1" stopColor="#0a1e2c"/></linearGradient>
      </defs>
      <rect x="0" y="0" width={map.board.width_mm} height={map.board.height_mm} rx="5" fill={`url(#${id}-board)`} stroke="#265371" strokeWidth=".8"/>
      {map.edges.map(edge => {
        const from = byId.get(edge.from); const to = byId.get(edge.to);
        return from && to ? <g key={`${edge.from}-${edge.to}`}>
          <line x1={from.x_mm} y1={from.y_mm} x2={to.x_mm} y2={to.y_mm} stroke="#304a5a" strokeWidth={map.board.road_width_mm} strokeLinecap="square"/>
          <line x1={from.x_mm} y1={from.y_mm} x2={to.x_mm} y2={to.y_mm} stroke="#87a3b3" strokeWidth=".65" strokeDasharray="3 3" opacity=".4"/>
        </g> : null;
      })}
      {map.building_panels.map(panel => {
        const [x0, y0, x1, y1] = panel.bounds_mm;
        const target = validRoute?.destination === panel.id;
        return <g key={panel.id}>
          <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} rx="3" fill={target ? '#0d3538' : '#112d40'} stroke={target ? '#187d78' : '#214c64'} strokeWidth=".8"/>
          <path d={`M${(x0 + x1) / 2 - 9} ${y0 + 19} l9 -6 9 6 v10 h-18 Z`} fill="none" stroke={target ? '#50cebd' : '#4d819d'} strokeWidth="1.2"/>
          <path d={`M${(x0 + x1) / 2 - 3} ${y0 + 29} v-7 h6 v7`} fill="none" stroke={target ? '#50cebd' : '#4d819d'} strokeWidth="1"/>
          <text x={(x0 + x1) / 2} y={y1 - 10} textAnchor="middle" fill={target ? '#9aeee1' : '#83b3cd'} fontSize="6.7" letterSpacing=".8">{panel.id}</text>
        </g>;
      })}
      {map.nodes.filter(node => node.kind === 'junction').map(node => <g key={node.id}>
        <rect x={node.x_mm - 8} y={node.y_mm - 8} width="16" height="16" rx="4" fill="#233e50" stroke="#45677a" strokeWidth=".7"/>
        <text x={node.x_mm} y={node.y_mm + 2.3} fontSize="6.5" fill="#a8c5d6" textAnchor="middle">{node.id}</text>
      </g>)}
      <RouteStroke points={validRoute?.points_mm ?? []} id={`${id}-spatial-arrow`}/>
      {map.nodes.filter(node => node.kind === 'destination').map(node => <g key={node.id}>
        <circle cx={node.x_mm} cy={node.y_mm} r="3.2" fill={node.id === validRoute?.destination ? '#43f2d0' : '#95b2c6'} stroke="#0c2738" strokeWidth="1.3"/>
        <text x={node.x_mm} y={node.y_mm + 13} fill={node.id === validRoute?.destination ? '#85f3df' : '#a8c7d9'} textAnchor="middle" fontSize="5.5" letterSpacing=".2">{node.id === map.start ? 'START' : node.id === validRoute?.destination ? 'GOAL' : 'DESTINATION'}</text>
      </g>)}
      {map.markers.map(marker => <g key={marker.id}>
        <rect x={marker.center_mm[0] - 4} y={marker.center_mm[1] - 4} width="8" height="8" rx=".5" fill="#0c1b27" stroke="#4b7186" strokeWidth=".7"/>
        <text x={marker.center_mm[0]} y={marker.center_mm[1] + 1.7} textAnchor="middle" fill="#9ec2d6" fontSize="4.5">{marker.id}</text>
      </g>)}
      <text x="0" y={map.board.height_mm + 23} fill="#557f9b" fontSize="5.5">DRAWING {map.board.width_mm} × {map.board.height_mm} mm · NOT ROBOT COORDINATES</text>
    </svg>
    <div className="map-view-caption"><Icon name="route" size={14}/>Self-authored schematic · temporary print geometry</div>
  </div>;
}

function RecordedFrame({ scene, route, map }: { scene: SceneSnapshot; route: MapRoute | null; map: TemporaryMap | null }) {
  const id = useId().replace(/:/g, '');
  const frame = scene.frame!;
  const matrix = scene.registration.homography;
  const matchesMap = Boolean(map && route && route.map_hash === map.geometry_hash && scene.map_hash === map.geometry_hash);
  const overlayAllowed = matchesMap && usableRegistration.has(scene.registration.status) && Boolean(matrix);
  const projected = overlayAllowed ? route!.points_mm.map(point => projectPoint(point, matrix!)) : [];
  const points = projected.every((point): point is Point => point !== null) ? projected : [];
  const scale = frame.width / 530;
  const candidate = scene.registration.status === 'candidate';
  return <div className="recorded-frame-wrap">
    <svg className="recorded-frame" viewBox={`0 0 ${frame.width} ${frame.height}`}
      style={{ aspectRatio: `${frame.width} / ${frame.height}` }} role="img"
      aria-label={`Recorded workspace image${points.length ? ` with ${candidate ? 'candidate' : 'test-only'} route overlay` : ''}`}>
      <image href={frame.image_url} x="0" y="0" width={frame.width} height={frame.height} preserveAspectRatio="xMidYMid meet"/>
      {scene.detection.markers.map(marker => <g key={marker.id}>
        <polygon points={marker.corners.map(point => point.join(',')).join(' ')} fill="none" stroke="#f3cb79" strokeWidth={1.2 * scale}/>
        {marker.corners[0] && <text x={marker.corners[0][0]} y={marker.corners[0][1] - 4 * scale}
          fill="#ffe4a5" stroke="#102333" strokeWidth={.35 * scale} paintOrder="stroke" fontSize={7 * scale}>{marker.id}</text>}
      </g>)}
      <RouteStroke points={points} id={`${id}-photo-arrow`} scale={scale} candidate={candidate}/>
    </svg>
    <div className="recorded-frame-label"><span className="recorded-dot"/>{frame.source.toUpperCase()} FRAME<span>{frame.width} × {frame.height}</span></div>
    {scene.registration.status === 'view_changed' && <div className="overlay-inhibition"><Icon name="shield" size={17}/>View changed. The previous overlay is hidden.</div>}
    {scene.registration.status === 'locked_partial' && <div className="overlay-inhibition partial"><Icon name="eye" size={17}/>Some markers are obscured. The locked test mapping is retained.</div>}
    {matchesMap && !overlayAllowed && scene.registration.status !== 'view_changed' && <div className="overlay-note">{candidate ? 'Lock the test view to project the planned route.' : 'Route overlay requires a valid locked test registration.'}</div>}
  </div>;
}

export function MapScene({ workspace, readOnly = false, onSnapshot }: {
  workspace: WorkspaceSnapshot | null; readOnly?: boolean; onSnapshot: (snapshot: SceneSnapshot) => void;
}) {
  const [map, setMap] = useState<TemporaryMap | null>(null);
  const [scene, setScene] = useState<SceneSnapshot | null>(null);
  const [view, setView] = useState<'camera' | 'spatial'>('camera');
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<'upload' | 'registration' | 'inspection' | null>(null);
  const [capturedAt, setCapturedAt] = useState('');
  const [expected, setExpected] = useState('Inspect the temporary Little Town map. Report visible places, car visibility and signal color. Do not infer physical motion.');
  const fileInput = useRef<HTMLInputElement>(null);
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
  useEffect(() => { if (currentExpectation) setExpected(currentExpectation); }, [currentExpectation]);

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
    } catch (err) { setError(err instanceof Error ? err.message : 'The scene request failed.'); }
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
    } catch (err) { setError(err instanceof Error ? err.message : 'The image upload failed.'); }
    finally { setBusy(null); if (fileInput.current) fileInput.current.value = ''; }
  }

  const route = workspace?.plan?.route ?? null;
  const status = scene?.registration.status ?? 'unregistered';
  const markerCount = scene?.detection.marker_ids.filter(id => map?.markers.some(marker => marker.id === id)).length ?? 0;
  const canLock = ['candidate', 'view_changed'].includes(status) && markerCount === 4 && !active && !readOnly && !busy;
  const inspection = scene?.inspection;
  const currentInspection = inspection?.frame_id === scene?.frame?.id ? inspection : null;

  return <div className="map-scene-component">
    <div className="map-scene-controls">
      <div className="scene-view-toggle" role="group" aria-label="Scene view">
        <button className={view === 'camera' ? 'selected' : ''} onClick={() => setView('camera')}><Icon name="camera" size={15}/>Camera frame</button>
        <button className={view === 'spatial' ? 'selected' : ''} onClick={() => setView('spatial')}><Icon name="route" size={15}/>Spatial map</button>
      </div>
      <button className="scene-tools-toggle" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}><Icon name="settings" size={15}/>Image tools</button>
    </div>
    {error && <div className="scene-error" role="alert"><Icon name="shield" size={16}/><span>{error}</span><button onClick={() => { setError(''); void refresh(true); void refreshMap(); }} aria-label="Refresh scene state"><Icon name="refresh" size={15}/></button></div>}
    {view === 'camera' ? scene?.frame ? <RecordedFrame scene={scene} route={route} map={map}/> : <div className="no-recorded-frame"><Icon name="camera" size={40}/><h2>Your workspace, in view.</h2><p>Load a recorded image of the temporary print to detect its markers and inspect the scene.</p><button disabled={readOnly || Boolean(busy)} onClick={() => { setExpanded(true); fileInput.current?.click(); }}><Icon name="upload" size={17}/>Choose a recorded frame</button><small>No live camera is connected.</small></div> : map ? <SpatialMap map={map} route={route}/> : <div className="no-recorded-frame"><Icon name="route" size={36}/><h2>Loading temporary geometry…</h2><p>The map remains replaceable. No robot coordinates are included.</p></div>}
    <div className="registration-summary">
      <span className={`registration-badge ${status}`}><span/>{registrationLabels[status]}</span>
      <span className="marker-count">{markerCount}/4 markers{scene?.registration.residual_px != null ? ` · ${scene.registration.residual_px.toFixed(2)} px residual` : ''}</span>
      {['candidate', 'view_changed'].includes(status) && markerCount === 4 && <button disabled={!canLock} onClick={() => void sceneCommand('registration')} title={active ? 'Lock the test view during mission preparation.' : 'Explicitly lock this temporary camera-to-board test overlay.'}>{busy === 'registration' ? 'Locking…' : status === 'view_changed' ? 'Lock new test view' : 'Lock test view'}<Icon name="check" size={13}/></button>}
    </div>
    {scene?.registration.message && <p className={`registration-message ${status}`}>{scene.registration.message}</p>}
    <div className="frame-provenance">
      <span>{scene?.frame ? captureLabel(scene.frame) : 'No image evidence loaded'}</span>
      <span>{map ? `${map.title} · ${map.version} · temporary` : 'Temporary map pending'}</span>
    </div>
    {route && map && route.map_hash === map.geometry_hash && <div className="map-route-summary"><Icon name="route" size={14}/><span>{route.node_ids.join(' → ')}</span><strong>{route.distance_mm.toFixed(0)} mm</strong><small>drawing centerline only</small></div>}
    {route && map && route.map_hash !== map.geometry_hash && <div className="scene-error"><Icon name="shield" size={16}/><span>The stored plan belongs to different map geometry. Its route is hidden. Reset the simulation and create a new plan.</span></div>}

    <input ref={fileInput} type="file" accept="image/jpeg,image/png" className="hidden-file-input" aria-label="Recorded JPEG or PNG frame" disabled={readOnly || Boolean(busy)} onChange={event => void upload(event.target.files?.[0])}/>
    {expanded && <div className="image-tools-panel">
      <div className="image-tools-heading"><span className="eyebrow">RECORDED IMAGE TOOLS</span><span>Independent scene evidence</span></div>
      <div className="image-upload-row"><button className="image-upload-button" disabled={readOnly || Boolean(busy)} onClick={() => fileInput.current?.click()}><Icon name="upload" size={16}/>{busy === 'upload' ? 'Uploading…' : 'Upload recorded frame'}</button><label>Capture time <span>(optional · local time)</span><input type="datetime-local" value={capturedAt} disabled={readOnly || Boolean(busy)} onChange={event => setCapturedAt(event.target.value)}/></label></div>
      <p className="image-input-note">JPEG or PNG · up to 8 MiB / 12 megapixels. An omitted capture time stays unknown.</p>
      <label className="inspection-expected">Expected scene or action outcome<textarea value={expected} maxLength={1000} rows={2} disabled={readOnly || Boolean(busy)} onChange={event => setExpected(event.target.value)}/></label>
      <div className="inspection-submit-row"><button className="inspect-image-button" disabled={readOnly || Boolean(busy) || !scene?.frame || !scene.capabilities.muse_configured || !expected.trim()} onClick={() => void sceneCommand('inspection')}><Icon name="spark" size={17}/>{busy === 'inspection' ? 'MUSE is inspecting…' : 'Inspect image with MUSE'}</button><span>{scene?.capabilities.muse_configured ? 'Actual Meta API · explicit request' : 'Meta image inspection not configured'}</span></div>
      <div className="inspection-authority-note"><Icon name="shield" size={14}/>Scene inspection cannot approve an action or advance the mission.</div>
    </div>}
    {currentInspection && <section className="scene-inspection-result" aria-label="MUSE scene inspection result">
      <div className="scene-inspection-heading"><Icon name="spark" size={17}/><strong>MUSE IMAGE INSPECTION</strong><span className={`verdict ${currentInspection.verdict.toLowerCase()}`}>{currentInspection.verdict}</span></div>
      <p>{currentInspection.summary}</p>
      <dl><div><dt>Visible places</dt><dd>{currentInspection.visible_places.join(', ') || 'None confirmed'}</dd></div><div><dt>Car</dt><dd>{currentInspection.car_visible ? 'Visible according to the model' : 'Not confirmed visible'}</dd></div><div><dt>Image signal</dt><dd>{currentInspection.signal} · model report only</dd></div><div><dt>Expected</dt><dd>{currentInspection.expected}</dd></div></dl>
      {currentInspection.limitations.length > 0 && <ul>{currentInspection.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>}
      <footer><span>{currentInspection.model} · {new Date(currentInspection.created_at).toLocaleString('en-US')}</span><strong>No motion authority</strong></footer>
    </section>}
  </div>;
}
