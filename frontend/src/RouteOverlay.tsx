import { useId } from 'react';
import { directionArrows, type Point } from './projection';
import { routeLabelLayout, type RouteDisplay, type RoutePhase } from './routeProgress';

const colors: Record<RoutePhase, string> = {
  planned: '#6f929d', upcoming: '#8299a0', current: '#09b8dc', review: '#c88b43',
  waiting: '#c58b3e', complete: '#389779', fault: '#b66a54',
};

/** SVG drawing coordinates are already projected into the image or spatial plane. */
export function RouteOverlay({ display, scale = 1, boundary }: { display: RouteDisplay | null; scale?: number; boundary?: Point[] }) {
  const id = useId().replace(/:/g, '');
  if (!display?.points.length) return null;
  const start = display.points[0], goal = display.points.at(-1)!;
  return <g className="map-route-layer" aria-label={`${display.source}: ${display.currentLabel}`}>
    <title>{display.source}. {display.currentLabel}. {display.detailed ? `${display.completed} of ${display.total} motion segments reviewed.` : 'Execution progress unavailable for this stored plan.'} No measured car pose.</title>
    <defs>{Object.entries(colors).map(([phase, color]) => <marker key={phase} id={`${id}-${phase}`} viewBox="0 0 12 12" markerWidth={9 * scale} markerHeight={9 * scale}
      refX="9" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="m3 2 6 4-6 4" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></marker>)}</defs>
    {display.segments.map(segment => {
      const color = colors[segment.phase], quiet = ['upcoming', 'planned'].includes(segment.phase);
      return <g key={segment.id} data-route-segment={segment.id} data-route-phase={segment.phase} opacity={quiet ? .73 : 1}>
        <title>{segment.kind}: {segment.phase}</title>
        <polyline points={segment.points_mm.map(point => point.join(',')).join(' ')} fill="none" stroke={quiet ? '#fff' : color} strokeWidth={(quiet ? 5.6 : 9) * scale}
          opacity={quiet ? .72 : .17} strokeLinecap="round" strokeLinejoin="round"/>
        <polyline points={segment.points_mm.map(point => point.join(',')).join(' ')} fill="none" stroke={color} strokeWidth={(quiet ? 2 : 3.2) * scale}
          strokeDasharray={quiet ? `${4 * scale} ${4 * scale}` : undefined} strokeLinecap="round" strokeLinejoin="round"/>
        {directionArrows(segment.points_mm).map((arrow, index) => <path key={index} d={`M${arrow.start.join(',')} L${arrow.end.join(',')}`} fill="none" stroke={color}
          strokeWidth={1.8 * scale} markerEnd={`url(#${id}-${segment.phase})`}/>) }
      </g>;
    })}
    {display.junctions.map(junction => {
      const [from, to] = junction.stop_line_mm, color = colors[junction.phase];
      const label = `${junction.label} · ${junction.status}`;
      const layout = junction.active ? routeLabelLayout(junction.stop_point_mm, label, scale, boundary) : null;
      const clipId = `${id}-label-${display.junctions.indexOf(junction)}`;
      return <g key={junction.node_id} data-junction={junction.node_id} data-junction-phase={junction.phase}>
        <title>{label}. Display-only stop line from map configuration.</title>
        <path d={`M${from.join(',')} L${to.join(',')}`} stroke="#fff" strokeWidth={5 * scale} opacity=".76"/>
        <path d={`M${from.join(',')} L${to.join(',')}`} stroke={color} strokeWidth={2.4 * scale} strokeLinecap="round"/>
        {layout && <g className="route-junction-status">
          <title>{label}</title>
          <defs><clipPath id={clipId}><rect x={layout.x + 5 * scale} y={layout.y} width={layout.width - 10 * scale} height={layout.height}/></clipPath></defs>
          <path d={`M${junction.stop_point_mm.join(',')} L${Math.max(layout.x, Math.min(layout.x + layout.width, junction.stop_point_mm[0]))} ${layout.y + 11 * scale}`} stroke={color} strokeWidth={.65 * scale} opacity=".7"/>
          <rect x={layout.x} y={layout.y} width={layout.width} height={layout.height} rx={5 * scale} fill="#fffffff0" stroke={color} strokeWidth={.6 * scale}/>
          <text x={layout.x + 7 * scale} y={layout.y + 11.1 * scale} fontSize={6.8 * scale} fontWeight="550" fill="#3e5356" clipPath={`url(#${clipId})`}>{layout.text}</text>
        </g>}
      </g>;
    })}
    <circle cx={start[0]} cy={start[1]} r={3.5 * scale} fill="#f4fbfb" stroke="#668a94" strokeWidth={1.7 * scale}/>
    <circle cx={goal[0]} cy={goal[1]} r={6 * scale} fill="#ffffffc9" stroke="#389779" strokeWidth={1.8 * scale}/>
    <circle cx={goal[0]} cy={goal[1]} r={1.9 * scale} fill="#389779"/>
  </g>;
}

export function RouteLegend({ display, physicalLabel }: { display: RouteDisplay | null; physicalLabel?: string }) {
  if (!display) return null;
  return <div className="route-progress-legend" aria-label="Route display status">
    <strong>{display.source}</strong>
    {physicalLabel ? <span className="route-legend-next">Robot mission</span> : display.source === 'Simulation progress' ? <><span className="route-legend-done">Reviewed</span><span className="route-legend-current">Current</span><span className="route-legend-next">Upcoming</span></>
      : <span className="route-legend-next">{display.awaitingApproval ? 'Awaiting approval' : 'Plan only'}</span>}
    <span className="route-progress-message">{physicalLabel ?? display.currentLabel}</span>
  </div>;
}
