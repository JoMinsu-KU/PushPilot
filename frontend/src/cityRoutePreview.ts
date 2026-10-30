import type { SpatialPreview, TemporaryMap } from '../../contracts/scene.ts';
import type { Point } from './projection.ts';

export const CITY_MODEL_ID = 'pushpilot-seoul-city-web-clean-roads';
export const CITY_MODEL_SHA256 = 'f5fb0b2524d6bee45f5b939f121b29d5eac274ea34e670895dada3a2b70b39d7';
export interface CityModelBinding { id: string; sha256: string }
export interface CityPreviewFit {
  left: number; top: number; width: number; height: number;
  spatial?: SpatialPreview;
}
export interface CityProjection { width: number; height: number; matrix: number[] }
export interface CityDisplayManifest {
  schema_version: 'pushpilot.city-display.v1';
  coordinate_authority: 'display_only';
  map_geometry_hash: string;
  model: { id: string; sha256: string; url: string };
  drawing_rect_mm: [number, number, number, number];
  model_rect_xz: [number, number, number, number];
  elevation: number;
}

// Legacy maps keep an explicitly unaligned, complete-graph preview.
const cityRoadEnvelope = { width: 472, depth: 298, elevation: 2 };
const modelBinding: CityModelBinding = { id: CITY_MODEL_ID, sha256: CITY_MODEL_SHA256 };
const spatialKeys = ['schema_version', 'model_id', 'model_sha256', 'drawing_rect_mm', 'model_rect_xz',
  'elevation', 'alignment', 'coordinate_authority'];
const rect = (value: unknown): value is [number, number, number, number] => Array.isArray(value)
  && value.length === 4 && value.every(item => typeof item === 'number' && Number.isFinite(item))
  && value[0] < value[2] && value[1] < value[3];

function validSpatial(map: TemporaryMap, binding: CityModelBinding): map is TemporaryMap & { spatial_preview: SpatialPreview } {
  const value = map.spatial_preview;
  if (!value || typeof value !== 'object' || Object.keys(value).length !== spatialKeys.length
    || spatialKeys.some(key => !Object.hasOwn(value, key))
    || value.schema_version !== 'pushpilot.spatial-preview.v1' || value.coordinate_authority !== 'display_only'
    || value.alignment !== 'drawing_correspondence' || value.model_id !== binding.id || value.model_sha256 !== binding.sha256
    || !/^[0-9a-f]{64}$/.test(value.model_sha256) || !rect(value.drawing_rect_mm) || !rect(value.model_rect_xz)
    || typeof value.elevation !== 'number' || !Number.isFinite(value.elevation) || value.elevation < 0 || value.elevation > 1000
    || !map.board || ![map.board.width_mm, map.board.height_mm].every(item => typeof item === 'number' && Number.isFinite(item) && item > 0)) return false;
  const [left, top, right, bottom] = value.drawing_rect_mm;
  return left >= 0 && top >= 0 && right <= map.board.width_mm && bottom <= map.board.height_mm
    && value.model_rect_xz.every(item => Math.abs(item) <= 1_000_000)
    && map.nodes.every(node => node.x_mm >= left - 1e-8 && node.x_mm <= right + 1e-8 && node.y_mm >= top - 1e-8 && node.y_mm <= bottom + 1e-8);
}

/** Explicit correspondence is map-bound; invalid/mismatched metadata never falls back. */
export function cityPreviewFit(map: TemporaryMap | null, binding: CityModelBinding = modelBinding): CityPreviewFit | null {
  if (!map || !Array.isArray(map.nodes) || !map.nodes.length
    || map.nodes.some(node => !node || !Number.isFinite(node.x_mm) || !Number.isFinite(node.y_mm))) return null;
  if (Object.hasOwn(map, 'spatial_preview')) {
    if (!validSpatial(map, binding)) return null;
    const [left, top, right, bottom] = map.spatial_preview.drawing_rect_mm;
    return { left, top, width: right - left, height: bottom - top, spatial: map.spatial_preview };
  }
  const xs = map.nodes.map(node => node.x_mm), ys = map.nodes.map(node => node.y_mm);
  const left = Math.min(...xs), top = Math.min(...ys);
  const width = Math.max(...xs) - left, height = Math.max(...ys) - top;
  return width > 0 && height > 0 ? { left, top, width, height } : null;
}

export function cityPreviewLabel(fit: CityPreviewFit | null): string {
  return !fit ? 'Route correspondence unavailable' : fit.spatial
    ? 'Drawing-aligned route · display only' : '2D route preview · alignment pending';
}

/** The new artwork is independently bound. Never mutate the physical map to display a model. */
export function cityDisplayFit(map: TemporaryMap | null, manifest: CityDisplayManifest | null, actualModelSha256: string | null): CityPreviewFit | null {
  if (!map || !manifest || manifest.schema_version !== 'pushpilot.city-display.v1'
    || manifest.coordinate_authority !== 'display_only' || manifest.map_geometry_hash !== map.geometry_hash
    || !/^[a-f0-9]{64}$/.test(manifest.model?.sha256 ?? '') || manifest.model.sha256 !== actualModelSha256
    || !manifest.model.id || manifest.model.url !== '/models/private/pushpilot-city-clean-roads.glb') return null;
  const correspondence: SpatialPreview = {
    schema_version: 'pushpilot.spatial-preview.v1', coordinate_authority: 'display_only', alignment: 'drawing_correspondence',
    model_id: manifest.model.id, model_sha256: manifest.model.sha256,
    drawing_rect_mm: manifest.drawing_rect_mm, model_rect_xz: manifest.model_rect_xz, elevation: manifest.elevation,
  };
  // Reuse all rectangle/node containment checks against a copy, preserving the original map byte-for-byte.
  return cityPreviewFit({ ...map, spatial_preview: correspondence }, manifest.model);
}

/** Drawing to model world, for the same display-only fit used by the route. */
export function cityPreviewWorld(point: Point, fit: CityPreviewFit): [number, number, number] | null {
  if (!point.every(Number.isFinite) || ![fit.left, fit.top, fit.width, fit.height].every(Number.isFinite)
    || fit.width <= 0 || fit.height <= 0) return null;
  const spatial = fit.spatial;
  if (spatial && (!rect(spatial.model_rect_xz) || !Number.isFinite(spatial.elevation))) return null;
  const [left, top, right, bottom] = spatial?.model_rect_xz ?? [-cityRoadEnvelope.width / 2, -cityRoadEnvelope.depth / 2,
    cityRoadEnvelope.width / 2, cityRoadEnvelope.depth / 2];
  return [left + (point[0] - fit.left) / fit.width * (right - left), spatial?.elevation ?? cityRoadEnvelope.elevation,
    top + (point[1] - fit.top) / fit.height * (bottom - top)];
}

/** Preserve canonical path order/direction, using the exact rendered Three camera. */
export function projectCityPreview(point: Point, fit: CityPreviewFit, view: CityProjection): Point | null {
  const m = view.matrix;
  if (m.length !== 16 || !m.every(Number.isFinite) || !point.every(Number.isFinite)
    || !Number.isFinite(view.width) || !Number.isFinite(view.height) || view.width <= 0 || view.height <= 0
    || ![fit.left, fit.top, fit.width, fit.height].every(Number.isFinite) || fit.width <= 0 || fit.height <= 0) return null;
  const u = (point[0] - fit.left) / fit.width, v = (point[1] - fit.top) / fit.height;
  const spatial = fit.spatial;
  if (spatial && (!rect(spatial.model_rect_xz) || !Number.isFinite(spatial.elevation))) return null;
  const [left, top, right, bottom] = spatial?.model_rect_xz ?? [-cityRoadEnvelope.width / 2, -cityRoadEnvelope.depth / 2,
    cityRoadEnvelope.width / 2, cityRoadEnvelope.depth / 2];
  const x = left + u * (right - left), y = spatial?.elevation ?? cityRoadEnvelope.elevation, z = top + v * (bottom - top);
  const w = m[3] * x + m[7] * y + m[11] * z + m[15];
  const depth = m[2] * x + m[6] * y + m[10] * z + m[14];
  if (w <= 0 || depth < -w || depth > w) return null;
  const px = m[0] * x + m[4] * y + m[8] * z + m[12];
  const py = m[1] * x + m[5] * y + m[9] * z + m[13];
  return [(px / w + 1) * view.width / 2, (1 - py / w) * view.height / 2];
}
