/** Server-qualified route identifiers. An absent list grants no destination authority. */
export interface PhysicalCapabilities {
  destinations?: string[];
  /** Only an explicit true advertises destination parking alignment. */
  parking_alignment?: boolean;
  release_mode?: 'site_trial' | 'qualified';
  [key: string]: boolean | string[] | 'site_trial' | 'qualified' | undefined;
}

export interface PhysicalSequenceStep {
  id: string;
  label: string;
  kind: string;
  status: 'pending' | 'current' | 'complete' | 'held';
  detail: string;
}

export interface PhysicalHistoryEvent {
  id: string;
  /** Unix seconds, recorded by the executor. */
  at: number;
  kind: string;
  title: string;
  detail: string;
  source: string;
}

export interface PhysicalTelemetry {
  sequence: PhysicalSequenceStep[];
  current_step_id: string | null;
  history: PhysicalHistoryEvent[];
  review: { verdict: string; summary: string; observed_at: number; source: 'meta'; frame_ids: string[] } | null;
  signal_gate_id: string | null;
  signal_observed_at: number | null;
  /** Measured TCP travel only. Never drawing distance or inferred car travel. */
  distance_mm: number | null;
  distance_source: 'native_tcp' | null;
}

/** Separate physical authority. A simulation workspace never grants robot motion. */
export interface PhysicalStatus {
  schema_version: 'pushpilot.physical.v1';
  enabled: boolean;
  available: boolean;
  state: string;
  revision: number;
  mission_id: string | null;
  destination: string | null;
  plan_id?: string | null;
  plan_revision?: number | null;
  workspace_session_id?: string | null;
  stage_label: string;
  progress: { completed: number; total: number; step_index?: number };
  robot: { connected: boolean; stationary: boolean; at_start?: boolean };
  car: { arrived: boolean; aligned: boolean; heading_error_deg: number | null };
  signal: { color: 'RED' | 'GREEN' | 'UNKNOWN'; waiting: boolean; stable_green_frames?: number; required_green_frames?: number };
  vision?: { in_flight: boolean; kind: 'signal' | 'car' | null; started_at: number | null; last_result_at: number | null; summary: string | null };
  returning_home: boolean;
  error: string | null;
  blockers: string[];
  capabilities: PhysicalCapabilities;
  telemetry?: PhysicalTelemetry;
}

export interface PhysicalStartCommand {
  request_id: string;
  expected_revision: number;
  workspace_session_id: string;
  plan_id: string;
  plan_revision: number;
  destination: string;
  route_nodes: string[];
  map_id: string;
  map_version: string;
  map_hash: string;
}
