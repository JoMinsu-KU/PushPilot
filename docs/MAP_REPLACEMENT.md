# Replace the drawing, preserve the evidence

**A reviewed map definition supplies the road graph, place vocabulary, display geometry and optional signal regions. Validation previews a candidate without installing it.**

[Temporary map](TEMPORARY_MAP.md) · [Route display](ROUTE_DISPLAY.md) · [Live camera](LIVE_CAMERA.md) · [MUSE signal gate](MUSE_SIGNAL_GATE.md)

The user replaced the Little Town print with the supplied Seoul City artwork on October 28, confirming nominal A3 landscape. The separate [`seoul-city-a3.json`](../backend/data/seoul-city-a3.json) adapter records the reviewed drawing and exact source hash. It is selected explicitly on GX10; the historical Little Town file/default remains a compatibility fixture. See [City A3 registration](CITY_A3.md) for drawing provenance, intended waypoints and shared Camera/Spatial display correspondence. No drawing establishes robot BASE geometry, measured car pose or a qualified signal region.

## Spatial-only map definitions

An optional `camera_registration_supported` boolean separates spatial drawing geometry from a camera-registerable print. Omitted or explicitly `true` retains the existing requirement for at least four declared, unique markers and preserves the legacy geometry hash. Explicit `false` joins the geometry hash and permits `markers: []`. The retained `marker_dictionary` names the file format's supported dictionary; it does not claim that physical markers exist or are in use.

The separately supplied 3D asset uses an A2 594 × 420 mm model frame; it is currently a display reference, not the active mission graph. Planning continues to use the separate 400 × 250 mm 2D print until a reviewed replacement is installed. These identities and dimensions must remain distinct. A spatial-only model may supply a validated graph, labels and drawing geometry without guessed marker placements. Its `camera_registration_supported: false` appears in the public map snapshot, planning graph, audit and validation preview. The validation preview warns that live camera registration and live-image planning are unavailable for that candidate.

This flag does not relax graph connectivity, metric drawing lengths, page bounds, signal-target metadata or the requirement for `physical_execution_enabled: false`. It does not install the map, change the current camera source or authorize camera registration. Camera and live-operation endpoints must reject a spatial-only map until an explicitly reviewed camera-compatible definition exists.

## What changes with the map

| Drawing fact | Role | Boundary |
|---|---|---|
| Map `id`, `version` and geometry hash | Bind plans, frames, registrations and reviews | A similar-looking print does not make an old binding reusable |
| Nodes, directed edges, start and destinations | Ground MUSE route selection and backend validation | A road centerline does not qualify physical pushing or turns |
| English labels and language aliases | Interpret operator place names and show readable directions | They are display metadata; version semantic changes deliberately |
| Board, page, marker and panel geometry | Project the drawing into a registered image | Camera display registration is separate from robot BASE/TCP calibration |
| Optional approach-specific `signal_targets` | Identify which signal MUSE must inspect after stopping | Missing regions are unavailable; the backend invents no default |

The canonical geometry hash preserves the original value for maps without signal targets, including an explicitly empty `signal_targets` list. Nonempty signal metadata participates in the hash. Changing a target region or its approach binding therefore invalidates prior map-bound approvals and display registrations. Labels and aliases remain outside the geometry hash; change `version` when changing their meaning.

## Ground route selection in the selected graph

`MapDefinition.planning_context()` provides the active map identity, node IDs, labels, aliases, nonmetric row/column ordering and every allowed directed edge. Bidirectional roads appear as two directed edges. Cardinal directions refer to the fixed drawing frame: east is map right, south is map down. A maneuver such as left or right refers to the incoming path direction at the particular junction.

The declared start is configuration with `measured_pose: false`. Its configured heading preserves legacy demo behavior but does not restrict an explicit MUSE-selected path. The existing `route(destination)` demo router still applies the configured departure heading. `route_from_nodes(destination, node_ids)` compiles the exact selected connected path, including a west departure, without recomputing a shortest path or silently substituting another road.

Explicit paths must contain 2–64 known nodes, begin at the declared start, end at the selected destination, obey every directed edge and contain no repeated nodes. Intermediate places on a road cannot be skipped. Distances, drawing points, AR segments, stop-line illustrations and English maneuver descriptions are derived locally from this validated path. Model prose cannot change the direction of an AR arrow.

Structured route constraints have exactly four fields:

```json
{
  "departure": "west",
  "first_turn": "left",
  "via_nodes": ["W", "SW"],
  "avoid_nodes": ["C"]
}
```

This example refers only to the existing temporary Little Town graph. `departure` accepts `any`, `north`, `east`, `south` or `west`; `first_turn` accepts `any`, `left`, `right` or `straight`. The first-turn condition means the maneuver at the **first encountered junction**, including a straight continuation. Via nodes must appear in order; avoided nodes must be absent. Unsupported, contradictory or unsatisfied constraints reject the route. This validates the model's structured interpretation; it does not prove that the interpretation matches an ambiguous human sentence. The operator still reviews the visible interpretation and projected path before approval.

## Validate a candidate without changing the running application

Prepare a complete reviewed JSON definition based on `backend/data/little-town-temporary.json` or the independently authored [Harbor software fixture](../tests/fixtures/harbor-map.json). Keep `schema_version: "pushpilot.temporary-map.v1"`, `temporary: true` and `physical_execution_enabled: false`. Assign a new reviewed version; update all drawing facts together rather than editing only visible shop labels.

The read-only CLI loads the candidate and checks drawing validation plus directed reachability within the route node limit:

```sh
python tools/validate_map.py /private/maps/reviewed-town.json
```

It prints JSON with the candidate identity, graph counts, unavailable destinations, configured signal-target count and `equipment_contacted: false`. Exit status is nonzero for malformed definitions or destinations unavailable within the route limit. No provider, camera, robot, workspace database or service is contacted.

The API provides the same preview to a future map editor or upload workflow:

```http
POST /api/v1/maps/validate
Content-Type: application/json
```

Its body is exactly `{ "definition": <complete map object> }`. The endpoint never persists the object, switches the active map, modifies an existing plan or restarts a service. An otherwise valid but disconnected graph returns a preview with `valid: false`; malformed definitions return HTTP 422. The response includes a generic startup command template with placeholders, not local installation paths.

| API limit | Value |
|---|---:|
| Entire streamed JSON request | 1 MiB |
| Nodes / destinations | 500 each |
| Edge records | 2,000 |
| ArUco marker records | 50 |
| Building panels / signal targets | 500 each |
| Selected route | 64 nodes |

Collection bounds are checked before map construction. Duplicate JSON keys, nonfinite numbers, invalid UTF-8 and excessive nesting are rejected. The API accepts `application/json` only. A successful validation is a drawing audit; it is not physical commissioning.

## Install a reviewed replacement

1. Finish or explicitly terminate the current simulated mission and reconcile its state. Preserve its map, private evidence and database history.
2. Save the reviewed definition as a new private file. Do not overwrite the definition used by an active installation.
3. Start a separate application release or restart only this application with `python tools/serve.py --map-path <reviewed-map.json> --state-path <private-workspace.sqlite3>`. `PUSHPILOT_MAP_PATH` remains the environment alternative. Keep the camera helper, Rodi and POC services untouched.
4. Verify the reported map ID, version, geometry hash and supported destinations. Incompatible stored plans must be invalidated; create a new plan. Do not restore pending historical robot commands or coordinates.
5. Inspect the actual print and camera view, then explicitly lock a new display registration. Recorded and live sources have separate registrations. Replacing, scaling or moving a print can invalidate alignment even when its design looks familiar.
6. Independently commission any later robot geometry, tool/car contact, work height, stopping and turns. The current application does not turn drawing positions into qualified physical targets.

There is no executing-mission hot swap. Validation does not authorize restarting unrelated services. Terminating the web application is not evidence that a physical robot has stopped.

## Configure signal targets explicitly

`signal_targets` is optional. Each target binds one incoming directed road to one junction and an axis-aligned rectangle in drawing millimeters. The object contains exactly `id`, `junction_id`, `approach_from`, `bounds_mm` and `description`. IDs and junction/approach pairs must be unique. The incoming road must exist in that direction, the destination node must be a junction, the rectangle must have positive area inside the board, and the description is 1–500 characters.

The fragment below is a **synthetic example for the Harbor software fixture**, not a measured target on the current print or a complete replacement map:

```json
{
  "signal_targets": [
    {
      "id": "example-only-west-junction-from-dock",
      "junction_id": "J_WEST",
      "approach_from": "DOCK",
      "bounds_mm": [95, 150, 105, 160],
      "description": "Synthetic example only: paper signal for the Dock approach."
    }
  ]
}
```

The shipped Little Town map has **no configured signal targets**. A stopped-live signal request must remain unavailable until the applicable region is reviewed and configured. `signal_target(junction_id, approach_from)` returns that exact isolated metadata or `None`; it does not infer a region from road geometry, marker positions or another approach's signal.

At a configured junction, the intended flow is mandatory stop, verified stop context, a new source-bound image, MUSE color judgment, then deterministic context/freshness checks. RED, UNKNOWN, occlusion, stale context or provider failure keep the mission stopped. A valid current GREEN can admit the crossing. Signal regions are observation context, never robot targets or independent proof of a physical stop.
