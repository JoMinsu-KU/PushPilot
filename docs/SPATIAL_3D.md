# Spatial 3D city preview

The existing **Camera / Spatial** switch remains the only scene navigation. Spatial replaces the former illustrative grid/building drawing with the supplied city GLB; there is no separate 3D City tab. MUSE routes continue to use the active 2D map. At the user's request, Spatial previews the same selected path, arrows, stop lines and simulation progress over the model, clearly labelled **2D route preview · alignment pending**. This approximate display fit is not a registered 3D route, measured vehicle position or robot coordinate.

The user confirmed that the supplied 3D layout is the final design reference, while the installed 2D print is provisional test material. This does not replace the currently active 2D mission profile: the latest instruction keeps routing on that profile and uses the 3D asset with an illustrative route preview until the final 2D artwork and its alignment are ready.

## User-confirmed block names

Confirmed on October 27, 2026 from the user's annotated 3D reference:

| Position in the supplied view | Canonical ID | English UI name | Scope |
|---|---|---|---|
| Upper left | `VILLA` | Villa | Entire red-outlined block |
| Upper right | `HANOK` | Hanok | Entire red-outlined block |
| Lower left | `PIZZA` | Pizza | Entire red-outlined block, including the adjacent park |
| Lower right | `OFFICE_BUILDING` | Office Building | Entire red-outlined block |

These user-confirmed names take precedence over names inferred from individual facade graphics. The model's convenience store, cafe and beauty-store details do not create additional mission destinations. The [machine-readable record](data/spatial-city-landmarks.json) records the model hash and the explicit absence of navigation/physical authority. The private annotated screenshot is retained outside the repository. Existing temporary-map Bakery, Bookstore and School identities are unchanged.

## Model and origin

The user supplied `PushPilot_city_web_package.zip`, containing `web/PushPilot_city_web.glb`, an example HTML viewer and two Blender conversion scripts. The scripts and HTML were inspected as source material, not executed. The application uses a newly authored React/Three.js viewer; the example's Korean UI and CDN imports are not copied into the application.

- GLB 2 binary, 4,311,436 bytes; SHA-256 `8ecbdf4d4c0a5a58b502f5366a96bc37fa2ce2cbfec9af14896d63743ca49f78`.
- Supplied board dimensions: 594 x 420 model units, described as millimetres; centered origin, Y up. These model dimensions do not measure the installed physical print.
- Buildings contain 3D height geometry. Repeated vegetation uses crossed texture cards; it is not fully modeled botanical geometry.
- Embedded WebP textures and Draco mesh compression; no external texture URLs are needed for this supplied model.
- The model includes a 6000-unit background plane. The viewer frames the city board/preset camera rather than fitting the entire ground plane.
- Baked red/green signal appearances are neutralized in the runtime view so that static artwork cannot suggest a current MUSE signal observation. Original GLB bytes remain unchanged.
- The user requested new-road appearance on October 27, 2026. Cracks are in the exclusive `asphalt_photo` base-color texture, not geometry. The private derived model replaces only that material's base-color texture with matte charcoal (`#454c50`, roughness 0.95, metalness 0). All six road planes, UVs, nodes, buildings, sidewalks, lane markings, stop lines and crosswalk geometry remain unchanged. The original model is retained alongside the derived file.
- The archive does not include a complete asset-licensing/provenance record. The user-supplied model stays in ignored private runtime assets, outside Git and public source archives. No public redistribution rights are inferred.

## Local assets and build

Install frontend dependencies from the lockfile, then install the private model using:

```sh
python tools/install_city_model.py /path/to/PushPilot_city_web_package.zip
```

The installer reads only the expected GLB entry, validates its identity and preserves it at `frontend/public/models/private/pushpilot-city.glb`. It also creates `pushpilot-city-clean-roads.glb` in the same ignored private directory; Spatial loads this clean-road variant. The variant changes only the named road material in the GLB JSON chunk and copies all remaining binary chunks byte-for-byte. Embedded source textures remain in the binary but the road material no longer uses the cracked texture. This is a native material edit, with no generated image, mesh conversion or Draco re-encoding.

For an already installed original, generate the same variant independently with `python tools/clean_city_roads.py`. The tool validates the reviewed source hash and refuses symlinks, overwriting the original or replacing an unrelated existing file. The frontend preparation script copies pinned Draco decoder assets from the installed Three.js package to ignored `public/vendor/draco/` before build/dev. The built static frontend includes the private variant and local decoders, so the private deployment does not need a model or decoder CDN. Source releases built from committed Git blobs exclude private models and generated decoders; reinstall them when preparing a private deployment.

The viewer is lazy-loaded only when Spatial is selected. Drag to orbit, pinch/wheel to zoom, and use City, Intersection or Reset for the predefined views. Pixel ratio is capped, shadows use a modest map and repeated planting is instanced; compatible opaque city meshes are batched. Rendering runs in the viewing browser's WebGL context; GX10 serves the static files rather than rendering frames for the tablet. Actual browser/tablet performance still requires measurement. Three.js and Draco notices are copied with the static frontend.

All existing glass cards, navigation, font and stage dimensions remain in place. Spatial changes its scene content and adds only small scoped view controls. The oversized export staging plane is given a neutral runtime tabletop material; the city textures and original GLB bytes are preserved. A scoped error boundary keeps failed lazy-chunk loading from removing Camera navigation, and WebGL recovery remains explicit.

## Route preview and later alignment

`MapScene` supplies the same validated `RouteDisplay` to Camera and Spatial. No plan request, alternate graph search, mission mutation, registration update or provider call is triggered by switching views. If map identity/version/hash validation fails, neither view receives that route. No invented example is substituted when a plan is absent.

`cityRoutePreview.ts` keeps the temporary display fit separate from both camera registration and the mission graph. It fits the complete active graph's X/Y extent into the supplied model's illustrative road envelope (X -236 to 236, Z -149 to 149, Y 2). It never fits just the current route or binds old 2D destination names to city buildings. Replacement map coordinates recompute that fit without old place IDs. This generic envelope fit can put paths across city artwork; the user explicitly accepted approximate placement at this stage.

The SVG route layer uses the exact Three camera view/projection matrix, including lens offset, orbit, zoom, pan and viewport resize. Path, arrows and junction geometry share one projection. The layer does not intercept pointer input or test model occlusion; it remains a visible illustrative overlay. Points behind the camera or outside its depth range withhold the preview. Workspace updates change the route without recreating the WebGL renderer or loading the model again. The existing legend retains its planned/simulated source and receipt-derived progress; it never displays measured car pose.

When the final 2D map is ready, replace this approximate display fit with an explicit binding of map identity, road graph, block/arrival anchors and signal approach targets. Preserve the same MUSE-selected node/edge order and executor receipts in both views. Physical camera/BASE/contact geometry remain separate measurements. The current preview grants no physical execution authority.

## Verification

The initial route-preview revision passed its frontend build, 52 frontend tests, repository checks and 290 Python tests. The focused route-preview tests cover replacement graph fitting, exact Three-camera projection, orbit changes, degenerate input and behind-camera/depth rejection. Four private-model import tests cover fixed-entry reads without script execution, unreviewed bytes, external texture references and duplicate entries.

Browser verification on the running application confirmed:

- Scene navigation contains exactly Camera and Spatial; Spatial renders the supplied city and current 2D route preview.
- Camera and Spatial expose the same selected route segment IDs and planned phases. Switching views preserves the current pending mission.
- City, Intersection and Reset presets work. Orbit and wheel zoom update the route projection while it remains visible.
- At 1194 x 834, 1366 x 1024 and 1024 x 768, document/body dimensions equal viewport dimensions: no vertical page scrolling. Existing glass mission/status surfaces remain in place.
- No browser console errors or warnings were reported during these checks.
- No mission command, camera lock/refit, service restart or robot operation was performed for this UI change.

The subsequent clean-road revision passed seven focused native GLB tests and the four existing import tests. The full frontend build, 53 frontend tests, repository checks and joint 322-test Python suite passed with the concurrent camera work present. The exported original/clean pair was compared directly: only `asphalt_photo.pbrMetallicRoughness` differs semantically, and every post-JSON binary byte is identical. Actual City and Intersection browser views show smooth matte roads with the same lane/crosswalk geometry, buildings and current route overlay, no console errors, and no document overflow at 1194 x 834. Private screenshots are `clean-roads-city-1194.png` and `clean-roads-intersection-1194.png` in the same local evidence folder; a standalone private derivative is `PushPilot_city_clean_roads.glb`.

Private deployment screenshots remain outside Git under `output/spatial-city-20261027/`: `spatial-route-1194.png`, `spatial-route-1366.png`, `spatial-route-1024.png` and `spatial-route-intersection-1194.jpg`. An available city viewer is not a scan, live digital twin, recognized vehicle pose or robot test.
