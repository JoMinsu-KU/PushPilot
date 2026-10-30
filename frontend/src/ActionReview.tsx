import { useEffect, useState } from 'react';
import type { RecordedActionEvidence, RecordedActionReviewCommand, RecordedFrameEvidence } from '../../contracts/action-review';
import type { SceneSnapshot } from '../../contracts/scene';
import type { WorkspaceSnapshot } from '../../contracts/workspace';
import { Icon } from './Icons';
import { pairReadiness, recordedCaptureLabel, selectRecordedFrame, type SelectedRecordedFrame } from './recordedReview';
import './action-review.css';

type Frame = NonNullable<SceneSnapshot['frame']> | RecordedFrameEvidence;
type ReviewInput = Omit<RecordedActionReviewCommand, 'request_id' | 'expected_revision'>;
type ReviewTab = 'images' | 'review' | 'result' | 'evidence';

/** Bound text to a page, preserving every character and explicit line break. */
function textPages(text: string, limit = 520, lineLimit = 8): string[] {
  if (!text) return [''];
  const pages: string[] = [];
  let offset = 0;
  while (offset < text.length) {
    let end = Math.min(offset + limit, text.length);
    let lines = 0;
    for (let position = offset; position < end; position += 1) {
      if (text[position] === '\n' && ++lines === lineLimit) { end = position + 1; break; }
    }
    if (end < text.length && end === offset + limit) {
      const boundary = text.lastIndexOf(' ', end - 1);
      if (boundary > offset + limit * .65) end = boundary + 1;
    }
    pages.push(text.slice(offset, end));
    offset = end;
  }
  return pages;
}

function PageControl({ page, count, onChange, label = 'Page' }: { page: number; count: number; onChange: (page: number) => void; label?: string }) {
  return <div className="ar-pagination" aria-label={`${label} navigation`}>
    <button type="button" aria-label={`Previous ${label.toLowerCase()}`} disabled={page === 0} onClick={() => onChange(page - 1)}><Icon name="chevron" size={17} className="ar-previous"/></button>
    <span aria-live="polite">{label} {page + 1} <span>/ {count}</span></span>
    <button type="button" aria-label={`Next ${label.toLowerCase()}`} disabled={page >= count - 1} onClick={() => onChange(page + 1)}><Icon name="chevron" size={17}/></button>
  </div>;
}

function PagedText({ text, label, code = false }: { text: string; label: string; code?: boolean }) {
  const [page, setPage] = useState(0);
  const pages = textPages(text, code ? 650 : 520, code ? 11 : 8);
  const current = Math.min(page, pages.length - 1);
  useEffect(() => { setPage(0); }, [text]);
  return <div className={`ar-paged-text${code ? ' ar-code' : ''}`}>
    <p className="ar-text-page" aria-label={label}>{pages[current] || 'Not reported.'}</p>
    <PageControl page={current} count={pages.length} onChange={setPage}/>
  </div>;
}

function ExpectedEditor({ value, disabled, onChange }: { value: string; disabled: boolean; onChange: (value: string) => void }) {
  const [pages, setPages] = useState(() => textPages(value, 240, 4));
  const [page, setPage] = useState(0);
  const current = Math.min(page, pages.length - 1);
  useEffect(() => {
    if (value !== pages.join('')) { setPages(textPages(value, 240, 4)); setPage(0); }
  }, [value, pages]);
  const updatePage = (text: string) => {
    const available = 1000 - (value.length - pages[current].length);
    const replacement = textPages(text.slice(0, available), 240, 4);
    const next = [...pages.slice(0, current), ...replacement, ...pages.slice(current + 1)];
    setPages(next);
    setPage(current + replacement.length - 1);
    onChange(next.join(''));
  };
  return <div className="ar-editor">
    <textarea id="recorded-expected-outcome" value={pages[current]} rows={8} disabled={disabled} maxLength={1000 - (value.length - pages[current].length)} onChange={event => updatePage(event.target.value)} placeholder="Describe what should be visibly different after this action."/>
    <div className="ar-editor-tools"><span>{value.length} / 1,000 characters</span><PageControl page={current} count={pages.length} onChange={setPage}/><button type="button" className="ar-text-button" disabled={disabled || !pages[pages.length - 1] || value.length >= 1000} onClick={() => { setPages([...pages, '']); setPage(pages.length); }}>Add page</button></div>
  </div>;
}

function FramePreview({ frame, label, empty }: { frame: Frame | null; label: 'BEFORE' | 'AFTER'; empty: string }) {
  return <figure className="ar-frame">
    <div className="ar-frame-image">{frame ? <img src={frame.image_url} alt={`${label.toLowerCase()} operator-selected recording`} loading="lazy"/> : <div className="ar-frame-placeholder"><Icon name="camera" size={24}/><span>{empty}</span></div>}<span className="ar-frame-label">{label}</span></div>
    <figcaption>{frame ? <><strong>{frame.source} · {frame.width} × {frame.height}</strong><span>{recordedCaptureLabel(frame)}</span><span className="mono">Frame {frame.id.slice(0, 8)} · SHA {frame.sha256.slice(0, 10)}</span></> : <span>{empty}</span>}</figcaption>
  </figure>;
}

function ReviewResult({ evidence }: { evidence: RecordedActionEvidence }) {
  const [section, setSection] = useState<'summary' | 'expected' | 'observed' | 'limitations'>('summary');
  const sections = { summary: 'Summary', expected: 'Expected', observed: 'Observed', limitations: 'Limitations' };
  const text = { summary: evidence.summary, expected: evidence.expected_visual, observed: evidence.observed, limitations: evidence.limitations.length ? evidence.limitations.map((item, index) => `${index + 1}. ${item}`).join('\n\n') : 'The model reported no limitations. Recorded images still do not establish freshness or physical task completion.' }[section];
  return <div className="ar-result">
    <div className="ar-result-heading"><div><span className="ar-eyebrow">Last accepted recorded review</span><h3>{evidence.server_action.label}</h3></div><span className={`ar-verdict ${evidence.verdict.toLowerCase()}`}>{evidence.verdict}</span></div>
    <div className="ar-segmented" aria-label="Review result sections">{Object.entries(sections).map(([key, label]) => <button type="button" key={key} aria-pressed={section === key} className={section === key ? 'active' : ''} onClick={() => setSection(key as typeof section)}>{label}</button>)}</div>
    <PagedText key={`${evidence.id}-${section}`} text={text} label={sections[section]}/>
  </div>;
}

function EvidenceDetails({ evidence }: { evidence: RecordedActionEvidence }) {
  const [page, setPage] = useState(0);
  const groups = [
    { title: 'Action binding', items: [
      ['Simulated action', `${evidence.server_action.label} · ${evidence.server_action.kind}`],
      ['Plan / action / review', `${evidence.plan_id}\n${evidence.action_id}\n${evidence.review_id}`],
      ['Input revisions', `Workspace ${evidence.input_workspace_revision} · scene ${evidence.input_scene_revision}`],
      ['Map', `${evidence.map_id} · ${evidence.map_version}\n${evidence.map_hash}`],
    ] },
    { title: 'Recording provenance', items: [
      ['BEFORE identity / SHA-256', `${evidence.before.id}\n${evidence.before.sha256}`],
      ['AFTER identity / SHA-256', `${evidence.after.id}\n${evidence.after.sha256}`],
      ['BEFORE capture', `${evidence.before.source} · ${recordedCaptureLabel(evidence.before)}`],
      ['AFTER capture', `${evidence.after.source} · ${recordedCaptureLabel(evidence.after)}`],
    ] },
    { title: 'Provider receipt', items: [
      ['Model / elapsed', `${evidence.model} · ${(evidence.elapsed_ms / 1000).toFixed(2)} s`],
      ['Token usage', evidence.usage ? `Input ${evidence.usage.prompt_tokens ?? 'not reported'} · output ${evidence.usage.completion_tokens ?? 'not reported'} · total ${evidence.usage.total_tokens ?? 'not reported'}` : 'Not reported by the provider'],
      ['Reviewed at', new Date(evidence.created_at).toLocaleString('en-US')],
      ['Prompt / schema', `${evidence.prompt_version}\n${evidence.schema_version}`],
    ] },
    { title: 'Complete immutable record', items: [] },
  ];
  return <div className="ar-provenance">
    <div className="ar-provenance-heading"><div><span className="ar-eyebrow">Evidence</span><h3>{groups[page].title}</h3></div><PageControl page={page} count={groups.length} onChange={setPage} label="Section"/></div>
    {page === 3 ? <PagedText text={JSON.stringify(evidence, null, 2)} label="Complete evidence record" code/> : <dl className="ar-metadata">{groups[page].items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
  </div>;
}

function AuthorityNote() {
  return <p className="ar-authority"><Icon name="shield" size={15}/><span>Operator-selected recordings <span>·</span> Simulation only <span>·</span> No hardware motion authority</span></p>;
}

export function ActionEvidence({ evidence }: { evidence: RecordedActionEvidence }) {
  const [tab, setTab] = useState<'images' | 'result' | 'evidence'>('result');
  return <section className="ar-workspace ar-readonly" aria-label="Recorded MUSE action evidence">
    <header className="ar-heading"><div><span className="ar-eyebrow">Mission Log</span><h2>Recorded comparison</h2></div><span className="ar-source">MUSE · read only</span></header>
    <nav className="ar-tabs" aria-label="Recorded evidence views">{(['images', 'result', 'evidence'] as const).map(item => <button type="button" key={item} aria-pressed={tab === item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
    <div className="ar-stage">{tab === 'images' && <div className="ar-pair"><FramePreview frame={evidence.before} label="BEFORE" empty="Before recording"/><FramePreview frame={evidence.after} label="AFTER" empty="After recording"/></div>}{tab === 'result' && <ReviewResult evidence={evidence}/>} {tab === 'evidence' && <EvidenceDetails evidence={evidence}/>}</div>
    <AuthorityNote/>
  </section>;
}

export function ActionReviewPanel({ workspace, scene, online, pending, busy, readOnly, replayEvidence, onReview, onOpenTools }: {
  workspace: WorkspaceSnapshot | null; scene: SceneSnapshot | null; online: boolean; pending: boolean; busy: boolean;
  readOnly: boolean; replayEvidence?: RecordedActionEvidence;
  onReview: (data: ReviewInput) => Promise<void>; onOpenTools: () => void;
}) {
  const [before, setBefore] = useState<SelectedRecordedFrame | null>(null);
  const [expected, setExpected] = useState('');
  const [tab, setTab] = useState<ReviewTab>('images');
  const reviewId = workspace?.review?.id;
  const pendingReview = workspace?.state === 'REVIEW_REQUIRED' && workspace.review?.verdict === 'PENDING';
  useEffect(() => {
    if (workspace?.review?.verdict === 'PENDING') setExpected(workspace.review.expected);
  }, [reviewId]);
  useEffect(() => { if (pendingReview) setTab('review'); }, [pendingReview, reviewId]);
  const candidate = workspace?.review?.evidence?.input_kind === 'operator_selected_recorded_pair'
    ? workspace.review.evidence : [...(workspace?.events ?? [])].reverse().find(event => event.record?.input_kind === 'operator_selected_recorded_pair')?.record;
  const latestEvidence = candidate?.input_kind === 'operator_selected_recorded_pair' ? candidate : undefined;
  const evidence = readOnly ? replayEvidence : latestEvidence;
  const readiness = pairReadiness({ workspace, scene, before, expected, online, pending });
  const editable = !readOnly && !busy && !pending;
  const after = before && scene?.frame && before.frame.id !== scene.frame.id && before.frame.sha256 !== scene.frame.sha256 ? scene.frame : null;
  useEffect(() => { if (latestEvidence && !pendingReview) setTab('result'); }, [latestEvidence?.id]);

  if (readOnly) return evidence ? <ActionEvidence key={evidence.id} evidence={evidence}/> : null;

  return <section className="ar-workspace" id="recorded-action-review" aria-label="Recorded action review">
    <header className="ar-heading"><div><span className="ar-eyebrow">Action-bound image review</span><h2>Recorded comparison</h2></div><span className="ar-source">Real MUSE review</span></header>
    <nav className="ar-tabs" aria-label="Recorded action review views">{(['images', 'review', 'result', 'evidence'] as const).map(item => <button type="button" key={item} disabled={(item === 'result' || item === 'evidence') && !evidence} aria-pressed={tab === item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item[0].toUpperCase() + item.slice(1)}{item === 'images' && before && <span className="ar-tab-dot"/>}</button>)}</nav>
    <div className="ar-stage">
      {tab === 'images' && <div className="ar-image-setup"><div className="ar-pair"><FramePreview frame={before?.frame ?? null} label="BEFORE" empty="Select the current recording"/><FramePreview frame={after} label="AFTER" empty="Upload a different recording"/></div><div className="ar-image-controls"><button type="button" className="ar-secondary" disabled={!editable || !scene?.frame} onClick={() => setBefore(selectRecordedFrame(scene))}>{before ? 'Replace BEFORE' : 'Use current frame as BEFORE'}</button><button type="button" className="ar-secondary" disabled={!editable} onClick={onOpenTools}>Upload AFTER</button>{before && <button type="button" className="ar-text-button" disabled={!editable} onClick={() => setBefore(null)}>Clear selection</button>}<button type="button" className="ar-next" onClick={() => setTab('review')}>Continue<Icon name="arrow" size={17}/></button></div></div>}
      {tab === 'review' && <div className="ar-review-grid"><section className="ar-expected"><label htmlFor="recorded-expected-outcome">Expected visual outcome</label><p>{pendingReview ? workspace?.plan?.steps[workspace.current_step]?.label ?? 'Current simulated action' : 'Available after a simulated action opens a pending review.'}</p><ExpectedEditor key={reviewId ?? 'prepare'} value={expected} disabled={!editable || !pendingReview} onChange={setExpected}/></section><section className="ar-review-readiness"><span className="ar-eyebrow">Selected comparison</span><h3>{before && after ? 'Two recordings selected' : 'Choose the image pair'}</h3><div className="ar-pair-status"><span className={before ? 'selected' : ''}>BEFORE <strong>{before ? 'Selected' : 'Missing'}</strong></span><span className={after ? 'selected' : ''}>AFTER <strong>{after ? 'Selected' : 'Missing'}</strong></span></div><p className="ar-readiness-reason" role={pending ? 'status' : undefined}>{readiness.reason}</p><button type="button" className="ar-review-submit" disabled={!readiness.ready || busy} onClick={() => { if (scene?.frame && before && workspace?.review) void onReview({ review_id: workspace.review.id, expected_scene_revision: scene.revision, before_frame_id: before.frame.id, after_frame_id: scene.frame.id, expected_visual: expected.trim() }); }}>{pending ? 'MUSE is reviewing…' : 'Review action with MUSE'}<Icon name="arrow" size={18}/></button>{(!before || !after) && <button type="button" className="ar-text-button" onClick={() => setTab('images')}>Choose recordings</button>}<small>Local stop and signal checks remain required.</small></section></div>}
      {tab === 'result' && evidence && <ReviewResult evidence={evidence}/>} {tab === 'evidence' && evidence && <EvidenceDetails evidence={evidence}/>}
    </div>
    <AuthorityNote/>
  </section>;
}
