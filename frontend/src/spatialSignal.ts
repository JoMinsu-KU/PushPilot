// Preview color only; a shown green is not crossing authority.
// Decide which signal color the 3D preview may show; display only, never admission.
import type { PhysicalStatus } from '../../contracts/physical';
import type { WorkspaceSnapshot } from '../../contracts/workspace';
import type { CitySignalState } from './citySignal';
import { displayMatchesStatus, type PhysicalDisplaySnapshot } from './physicalDisplay.ts';
import { physicalMatchesPlan } from './physicalMission.ts';

const ended = new Set(['COMPLETE', 'COMPLETED', 'HOLD', 'HELD', 'STOPPING', 'FAILED', 'FAULT', 'ERROR', 'CANCELLED', 'DISABLED', 'UNAVAILABLE', 'READY', 'IDLE']);

/** Visualizes source-bound signal evidence/admission; it cannot command a mission. */
export function spatialSignalState(status: PhysicalStatus | null, workspace: WorkspaceSnapshot | null,
  connected: boolean, snapshot: PhysicalDisplaySnapshot | null, nowSeconds: number): CitySignalState {
  if (!connected || !status?.enabled || !status.robot.connected || status.error || ended.has(status.state)
    || !physicalMatchesPlan(status, workspace) || !snapshot?.available || snapshot.feed_fresh !== true
    || !displayMatchesStatus(snapshot, status) || snapshot.map_hash !== workspace?.plan?.route.map_hash
    || !status.telemetry?.signal_gate_id || !Number.isFinite(nowSeconds)) return 'base';

  const observedAt = status.telemetry.signal_observed_at;
  if (typeof observedAt !== 'number' || !Number.isFinite(observedAt) || observedAt <= 0 || observedAt > nowSeconds) return 'base';
  const phase = snapshot.signal.phase;
  // Accepted single-departure admission survives the normal recontact counter reset.
  // This indicates approval, not a claim that an old image is still a live color observation.
  if (phase === 'recontacting' || phase === 'passed') return 'green-approved';

  const checkingSignal = status.vision?.in_flight && status.vision.kind === 'signal';
  // RED describes the server's current stopped wait, never a new admission or local classifier.
  if (status.state === 'WAITING_SIGNAL' && status.signal.waiting && status.signal.color === 'RED' && status.robot.stationary
    && phase === 'waiting' && snapshot.phase === 'signal_wait' && !checkingSignal) return 'red-observed';

  // The server owns the configured image-age/admission budget. Do not invent a second UI timeout.
  if (phase !== 'admitted' || status.signal.color !== 'GREEN' || status.signal.waiting
    || checkingSignal) return 'base';
  const count = status.signal.stable_green_frames, required = status.signal.required_green_frames;
  return typeof count === 'number' && typeof required === 'number' && Number.isSafeInteger(count)
    && Number.isSafeInteger(required) && required > 0 && count >= required ? 'green-approved' : 'base';
}
