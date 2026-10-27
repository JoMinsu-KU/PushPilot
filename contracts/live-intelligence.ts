/** Explicit original-frame MUSE decisions; all execution remains simulation only. */
import type { CommandBase, ReviewVerdict, WorkspaceSnapshot } from './workspace';
import type { LiveCameraSnapshot } from './live-camera';

export type MapDirection = 'north' | 'east' | 'south' | 'west';
export interface RouteConstraints {
  departure: 'any' | MapDirection;
  /** Relative to the incoming route at the first junction, including straight. */
  first_turn: 'any' | 'left' | 'right' | 'straight';
  via_nodes: string[];
  avoid_nodes: string[];
}

export interface LivePlanCommand extends CommandBase {
  text: string;
  source: 'typed' | 'voice';
  /** Optional on /plans/live; this endpoint always uses the MUSE provider. */
  provider?: 'meta';
  /** Required for voice; must match the current workspace/map transcript binding. */
  transcript_id?: string;
  route_constraints?: RouteConstraints;
}
export type LiveAdvanceCommand = CommandBase;
export type LiveRunCommand = CommandBase;
export interface LiveActionReviewCommand extends CommandBase {
  review_id: string;
  expected_visual: string;
}
export type LiveReobserveCommand = CommandBase;
export type LiveSignalReviewCommand = CommandBase;
export interface LiveSignalWaitCommand extends CommandBase {
  /** Integer in 1..3, default 3; the request always has a finite attempt bound. */
  max_attempts?: number;
  /** Number in 0.5..10, default 2; the wait loop never runs as preview polling. */
  interval_seconds?: number;
}
export interface LiveSignalWatchCommand extends CommandBase {
  /** Integer in 1..60, default 30. */
  max_attempts?: number;
  /** Number in 0.5..10, default 2. */
  interval_seconds?: number;
  /** Number in 1..900, default 300; elapsed time also bounds inference. */
  max_duration_seconds?: number;
}
export type LiveSignalWatchStopCommand = CommandBase;
export interface LiveSignalWatchSnapshot {
  signal_watch: NonNullable<WorkspaceSnapshot['signal_watch']> | null;
  motion_authority: false;
}

export interface LiveMapIdentity {
  map_id: string;
  map_version: string;
  map_hash: string;
}
export interface LiveFrameEvidence extends NonNullable<LiveCameraSnapshot['frame']>, LiveMapIdentity {
  /** Durable observation identity; native_frame_id retains the preview identity. */
  id: string;
  native_frame_id: string;
  image_url: string;
  age_at_selection_ms: number;
  camera_id: string;
  epoch: string;
  timestamp_source: 'camera_host_receive';
  sensor_exposure_time_known: false;
  registration: LiveCameraSnapshot['registration'];
  motion_authority: false;
}

export interface LivePlanResult {
  destination: string;
  summary: string;
  /** Empty when clarification is required; otherwise a complete directed path. */
  route_nodes: string[];
  requires_clarification: boolean;
  constraints: RouteConstraints;
  scene_assessment: { status: 'clear' | 'uncertain'; detail: string };
}
export interface LiveActionResult {
  verdict: ReviewVerdict;
  observed: string;
  summary: string;
  limitations: string[];
}
export type LiveSignalResult = {
  color: 'RED' | 'GREEN'; visible: true; summary: string; limitations: string[];
} | {
  color: 'UNKNOWN'; visible: false; summary: string; limitations: string[];
};

export interface LiveDecisionBase extends LiveMapIdentity {
  id: string;
  request_id: string;
  source: 'meta';
  model: string;
  simulation_only: true;
  motion_authority: false;
  session_id: string;
  workspace_revision: number;
  elapsed_ms: number;
  /** Selected before inference, retained with the operation even on failure. */
  prompt_version: string;
  schema_version: string;
}
export interface LivePlanningEvidence extends LiveDecisionBase {
  input_kind: 'live_native_frame_and_graph';
  text: string;
  voice: null | {
    transcript_id: string;
    original_text: string;
    confirmed_text: string;
    audio_source: string;
  };
  frame: LiveFrameEvidence;
  result: LivePlanResult;
}
export interface SimulatedActionReceipt {
  id: string;
  source: 'simulation';
  kind: string;
  action_id: string;
  completed_at: string;
  physical_stop_verified: false;
}
export interface LiveActionEvidence extends LiveDecisionBase, LiveActionResult {
  input_kind: 'server_bound_live_pair';
  plan_id: string;
  plan_revision: number;
  action_id: string;
  review_id: string;
  action_receipt: SimulatedActionReceipt;
  server_action: Record<string, unknown>;
  before: LiveFrameEvidence;
  after: LiveFrameEvidence;
  expected_visual: string;
}
export interface SignalTarget {
  id: string;
  junction_id: string;
  approach_from: string;
  description: string;
  /** Drawing rectangle [x_min, y_min, x_max, y_max], never a robot target. */
  bounds_mm: [number, number, number, number];
}
export interface ProjectedSignalTarget extends SignalTarget {
  /** Server-derived hint; original image is still sent unchanged. */
  image_polygon: [number, number][];
  pixel_frame_id: string;
}
export type LiveSignalEvidence = LiveDecisionBase & LiveSignalResult & {
  input_kind: 'post_stop_live_frame';
  plan_id: string;
  plan_revision: number;
  stop_receipt: SimulatedActionReceipt;
  junction_id: string;
  approach_from: string;
  signal_target: SignalTarget;
  projected_signal_target: ProjectedSignalTarget;
  frame: LiveFrameEvidence;
};

export type LiveOperationKind = 'live-plans' | 'live-advance' | 'live-action-reviews' | 'live-reobserve' | 'live-signal-reviews' | 'live-run' | 'live-signal-wait' | 'live-signal-watch' | 'live-signal-watch-stop';
export interface LiveOperation {
  id: string;
  kind: LiveOperationKind;
  /** accepted describes the operation receipt, not vehicle success or permission. */
  status: 'pending' | 'accepted' | 'rejected' | 'interrupted';
  /** The immutable request context, extended with selected frame metadata before dispatch. */
  binding: Record<string, unknown>;
  result: LivePlanningEvidence | LiveActionEvidence | LiveSignalEvidence | null;
}
export interface LiveOperationsSnapshot {
  schema_version: 'pushpilot.live-operations.v1';
  motion_authority: false;
  operations: LiveOperation[];
}

/** Additional fields in live-backed workspace snapshots; legacy types remain valid. */
export type LiveWorkspaceSnapshot = Omit<WorkspaceSnapshot, 'plan' | 'signal' | 'review' | 'events'> & {
  planning_pending?: { request_id: string; source: 'meta' };
  plan: null | (NonNullable<WorkspaceSnapshot['plan']> & { planning?: LivePlanningEvidence });
  signal: Omit<WorkspaceSnapshot['signal'], 'source'> & {
    source: 'simulation' | 'meta'; evidence?: LiveSignalEvidence;
  };
  review: null | (Omit<NonNullable<WorkspaceSnapshot['review']>, 'evidence'> & {
    evidence?: NonNullable<WorkspaceSnapshot['review']>['evidence'] | LiveActionEvidence;
  });
  events: (Omit<WorkspaceSnapshot['events'][number], 'record'> & {
    record?: WorkspaceSnapshot['events'][number]['record'] | LivePlanningEvidence | LiveActionEvidence | LiveSignalEvidence;
  })[];
  action_receipt?: SimulatedActionReceipt;
  stop_receipt?: SimulatedActionReceipt;
};

/**
 * POST /api/v1/plans/live -> LiveWorkspaceSnapshot
 * POST /api/v1/live-actions/advance -> LiveWorkspaceSnapshot
 * POST /api/v1/live-actions/run -> LiveWorkspaceSnapshot (one action plus review)
 * POST /api/v1/live-actions/reviews -> LiveWorkspaceSnapshot
 * POST /api/v1/live-actions/reobserve -> LiveWorkspaceSnapshot
 * POST /api/v1/live-signals/reviews -> LiveWorkspaceSnapshot
 * POST /api/v1/live-signals/wait -> LiveWorkspaceSnapshot (finite attempt bound)
 * POST /api/v1/live-signals/watch -> LiveWorkspaceSnapshot (bounded background task)
 * POST /api/v1/live-signals/watch/stop -> LiveWorkspaceSnapshot (cancel observations)
 * GET /api/v1/live-signals/watch -> LiveSignalWatchSnapshot
 * GET /api/v1/live-intelligence/operations -> LiveOperationsSnapshot (latest 100)
 * GET /api/v1/live-evidence/frames/{id}/image -> unchanged private JPEG bytes
 *
 * Equal request IDs/payloads return their original receipt, not current state.
 * A pending duplicate never redispatches inference. Conflicting IDs fail.
 * A current GREEN may admit one simulated crossing; source remains meta.
 * This contract creates no physical robot, stop or vehicle-position authority.
 */
