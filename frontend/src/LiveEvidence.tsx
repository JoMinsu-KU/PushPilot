import { useState } from 'react';
import type { LiveActionEvidence, LiveFrameEvidence, LivePlanningEvidence, LiveSignalEvidence } from '../../contracts/live-intelligence';
import { Icon } from './Icons';
import { TextPages } from './WorkspaceUI';

export type LiveDecisionEvidence = LivePlanningEvidence | LiveActionEvidence | LiveSignalEvidence;

function Frame({ frame, label }: { frame: LiveFrameEvidence; label: string }) {
  return <figure className="ar-frame">
    <a className="ar-frame-image" href={frame.image_url} target="_blank" rel="noreferrer" aria-label={`Open original ${label.toLowerCase()} image`}>
      <img src={frame.image_url} alt={`${label.toLowerCase()} native camera evidence`} loading="lazy"/>
      <span className="ar-frame-label">{label}</span>
    </a>
    <figcaption><strong>Native camera · {frame.width} × {frame.height}</strong><span>Host receive time · exposure time unknown</span><span className="mono">Frame {frame.native_frame_id.slice(0, 8)} · SHA {frame.sha256.slice(0, 10)}</span></figcaption>
  </figure>;
}

/** Read-only native-image evidence; never route it through recorded-pair controls. */
export function LiveEvidence({ evidence }: { evidence: LiveDecisionEvidence }) {
  const [tab, setTab] = useState<'summary' | 'images' | 'record'>('summary');
  const planning = evidence.input_kind === 'live_native_frame_and_graph';
  const action = evidence.input_kind === 'server_bound_live_pair';
  const title = planning ? 'Live route planning' : action ? 'Live action comparison' : 'Stopped signal judgment';
  const summary = planning ? `${evidence.result.summary}\n\n${evidence.result.scene_assessment.detail}`
    : action ? `${evidence.summary}\n\n${evidence.observed}\n\n${evidence.limitations.join('\n')}`
      : `${evidence.color} · ${evidence.summary}\n\n${evidence.limitations.join('\n')}`;
  return <section className="ar-workspace ar-readonly" aria-label="Live MUSE evidence">
    <header className="ar-heading"><div><span className="ar-eyebrow">Native image evidence</span><h2>{title}</h2></div><span className="ar-source">MUSE · read only</span></header>
    <nav className="ar-tabs" aria-label="Live evidence views">{(['summary', 'images', 'record'] as const).map(item => <button key={item} type="button" className={tab === item ? 'active' : ''} aria-pressed={tab === item} onClick={() => setTab(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
    <div className="ar-stage">
      {tab === 'summary' && <section className="ar-result"><div className="ar-result-heading"><h3>{planning ? evidence.result.requires_clarification ? 'Clarification needed' : 'Route proposed' : action ? evidence.verdict : evidence.color}</h3><span className="ar-source">Simulation only</span></div><TextPages text={summary} size={400}/></section>}
      {tab === 'images' && <div className="ar-pair" style={action ? undefined : { gridTemplateColumns: 'minmax(0, 1fr)' }}>{action ? <><Frame frame={evidence.before} label="BEFORE"/><Frame frame={evidence.after} label="AFTER"/></> : <Frame frame={evidence.frame} label={planning ? 'PLANNING' : 'POST-STOP'}/>}</div>}
      {tab === 'record' && <section className="ar-provenance"><h3>Complete immutable record</h3><TextPages text={JSON.stringify(evidence, null, 2)} size={420}/></section>}
    </div>
    <p className="ar-authority"><Icon name="shield" size={15}/><span>Native camera evidence · simulated actions · no physical motion authority</span></p>
  </section>;
}
