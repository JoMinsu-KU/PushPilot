import { useId } from 'react';
import type { Point } from './projection';
import { routeLabelLayout, type RouteDisplay, type RoutePhase } from './routeProgress';

const colors: Record<RoutePhase, string> = {
  planned: '#ff7a2f', upcoming: '#ff7a2f', current: '#ff6418', review: '#f5a524',
  waiting: '#f5a524', complete: '#20b07a', fault: '#e5483a',
};
/** Route hierarchy: a white core with a neon glow in the phase colour. Not yet driven = dashed and dimmer;
 *  the action in progress = solid, brightest, with flowing dashes in the travel direction; driven = solid green. */
const looks: Record<RoutePhase, { core: string; glow: number; dashed?: boolean; flow?: boolean }> = {
  planned: { core: '#ffffff', glow: .38, dashed: true }, upcoming: { core: '#ffffff', glow: .38, dashed: true },
  current: { core: '#ffffff', glow: .75, flow: true }, review: { core: '#fff4dc', glow: .6 }, waiting: { core: '#fff4dc', glow: .6 },
  complete: { core: '#e8fff4', glow: .45 }, fault: { core: '#ffe2dd', glow: .65 },
};
/** Stop lines mean "full stop here before the signal check": red until crossed, amber while waiting there, green once crossed. */
const stopColors: Record<RoutePhase, string> = {
  planned: '#e4574b', upcoming: '#e4574b', current: '#e4574b', review: '#f5a524', waiting: '#f5a524', complete: '#20b07a', fault: '#e5483a',
};

/** SVG drawing coordinates are already projected into the image or spatial plane. */
/** Name tag above an endpoint, drawn in the overlay's coordinates; the tail points at the dot. */
function EndpointTag({ at, text, offset, scale, tone }: { at: Point; text: string; offset: number; scale: number; tone: 'start' | 'goal' }) {
  const font = 6.8 * scale, height = 15 * scale, width = text.length * font * .56 + 14 * scale;
  const x = at[0] - width / 2, y = at[1] - offset - 4 * scale - height;
  return <g className={`route-endpoint-tag route-intro-${tone}-tag`} data-endpoint={tone}>
    <path d={`M${at[0] - 3.5 * scale},${y + height - .5} L${at[0]},${y + height + 4 * scale} L${at[0] + 3.5 * scale},${y + height - .5} Z`}/>
    <rect x={x} y={y} width={width} height={height} rx={height / 2}/>
    <text x={at[0]} y={y + height / 2} fontSize={font} textAnchor="middle" dominantBaseline="central">{text}</text>
  </g>;
}

/** Display only: when a new route appears it is revealed like a trip being drawn (start, path, destination). */
export function RouteOverlay({ display, scale = 1, labelScale = scale, boundary, names, occlusionMask }: { display: RouteDisplay | null; scale?: number; labelScale?: number; boundary?: Point[]; names?: { start: string; goal: string }; occlusionMask?: string }) {
  const id = useId().replace(/:/g, '');
  if (!display?.points.length) return null;
  const start = display.points[0], goal = display.points.at(-1)!;
  // Replays only for a different route; progress updates and camera moves keep the drawn state.
  const introKey = [...display.segments.map(segment => segment.id), names?.start, names?.goal].join('|');
  const path = `M${display.points.map(point => point.join(',')).join(' L')}`;
  return <g key={introKey} className="map-route-layer route-intro" aria-label={`${display.source}: ${display.currentLabel}`}>
    <title>{display.source}. {display.currentLabel}. {display.detailed ? `${display.completed} of ${display.total} motion segments reviewed.` : 'Execution progress unavailable for this stored plan.'} No measured car pose.</title>
    <defs>
      <mask id={`${id}-reveal`} maskUnits="userSpaceOnUse" x="-100000" y="-100000" width="200000" height="200000">
        <path className="route-intro-reveal" d={path} pathLength={1} fill="none" stroke="#fff" strokeWidth={30 * scale} strokeLinecap="round" strokeLinejoin="round"/>
      </mask></defs>
    {/* Lines and dots only: an optional mask (the Spatial car) hides them where something stands on the route; tags and labels stay on top. */}
    <g mask={occlusionMask ? `url(#${occlusionMask})` : undefined}>
    <g mask={`url(#${id}-reveal)`}>
    {display.segments.map(segment => {
      const color = colors[segment.phase], look = looks[segment.phase];
      const points = segment.points_mm.map(point => point.join(',')).join(' ');
      return <g key={segment.id} data-route-segment={segment.id} data-route-phase={segment.phase}>
        <title>{segment.kind}: {segment.phase}</title>
        <polyline className="route-glow" points={points} fill="none" stroke={color} strokeWidth={15 * scale} opacity={look.glow * .35} strokeLinecap="round" strokeLinejoin="round"/>
        <polyline className="route-glow" points={points} fill="none" stroke={color} strokeWidth={8 * scale} opacity={look.glow * .8} strokeLinecap="round" strokeLinejoin="round"/>
        <polyline points={points} fill="none" stroke={look.core} strokeWidth={3.2 * scale}
          strokeDasharray={look.dashed ? `${6 * scale} ${5 * scale}` : undefined} strokeLinecap="round" strokeLinejoin="round"/>
        {look.flow && <polyline className="route-flow" points={points} fill="none" stroke={color} strokeWidth={1.6 * scale}
          strokeDasharray={`${4 * scale} ${10 * scale}`} style={{ '--route-flow': `${-14 * scale}px` } as React.CSSProperties} strokeLinecap="round" strokeLinejoin="round"/>}
      </g>;
    })}
    </g>
    <g className="route-intro-junctions">
    {display.junctions.map(junction => {
      const [from, to] = junction.stop_line_mm;
      const label = `${junction.label} · ${junction.status}`;
      return <g key={junction.node_id} data-junction={junction.node_id} data-junction-phase={junction.phase}>
        <title>{label}. Display-only stop line from map configuration.</title>
        <path d={`M${from.join(',')} L${to.join(',')}`} stroke="#fff" strokeWidth={3.8 * scale} opacity=".85" strokeLinecap="round"/>
        <path className={junction.active ? 'route-stop-active' : undefined} d={`M${from.join(',')} L${to.join(',')}`} stroke={stopColors[junction.phase]} strokeWidth={2 * scale} opacity=".85" strokeLinecap="round"/>
      </g>;
    })}
    </g>
    <circle className="route-intro-start" cx={start[0]} cy={start[1]} r={3.8 * scale} fill="#ffffff" stroke="#20292e" strokeWidth={1.8 * scale}/>
    {/* The view can hide the dot (Spatial: once the car stands on the destination). */}
    <g data-endpoint-dot="goal">
    <g className="route-intro-goal">
      <circle cx={goal[0]} cy={goal[1]} r={6 * scale} fill="#ffffff" stroke="#c45a24" strokeWidth={2 * scale}/>
      <circle cx={goal[0]} cy={goal[1]} r={2.2 * scale} fill="#c45a24"/>
    </g>
    </g>
    </g>
    {/* The wrappers can be moved by the view (Spatial floats each tag above its place's building). */}
    {names && <g data-endpoint-lift="start"><EndpointTag at={start} text={names.start} offset={3.5 * scale} scale={labelScale} tone="start"/></g>}
    {names && <g data-endpoint-lift="goal"><EndpointTag at={goal} text={names.goal} offset={6 * scale} scale={labelScale} tone="goal"/></g>}
    {/* Status labels sit in their own top layer so no stop line, route or endpoint covers them. */}
    <g className="route-intro-junctions route-junction-labels">
    {display.junctions.map((junction, index) => {
      const label = `${junction.label} · ${junction.status}`, color = colors[junction.phase];
      const layout = junction.active ? routeLabelLayout(junction.stop_point_mm, label, labelScale, boundary) : null;
      if (!layout) return null;
      const clipId = `${id}-label-${index}`;
      return <g key={junction.node_id} className="route-junction-status" data-junction-label={junction.node_id}>
        <title>{label}</title>
        <defs><clipPath id={clipId}><rect x={layout.x + 5 * labelScale} y={layout.y} width={layout.width - 10 * labelScale} height={layout.height}/></clipPath></defs>
        <path d={`M${junction.stop_point_mm.join(',')} L${Math.max(layout.x, Math.min(layout.x + layout.width, junction.stop_point_mm[0]))} ${layout.y + 11 * labelScale}`} stroke={color} strokeWidth={.65 * labelScale} opacity=".7"/>
        <rect x={layout.x} y={layout.y} width={layout.width} height={layout.height} rx={5 * labelScale} fill="#fffffff0" stroke={color} strokeWidth={.6 * labelScale}/>
        <text x={layout.x + 7 * labelScale} y={layout.y + 11.1 * labelScale} fontSize={6.8 * labelScale} fontWeight="550" fill="#3e5356" clipPath={`url(#${clipId})`}>{layout.text}</text>
      </g>;
    })}
    </g>
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
