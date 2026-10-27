# Spatial 3D city preview

The supplied city GLB is a display-only view alongside the existing camera and 2D route map. MUSE routes continue to use the active 2D map. No route, simulated progress, vehicle position, camera registration or robot coordinate is projected onto the city model in this implementation. The user explicitly deferred joining the two views until the final 2D design is available.

The user confirmed that the supplied 3D layout is the final design reference, while the installed 2D print is provisional test material. This does not replace the currently active 2D mission profile: the latest instruction keeps routing on that profile and uses the 3D asset for display only until the final 2D artwork and its alignment are ready.

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
- The archive does not include a complete asset-licensing/provenance record. The user-supplied model stays in ignored private runtime assets, outside Git and public source archives. No public redistribution rights are inferred.

## Local assets and build

Install frontend dependencies from the lockfile, then install the private model using:

```sh
python tools/install_city_model.py /path/to/PushPilot_city_web_package.zip
```

The installer reads only the expected GLB entry, validates its identity and copies it to `frontend/public/models/private/pushpilot-city.glb`. The private model directory is ignored. The frontend preparation script copies pinned Draco decoder assets from the installed Three.js package to ignored `public/vendor/draco/` before build/dev. The built static frontend includes those local files, so the private deployment does not need a model or decoder CDN. Source releases built from committed Git blobs exclude the private model and generated decoders; reinstall them when preparing a private deployment.

The viewer is lazy-loaded only when Spatial 3D is selected. Drag to orbit, pinch/wheel to zoom, and use City, Intersection or Reset for the predefined views. Pixel ratio is capped, shadows use a modest map and repeated planting is instanced; compatible opaque city meshes are batched. Rendering runs in the viewing browser's WebGL context; GX10 serves the static files rather than rendering frames for the tablet. Actual browser/tablet performance still requires measurement. Three.js and Draco notices are copied with the static frontend.

All existing glass cards, navigation, font and stage dimensions remain in place. Only the optional scene branch and its small scoped controls are added. The oversized export staging plane is given a neutral runtime tabletop material; the city textures and original GLB bytes are preserved. A scoped error boundary keeps failed lazy-chunk loading from removing Camera and 2D navigation, and WebGL recovery remains explicit.

## Later 2D/3D alignment

When the final 2D map is ready, explicitly bind its identity, road graph, block/arrival anchors and signal approach targets to this model. Preserve the same MUSE-selected node/edge order and executor receipts in both views. The current 400 x 250 temporary geometry must not be stretched onto the 594 x 420 model or silently renamed. A future 3D route layer requires a validated display mapping; physical camera/BASE/contact geometry remain separate measurements.

## Verification

The pinned frontend build and 48 existing frontend tests passed after integration. Four private-model import tests passed, covering fixed-entry reads without script execution, unreviewed bytes, external texture references and duplicate entries. The final joint Python suite passed 290 tests, including those import checks.

Coordinated browser verification on the actual application confirmed:

- The supplied GLB renders with the neutral tabletop and existing glass surfaces, without a route on the 3D model or console errors.
- City, Intersection and Reset switch the view correctly.
- Returning to 2D Map preserves the existing `PIZZA -> C -> S -> SCHOOL` route, pending approval and workspace revision 49.
- At 1194 x 834, 1366 x 1024 and 1024 x 768, document/body heights equal viewport height: no vertical page scrolling.
- The native camera helper and its epoch remain unchanged. The coordinating backend session explicitly resumed its genuine saved fixed display reference with matching visible markers; the old homography was reused without fitting a new one.

Private screenshots are saved outside Git under `output/spatial-city-20261027/` as `city-1194.jpg`, `intersection-1194.jpg`, `city-1366.jpg` and `city-1024.jpg`. These are local deployment screenshots, not public documentation assets. An available GLB viewer is not a scan, live digital twin, recognized vehicle pose or robot test.
