import type { MapRoute } from './scene';
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
  plan: null | { id: string; revision: number; steps: PlanStep[]; route: MapRoute };
  current_step: number;
  approved: boolean;
  stopped: boolean;
  signal: { color: SignalColor; source: 'simulation'; observed_at: string | null; junction_id: string | null };
  review: null | {
    id: string;
    verdict: ReviewVerdict | 'PENDING';
    source: 'demo' | 'meta';
    expected: string;
    observed: string;
    summary: string;
  };
  next_check: string;
  capabilities: {
    robot: false;
    camera: false;
    registered_ar: false;
    muse_configured: boolean;
    voice: boolean;
    image_review: boolean;
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
 * POST /api/v1/reobserve, /cancel, /reset: CommandBase
 * All successful mutations return WorkspaceSnapshot. HTTP409 rejects stale state.
 * Simulation review injection is explicitly demo-sourced; no hardware receipts.
 */
