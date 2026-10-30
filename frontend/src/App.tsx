import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ProviderMode, ReviewVerdict, SignalColor, WorkspaceSnapshot } from '../../contracts/workspace';
import type { SceneSnapshot, TemporaryMap } from '../../contracts/scene';
import type { RecordedActionReviewCommand } from '../../contracts/action-review';
import { BrandMark, Icon } from './Icons';
import { MapScene } from './MapScene';
import { createRequestId } from './requestId';
import { ActionReviewPanel } from './ActionReview';
import { LiveEvidence } from './LiveEvidence';
import { ViewportDialog, PlanBrowser, EvidenceBrowser, PhysicalHistoryBrowser, PhysicalReviewPanel, PhysicalRouteBrowser, PhysicalStatusPanel, TextPages, SelectField, executionStepLabel, physicalSequenceFocus, signalGateLabel } from './WorkspaceUI';
import { GoalIntentBar, VoiceInputOptions } from './GoalIntent';
import { destinationGoal, destinationOptions, destinationPage, drawingDistance, nodeLabel, planStepLabel } from './mapMetadata';
import { currentSignalJunction, signalDisplay } from './routeProgress';
import { commandErrorMessage, readableError } from './commandError';
import { usePhysicalDisplay, displaySignalLabel } from './usePhysicalDisplay';
import { usePhysicalMission } from './usePhysicalMission';
import { physicalAvailable, physicalProgress, physicalReviewLabel, physicalTelemetry, physicalDestinationBlocker, physicalDetail, physicalFinished, physicalMatchesPlan, physicalParkingEnabled, physicalRunning, physicalStartCommand, physicalTitle, physicalVisionActive, type ExecutionMode } from './physicalMission';

type View = 'Workspace' | 'Plan' | 'Replay';
const terminalStates = new Set(['COMPLETED', 'CANCELLED', 'FAULT', 'RECOVERY_REQUIRED']);
const stateLabels: Record<string, string> = {
  IDLE: 'Ready for a goal', PLAN_READY: 'Awaiting approval', READY: 'Ready for next action',
  REVIEW_REQUIRED: 'Review required', WAITING_SIGNAL: 'Waiting for green', REOBSERVE: 'New observation required',
  COMPLETED: 'Mission complete', CANCELLED: 'Mission cancelled', FAULT: 'Review failed', RECOVERY_REQUIRED: 'Reconciliation required',
};
const stepDescriptions: Record<string, string> = {
  PUSH: 'Surface push to the next waypoint.',
  STOP: 'Full stop before checking the signal.',
  CROSS: 'Fresh green required before entry.',
  VERIFY: 'Compare arrival with the planned goal.',
};
function timeLabel(at: string) {
  const date = new Date(at);
  return Number.isNaN(date.valueOf()) ? at : date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}
export function App() {
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [view, setView] = useState<View>('Workspace');
  const [draft, setDraft] = useState('');
  const [mapSnapshot, setMapSnapshot] = useState<TemporaryMap | null>(null);
  const [goalPage, setGoalPage] = useState(0);
  const [provider, setProvider] = useState<ProviderMode>('demo');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [online, setOnline] = useState(false);
  const [showDemo, setShowDemo] = useState(false);
  const [modal, setModal] = useState<'goal' | 'review' | 'companion' | 'robot' | null>(null);
  const [goalMode, setGoalMode] = useState<'text' | 'voice' | 'query'>('text');
  const [mobileMission, setMobileMission] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [sceneSnapshot, setSceneSnapshot] = useState<SceneSnapshot | null>(null);
  const [previewSource, setPreviewSource] = useState<string | null>(null);
  const [actionReviewPending, setActionReviewPending] = useState(false);
  const [localVisionRequest, setLocalVisionRequest] = useState<'plan' | 'car' | 'signal' | null>(null);
  const [imageToolsRequest, setImageToolsRequest] = useState(0);
  const [missionCollapsed, setMissionCollapsed] = useState(false);
  const [sceneInsetRight, setSceneInsetRight] = useState(0);
  const [cameraPreview, setCameraPreview] = useState(false);
  const stageRef = useRef<HTMLElement>(null);
  const missionRef = useRef<HTMLElement>(null);
  const stepsRef = useRef<HTMLOListElement>(null);
  const planReveal = useRef<{ id: string | undefined; at: number }>({ id: undefined, at: 0 });
  const physical = usePhysicalMission();
  // An unavailable first status must not opt the tablet into simulated data.
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('physical');
  const [physicalBusy, setPhysicalBusy] = useState(false);
  const [physicalUnconfirmed, setPhysicalUnconfirmed] = useState<'start' | 'stop' | null>(null);
  const modeChosen = useRef(false);
  const current = useRef<WorkspaceSnapshot | null>(null);
  const goalInput = useRef<HTMLInputElement>(null);
  const applySnapshot = useCallback((snapshot: WorkspaceSnapshot) => {
    if (snapshot.schema_version !== 'pushpilot.workspace.v1') throw new Error('The server returned an unsupported workspace version.');
    setWorkspace(previous => {
      if (previous && previous.session_id === snapshot.session_id && previous.revision > snapshot.revision) return previous;
      current.current = snapshot;
      return snapshot;
    });
    setOnline(true);
  }, []);
  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/state', { cache: 'no-store' });
      if (!response.ok) throw new Error('Workspace state is unavailable.');
      applySnapshot(await response.json() as WorkspaceSnapshot);
    } catch { setOnline(false); }
  }, [applySnapshot]);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 1500); return () => window.clearInterval(timer); }, [refresh]);
  useEffect(() => { if (workspace?.goal) setDraft(workspace.goal.text); }, [workspace?.goal?.text]);
  useEffect(() => { if (workspace?.goal) setProvider(workspace.goal.provider); }, [workspace?.goal?.provider]);
  useEffect(() => {
    if (!physical.loaded || modeChosen.current) return;
    if (physical.status?.enabled && physical.connected) {
      setExecutionMode('physical');
      setProvider('meta');
      modeChosen.current = true;
    }
  }, [physical.status, physical.loaded, physical.connected]);
  useEffect(() => {
    if (!physical.connected || !physical.status || !physicalUnconfirmed) return;
    if (physicalUnconfirmed === 'start' && physicalMatchesPlan(physical.status, current.current)) setPhysicalUnconfirmed(null);
    if (physicalUnconfirmed === 'stop' && physical.status.robot.stationary && ['HOLD', 'HELD', 'CANCELLED', 'COMPLETE', 'COMPLETED', 'FAILED', 'FAULT'].includes(physical.status.state)) setPhysicalUnconfirmed(null);
  }, [physical.status, physical.connected, physicalUnconfirmed]);
  useEffect(() => {
    setGoalPage(0);
  }, [mapSnapshot?.id, mapSnapshot?.version, mapSnapshot?.geometry_hash]);

  async function command(endpoint: string, data: Record<string, unknown> = {}) {
    const snapshot = current.current;
    if (!snapshot || physicalRunning(physical.status) || physicalBusy || physicalUnconfirmed || (busy && endpoint !== 'cancel') || view === 'Replay' || (actionReviewPending && endpoint !== 'cancel')) return;
    const liveInference = ['live-actions/run', 'live-actions/reviews', 'live-signals/wait'].includes(endpoint)
      || (endpoint === 'goals' && data.provider === 'meta' && Boolean(snapshot.capabilities.live_planning));
    setBusy(true); setError('');
    if (liveInference) { setActionReviewPending(true); setLocalVisionRequest(endpoint === 'goals' ? 'plan' : endpoint === 'live-signals/wait' ? 'signal' : 'car'); }
    try {
      const response = await fetch(`/api/v1/${endpoint}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: createRequestId(), expected_revision: snapshot.revision, ...data }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        if (response.status === 409) await refresh();
        throw new Error(commandErrorMessage(payload, response.status));
      }
      applySnapshot(payload as WorkspaceSnapshot);
    } catch (err) { setError(err instanceof Error ? err.message : 'Connection interrupted. Refresh the workspace before continuing.'); }
    finally { setBusy(false); if (liveInference) { setActionReviewPending(false); setLocalVisionRequest(null); } }
  }
  async function physicalCommand(kind: 'start' | 'stop') {
    if (physicalBusy || physicalUnconfirmed === kind || (kind === 'start' && view === 'Replay') || !physical.status) return;
    setPhysicalBusy(true); setError('');
    let submitted = false;
    let responseConfirmed = false;
    try {
      if (kind === 'start' && (!physical.connected || busy || actionReviewPending)) throw new Error('Wait for a fresh robot status before starting.');
      const body = kind === 'start' ? physicalStartCommand(current.current, physical.status, createRequestId())
        : { request_id: createRequestId(), expected_revision: physical.status.revision };
      submitted = true;
      const response = await fetch(`/api/v1/physical/${kind}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
        signal: AbortSignal.timeout(15000),
      });
      const payload: unknown = await response.json();
      responseConfirmed = !response.ok;
      if (!response.ok) {
        await physical.refresh();
        throw new Error(commandErrorMessage(payload, response.status));
      }
      physical.apply(payload);
      responseConfirmed = true;
    } catch (err) {
      if (submitted && !responseConfirmed) setPhysicalUnconfirmed(kind);
      setError(err instanceof Error ? err.message : 'Robot command outcome is unconfirmed. Check live status before retrying.');
      void physical.refresh();
    } finally { setPhysicalBusy(false); }
  }
  async function reviewRecordedAction(data: Omit<RecordedActionReviewCommand, 'request_id' | 'expected_revision'>) {
    const snapshot = current.current;
    if (!snapshot || busy || actionReviewPending || physicalRunning(physical.status) || physicalBusy || physicalUnconfirmed || view === 'Replay') return;
    setActionReviewPending(true); setLocalVisionRequest('car'); setError('');
    try {
      const response = await fetch('/api/v1/action-reviews', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: createRequestId(), expected_revision: snapshot.revision, ...data }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        if (response.status === 409) {
          await refresh();
          throw new Error('The mission or recorded pair changed. The result was not applied. Check the current action and select its recordings again.');
        }
        const detail = payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : payload;
        throw new Error(readableError(detail));
      }
      applySnapshot(payload as WorkspaceSnapshot);
    } catch (err) { setError(err instanceof Error ? err.message : 'MUSE action review could not be completed. No demo verdict was substituted.'); }
    finally { setActionReviewPending(false); setLocalVisionRequest(null); }
  }
  const state = workspace?.state ?? 'IDLE';
  const robotRunning = physicalRunning(physical.status);
  const robotMode = executionMode === 'physical' || robotRunning;
  const display = usePhysicalDisplay(physical.status, robotMode && physical.connected);
  const sceneReadOnly = actionReviewPending || robotRunning || physicalBusy || Boolean(physicalUnconfirmed);
  const robotStatusDialog = robotMode || modal === 'robot';
  const robotMission = robotMode && (robotRunning || physicalMatchesPlan(physical.status, workspace));
  const robotFinished = robotMission && physicalFinished(physical.status);
  const robotTelemetry = robotMode ? physicalTelemetry(physical.status, workspace, physical.connected) : null;
  const robotFocus = physicalSequenceFocus(robotTelemetry?.sequence ?? [], robotTelemetry?.current_step_id);
  const robotProgress = physicalProgress(physical.status, robotTelemetry);
  const missionStatus = robotMission ? physical.status : null;
  const canEditGoal = Boolean(workspace && ['IDLE', 'PLAN_READY'].includes(state) && online && !busy && !actionReviewPending && !robotRunning && !physicalBusy && !physicalUnconfirmed);
  const active = Boolean(workspace?.approved && !terminalStates.has(state));
  const selected = workspace?.events.find(event => event.id === selectedEvent) ?? workspace?.events.at(-1);
  const signal = workspace?.signal.color ?? 'UNKNOWN';
  const pendingReview = state === 'REVIEW_REQUIRED' && workspace?.review?.verdict === 'PENDING';
  const liveBacked = Boolean(workspace?.plan?.planning);
  const signalWatchRunning = liveBacked && state === 'WAITING_SIGNAL' && workspace?.signal_watch?.status === 'running';
  const liveReviewEvidence = workspace?.review?.evidence?.input_kind === 'server_bound_live_pair' ? workspace.review.evidence : undefined;
  const replayLiveEvidence = selected?.record && selected.record.input_kind !== 'operator_selected_recorded_pair' ? selected.record : undefined;
  const replayRecordedEvidence = selected?.record?.input_kind === 'operator_selected_recorded_pair' ? selected.record : undefined;
  const destination = robotMission ? physical.status?.destination ?? workspace?.goal?.destination : workspace?.goal?.destination;
  const destinationName = nodeLabel(mapSnapshot, destination);
  const startName = nodeLabel(mapSnapshot, workspace?.plan?.route.start ?? mapSnapshot?.start);
  const goalChoices = destinationPage(destinationOptions(mapSnapshot), goalPage);
  const currentStep = workspace?.plan?.steps[workspace.current_step];
  const signalJunction = currentSignalJunction(workspace);
  const signalReading = workspace && signalJunction ? signalDisplay(workspace, signalJunction, Date.now()) : 'unknown';
  const admittedCrossing = active && currentStep?.kind === 'CROSS';
  const signalCardLabel = admittedCrossing ? 'Crossing admitted' : signalReading === 'stale' ? 'Signal expired'
    : signalReading === 'unknown' ? 'Awaiting signal' : signalReading === 'red' ? 'Stop and wait' : 'Green observed';
  const completedSteps = robotMode ? robotProgress?.completed ?? 0 : workspace?.plan?.steps.filter(step => step.status === 'complete').length ?? 0;
  const totalSteps = robotMode ? robotProgress?.total ?? 0 : workspace?.plan?.steps.length ?? 0;
  const robotStatusTitle = physicalTitle(physical.status, physical.connected);
  const signalScanning = robotMode ? physicalVisionActive(missionStatus, physical.connected, 'signal') : localVisionRequest === 'signal';
  const carScanning = robotMode ? physicalVisionActive(missionStatus, physical.connected, 'car') : localVisionRequest === 'car' || localVisionRequest === 'plan';
  const robotStatusDetail = physicalDetail(physical.status, physical.connected);
  const robotParkingEnabled = physicalParkingEnabled(physical.status);
  const robotDestinationBlocker = physicalDestinationBlocker(physical.status, workspace?.plan?.route.destination, destinationName);
  const robotCanStart = robotMode && physical.connected && physicalAvailable(physical.status) && physical.status?.robot.connected && physical.status.robot.stationary && !physicalUnconfirmed
    && !robotRunning && !robotFinished && !robotDestinationBlocker && liveBacked && workspace?.goal?.provider === 'meta' && state === 'PLAN_READY';
  const robotCheckUsesStatus = robotMission || !physical.connected || !physicalAvailable(physical.status);
  const robotCheckTitle = robotCheckUsesStatus ? robotStatusTitle : state === 'PLAN_READY'
    ? robotDestinationBlocker ? 'Destination unavailable' : 'Ready for your approval' : 'Ready for a goal';
  const robotCheckDetail = robotCheckUsesStatus ? robotStatusDetail : state === 'PLAN_READY'
    ? robotDestinationBlocker ?? (!liveBacked || workspace?.goal?.provider !== 'meta'
      ? 'Create a MUSE plan from the live view to start the robot.'
      : robotParkingEnabled ? 'Start once. The executor handles movement, signal waits, parking and return.'
      : 'Start once. The executor handles delivery, signal waits and return.')
    : 'Choose a destination and review the MUSE route.';


  // Layout and read-only presentation effects never dispatch robot commands.
  const planId = robotMode ? physical.status?.mission_id ?? undefined : workspace?.plan?.id;
  if (planReveal.current.id !== planId) planReveal.current = { id: planId, at: performance.now() };
  const stepReveal = useMemo(() => {
    const elapsed = performance.now() - planReveal.current.at;
    return !robotMode && planId && !missionCollapsed && elapsed < 3000
      ? { '--reveal': `${Math.round(Math.max(0, 1750 - elapsed))}ms` } as React.CSSProperties : undefined;
  }, [planId, missionCollapsed, robotMode]);
  const liveMode = robotMode;
  const devices: [string, boolean][] = [
    ['Robot', physical.connected && Boolean(physical.status?.robot.connected)],
    ['Camera', cameraPreview], ['MUSE', Boolean(workspace?.capabilities.muse_configured)],
  ];
  useEffect(() => {
    if (robotMode ? ['WAITING_SIGNAL', 'HOLD', 'HELD', 'STOPPING', 'FAULT', 'FAILED'].includes(physical.status?.state ?? '')
      : ['PLAN_READY', 'REVIEW_REQUIRED', 'WAITING_SIGNAL', 'REOBSERVE', 'FAULT', 'RECOVERY_REQUIRED'].includes(state)) setMissionCollapsed(false);
  }, [state, robotMode, physical.status?.state]);
  useEffect(() => {
    const list = stepsRef.current, focused = list?.querySelector<HTMLElement>('li.focused');
    if (list && focused) {
      const anchor = focused.previousElementSibling as HTMLElement | null;
      list.scrollTo({ top: Math.max(0, (anchor ?? focused).offsetTop - list.offsetTop - 8), behavior: 'smooth' });
    }
  }, [workspace?.current_step, workspace?.plan?.id, robotFocus, planId, missionCollapsed]);
  useEffect(() => {
    const stage = stageRef.current, panel = missionRef.current;
    if (!stage || !panel) return;
    const measure = () => {
      const stageBox = stage.getBoundingClientRect(), panelBox = panel.getBoundingClientRect();
      setSceneInsetRight(missionCollapsed || panelBox.width === 0 ? 0 : Math.max(0, Math.round(stageBox.right - panelBox.left)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(stage); observer.observe(panel);
    return () => observer.disconnect();
  }, [missionCollapsed]);

  function renderStopAction() {
    return <button className="primary-button physical-stop" disabled={physicalBusy || physicalUnconfirmed === 'stop'} onClick={() => void physicalCommand('stop')}><Icon name="pause"/>{physicalBusy ? 'Sending request…' : physical.status?.state === 'STOPPING' || physicalUnconfirmed === 'stop' ? 'Stop requested' : 'Stop robot mission'}</button>;
  }

  function renderPrimaryAction() {
    if (!workspace) return <button className="primary-button" disabled>Connecting to workspace…</button>;
    if (robotMode && robotMission) {
      if (robotFinished) return <button className="primary-button" disabled={physicalBusy || busy || !online || !physical.connected || !physical.status?.robot.stationary} onClick={() => void command('reset')}><Icon name="refresh"/>Plan the next mission</button>;
      return renderStopAction();
    }
    if (state === 'IDLE') return <button className="primary-button" disabled={!canEditGoal || !draft.trim()} onClick={() => void command('goals', { text: draft, provider, source: 'typed' })}><Icon name="spark"/>Create a plan<Icon name="arrow"/></button>;
    if (robotMode && state === 'PLAN_READY') return <button className="primary-button" disabled={!robotCanStart || physicalBusy || busy || actionReviewPending || !online} onClick={() => void physicalCommand('start')}><Icon name="play"/>{physicalBusy ? 'Starting mission…' : physicalUnconfirmed ? 'Confirming robot status…' : 'Start robot mission'}<Icon name="arrow"/></button>;
    if (robotMode) return <button className="primary-button" disabled={busy || actionReviewPending || physicalBusy || !online} onClick={() => void command('reset')}><Icon name="refresh"/>Create a new robot plan</button>;
    if (state === 'PLAN_READY') return <button className="primary-button" disabled={busy || actionReviewPending || !online} onClick={() => void command('approve', { plan_id: workspace.plan!.id, plan_revision: workspace.plan!.revision })}>Approve simulation<Icon name="arrow"/></button>;
    if (state === 'READY') return <button className="primary-button" disabled={busy || actionReviewPending || !online} onClick={() => void command(liveBacked ? 'live-actions/run' : 'advance')}><Icon name="play"/>{liveBacked && actionReviewPending ? 'Reviewing live images…' : 'Run next simulated action'}<Icon name="arrow"/></button>;
    if (state === 'REOBSERVE') return <button className="primary-button" disabled={busy || actionReviewPending || !online} onClick={() => { void command(liveBacked ? 'live-actions/reobserve' : 'reobserve'); if (liveBacked) setModal('review'); }}><Icon name="refresh"/>Open a new observation review</button>;
    if (terminalStates.has(state)) return <button className="primary-button" disabled={busy || actionReviewPending || !online} onClick={() => void command('reset')}><Icon name="refresh"/>Start a new simulation</button>;
    if (state === 'WAITING_SIGNAL') return liveBacked ? <button className="primary-button" disabled={signalWatchRunning || busy || actionReviewPending || !online} onClick={() => void command('live-signals/watch', { max_attempts: 30, interval_seconds: 2, max_duration_seconds: 300 })}><Icon name="eye"/>{signalWatchRunning ? `Watching signal… ${workspace.signal_watch!.attempts}/${workspace.signal_watch!.max_attempts}` : actionReviewPending ? 'Checking the signal…' : workspace.signal_watch ? 'Restart signal watch' : 'Watch signal with MUSE'}{!signalWatchRunning && <Icon name="arrow"/>}</button> : <div className="waiting-message"><Icon name="pause" size={22}/><span>Waiting for a fresh green signal.<small>Accepted checks allow automatic entry.</small></span></div>;
    return <button className="primary-button" disabled={busy || actionReviewPending || !online} onClick={() => setModal('review')}><Icon name="eye"/>{actionReviewPending ? liveBacked ? 'Reviewing live images…' : 'Reviewing recorded images…' : liveBacked ? 'Review live images' : 'Review recorded images'}<Icon name="arrow"/></button>;
  }


  const route = workspace?.plan?.route;
  const steps = workspace?.plan?.steps ?? [];
  const inspection = sceneSnapshot?.inspection;
  const modelLabel = actionReviewPending ? 'Reviewing images' : workspace?.review ? workspace.review.verdict : inspection?.verdict ?? 'No image review';
  const openImageTools = () => { if (sceneReadOnly) return; setModal(null); setView('Workspace'); window.setTimeout(() => setImageToolsRequest(value => value + 1), 0); };
  const openVoice = () => { setGoalMode('voice'); setView('Workspace'); setModal('goal'); };
  const openQuery = () => { setGoalMode(workspace?.goal ? 'query' : 'text'); setView('Workspace'); setModal('goal'); };

  return <div className="app-shell">
    <header className="topbar">
      <div className="header-title"><span className="brand" aria-hidden="true"><BrandMark/></span><h1>PushPilot</h1>{mapSnapshot && <span className="header-map"><span aria-hidden="true">/</span>{mapSnapshot.title}</span>}</div>
      <div className="header-status"><ul className="device-status" aria-label="Connections">{devices.map(([name, on]) => <li key={name} className={on ? 'on' : ''}><i key={String(on)} aria-hidden="true"/>{name}<span className="sr-only">{name === 'MUSE' ? on ? ' configured' : ' not configured' : on ? ' connected' : ' offline'}</span></li>)}</ul>
        <select className={`mode-label ${liveMode ? 'live' : ''}`} aria-label="Execution mode" value={robotMode ? 'physical' : 'simulation'} disabled={robotRunning || physicalBusy || Boolean(physicalUnconfirmed) || busy || actionReviewPending || (!robotMode && active)} onChange={event => { modeChosen.current = true; setExecutionMode(event.target.value as ExecutionMode); if (event.target.value === 'physical') setProvider('meta'); }}><option value="simulation">Simulation</option><option value="physical" disabled={!physical.connected || !physical.status?.enabled}>Robot</option></select>
        <button className={`header-replay ${view === 'Replay' ? 'active' : ''}`} aria-pressed={view === 'Replay'} onClick={() => setView('Replay')}><Icon name="clock" size={18}/><span>Mission Log</span></button></div>
    </header>
    <main ref={stageRef} className={`workspace-stage ${mobileMission ? 'mission-visible' : ''}`}>
      <MapScene presentation="stage" workspace={workspace} physicalLabel={robotMode ? robotMission ? robotStatusTitle : 'Awaiting robot execution' : undefined} physicalDisplay={display.snapshot} onSnapshot={setSceneSnapshot} onMapSnapshot={setMapSnapshot} onPreviewSource={setPreviewSource} onLiveCamera={setCameraPreview} sceneInsetRight={sceneInsetRight} readOnly={sceneReadOnly} openToolsRequest={imageToolsRequest}/>
      <div className="scene-heading"><GoalIntentBar query={workspace?.goal?.text ?? null} source={workspace?.goal?.source ?? null} onQuery={openQuery} onVoice={openVoice}/></div>
      <button className="mobile-mission-switch glass-surface" onClick={() => setMobileMission(value => !value)} aria-expanded={mobileMission}>{mobileMission ? 'Show scene' : 'Mission'}<Icon name={mobileMission ? 'close' : 'chevron'} size={16}/></button>
      {(error || !online) && <div className={`stage-notice ${error ? 'error' : ''}`} role={error ? 'alert' : 'status'}><Icon name="shield" size={17}/><span>{error || 'Backend unavailable. Refresh before taking action.'}</span><button aria-label={error ? 'Dismiss error' : 'Retry connection'} onClick={() => error ? setError('') : void refresh()}><Icon name={error ? 'close' : 'refresh'} size={16}/></button></div>}

      <aside ref={missionRef} className={`floating-mission glass-surface ${missionCollapsed ? 'collapsed' : ''}`} aria-label="Mission and execution controls">
        <div className="mission-heading"><span>Active mission</span><button className="mission-collapse" aria-expanded={!missionCollapsed} aria-label={missionCollapsed ? 'Expand mission panel' : 'Collapse mission panel'} onClick={() => setMissionCollapsed(value => !value)}><Icon name="chevron" size={16}/></button></div>
        <div className="mission-intro"><dl className="mission-journey"><div><dt>From</dt><dd>{startName}</dd></div><div><dt>To</dt><dd className={destination || workspace?.planning_pending ? '' : 'pending'}>{workspace?.planning_pending ? 'Planning…' : destination ? destinationName : 'Choose a destination'}</dd></div></dl>{missionCollapsed && <p className="mission-compact-state">{robotMode ? robotCheckTitle : stateLabels[state]}{totalSteps ? ` · ${completedSteps} / ${totalSteps} ${robotMode ? 'receipts' : 'actions'}` : ''}</p>}</div>
        {!missionCollapsed && <><div className="mission-progress"><div><span>Mission progress</span><strong>{robotMode && !robotProgress ? physical.connected ? 'Awaiting execution' : 'Unavailable' : <><span key={completedSteps} className="count-pop">{completedSteps}</span><small> / {totalSteps} {robotMode ? 'receipts' : 'actions'}</small></>}</strong></div><div className="mission-progress-bar" role="progressbar" aria-label={robotMode ? 'Native executor receipts' : 'Completed mission actions'} aria-valuemin={0} aria-valuemax={totalSteps || 1} aria-valuenow={completedSteps}><span style={{ width: `${totalSteps ? completedSteps / totalSteps * 100 : 0}%` }}/></div></div>
        <section className="mission-context"><div className="section-caption"><h3>Route sequence</h3><button onClick={() => setView('Plan')} aria-label="View full route">View all<Icon name="chevron" size={13}/></button></div>
          {robotMode ? robotTelemetry?.sequence.length ? <ol ref={stepsRef} className="context-steps" aria-label="Robot route context">{robotTelemetry.sequence.map((step, index) => <li key={step.id} className={`${step.status} ${index === robotFocus ? `focused${step.id !== robotTelemetry.current_step_id ? ' display-anchor' : ''}` : ''}`}><span className="context-number">{step.status === 'complete' ? <Icon name="check" size={12}/> : String(index + 1).padStart(2, '0')}</span><div><strong title={step.label}>{executionStepLabel(step)}</strong>{index === robotFocus && <small title={step.detail}>{step.detail || step.status}</small>}</div></li>)}</ol> : <p className="empty-copy">{physical.connected ? 'Awaiting the executor sequence.' : 'Robot sequence unavailable.'}</p> : steps.length ? <ol key={planId} ref={stepsRef} className={`context-steps${stepReveal ? ' stagger' : ''}`} style={stepReveal} aria-label="Current route context">{steps.map((step, index) => <li key={step.id} style={{ '--i': index } as React.CSSProperties} className={`${step.status} ${!terminalStates.has(state) && workspace?.current_step === index ? 'focused' : ''}`}><span className="context-number">{step.status === 'complete' ? <Icon name="check" size={12}/> : String(index + 1).padStart(2, '0')}</span><div><strong>{planStepLabel(mapSnapshot, step)}</strong>{workspace?.current_step === index && <small>{stepDescriptions[step.kind]}</small>}</div></li>)}</ol> : <p className="empty-copy">The route's actions appear here once a plan is created.</p>}
        </section>
        {(robotMode || state !== 'READY') && <section className={`next-check ${robotMode ? 'physical-check' : ''}`} aria-live="polite"><div><Icon name={(robotMode ? physical.status?.signal.waiting : state === 'WAITING_SIGNAL') ? 'pause' : 'shield'} size={16}/><h3>{robotMode ? robotCheckTitle : stateLabels[state]}</h3></div><p>{robotMode ? robotCheckDetail : workspace?.next_check ?? 'Set a goal and inspect the proposed route.'}</p>{robotMode && <button className="physical-detail-link" onClick={() => setModal('robot')}>Robot status<Icon name="chevron" size={12}/></button>}</section>}</>}
        <div className="mission-actions">{!robotMode && signalWatchRunning && <button className="secondary-button" disabled={busy || !online} onClick={() => void command('live-signals/watch/stop')}>Stop signal watch<Icon name="pause" size={16}/></button>}{!robotMode && (active || workspace?.planning_pending) && <button className="cancel-button" disabled={(busy && !actionReviewPending) || !online} onClick={() => void command('cancel')}>End simulation</button>}{renderPrimaryAction()}</div>
      </aside>

      <div className="status-dock" aria-label="Workspace status">
        <button className="status-card glass-surface" onClick={() => setView('Plan')}><span className="status-card-top">Route overview<Icon name="chevron" size={14}/></span><span className="status-card-value value-swap">{robotMode ? robotProgress ? <>{completedSteps}<small>/ {totalSteps} receipts</small></> : 'Awaiting execution' : <>{drawingDistance(route?.distance_mm)}<small>drawing mm</small></>}</span><span className="status-card-bottom">{robotMode ? robotTelemetry?.distance_source === 'native_tcp' ? `TCP travel · ${robotTelemetry.distance_mm!.toFixed(1)} mm` : 'TCP travel not measured' : `${route?.junction_ids.length ?? '—'} junction checks`}<span>{robotMode ? 'Executor' : `${completedSteps}/${totalSteps} actions`}</span></span></button>
        <button className={`status-card glass-surface ${signalScanning ? 'is-scanning' : ''} signal-${robotMode ? physical.connected && missionStatus ? missionStatus.signal.color.toLowerCase() : 'unknown' : admittedCrossing ? 'green' : signalReading}`} onClick={() => robotMode ? setModal('robot') : liveBacked ? setView('Replay') : setShowDemo(true)}><span className="status-card-top"><i/>Signal {robotMode ? robotTelemetry?.signal_gate_id ? `· ${signalGateLabel(robotTelemetry.signal_gate_id)}` : '' : signalJunction ? `· ${nodeLabel(mapSnapshot, signalJunction)}` : ''}<Icon name="chevron" size={14}/></span><span className="status-card-value value-swap">{robotMode ? displaySignalLabel(missionStatus, physical.connected, display.snapshot) : signalScanning ? 'Checking signal · MUSE' : signalCardLabel}</span><span className="status-card-bottom">{robotMode ? signalScanning ? 'Reading a fresh camera image' : missionStatus?.signal.waiting ? 'Waiting for confirmed green' : robotTelemetry?.signal_observed_at != null ? `Observed ${timeLabel(new Date(robotTelemetry.signal_observed_at * 1000).toISOString())}` : 'No robot signal observation' : admittedCrossing ? 'Accepted entry · review required' : workspace?.stopped ? 'Simulated stop confirmed' : 'Mandatory stop before entry'}<span>{robotMode ? 'Robot' : 'Simulation'}</span></span></button>
        <button className={`status-card glass-surface ${carScanning || signalScanning ? 'is-scanning' : ''}`} onClick={() => robotMode || workspace?.review ? setModal('review') : openImageTools()}><span className="status-card-top"><i className="model-dot"/>Visual review<Icon name="chevron" size={14}/></span><span className="status-card-value model-value value-swap">{robotMode ? physicalReviewLabel(missionStatus, robotTelemetry, physical.connected) : localVisionRequest === 'plan' ? 'Planning route · MUSE' : localVisionRequest === 'car' ? 'Checking images · MUSE' : modelLabel === 'USABLE' ? 'Scene inspected' : modelLabel}</span><span className="status-card-bottom">{robotMode ? robotTelemetry?.review ? `MUSE · ${timeLabel(new Date(robotTelemetry.review.observed_at * 1000).toISOString())}` : 'Awaiting robot image evidence' : workspace?.review ? liveBacked ? liveReviewEvidence ? 'MUSE · native live pair' : 'Native pair pending' : workspace.review.source === 'meta' ? 'MUSE · recorded pair' : 'Demo action review' : inspection ? 'MUSE · recorded scene' : 'Awaiting image evidence'}<span>{robotMode ? 'Robot' : workspace?.review ? 'Action' : 'Scene'}</span></span></button>
      </div>

    </main>

    <ViewportDialog actions={robotMission && !robotFinished ? renderStopAction() : undefined} open={modal === 'goal'} title="Mission goal" subtitle="SET THE INTENT" onClose={() => setModal(null)} className="goal-dialog">
      <nav className="goal-modal-tabs" role="tablist" aria-label="Goal input sections"><button role="tab" aria-selected={goalMode === 'text'} disabled={!canEditGoal} onClick={() => setGoalMode('text')}>Type a goal</button><button role="tab" aria-selected={goalMode === 'voice'} onClick={() => setGoalMode('voice')}><Icon name="mic" size={15}/>Voice input</button>{workspace?.goal && <button role="tab" aria-selected={goalMode === 'query'} onClick={() => setGoalMode('query')}>Original query</button>}</nav>
      <div className="goal-mode-panel" role="tabpanel" aria-label={goalMode === 'voice' ? 'Voice input options' : goalMode === 'query' ? 'Original user query' : 'Typed goal input'}>
      {goalMode === 'voice' ? <VoiceInputOptions canEdit={canEditGoal} onContinue={() => setGoalMode(canEditGoal ? 'text' : 'query')}/>
        : goalMode === 'query' ? <section className="original-query-panel"><div className="original-query-source"><Icon name={workspace?.goal?.source === 'voice' ? 'mic' : 'text'} size={16}/><span>{workspace?.goal?.source === 'voice' ? 'Voice input' : 'Typed input'} · original request</span></div><TextPages text={workspace?.goal?.text ?? 'No submitted goal yet.'} size={220}/><footer><span>{canEditGoal ? 'Your original words, saved with this plan.' : 'The active goal is read-only during execution.'}</span>{canEditGoal && <button className="secondary-button" onClick={() => setGoalMode('text')}>Edit goal<Icon name="arrow" size={16}/></button>}</footer></section>
        : <form className="goal-form" onSubmit={event => { event.preventDefault(); if (canEditGoal && draft.trim()) { void command('goals', { text: draft, provider, source: 'typed' }); setModal(null); } }}>
        <div className="goal-choices"><div className="goal-destinations">{goalChoices.items.map(place => <button type="button" key={place.id} title={`${place.label} · ${place.id}`} disabled={!canEditGoal} onClick={() => mapSnapshot && setDraft(destinationGoal(mapSnapshot, place.id))}><span>{place.label}</span><Icon name="arrow" size={16}/></button>)}</div>{goalChoices.pages > 1 && <nav className="goal-choice-pager" aria-label="Destination pages"><button type="button" disabled={goalChoices.page === 0} onClick={() => setGoalPage(value => value - 1)} aria-label="Previous destinations"><Icon name="chevron" className="reverse" size={14}/></button><span>{goalChoices.page + 1} / {goalChoices.pages}</span><button type="button" disabled={goalChoices.page + 1 >= goalChoices.pages} onClick={() => setGoalPage(value => value + 1)} aria-label="Next destinations"><Icon name="chevron" size={14}/></button></nav>}</div>
        <label htmlFor="goal-input">Your goal<input ref={goalInput} id="goal-input" value={draft} onChange={event => setDraft(event.target.value)} disabled={!canEditGoal} maxLength={500} aria-label="Your mission goal"/></label>
        <SelectField id="provider-mode" label="Goal interpreter" value={provider} disabled={!canEditGoal} onChange={setProvider} options={[{ value: 'demo', label: 'Demo interpreter', disabled: robotMode }, { value: 'meta', label: `MUSE · Meta API${workspace?.capabilities.muse_configured ? '' : ' (not configured)'}`, disabled: !workspace?.capabilities.muse_configured }]}/>

        <button className="goal-voice-shortcut" type="button" onClick={() => setGoalMode('voice')}><Icon name="mic" size={16}/><span>Voice input</span><small>Not connected</small><Icon name="chevron" size={14}/></button>
        <div className="dialog-bottom"><span>A new plan requires explicit approval.</span><button className="primary-button" type="submit" disabled={!canEditGoal || !draft.trim()}><Icon name="spark" size={17}/>Create a plan<Icon name="arrow" size={17}/></button></div>
      </form>}
      </div>
    </ViewportDialog>
    <ViewportDialog actions={robotMission && !robotFinished ? renderStopAction() : undefined} open={view === 'Plan'} title="Route plan" subtitle="INSPECT THE SEQUENCE" onClose={() => setView('Workspace')}>{robotMode ? <PhysicalRouteBrowser status={missionStatus} telemetry={robotTelemetry} connected={physical.connected} map={mapSnapshot}/> : <PlanBrowser workspace={workspace} map={mapSnapshot}/>}</ViewportDialog>
    <ViewportDialog actions={robotMission && !robotFinished ? renderStopAction() : undefined} open={view === 'Replay' && modal !== 'review'} title="Mission Log" subtitle="SOURCE-LABELLED EVIDENCE" onClose={() => setView('Workspace')}>{robotMode ? <PhysicalHistoryBrowser telemetry={robotTelemetry} connected={physical.connected}/> : <EvidenceBrowser events={workspace?.events ?? []} selected={selected} onSelect={setSelectedEvent} onOpenRecord={() => setModal('review')}/>}</ViewportDialog>
    <ViewportDialog actions={robotMission && !robotFinished ? renderStopAction() : undefined} open={modal === 'review'} title={robotMode ? 'Robot visual review' : view === 'Replay' ? replayLiveEvidence ? 'Live image evidence' : 'Recorded evidence' : 'Visual action review'} subtitle={view === 'Replay' ? 'READ-ONLY REPLAY' : 'COMPARE EXPECTED AND OBSERVED'} onClose={() => setModal(null)} className="review-dialog">
      {error && <div className="dialog-error" role="alert"><Icon name="shield" size={17}/><span>{error}</span><button aria-label="Dismiss review error" onClick={() => setError('')}><Icon name="close" size={16}/></button></div>}
      {robotMode ? <PhysicalReviewPanel status={missionStatus} telemetry={robotTelemetry} connected={physical.connected}/> : view === 'Replay' && replayLiveEvidence ? <LiveEvidence key={replayLiveEvidence.id} evidence={replayLiveEvidence}/>
        : view !== 'Replay' && liveBacked ? pendingReview ? <section className="ar-workspace" aria-label="Live action review"><header className="ar-heading"><div><span className="ar-eyebrow">Server-bound native image pair</span><h2>Review live images</h2></div><span className="ar-source">MUSE · simulation only</span></header><section className="ar-stage ar-result"><TextPages text={`${workspace?.review?.expected ?? 'Inspect the current action.'}\n\nThe backend retains the original BEFORE image and selects a new AFTER image. MUSE reviews the visible result; a simulated action receipt does not prove real vehicle motion.`} size={380}/><button className="ar-review-submit" disabled={busy || actionReviewPending || !online} onClick={() => void command('live-actions/reviews', { review_id: workspace!.review!.id, expected_visual: workspace!.review!.expected })}>{actionReviewPending ? 'MUSE is reviewing…' : 'Review live images'}<Icon name="arrow" size={18}/></button></section><p className="ar-authority"><Icon name="shield" size={15}/><span>Native camera images · no physical motion authority</span></p></section>
          : liveReviewEvidence ? <LiveEvidence key={liveReviewEvidence.id} evidence={liveReviewEvidence}/>
            : <section className="ar-workspace"><TextPages text="Run an approved simulated action to capture its native BEFORE image and request a new AFTER-image review. No action has been physically executed."/></section>
        : <ActionReviewPanel workspace={workspace} scene={sceneSnapshot} online={online} pending={actionReviewPending} busy={busy} readOnly={view === 'Replay'} replayEvidence={replayRecordedEvidence} onReview={reviewRecordedAction} onOpenTools={openImageTools}/>}
    </ViewportDialog>
    <ViewportDialog actions={robotMission && !robotFinished ? renderStopAction() : undefined} open={showDemo || modal === 'robot'} title={robotStatusDialog ? 'Robot status' : 'Simulation inputs'} subtitle={robotStatusDialog ? 'PHYSICAL MISSION' : 'OPERATOR-INJECTED DEMO DATA'} onClose={() => { setShowDemo(false); if (modal === 'robot') setModal(null); }} className="simulation-dialog">{robotStatusDialog ? <PhysicalStatusPanel status={physical.status} connected={physical.connected} map={mapSnapshot} missionBound={robotMission}/> : <div className="simulation-body" id="simulation-controls"><section><span className="form-eyebrow">PAPER SIGNAL STAND-IN</span><h3>{signalJunction ? `Junction ${signalJunction}` : 'Current junction'}</h3><p>{liveBacked ? 'This live-backed plan uses a fresh post-stop MUSE judgment. Manual signal inputs are disabled.' : 'Each fresh observation applies to one junction. A full stop is required before entry.'}</p><div className="signal-buttons">{(['RED', 'GREEN', 'UNKNOWN'] as SignalColor[]).map(color => <button key={color} className={`signal-option ${color.toLowerCase()} ${signal === color ? 'selected' : ''}`} disabled={liveBacked || busy || actionReviewPending || !online || !workspace || view === 'Replay'} onClick={() => void command('signal', { color })}><i/>{color[0] + color.slice(1).toLowerCase()}</button>)}</div></section><section><span className="form-eyebrow">ACTION REVIEW STAND-IN</span><h3>Demo verdict</h3><p>{liveBacked ? 'Native BEFORE and AFTER images are reviewed by MUSE. Demo verdicts cannot advance this plan.' : 'These explicit operator inputs are labelled demo. Actual MUSE review uses recorded image pairs.'}</p><div className="review-buttons">{(['PASS', 'REOBSERVE', 'UNKNOWN', 'FAIL'] as ReviewVerdict[]).map(verdict => <button key={verdict} disabled={liveBacked || !pendingReview || busy || actionReviewPending || !online || view === 'Replay'} onClick={() => void command('reviews', { review_id: workspace!.review!.id, verdict })}>{verdict === 'REOBSERVE' ? 'Re-observe' : verdict[0] + verdict.slice(1).toLowerCase()}</button>)}</div></section></div>}</ViewportDialog>
    <ViewportDialog actions={robotMission && !robotFinished ? renderStopAction() : undefined} open={modal === 'companion'} title="A shared perspective." subtitle="FUTURE GLASSES COMPANION" onClose={() => setModal(null)} className="companion-dialog"><div className="companion-concept"><span className="concept-pill">Concept · hardware not connected</span><h3>Look.<br/>Ask.<br/>Review.</h3><p>A future wearable view can bring the same scene, intent and reviewable plan into the operator's perspective.</p><div className="concept-sequence"><span>See the workspace</span><Icon name="arrow" size={18}/><span>State the goal</span><Icon name="arrow" size={18}/><span>Review on tablet</span></div><small>Wearable capture, voice and display integration require separate validation.</small></div></ViewportDialog>
  </div>;
}
