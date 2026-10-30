import type { TemporaryMap } from '../../contracts/scene';
import type { Point } from './projection.ts';
import type { RouteDisplay } from './routeProgress.ts';

/**
 * Display-only car for the Spatial view. Its position follows simulated step progress along the drawn route,
 * never a measured car pose. When robot timing or a measured pose reaches the workspace, replace the nominal
 * speed and progress here rather than in the 3D view.
 */
// Nominal push speed: the robot-control service's default max_speed_mm_s; not a measured robot speed.
export const SIMULATED_PUSH_SPEED_MM_S = 5;
// Display car size in drawing millimetres: the demo video's hatchback (76 × 32 × 28.5 mm) scaled uniformly to the real
// car's ~18 mm body width (docs/PUSH_ALIGNMENT.md). Real length and height are not recorded; the video proportions stand in.
const VIDEO_CAR_MM = { length: 76, width: 32, height: 28.5 } as const;
export const SIMULATED_CAR_SCALE = 18 / VIDEO_CAR_MM.width;
export const SIMULATED_CAR_MM = {
  length: 45, width: 18, height: 15,
} as const;

export interface CarTrack {
  /** Route identity: a changed key places the car without animating from the old route. */
  key: string;
  path: Point[];
  /** Distance of the car's centre along `path`: centred on the start, front at a push's end, centre at a crossing's exit. */
  distance_mm: number;
}

const HEADINGS: Record<NonNullable<TemporaryMap['start_heading']>, Point> = { east: [1, 0], south: [0, 1], west: [-1, 0], north: [0, -1] };
// A pushed segment counts as travelled once its action ran, including while its review is pending.
const TRAVELLED = new Set(['complete', 'review']);

export function simulatedCarTrack(map: TemporaryMap | null, display: RouteDisplay | null): CarTrack | null {
  if (display?.segments.length) {
    const path: Point[] = [];
    let distance = 0, reached = true, last: RouteDisplay['segments'][number] | null = null;
    for (const segment of display.segments) {
      path.push(...(path.length ? segment.points_mm.slice(1) : segment.points_mm));
      reached = reached && TRAVELLED.has(segment.phase);
      if (reached) { distance += segment.length_mm; last = segment; }
    }
    const key = display.segments.map(segment => segment.id).join('|') + `@${path[0].join(',')}>${path.at(-1)!.join(',')}`;
    // A push ends at a stop line or the destination, where the front bumper stops; after a crossing the car has
    // turned onto the exit road with its centre on the exit point.
    const end = Math.min(distance, pathLength(path));
    return { key, path, distance_mm: last?.kind === 'push' ? Math.max(0, end - SIMULATED_CAR_MM.length / 2) : end };
  }
  const start = map?.nodes.find(node => node.id === map.start);
  if (!start || !Number.isFinite(start.x_mm) || !Number.isFinite(start.y_mm)) return null;
  const [dx, dy] = HEADINGS[map!.start_heading ?? 'east'];
  return { key: `start:${map!.id}:${start.id}`, path: [[start.x_mm, start.y_mm], [start.x_mm + dx, start.y_mm + dy]], distance_mm: 0 };
}

export function pathLength(path: Point[]): number {
  return path.slice(1).reduce((length, next, index) => length + Math.hypot(next[0] - path[index][0], next[1] - path[index][1]), 0);
}

/** Point and unit travel direction at `distance` along the path (clamped to its ends). */
export function pointAlong(path: Point[], distance: number): { at: Point; heading: Point } {
  let left = Math.max(0, distance), heading: Point = [1, 0];
  for (let index = 1; index < path.length; index += 1) {
    const [ax, ay] = path[index - 1], [bx, by] = path[index];
    const length = Math.hypot(bx - ax, by - ay);
    if (length <= 1e-9) continue;
    heading = [(bx - ax) / length, (by - ay) / length];
    if (left <= length) return { at: [ax + heading[0] * left, ay + heading[1] * left], heading };
    left -= length;
  }
  return { at: path.at(-1) ?? [0, 0], heading };
}
