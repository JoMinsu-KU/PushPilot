/** Temporary printed-map inspection. This boundary never grants motion authority. */
export interface TemporaryMap {
  schema_version: 'pushpilot.temporary-map.v1';
  id: string; version: string; title: string; geometry_hash: string;
  temporary: true; physical_execution_enabled: false;
  board: {width_mm: number; height_mm: number; road_width_mm: number; junction_size_mm: number};
  start: string; start_heading?: 'east' | 'south' | 'west' | 'north'; destinations: string[];
  nodes: {id: string; x_mm: number; y_mm: number; kind: 'junction' | 'destination'; label?: string; aliases?: string[];
    /** Optional drawing-only dimensions for a junction with different printed geometry. */
    junction_size_mm?: number; road_width_mm?: number}[];
  edges: {from: string; to: string; length_mm: number; bidirectional: boolean}[];
  markers: {id: number; center_mm: [number,number]; size_mm: number}[];
  building_panels: {id: string; bounds_mm: [number,number,number,number]}[];
  limitations: string[];
  /** Drawing-to-model display correspondence only; never camera or robot calibration. */
  spatial_preview?: SpatialPreview;
}
export interface SpatialPreview {
  schema_version: 'pushpilot.spatial-preview.v1';
  model_id: string; model_sha256: string;
  drawing_rect_mm: [number, number, number, number];
  model_rect_xz: [number, number, number, number]; elevation: number;
  alignment: 'drawing_correspondence'; coordinate_authority: 'display_only';
}
export interface MapRoute {
  map_id: string; map_version: string; map_hash: string;
  temporary: true; physical_execution_enabled: false;
  start: string; destination: string; node_ids: string[];
  points_mm: [number,number][]; distance_mm: number; junction_ids: string[];
  /** Optional on older stored plans; never synthesize execution progress for them. */
  visualization?: RouteVisualization;
}
export type MapPoint = [number,number];
/** Drawing-only stop/crossing divisions. These are not calibrated robot targets. */
export interface RouteVisualization {
  schema_version: 'pushpilot.route-display.v1'; source: 'drawing_only';
  segments: {id: string; kind: 'push' | 'crossing'; from_node_id: string; to_node_id: string;
    junction_id: string | null; points_mm: MapPoint[]; length_mm: number}[];
  junctions: {node_id: string; label: string; center_mm: MapPoint; stop_point_mm: MapPoint;
    stop_line_mm: [MapPoint,MapPoint]; exit_point_mm: MapPoint;
    approach_segment_id: string; crossing_segment_id: string}[];
}
export interface SceneSnapshot {
  schema_version: 'pushpilot.scene.v1'; revision: number;
  map_id: string; map_version: string; map_hash: string;
  frame: null | {id: string; image_url: string; width: number; height: number;
    source: 'uploaded' | 'recorded'; captured_at: string | null; received_at: string;
    timestamp_source: 'operator_provided' | 'unknown'; sha256: string};
  detection: {marker_ids: number[]; markers: {id: number; corners: [number,number][]}[]};
  registration: {
    status: 'unregistered' | 'partial' | 'candidate' | 'locked' | 'locked_partial' | 'view_changed';
    id: string | null; reference_frame_id: string | null;
    homography: number[][] | null; residual_px: number | null; message: string;
  };
  inspection: null | {id: string; frame_id: string; source: 'meta'; model: string;
    created_at: string; verdict: 'USABLE' | 'REOBSERVE' | 'UNKNOWN'; summary: string;
    visible_places: string[]; car_visible: boolean; signal: 'RED' | 'GREEN' | 'UNKNOWN';
    limitations: string[]; expected: string; applies_to: 'scene_inspection'; motion_authority: false};
  capabilities: {live_camera: false; robot: false; muse_configured: boolean};
}
/** GET /api/v1/map, GET /api/v1/scene. Mutations return SceneSnapshot.
 * POST /api/v1/scene/frames: multipart file plus optional captured_at (operator-provided).
 * POST /api/v1/scene/registration: {expected_revision, frame_id}.
 * POST /api/v1/scene/reviews: {expected_revision, frame_id, expected}.
 * GET /api/v1/scene/frames/{id}/image: immutable private runtime image.
 */
