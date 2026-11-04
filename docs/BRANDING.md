# PushPilot mark

The operator supplied the current official mark on November 4, 2026: a white route joining an orange departure dot and destination ring on a charcoal rounded panel. The canonical asset is [`frontend/public/brand/pushpilot-mark.png`](../frontend/public/brand/pushpilot-mark.png).

![PushPilot mark](../frontend/public/brand/pushpilot-mark.png)

The original file is a 1024 by 1024 RGBA PNG, 53,568 bytes, SHA-256 `1fa5f8f55cce14bde9b382ece6f6dbe594d48dd1263ceaf59ee56edfeae6f675`. Its corners are transparent; the panel, orange and white are respectively `#121417`, `#e8733c` and `#ffffff`. Preserve the original bytes. Scale it as a square; do not crop, stretch, tint, redraw, add filters or change the supplied rounding.

## Audited current surfaces

| Surface | Use |
|---|---|
| Operator workspace | Shared `BrandMark` in `frontend/src/Icons.tsx`, with existing header dimensions and spacing. |
| Standalone Spatial preview | The same shared component and square display dimensions. Preview controls remain local design tools. |
| Browser tabs and iPad home icon | Both HTML entries point to the canonical PNG. The new path separates it from the retired triangle favicon cache. Existing iPad home shortcuts may need to be re-added to refresh their saved icon. |
| GitHub README | The exact mark precedes the product title. |
| Public recorded-review page | The same PNG is embedded in the header and favicon as data URIs. The narrow builder verifies the canonical asset; its four-file output and no-connection CSP are retained. |

The repository-wide audit found the old triangle geometry only in the previous shared component and retired `frontend/public/favicon.svg`. No separate application manifest, icon package, logo generator or backend/robot identifier needs a brand change. GitHub account avatars and repository social-preview settings are outside tracked source and are not changed by committing an asset.

## Preserve historical evidence

Actual tablet recordings and extracted photographs can contain the previous mark. Keep those original pixels and their evidence hashes, including `physical-action-muse-review.jpg`, `robot-tablet-recording.jpg` and `spatial-tablet-recording.jpg`. Do not repaint a historical recording to imply it used the current interface. Original synthetic fixture PNGs, archived model-response JSON, scripts, concept-generation prompts and dated concept images likewise remain unchanged.

## Verification and activation

Compare the asset's bytes/hash against the supplied original, check square header layout at tablet sizes, and verify the production build serves the PNG with `image/png`. The public-review tests continue to enforce original response/fixture integrity and its offline resource boundary. UI screenshots are presentation checks, not microphone, camera, signal or robot test evidence.

Coordinate static activation with the operational owner: add the new immutable assets and PNG first, atomically replace `index.html` last, retain old hashed chunks plus worklet/model/font files for already-open clients, and verify asset hashes and unchanged process/mission identities. No backend, service, geometry or execution change is required. Record actual activation separately; source or build success alone does not establish a deployed release.

## Operational activation · November 4, 2026

Frontend source `9e9d96edb8e0953e48e4e4a5670a99b2d280604c` was activated as a static-only overlay on the existing `20261104-ipad-voice-d293dfd` application release. The backend release link and all running process identities were retained. New assets were installed first and the HTML entry replaced atomically last. Certificate-validating HTTPS returned all six payloads with matching SHA-256 and MIME types, including the original PNG as `image/png`. Entry SHA-256: `091079663d2a52f4eb74df69bb1bfb8b460c30682207bbba96e697a225acf087`.

Old hashed chunks, recorder worklet, model, display manifest and font hashes were preserved. Workspace PLAN_READY revision 132 and the physical COMPLETE 31/31 record at revision 2318 remained byte-identical, as did the private motion configuration. No service restart, camera activation, robot motion or mission reset occurred. This is branding deployment evidence, not a new voice, camera or robot qualification.

Validation passed: 180 frontend tests, nine public-review tests with one unavailable Windows symlink-permission skip, checks of 176 Python/48 JSON files, TypeScript and the production build. Offline previews at 1194 by 834 and 1366 by 1024 verified the actual mark component with current styles and font. The source changes were normally fast-forwarded to GitHub main; the public-review Pages workflow has its own publication check.

The [Pages publication run](https://github.com/JoMinsu-KU/PushPilot/actions/runs/41778821450) for the same source completed successfully. Independent session (6) verified the actual [public review](https://jominsu-ku.github.io/PushPilot/) header and favicon decode to the byte-identical 53,568-byte PNG, the original CSP and font load remain intact, and all three tabs retain PASS/READY, FAIL/FAULT and REOBSERVE/REOBSERVE. The public README displays the supplied mark and the operator-provided team names while retaining its original recorded-video lead. These archived-case checks invoke no new inference or equipment control.
