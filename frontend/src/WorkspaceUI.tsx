import { useEffect, useRef, useState } from 'react';
import type { EvidenceEvent, WorkspaceSnapshot } from '../../contracts/workspace';
import type { PhysicalStatus, PhysicalTelemetry } from '../../contracts/physical';
import { physicalDetail, physicalModeLabel, physicalParkingEnabled, physicalProgress, physicalReviewLabel, physicalTitle } from './physicalMission';
import type { TemporaryMap } from '../../contracts/scene';
import { Icon } from './Icons';
import { drawingDistance, nodeLabel, planStepLabel } from './mapMetadata';

function humanizeNodeIds(map: TemporaryMap | null, text: string): string {
  return [...(map?.nodes ?? [])].sort((a, b) => b.id.length - a.id.length).reduce((value, node) => {
    const escaped = node.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return value.replace(new RegExp(`\\b${escaped}\\b`, 'g'), node.label ?? node.id);
  }, text);
}

export function ViewportDialog({ open, title, subtitle, onClose, children, actions, className = '' }: {
  open: boolean; title: string; subtitle?: string; onClose: () => void;
  children: React.ReactNode; actions?: React.ReactNode; className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (open && element && !element.open) element.showModal();
    else if (!open && element?.open) element.close();
  }, [open]);
  return <dialog ref={ref} className={`viewport-dialog ${className}`} aria-label={title}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className="dialog-header"><div><span>{subtitle}</span><h2>{title}</h2></div><div className="dialog-header-actions">{actions}<button className="icon-button" onClick={onClose} aria-label={`Close ${title}`}><Icon name="close" size={20}/></button></div></header>
    <div className="dialog-content">{children}</div>
  </dialog>;
}

function useCompact() {
  const [compact, setCompact] = useState(() => window.matchMedia('(max-width: 700px)').matches);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 700px)');
    const update = () => setCompact(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return compact;
}

export function Pager({ page, total, onChange, label = 'Page' }: { page: number; total: number; onChange: (page: number) => void; label?: string }) {
  return <nav className="pager" aria-label={`${label} navigation`}><button disabled={page <= 0} onClick={() => onChange(page - 1)} aria-label={`Previous ${label.toLowerCase()}`}><Icon name="chevron" className="reverse" size={16}/></button><span>{label} {page + 1} <span>/ {Math.max(1, total)}</span></span><button disabled={page >= total - 1} onClick={() => onChange(page + 1)} aria-label={`Next ${label.toLowerCase()}`}><Icon name="chevron" size={16}/></button></nav>;
}

export function TextPages({ text, size = 440 }: { text: string; size?: number }) {
  const [page, setPage] = useState(0);
  const chunks: string[] = [];
  let remaining = text;
  while (remaining.length) {
    let cut = Math.min(size, remaining.length);
    let lines = 0;
    for (let index = 0; index < cut; index += 1) {
      if (remaining[index] === '\n' && ++lines === 7) { cut = index + 1; break; }
    }
    if (cut === size && cut < remaining.length) {
      const boundary = remaining.lastIndexOf(' ', cut - 1);
      if (boundary > size * .65) cut = boundary + 1;
    }
    chunks.push(remaining.slice(0, cut)); remaining = remaining.slice(cut);
  }
  if (!chunks.length) chunks.push('');
  useEffect(() => setPage(0), [text]);
  const index = Math.min(page, chunks.length - 1);
  return <div className="text-pages"><p>{chunks[index]}</p>{chunks.length > 1 && <Pager page={index} total={chunks.length} onChange={setPage} label="Text"/>}</div>;
}

// Simulation disclaimers in backend step descriptions are covered by the header badge.
const STEP_DISCLAIMER = /\s*(?:No physical [^.]*qualified\.|Physical [^.]*unqualified\.)\s*$/;
export const stepDescription = (text: string) => text.replace(STEP_DISCLAIMER, '');

export function PlanBrowser({ workspace, map = null }: { workspace: WorkspaceSnapshot | null; map?: TemporaryMap | null }) {
  const steps = workspace?.plan?.steps ?? [];
  const listRef = useRef<HTMLOListElement>(null);
  // Every step is listed and scrolls inside the dialog; open with the current step in view.
  // The dialog keeps this mounted while closed, so also re-centre when the list becomes visible (dialog opens).
  const currentStep = workspace?.current_step ?? 0;
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const reveal = () => {
      const current = list.children[currentStep] as HTMLElement | undefined;
      if (current && list.clientHeight > 0) list.scrollTop = Math.max(0, current.offsetTop - list.offsetTop - 8);
    };
    reveal();
    let visible = list.clientHeight > 0;
    const observer = new ResizeObserver(() => { const now = list.clientHeight > 0; if (now && !visible) reveal(); visible = now; });
    observer.observe(list);
    return () => observer.disconnect();
  }, [currentStep, workspace?.plan?.id]);
  return <div className="plan-browser">
    <div className="route-facts"><span><small>From</small><strong>{nodeLabel(map, workspace?.plan?.route.start ?? map?.start)}</strong></span><Icon name="arrow" size={24}/><span><small>To</small><strong>{nodeLabel(map, workspace?.goal?.destination)}</strong></span><span><small>Drawing distance</small><strong>{drawingDistance(workspace?.plan?.route.distance_mm)} mm</strong></span><span><small>Junction checks</small><strong>{workspace?.plan?.route.junction_ids.length ?? '—'} </strong></span></div>
    <ol ref={listRef} className="route-page" aria-label="Route steps">{steps.map((step, index) => <li className={`${step.status}${index === currentStep ? ' focused' : ''}`} key={step.id}><span className="route-number">{step.status === 'complete' ? <Icon name="check" size={16}/> : String(index + 1).padStart(2, '0')}</span><div><strong>{planStepLabel(map, step)}</strong><p>{humanizeNodeIds(map, stepDescription(step.description))}</p></div><span className={`route-kind kind-${step.kind.toLowerCase()}`}>{step.kind}</span></li>)}</ol>
    {steps.length === 0 && <p className="empty-copy">Create a goal to inspect its route.</p>}
  </div>;
}

export function EvidenceBrowser({ events, selected, onSelect, onOpenRecord }: {
  events: EvidenceEvent[]; selected: EvidenceEvent | undefined;
  onSelect: (id: string) => void; onOpenRecord: () => void;
}) {
  const compact = useCompact();
  const [tab, setTab] = useState<'timeline' | 'detail'>('timeline');
  // Newest first; the whole log scrolls inside the left column instead of paging.
  const ordered = [...events].reverse();
  return <div className={`evidence-browser show-${tab}`}>
    <div className="compact-evidence-tabs"><button className={tab === 'timeline' ? 'selected' : ''} onClick={() => setTab('timeline')}>Timeline</button><button className={tab === 'detail' ? 'selected' : ''} onClick={() => setTab('detail')}>Decision</button></div>
    <div className="evidence-columns"><section className="event-page" aria-label={`Recorded decisions, ${ordered.length}`}>{ordered.map(event => <button key={event.id} className={selected?.id === event.id ? 'selected' : ''} onClick={() => { onSelect(event.id); setTab('detail'); }}><span className="event-sequence">{String(event.sequence).padStart(3, '0')}</span><span><strong>{event.title}</strong><small>{event.source} · {new Date(event.at).toLocaleTimeString('en-US', { hour12: false })}</small></span><Icon name="chevron" size={16}/></button>)}</section>
      <section key={selected?.id ?? 'none'} className="decision-page" aria-label="Selected decision">{selected ? <><div className="decision-label"><span>Decision #{selected.sequence}</span><span>{selected.source}</span></div><h3>{selected.title}</h3><TextPages text={selected.detail} size={compact ? 250 : 470}/><dl><div><dt>State</dt><dd>{selected.state.replaceAll('_', ' ')}</dd></div><div><dt>Recorded</dt><dd>{new Date(selected.at).toLocaleString('en-US')}</dd></div></dl>{selected.record && <button className="secondary-button" onClick={onOpenRecord}><Icon name="eye" size={16}/>Open bound image evidence</button>}</> : <p className="empty-copy">No decisions have been recorded.</p>}</section></div>
  </div>;
}

/** Same box as the text inputs; the list opens below the field instead of the native menu covering it. */
export function SelectField<T extends string>({ id, label, value, options, disabled = false, onChange }: {
  id: string; label: string; value: T; disabled?: boolean;
  options: { value: T; label: string; disabled?: boolean }[]; onChange: (value: T) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const selected = options.find(option => option.value === value) ?? options[0];
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, [open]);
  const choose = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value); setOpen(false); button.current?.focus();
  };
  const step = (from: number, delta: number) => {
    for (let index = from + delta; index >= 0 && index < options.length; index += delta) if (!options[index].disabled) return index;
    return from;
  };
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) { setActive(Math.max(0, options.indexOf(selected))); setOpen(true); return; }
      setActive(current => step(current, event.key === 'ArrowDown' ? 1 : -1));
    }
    if ((event.key === 'Enter' || event.key === ' ') && open) { event.preventDefault(); choose(active); }
  };
  return <div className={`select-field ${open ? 'open' : ''}`} ref={root}>
    <span className="select-field-label" id={`${id}-label`}>{label}</span>
    <button ref={button} type="button" id={id} className="select-field-control" disabled={disabled} aria-haspopup="listbox" aria-expanded={open}
      aria-labelledby={`${id}-label ${id}-value`} aria-controls={`${id}-list`} onKeyDown={onKeyDown}
      onClick={() => { setActive(Math.max(0, options.indexOf(selected))); setOpen(value => !value); }}>
      <span id={`${id}-value`}>{selected?.label}</span><Icon name="chevron" size={16}/>
    </button>
    {open && <ul className="select-field-list" id={`${id}-list`} role="listbox" aria-labelledby={`${id}-label`}>
      {options.map((option, index) => <li key={option.value} role="option" aria-selected={option.value === value} aria-disabled={option.disabled || undefined}
        className={index === active ? 'active' : ''} onPointerEnter={() => !option.disabled && setActive(index)} onClick={() => choose(index)}>
        <span>{option.label}</span>{option.value === value && <Icon name="check" size={15}/>}
      </li>)}
    </ul>}
  </div>;
}


export function executionStepLabel(step: { label: string; id: string; kind: string }): string {
  const simple = /^([BCD])-step-(\d+)$/.exec(step.label);
  if (simple) return `${simple[1]} · Step ${simple[2]}`;
  if (step.id.endsWith('/signal-recontact')) return 'Recontact vehicle';
  if (step.kind === 'SIGNAL_RECONTACT') return 'Return to contact';
  if (step.kind === 'RETURN_HOME') return 'Return to start';
  return step.label;
}

/** A scroll anchor only: a missing active step never becomes an execution status. */
export function physicalSequenceFocus(steps: readonly { id: string; status: string }[], currentStepId: string | null | undefined): number {
  const explicit = currentStepId == null ? -1 : steps.findIndex(step => step.id === currentStepId);
  if (explicit >= 0) return explicit;
  let lastComplete = -1;
  for (let index = 0; index < steps.length; index += 1) if (steps[index].status === 'complete') lastComplete = index;
  const next = steps.findIndex((step, index) => index > lastComplete && step.status !== 'complete');
  return next >= 0 ? next : lastComplete;
}

export function signalGateLabel(id: string): string {
  if (/^SOUTH_JUNCTION(?:_|$)/.test(id)) return 'South Junction';
  if (/^NORTH_JUNCTION(?:_|$)/.test(id)) return 'North Junction';
  return id.replaceAll('_', ' ');
}

function useRevealCurrent(ref: React.RefObject<HTMLOListElement | null>, current: number, missionId: string | null | undefined) {
  useEffect(() => {
    const list = ref.current;
    if (!list) return;
    const reveal = () => {
      const row = list.children[current] as HTMLElement | undefined;
      if (row && list.clientHeight > 0) {
        const anchor = row.previousElementSibling as HTMLElement | null;
        list.scrollTop = Math.max(0, (anchor ?? row).offsetTop - list.offsetTop - 8);
      }
    };
    reveal();
    let visible = list.clientHeight > 0;
    const observer = new ResizeObserver(() => { const now = list.clientHeight > 0; if (now && !visible) reveal(); visible = now; });
    observer.observe(list);
    return () => observer.disconnect();
  }, [ref, current, missionId]);
}

export function PhysicalStatusPanel({ status, connected, map = null, missionBound = true }: { status: PhysicalStatus | null; connected: boolean; map?: TemporaryMap | null; missionBound?: boolean }) {
  const destinations = connected && status?.capabilities.destinations;
  const destinationDetail = !destinations ? 'Robot destinations have not been confirmed.'
    : destinations.length ? `Available robot destinations: ${destinations.map(id => nodeLabel(map, id)).join(', ')}.` : 'No robot destinations are currently available.';
  const currentTitle = !missionBound && connected && status?.available ? 'Robot ready' : physicalTitle(status, connected);
  const currentDetail = !missionBound && connected && status?.available && !status.error && !status.blockers.length
    ? 'No robot execution is bound to the current plan.' : physicalDetail(status, connected);
  return <section className="physical-status-panel">
    <h3>{currentTitle}</h3>
    <TextPages text={`${currentDetail}\n\n${destinationDetail}`} size={320}/>
    <dl className="physical-status-facts">
      <div><dt>Robot</dt><dd>{!connected ? 'Status unavailable' : !status?.robot.connected ? 'Disconnected' : status.robot.at_start ? 'Ready at start' : status.robot.stationary ? 'Stationary' : 'Moving'}</dd></div>
      <div><dt>Car arrival</dt><dd>{!missionBound ? 'No current mission' : connected && status?.car.arrived ? 'Confirmed' : 'Not confirmed'}</dd></div>
      {physicalParkingEnabled(status) ? <div><dt>Parking alignment</dt><dd>{!missionBound ? 'No current mission' : connected && status?.car.aligned ? 'Confirmed' : 'Not confirmed'}</dd></div>
        : <div><dt>Mission scope</dt><dd>Delivery and return</dd></div>}
      <div><dt>Heading error</dt><dd>{missionBound && connected && status?.car.heading_error_deg != null ? `${Math.abs(status.car.heading_error_deg).toFixed(1)}°` : 'Not measured'}</dd></div>
      <div><dt>Signal</dt><dd>{missionBound && connected ? status?.signal.color ?? 'UNKNOWN' : 'UNKNOWN'}</dd></div>
      <div><dt>{physicalModeLabel(status)}</dt><dd>{!missionBound ? 'No active stage' : connected ? status?.stage_label || 'No active stage' : 'Current stage unconfirmed'}</dd></div>
    </dl>
    <p className="physical-stop-note">A stop request holds further dispatch. A stopped state is confirmed separately by the robot.</p>
  </section>;
}

const recordedTime = (at: number) => new Date(at * 1000).toLocaleTimeString('en-US', { hour12: false });

export function PhysicalRouteBrowser({ status, telemetry, connected, map }: {
  status: PhysicalStatus | null; telemetry: PhysicalTelemetry | null; connected: boolean; map: TemporaryMap | null;
}) {
  const steps = telemetry?.sequence ?? [];
  const listRef = useRef<HTMLOListElement>(null);
  const current = physicalSequenceFocus(steps, telemetry?.current_step_id);
  const progress = physicalProgress(status, telemetry);
  useRevealCurrent(listRef, current, status?.mission_id);
  return <div className="plan-browser physical-telemetry">
    <div className="route-facts"><span><small>Destination</small><strong>{telemetry ? nodeLabel(map, status?.destination) : 'Not started'}</strong></span><span><small>Executor receipts</small><strong>{progress ? `${progress.completed} / ${progress.total}` : 'Awaiting execution'}</strong></span><span><small>TCP travel</small><strong>{telemetry?.distance_source === 'native_tcp' ? `${telemetry.distance_mm!.toFixed(1)} mm` : 'Not measured'}</strong></span></div>
    {steps.length ? <ol ref={listRef} className="route-page" aria-label="Robot execution sequence">{steps.map((step, index) => <li className={`${step.status}${index === current ? ' focused' : ''}`} key={step.id}><span className="route-number">{step.status === 'complete' ? <Icon name="check" size={16}/> : String(index + 1).padStart(2, '0')}</span><div><strong title={step.label}>{executionStepLabel(step)}</strong><p>{step.detail}</p><small>{step.status} · {step.id}</small></div><span className={`route-kind kind-${step.kind.toLowerCase()}`}>{step.kind.replaceAll('_', ' ')}</span></li>)}</ol> : <p className="empty-copy">{connected ? 'The executor has not reported a sequence for this mission.' : 'Robot telemetry is unavailable. No completion is inferred.'}</p>}
  </div>;
}

export function PhysicalHistoryBrowser({ telemetry, connected }: { telemetry: PhysicalTelemetry | null; connected: boolean }) {
  const compact = useCompact();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<'timeline' | 'detail'>('timeline');
  const ordered = [...(telemetry?.history ?? [])].reverse();
  const selected = ordered.find(event => event.id === selectedId) ?? ordered[0];
  return <div className={`evidence-browser physical-telemetry show-${tab}`}>
    <div className="compact-evidence-tabs"><button className={tab === 'timeline' ? 'selected' : ''} onClick={() => setTab('timeline')}>Timeline</button><button className={tab === 'detail' ? 'selected' : ''} onClick={() => setTab('detail')}>Record</button></div>
    <div className="evidence-columns"><section className="event-page" aria-label={`Robot execution records, ${ordered.length}`}>{ordered.map(event => <button key={event.id} className={selected?.id === event.id ? 'selected' : ''} onClick={() => { setSelectedId(event.id); setTab('detail'); }}><span><strong>{event.title}</strong><small>{event.source} · {recordedTime(event.at)}</small></span><Icon name="chevron" size={16}/></button>)}</section>
      <section key={selected?.id ?? 'none'} className="decision-page" aria-label="Selected robot record">{selected ? <><div className="decision-label"><span>{selected.kind}</span><span>{selected.source}</span></div><h3>{selected.title}</h3><TextPages text={selected.detail} size={compact ? 250 : 440}/><dl><div><dt>Recorded</dt><dd>{recordedTime(selected.at)}</dd></div><div><dt>Record ID</dt><dd>{selected.id}</dd></div></dl></> : <p className="empty-copy">{connected ? 'No robot records for this mission yet.' : 'Robot records are unavailable.'}</p>}</section></div>
  </div>;
}

export function PhysicalReviewPanel({ status, telemetry, connected }: { status: PhysicalStatus | null; telemetry: PhysicalTelemetry | null; connected: boolean }) {
  const review = telemetry?.review;
  const inFlight = connected && status?.vision?.in_flight;
  return <section className="physical-status-panel"><h3>{physicalReviewLabel(status, telemetry, connected)}</h3><TextPages text={inFlight
    ? 'MUSE is reviewing the current camera evidence. The executor will apply the result when the request completes.'
    : review?.summary ?? (connected ? 'No MUSE review has been recorded for this robot mission.' : 'Live review status is unavailable. No verdict is inferred.')} size={380}/>
    {review && <dl className="physical-status-facts"><div><dt>Source</dt><dd>MUSE · Meta</dd></div><div><dt>Observed</dt><dd>{recordedTime(review.observed_at)}</dd></div><div><dt>Bound frames</dt><dd>{review.frame_ids.length}</dd></div><div><dt>Verdict</dt><dd>{review.verdict}</dd></div></dl>}
  </section>;
}
