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
