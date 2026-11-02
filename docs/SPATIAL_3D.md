# Spatial: one city, the selected route

**Camera and Spatial share one validated 2D plan. Spatial changes the presentation, never the executor.**

[City map](CITY_A3.md) · [Route display](ROUTE_DISPLAY.md) · [Execution display](DESIGNER_LIVE_DISPLAY.md) · [Current status](CURRENT_STATUS.md)

Reviewed November 2, 2026. Spatial is the existing **Camera / Spatial** scene switch, not a separate 3D navigation product. The current city model displays the active 2D path with the same node order, direction arrows and stop geometry as Camera. The camera retains its natural perspective; no live-camera top view is generated. A model's independently orbitable view does not rectify the camera image.

The final A3 2D drawing adapter is `seoul-city-a3` v`2026-10-28.4`. Little Town remains the source-default compatibility fixture. Current physical recipes, camera registration and display-model fitting have separate identities and authority.

## Current display binding

The checked-in [city display manifest](../frontend/public/models/city-display.json) binds a private GLB to the **unchanged** map geometry hash. The viewer verifies downloaded model bytes before parsing, including LAN HTTP without WebCrypto.

| Manifest field | Reviewed value |
|---|---|
| Schema / authority | `pushpilot.city-display.v1` / `display_only` |
| Map geometry hash | `9fea848ee172ea6779edda861ddb15c51ba562117d77a3558eb8a85811aefb50` |
| Model ID | `pushpilot-seoul-city-toy3d` |
| Model SHA-256 | `842a7c32e9c8634a9eef12a741e3d4f5ea7727710b88353dc116095d309d9bf2` |
| Private served URL | `/models/private/pushpilot-city-clean-roads.glb` |
| Drawing rectangle, mm | `[39.539623717, 39.542128603, 380.340649943, 257.398004435]` |
| Model X/Z rectangle | `[-241, -154, 241, 154]` |
| Display elevation | `0.6` model units |

`cityDisplayFit()` creates a display-only map copy to validate the manifest correspondence. It does **not** rewrite `backend/data/seoul-city-a3.json`, replace the physical geometry hash, migrate approvals or change taught BASE coordinates. Its private GLB hash differs from the older clean-road asset referenced by the historical map `spatial_preview`; preserve both provenance records rather than editing physical map identity to make a viewer load.

Missing bytes, a wrong hash, malformed manifest or incompatible map disables the optional model/route correspondence. Camera and physical control remain separate. Do not substitute another GLB and update its hash without reviewing a new display manifest.

## Install the current private display asset

The required current GLB is deliberately absent from Git. Obtain the privately retained **exact** asset matching the manifest above; the original October 27 ZIP cannot generate these newer bytes. From the repository root on a POSIX development/build host, the following copies a reviewed asset only after verifying it and refuses to overwrite unrelated existing bytes:

```sh
python - /private/reviewed/pushpilot-city-clean-roads.glb <<'PY'
import hashlib, json, shutil, struct, sys
from pathlib import Path
root = Path.cwd().resolve()
manifest = json.loads((root / 'frontend/public/models/city-display.json').read_text(encoding='utf-8'))
assert manifest['schema_version'] == 'pushpilot.city-display.v1'
assert manifest['coordinate_authority'] == 'display_only'
assert manifest['model']['url'] == '/models/private/pushpilot-city-clean-roads.glb'
source = Path(sys.argv[1]).resolve(strict=True)
data = source.read_bytes()
assert 20 <= len(data) <= 32 * 1024 * 1024, 'Invalid model size'
assert hashlib.sha256(data).hexdigest() == manifest['model']['sha256'], 'Wrong private model'
magic, version, size = struct.unpack_from('<III', data)
assert (magic, version, size) == (0x46546C67, 2, len(data)), 'Invalid GLB 2'
destination = root / 'frontend/public/models/private/pushpilot-city-clean-roads.glb'
assert not destination.is_symlink() and not any(p.is_symlink() for p in destination.parents)
if destination.exists():
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == manifest['model']['sha256'], 'Preserve/review the existing different asset first'
else:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
assert hashlib.sha256(destination.read_bytes()).hexdigest() == manifest['model']['sha256']
print('Reviewed private display asset installed; no map or robot configuration changed.')
PY
cd frontend
npm ci
npm run build
```

This example is documentation, not an automatic equipment/deployment action. On PowerShell run the same Python body through a literal here-string with the asset path supplied as its argument. Keep an older conflicting model privately and review replacement deliberately; do not overwrite it to bypass the check. The build preparation copies the pinned Three.js Draco decoder locally into ignored `public/vendor/draco/`. Include that directory, the verified model, manifest and notices in the private static deployment. Source-only archives intentionally exclude private models and generated decoders.

The asset archive has no complete public redistribution/licensing record. Do not publish GLBs, original print artwork or camera images merely because local use was authorized.

## Route and vehicle semantics

MUSE selects a grounded route using the active graph and explicit source image; the backend validates its exact connected node order and constraints. Camera and Spatial display that one route, not independent model-generated paths. MUSE also reviews deliberately selected original action/signal images through separate evidence/policy paths. A visible model review is evidence of that judgment, while the illustrated Spatial car remains a contact-receipt estimate; neither substitutes for the other.

`MapScene` supplies one `RouteDisplay`. The route overlay uses the exact rendered Three.js view/projection matrix, including orbit, pan, zoom, lens offset and viewport resize. Switching views issues no plan, model-provider or robot request. Malformed/mismatched identities withhold the route instead of inventing an example. Legacy maps lacking explicit correspondence can retain a clearly labelled approximate preview; that fallback is not the current City manifest.

In Robot mode the optional read-only display collector verifies journal/packet/mission/Native bindings. The Spatial vehicle follows confirmed **contact** receipts along direction-compressed drawing legs. Its short tween illustrates newly confirmed progress, not continuous physical tracking. Approach, withdrawal, unloaded wrist, signal wait, MUSE review, HOLD, stale feeds and empty home return do not animate vehicle travel. After delivery the estimate remains at the destination while the empty tool returns.

The visible label is **Execution estimate / Display only**; simulation is labelled **Simulation preview**. Neither tool receipts nor drawing interpolation measure actual car slip, position, yaw or parking alignment. This display cannot accept arrival, change signal admission or authorize continuation. See [Execution display](DESIGNER_LIVE_DISPLAY.md).

The viewer lazy-loads, caps initial DPR at 1.5, uses 1024-pixel shadows, pauses rendering when hidden and disposes resources on unmount. Named model meshes remain available for picking; baked signal colors are neutralized as artwork. WebGL/model failure keeps Camera navigation available. Sustained target-tablet performance still needs device measurements.

## User-confirmed block names

Confirmed October 27, 2026 from the annotated reference:

| Reference quadrant | Canonical ID | English UI name | Scope |
|---|---|---|---|
| Upper left | `VILLA` | Villa | Entire block |
| Upper right | `HANOK` | Hanok | Entire block |
| Lower left | `PIZZA` | Pizza | Includes adjacent park |
| Lower right | `OFFICE_BUILDING` | Office Building | Entire block |

Facade details do not create extra destinations. [Landmark provenance](data/spatial-city-landmarks.json) identifies the **older annotated source model**, not the current installed display asset. Its absence of coordinate authority remains valid; current asset installation uses `city-display.json`.

## Historical October 27 asset workflow

The original `PushPilot_city_web_package.zip` contained `web/PushPilot_city_web.glb`, example HTML and Blender scripts. Those scripts were inspected, not executed. Original GLB: 4,311,436 bytes; SHA-256 `8ecbdf4d4c0a5a58b502f5366a96bc37fa2ce2cbfec9af14896d63743ca49f78`. Its nominal 594 × 420 model frame is distinct from the installed A3 print. Embedded WebP/Draco data and a large staging plane belong to that export.

The historical commands below preserve that original and derive its matte charcoal road material. They are **not installation instructions for the current toy3d manifest**:

```sh
python tools/install_city_model.py /private/archive/PushPilot_city_web_package.zip
python tools/clean_city_roads.py
```

The derivative's SHA-256 is `f5fb0b2524d6bee45f5b939f121b29d5eac274ea34e670895dada3a2b70b39d7`. Only the exclusive `asphalt_photo` material changed; original geometry and post-JSON binary chunks remained identical. These tools are intentionally pinned to old source bytes and refuse unrelated replacements. Run them only in a separate historical asset workspace, since their destination filename overlaps the current private asset.

## Historical verification and current limits

The initial route-preview revision passed 52 frontend/290 Python tests and its build. The clean-road revision passed 53 frontend/322 Python tests and native GLB comparisons. Dated browser checks covered identical selected segment order, orbit/presets, no console errors and no vertical **page** overflow at 1194 × 834, 1366 × 1024 and 1024 × 768. Private screenshots remain outside Git under `output/spatial-city-20261027/`. These results describe those earlier revisions, not the new model or a fresh hardware test.

The October 30 designer/display integration separately tested manifest hashes, physical journal projection, phase freezing and route/history presentation; see [its dated evidence](DESIGNER_LIVE_DISPLAY.md). Current internal list scrolling and on-device acceptance are documented in [Design system](DESIGN_SYSTEM.md). A rendered city is not a scan, a live digital twin, measured vehicle pose or proof of reliable physical execution.
