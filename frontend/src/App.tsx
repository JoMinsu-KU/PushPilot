import { useCallback, useEffect, useRef, useState } from 'react';
import type { EvidenceEvent, ProviderMode, ReviewVerdict, SignalColor, WorkspaceSnapshot } from '../../contracts/workspace';
import type { SceneSnapshot } from '../../contracts/scene';
import type { RecordedActionReviewCommand } from '../../contracts/action-review';
import { BrandMark, Icon, type IconName } from './Icons';
import { GlassesArt } from './Scene';
import { MapScene } from './MapScene';
import { createRequestId } from './requestId';
import { ActionReviewPanel } from './ActionReview';

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
function readableError(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && 'message' in value && typeof value.message === 'string') return value.message;
  return 'The request could not be completed. Refresh the state and try again.';
}
function timeLabel(at: string) {
  const date = new Date(at);
  return Number.isNaN(date.valueOf()) ? at : date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}
function SourcePill({ children, status = 'neutral' }: { children: React.ReactNode; status?: 'neutral' | 'cyan' | 'green' | 'amber' }) {
  return <span className={`source-pill ${status}`}><span/>{children}</span>;
}
function ActionLoop({ workspace }: { workspace: WorkspaceSnapshot | null }) {
  const phase = !workspace || workspace.state === 'IDLE' ? 0 : workspace.state === 'PLAN_READY' ? 2 : workspace.state === 'COMPLETED' ? 4 : workspace.state === 'REVIEW_REQUIRED' || workspace.state === 'REOBSERVE' ? 4 : 3;
  return <section className="panel loop-card" aria-label="Mission action loop">
    <div className="card-heading"><span className="card-status-dot"/><h2>Action loop</h2><span>Simulation</span></div>
    <div className="loop-illustration"><div><Icon name="car" size={26}/><span>Push</span></div><Icon name="arrow" className="loop-arrow"/><div><Icon name="pause" size={26}/><span>Stop</span></div><Icon name="arrow" className="loop-arrow"/><div><Icon name="eye" size={26}/><span>Observe</span></div></div>
    <div className="phase-track">{['Observe', 'Plan', 'Approve', 'Act', 'Verify'].map((label, index) => <div key={label} className={index <= phase ? 'reached' : ''}><span className={index === phase ? 'current' : ''}/><small>{label}</small></div>)}</div>
  </section>;
}
function RouteSummary({ workspace }: { workspace: WorkspaceSnapshot | null }) {
  const route = workspace?.plan?.route;
  const label = route ? route.destination[0] + route.destination.slice(1).toLowerCase() : 'Little Town';
  const complete = workspace?.plan?.steps.filter(step => step.status === 'complete').length ?? 0;
  const total = workspace?.plan?.steps.length ?? 0;
  return <section className="panel route-summary-card" aria-label="Route overview">
    <div className="card-heading"><span className="card-status-dot orange"/><h2>Route overview</h2><span>Temporary map</span></div>
    <div className="route-summary-body"><div><h3>{label}</h3><p>{route ? `${route.start} → ${route.destination}` : 'Create a plan to explore a route.'}</p></div><CarModelArt/></div>
    <div className="route-summary-stats"><span><strong>{route?.distance_mm ?? '—'}</strong> Drawing mm</span><span><strong>{route?.junction_ids.length ?? '—'}</strong> Junctions</span><span><strong>{complete}/{total}</strong> Actions</span></div>
  </section>;
}
function CarModelArt() {
  return <svg className="car-model-art" viewBox="0 0 156 88" role="img" aria-label="Illustration of the wheel-less surface-push car">
    <ellipse cx="78" cy="73" rx="65" ry="8" fill="#e7e8eb"/>
    <path d="m12 46 29-9 19-20 42-4 25 19 16 8 1 22-88 18-44-19Z" fill="#e1e3e6" stroke="#bcc1c7" strokeWidth=".8"/>
    <path d="m12 46 41 14 91-20-17-8-25-19-42 4-19 20Z" fill="#fafbfc" stroke="#c9cdd2" strokeWidth=".8"/>
    <path d="m53 60 91-20v22L56 80Z" fill="#d6d9de" stroke="#b9bec6" strokeWidth=".8"/>
    <path d="m44 38 17-19 38-4 23 18-68 15Z" fill="#eef0f2" stroke="#c9cdd3" strokeWidth=".8"/>
    <path d="m61 21 2 14 49-10m-30-7 1 13" stroke="#d3d7dd" fill="none" strokeWidth="1"/>
    <path d="m21 47 32 11 79-17" fill="none" stroke="#fff" strokeWidth="2"/>
    <path d="m63 67 24-5m30-7 16-4" fill="none" stroke="#bec4cc" strokeWidth="1.5"/>
  </svg>;
}
function PlanList({ workspace, expanded = false }: { workspace: WorkspaceSnapshot | null; expanded?: boolean }) {
  const listRef = useRef<HTMLOListElement>(null);
  const currentStepId = workspace?.plan?.steps.find(step => step.status === 'current')?.id;
  useEffect(() => {
    if (expanded) return;
    const list = listRef.current;
    const item = list?.querySelector<HTMLElement>('[data-current-step="true"]');
    if (!list || !item) return;
    const top = item.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop;
    const bottom = top + item.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight;
  }, [currentStepId, expanded, workspace?.plan?.id]);
  return <ol ref={listRef} className={`plan-list ${expanded ? 'expanded' : ''}`} tabIndex={expanded ? undefined : 0} aria-label="Route steps">
    {(workspace?.plan?.steps ?? [
      { id: 'push', label: 'Approach the intersection', description: 'Bounded surface push from PIZZA.', kind: 'PUSH', status: 'pending' },
      { id: 'stop', label: 'Stop and check the signal', description: 'Mandatory stop, including on green.', kind: 'STOP', status: 'pending' },
      { id: 'cross', label: 'Cross on fresh green', description: 'Accepted checks permit automatic entry.', kind: 'CROSS', status: 'pending' },
      { id: 'verify', label: 'Verify the destination', description: 'Review the expected arrival at BAKERY.', kind: 'VERIFY', status: 'pending' },
    ]).map((step, index) => <li key={step.id} className={`plan-step ${step.status}`} data-current-step={step.status === 'current' ? 'true' : undefined}>
      <span className="step-number">{step.status === 'complete' ? <Icon name="check" size={14}/> : String(index + 1).padStart(2, '0')}</span>
      <span className="step-icon"><Icon name={stepIcons[step.kind] ?? 'route'} size={24}/></span>
      <span className="step-copy"><strong>{step.label}</strong><small>{expanded ? step.description : stepDescriptions[step.kind] ?? step.description}</small></span>
      {step.status === 'current' && <span className="step-current" aria-label="Current step"/>}
    </li>)}
  </ol>;
}
function EvidenceTimeline({ events, selected, onSelect }: { events: EvidenceEvent[]; selected: string | null; onSelect: (id: string) => void }) {
  return <div className="evidence-timeline">{events.length === 0 ? <div className="empty-evidence"><Icon name="clock" size={36}/><h3>Your evidence starts here.</h3><p>Goals, approvals, observations and decisions appear in the immutable timeline.</p></div> : [...events].reverse().map(event => <button key={event.id} className={`evidence-event ${selected === event.id ? 'selected' : ''}`} onClick={() => onSelect(event.id)}><span className="event-dot"/><span><span className="event-top"><small>#{String(event.sequence).padStart(3, '0')}</small><time>{timeLabel(event.at)}</time></span><strong>{event.title}</strong><span className="event-detail">{event.detail}</span><span className="event-source">{event.source} <span>·</span> {stateLabels[event.state] ?? event.state}</span></span><Icon name="chevron" size={16}/></button>)}</div>;
}

export function App() {
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [view, setView] = useState<View>('Workspace');
  const [draft, setDraft] = useState('Push the car from Pizza to the Bakery.');
  const [provider, setProvider] = useState<ProviderMode>('demo');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [online, setOnline] = useState(false);
  const [showDemo, setShowDemo] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [sceneSnapshot, setSceneSnapshot] = useState<SceneSnapshot | null>(null);
  const [actionReviewPending, setActionReviewPending] = useState(false);
  const [imageToolsRequest, setImageToolsRequest] = useState(0);
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
  useEffect(() => {
    if (showDemo && view !== 'Replay') document.getElementById('simulation-controls')?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
  }, [showDemo, view]);

  async function command(endpoint: string, data: Record<string, unknown> = {}) {
    const snapshot = current.current;
    if (!snapshot || busy || view === 'Replay' || (actionReviewPending && endpoint !== 'cancel')) return;
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/v1/${endpoint}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: createRequestId(), expected_revision: snapshot.revision, ...data }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        if (response.status === 409) { await refresh(); throw new Error('The mission state changed. Review the current state before trying again.'); }
        const detail = payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : payload;
        throw new Error(readableError(detail));
      }
      applySnapshot(payload as WorkspaceSnapshot);
    } catch (err) { setError(err instanceof Error ? err.message : 'Connection interrupted. Refresh the workspace before continuing.'); }
    finally { setBusy(false); }
  }
  async function reviewRecordedAction(data: Omit<RecordedActionReviewCommand, 'request_id' | 'expected_revision'>) {
    const snapshot = current.current;
    if (!snapshot || busy || actionReviewPending || view === 'Replay') return;
    setActionReviewPending(true); setError('');
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
    finally { setActionReviewPending(false); }
  }
  const state = workspace?.state ?? 'IDLE';
  const canEditGoal = Boolean(workspace && ['IDLE', 'PLAN_READY'].includes(state) && online && !busy && !actionReviewPending);
  const active = Boolean(workspace?.approved && !terminalStates.has(state));
  const selected = workspace?.events.find(event => event.id === selectedEvent) ?? workspace?.events.at(-1);
  const signal = workspace?.signal.color ?? 'UNKNOWN';
  const pendingReview = workspace?.review?.verdict === 'PENDING';
  const destination = workspace?.goal?.destination ?? 'BAKERY';
  const destinationName = destination[0] + destination.slice(1).toLowerCase();
  const currentStep = workspace?.plan?.steps[workspace.current_step];
  const signalJunction = workspace?.signal.junction_id ?? (currentStep?.kind === 'STOP' ? currentStep.node_id : null);
  const title = state === 'IDLE' ? 'Ready for a goal.' : state === 'WAITING_SIGNAL' ? 'Waiting for green.' : state === 'COMPLETED' ? 'Destination verified.' : state === 'REVIEW_REQUIRED' ? 'Review the result.' : `Route to ${destinationName}`;
  const completedSteps = workspace?.plan?.steps.filter(step => step.status === 'complete').length ?? 0;
  const totalSteps = workspace?.plan?.steps.length ?? 0;

  function renderPrimaryAction() {
    if (!workspace) return <button className="primary-button" disabled>Connecting to workspace…</button>;
    if (state === 'IDLE') return <button className="primary-button" disabled={!canEditGoal || !draft.trim()} onClick={() => void command('goals', { text: draft, provider, source: 'typed' })}><Icon name="spark"/>Create a plan<Icon name="arrow"/></button>;
    if (state === 'PLAN_READY') return <button className="primary-button" disabled={busy || actionReviewPending || !online} onClick={() => void command('approve', { plan_id: workspace.plan!.id, plan_revision: workspace.plan!.revision })}>Approve simulation<Icon name="arrow"/></button>;
    if (state === 'READY') return <button className="primary-button" disabled={busy || actionReviewPending || !online} onClick={() => void command('advance')}><Icon name="play"/>Run next simulated action<Icon name="arrow"/></button>;
    if (state === 'REOBSERVE') return <button className="primary-button" disabled={busy || actionReviewPending || !online} onClick={() => void command('reobserve')}><Icon name="refresh"/>Open a new observation review</button>;
    if (terminalStates.has(state)) return <button className="primary-button" disabled={busy || actionReviewPending || !online} onClick={() => void command('reset')}><Icon name="refresh"/>Start a new simulation</button>;
    if (state === 'WAITING_SIGNAL') return <div className="waiting-message"><Icon name="pause" size={22}/><span>Waiting for a fresh green signal.<small>Accepted checks allow automatic entry.</small></span></div>;
    return <button className="primary-button" disabled><Icon name="eye"/>Review the action result</button>;
  }

  return <div className="app-shell">
    <aside className="side-rail" aria-label="Workspace tools">
      <a className="brand" href="#workspace" onClick={event => { event.preventDefault(); setView('Workspace'); }} aria-label="PushPilot workspace"><BrandMark/><span className="sr-only">PushPilot</span></a>
      <span className="rail-section-label">MAIN</span>
      <button title="Workspace" aria-label="Workspace" className={view === 'Workspace' ? 'active' : ''} onClick={() => setView('Workspace')}><Icon name="home"/><span>Workspace</span></button>
      <button title="Mission plan" aria-label="Mission plan" className={view === 'Plan' ? 'active' : ''} onClick={() => setView('Plan')}><Icon name="route"/><span>Plan</span></button>
      <button title="Voice capture is not connected in this build" aria-label="Voice unavailable" disabled><Icon name="mic"/><span>Voice</span></button>
      <button title="Evidence replay" aria-label="Evidence replay" className={view === 'Replay' ? 'active' : ''} onClick={() => setView('Replay')}><Icon name="clock"/><span>Replay</span></button>
      <button title="Simulation inputs" aria-label="Simulation inputs" className={showDemo ? 'active' : ''} onClick={() => setShowDemo(value => !value)} aria-expanded={showDemo} aria-controls="simulation-controls"><Icon name="settings"/><span>Demo</span></button>
      <div className="rail-bottom"><span className="rail-line"/><Icon name="glasses" size={21}/><span>v0.1</span></div>
    </aside>
    <header className="topbar">
      <div className="header-title"><h1>{view}</h1><span>PushPilot <span>/</span> Little Town</span></div>
      <nav className="topnav" aria-label="Main navigation">{(['Workspace', 'Plan', 'Replay'] as View[]).map(tab => <button key={tab} className={view === tab ? 'active' : ''} onClick={() => setView(tab)} aria-current={view === tab ? 'page' : undefined}>{tab}{tab === 'Replay' && Boolean(workspace?.events.length) && <span className="nav-count">{workspace!.events.length}</span>}</button>)}</nav>
      <div className="header-status"><span className="backend-status"><span className={`connection-dot ${online ? 'online' : ''}`}/>{online ? 'Connected' : 'Offline'}</span><button className="header-tool" onClick={() => setShowDemo(value => !value)} aria-expanded={showDemo} aria-controls="simulation-controls" aria-label="Toggle simulation inputs" title="Simulation inputs"><Icon name="settings" size={19}/></button><div className="workspace-identity"><span className="workspace-avatar">P</span><span><strong>PushPilot</strong><small>Simulation workspace</small></span></div></div>
    </header>
    <main className="main-shell">
      <div className="workspace-layout">
        <section className="left-workspace">
          <form className="goal-bar" onSubmit={event => { event.preventDefault(); if (canEditGoal && draft.trim()) void command('goals', { text: draft, provider, source: 'typed' }); }}>
            <button type="button" className="voice-button" disabled title="Voice capture requires the upcoming Meta Voice adapter" aria-label="Voice input unavailable"><Icon name="mic" size={25}/></button>
            <div className="goal-field"><label htmlFor="goal-input">Mission goal <span>{active ? 'Mission in progress' : 'Bakery · Bookstore · School'}</span></label><input ref={goalInput} id="goal-input" value={draft} onChange={event => setDraft(event.target.value)} disabled={!canEditGoal} maxLength={500} aria-label="Your mission goal"/></div>
            <button className="goal-submit" type="submit" disabled={!canEditGoal || !draft.trim()} aria-label="Interpret goal"><Icon name="arrow" size={28}/></button>
          </form>

          {error && <div className="error-banner" role="alert"><Icon name="shield" size={20}/><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><Icon name="close" size={16}/></button></div>}
          {!online && <div className="connection-banner" role="status"><span className="connection-dot"/>{workspace ? 'Backend disconnected. Actions are unavailable until state is refreshed.' : 'Connecting to the mission backend…'}<button onClick={() => void refresh()}>Retry</button></div>}

          <section className={`scene-panel panel ${view !== 'Workspace' ? 'alternate-view' : ''}`} aria-label={view === 'Workspace' ? 'Scene preview' : view === 'Plan' ? 'Mission plan' : 'Evidence replay'}>
            <div className="scene-toolbar"><div className="scene-toolbar-label"><Icon name={view === 'Workspace' ? 'camera' : view === 'Plan' ? 'route' : 'clock'} size={19}/><h2>{view === 'Workspace' ? 'Scene workspace' : view === 'Plan' ? 'Mission plan' : 'Evidence replay'}</h2></div><span className="scene-preview-label">{view === 'Workspace' ? 'Temporary print' : view === 'Plan' ? 'Temporary road graph' : 'Recorded decisions'}</span><span className="ar-status"><span/>{sceneSnapshot?.registration.status === 'locked' || sceneSnapshot?.registration.status === 'locked_partial' ? 'Test overlay locked' : 'Test overlay only'}</span></div>
            {view === 'Workspace' && <MapScene workspace={workspace} onSnapshot={setSceneSnapshot} readOnly={actionReviewPending} openToolsRequest={imageToolsRequest}/>}
            {view === 'Plan' && <div className="plan-canvas"><span className="eyebrow">ONE ACTION. ONE CHECK.</span><h2>A plan you can inspect.</h2><p>Push on the surface, stop at every planned intersection, check its signal, then verify arrival. Temporary drawing geometry defines the simulation route; robot coordinates remain unqualified.</p><PlanList workspace={workspace} expanded/><div className="plan-note"><Icon name="shield" size={20}/><span>Every intersection requires its own verified stop and fresh green. Unknown or stale signals inhibit entry.</span></div></div>}
            {view === 'Replay' && <EvidenceTimeline events={workspace?.events ?? []} selected={selectedEvent} onSelect={setSelectedEvent}/>}
            <div className="source-strip"><SourcePill>Robot · disconnected</SourcePill><SourcePill>Image · {sceneSnapshot?.frame?.source ?? 'none'}</SourcePill><SourcePill>Car pose · unmeasured</SourcePill><SourcePill status="amber">Signal · simulation</SourcePill></div>
          </section>

          <ActionReviewPanel workspace={workspace} scene={sceneSnapshot} online={online} pending={actionReviewPending} busy={busy} readOnly={view === 'Replay'} replayEvidence={selected?.record} onReview={reviewRecordedAction} onOpenTools={() => { setView('Workspace'); setImageToolsRequest(value => value + 1); }}/>

          <div className="bottom-cards"><RouteSummary workspace={workspace}/><ActionLoop workspace={workspace}/><section className="panel companion-card"><div className="card-heading"><span className="card-status-dot muted"/><h2>Glasses companion</h2><span className="concept-tag">Concept</span></div><div className="companion-body"><div><h3>Beyond<br/>the tablet.</h3><p>See it. Say it. Review it.</p></div><GlassesArt/></div><span className="companion-note">Future experience · hardware not connected</span></section></div>

          {showDemo && view !== 'Replay' && <section className="panel demo-controls" id="simulation-controls"><div className="demo-heading"><span className="eyebrow">SIMULATION INPUTS</span><span>No live camera or physical robot</span><button aria-label="Close simulation controls" onClick={() => setShowDemo(false)}><Icon name="close" size={18}/></button></div><div className="demo-grid"><div><h3>Paper signal stand-in {signalJunction ? `· ${signalJunction}` : ''}</h3><p>{signalJunction ? `A fresh observation applies only to junction ${signalJunction}.` : 'The backend binds an observation to the current junction.'}</p><div className="signal-buttons">{(['RED', 'GREEN', 'UNKNOWN'] as SignalColor[]).map(color => <button key={color} className={`signal-option ${color.toLowerCase()} ${signal === color ? 'selected' : ''}`} disabled={busy || actionReviewPending || !online || !workspace} onClick={() => void command('signal', { color })}><span/>{color[0] + color.slice(1).toLowerCase()}</button>)}</div></div><div><h3>Action review stand-in</h3><p>Demo decisions are never labelled as MUSE.</p><div className="review-buttons">{(['PASS', 'REOBSERVE', 'UNKNOWN', 'FAIL'] as ReviewVerdict[]).map(verdict => <button key={verdict} disabled={!pendingReview || busy || actionReviewPending || !online} className={verdict === 'FAIL' ? 'danger-text' : ''} onClick={() => void command('reviews', { review_id: workspace!.review!.id, verdict })}>{verdict === 'REOBSERVE' ? 'Re-observe' : verdict[0] + verdict.slice(1).toLowerCase()}</button>)}</div></div></div></section>}
        </section>

        <aside className="plan-panel panel" aria-label="AI plan and mission controls">
          <div className="plan-panel-top"><span className="eyebrow">{view === 'Replay' && selected ? 'Decision evidence' : 'Active mission'}</span><span className="provider-label">{workspace?.goal?.provider === 'meta' ? 'MUSE interpretation' : 'Demo interpretation'}</span></div>
          {view === 'Replay' ? <div className="selected-evidence">{selected ? <><span className="evidence-index">#{String(selected.sequence).padStart(3, '0')}</span><h2>{selected.title}</h2><p>{selected.detail}</p><dl><div><dt>Source</dt><dd>{selected.source}</dd></div><div><dt>Recorded at</dt><dd>{new Date(selected.at).toLocaleString('en-US')}</dd></div><div><dt>State after event</dt><dd>{stateLabels[selected.state] ?? selected.state}</dd></div><div><dt>Event identifier</dt><dd className="mono">{selected.id}</dd></div></dl></> : <><h2>Every decision, visible.</h2><p>Select a recorded event to inspect its source and the state it produced.</p></>}<div className="plan-note"><Icon name="clock" size={19}/><span>Replay is evidence only. Return to Workspace to interact with the simulation.</span></div></div> : <>
            <h2 className="plan-title">{title.split('\n').map((line, i) => <span key={i}>{line}</span>)}</h2>
            <p className="plan-description">{workspace?.goal?.summary ?? 'Your perspective. A shared plan. Review each step before the next action.'}</p>
            <div className="journey-summary"><div className="journey-from"><span className="destination-icon"><Icon name="car" size={31}/></span><span><strong>{workspace?.plan?.route.start ?? 'PIZZA'}</strong><small>Start</small></span></div><Icon name="arrow" className="journey-arrow" size={30}/><div className="journey-to"><span className="destination-icon"><Icon name="route" size={29}/></span><span><strong>{destination}</strong><small>Destination</small></span></div></div>
            <div className="mission-progress"><div><span>Completed actions</span><strong>{completedSteps}<span> / {totalSteps}</span></strong></div><progress aria-label="Completed mission actions" value={completedSteps} max={totalSteps || 1}/></div>
            <div className="section-label"><h3>Route plan</h3><span>{workspace?.plan?.route ? `${Math.min(workspace.current_step + 1, workspace.plan.steps.length)}/${workspace.plan.steps.length} · ${workspace.plan.route.junction_ids.length} junction ${workspace.plan.route.junction_ids.length === 1 ? 'check' : 'checks'}` : 'Temporary road graph'}</span></div><PlanList workspace={workspace}/>
            {workspace?.review && <section className="review-card" aria-label="Current action review"><div className="review-card-heading"><Icon name="eye" size={17}/><strong>{workspace.review.source === 'meta' || actionReviewPending ? 'MUSE REVIEW' : 'DEMO REVIEW'}</strong><span className={`verdict ${workspace.review.verdict.toLowerCase()}`}>{workspace.review.verdict}</span></div><p className="review-brief">{actionReviewPending ? 'MUSE is comparing the selected recordings.' : workspace.review.summary ? workspace.review.summary.length > 160 ? `${workspace.review.summary.slice(0, 157)}…` : workspace.review.summary : 'Awaiting a source-labelled observation.'}</p><details className="review-card-details" key={workspace.review.id}><summary>Expected and observed</summary><dl><div><dt>Expected</dt><dd>{workspace.review.expected}</dd></div><div><dt>Observed</dt><dd>{workspace.review.observed || 'Awaiting a source-labelled observation.'}</dd></div>{workspace.review.summary && <div><dt>Full review summary</dt><dd>{workspace.review.summary}</dd></div>}</dl></details></section>}
            <div className="execution-check"><div><Icon name="shield" size={17}/><h3>NEXT CHECK</h3></div><p>{workspace?.next_check ?? 'Connect to the backend, enter a goal and review the proposed plan.'}</p></div>
            <div className="mission-action"><div className="action-status"><span className={`status-dot ${state.toLowerCase()}`}/><strong>{stateLabels[state]}</strong></div>{renderPrimaryAction()}{state === 'PLAN_READY' && <button className="secondary-button" disabled={!canEditGoal} onClick={() => { setView('Workspace'); goalInput.current?.focus(); }}>Edit goal</button>}{pendingReview && <button className="secondary-button" onClick={() => document.getElementById('recorded-action-review')?.scrollIntoView({ block: 'start', behavior: 'instant' })}><Icon name="spark" size={17}/>Review recorded images</button>}{pendingReview && <button className="secondary-button" onClick={() => setShowDemo(true)}><Icon name="settings" size={17}/>Open demo review controls</button>}{state === 'WAITING_SIGNAL' && <button className="secondary-button" onClick={() => setShowDemo(true)}><span className={`small-signal ${signal.toLowerCase()}`}/>Signal: {signal.toLowerCase()}<Icon name="chevron" size={16}/></button>}{active && <button className="cancel-button" disabled={busy || !online} onClick={() => void command('cancel')}>End simulation</button>}<small className="action-footnote">{actionReviewPending ? 'MUSE is reviewing recorded images…' : busy ? 'Updating the mission…' : 'Simulation only · no physical execution'}</small></div>
            <div className="provider-control"><label htmlFor="provider-mode">Goal interpreter</label><select id="provider-mode" value={provider} disabled={!canEditGoal} onChange={event => setProvider(event.target.value as ProviderMode)}><option value="demo">Demo interpreter</option><option value="meta" disabled={!workspace?.capabilities.muse_configured}>MUSE · Meta API{!workspace?.capabilities.muse_configured ? ' (not configured)' : ''}</option></select></div>
          </>}
        </aside>
      </div>
    </main>
    <footer className="page-footer"><span>PushPilot <span>·</span> Look. Ask. Review.</span><span>Temporary test map <span>·</span> Wearable concept <span>·</span> No robot connected</span><span className="revision">{workspace ? `rev ${workspace.revision}` : 'offline'}</span></footer>
  </div>;
}
