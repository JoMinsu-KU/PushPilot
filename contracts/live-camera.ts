/** Ephemeral live preview; no mission revision, persisted evidence or motion authority. */
import type {SceneSnapshot} from './scene';

export interface LiveCameraSnapshot {
  schema_version: 'pushpilot.live-camera.v1';
  enabled: boolean;
  state: 'connecting' | 'live' | 'stale' | 'unavailable';
  camera_id: string | null;
  epoch: string | null;
  frame: null | {
    id: string; image_url: string; width: number; height: number; source: 'live';
    received_at: string; age_ms: number; sha256: string; sequence: number;
  };
  map_id: string; map_version: string; map_hash: string;
  detection: SceneSnapshot['detection'];
  registration: {
    status: 'unregistered' | 'candidate' | 'locked' | 'locked_partial' | 'locked_occluded' | 'view_changed';
    id: string | null; reference_frame_id: string | null;
    homography: number[][] | null; residual_px: number | null; message: string;
  };
  freshness_limit_ms: number;
  last_error: string | null;
  motion_authority: false;
  saved_reference_available?: boolean;
}

/** GET /api/v1/live-camera; GET frame.image_url returns native JPEG cache bytes.
 * POST /api/v1/live-camera/registration: {epoch, frame_id} explicitly locks a
 * fresh consistent four-marker view. A saved reference remains display-only.
 * POST /api/v1/live-camera/registration/resume: {epoch} requests reuse of the
 * server-held fixed reference after its identity and visible-marker checks.
 * received_at is camera-host JPEG dequeue time, not sensor exposure time.
 */
