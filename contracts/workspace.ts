import type { MapRoute } from './scene';
import type { RecordedActionEvidence } from './action-review';
import type { LivePlanningEvidence, LiveActionEvidence, LiveSignalEvidence, SimulatedActionReceipt } from './live-intelligence';
export type DecisionEvidence = RecordedActionEvidence | LivePlanningEvidence | LiveActionEvidence | LiveSignalEvidence;
/** Versioned boundary for the hardware-free temporary-map workspace. */
export type MissionState = 'IDLE' | 'PLAN_READY' | 'READY' | 'REVIEW_REQUIRED' | 'WAITING_SIGNAL' | 'REOBSERVE' | 'COMPLETED' | 'CANCELLED' | 'FAULT' | 'RECOVERY_REQUIRED';
export type ProviderMode = 'demo' | 'meta';
export type SignalColor = 'RED' | 'GREEN' | 'UNKNOWN';
export type ReviewVerdict = 'PASS' | 'FAIL' | 'REOBSERVE' | 'UNKNOWN';
export interface PlanStep {
  id: string;
  label: string;
  description: string;
  kind: 'PUSH' | 'STOP' | 'CROSS' | 'VERIFY';
  status: 'pending' | 'current' | 'complete';
  node_id?: string;
  /** Binds simulated step status to drawing geometry, never to measured car pose. */
  route_segment_id?: string;
}
export interface EvidenceEvent {
  id: string;
  sequence: number;
  at: string;
  kind: string;
  title: string;
  detail: string;
  source: string;
  state: MissionState;
  record?: DecisionEvidence;
}
export interface WorkspaceSnapshot {
  schema_version: 'pushpilot.workspace.v1';
  session_id: string;
  revision: number;
  state: MissionState;
  mode: 'simulation';
  goal: null | {
    text: string;
    destination: string;
    summary: string;
    source: 'typed' | 'voice';
    provider: ProviderMode;
  };
  plan: null | { id: string; revision: number; steps: PlanStep[]; route: MapRoute; planning?: LivePlanningEvidence };
  planning_pending?: { request_id: string; source: 'meta' };
  action_receipt?: SimulatedActionReceipt;
  stop_receipt?: SimulatedActionReceipt;
  /** Bounded background observations only; never a physical stop command. */
  signal_watch?: {
    id: string;
    status: 'running' | 'green_admitted' | 'held' | 'cancelled' | 'exhausted' | 'interrupted';
    attempts: number;
    max_attempts: number;
    interval_seconds: number;
    max_duration_seconds: number;
    started_at: string;
    detail: string;
  };
  current_step: number;
  approved: boolean;
  stopped: boolean;
  signal: { color: SignalColor; source: 'simulation' | 'meta'; observed_at: string | null; junction_id: string | null; freshness_limit_ms?: number; evidence?: LiveSignalEvidence };
  review: null | {
    id: string;
    verdict: ReviewVerdict | 'PENDING';
    source: 'demo' | 'meta';
    expected: string;
    observed: string;
    summary: string;
    evidence?: RecordedActionEvidence | LiveActionEvidence;
  };
  next_check: string;
  capabilities: {
    robot: false;
    camera: false;
    registered_ar: false;
    muse_configured: boolean;
    voice: boolean;
    image_review: boolean;
    recorded_action_review: boolean;
    live_planning?: boolean;
    live_action_review?: boolean;
    muse_signal_review?: boolean;
    voice_transcription?: boolean;
  };
  events: EvidenceEvent[];
}

export interface CommandBase { request_id: string; expected_revision: number }
/**
 * GET /api/v1/state -> WorkspaceSnapshot
 * POST /api/v1/goals: CommandBase & {text, provider: ProviderMode, source?:'typed'|'voice'}
 * POST /api/v1/approve: CommandBase & {plan_id, plan_revision}
 * POST /api/v1/advance: CommandBase
 * POST /api/v1/signal: CommandBase & {color:SignalColor,junction_id?:string}
 * POST /api/v1/reviews: CommandBase & {review_id, verdict:ReviewVerdict}
 * POST /api/v1/action-reviews: RecordedActionReviewCommand (see action-review.ts)
 * POST /api/v1/live-signals/watch: CommandBase & {max_attempts?,interval_seconds?,max_duration_seconds?}
 * POST /api/v1/live-signals/watch/stop: CommandBase; cancels observations only
 * POST /api/v1/reobserve, /cancel, /reset: CommandBase
 * All successful mutations return WorkspaceSnapshot. HTTP409 rejects stale state.
 * Simulation review injection is explicitly demo-sourced; no hardware receipts.
 */
