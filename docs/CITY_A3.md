# One city route, two projections

The user placed the supplied city drawing on October 28, 2026 and confirmed **A3 landscape**. The active replacement adapter is [`backend/data/seoul-city-a3.json`](../backend/data/seoul-city-a3.json). It has a new map identity/version/hash and leaves the historical Little Town definition untouched.

## Drawing and places

| Fact | Source and limit |
|---|---|
| Page and drawing frame | Nominal 420 × 297 mm, full-page upper-left origin; printer scale has not been independently measured |
| Source artwork | User-supplied 2400 × 1697 PNG; exact SHA-256 and pixel-derived geometry in the adapter; image remains private |
| Four print markers | IDs 10–13, clockwise from upper-left; centers and black-square dimensions derived from this source, not reused from Little Town |
| Start | Pizza, on the south road in front of its south-facing red storefront/blue-roof building; initial printed-map-east departure |
| Destinations | Villa (northwest block), Hanok (northeast), Office Building (southeast) |
| Approach waypoints | Declared drawing-road points near each named block; not measured entrances or physical arrival tolerances |
| Main Junction | Central crossing; required prefix `PIZZA → S → C`, approaching from the south after a left/north turn at South Junction |
| Signal | No active paper-signal region has been placed/reviewed; `signal_targets` stays empty |

The road graph uses thirteen named points, explicit directed connectivity, three destinations and per-junction display dimensions. The central yellow-line/crosswalk artwork needs a wider display stop region than the outer roads. Main Junction uses 99 mm with a 63.525 mm stop-line width. An incoming destination does not consume another junction's half-edge allocation; adjacent junctions still share limited road space. These values position a **drawing overlay**, not a robot stopping target.

The user corrected the former rear-of-building start on October 28. Version `2026-10-28.2` moves Pizza to source pixel [534,1472], nominal [93.45,257.621685327] mm: in front of the storefront rather than in front of its neighboring park. Pizza's only departure is east to S; S cannot bypass C along the southeast road. This is an authored demonstration route restriction, not a claim about printed one-way lanes. The central incoming signal binding is now `C` from `S`, never `C` from `PIZZA`; its drawing stop is on the south side of the central crosswalk. Physical start pose, turning, stop and signal ROI still require qualification. The old route/reference identity must not authorize the corrected version.

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

## Verified front-start correction, October 28

Release `20261028-city-pizza-front-48c1fd5` activates version `2026-10-28.2`. Fresh native-image MUSE requests accepted all three destinations with the required `PIZZA → S → C` prefix. The former rear-start plan was invalidated; a fresh current-version four-marker view was explicitly locked. The final CSS-only release then explicitly resumed that exact current-version transform and requested a fresh Office plan. No plan was approved and no robot moved.

Both Camera and Spatial show the same five Office route segments, two junction stop geometries and the front-storefront start marker. The existing glass source badge was moved above the road so it no longer covers the marker; camera pixels, perspective and map projections are unchanged. Python suites passed 433 tests locally and on GX10; the frontend passed 59 tests and its build. See the [front-start verification](evidence/city-pizza-front-20261028.json), including short-window partial-marker observations and device-test limits. Physical signal coverage at S or C is not established by their simulated checkpoints.

## Earlier rear-start rollout, October 28

The isolated GX10 release `20261028-city-a3-88331e6` served the earlier version `2026-10-28.1`, before the user corrected the Pizza start. Its [historical evidence](evidence/city-a3-20261028.json) does not verify the corrected route. Actual unchanged native-camera MUSE requests accepted Villa, Hanok, Office Building and a longer northern/eastern Office route. A new four-marker city reference replaced the prior-map display setup; the final web-only update explicitly resumed that exact current-city transform and requested a fresh MUSE plan. All plans remained unapproved simulation. No physical car was visible.

The initial 24-frame marker check and 24 post-lock checks passed. A final 60-frame window retained the exact transform throughout: 59 `locked` frames and one `locked_partial` frame with three visible markers. Camera and Spatial rendered the same ten selected route segments and four junction stop geometries. Both views fit 1194 × 834, 1366 × 1024 and 1024 × 768 browser viewports without vertical overflow; the bounded route dialog also fit the smallest size. Nominal distances are rounded only in UI copy, and step headings use the selected map's display names.

Python suites passed 431 tests locally and on GX10; the final frontend passed 59 tests and its production build. The camera helper, Rodi and robot-control API were not restarted. See the scoped [machine-readable verification](evidence/city-a3-20261028.json). These short display/planning checks do not establish long-run recognition rates, iPad Safari hardware behavior, physical coordinates, paper-signal recognition or robot motion.
