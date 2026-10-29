import { useCallback, useEffect, useRef, useState } from 'react';
import type { EvidenceEvent, ProviderMode, ReviewVerdict, SignalColor, WorkspaceSnapshot } from '../../contracts/workspace';
import type { SceneSnapshot, TemporaryMap } from '../../contracts/scene';
import type { RecordedActionReviewCommand } from '../../contracts/action-review';
import { BrandMark, Icon, type IconName } from './Icons';
import { MapScene } from './MapScene';
import { createRequestId } from './requestId';
import { ActionReviewPanel } from './ActionReview';
import { LiveEvidence } from './LiveEvidence';
import { ViewportDialog, PlanBrowser, EvidenceBrowser, PhysicalStatusPanel, TextPages } from './WorkspaceUI';
import { GoalIntentBar, VoiceInputOptions } from './GoalIntent';
import { destinationGoal, destinationOptions, destinationPage, drawingDistance, nodeLabel, planStepLabel } from './mapMetadata';
import { currentSignalJunction, signalDisplay } from './routeProgress';
import { commandErrorMessage, readableError } from './commandError';
import { usePhysicalMission } from './usePhysicalMission';
import { physicalAvailable, physicalDestinationBlocker, physicalDetail, physicalFinished, physicalMatchesPlan, physicalRunning, physicalSignalLabel, physicalStartCommand, physicalTitle, physicalVisionActive, type ExecutionMode } from './physicalMission';

type View = 'Workspace' | 'Plan' | 'Replay';
const terminalStates = new Set(['COMPLETED', 'CANCELLED', 'FAULT', 'RECOVERY_REQUIRED']);
const stateLabels: Record<string, string> = {
  IDLE: 'Ready for a goal', PLAN_READY: 'Awaiting approval', READY: 'Ready for next action',
  REVIEW_REQUIRED: 'Review required', WAITING_SIGNAL: 'Waiting for green', REOBSERVE: 'New observation required',
  COMPLETED: 'Mission complete', CANCELLED: 'Mission cancelled', FAULT: 'Review failed', RECOVERY_REQUIRED: 'Reconciliation required',
};
const stepIcons: Record<string, IconName> = { PUSH: 'car', STOP: 'pause', CROSS: 'route', VERIFY: 'eye' };
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
  const physical = usePhysicalMission();
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('simulation');
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
    if (current.current?.approved && !terminalStates.has(current.current.state)) return;
    if (physicalAvailable(physical.status) && physical.connected) {
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
    if (mapSnapshot?.destinations.length) setDraft(value => value || destinationGoal(mapSnapshot, mapSnapshot.destinations[0]));
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
    if (physicalBusy || physicalUnconfirmed === kind || view === 'Replay' || !physical.status) return;
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
  const robotStatusDialog = robotMode || modal === 'robot';
  const robotMission = robotMode && (robotRunning || physicalMatchesPlan(physical.status, workspace));
  const robotFinished = robotMission && physicalFinished(physical.status);
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
  const title = workspace?.planning_pending ? 'Planning from the live view.' : state === 'IDLE' ? 'Ready for a goal.' : state === 'WAITING_SIGNAL' ? 'Waiting for green.' : state === 'COMPLETED' ? 'Destination verified.' : state === 'REVIEW_REQUIRED' ? 'Review the result.' : `Route to ${destinationName}`;
  const completedSteps = robotMission ? physical.status?.progress.completed ?? 0 : workspace?.plan?.steps.filter(step => step.status === 'complete').length ?? 0;
  const totalSteps = robotMission ? physical.status?.progress.total ?? 0 : workspace?.plan?.steps.length ?? 0;
  const robotStatusTitle = physicalTitle(physical.status, physical.connected);
  const signalScanning = robotMode ? physicalVisionActive(physical.status, physical.connected, 'signal') : localVisionRequest === 'signal';
  const carScanning = robotMode ? physicalVisionActive(physical.status, physical.connected, 'car') : localVisionRequest === 'car' || localVisionRequest === 'plan';
  const robotStatusDetail = physicalDetail(physical.status, physical.connected);
  const robotDestinationBlocker = physicalDestinationBlocker(physical.status, workspace?.plan?.route.destination, destinationName);
  const robotCanStart = robotMode && physical.connected && physicalAvailable(physical.status) && physical.status?.robot.connected && physical.status.robot.stationary && !physicalUnconfirmed
    && !robotRunning && !robotFinished && !robotDestinationBlocker && liveBacked && workspace?.goal?.provider === 'meta' && state === 'PLAN_READY';
  const robotCheckUsesStatus = robotMission || !physical.connected || !physicalAvailable(physical.status);
  const robotCheckTitle = robotCheckUsesStatus ? robotStatusTitle : state === 'PLAN_READY'
    ? robotDestinationBlocker ? 'Destination unavailable' : 'Ready for your approval' : 'Ready for a goal';
  const robotCheckDetail = robotCheckUsesStatus ? robotStatusDetail : state === 'PLAN_READY'
    ? robotDestinationBlocker ?? (!liveBacked || workspace?.goal?.provider !== 'meta'
      ? 'Create a MUSE plan from the live view to start the robot.'
      : 'Start once. The executor handles movement, signal waits, parking and return.')
    : 'Choose a destination and review the MUSE route.';
  const robotSource = robotMode ? !physical.connected ? 'Robot status unavailable'
    : physical.status?.robot.connected ? 'Physical robot · autonomous execution' : 'Physical robot · disconnected'
    : physical.status?.enabled && !physical.status.available ? 'Simulation · robot not available' : 'Simulation · no physical motion';

  function renderPrimaryAction() {
    if (!workspace) return <button className="primary-button" disabled>Connecting to workspace…</button>;
    if (robotMode && robotMission) {
      if (robotFinished) return <button className="primary-button" disabled={physicalBusy || busy || !online || !physical.connected || !physical.status?.robot.stationary} onClick={() => void command('reset')}><Icon name="refresh"/>Plan the next mission</button>;
      return <button className="primary-button physical-stop" disabled={physicalBusy || physicalUnconfirmed === 'stop'} onClick={() => void physicalCommand('stop')}><Icon name="pause"/>{physicalBusy ? 'Sending request…' : physical.status?.state === 'STOPPING' || physicalUnconfirmed === 'stop' ? 'Stop requested' : 'Stop robot mission'}</button>;
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
  const contextStart = Math.max(0, Math.min(workspace?.current_step ?? 0, steps.length - 3));
  const visibleSteps = steps.slice(contextStart, contextStart + 3);
  const inspection = sceneSnapshot?.inspection;
  const modelLabel = actionReviewPending ? 'Reviewing images' : workspace?.review ? workspace.review.verdict : inspection?.verdict ?? 'No image review';
  const openImageTools = () => { setModal(null); setView('Workspace'); window.setTimeout(() => setImageToolsRequest(value => value + 1), 0); };
  const openGoal = () => { setGoalMode(canEditGoal ? 'text' : 'query'); setView('Workspace'); setModal('goal'); };
  const openVoice = () => { setGoalMode('voice'); setView('Workspace'); setModal('goal'); };
  const openQuery = () => { setGoalMode(workspace?.goal ? 'query' : 'text'); setView('Workspace'); setModal('goal'); };

  return <div className="app-shell">
    <aside className="side-rail" aria-label="Workspace tools">
      <a className="brand" href="#workspace" aria-label="PushPilot workspace" onClick={event => { event.preventDefault(); setView('Workspace'); }}><BrandMark/></a>
      <span className="rail-section-label">MAIN</span>
      <button title="Workspace" aria-label="Workspace" className={view === 'Workspace' ? 'active' : ''} onClick={() => setView('Workspace')}><Icon name="home"/></button>
      <button title="Route plan" aria-label="Route plan" className={view === 'Plan' ? 'active' : ''} onClick={() => setView('Plan')}><Icon name="route"/></button>
      <button title="Replay" aria-label="Evidence replay" className={view === 'Replay' ? 'active' : ''} onClick={() => setView('Replay')}><Icon name="clock"/></button>
      <button title={robotMode || physical.status?.enabled ? 'Robot status' : 'Simulation inputs'} aria-label={robotMode || physical.status?.enabled ? 'Robot status' : 'Simulation inputs'} onClick={() => robotMode || physical.status?.enabled ? setModal('robot') : setShowDemo(true)}><Icon name="settings"/></button>
      <div className="rail-bottom"><span/><button title="Future glasses companion" aria-label="Glasses concept" onClick={() => setModal('companion')}><Icon name="glasses"/></button><small>0.1</small></div>
    </aside>
    <header className="topbar">
      <div className="header-title"><strong>PushPilot</strong><span>/</span><h1>Workspace</h1></div>
      <nav className="topnav" aria-label="Main navigation">{(['Workspace', 'Plan', 'Replay'] as View[]).map(tab => <button className={view === tab ? 'active' : ''} key={tab} onClick={() => setView(tab)} aria-current={view === tab ? 'page' : undefined}>{tab}</button>)}</nav>
      <div className="header-status"><span className="backend-status"><i className={(robotMode ? physical.connected : online) ? 'online' : ''}/>{(robotMode ? physical.connected : online) ? 'Connected' : 'Offline'}</span><select className="mode-label" aria-label="Execution mode" value={robotMode ? 'physical' : 'simulation'} disabled={robotRunning || physicalBusy || Boolean(physicalUnconfirmed) || busy || actionReviewPending || active} onChange={event => { modeChosen.current = true; setExecutionMode(event.target.value as ExecutionMode); if (event.target.value === 'physical') setProvider('meta'); }}><option value="simulation">Simulation</option><option value="physical" disabled={!physical.connected || !physicalAvailable(physical.status)}>Robot{!physicalAvailable(physical.status) ? ' unavailable' : ''}</option></select><button className="header-concept" aria-label="Glasses companion concept" onClick={() => setModal('companion')}><Icon name="glasses" size={18}/><span>Companion concept</span></button></div>
    </header>
    <main className={`workspace-stage ${mobileMission ? 'mission-visible' : ''}`}>
      <MapScene presentation="stage" workspace={workspace} physicalLabel={robotMission ? robotStatusTitle : undefined} onSnapshot={setSceneSnapshot} onMapSnapshot={setMapSnapshot} onPreviewSource={setPreviewSource} readOnly={actionReviewPending || robotRunning || physicalBusy} openToolsRequest={imageToolsRequest}/>
      <div className="scene-heading"><div className="scene-context"><span>Temporary workspace</span><h2 title={mapSnapshot?.title}>{mapSnapshot?.title ?? 'Loading map…'}</h2></div><GoalIntentBar query={workspace?.goal?.text ?? null} source={workspace?.goal?.source ?? null} onQuery={openQuery} onVoice={openVoice}/></div>
      <button className="mobile-mission-switch glass-surface" onClick={() => setMobileMission(value => !value)} aria-expanded={mobileMission}>{mobileMission ? 'Show scene' : 'Mission'}<Icon name={mobileMission ? 'close' : 'chevron'} size={16}/></button>
      {(error || !online) && <div className={`stage-notice ${error ? 'error' : ''}`} role={error ? 'alert' : 'status'}><Icon name="shield" size={17}/><span>{error || 'Backend unavailable. Refresh before taking action.'}</span><button aria-label={error ? 'Dismiss error' : 'Retry connection'} onClick={() => error ? setError('') : void refresh()}><Icon name={error ? 'close' : 'refresh'} size={16}/></button></div>}

      <aside className="floating-mission glass-surface" aria-label="Mission and execution controls">
        <div className="mission-heading"><span><i/>Active mission</span><button className="icon-button" onClick={openGoal} disabled={!canEditGoal} aria-label="Edit mission goal"><Icon name="settings" size={17}/></button></div>
        <div className="mission-intro"><span className="mission-provider">{robotMode ? 'MUSE · physical robot mission' : liveBacked ? 'MUSE · live image + road graph' : workspace?.goal?.provider === 'meta' ? 'MUSE interpretation' : 'Demo interpretation'}</span><h2 title={destinationName}>{workspace?.planning_pending ? 'Planning…' : state === 'IDLE' && !robotMission ? 'Where to next?' : `To ${destinationName}`}</h2><div className="mission-journey"><span title={startName}>{startName}</span><Icon name="arrow" size={18}/><strong title={destinationName}>{destinationName}</strong></div></div>
        <div className="mission-progress"><div><span>Mission progress</span><strong>{completedSteps}<small> / {totalSteps} actions</small></strong></div><progress aria-label="Completed mission actions" value={completedSteps} max={totalSteps || 1}/></div>
        <section className="mission-context"><div className="section-caption"><h3>{robotMode ? 'Planned route' : 'Route sequence'}</h3><button onClick={() => setView('Plan')} aria-label="View full route">View all<Icon name="chevron" size={13}/></button></div>
          {visibleSteps.length ? <ol className="context-steps" aria-label="Current route context">{visibleSteps.map((step, index) => <li key={step.id} className={`${step.status} ${workspace?.current_step === contextStart + index ? 'focused' : ''}`}><span className="context-number">{step.status === 'complete' ? <Icon name="check" size={12}/> : String(contextStart + index + 1).padStart(2, '0')}</span><div><strong>{planStepLabel(mapSnapshot, step)}</strong><small>{stepDescriptions[step.kind]}</small></div></li>)}</ol> : <p className="empty-copy">Choose a destination from the selected map to build a route.</p>}
        </section>
        <section className={`next-check ${robotMode ? 'physical-check' : ''}`} aria-live="polite"><div><Icon name={(robotMode ? physical.status?.signal.waiting : state === 'WAITING_SIGNAL') ? 'pause' : 'shield'} size={16}/><h3>{robotMode ? robotCheckTitle : stateLabels[state]}</h3></div><p title={robotMode ? robotCheckDetail : undefined}>{robotMode ? robotCheckDetail : workspace?.next_check ?? 'Set a goal and inspect the proposed route.'}</p>{robotMode && <button className="physical-detail-link" onClick={() => setModal('robot')}>Robot status<Icon name="chevron" size={12}/></button>}</section>
        <div className="mission-actions">{renderPrimaryAction()}{!robotMode && signalWatchRunning && <button className="secondary-button" disabled={busy || !online} onClick={() => void command('live-signals/watch/stop')}>Stop signal watch<Icon name="pause" size={16}/></button>}{!robotMode && state === 'WAITING_SIGNAL' && !liveBacked && <button className="secondary-button" onClick={() => setShowDemo(true)}>Signal controls<Icon name="chevron" size={16}/></button>}{state === 'PLAN_READY' && !robotMission && <button className="edit-goal-link" disabled={!canEditGoal} onClick={openGoal}>Edit goal</button>}{!robotMode && pendingReview && !liveBacked && <button className="edit-goal-link" onClick={() => setShowDemo(true)}>Demo review inputs</button>}{!robotMode && (active || workspace?.planning_pending) && <button className="cancel-button" disabled={(busy && !actionReviewPending) || !online} onClick={() => void command('cancel')}>End simulation</button>}<span className="execution-source">{robotSource}</span></div>
      </aside>

      <div className="status-dock" aria-label="Workspace status">
        <button className="status-card glass-surface" onClick={() => setView('Plan')}><span className="status-card-top"><i className="accent-dot"/>Route overview<Icon name="chevron" size={14}/></span><span className="status-card-value">{drawingDistance(route?.distance_mm)}<small>drawing mm</small></span><span className="status-card-bottom">{route?.junction_ids.length ?? '—'} junction checks<span>{completedSteps}/{totalSteps} actions</span></span></button>
        <button className={`status-card glass-surface ${signalScanning ? 'is-scanning' : ''} signal-${robotMode ? physical.connected ? physical.status?.signal.color.toLowerCase() ?? 'unknown' : 'unknown' : admittedCrossing ? 'green' : signalReading}`} onClick={() => robotMode ? setModal('robot') : liveBacked ? setView('Replay') : setShowDemo(true)}><span className="status-card-top"><i/>Signal {signalJunction ? `· ${nodeLabel(mapSnapshot, signalJunction)}` : ''}<Icon name="chevron" size={14}/></span><span className="status-card-value">{robotMode ? physicalSignalLabel(physical.status, physical.connected) : signalScanning ? 'Checking signal · MUSE' : signalCardLabel}</span><span className="status-card-bottom">{robotMode ? signalScanning ? 'Reading a fresh camera image' : physical.status?.signal.waiting ? 'Automatic continuation on fresh green' : 'Full stop before the signal check' : admittedCrossing ? 'Accepted entry · review required' : workspace?.stopped ? 'Simulated stop confirmed' : 'Mandatory stop before entry'}<span>{robotMode ? 'Robot' : 'Simulation'}</span></span></button>
        <button className={`status-card glass-surface ${carScanning ? 'is-scanning' : ''}`} onClick={() => robotMode ? setModal('robot') : workspace?.review ? setModal('review') : openImageTools()}><span className="status-card-top"><i className="model-dot"/>{carScanning ? 'MUSE visual check' : robotMode ? 'Delivery and parking' : 'Visual review'}<Icon name="chevron" size={14}/></span><span className="status-card-value model-value">{robotMode ? !physical.connected ? 'Status unavailable' : carScanning ? 'Checking car · MUSE' : physical.status?.returning_home && !['HOLD', 'HELD', 'STOPPING', 'COMPLETE', 'COMPLETED', 'CANCELLED', 'FAILED', 'FAULT'].includes(physical.status.state) ? 'Returning to start' : physical.status?.car.arrived ? physical.status.car.aligned ? 'Parked and aligned' : 'Arrival confirmed' : physical.status?.state === 'ALIGNING' ? 'Aligning the car' : 'Arrival pending' : localVisionRequest === 'plan' ? 'Planning route · MUSE' : localVisionRequest === 'car' ? 'Checking images · MUSE' : modelLabel === 'USABLE' ? 'Scene inspected' : modelLabel}</span><span className="status-card-bottom">{robotMode ? carScanning ? 'Reading a fresh camera image' : physical.status?.car.arrived && !physical.status.car.aligned ? 'Parking alignment not yet confirmed' : 'Car arrival and robot return tracked separately' : workspace?.review ? liveBacked ? liveReviewEvidence ? 'MUSE · native live pair' : 'Native pair pending' : workspace.review.source === 'meta' ? 'MUSE · recorded pair' : 'Demo action review' : inspection ? 'MUSE · recorded scene' : 'Awaiting image evidence'}<span>{robotMode ? 'Robot' : workspace?.review ? 'Action' : 'Scene'}</span></span></button>
      </div>
      <div className="stage-bottom-line"><span>{previewSource ?? sceneSnapshot?.frame?.source ?? 'No image'} · {robotMode ? 'Planned route · robot status in mission panel' : 'car pose unmeasured'}</span><span>{robotMode ? `Robot revision ${physical.status?.revision ?? '—'}` : workspace ? `Session revision ${workspace.revision}` : 'Offline'}</span></div>
    </main>

    <ViewportDialog open={modal === 'goal'} title="Mission goal" subtitle="SET THE INTENT" onClose={() => setModal(null)} className="goal-dialog">
      <nav className="goal-modal-tabs" role="tablist" aria-label="Goal input sections"><button role="tab" aria-selected={goalMode === 'text'} disabled={!canEditGoal} onClick={() => setGoalMode('text')}>Type a goal</button><button role="tab" aria-selected={goalMode === 'voice'} onClick={() => setGoalMode('voice')}><Icon name="mic" size={15}/>Voice input</button>{workspace?.goal && <button role="tab" aria-selected={goalMode === 'query'} onClick={() => setGoalMode('query')}>Original query</button>}</nav>
      <div className="goal-mode-panel" role="tabpanel" aria-label={goalMode === 'voice' ? 'Voice input options' : goalMode === 'query' ? 'Original user query' : 'Typed goal input'}>
      {goalMode === 'voice' ? <VoiceInputOptions canEdit={canEditGoal} onContinue={() => setGoalMode(canEditGoal ? 'text' : 'query')}/>
        : goalMode === 'query' ? <section className="original-query-panel"><div className="original-query-source"><Icon name={workspace?.goal?.source === 'voice' ? 'mic' : 'text'} size={16}/><span>{workspace?.goal?.source === 'voice' ? 'Voice input' : 'Typed input'} · original request</span></div><TextPages text={workspace?.goal?.text ?? 'No submitted goal yet.'} size={220}/><footer><span>{canEditGoal ? 'Your original words, saved with this plan.' : 'The active goal is read-only during execution.'}</span>{canEditGoal && <button className="secondary-button" onClick={() => setGoalMode('text')}>Edit goal<Icon name="arrow" size={16}/></button>}</footer></section>
        : <form className="goal-form" onSubmit={event => { event.preventDefault(); if (canEditGoal && draft.trim()) { void command('goals', { text: draft, provider, source: 'typed' }); setModal(null); } }}>
        <div className="goal-choices"><div className="goal-destinations">{goalChoices.items.map(place => <button type="button" key={place.id} title={`${place.label} · ${place.id}`} disabled={!canEditGoal} onClick={() => mapSnapshot && setDraft(destinationGoal(mapSnapshot, place.id))}><span>{place.label}</span><Icon name="arrow" size={16}/></button>)}</div>{goalChoices.pages > 1 && <nav className="goal-choice-pager" aria-label="Destination pages"><button type="button" disabled={goalChoices.page === 0} onClick={() => setGoalPage(value => value - 1)} aria-label="Previous destinations"><Icon name="chevron" className="reverse" size={14}/></button><span>{goalChoices.page + 1} / {goalChoices.pages}</span><button type="button" disabled={goalChoices.page + 1 >= goalChoices.pages} onClick={() => setGoalPage(value => value + 1)} aria-label="Next destinations"><Icon name="chevron" size={14}/></button></nav>}</div>
        <label htmlFor="goal-input">Your goal<input ref={goalInput} id="goal-input" value={draft} onChange={event => setDraft(event.target.value)} disabled={!canEditGoal} maxLength={500} aria-label="Your mission goal"/></label>
        <label htmlFor="provider-mode">Goal interpreter<select id="provider-mode" value={provider} disabled={!canEditGoal} onChange={event => setProvider(event.target.value as ProviderMode)}><option value="demo" disabled={robotMode}>Demo interpreter</option><option value="meta" disabled={!workspace?.capabilities.muse_configured}>MUSE · Meta API{!workspace?.capabilities.muse_configured ? ' (not configured)' : ''}</option></select></label>
        <button className="goal-voice-shortcut" type="button" onClick={() => setGoalMode('voice')}><Icon name="mic" size={16}/><span>Voice input</span><small>Not connected</small><Icon name="chevron" size={14}/></button>
        <div className="dialog-bottom"><span>A new plan requires explicit approval.</span><button className="primary-button" type="submit" disabled={!canEditGoal || !draft.trim()}><Icon name="spark" size={17}/>Create a plan<Icon name="arrow" size={17}/></button></div>
      </form>}
      </div>
    </ViewportDialog>
    <ViewportDialog open={view === 'Plan'} title="Route plan" subtitle="INSPECT THE SEQUENCE" onClose={() => setView('Workspace')}><PlanBrowser workspace={workspace} map={mapSnapshot} physical={robotMode}/></ViewportDialog>
    <ViewportDialog open={view === 'Replay' && modal !== 'review'} title="Decision replay" subtitle="SOURCE-LABELLED EVIDENCE" onClose={() => setView('Workspace')}><EvidenceBrowser events={workspace?.events ?? []} selected={selected} onSelect={setSelectedEvent} onOpenRecord={() => setModal('review')}/></ViewportDialog>
    <ViewportDialog open={modal === 'review'} title={view === 'Replay' ? replayLiveEvidence ? 'Live image evidence' : 'Recorded evidence' : 'Visual action review'} subtitle={view === 'Replay' ? 'READ-ONLY REPLAY' : 'COMPARE EXPECTED AND OBSERVED'} onClose={() => setModal(null)} className="review-dialog">
      {error && <div className="dialog-error" role="alert"><Icon name="shield" size={17}/><span>{error}</span><button aria-label="Dismiss review error" onClick={() => setError('')}><Icon name="close" size={16}/></button></div>}
      {view === 'Replay' && replayLiveEvidence ? <LiveEvidence key={replayLiveEvidence.id} evidence={replayLiveEvidence}/>
        : view !== 'Replay' && liveBacked ? pendingReview ? <section className="ar-workspace" aria-label="Live action review"><header className="ar-heading"><div><span className="ar-eyebrow">Server-bound native image pair</span><h2>Review live images</h2></div><span className="ar-source">MUSE · simulation only</span></header><section className="ar-stage ar-result"><TextPages text={`${workspace?.review?.expected ?? 'Inspect the current action.'}\n\nThe backend retains the original BEFORE image and selects a new AFTER image. MUSE reviews the visible result; a simulated action receipt does not prove real vehicle motion.`} size={380}/><button className="ar-review-submit" disabled={busy || actionReviewPending || !online} onClick={() => void command('live-actions/reviews', { review_id: workspace!.review!.id, expected_visual: workspace!.review!.expected })}>{actionReviewPending ? 'MUSE is reviewing…' : 'Review live images'}<Icon name="arrow" size={18}/></button></section><p className="ar-authority"><Icon name="shield" size={15}/><span>Native camera images · no physical motion authority</span></p></section>
          : liveReviewEvidence ? <LiveEvidence key={liveReviewEvidence.id} evidence={liveReviewEvidence}/>
            : <section className="ar-workspace"><TextPages text="Run an approved simulated action to capture its native BEFORE image and request a new AFTER-image review. No action has been physically executed."/></section>
        : <ActionReviewPanel workspace={workspace} scene={sceneSnapshot} online={online} pending={actionReviewPending} busy={busy} readOnly={view === 'Replay'} replayEvidence={replayRecordedEvidence} onReview={reviewRecordedAction} onOpenTools={openImageTools}/>}
    </ViewportDialog>
    <ViewportDialog open={showDemo || modal === 'robot'} title={robotStatusDialog ? 'Robot status' : 'Simulation inputs'} subtitle={robotStatusDialog ? 'PHYSICAL MISSION' : 'OPERATOR-INJECTED DEMO DATA'} onClose={() => { setShowDemo(false); if (modal === 'robot') setModal(null); }} className="simulation-dialog">{robotStatusDialog ? <PhysicalStatusPanel status={physical.status} connected={physical.connected} map={mapSnapshot}/> : <div className="simulation-body" id="simulation-controls"><section><span className="form-eyebrow">PAPER SIGNAL STAND-IN</span><h3>{signalJunction ? `Junction ${signalJunction}` : 'Current junction'}</h3><p>{liveBacked ? 'This live-backed plan uses a fresh post-stop MUSE judgment. Manual signal inputs are disabled.' : 'Each fresh observation applies to one junction. A full stop is required before entry.'}</p><div className="signal-buttons">{(['RED', 'GREEN', 'UNKNOWN'] as SignalColor[]).map(color => <button key={color} className={`signal-option ${color.toLowerCase()} ${signal === color ? 'selected' : ''}`} disabled={liveBacked || busy || actionReviewPending || !online || !workspace || view === 'Replay'} onClick={() => void command('signal', { color })}><i/>{color[0] + color.slice(1).toLowerCase()}</button>)}</div></section><section><span className="form-eyebrow">ACTION REVIEW STAND-IN</span><h3>Demo verdict</h3><p>{liveBacked ? 'Native BEFORE and AFTER images are reviewed by MUSE. Demo verdicts cannot advance this plan.' : 'These explicit operator inputs are labelled demo. Actual MUSE review uses recorded image pairs.'}</p><div className="review-buttons">{(['PASS', 'REOBSERVE', 'UNKNOWN', 'FAIL'] as ReviewVerdict[]).map(verdict => <button key={verdict} disabled={liveBacked || !pendingReview || busy || actionReviewPending || !online || view === 'Replay'} onClick={() => void command('reviews', { review_id: workspace!.review!.id, verdict })}>{verdict === 'REOBSERVE' ? 'Re-observe' : verdict[0] + verdict.slice(1).toLowerCase()}</button>)}</div></section></div>}</ViewportDialog>
    <ViewportDialog open={modal === 'companion'} title="A shared perspective." subtitle="FUTURE GLASSES COMPANION" onClose={() => setModal(null)} className="companion-dialog"><div className="companion-concept"><span className="concept-pill">Concept · hardware not connected</span><h3>Look.<br/>Ask.<br/>Review.</h3><p>A future wearable view can bring the same scene, intent and reviewable plan into the operator's perspective.</p><div className="concept-sequence"><span>See the workspace</span><Icon name="arrow" size={18}/><span>State the goal</span><Icon name="arrow" size={18}/><span>Review on tablet</span></div><small>Wearable capture, voice and display integration require separate validation.</small></div></ViewportDialog>
  </div>;
}
