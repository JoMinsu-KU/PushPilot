<sub>[PushPilot](../README.md) / Application / Frontend</sub>

# The operator workspace

**From sight to action. One scene, a shared plan, and its evidence in view.**

[Current status](../docs/CURRENT_STATUS.md) · [Design system](../docs/DESIGN_SYSTEM.md) · [Route display](../docs/ROUTE_DISPLAY.md) · [Architecture](../docs/ARCHITECTURE.md) · [Robot operations](../docs/ROBOT_OPERATIONS.md)

The React/TypeScript workspace preserves **Observe → Plan → Approve → Act → Verify**. One Camera/Spatial stage sits beneath a slim rail, rounded translucent controls and a collapsible mission panel. Quiet charcoal text, restrained orange accents and self-hosted Pretendard carry the product identity. GX10 serves the compiled Vite bundle with Python; it does not need Node.js at runtime.

This describes source behavior reviewed on **November 2, 2026**, not a currently connected robot, camera lock or running service. The configured site trial and equipment-free default remain distinct.

## The experience

| Area | Implemented behavior |
|---|---|
| Goal | Original Typed/Voice query stays separate from interpretation. **From / To** shows the map start and interpreted destination. Edits are preparation actions. |
| Workspace | Continuous stage, glass overlays, collapsible mission controls and complete bounded route/history views. Stop remains visible during an active physical mission, including open application dialogs; a pending Start response can still disable it through shared request state. [Open finding](../docs/REVIEW_FOLLOW_UP.md#code-findings-remain-open) |
| Simulation | Equipment-free planning, exact-plan approval and symbolic actions/reviews. Demo inputs are labelled. Explicit live-backed simulation can use native images and MUSE without robot commands. |
| Robot | Configured current-site Start/Stop, actual sequence rows, Native receipt counts, physical MUSE/signal status, history and faults. Missing physical data is unavailable, never filled from simulator values. |
| Camera | Live/Recorded, original JPEG decode-before-swap, age, fixed display registration, Board focus and shared image/route pan/zoom. Natural perspective; no rectified camera top view. |
| Spatial | Manifest-verified private city and the same selected 2D path. The vehicle illustration follows confirmed contact receipts: **Execution estimate / Display only**, not measured car pose. |
| Signal/review | Active MUSE work has visible scanning status. Robot signal presentation follows the existing physical gate; accepted departure remains **Signal passed** through recontact. |
| History | Read-only, source-labelled records and complete evidence. Opening history never replays commands. |
| Voice | Typed fallback and **Not connected** guidance. Capture, transcription and streaming voice remain unimplemented. |
| Companion | AR-glasses integration remains an explicit concept. |

The source-default compatibility map is Little Town. The reviewed site deployment explicitly selects [Seoul City A3](../docs/CITY_A3.md), `seoul-city-a3` v`2026-10-28.4`: Pizza front departure, Office straight east, Villa/Hanok via the central junction. Public drawing-only map flags do not describe the separate private physical executor.

## Run and build

Use Node.js 24 or later for development. Dependencies are pinned by `package-lock.json`.

```sh
cd frontend
npm ci
npm run dev
```

Vite listens on loopback 5173 and proxies `/api` to Python at `http://127.0.0.1:8080`. Start the backend using [Development](../docs/DEVELOPMENT.md).

```sh
npm test
npm run build
```

The build type-checks and writes `frontend/dist`. Serve bundle and API from one origin. Preserve Pretendard Variable v1.3.9, its [SIL license](public/fonts/pretendard/OFL.txt), [provenance](public/fonts/pretendard/README.md) and [third-party notices](public/third-party-licenses.txt). No runtime font CDN or frontend provider credentials are required.

Spatial also needs the matching private GLB and local Draco decoders: follow [current asset installation](../docs/SPATIAL_3D.md#install-the-current-private-display-asset). The old ZIP installer creates a historical asset rejected by the current viewer. Private artwork remains outside Git/source releases.

## MUSE connects the scene to the plan

MUSE is the Meta reasoning path for grounded goal/route interpretation and visual verification, rather than a decorative chat panel. Explicit planning uses the selected map graph and original image; action review compares source-bound BEFORE/AFTER images, and signal review judges the applicable fresh paper-signal view. The backend validates the returned structure and policy context before it can affect a mission. Visible scanning/review states explain when that model work is happening. Camera and Spatial then display **the same MUSE-selected, locally validated graph route**.

The Spatial vehicle is only a receipt-driven illustration of execution; it is neither MUSE's observed car position nor independent verification. MUSE review, Native tool completion and the display estimate retain separate sources.

## Source and coordinate boundaries

| Display | Source of truth | Limit |
|---|---|---|
| Planned line/arrows | Validated selected map route and visualization | No TCP trajectory or measured vehicle travel |
| Simulation progress | Workspace supervisor actions | No physical arrival |
| Robot sequence/progress | Physical status and Native-bound receipts | Tool movement alone does not measure car movement |
| Spatial car estimate | Read-only physical display collector, confirmed contact receipts and drawing legs | No slip, exact car position/yaw or parking alignment |
| Camera route | Matching map/plan and fixed display homography | No camera-to-BASE/contact calibration |
| Signal/review | Source-bound model evidence and backend policy | No permission from baked model colors or preview connection |

Exact directed routes and departure/first-turn/via/avoid constraints are validated by the backend. Camera and Spatial preserve selected node order; switching views never replans. Drawing distances, physical receipt totals and the Spatial estimate remain distinct.

Configured B/C/D site recipes use independently taught BASE coordinates. MUSE never supplies arbitrary TCP coordinates. The C recipe retains its C26 endpoint and empty START return; final alignment/parallel parking is deferred. Read [Robot operations](../docs/ROBOT_OPERATIONS.md) and [Known limitations](../docs/KNOWN_LIMITATIONS.md) for prerequisites and recovery boundaries.

## Camera fidelity and continuity

The browser targets a **250 ms** preview cycle. Each original JPEG is downloaded once into a bounded Blob URL, decoded, then shared unchanged with SVG. The previous resource survives until React commits its replacement. No canvas copy, resize or recompression occurs. Transport/decode count against the unchanged 1500 ms freshness limit; repeated sequences do not refresh old pixels.

Board focus masks only outside the registered board. Full frame stays available. Pan/pinch/wheel zoom moves image, route and mask together while HUD cards stay fixed. No global image blur, synthetic detail or camera top-view rectification is used; glass softens its own backdrop only.

Prepare a four-marker lock. Expected robot/hose marker covers retain that exact transform quietly, without refits or missing-marker banners. `Fixed mapping` means retained reference, not remeasured hidden alignment. Contradictions, confirmed changes, stale images and identity mismatches keep independent guards. See [Live camera](../docs/LIVE_CAMERA.md) and [Preview recovery](../docs/CAMERA_PREVIEW_RECOVERY.md).

Preview alone does not persist MUSE evidence or complete actions. Explicit live-intelligence and physical-review operations separately select unchanged originals into their ledgers. Image tools retain recorded-image inspection and immutable BEFORE/AFTER pairs; upload time does not establish capture order or freshness.

## State and tablet interaction

- Workspace and physical status retain separate revisions, sessions and plan bindings. Mutations require unique request IDs and expected revisions; uncertain replies require reconciliation, never automatic motion replay.
- Robot Start requires configured readiness and a matching plan. Stop is shown for an active mission, with the pending-request limitation above. View changes and evidence browsing send no motion commands.
- Missing telemetry, stale imagery and provider failures show actual source errors rather than mock values, timed progress or demo substitutions.
- Scene-only inspection cannot resolve an action review. Recorded pairs bind immutable IDs/hashes to the pending simulated review.
- Keep microphone capture disabled until implemented and verified.

The primary target is a **13-inch landscape tablet**. The page fits one viewport; current route/history lists and dialogs **scroll internally**. Earlier documentation also forbade vertically scrolling panels. That broader gate was not met and has no recorded user-approved relaxation. Explicit UX acceptance is still needed; this documentation update does not change the interface or declare that gate passed.

Keep current action, next check and Stop visible while browsing. Tests cover projection/arrows, map replacement, camera transport/resources, physical-data presentation and LAN HTTP request identifiers. Historical viewport checks and screenshots belong in [Verification](../docs/VERIFICATION.md); desktop viewport tests alone do not qualify sustained iPad Safari behavior.
