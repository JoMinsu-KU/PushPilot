import type { MapRoute, TemporaryMap } from '../../contracts/scene';
import type { LiveCameraSnapshot } from '../../contracts/live-camera';

export const LIVE_FRESHNESS_LIMIT_MS = 1500;

/** Successful explicit locks supersede only requests already in flight, never future server state. */
export function createLivePollGate() {
  let generation = 0;
  return {
    begin: () => generation,
    registrationApplied: () => { generation += 1; },
    accept: (startedGeneration: number, snapshot: LiveCameraSnapshot): LiveCameraSnapshot | null =>
      startedGeneration === generation ? snapshot : null,
  };
}

/** Withhold old decoded geometry immediately when the server withdraws its registration. */
export function liveDisplaySnapshot(decoded: LiveCameraSnapshot | null, latest: LiveCameraSnapshot | null): LiveCameraSnapshot | null {
  if (!decoded || !latest) return decoded;
  const sameIdentity = decoded.epoch === latest.epoch && decoded.camera_id === latest.camera_id
    && decoded.map_id === latest.map_id && decoded.map_version === latest.map_version && decoded.map_hash === latest.map_hash
    && decoded.frame?.width === latest.frame?.width && decoded.frame?.height === latest.frame?.height;
  if (sameIdentity && decoded.registration.id === latest.registration.id && latest.registration.status !== 'view_changed') return decoded;
  return { ...decoded, registration: { ...latest.registration, homography: null } };
}

/** Start the monotonic clock before the request; transport and JPEG decode cannot refresh an old frame. */
export function liveFrameAge(snapshot: LiveCameraSnapshot | null, receivedAt: number, now: number): number {
  if (!snapshot?.frame || !Number.isFinite(snapshot.frame.age_ms)) return Infinity;
  return Math.max(0, snapshot.frame.age_ms) + Math.max(0, now - receivedAt);
}

export function liveFrameFresh(snapshot: LiveCameraSnapshot | null, receivedAt: number, now: number): boolean {
  return Boolean(snapshot?.enabled && snapshot.state === 'live' && snapshot.frame
    && liveFrameAge(snapshot, receivedAt, now) <= (snapshot.freshness_limit_ms ?? LIVE_FRESHNESS_LIMIT_MS));
}

/** Camera pixels, marker positions and the planned route share this exact frame geometry. */
export function liveOverlayAllowed(snapshot: LiveCameraSnapshot, route: MapRoute | null, map: TemporaryMap | null, fresh: boolean): boolean {
  return Boolean(fresh && map && route && snapshot.registration.homography
    && ['locked', 'locked_partial', 'locked_occluded'].includes(snapshot.registration.status)
    && snapshot.map_id === map.id && snapshot.map_version === map.version && snapshot.map_hash === map.geometry_hash
    && route.map_id === map.id && route.map_version === map.version && route.map_hash === map.geometry_hash);
}
