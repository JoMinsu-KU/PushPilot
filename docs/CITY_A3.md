# One city route, two projections

The user installed the final toy-style A3 print on October 28, 2026. The active adapter [`backend/data/seoul-city-a3.json`](../backend/data/seoul-city-a3.json), version `2026-10-28.4`, derives its nominal geometry from `PushPilot_map2d_toy_A3_100pct.pdf`. The previous sheet's camera reference, route approvals and robot installation do not transfer to this replacement. The historical Little Town definition remains unchanged.

## Final PDF and drawing anchors

| Fact | Source and limit |
|---|---|
| Page and drawing frame | One landscape A3 page, nominal 420 × 297 mm, upper-left drawing origin; the PDF MediaBox and CropBox agree, with no rotation |
| Source artwork | The unchanged 7016 × 4961 embedded JPEG stream covers the entire page; exact JPEG and PDF SHA-256 values are in the adapter; both media files remain private |
| Four print markers | `DICT_4X4_50`, IDs 10–13 clockwise from upper-left; native subpixel centers, with an approximate 8.45 mm square model |
| Marker-size limit | The native lower markers are about one source pixel taller; square-only dimensions are a drawing approximation, not surveyed print metrology |
| Start | The center of Pizza's printed pink start rectangle, source [1600,4299.5], nominal [95.781072,257.398004] mm; initial printed-map-east departure |
| Destinations | Villa (northwest), Hanok (northeast), Office Building (southeast), each on the road south/in front of its block |
| Main Junction | On the default Villa/Hanok routes, approached from S; the direct Office route continues east at S |
| Signal | No current approach-specific paper-signal region has been reviewed; `signal_targets` remains empty |

Source geometry is converted using 420/7016 and 297/4961 mm per native pixel. Panel edges and plain-road midpoints have approximately two source pixels of reading uncertainty, roughly 0.12 mm at nominal A3 scale. Printer scaling, mounting, camera error, car dimensions and contact geometry require separate measurements; the raster precision does not establish those tolerances.

The pink outline spans source [1056,3980,2144,4619], about 65.13 × 38.25 mm on the nominal page. Its center anchors the scenario's start node. It does not measure the actual car center, yaw, pusher contact point, contact Z or robot BASE coordinates. Fixing the car at this area is an operator setup convention; completion after a push still needs its own outcome evidence.

The graph retains thirteen named points and explicit directed connectivity. Main Junction uses a rounded 99 mm display stop region and 63.7 mm crossing width; outer roads use a nominal 42.4 mm width. The central stop point from S lies inside the south yellow band, before entering the central crosswalk. These values position drawing overlays and simulated actions, with no claim of physical swept clearance or stopping accuracy.

Pizza's only departure is east to S. The default paths preserve the prior frontage correction:

| Destination | Default drawing route | Nominal drawing distance |
|---|---|---|
| Office Building | `PIZZA → S → OFFICE_BUILDING`, straight east | 204.732041 mm |
| Villa | `PIZZA → S → C → VILLA`, north at S, west at C | 313.600114 mm |
| Hanok | `PIZZA → S → C → HANOK`, north at S, east at C | 313.630045 mm |

A valid requested alternative keeps its exact node sequence. Every traversed junction retains its simulated stop and signal gate. The direct Office route visits S rather than C, so a signal registered only at Main Junction does not cover it. No central detour is silently added to a direct Office request.

The final artwork changes source pixels, marker positions, road envelope, building bounds and the Pizza anchor. It therefore has a new version and geometry hash. Explicitly register the actual new print; the unchanged-print route-revision exception cannot reuse the previous sheet's homography. Do not restore prior robot poses, profiles, BASE transforms or pending commands.

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

Use dedicated application state for this print and preserve prior evidence. When retaining the current simulation ledger, the map-version/hash checks must invalidate prior plans and discard old display references; no approval or command may resume. Select the map when starting the web application; the camera helper, Rodi and robot-control API need no restart. Inspect the actual current print and deliberately lock a fresh four-marker view. Do not restore a Little Town reference, route, approval or historical robot command.

Check all three destination paths and at least one longer alternative using the same node sequence in Camera and Spatial. Actual native-image MUSE planning remains unapproved simulation; a missing physical car must be disclosed. Confirm fresh camera frames, stable fixed registration, original image bytes, route/stop-line consistency and tablet viewport fit.

Live registration failures now preserve their specific error code/message so `view_changed` does not masquerade as a revision conflict. A real revision conflict still requires refreshing the workspace. Neither condition triggers automatic re-registration, provider fallback or robot movement.

## Historical front-start correction, October 28

Release `20261028-city-pizza-front-48c1fd5` activated version `2026-10-28.2`, before the remaining destination frontage correction. Fresh native-image MUSE requests accepted all three destinations with its then-required `PIZZA → S → C` prefix. That evidence preserves the earlier routing behavior; it does not verify the corrected direct Office route in version `.3`. The former rear-start plan was invalidated; a fresh then-current four-marker view was explicitly locked. The final CSS-only release then explicitly resumed that exact transform and requested a fresh Office plan. No plan was approved and no robot moved.

Both Camera and Spatial show the same five Office route segments, two junction stop geometries and the front-storefront start marker. The existing glass source badge was moved above the road so it no longer covers the marker; camera pixels, perspective and map projections are unchanged. Python suites passed 433 tests locally and on GX10; the frontend passed 59 tests and its build. See the [front-start verification](evidence/city-pizza-front-20261028.json), including short-window partial-marker observations and device-test limits. Physical signal coverage at S or C is not established by their simulated checkpoints.

## Earlier rear-start rollout, October 28

The isolated GX10 release `20261028-city-a3-88331e6` served the earlier version `2026-10-28.1`, before the user corrected the Pizza start. Its [historical evidence](evidence/city-a3-20261028.json) does not verify the corrected route. Actual unchanged native-camera MUSE requests accepted Villa, Hanok, Office Building and a longer northern/eastern Office route. A new four-marker city reference replaced the prior-map display setup; the final web-only update explicitly resumed that exact current-city transform and requested a fresh MUSE plan. All plans remained unapproved simulation. No physical car was visible.

The initial 24-frame marker check and 24 post-lock checks passed. A final 60-frame window retained the exact transform throughout: 59 `locked` frames and one `locked_partial` frame with three visible markers. Camera and Spatial rendered the same ten selected route segments and four junction stop geometries. Both views fit 1194 × 834, 1366 × 1024 and 1024 × 768 browser viewports without vertical overflow; the bounded route dialog also fit the smallest size. Nominal distances are rounded only in UI copy, and step headings use the selected map's display names.

Python suites passed 431 tests locally and on GX10; the final frontend passed 59 tests and its production build. The camera helper, Rodi and robot-control API were not restarted. See the scoped [machine-readable verification](evidence/city-a3-20261028.json). These short display/planning checks do not establish long-run recognition rates, iPad Safari hardware behavior, physical coordinates, paper-signal recognition or robot motion.
