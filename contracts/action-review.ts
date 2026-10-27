import type { CommandBase, ReviewVerdict } from './workspace';

/** Operator-selected recordings support simulation review, never hardware authority. */
export interface RecordedFrameEvidence {
  id: string; image_url: string; sha256: string; width: number; height: number;
  source: 'uploaded' | 'recorded'; captured_at: string | null; received_at: string;
  timestamp_source: 'operator_provided' | 'unknown';
  map_id: string; map_version: string; map_hash: string;
}
export interface RecordedActionEvidence {
  id: string; source: 'meta'; input_kind: 'operator_selected_recorded_pair';
  applies_to: 'simulated_action_review'; simulation_only: true; motion_authority: false;
  created_at: string; model: string; prompt_version: string; schema_version: string;
  session_id: string; plan_id: string; plan_revision: number; action_id: string;
  review_id: string; input_workspace_revision: number; input_scene_revision: number;
  map_id: string; map_version: string; map_hash: string;
  before: RecordedFrameEvidence; after: RecordedFrameEvidence;
  expected_visual: string; server_action: {kind: string; label: string; description: string; node_id?: string};
  verdict: ReviewVerdict; observed: string; summary: string; limitations: string[];
  result: {verdict: ReviewVerdict; observed: string; summary: string; limitations: string[]};
  elapsed_ms: number; usage: null | {prompt_tokens: number | null; completion_tokens: number | null; total_tokens: number | null};
}
export interface RecordedActionReviewCommand extends CommandBase {
  review_id: string; expected_scene_revision: number;
  before_frame_id: string; after_frame_id: string; expected_visual: string;
}
/** POST /api/v1/action-reviews -> WorkspaceSnapshot. Independent scene inspection never advances a mission. */
