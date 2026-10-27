import type { TemporaryMap } from '../../contracts/scene';
import { projectPoint, type Point } from './projection.ts';

export interface RecordedDisplay {
  /** The display-only bounding region, in original image pixels. */
  viewport: [number, number, number, number];
  /** The paper mask, in the same original pixels as the image and route. */
  quad: Point[] | null;
}

const usableRegistration = new Set(['locked', 'locked_partial', 'locked_occluded']);
const PAPER_PADDING_MM = 3;

/** The common display geometry of recorded and live frames; never motion data. */
export interface BoardDisplayInput {
  map_id: string; map_version: string; map_hash: string;
  frame: { width: number; height: number } | null;
  registration: { status: string; homography: number[][] | null };
}

export interface BoardBounds { left: number; top: number; width: number; height: number }
export function boardPresentationBounds(map: TemporaryMap): BoardBounds | null {
  if (![map.board.width_mm, map.board.height_mm].every(value => Number.isFinite(value) && value > 0)
    || map.markers.some(marker => ![...marker.center_mm, marker.size_mm].every(Number.isFinite) || marker.size_mm <= 0)) return null;
  const left = Math.min(0, ...map.markers.map(marker => marker.center_mm[0] - marker.size_mm / 2)) - PAPER_PADDING_MM;
  const top = Math.min(0, ...map.markers.map(marker => marker.center_mm[1] - marker.size_mm / 2)) - PAPER_PADDING_MM;
  const right = Math.max(map.board.width_mm, ...map.markers.map(marker => marker.center_mm[0] + marker.size_mm / 2)) + PAPER_PADDING_MM;
  const bottom = Math.max(map.board.height_mm, ...map.markers.map(marker => marker.center_mm[1] + marker.size_mm / 2)) + PAPER_PADDING_MM;
  return { left, top, width: right - left, height: bottom - top };
}

function convexQuad(points: Point[]): boolean {
  const crosses = points.map((point, index) => {
    const next = points[(index + 1) % 4], after = points[(index + 2) % 4];
    return (next[0] - point[0]) * (after[1] - next[1]) - (next[1] - point[1]) * (after[0] - next[0]);
  });
  if (!(crosses.every(value => value > 1e-6) || crosses.every(value => value < -1e-6))) return false;
  const area = Math.abs(points.reduce((sum, point, index) => {
    const next = points[(index + 1) % 4];
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0)) / 2;
  return Number.isFinite(area) && area >= 1024;
}

/**
 * Fit a display mask around the working board and its printed fiducials.
 * This never changes image bytes, the homography, marker points or route points.
 * A missing/changed/unusable mapping always displays the full original frame.
 */
export function recordedDisplay(scene: BoardDisplayInput, map: TemporaryMap | null, focused: boolean): RecordedDisplay {
  const frame = scene.frame;
  if (!frame) return { viewport: [0, 0, 1, 1], quad: null };
  if (![frame.width, frame.height].every(value => Number.isFinite(value) && value > 0)) return { viewport: [0, 0, 1, 1], quad: null };
  const full: RecordedDisplay = { viewport: [0, 0, frame.width, frame.height], quad: null };
  const matrix = scene.registration.homography;
  if (!focused || !map || !matrix || !usableRegistration.has(scene.registration.status)
    || scene.map_id !== map.id || scene.map_version !== map.version || scene.map_hash !== map.geometry_hash) return full;
  if (!Array.isArray(matrix) || matrix.length !== 3 || matrix.some(row => !Array.isArray(row) || row.length !== 3 || row.some(value => !Number.isFinite(value)))) return full;
  const board = boardPresentationBounds(map);
  if (!board) return full;
  const { left, top } = board, right = left + board.width, bottom = top + board.height;
  const bounds: Point[] = [[left, top], [right, top], [right, bottom], [left, bottom]];
  const corners = bounds.map(point => projectPoint(point, matrix));
  if (!corners.every((point): point is Point => point !== null)) return full;

  // A projective horizon inside the rectangle is not a continuous visible board.
  const denominators = bounds.map(([x, y]) => matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]);
  if (!(denominators.every(value => value > 1e-9) || denominators.every(value => value < -1e-9)) || !convexQuad(corners)) return full;
  const minX = Math.min(...corners.map(point => point[0])), maxX = Math.max(...corners.map(point => point[0]));
  const minY = Math.min(...corners.map(point => point[1])), maxY = Math.max(...corners.map(point => point[1]));
  const margin = Math.max(maxX - minX, maxY - minY) * .012;
  const x = Math.max(0, minX - margin), y = Math.max(0, minY - margin);
  const width = Math.min(frame.width, maxX + margin) - x, height = Math.min(frame.height, maxY + margin) - y;
  return width >= 32 && height >= 32 ? { viewport: [x, y, width, height], quad: corners } : full;
}
