import type { PhysicalStatus } from '../../contracts/physical.ts';
import type { TemporaryMap } from '../../contracts/scene.ts';
import type { Point } from './projection.ts';
import type { RouteDisplay } from './routeProgress.ts';
import { physicalSignalLabel } from './physicalMission.ts';
import { pathLength, type CarTrack } from './simulatedCar.ts';

import type { PhysicalDisplay } from '../../contracts/physical-display.ts';
export type DisplayPhase = PhysicalDisplay['phase'];
export type PhysicalDisplaySnapshot = PhysicalDisplay & {
  /** Browser receipt health; never sent to a controller. */
  feed_fresh?: boolean;
};
const phases = new Set<DisplayPhase>(['idle','pending','contact','approach','withdraw','wrist','recontact','signal_wait','muse_review','return','hold','complete','unavailable']);
const integer = (n: unknown): n is number => typeof n === 'number' && Number.isSafeInteger(n) && n >= 0;
const nullableId = (n: unknown) => n === null || typeof n === 'string' && n.length > 0 && n.length < 500;
const fraction = (n: unknown) => n === null || typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1;

/** This separate GET contract never supplies start/stop/admission decisions. */
export function parsePhysicalDisplay(value: unknown): PhysicalDisplaySnapshot {
  const p = value as PhysicalDisplaySnapshot;
  if (!p || p.schema_version !== 'pushpilot.physical-display.v1' || typeof p.available !== 'boolean'
    || typeof p.producer_epoch !== 'string' || !/^[a-f0-9]{32}$/.test(p.producer_epoch)
    || !(p.reason === null || typeof p.reason === 'string') || !integer(p.sequence)
    || typeof p.captured_at !== 'string' || !Number.isFinite(Date.parse(p.captured_at))
    || !nullableId(p.mission_id) || !nullableId(p.plan_id) || !nullableId(p.workspace_session_id) || !(p.plan_revision === null || integer(p.plan_revision))
    || !(p.map_hash === null || typeof p.map_hash === 'string' && /^[a-f0-9]{64}$/.test(p.map_hash))
    || typeof p.state !== 'string' || !phases.has(p.phase) || !nullableId(p.primitive_id) || !nullableId(p.stage_id)
    || !(p.stage_index === null || integer(p.stage_index)) || !(p.stage_count === null || integer(p.stage_count))
    || !['intent','confirmed','none'].includes(p.stage_status) || p.animation_authority !== 'confirmed_only' || p.motion_authority !== false
    || !p.vehicle || p.vehicle.estimated !== true || !fraction(p.vehicle.route_fraction) || !fraction(p.vehicle.leg_fraction)
    || !(p.vehicle.route_leg_index === null || integer(p.vehicle.route_leg_index))
    || !integer(p.vehicle.confirmed_contact_stages) || !integer(p.vehicle.total_contact_stages)
    || p.vehicle.confirmed_contact_stages > p.vehicle.total_contact_stages
    || ![null,'EAST','NORTH','WEST','SOUTH'].includes(p.vehicle.heading) || typeof p.vehicle.moving !== 'boolean'
    || !p.signal || !['none','waiting','confirming','admitted','recontacting','passed'].includes(p.signal.phase)
    || !integer(p.signal.green_count) || !integer(p.signal.green_required)) throw new Error('Spatial execution display is unavailable.');
  return p;
}

export interface DisplayCursor { producer: string | null; sequence: number; retired: string[] }
/** A producer restart may reset its sequence; a retired producer can never revive a previous animation. */
export function acceptDisplayCursor(cursor: DisplayCursor, snapshot: PhysicalDisplaySnapshot, status: PhysicalStatus | null): DisplayCursor {
  if (!displayMatchesStatus(snapshot, status) || cursor.retired.includes(snapshot.producer_epoch)
    || cursor.producer === snapshot.producer_epoch && snapshot.sequence < cursor.sequence) throw new Error('Display binding changed');
  return { producer: snapshot.producer_epoch, sequence: snapshot.sequence,
    retired: cursor.producer && cursor.producer !== snapshot.producer_epoch ? [...cursor.retired, cursor.producer] : cursor.retired };
}

export interface DisplayFeedState { cursor: DisplayCursor; advanced_at: number | null }
/** Successful HTTP delivery alone does not prove that the optional collector is still publishing. */
export function advanceDisplayFeed(feed: DisplayFeedState, snapshot: PhysicalDisplaySnapshot, status: PhysicalStatus | null, now: number): DisplayFeedState {
  const cursor = acceptDisplayCursor(feed.cursor, snapshot, status);
  const advanced = cursor.producer !== feed.cursor.producer || cursor.sequence > feed.cursor.sequence;
  return { cursor, advanced_at: advanced ? now : feed.advanced_at };
}
export function displayFeedFresh(feed: DisplayFeedState, now: number): boolean {
  return feed.advanced_at !== null && Number.isFinite(now) && now >= feed.advanced_at && now - feed.advanced_at <= 3500;
}

export function displayMatchesStatus(snapshot: PhysicalDisplaySnapshot, status: PhysicalStatus | null): boolean {
  return Boolean(snapshot.mission_id && status?.mission_id === snapshot.mission_id
    && snapshot.plan_id === status.plan_id && snapshot.plan_revision === status.plan_revision
    && snapshot.workspace_session_id === status.workspace_session_id);
}

/** Collinear graph edges form one display leg, so contact counts cannot move a car into a turn early. */
export function directionLegs(points: Point[]): Point[] {
  const result: Point[] = [];
  for (const point of points) {
    if (!point.every(Number.isFinite)) return [];
    if (result.length && Math.hypot(point[0] - result.at(-1)![0], point[1] - result.at(-1)![1]) < 1e-7) continue;
    while (result.length > 1) {
      const a = result.at(-2)!, b = result.at(-1)!;
      const first: Point = [b[0] - a[0], b[1] - a[1]], second: Point = [point[0] - b[0], point[1] - b[1]];
      if (Math.abs(first[0] * second[1] - first[1] * second[0]) > 1e-6 || first[0] * second[0] + first[1] * second[1] <= 0) break;
      result.pop();
    }
    result.push([...point]);
  }
  return result;
}

export interface PhysicalCarTrack extends CarTrack { animate: boolean; sequence: number }
export interface DisplayCarMotion {
  key: string | null; distance: number;
  tween: { from: number; to: number; start: number; duration: number } | null;
}
/** A short receipt illustration, never a clock-based estimate of unconfirmed travel. */
export function updatePhysicalCarMotion(current: DisplayCarMotion, track: PhysicalCarTrack | null,
  now: number, options: { animate: boolean; fresh: boolean; reduced: boolean }): DisplayCarMotion {
  if (!track) return { ...current, key: null, tween: null };
  if (!options.fresh && current.key === track.key) return { ...current, tween: null };
  if (current.key !== track.key) return { key: track.key, distance: track.distance_mm, tween: null };
  // Delayed/out-of-order evidence cannot replay a previous piece of the trip.
  if (track.distance_mm < current.distance - .01) return { ...current, tween: null };
  if (!options.animate || options.reduced || !track.animate) return { key: track.key, distance: track.distance_mm, tween: null };
  if (Math.abs(track.distance_mm - (current.tween?.to ?? current.distance)) <= .01) return current;
  return { ...current, tween: { from: current.distance, to: track.distance_mm, start: now, duration: 650 } };
}
/** Rough semantic route position from confirmed contact receipts. No TCP, images, or motion commands. */
export function physicalCarTrack(map: TemporaryMap | null, display: RouteDisplay | null, snapshot: PhysicalDisplaySnapshot | null): PhysicalCarTrack | null {
  if (!map || !display || !snapshot?.available || !snapshot.mission_id || snapshot.map_hash !== map.geometry_hash) return null;
  const path = directionLegs(display.points), index = snapshot.vehicle.route_leg_index, progress = snapshot.vehicle.leg_fraction;
  if (path.length < 2 || index === null || progress === null || index >= path.length - 1) return null;
  let distance = 0;
  for (let leg = 0; leg < index; leg++) distance += pathLength([path[leg], path[leg + 1]]);
  distance += pathLength([path[index], path[index + 1]]) * progress;
  return { key: [snapshot.producer_epoch, snapshot.mission_id, snapshot.plan_id, snapshot.plan_revision, snapshot.map_hash].join('|'),
    path, distance_mm: distance, sequence: snapshot.sequence,
    animate: snapshot.feed_fresh !== false && snapshot.vehicle.moving && snapshot.phase === 'contact' && snapshot.stage_status === 'confirmed'
      && !['HOLD','HELD','STOPPING','FAILED','FAULT','ERROR','CANCELLED'].includes(snapshot.state) };
}

/** A passed admission stays passed instead of being reconstructed from a reset green counter. */
export function displaySignalLabel(status: PhysicalStatus | null, connected: boolean, snapshot: PhysicalDisplaySnapshot | null): string {
  if (connected && snapshot?.available && snapshot.feed_fresh !== false && displayMatchesStatus(snapshot, status)) {
    if (snapshot.signal.phase === 'passed') return 'Signal passed';
    if (snapshot.signal.phase === 'recontacting') return 'Green confirmed · Recontacting';
    if (snapshot.signal.phase === 'admitted') return 'Green confirmed';
    if (snapshot.signal.phase === 'confirming') return `Confirming green (${snapshot.signal.green_count}/${snapshot.signal.green_required})`;
  }
  return physicalSignalLabel(status, connected);
}
