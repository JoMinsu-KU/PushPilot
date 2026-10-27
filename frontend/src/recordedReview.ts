import type { SceneSnapshot } from '../../contracts/scene';
import type { WorkspaceSnapshot } from '../../contracts/workspace';

export interface SelectedRecordedFrame {
  frame: NonNullable<SceneSnapshot['frame']>;
  map_id: string;
  map_version: string;
  map_hash: string;
}

export function selectRecordedFrame(scene: SceneSnapshot | null): SelectedRecordedFrame | null {
  return scene?.frame ? { frame: scene.frame, map_id: scene.map_id, map_version: scene.map_version, map_hash: scene.map_hash } : null;
}

/** Selection is an operator assertion, not proof of capture order or physical motion. */
export function pairReadiness({ workspace, scene, before, expected, online, pending }: {
  workspace: WorkspaceSnapshot | null; scene: SceneSnapshot | null;
  before: SelectedRecordedFrame | null; expected: string; online: boolean; pending: boolean;
}): { ready: boolean; reason: string } {
  const blocked = (reason: string) => ({ ready: false, reason });
  if (pending) return blocked('MUSE is reviewing this recorded pair. You can still end the simulation.');
  if (!online || !workspace) return blocked('Connect to the mission backend before requesting a review.');
  if (!workspace.capabilities.muse_configured) return blocked('Configure the backend Meta API key to review a recorded pair.');
  if (!workspace.capabilities.recorded_action_review) return blocked('Recorded action review is unavailable from this backend.');
  if (workspace.state !== 'REVIEW_REQUIRED' || workspace.review?.verdict !== 'PENDING') return blocked('Run a simulated action to open its action-bound review.');
  if (!before) return blocked('Select a BEFORE recording, then upload a different AFTER recording.');
  if (!scene?.frame) return blocked('Upload an AFTER recording using Image tools.');
  const route = workspace.plan?.route;
  if (!route || before.map_id !== scene.map_id || before.map_version !== scene.map_version || before.map_hash !== scene.map_hash ||
      route.map_id !== scene.map_id || route.map_version !== scene.map_version || route.map_hash !== scene.map_hash) {
    return blocked('The selected recordings and active plan must belong to the current map. Select a new pair.');
  }
  if (before.frame.id === scene.frame.id) return blocked('Upload a different AFTER recording using Image tools.');
  if (before.frame.sha256 === scene.frame.sha256) return blocked('BEFORE and AFTER contain identical image bytes. Choose a genuinely different recording.');
  if (!expected.trim()) return blocked('Describe the visible result MUSE should compare with the recordings.');
  if (expected.trim().length > 1000) return blocked('Keep the expected visual outcome within 1,000 characters.');
  return { ready: true, reason: 'This explicit request reviews the selected pair for the pending simulated action.' };
}

export function recordedCaptureLabel(frame: Pick<NonNullable<SceneSnapshot['frame']>, 'captured_at' | 'timestamp_source'>): string {
  if (!frame.captured_at || frame.timestamp_source === 'unknown') return 'Capture time unknown';
  const date = new Date(frame.captured_at);
  return Number.isNaN(date.valueOf()) ? 'Capture time unknown' : `Captured ${date.toLocaleString('en-US')}`;
}
