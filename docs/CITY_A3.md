# One city route, two projections

The user placed the supplied city drawing on October 28, 2026 and confirmed **A3 landscape**. The active replacement adapter is [`backend/data/seoul-city-a3.json`](../backend/data/seoul-city-a3.json). It has a new map identity/version/hash and leaves the historical Little Town definition untouched.

## Drawing and places

| Fact | Source and limit |
|---|---|
| Page and drawing frame | Nominal 420 × 297 mm, full-page upper-left origin; printer scale has not been independently measured |
| Source artwork | User-supplied 2400 × 1697 PNG; exact SHA-256 and pixel-derived geometry in the adapter; image remains private |
| Four print markers | IDs 10–13, clockwise from upper-left; centers and black-square dimensions derived from this source, not reused from Little Town |
| Start | Pizza, on the central road north of the southwest block, initial printed-map-east departure |
| Destinations | Villa (northwest block), Hanok (northeast), Office Building (southeast) |
| Approach waypoints | Declared drawing-road points near each named block; not measured entrances or physical arrival tolerances |
| Main Junction | Central crossing; Pizza's only outgoing scenario edge enters it, preserving the declared initial approach |
| Signal | No active paper-signal region has been placed/reviewed; `signal_targets` stays empty |

The road graph uses thirteen named points, explicit directed connectivity, three destinations and per-junction display dimensions. The central yellow-line/crosswalk artwork needs a wider display stop region than the outer roads. Main Junction uses 99 mm with a 63.525 mm stop-line width. An incoming destination does not consume another junction's half-edge allocation; adjacent junctions still share limited road space. These values position a **drawing overlay**, not a robot stopping target.

## Shared path contract

MUSE selects graph node IDs. The backend validates that exact connected path and derives its drawing points, arrow direction, stop lines and simulated progress. `MapScene` creates one `RouteDisplay`; Camera and Spatial use that same object and `RouteOverlay`.

- **Camera:** the explicit current four-marker test registration projects drawing points into the unchanged native JPEG. Partial marker coverage keeps the fixed transform under the existing independent freshness/identity/contradiction checks. Never auto-refit to a hand, hose or vehicle.
- **Spatial:** `spatial_preview` maps the declared drawing-road envelope to the corresponding clean GLB's road envelope. It binds the exact model ID/SHA-256 and participates in the map geometry hash. The same route is projected by the exact rendered Three.js camera, including orbit and lens offset.
- **Invalid binding:** malformed metadata or a different GLB cannot silently receive a guessed city route. Legacy maps without the new correspondence retain their explicitly unaligned preview.

The Spatial label is **`Drawing-aligned route · display only`**. This is an authored UI correspondence between drawing and model roads. It is not camera-to-3D calibration, physical car tracking, BASE registration or proof of swept clearance. No city artwork, model or raw camera image is published in Git.

## Activate and verify

```sh
python tools/validate_map.py backend/data/seoul-city-a3.json
python tools/serve.py --map-path backend/data/seoul-city-a3.json --state-path <new-private-workspace.sqlite3>
```

Use a new isolated workspace for this print and preserve prior evidence separately. Select the map when starting the web application; the camera helper, Rodi and robot-control API need no restart. Inspect the actual current print and deliberately lock a fresh four-marker view. Do not restore a Little Town reference, route, approval or historical robot command.

Check all three destination paths and at least one longer alternative using the same node sequence in Camera and Spatial. Actual native-image MUSE planning remains unapproved simulation; a missing physical car must be disclosed. Confirm fresh camera frames, stable fixed registration, original image bytes, route/stop-line consistency and tablet viewport fit.

Live registration failures now preserve their specific error code/message so `view_changed` does not masquerade as a revision conflict. A real revision conflict still requires refreshing the workspace. Neither condition triggers automatic re-registration, provider fallback or robot movement.
