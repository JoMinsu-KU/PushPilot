import type { LiveCameraSnapshot } from '../../contracts/live-camera';
import type { TemporaryMap } from '../../contracts/scene';

export interface LiveCameraAlert {
  kind: 'view_changed' | 'stale';
  message: string;
}

/** Keep marker detection changes in compact diagnostics, separate from withdrawn views and stale images. */
export function liveCameraPresentation(snapshot: LiveCameraSnapshot | null, map: TemporaryMap | null, fresh: boolean) {
  const status = snapshot?.registration.status;
  const knownIds = new Set(map?.markers.map(marker => marker.id) ?? []);
  const count = new Set(snapshot?.detection.marker_ids.filter(id => knownIds.has(id)) ?? []).size;
  const markers = `${count}/${map?.markers.length ?? 4} markers`;
  const disagreement = status === 'locked_occluded' && snapshot?.registration.verification === 'marker_disagreement';
  const label = disagreement ? 'Alignment conflict'
    : status === 'locked' || status === 'locked_partial' || status === 'locked_occluded' ? 'Fixed mapping'
    : status === 'view_changed' ? 'View changed · AR hidden' : 'Live view is not locked';
  const detail = `${markers} visible. ${disagreement ? 'Visible evidence conflicts with the fixed reference.'
    : status === 'locked_occluded' ? 'Fixed reference retained; current alignment is unverified while markers are covered.'
    : status === 'locked' || status === 'locked_partial' ? 'Visible markers support the fixed reference.'
    : 'A valid fixed reference is required for the route overlay.'}`;
  const alerts: LiveCameraAlert[] = [];
  if (status === 'view_changed') alerts.push({ kind: 'view_changed', message: 'View changed. The previous overlay is hidden.' });
  if (!fresh) alerts.push({ kind: 'stale', message: 'STALE · Last decoded image. Route overlay is hidden.' });
  return { label, detail, alerts };
}
