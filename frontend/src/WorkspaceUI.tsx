import { useEffect, useRef, useState } from 'react';
import type { EvidenceEvent, WorkspaceSnapshot } from '../../contracts/workspace';
import { Icon } from './Icons';

export function ViewportDialog({ open, title, subtitle, onClose, children, className = '' }: {
  open: boolean; title: string; subtitle?: string; onClose: () => void;
  children: React.ReactNode; className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (open && element && !element.open) element.showModal();
    else if (!open && element?.open) element.close();
  }, [open]);
  return <dialog ref={ref} className={`viewport-dialog ${className}`} aria-label={title}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className="dialog-header"><div><span>{subtitle}</span><h2>{title}</h2></div><button className="icon-button" onClick={onClose} aria-label={`Close ${title}`}><Icon name="close" size={20}/></button></header>
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

export function PlanBrowser({ workspace }: { workspace: WorkspaceSnapshot | null }) {
  const compact = useCompact();
  const size = compact ? 2 : 4;
  const [page, setPage] = useState(0);
  const steps = workspace?.plan?.steps ?? [];
  const pages = Math.max(1, Math.ceil(steps.length / size));
  const index = Math.min(page, pages - 1);
  useEffect(() => setPage(Math.floor((workspace?.current_step ?? 0) / size)), [workspace?.current_step, size, workspace?.plan?.id]);
  return <div className="plan-browser">
    <div className="route-facts"><span><small>From</small><strong>{workspace?.plan?.route.start ?? 'PIZZA'}</strong></span><Icon name="arrow" size={24}/><span><small>To</small><strong>{workspace?.goal?.destination ?? '—'}</strong></span><span><small>Drawing distance</small><strong>{workspace?.plan?.route.distance_mm ?? '—'} mm</strong></span><span><small>Junction checks</small><strong>{workspace?.plan?.route.junction_ids.length ?? '—'}</strong></span></div>
    <ol className="route-page" start={index * size + 1} aria-label="Route steps">{steps.slice(index * size, (index + 1) * size).map((step, offset) => <li className={step.status} key={step.id}><span className="route-number">{step.status === 'complete' ? <Icon name="check" size={16}/> : String(index * size + offset + 1).padStart(2, '0')}</span><div><strong>{step.label}</strong><p>{step.description}</p></div><span className="route-kind">{step.kind}</span></li>)}</ol>
    {steps.length === 0 && <p className="empty-copy">Create a goal to inspect its route.</p>}
    <footer className="dialog-bottom"><span>Temporary drawing graph · simulated actions</span><Pager page={index} total={pages} onChange={setPage} label="Route page"/></footer>
  </div>;
}

export function EvidenceBrowser({ events, selected, onSelect, onOpenRecord }: {
  events: EvidenceEvent[]; selected: EvidenceEvent | undefined;
  onSelect: (id: string) => void; onOpenRecord: () => void;
}) {
  const compact = useCompact();
  const size = compact ? 2 : 4;
  const [page, setPage] = useState(0);
  const [tab, setTab] = useState<'timeline' | 'detail'>('timeline');
  const ordered = [...events].reverse();
  const pages = Math.max(1, Math.ceil(ordered.length / size));
  const index = Math.min(page, pages - 1);
  return <div className={`evidence-browser show-${tab}`}>
    <div className="compact-evidence-tabs"><button className={tab === 'timeline' ? 'selected' : ''} onClick={() => setTab('timeline')}>Timeline</button><button className={tab === 'detail' ? 'selected' : ''} onClick={() => setTab('detail')}>Decision</button></div>
    <div className="evidence-columns"><section className="event-page" aria-label="Recorded decisions">{ordered.slice(index * size, (index + 1) * size).map(event => <button key={event.id} className={selected?.id === event.id ? 'selected' : ''} onClick={() => { onSelect(event.id); setTab('detail'); }}><span className="event-sequence">{String(event.sequence).padStart(3, '0')}</span><span><strong>{event.title}</strong><small>{event.source} · {new Date(event.at).toLocaleTimeString('en-US', { hour12: false })}</small></span><Icon name="chevron" size={16}/></button>)}</section>
      <section className="decision-page" aria-label="Selected decision">{selected ? <><div className="decision-label"><span>Decision #{selected.sequence}</span><span>{selected.source}</span></div><h3>{selected.title}</h3><TextPages text={selected.detail} size={compact ? 250 : 470}/><dl><div><dt>State</dt><dd>{selected.state.replaceAll('_', ' ')}</dd></div><div><dt>Recorded</dt><dd>{new Date(selected.at).toLocaleString('en-US')}</dd></div></dl>{selected.record && <button className="secondary-button" onClick={onOpenRecord}><Icon name="eye" size={16}/>Open bound image evidence</button>}</> : <p className="empty-copy">No decisions have been recorded.</p>}</section></div>
    <footer className="dialog-bottom"><span>Read-only replay · no execution controls</span><Pager page={index} total={pages} onChange={setPage} label="Timeline page"/></footer>
  </div>;
}
