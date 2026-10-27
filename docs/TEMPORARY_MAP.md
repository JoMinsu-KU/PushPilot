# Little Town temporary workspace

**A replaceable drawing, recorded scene and inspectable simulated route.**

[Development](DEVELOPMENT.md) · [Route display](ROUTE_DISPLAY.md) · [Scene inputs](TEST_INPUTS.md) · [Verification](VERIFICATION.md) · [Contracts](../contracts/README.md)

The user authorized implementation against the temporary print on 2026-10-27. This releases the earlier map hold for a test adapter and camera-to-board image overlays. It does not establish the final production map, robot BASE coordinates, physical stop lines, pushing contact or turn qualification.

## Drawing and route identity

The reviewed data file is `backend/data/little-town-temporary.json`, with map ID `little-town-temporary` and version `2026-10-27.1`. It adapts printed geometry, graph connectivity and marker facts from the existing PushPilot v11 design. Source hash and exact adaptation are recorded inside the file; original artwork, historical POC transforms and obsolete grasp assumptions are excluded.

| Destination | Deterministic route | Drawing centerline | Abstract actions |
|---|---|---:|---:|
| BOOKSTORE | PIZZA → C → BOOKSTORE | 148 mm | 5 |
| BAKERY | PIZZA → C → S → BAKERY | 232 mm | 8 |
| SCHOOL | PIZZA → C → S → SCHOOL | 232 mm | 8 |

The current drawing starts at PIZZA facing east and follows enabled cardinal drawing edges. Replacement maps can declare their own start, destinations and cardinal `start_heading`; omitted heading preserves the original east-facing behavior. The canonical geometry hash binds the board, graph, markers, destination layout and routing heading, preserving the original hash for the default east heading. Node display labels and aliases are excluded from this geometry hash; assign a reviewed version when replacing their meaning. These lengths describe the drawing; they are not TCP travel distances or qualified vehicle trajectories. Centerline containment does not establish car/tool swept clearance.

Each intermediate junction contributes an approach, mandatory simulated stop and admitted crossing. Crossing descriptions retain the intended turn direction. Every junction needs its own accepted action review and fresh scoped simulated GREEN. A previous junction's GREEN or stop verification cannot authorize the next one. Actual stop-line offsets and physical contact-turn motions remain unqualified.

New plans include optional `pushpilot.route-display.v1` visualization data: map-derived push/cross segments, stable action-to-segment bindings and illustrative incoming stop lines. The frontend uses those bindings for completed/current/remaining line treatment and junction wait/review context. It does not use the live photograph to estimate progress. See [Route display](ROUTE_DISPLAY.md) for compatibility and source boundaries.

## Recorded scene and test overlay

1. Open **Image tools** and upload a JPEG or PNG, at most 8 MiB and 12 megapixels. No image means the spatial schematic remains available.
2. An optional capture time is explicitly operator-provided. Without it, capture time stays unknown. The receive timestamp never turns a recorded photograph into a live observation.
3. Detect ArUco `DICT_4X4_50` markers 10–13. Four consistent marker regions support a candidate planar projection.
4. Select **Lock test view** to bind the reference frame, image dimensions, map ID/version/hash and matrix to a new registration ID. The photograph's SHA-256 identifies its immutable bytes.
5. Create a goal and inspect its projected route. The photograph and SVG overlay share the original image viewBox, so responsive resizing preserves their alignment without cropping.

Candidate detections do not display a planned photo overlay until the reference is explicitly locked. The spatial schematic is an original code-native rendering of the drawing facts and is available without private artwork.

After locking, visible marker agreement checks the retained matrix. Partial visibility keeps the reference without refitting and warns that hidden areas are unverified. Moved/inconsistent views, missing markers or changed image dimensions withhold the old overlay. A complete new observation can be explicitly registered again. These image-space checks do not establish absolute millimeter accuracy.

The implementation uses a 3 px RMS / 6 px maximum residual check for this test overlay. Those are software image checks, not qualified robot tolerances. Replacing map identity or version invalidates the stored frame, registration and inspection bindings; it also invalidates incompatible mission plans. Raw frame/history records remain preserved for review.

## Actual MUSE image inspection

**Inspect image with MUSE** sends the selected original frame and stated expectation to the backend Meta adapter. The image is sent only on this explicit action; the key remains server-side. The result binds frame hash, map identity, model, expectation and timestamp. A newer scene revision prevents a late response from attaching to the current frame.

The strict response reports `USABLE`, `REOBSERVE` or `UNKNOWN`, visible places, physical-car visibility, a model-reported paper-signal color and limitations. A printed START rectangle or vehicle footprint is not a physical car. Tiny printed traffic-light artwork is not the separate operator paper signal.

**Scene inspection does not approve an action, supply the deterministic signal gate or advance the mission.** A separate [action-review endpoint](ACTION_REVIEWS.md) compares a selected recorded before/after pair for the pending simulated action; demo verdicts remain separately labelled. Trusted fresh physical capture and measured local completion remain pending. Scene `USABLE` means the image supports inspection, not successful vehicle arrival.

The application can connect to a separately authorized, already-running [live preview](LIVE_CAMERA.md) service when explicitly configured. That preview has its own memory-only frames and fixed display registration. It does not replace recorded MUSE inputs or provide qualified physical observations. The first scene-inspection frame was a recorded native 1920×1080 GX10 photograph; its source stays `recorded`. The application starts no camera or robot process and does not manage existing POC services.

## Replace the temporary map

Map selection is a startup configuration, not an executing-mission hot swap. Keep old map definitions and evidence rather than editing an active installation in place.

1. Prepare a reviewed JSON definition based on `backend/data/little-town-temporary.json`. Assign an installation-appropriate `id` and a new `version`, keeping `schema_version: "pushpilot.temporary-map.v1"`, `temporary: true` and `physical_execution_enabled: false`.
2. Update the drawing facts together: board/page dimensions, graph nodes/edges, start, destinations, heading, print markers and building-panel bounds. Edges must have positive cardinal drawing lengths consistent with their endpoints. The image adapter currently supports `DICT_4X4_50` and requires at least four unique markers.
3. Give nodes English `label` values and optional `aliases` for operator wording. Identifiers remain the route/evidence keys; labels are presentation, not replacement coordinates. MUSE receives the selected map's supported destinations and aliases instead of a fixed shop vocabulary.
4. Finish or explicitly end an existing simulation and reconcile its state. Start only this application with `python tools/serve.py --map-path /private/maps/replacement.json`, or set `PUSHPILOT_MAP_PATH`. Use a private shared `--state-path` and preserve previous evidence. `PUSHPILOT_SCENE_DIR` optionally selects a separate private image directory; its default is beside SQLite.
5. Inspect the reported map identity/version/hash and destination choices. Prepare a new plan; never reuse a mismatched historical plan after a definition/version change. Labels and aliases alone do not change the geometry hash, so version them deliberately rather than treating the hash as a complete content hash. Old plans without route-display metadata remain planned-only until replaced.
6. Check the newly installed physical print and camera view, then explicitly lock a fresh display registration. A live source needs its independent **Lock live view**; a recorded source uses **Lock test view**. Reprinting, scaling, replacing or moving the board can invalidate the prior alignment even if the road artwork looks similar.

The map file is an adapter contract, not an editor: validation rejects unsupported geometry rather than converting it to robot motion. The selected map is shared by deterministic routing, MUSE goal vocabulary, scene matching and frontend labels. No per-shop frontend code or route screenshot must be replaced.

The following metadata fragment illustrates a replacement; it is not a complete map. Keep the board, page, edges, markers, panels, source and limitations from a reviewed full definition, updating them to match the actual print.

```json
{
  "id": "reviewed-town-temporary",
  "version": "reviewed-installation.1",
  "start": "DEPOT",
  "start_heading": "south",
  "destinations": ["CAFE"],
  "nodes": [
    {"id": "DEPOT", "label": "Depot", "aliases": ["start"], "kind": "destination", "x_mm": 80, "y_mm": 60},
    {"id": "J1", "label": "Central junction", "kind": "junction", "x_mm": 80, "y_mm": 120},
    {"id": "CAFE", "label": "Cafe", "aliases": ["coffee shop"], "kind": "destination", "x_mm": 180, "y_mm": 120}
  ]
}
```

`start_heading` accepts `east`, `south`, `west` or `north` and constrains the first graph edge. Map node labels are nonempty strings of at most 100 characters. A node may have up to 20 aliases, each 1–100 characters. `UNKNOWN` is reserved for unresolved goals and cannot be a destination identifier. The adapter does not send drawing coordinates to MUSE for goal interpretation.

A complete [Harbor replacement fixture](../tests/fixtures/harbor-map.json) is available for offline development. It has a different board size, a north-facing DOCK start, four destinations and different markers. It is an original drawing-only software fixture, not a proposed installation or robot coordinate file.

Display registration relates drawing coordinates to image pixels. It does not recover robot BASE, TCP, work Z, car contact geometry, stopping distance or turn capability. No prior robot profile, mailbox, TCP pose or camera-to-BASE transform is imported. Final installation and measured physical qualification remain a separate release gate.
