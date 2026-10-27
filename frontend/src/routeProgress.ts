import type { MapRoute, TemporaryMap } from '../../contracts/scene';
import type { PlanStep, WorkspaceSnapshot } from '../../contracts/workspace';
import type { Point } from './projection.ts';

export type RoutePhase = 'planned' | 'upcoming' | 'current' | 'review' | 'waiting' | 'complete' | 'fault';
interface SegmentGeometry {
  id: string; kind: 'push' | 'crossing'; from_node_id: string; to_node_id: string;
  junction_id: string | null; points_mm: Point[]; length_mm: number;
}
interface JunctionGeometry {
  node_id: string; label: string; center_mm: Point; stop_point_mm: Point;
  stop_line_mm: [Point, Point]; exit_point_mm: Point;
  approach_segment_id: string; crossing_segment_id: string;
}
export interface DisplaySegment extends SegmentGeometry { phase: RoutePhase }
export interface DisplayJunction extends JunctionGeometry { phase: RoutePhase; status: string; active: boolean }
export interface RouteDisplay {
  detailed: boolean; source: 'Simulation progress' | 'Planned route'; awaitingApproval: boolean;
  segments: DisplaySegment[]; junctions: DisplayJunction[]; points: Point[];
  currentLabel: string; completed: number; total: number;
}

const point = (value: unknown): value is Point => Array.isArray(value) && value.length === 2 && value.every(Number.isFinite);
const samePoint = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1]) < .001;
const geometryLength = (points: Point[]) => points.slice(1).reduce((length, next, index) => length + Math.hypot(next[0] - points[index][0], next[1] - points[index][1]), 0);

export function routeMatchesMap(route: MapRoute | null, map: TemporaryMap | null): boolean {
  return Boolean(route && map && route.map_id === map.id && route.map_version === map.version && route.map_hash === map.geometry_hash);
}

/** Invalid or legacy metadata is drawn as a complete planned route, never inferred progress. */
function visualization(route: MapRoute, map: TemporaryMap, steps: PlanStep[]) {
  const data = route.visualization;
  if (!data || data.schema_version !== 'pushpilot.route-display.v1' || data.source !== 'drawing_only'
    || !Array.isArray(data.segments) || !data.segments.length || !Array.isArray(data.junctions)) return null;
  const nodes = new Set(map.nodes.map(node => node.id));
  const ids = new Set<string>();
  for (const segment of data.segments) {
    if (!segment || typeof segment.id !== 'string' || !segment.id || ids.has(segment.id)
      || !['push', 'crossing'].includes(segment.kind) || !nodes.has(segment.from_node_id) || !nodes.has(segment.to_node_id)
      || (segment.junction_id !== null && !nodes.has(segment.junction_id))
      || !Array.isArray(segment.points_mm) || segment.points_mm.length < 2 || !segment.points_mm.every(point)
      || !Number.isFinite(segment.length_mm) || segment.length_mm < 0
      || Math.abs(segment.length_mm - geometryLength(segment.points_mm)) > .02) return null;
    ids.add(segment.id);
  }
  if (!samePoint(data.segments[0].points_mm[0], route.points_mm[0])
    || !samePoint(data.segments.at(-1)!.points_mm.at(-1)!, route.points_mm.at(-1)!)) return null;
  if (data.segments.some((segment, index) => index > 0 && !samePoint(data.segments[index - 1].points_mm.at(-1)!, segment.points_mm[0]))) return null;
  const bindings = steps.filter(step => step.kind === 'PUSH' || step.kind === 'CROSS');
  if (bindings.length !== data.segments.length || new Set(bindings.map(step => step.route_segment_id)).size !== bindings.length
    || bindings.some((step, index) => step.route_segment_id !== data.segments[index].id
      || (step.kind === 'CROSS') !== (data.segments[index].kind === 'crossing')
      || step.node_id !== (step.kind === 'CROSS' ? data.segments[index].junction_id : data.segments[index].to_node_id))) return null;
  const junctionIds = new Set<string>();
  for (const junction of data.junctions) {
    if (!junction || typeof junction !== 'object') return null;
    const approach = data.segments.find(segment => segment.id === junction.approach_segment_id);
    const crossing = data.segments.find(segment => segment.id === junction.crossing_segment_id);
    if (!nodes.has(junction.node_id) || junctionIds.has(junction.node_id) || typeof junction.label !== 'string'
      || !point(junction.center_mm) || !point(junction.stop_point_mm) || !point(junction.exit_point_mm)
      || !Array.isArray(junction.stop_line_mm) || junction.stop_line_mm.length !== 2 || !junction.stop_line_mm.every(point)
      || samePoint(junction.stop_line_mm[0], junction.stop_line_mm[1])
      || !approach || approach.kind !== 'push' || approach.junction_id !== junction.node_id
      || !crossing || crossing.kind !== 'crossing' || crossing.junction_id !== junction.node_id
      || !samePoint(approach.points_mm.at(-1)!, junction.stop_point_mm)
      || !samePoint(crossing.points_mm[0], junction.stop_point_mm) || !samePoint(crossing.points_mm.at(-1)!, junction.exit_point_mm)
      || !steps.some(step => step.kind === 'STOP' && step.node_id === junction.node_id)) return null;
    junctionIds.add(junction.node_id);
  }
  if (data.segments.some(segment => segment.kind === 'crossing' && !junctionIds.has(segment.junction_id ?? ''))) return null;
  return data;
}

/** Informational only: color cannot admit a crossing or move a progress segment. */
export function currentSignalJunction(workspace: WorkspaceSnapshot | null): string | null {
  const steps = workspace?.plan?.steps;
  if (!steps || !workspace || ['COMPLETED', 'CANCELLED', 'FAULT', 'RECOVERY_REQUIRED'].includes(workspace.state)) return null;
  const current = steps[workspace.current_step];
  if (current?.kind === 'STOP' || current?.kind === 'CROSS') return current.node_id ?? null;
  const next = steps[workspace.current_step + 1];
  return current?.kind === 'PUSH' && next?.kind === 'STOP' ? next.node_id ?? null : null;
}

/** Informational only: color cannot admit a crossing or move a progress segment. */
export function signalDisplay(workspace: WorkspaceSnapshot, junctionId: string, now: number): 'red' | 'green' | 'unknown' | 'stale' {
  const signal = workspace.signal;
  if (signal.source !== 'simulation' || signal.junction_id !== junctionId || !signal.observed_at) return 'unknown';
  const ttl = signal.freshness_limit_ms;
  const age = now - Date.parse(signal.observed_at);
  if (!Number.isFinite(age) || !Number.isFinite(ttl) || ttl! <= 0 || age < 0) return 'unknown';
  if (age > ttl!) return 'stale';
  return signal.color === 'RED' ? 'red' : signal.color === 'GREEN' ? 'green' : 'unknown';
}

/** Derive display state only from supervisor receipts. Never estimates physical car pose. */
export function createRouteDisplay(route: MapRoute | null, map: TemporaryMap | null, workspace: WorkspaceSnapshot | null, now = Date.now()): RouteDisplay | null {
  if (!routeMatchesMap(route, map) || !route || !map || !Array.isArray(route.points_mm) || route.points_mm.length < 2 || !route.points_mm.every(point)) return null;
  const fallback: RouteDisplay = {
    detailed: false, source: 'Planned route', awaitingApproval: workspace?.state === 'PLAN_READY',
    points: route.points_mm, junctions: [], currentLabel: workspace?.state === 'CANCELLED'
      && !workspace.plan?.steps.some(step => step.status === 'current' || step.status === 'complete') ? 'Plan cancelled · no execution' : 'Planned route', completed: 0, total: 0,
    segments: [{ id: 'planned-route', kind: 'push', from_node_id: route.start, to_node_id: route.destination,
      junction_id: null, points_mm: route.points_mm, length_mm: route.distance_mm, phase: 'planned' }],
  };
  if (!workspace?.plan || workspace.mode !== 'simulation' || workspace.plan.route !== route) return fallback;
  const steps = workspace.plan.steps;
  const data = visualization(route, map, steps);
  if (!data) return fallback;
  const hasProgress = steps.some(step => step.status === 'current' || step.status === 'complete');
  const progress = workspace.state !== 'PLAN_READY' && workspace.state !== 'IDLE'
    && (workspace.approved || (hasProgress && ['COMPLETED', 'CANCELLED', 'FAULT', 'RECOVERY_REQUIRED'].includes(workspace.state)));
  const current = steps[workspace.current_step];
  const interrupted = ['FAULT', 'CANCELLED', 'RECOVERY_REQUIRED'].includes(workspace.state);
  const awaiting = ['REVIEW_REQUIRED', 'REOBSERVE'].includes(workspace.state);
  const segments: DisplaySegment[] = data.segments.map(segment => {
    const stepIndex = steps.findIndex(step => step.route_segment_id === segment.id);
    const step = steps[stepIndex];
    let phase: RoutePhase = progress ? 'upcoming' : 'planned';
    if (progress && step.status === 'complete' && stepIndex <= workspace.current_step) phase = 'complete';
    else if (progress && step === current && step.status === 'current') phase = interrupted ? 'fault' : awaiting ? 'review' : 'current';
    return { ...segment, phase };
  });
  const junctions: DisplayJunction[] = data.junctions.map(junction => {
    const crossing = segments.find(segment => segment.id === junction.crossing_segment_id)!;
    const active = progress && current?.node_id === junction.node_id && ['STOP', 'CROSS'].includes(current.kind)
      && (current.status === 'current' || (current.kind === 'STOP' && current.status === 'complete' && workspace.state === 'WAITING_SIGNAL'));
    let phase: RoutePhase = crossing.phase === 'complete' ? 'complete' : progress ? 'upcoming' : 'planned';
    let status = phase === 'complete' ? 'Crossing reviewed' : 'Mandatory stop';
    if (active && current.kind === 'CROSS') {
      phase = interrupted ? 'fault' : awaiting ? 'review' : 'current';
      status = interrupted ? 'Crossing interrupted' : awaiting ? 'Crossing · review pending' : 'Crossing admitted';
    } else if (active) {
      phase = interrupted ? 'fault' : awaiting ? 'review' : 'current';
      status = interrupted ? 'Stop · interrupted' : awaiting ? 'Stop · review pending' : 'Mandatory stop';
      if (workspace.state === 'WAITING_SIGNAL') {
        phase = 'waiting';
        const signal = signalDisplay(workspace, junction.node_id, now);
        status = signal === 'red' ? 'Red · waiting' : signal === 'green' ? 'Green · awaiting admission' : signal === 'stale' ? 'Signal stale · waiting' : 'Signal unknown · waiting';
        crossing.phase = 'waiting';
      }
    }
    return { ...junction, phase, status, active };
  });
  return { detailed: true, source: progress ? 'Simulation progress' : 'Planned route', awaitingApproval: workspace.state === 'PLAN_READY', segments, junctions,
    points: route.points_mm, completed: segments.filter(segment => segment.phase === 'complete').length, total: segments.length,
    currentLabel: progress ? workspace.state === 'COMPLETED' ? 'Route reviewed' : junctions.find(junction => junction.active)?.status
      ?? (interrupted ? 'Mission interrupted' : awaiting ? 'Action · review pending' : current?.label ?? 'Awaiting supervisor')
      : workspace.state === 'CANCELLED' ? 'Plan cancelled · no execution' : 'Review the planned route' };
}

/** One projection for path, stop line and labels; no independent screen coordinates. */
export function projectRouteDisplay(display: RouteDisplay, project: (point: Point) => Point | null): RouteDisplay | null {
  const valid = (points: (Point | null)[]): points is Point[] => points.every((item): item is Point => item !== null && point(item));
  const points = display.points.map(project);
  if (!valid(points)) return null;
  const segments = display.segments.map(segment => ({ ...segment, points_mm: segment.points_mm.map(project) }));
  if (segments.some(segment => !valid(segment.points_mm))) return null;
  const junctions = display.junctions.map(junction => ({ ...junction, center_mm: project(junction.center_mm), stop_point_mm: project(junction.stop_point_mm),
    exit_point_mm: project(junction.exit_point_mm), stop_line_mm: junction.stop_line_mm.map(project) }));
  if (junctions.some(junction => !junction.center_mm || !junction.stop_point_mm || !junction.exit_point_mm || !valid(junction.stop_line_mm))) return null;
  return { ...display, points, segments, junctions } as RouteDisplay;
}

/** Keep compact status text inside the projected board, without changing route geometry. */
export function routeLabelLayout(anchor: Point, text: string, scale: number, boundary?: Point[]): { x: number; y: number; width: number; height: number; text: string } | null {
  const height = 17 * scale, desired = Math.min(194, Math.max(80, text.length * 4.2 + 16)) * scale;
  const compact = (width: number) => {
    const capacity = Math.max(1, Math.floor((width / scale - 14) / 4.2));
    return text.length > capacity ? `${text.slice(0, Math.max(0, capacity - 1))}…` : text;
  };
  if (!boundary?.length) return { x: anchor[0] + 9 * scale, y: anchor[1] - 22 * scale, width: desired, height, text: compact(desired) };
  const minY = Math.min(...boundary.map(point => point[1])), maxY = Math.max(...boundary.map(point => point[1]));
  if (maxY - minY < height + 4 * scale) return null;
  function span(y: number): [number, number] | null {
    const intersections = boundary!.flatMap((first, index) => {
      const last = boundary![(index + 1) % boundary!.length];
      if (Math.abs(first[1] - last[1]) < 1e-8) return Math.abs(first[1] - y) < 1e-8 ? [first[0], last[0]] : [];
      if (y < Math.min(first[1], last[1]) || y > Math.max(first[1], last[1])) return [];
      return [first[0] + (last[0] - first[0]) * (y - first[1]) / (last[1] - first[1])];
    });
    return intersections.length >= 2 ? [Math.min(...intersections), Math.max(...intersections)] : null;
  }
  const candidates = [anchor[1] - 22 * scale, anchor[1] + 7 * scale, anchor[1] - height / 2, (minY + maxY - height) / 2];
  for (const candidate of candidates) {
    const y = Math.max(minY + 2 * scale, Math.min(maxY - height - 2 * scale, candidate));
    const rows = [y, y + height, ...boundary.filter(point => point[1] > y && point[1] < y + height).map(point => point[1])];
    const spans = rows.map(span);
    if (spans.some(row => !row)) continue;
    const left = Math.max(...spans.map(row => row![0])) + 2 * scale;
    const right = Math.min(...spans.map(row => row![1])) - 2 * scale;
    const width = Math.min(desired, right - left);
    if (width < 45 * scale) continue;
    const preferred = anchor[0] + 9 * scale;
    const before = anchor[0] - 9 * scale - width;
    const x = preferred + width <= right ? Math.max(left, preferred)
      : before >= left && before + width <= right ? before : Math.max(left, Math.min(right - width, preferred));
    return { x, y, width, height, text: compact(width) };
  }
  return null;
}
