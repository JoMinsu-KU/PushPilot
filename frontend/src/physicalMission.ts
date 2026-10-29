import type { PhysicalStartCommand, PhysicalStatus, PhysicalTelemetry } from '../../contracts/physical';
import type { WorkspaceSnapshot } from '../../contracts/workspace';

export type ExecutionMode = 'simulation' | 'physical';
const terminal = new Set(['COMPLETE', 'COMPLETED', 'CANCELLED', 'FAILED', 'FAULT', 'ERROR']);
const inactive = new Set(['IDLE', 'DISABLED', 'UNAVAILABLE', 'READY']);
const labels: Record<string, string> = {
  IDLE: 'Robot ready', READY: 'Robot ready', STARTING: 'Preparing the robot',
  RUNNING: 'Moving to destination', MOVING: 'Executing the route', APPROACHING: 'Approaching the car', PUSHING: 'Moving the car',
  CLEARING_VIEW: 'Clearing the camera view',
  OBSERVING: 'Checking the car', CORRECTING: 'Correcting the car',
  WAITING_SIGNAL: 'Waiting for green', RECONTACTING: 'Returning to contact',
  ALIGNING: 'Aligning at destination', RETURNING_HOME: 'Returning to start',
  COMPLETE: 'Mission complete', COMPLETED: 'Mission complete', HOLD: 'Mission held',
  HELD: 'Mission held', STOPPING: 'Stop requested', CANCELLED: 'Mission stopped',
  FAILED: 'Mission could not finish', FAULT: 'Mission could not finish', ERROR: 'Mission could not finish',
};

/** Reject incomplete/invented physical authority instead of defaulting absent fields to ready. */
export function parsePhysicalStatus(value: unknown): PhysicalStatus {
  const p = value as PhysicalStatus | null;
  const finite = (n: unknown) => typeof n === 'number' && Number.isFinite(n);
  if (!p || p.schema_version !== 'pushpilot.physical.v1'
    || typeof p.enabled !== 'boolean' || typeof p.available !== 'boolean'
    || typeof p.state !== 'string' || !/^[A-Z_]+$/.test(p.state)
    || !Number.isSafeInteger(p.revision) || p.revision < 0
    || !(p.mission_id === null || typeof p.mission_id === 'string')
    || !(p.destination === null || typeof p.destination === 'string')
    || typeof p.stage_label !== 'string'
    || !p.progress || !Number.isSafeInteger(p.progress.completed) || !Number.isSafeInteger(p.progress.total)
    || p.progress.completed < 0 || p.progress.total < p.progress.completed
    || !p.robot || typeof p.robot.connected !== 'boolean' || typeof p.robot.stationary !== 'boolean'
    || !p.car || typeof p.car.arrived !== 'boolean' || typeof p.car.aligned !== 'boolean'
    || !(p.car.heading_error_deg === null || finite(p.car.heading_error_deg))
    || !p.signal || !['RED', 'GREEN', 'UNKNOWN'].includes(p.signal.color) || typeof p.signal.waiting !== 'boolean'
    || typeof p.returning_home !== 'boolean' || !(p.error === null || typeof p.error === 'string')
    || !Array.isArray(p.blockers) || p.blockers.some(item => typeof item !== 'string')
    || !p.capabilities || typeof p.capabilities !== 'object' || Array.isArray(p.capabilities)
    || Object.entries(p.capabilities).some(([key, item]) => key === 'destinations'
      ? !Array.isArray(item) || item.some(id => typeof id !== 'string' || !id.trim() || id !== id.trim()) || new Set(item).size !== item.length
      : key === 'release_mode' ? item !== 'site_trial' && item !== 'qualified' : typeof item !== 'boolean')
    || p.telemetry !== undefined && !validTelemetry(p.telemetry)) {
    throw new Error('Robot status could not be verified.');
  }
  return p;
}

function validTelemetry(value: PhysicalTelemetry): boolean {
  const strings = (items: unknown) => Array.isArray(items) && items.every(item => typeof item === 'string');
  const stamp = (n: unknown) => typeof n === 'number' && Number.isFinite(n) && n >= 0;
  const nullableString = (s: unknown) => s === null || typeof s === 'string';
  if (!value || !Array.isArray(value.sequence) || !Array.isArray(value.history)) return false;
  if (value.sequence.some(step => !step || !step.id || typeof step.id !== 'string' || typeof step.label !== 'string'
    || typeof step.kind !== 'string' || typeof step.detail !== 'string' || !['pending', 'current', 'complete', 'held'].includes(step.status))) return false;
  if (new Set(value.sequence.map(step => step.id)).size !== value.sequence.length) return false;
  if (!nullableString(value.current_step_id) || value.current_step_id !== null && !value.sequence.some(step => step.id === value.current_step_id)) return false;
  if (value.history.some(event => !event || !event.id || typeof event.id !== 'string' || !stamp(event.at)
    || typeof event.title !== 'string' || typeof event.kind !== 'string' || typeof event.detail !== 'string' || typeof event.source !== 'string')) return false;
  if (value.review !== null && (!value.review || value.review.source !== 'meta' || typeof value.review.verdict !== 'string'
    || typeof value.review.summary !== 'string' || !stamp(value.review.observed_at) || !strings(value.review.frame_ids))) return false;
  return nullableString(value.signal_gate_id) && (value.signal_observed_at === null || stamp(value.signal_observed_at))
    && (value.distance_mm === null && value.distance_source === null || stamp(value.distance_mm) && value.distance_source === 'native_tcp');
}

/** No fallback to simulator records, even when an old simulator plan is complete. */
export function physicalTelemetry(status: PhysicalStatus | null, workspace: WorkspaceSnapshot | null, connected: boolean): PhysicalTelemetry | null {
  return connected && (physicalRunning(status) || physicalMatchesPlan(status, workspace)) ? status?.telemetry ?? null : null;
}

export function physicalProgress(status: PhysicalStatus | null, telemetry: PhysicalTelemetry | null): { completed: number; total: number } | null {
  return status?.mission_id && telemetry && status.progress.total > 0 ? status.progress : null;
}

export function physicalRouteContext(telemetry: PhysicalTelemetry | null, size = 3) {
  const steps = telemetry?.sequence ?? [];
  const current = steps.findIndex(step => step.id === telemetry?.current_step_id);
  const start = Math.min(Math.max(0, current - 1), Math.max(0, steps.length - size));
  return { start, steps: steps.slice(start, start + size) };
}

export function physicalReviewLabel(status: PhysicalStatus | null, telemetry: PhysicalTelemetry | null, connected: boolean): string {
  if (!connected) return 'Review unavailable';
  if (physicalVisionActive(status, connected, 'car')) return 'Checking car · MUSE';
  if (physicalVisionActive(status, connected, 'signal')) return 'Checking signal · MUSE';
  return telemetry?.review ? telemetry.review.verdict.replaceAll('_', ' ') : 'No robot review';
}

export const physicalModeLabel = (status: PhysicalStatus | null) => status?.capabilities.release_mode === 'site_trial' ? 'Robot · current-site test' : 'Robot';

export const physicalAvailable = (status: PhysicalStatus | null) => Boolean(status?.enabled && status.available);
export const physicalRunning = (status: PhysicalStatus | null) => Boolean(status?.mission_id && !terminal.has(status.state) && !inactive.has(status.state));
export const physicalFinished = (status: PhysicalStatus | null) => Boolean(status?.mission_id && terminal.has(status.state));
export const physicalParkingEnabled = (status: PhysicalStatus | null) => status?.capabilities.parking_alignment === true;

/** Destination readiness is advertised by the server, never inferred from a map or old arrival. */
export function physicalDestinationBlocker(status: PhysicalStatus | null, destination: string | null | undefined, label = destination): string | null {
  if (!Array.isArray(status?.capabilities.destinations)) return 'The robot service has not confirmed its available destinations.';
  if (!destination) return 'Choose a destination and review the MUSE route.';
  if (!status.capabilities.destinations.includes(destination)) return `${label || destination} is not available in the installed robot routes.`;
  return null;
}

export function physicalMatchesPlan(status: PhysicalStatus | null, workspace: WorkspaceSnapshot | null): boolean {
  return Boolean(status?.mission_id && workspace?.plan && status.plan_id === workspace.plan.id
    && status.plan_revision === workspace.plan.revision && status.workspace_session_id === workspace.session_id);
}

export function physicalTitle(status: PhysicalStatus | null, connected: boolean): string {
  if (!connected) return 'Robot status unavailable';
  if (!status) return 'Robot unavailable';
  if (['HOLD', 'HELD', 'STOPPING'].includes(status.state) || terminal.has(status.state)) return labels[status.state] ?? 'Mission ended';
  if (status.returning_home) return 'Returning to start';
  return labels[status.state] ?? 'Robot mission in progress';
}

/** Only an actual outstanding backend request enables the visual scanning treatment. */
export function physicalVisionActive(status: PhysicalStatus | null, connected: boolean, kind: 'signal' | 'car'): boolean {
  return Boolean(connected && status?.vision?.in_flight === true && status.vision.kind === kind);
}

export function physicalSignalLabel(status: PhysicalStatus | null, connected: boolean): string {
  if (!connected) return 'Status unavailable';
  if (!status) return 'No active wait';
  if (physicalVisionActive(status, connected, 'signal')) return 'Checking signal · MUSE';
  if (status.state === 'RECONTACTING') return 'Recontacting';
  if (status.signal.color === 'RED') return status.signal.waiting ? 'Red · Waiting' : 'Red observed';
  if (status.signal.color === 'GREEN') {
    const count = status.signal.stable_green_frames;
    const required = status.signal.required_green_frames;
    if (typeof count === 'number' && typeof required === 'number' && required > 0) {
      return count >= required ? 'Green confirmed' : `Confirming green (${count}/${required})`;
    }
    return 'Green observed';
  }
  return status.signal.waiting ? 'Waiting for green' : 'No active wait';
}

export function physicalDetail(status: PhysicalStatus | null, connected: boolean): string {
  if (!connected) return 'Live status is unavailable. Motion completion is not confirmed.';
  if (!status) return 'The robot service is not available.';
  if (status.error) return status.error;
  if (status.blockers.length) return status.blockers.join(' · ');
  if (status.state === 'HOLD' || status.state === 'HELD') return 'The executor has held further movement. The last completed action is preserved.';
  if (status.state === 'STOPPING') return 'Stop requested. Waiting for the robot to confirm its state.';
  if (status.returning_home && !terminal.has(status.state)) return 'The car remains at its destination while the empty tool returns.';
  if (status.state === 'WAITING_SIGNAL' || status.signal.waiting) return 'The robot stays stopped until a fresh green signal permits automatic continuation.';
  if (status.state === 'ALIGNING') return 'Checking the parking angle and applying bounded corrections.';
  if (['COMPLETE', 'COMPLETED'].includes(status.state)) {
    if (physicalParkingEnabled(status)) return status.car.arrived && status.car.aligned
      ? 'Car delivered and aligned. Check the robot status before preparing the next mission.'
      : 'The run has ended. Arrival and parking alignment are reported separately.';
    return status.car.arrived
      ? 'Car delivered. Check the robot status before preparing the next mission.'
      : 'The run has ended. Vehicle arrival is not confirmed.';
  }
  return status.stage_label || 'The executor checks the car after each complete movement.';
}

export function physicalDeliveryLabel(status: PhysicalStatus | null, connected: boolean): string {
  if (!connected) return 'Status unavailable';
  if (physicalVisionActive(status, connected, 'car')) return 'Checking car · MUSE';
  if (status?.returning_home && !['HOLD', 'HELD', 'STOPPING'].includes(status.state) && !terminal.has(status.state)) return 'Returning to start';
  // An actual server phase remains visible even if capability reporting changes mid-mission.
  if (status?.state === 'ALIGNING') return 'Aligning the car';
  if (status?.car.arrived) return physicalParkingEnabled(status) && status.car.aligned ? 'Parked and aligned' : 'Arrival confirmed';
  return 'Arrival pending';
}

export function physicalDeliveryDetail(status: PhysicalStatus | null, connected: boolean): string {
  if (!connected) return 'Car arrival and robot return are unconfirmed';
  if (physicalVisionActive(status, connected, 'car')) return 'Reading a fresh camera image';
  if (physicalParkingEnabled(status) && status?.car.arrived && !status.car.aligned) return 'Parking alignment not yet confirmed';
  return 'Car arrival and robot return tracked separately';
}

export function physicalStartCommand(workspace: WorkspaceSnapshot | null, status: PhysicalStatus | null, requestId: string): PhysicalStartCommand {
  if (!workspace?.plan || !workspace.goal || workspace.state !== 'PLAN_READY') throw new Error('Create and review a new route before starting the robot.');
  if (!physicalAvailable(status) || !status!.robot.connected || !status!.robot.stationary || physicalRunning(status)) throw new Error('The robot is not ready for a new mission.');
  if (workspace.goal.provider !== 'meta' || !workspace.plan.planning) throw new Error('A MUSE plan from the live view is required for a robot mission.');
  const plan = workspace.plan;
  const route = plan.route;
  if (route.destination !== workspace.goal.destination || !route.node_ids.length || route.node_ids.at(-1) !== route.destination) throw new Error('The route does not match the selected destination.');
  const destinationBlocker = physicalDestinationBlocker(status, route.destination);
  if (destinationBlocker) throw new Error(destinationBlocker);
  return {
    request_id: requestId, expected_revision: status!.revision, workspace_session_id: workspace.session_id,
    plan_id: plan.id, plan_revision: plan.revision, destination: route.destination,
    route_nodes: [...route.node_ids], map_id: route.map_id, map_version: route.map_version, map_hash: route.map_hash,
  };
}
