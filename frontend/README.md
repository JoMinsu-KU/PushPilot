<sub>[PushPilot](../README.md) / Application / Frontend</sub>

# The operator workspace

**Look. Ask. Review. A shared plan, with its evidence in view.**

[Design system](../docs/DESIGN_SYSTEM.md) · [Mission](../docs/MISSION.md) · [Architecture](../docs/ARCHITECTURE.md) · [Voice input](../docs/VOICE_INPUT.md) · [Development](../docs/DEVELOPMENT.md)

The runnable workspace uses React, TypeScript and Vite. The current direction follows the user's industrial references through a continuous spatial stage, large rounded translucent overlays, quiet charcoal typography and restrained orange accents. The application fits a viewport without vertical scrolling; detailed tasks use dialogs, tabs and pages. It connects to the Python mission backend through the versioned [workspace contract](../contracts/workspace.ts). Production builds are static files served by that backend; GX10 does not need Node.js to run the built application.

## The experience

| Area | Implemented behavior |
| :--- | :--- |
| Goal | Editable typed input in a preparation dialog; explicit demo/MUSE interpreter selection. Provider availability comes from the backend. |
| Workspace | Fixed spatial stage spanning beneath navigation, header and translucent mission/status overlays. Recorded or uploaded image, detected markers, explicit test-view locking and a projected planned route. Image, car pose, signal and robot sources stay separate. |
| Camera board focus | Optional surrounding-background mask, available only with the current matching locked test registration. Camera perspective, original pixels and overlay geometry stay unchanged; Full frame remains available. |
| Spatial map | A self-authored schematic of the replaceable temporary Little Town geometry. Routes come from the backend graph. |
| Plan | Paged route dialog for PIZZA to BAKERY, BOOKSTORE or SCHOOL simulation, with bounded surface pushes, a mandatory stop and fresh signal at each junction, then arrival review. |
| Approval | Explicit approval of the displayed plan identifier and revision. |
| Action review | Explicit real MUSE comparison of two operator-selected recordings, bound to the pending simulated action and current map. Expected versus observed result, verdict, limitations, model, elapsed time and provider-reported token usage remain inspectable. Demo verdict injection stays separate and labelled. |
| Image inspection | Explicit actual MUSE request against the selected recorded frame and expected outcome; visible places, car visibility, model-reported signal and limitations are shown. Scene inspection cannot advance the mission. |
| Signal | RED, GREEN and UNKNOWN simulation inputs. The backend owns freshness, waiting and automatic crossing admission. |
| Replay | Paged event browser with selected decision details and read-only evidence dialogs. Replay cannot issue mission commands. |
| Companion | Clearly labelled future AR-glasses concept. |

This build has **no connected robot, live camera, production AR registration or voice capture**. A recorded photograph is labelled as recorded evidence, with its capture timestamp kept unknown unless explicitly supplied. The temporary camera-to-board homography supports test overlays only. Drawing millimeters are not robot coordinates or a qualified car/tool path. Demo action-review buttons do not call MUSE. Actual single-image inspection remains scene-only; the separate recorded-pair action review can update a simulated mission after backend validation. Neither grants hardware motion authority or establishes live capture freshness.

## Run locally

Use Node.js 24 or later to develop or build the frontend. Dependency versions and transitive packages are locked in `package-lock.json`.

```sh
cd frontend
npm ci
npm run dev
```

Vite listens on loopback port 5173 and proxies `/api` to the Python backend at `http://127.0.0.1:8080`. Start the backend separately as described in [Development](../docs/DEVELOPMENT.md).

```sh
npm run build
```

The build type-checks the source, then writes `frontend/dist`. Serve that bundle and the API from the same Python origin in production. Pretendard Variable v1.3.9 is bundled and self-hosted with its [SIL Open Font License](public/fonts/pretendard/OFL.txt); there are no runtime CDN font requests, external image downloads or frontend provider credentials. The [font provenance record](public/fonts/pretendard/README.md) pins its official source and SHA-256.

`npm test` verifies projective coordinates, direction arrows, invalid homography rejection, recorded-pair eligibility and the request-identifier contract, including browsers on LAN HTTP where native `crypto.randomUUID` is unavailable. Pair checks cover duplicated image bytes, map replacement, missing recordings, pending provider requests and capture-time uncertainty. Distributed React, React DOM and Scheduler license texts are preserved in [`public/third-party-licenses.txt`](public/third-party-licenses.txt), which Vite copies into the production bundle.

## Temporary scene inspection

**Camera frame** is the default view; **Spatial map** is a separate illustration. In Camera mode, the photo and route overlay share the original image's intrinsic pixel view box and aspect ratio. **Full frame** shows the complete recorded image. Projection uses the backend-provided drawing-to-image homography. SVG arrow markers follow individual route segments rather than bisecting corners.

1. Open **Image tools** and upload a JPEG or PNG of up to 8 MiB and 12 megapixels. Optionally supply its actual capture time in the operator's local time zone.
2. Inspect the four marker detections and registration message. A candidate fit does not project a route. During mission preparation, select **Lock test view** to accept that frame as a temporary overlay reference.
3. Create a destination plan. Its route appears only when the route, scene and map geometry identities match and the test view is locked.
4. In the **MUSE** image-tools tab, select **Inspect image with MUSE** to send the explicit expected outcome and selected original image to the configured provider. Read the scene-only verdict and model-reported observations in **Result**, with the complete paged details in **Evidence**.

A partially obscured locked view retains its test mapping and displays a warning. A changed view hides the previous overlay. A new complete marker view can be explicitly locked during preparation; missing markers never cause an automatic refit. The **Spatial map** remains a drawing preview rather than measured physical execution evidence.

With a valid matching lock, **Board focus** masks the surrounding desk/floor to a neutral tabletop backdrop. It preserves camera perspective, original image pixels and overlay geometry rather than rectifying or resampling the board. The mask adds no source detail, removes no occlusion and establishes no metric accuracy. **Full frame** remains available. Missing, mismatched or changed registration disables the mask and falls back to the complete Camera frame. MUSE requests, action-pair selection and evidence retain the original frame bytes, identifiers and hashes.

## Recorded action comparison

The **Visual action review** dialog opens from the mission action or visual-review status card. Its **Images**, **Review**, **Result** and **Evidence** tabs keep image comparison, the expected outcome and the complete receipt inside the viewport. It sends an explicit real provider request rather than a manual demo verdict.

1. Load a recording, open the action-review **Images** tab and select **Use current frame as BEFORE**. This image selection may happen during preparation or while an action review is pending.
2. Select **Upload AFTER**, then **Upload recorded frame** in image tools. The new current frame becomes the selected AFTER image. Distinct frame identifiers and distinct image bytes are required.
3. Create and approve a plan, then run one simulated action if a review is not already pending. In **Review**, read its server-supplied action and edit **Expected visual outcome** to describe the observable result. Long expectations use explicit pages.
4. Select **Review action with MUSE**. The request binds the current mission revision, pending review identifier, scene revision and both immutable frame identifiers. The backend validates the pair, compares it through MUSE and rechecks the bindings before applying any result.
5. Read the verdict in **Result**, with separate expected, observed and limitations sections. Return to **Images** to compare the pair. **Evidence** exposes image hashes, map identity, plan/action/review identifiers, model, elapsed time, token usage when reported and the complete immutable record through bounded pages.

The labels BEFORE and AFTER are operator-selected roles. They do not verify capture order, connection to a physical execution or fresh live observation. A map identity or version mismatch blocks submission, and an identical image uploaded twice is rejected. Recorded evidence remains explicitly limited to simulation.

While MUSE is pending, the UI disables competing review and scene mutations but keeps **End simulation** available. A late result from changed mission or scene state is not applied. Provider failures display an error without substituting a demo decision. The last accepted review remains inspectable in the dialog; **Replay** shows evidence attached to the selected historical event without mutation controls.

Single-frame **Inspect image with MUSE** remains an independent scene inspection. It cannot resolve the pending action review. Signal stand-ins and manual demo action verdicts remain under **Simulation inputs**, and deterministic stop and signal admission remain backend-owned.

## State and interaction boundaries

- Poll `/api/v1/state` for the authoritative snapshot. Ignore older revisions from the same session.
- Send a unique request identifier and the expected revision with every command. A stale-state response triggers a refresh and an explicit retry message.
- Accept goals during preparation only. Keep goal edits disabled throughout action, review and signal waits.
- Approve an exact plan before advancing its bounded simulation actions. Do not simulate successful reviews with timers.
- Show every independent source honestly. A successful model interpretation does not imply physical motion or a live observation.
- Keep recorded-pair provider requests outside the general mission busy state so the operator can cancel the simulation while upstream review is pending. Disable other competing mutation controls and ignore stale returned snapshots.
- Keep microphone controls disabled until capture, normalization, transcription and target-device HTTPS are implemented and verified.

## Visual system

The [design system](../docs/DESIGN_SYSTEM.md) supersedes both the earlier navy/cyan direction and the first flat light-card layout. The spatial stage spans the full application grid beneath the slim rail, compact header and rounded mission/status cards. The camera backdrop is broad enough to sit under these surfaces instead of ending beside an empty reserved right column. Soft material depth, restrained line work and readable type replace decorative vehicle/glasses renders. Orange identifies selected navigation and primary operator actions; status colors remain semantic and always include text. The future AR-glasses companion retains an explicit concept label. These requirements record the requested direction, not user design approval.

The current glass uses a white gradient of approximately 59% → 45% opacity for mission/status panels, 38% white for the rail and 45% for the header, with 12 px backdrop blur and 105% saturation. Darker operational text keeps the controls readable. Effects are confined to the overlay surfaces: the camera image and its scene parent have no filter or opacity treatment. The original image URL and SVG view box remain in use, with no canvas recompression or board resampling. Glass intentionally softens detail behind its own area; it does not enhance the image or make every covered detail fully visible.

All product typography uses the user-selected **Pretendard Variable**, with system sans-serif fallbacks. Its full unmodified v1.3.9 WOFF2 supports Korean and Latin text, loads from the application origin and is preloaded for the interface. The `@font-face` declares the upstream weight range of 45–920. JSON and machine-readable evidence retain monospace formatting. Preserve the font and `OFL.txt` when copying `frontend/dist` to GX10; no system font installation is required there.

CSS Grid controls the fixed shell and scene. SVG view boxes control icons and arrows; text glyphs are not used to draw action arrows. Landscape tablet layouts prioritize 1194 × 834, 1366 × 1024 and 1024 × 768 CSS pixels. Narrow layouts switch scene/mission panes instead of stacking the desktop panels. Horizontal paging or carousels are allowed with explicit controls; vertical scrolling and document overflow are not. Focus indicators, explicit button names, reduced-motion preferences and non-color status text support keyboard and assistive use.

The mission overlay shows a short current-route context so approval and the next action remain visible. **Plan** exposes the complete sequence through pages. **Replay**, image tools, action review and other dialogs use bounded sections and pagination; they do not grow into a long page. Full warnings and evidence remain reachable without silently clipping the information. Consult [verification](../docs/VERIFICATION.md) for the actual viewport and interaction checks, rather than treating layout intent as completed validation.

Original map artwork and raw runtime photographs remain outside Git and source packages. The schematic is drawn from the reviewed temporary geometry API. Replacing map geometry invalidates overlays from mismatched historical plans instead of drawing their routes on a new map.

Camera overlays use scene-specific contrast, including a light route casing and readable label backgrounds. Check that the start, destination, current action and route turns have clear viewing space around the cards; transparency alone does not make covered content inspectable. Full frame remains available for complete camera context. Preserve Camera's intrinsic image aspect ratio, perspective and locked overlay geometry in both Board focus and Full frame. Earlier flat-light screenshots and generated navy/cyan diagrams remain dated evidence rather than the current visual specification. Original camera bytes remain private and unchanged by the display mask. Recorded viewport and interaction checks have a specific scope and do not establish full accessibility conformance.
