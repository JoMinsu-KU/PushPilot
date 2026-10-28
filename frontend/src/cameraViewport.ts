/** Display-only movement shared by the original camera image and its overlays. */
export interface CameraViewport {
  zoom: number;
  /** Translation as a fraction of the full viewport width, independent of zoom. */
  panX: number;
  /** Translation as a fraction of the full viewport height, independent of zoom. */
  panY: number;
}

export const MIN_CAMERA_ZOOM = 0.5;
export const MAX_CAMERA_ZOOM = 4;
export const DEFAULT_CAMERA_VIEWPORT: Readonly<CameraViewport> = Object.freeze({ zoom: 1, panX: 0, panY: 0 });

type Midpoint = readonly [number, number];
const MAX_EVENT_COORDINATE = 1_000_000;

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function panLimit(zoom: number): number {
  // Keep a recoverable portion of the plane within reach at every supported zoom.
  return zoom / 2 + 0.25;
}

function midpoint(value: unknown): Midpoint | null {
  if (!Array.isArray(value) || value.length !== 2 || !value.every(finite)) return null;
  // Real centered pointer coordinates are normally within [-0.5, 0.5]. Bound
  // malformed but finite event magnitudes before any scale multiplication.
  return [clamp(value[0], -MAX_EVENT_COORDINATE, MAX_EVENT_COORDINATE),
    clamp(value[1], -MAX_EVENT_COORDINATE, MAX_EVENT_COORDINATE)];
}

export function normalizeCameraViewport(view: unknown): CameraViewport {
  const values = view && typeof view === 'object' ? view as Partial<CameraViewport> : {};
  const zoom = finite(values.zoom) ? clamp(values.zoom, MIN_CAMERA_ZOOM, MAX_CAMERA_ZOOM) : 1;
  const limit = panLimit(zoom);
  return {
    zoom,
    panX: finite(values.panX) ? clamp(values.panX, -limit, limit) : 0,
    panY: finite(values.panY) ? clamp(values.panY, -limit, limit) : 0,
  };
}

/** Preserve the source point under a centered, viewport-normalized pointer. */
export function zoomCameraViewport(
  view: unknown, newZoom: number, anchorNormalizedCentered: Midpoint = [0, 0],
): CameraViewport {
  const current = normalizeCameraViewport(view);
  const anchor = midpoint(anchorNormalizedCentered);
  if (!finite(newZoom) || !anchor) return current;
  const zoom = clamp(newZoom, MIN_CAMERA_ZOOM, MAX_CAMERA_ZOOM);
  const ratio = zoom / current.zoom;
  return normalizeCameraViewport({
    zoom,
    panX: anchor[0] - (anchor[0] - current.panX) * ratio,
    panY: anchor[1] - (anchor[1] - current.panY) * ratio,
  });
}

export function panCameraViewport(view: unknown, dxNormalized: number, dyNormalized: number): CameraViewport {
  const current = normalizeCameraViewport(view);
  if (!finite(dxNormalized) || !finite(dyNormalized)) return current;
  return normalizeCameraViewport({
    zoom: current.zoom,
    panX: current.panX + clamp(dxNormalized, -MAX_EVENT_COORDINATE, MAX_EVENT_COORDINATE),
    panY: current.panY + clamp(dyNormalized, -MAX_EVENT_COORDINATE, MAX_EVENT_COORDINATE),
  });
}

/** Apply pinch scale and midpoint travel together, from the gesture's start view. */
export function pinchCameraViewport(
  view: unknown, startMidpoint: Midpoint, currentMidpoint: Midpoint, ratio: number,
): CameraViewport {
  const current = normalizeCameraViewport(view);
  const start = midpoint(startMidpoint), end = midpoint(currentMidpoint);
  if (!start || !end || !finite(ratio) || ratio <= 0) return current;
  const effectiveRatio = clamp(ratio, MIN_CAMERA_ZOOM / current.zoom, MAX_CAMERA_ZOOM / current.zoom);
  return normalizeCameraViewport({
    zoom: current.zoom * effectiveRatio,
    panX: end[0] - (start[0] - current.panX) * effectiveRatio,
    panY: end[1] - (start[1] - current.panY) * effectiveRatio,
  });
}
