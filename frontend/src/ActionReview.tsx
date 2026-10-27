import { useEffect, useState } from 'react';
import type { RecordedActionEvidence, RecordedActionReviewCommand, RecordedFrameEvidence } from '../../contracts/action-review';
import type { SceneSnapshot } from '../../contracts/scene';
import type { WorkspaceSnapshot } from '../../contracts/workspace';
import { Icon } from './Icons';
import { pairReadiness, recordedCaptureLabel, selectRecordedFrame, type SelectedRecordedFrame } from './recordedReview';
import './action-review.css';

type Frame = NonNullable<SceneSnapshot['frame']> | RecordedFrameEvidence;
type ReviewInput = Omit<RecordedActionReviewCommand, 'request_id' | 'expected_revision'>;

function FramePreview({ frame, label, empty }: { frame: Frame | null; label: 'BEFORE' | 'AFTER'; empty: string }) {
  return <figure className="action-frame">
    <div className="action-frame-image">{frame ? <img src={frame.image_url} alt={`${label.toLowerCase()} operator-selected recording`} loading="lazy"/> : <div className="action-frame-placeholder"><Icon name="camera" size={24}/><span>{empty}</span></div>}<span className="action-frame-label">{label}</span></div>
    <figcaption>{frame ? <><strong>{frame.source} · {frame.width} × {frame.height}</strong><span>{recordedCaptureLabel(frame)}</span><span className="mono">Frame {frame.id.slice(0, 8)} · SHA {frame.sha256.slice(0, 10)}</span></> : <span>{empty}</span>}</figcaption>
  </figure>;
}

export function ActionEvidence({ evidence }: { evidence: RecordedActionEvidence }) {
  return <section className="action-evidence" aria-label="Recorded MUSE action evidence">
    <div className="action-evidence-title"><Icon name="spark" size={17}/><strong>Recorded MUSE action review</strong><span className={`verdict ${evidence.verdict.toLowerCase()}`}>{evidence.verdict}</span></div>
    <p className="action-evidence-summary">{evidence.summary.length > 200 ? `${evidence.summary.slice(0, 197)}…` : evidence.summary}</p>
    <div className="action-pair"><FramePreview frame={evidence.before} label="BEFORE" empty="Before recording"/><FramePreview frame={evidence.after} label="AFTER" empty="After recording"/></div>
    <details className="action-evidence-details"><summary>Expected, observed and provenance <span>Recorded pair · simulation only</span></summary>
      <dl className="action-outcomes"><div><dt>Expected visual outcome</dt><dd>{evidence.expected_visual}</dd></div><div><dt>Observed by MUSE</dt><dd>{evidence.observed}</dd></div><div><dt>Full review summary</dt><dd>{evidence.summary}</dd></div></dl>
      {evidence.limitations.length > 0 && <ul className="action-limitations">{evidence.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>}
      <dl className="action-binding"><div><dt>Simulated action</dt><dd>{evidence.server_action.label} · {evidence.server_action.kind}</dd></div><div><dt>Model / elapsed</dt><dd>{evidence.model} · {(evidence.elapsed_ms / 1000).toFixed(2)} s</dd></div><div><dt>Provider token usage</dt><dd>{evidence.usage ? `Input ${evidence.usage.prompt_tokens ?? 'not reported'} · output ${evidence.usage.completion_tokens ?? 'not reported'} · total ${evidence.usage.total_tokens ?? 'not reported'}` : 'Not reported by the provider'}</dd></div><div><dt>Map</dt><dd>{evidence.map_id} · {evidence.map_version}<span className="mono">{evidence.map_hash}</span></dd></div><div><dt>Plan / action / review</dt><dd className="mono">{evidence.plan_id} / {evidence.action_id} / {evidence.review_id}</dd></div><div><dt>Input revisions</dt><dd>Workspace {evidence.input_workspace_revision} · scene {evidence.input_scene_revision}</dd></div><div><dt>Reviewed at</dt><dd>{new Date(evidence.created_at).toLocaleString('en-US')}</dd></div></dl>
      <p className="action-recording-note"><Icon name="shield" size={14}/>Operator-selected recordings do not establish capture order, live freshness or physical task completion. This result has no hardware motion authority.</p>
    </details>
  </section>;
}

export function ActionReviewPanel({ workspace, scene, online, pending, busy, readOnly, replayEvidence, onReview, onOpenTools }: {
  workspace: WorkspaceSnapshot | null; scene: SceneSnapshot | null; online: boolean; pending: boolean; busy: boolean;
  readOnly: boolean; replayEvidence?: RecordedActionEvidence;
  onReview: (data: ReviewInput) => Promise<void>; onOpenTools: () => void;
}) {
  const [before, setBefore] = useState<SelectedRecordedFrame | null>(null);
  const [expected, setExpected] = useState('');
  const [setupExpanded, setSetupExpanded] = useState(false);
  const reviewId = workspace?.review?.id;
  const pendingReview = workspace?.state === 'REVIEW_REQUIRED' && workspace.review?.verdict === 'PENDING';
  useEffect(() => {
    if (workspace?.review?.verdict === 'PENDING') setExpected(workspace.review.expected);
  }, [reviewId]);
  useEffect(() => { setSetupExpanded(pendingReview); }, [pendingReview, reviewId]);
  const latestEvidence = workspace?.review?.evidence ?? [...(workspace?.events ?? [])].reverse().find(event => event.record)?.record;
  const evidence = readOnly ? replayEvidence : latestEvidence;
  const readiness = pairReadiness({ workspace, scene, before, expected, online, pending });
  const editable = !readOnly && !busy && !pending;
  const after = before && scene?.frame && before.frame.id !== scene.frame.id && before.frame.sha256 !== scene.frame.sha256 ? scene.frame : null;

  if (readOnly) return evidence ? <div className="panel recorded-action-panel replay-record"><ActionEvidence evidence={evidence}/></div> : null;

  return <section className="panel recorded-action-panel" id="recorded-action-review" aria-label="Recorded action review">
    <div className="recorded-action-heading"><span className="action-heading-icon"><Icon name="spark" size={20}/></span><div><h2>Compare the result.</h2><p>Real MUSE review · operator-selected recordings</p></div><span className="action-mode-badge">Simulation only</span></div>
    <details className="action-setup" open={setupExpanded} onToggle={event => setSetupExpanded(event.currentTarget.open)}>
      <summary>{pendingReview ? 'Review the pending action' : 'Prepare a recorded pair'}<span>{before ? 'BEFORE selected' : 'Select images when ready'}</span><Icon name="chevron" size={15}/></summary>
      <div className="recorded-action-body">
      <p className="action-review-intro">Select a before image, upload an after image, and compare them with the expected result of one simulated action.</p>
      <div className="action-selection-row"><button className="action-secondary" disabled={!editable || !scene?.frame} onClick={() => setBefore(selectRecordedFrame(scene))}><Icon name="check" size={15}/>{before ? 'Replace BEFORE with current frame' : 'Use current frame as BEFORE'}</button><button className="action-secondary" disabled={!editable} onClick={onOpenTools}><Icon name="upload" size={15}/>Upload AFTER in Image tools</button>{before && <button className="action-clear" disabled={!editable} onClick={() => setBefore(null)}>Clear selection</button>}</div>
      {before && <div className="action-pair"><FramePreview frame={before.frame} label="BEFORE" empty="Select a before recording"/><FramePreview frame={after} label="AFTER" empty="Upload a different after recording"/></div>}
      {pendingReview && <label className="action-expected">Expected visual outcome <span>Bound to {workspace?.plan?.steps[workspace.current_step]?.label ?? 'the current action'}</span><textarea value={expected} rows={2} maxLength={1000} disabled={!editable} onChange={event => setExpected(event.target.value)} placeholder="Describe what should be visibly different after this action."/></label>}
      <div className="action-submit-row"><button className="action-review-submit" disabled={!readiness.ready || busy} onClick={() => { if (scene?.frame && before && workspace?.review) void onReview({ review_id: workspace.review.id, expected_scene_revision: scene.revision, before_frame_id: before.frame.id, after_frame_id: scene.frame.id, expected_visual: expected.trim() }); }}><Icon name="spark" size={17}/>{pending ? 'MUSE is reviewing…' : 'Review action with MUSE'}</button><p role={pending ? 'status' : undefined}>{readiness.reason}</p></div>
      <p className="action-recording-note"><Icon name="shield" size={14}/>Recorded pair, not a live action capture. MUSE can update simulation review; local stop and signal checks remain required.</p>
      </div>
    </details>
    {evidence && <div className="last-action-evidence"><span className="last-evidence-label">Last accepted recorded review</span><ActionEvidence evidence={evidence}/></div>}
  </section>;
}
