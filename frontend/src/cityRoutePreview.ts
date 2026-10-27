import type { TemporaryMap } from '../../contracts/scene.ts';
import type { Point } from './projection.ts';

export interface CityPreviewFit { left: number; top: number; width: number; height: number }
export interface CityProjection { width: number; height: number; matrix: number[] }

// Display-only road envelope from the supplied GLB. This is not a registration.
const cityRoadEnvelope = { width: 472, depth: 298, elevation: 2 };

/** Fit the complete active graph, never the selected route or old place IDs. */
export function cityPreviewFit(map: TemporaryMap | null): CityPreviewFit | null {
  if (!map?.nodes.length || map.nodes.some(node => !Number.isFinite(node.x_mm) || !Number.isFinite(node.y_mm))) return null;
  const xs = map.nodes.map(node => node.x_mm), ys = map.nodes.map(node => node.y_mm);
  const left = Math.min(...xs), top = Math.min(...ys);
  const width = Math.max(...xs) - left, height = Math.max(...ys) - top;
  return width > 0 && height > 0 ? { left, top, width, height } : null;
}

/** Preserve 2D route order and direction in an explicitly unaligned city preview. */
export function projectCityPreview(point: Point, fit: CityPreviewFit, view: CityProjection): Point | null {
  const m = view.matrix;
  if (m.length !== 16 || !m.every(Number.isFinite) || !point.every(Number.isFinite)
    || !Number.isFinite(view.width) || !Number.isFinite(view.height) || view.width <= 0 || view.height <= 0
    || ![fit.left, fit.top, fit.width, fit.height].every(Number.isFinite) || fit.width <= 0 || fit.height <= 0) return null;
  const x = ((point[0] - fit.left) / fit.width - .5) * cityRoadEnvelope.width;
  const y = cityRoadEnvelope.elevation;
  const z = ((point[1] - fit.top) / fit.height - .5) * cityRoadEnvelope.depth;
  const w = m[3] * x + m[7] * y + m[11] * z + m[15];
  const depth = m[2] * x + m[6] * y + m[10] * z + m[14];
  if (w <= 0 || depth < -w || depth > w) return null;
  const px = m[0] * x + m[4] * y + m[8] * z + m[12];
  const py = m[1] * x + m[5] * y + m[9] * z + m[13];
  return [(px / w + 1) * view.width / 2, (1 - py / w) * view.height / 2];
}
