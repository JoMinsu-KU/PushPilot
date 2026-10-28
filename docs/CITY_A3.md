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
| Approach waypoints | On the road south/in front of each block: Villa/Hanok use the central road, Pizza/Office Building the south road; not measured entrances or physical arrival tolerances |
| Main Junction | Central crossing on the default Villa/Hanok routes, approached from S after a left/north turn at South Junction; the direct Office Building route continues east at S |
| Signal | No active paper-signal region has been placed/reviewed; `signal_targets` stays empty |

The road graph uses thirteen named points, explicit directed connectivity, three destinations and per-junction display dimensions. The central yellow-line/crosswalk artwork needs a wider display stop region than the outer roads. Main Junction uses 99 mm with a 63.525 mm stop-line width. An incoming destination does not consume another junction's half-edge allocation; adjacent junctions still share limited road space. These values position a **drawing overlay**, not a robot stopping target.

Version `2026-10-28.3` corrects the remaining rear-road destination waypoints. All four building frontages and their sidewalks face south in the supplied artwork. Pizza remains at source pixel [534,1472], nominal [93.45,257.621685327] mm, in front of its storefront. Villa and Hanok move to source y848.5 / drawing y148.5 mm, and Office Building moves to source y1472 / drawing y257.621685327 mm. Their source x values remain unchanged. The artwork, board frame, print markers and Spatial correspondence are unchanged.

Pizza's only departure remains east to S. The earlier blanket `PIZZA → S → C` restriction caused Office Building to take a northward detour and finish behind its building; that restriction is removed. The corrected default paths are:

| Destination | Default drawing route | Nominal drawing distance |
|---|---|---|
| Office Building | `PIZZA → S → OFFICE_BUILDING`, straight east along the south road | 206.7625 mm |
| Villa | `PIZZA → S → C → VILLA`, north at S and west at C | 316.059185327 mm |
| Hanok | `PIZZA → S → C → HANOK`, north at S and east at C | 315.884185327 mm |

All drawing roads remain connected, with explicit graph points splitting roads at each registered place. A requested longer directed route remains valid when its exact node sequence and constraints pass validation; the default route is not silently substituted. These are authored demonstration roads and waypoints, not inferred printed one-way lanes or measured robot targets.

Each traversed junction retains its mandatory simulated stop and signal gate. The direct Office Building path traverses S, not C, so a signal registered only at Main Junction would not cover that route. The default Villa/Hanok central incoming binding remains `C` from `S`; its drawing stop is on the south side of the central crosswalk. Physical start pose, contact turning, stopping and actual approach-specific signal regions still require qualification. Old route/reference identities must not authorize this corrected map version.

This correction changes the route graph on the same physical print. A deliberate deployment can derive a new display-reference identity only after the unchanged-print checks and fresh distributed-marker agreement described in [Live camera](LIVE_CAMERA.md). It retains the exact fixed homography, without fitting around the robot, and preserves private derivation provenance. This exception does not apply to a replaced or moved print, reuse old route approval or authorize motion.

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

## Historical front-start correction, October 28

Release `20261028-city-pizza-front-48c1fd5` activated version `2026-10-28.2`, before the remaining destination frontage correction. Fresh native-image MUSE requests accepted all three destinations with its then-required `PIZZA → S → C` prefix. That evidence preserves the earlier routing behavior; it does not verify the corrected direct Office route in version `.3`. The former rear-start plan was invalidated; a fresh then-current four-marker view was explicitly locked. The final CSS-only release then explicitly resumed that exact transform and requested a fresh Office plan. No plan was approved and no robot moved.

Both Camera and Spatial show the same five Office route segments, two junction stop geometries and the front-storefront start marker. The existing glass source badge was moved above the road so it no longer covers the marker; camera pixels, perspective and map projections are unchanged. Python suites passed 433 tests locally and on GX10; the frontend passed 59 tests and its build. See the [front-start verification](evidence/city-pizza-front-20261028.json), including short-window partial-marker observations and device-test limits. Physical signal coverage at S or C is not established by their simulated checkpoints.

## Earlier rear-start rollout, October 28

The isolated GX10 release `20261028-city-a3-88331e6` served the earlier version `2026-10-28.1`, before the user corrected the Pizza start. Its [historical evidence](evidence/city-a3-20261028.json) does not verify the corrected route. Actual unchanged native-camera MUSE requests accepted Villa, Hanok, Office Building and a longer northern/eastern Office route. A new four-marker city reference replaced the prior-map display setup; the final web-only update explicitly resumed that exact current-city transform and requested a fresh MUSE plan. All plans remained unapproved simulation. No physical car was visible.

The initial 24-frame marker check and 24 post-lock checks passed. A final 60-frame window retained the exact transform throughout: 59 `locked` frames and one `locked_partial` frame with three visible markers. Camera and Spatial rendered the same ten selected route segments and four junction stop geometries. Both views fit 1194 × 834, 1366 × 1024 and 1024 × 768 browser viewports without vertical overflow; the bounded route dialog also fit the smallest size. Nominal distances are rounded only in UI copy, and step headings use the selected map's display names.

Python suites passed 431 tests locally and on GX10; the final frontend passed 59 tests and its production build. The camera helper, Rodi and robot-control API were not restarted. See the scoped [machine-readable verification](evidence/city-a3-20261028.json). These short display/planning checks do not establish long-run recognition rates, iPad Safari hardware behavior, physical coordinates, paper-signal recognition or robot motion.
