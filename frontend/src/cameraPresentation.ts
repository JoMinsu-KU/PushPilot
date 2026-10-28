import type { LiveCameraSnapshot } from '../../contracts/live-camera';
import type { TemporaryMap } from '../../contracts/scene';

export interface LiveCameraAlert {
  kind: 'view_changed' | 'stale' | 'marker_disagreement';
  message: string;
}

/** Visibility is a compact diagnostic; contradictory or expired input remains prominent. */
export function liveCameraPresentation(snapshot: LiveCameraSnapshot | null, map: TemporaryMap | null, fresh: boolean) {
  const status = snapshot?.registration.status;
  const knownIds = new Set(map?.markers.map(marker => marker.id) ?? []);
  const count = new Set(snapshot?.detection.marker_ids.filter(id => knownIds.has(id)) ?? []).size;
  const markers = `${count}/${map?.markers.length ?? 4} markers`;
  const disagreement = status === 'locked_occluded' && snapshot?.registration.verification === 'marker_disagreement';
  const label = disagreement ? `Alignment conflict · ${markers}`
    : status === 'locked_occluded' ? `Alignment unverified · ${markers}`
    : status === 'locked' || status === 'locked_partial' ? `Fixed mapping · ${markers}`
    : status === 'view_changed' ? 'View changed · AR hidden' : 'Live view is not locked';
  const alerts: LiveCameraAlert[] = [];
  if (status === 'view_changed') alerts.push({ kind: 'view_changed', message: 'View changed. The previous overlay is hidden.' });
  if (!fresh) alerts.push({ kind: 'stale', message: 'STALE · Last decoded image. Route overlay is hidden.' });
  else if (disagreement) alerts.push({ kind: 'marker_disagreement', message: 'Visible markers disagree · check camera and map alignment.' });
  return { label, alerts };
}
