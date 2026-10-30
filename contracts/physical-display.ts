/** Read-only illustration from confirmed executor evidence, never car tracking. */
export interface PhysicalDisplay {
  schema_version: 'pushpilot.physical-display.v1';
  available: boolean;
  reason: string | null;
  /** Changes when only the optional display producer restarts. */
  producer_epoch: string;
  sequence: number;
  captured_at: string;
  mission_id: string | null;
  plan_id: string | null;
  plan_revision: number | null;
  workspace_session_id: string | null;
  map_hash: string | null;
  state: string;
  phase: 'idle' | 'pending' | 'contact' | 'approach' | 'withdraw' | 'wrist'
    | 'recontact' | 'signal_wait' | 'muse_review' | 'return' | 'hold'
    | 'complete' | 'unavailable';
  primitive_id: string | null;
  stage_id: string | null;
  stage_index: number | null;
  stage_count: number | null;
  stage_status: 'intent' | 'confirmed' | 'none';
  animation_authority: 'confirmed_only';
  motion_authority: false;
  vehicle: {
    estimated: true;
    /** Brief receipt-driven tween only. Never advances from an intent or clock. */
    moving: boolean;
    route_fraction: number | null;
    /** Direction-compressed map route legs: B one; C and D three. */
    route_leg_index: number | null;
    leg_fraction: number | null;
    heading: 'EAST' | 'NORTH' | 'WEST' | 'SOUTH' | null;
    confirmed_contact_stages: number;
    total_contact_stages: number;
    last_confirmed_at: string | null;
  };
  signal: {
    phase: 'none' | 'waiting' | 'confirming' | 'admitted' | 'recontacting' | 'passed';
    green_count: number;
    green_required: number;
  };
}
