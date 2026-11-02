import type { PhysicalStatus } from '../../contracts/physical';
import type { WorkspaceSnapshot } from '../../contracts/workspace';
import { physicalMatchesPlan } from './physicalMission.ts';

export interface MissionApprovalFeedback {
  phase: 'awaiting' | 'submitting' | 'unconfirmed' | 'approved';
  title: string;
  detail: string;
  buttonLabel: string;
}

const interrupted = new Set(['HOLD', 'HELD', 'STOPPING', 'FAILED', 'FAULT', 'ERROR', 'CANCELLED']);
const acceptedPhases = new Set(['STARTING', 'RUNNING', 'MOVING', 'APPROACHING', 'PUSHING', 'CLEARING_VIEW',
  'OBSERVING', 'CORRECTING', 'WAITING_SIGNAL', 'RECONTACTING', 'ALIGNING', 'RETURNING_HOME']);

/** Display only: approval is server acceptance for this exact plan, not a click,
 * a simulation flag, successful movement or permission to recover from a fault.
 */
export function missionApprovalFeedback(status: PhysicalStatus | null, workspace: WorkspaceSnapshot | null,
  connected: boolean, canApprove: boolean, submitting = false, unconfirmed = false): MissionApprovalFeedback | null {
  const matched = physicalMatchesPlan(status, workspace);
  if (matched && (!connected || !status?.robot.connected || status.error || interrupted.has(status.state))) return null;
  if (matched && connected && status?.enabled && acceptedPhases.has(status.state) && !status.blockers.length) {
    return { phase: 'approved', title: 'Approved once',
      detail: 'After this, PushPilot resumes on its own when the signal and execution conditions allow.', buttonLabel: 'Approved' };
  }
  if (submitting && workspace?.state === 'PLAN_READY') return {
    phase: 'submitting', title: 'Approving plan', detail: 'Waiting for the server to accept this mission.', buttonLabel: 'Approving…',
  };
  if (unconfirmed && workspace?.state === 'PLAN_READY') return {
    phase: 'unconfirmed', title: 'Confirming approval', detail: 'Checking whether the server accepted this mission.', buttonLabel: 'Confirming…',
  };
  if (canApprove && connected && workspace?.state === 'PLAN_READY' && !status?.mission_id) return {
    phase: 'awaiting', title: 'Awaiting approval', detail: 'Review and explicitly approve this plan revision.', buttonLabel: 'Approve plan',
  };
  return null;
}
