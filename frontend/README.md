<sub>[PushPilot](../README.md) / Application / Frontend</sub>

# The operator workspace

**Look. Ask. Review. A shared plan, with its evidence in view.**

[Design system](../docs/DESIGN_SYSTEM.md) · [Mission](../docs/MISSION.md) · [Architecture](../docs/ARCHITECTURE.md) · [Voice input](../docs/VOICE_INPUT.md) · [Development](../docs/DEVELOPMENT.md)

The runnable workspace uses React, TypeScript and Vite. The current visual direction follows the user's industrial light-dashboard references: off-white canvas, white panels, charcoal typography, thin gray borders and restrained orange accents. It connects to the Python mission backend through the versioned [workspace contract](../contracts/workspace.ts). Production builds are static files served by that backend; GX10 does not need Node.js to run the built application.

## The experience

| Area | Implemented behavior |
| :--- | :--- |
| Goal | Editable typed input during preparation; explicit demo/MUSE interpreter selection. Provider availability comes from the backend. |
| Workspace | Recorded or uploaded image, detected marker outlines, explicit test-view locking and a projected planned route. Image, car pose, signal and robot sources stay separate. |
| Spatial map | A self-authored schematic of the replaceable temporary Little Town geometry. Routes come from the backend graph. |
| Plan | PIZZA to BAKERY, BOOKSTORE or SCHOOL simulation, with bounded surface pushes, a mandatory stop and fresh signal at each junction, then arrival review. |
| Approval | Explicit approval of the displayed plan identifier and revision. |
| Action review | Explicit real MUSE comparison of two operator-selected recordings, bound to the pending simulated action and current map. Expected versus observed result, verdict, limitations, model, elapsed time and provider-reported token usage remain inspectable. Demo verdict injection stays separate and labelled. |
| Image inspection | Explicit actual MUSE request against the selected recorded frame and expected outcome; visible places, car visibility, model-reported signal and limitations are shown. Scene inspection cannot advance the mission. |
| Signal | RED, GREEN and UNKNOWN simulation inputs. The backend owns freshness, waiting and automatic crossing admission. |
| Replay | Inspectable event timeline and decision details. Replay cannot issue mission commands. |
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

The build type-checks the source, then writes `frontend/dist`. Serve that bundle and the API from the same Python origin in production. There are no third-party fonts, image downloads or frontend provider credentials.

`npm test` verifies projective coordinates, direction arrows, invalid homography rejection, recorded-pair eligibility and the request-identifier contract, including browsers on LAN HTTP where native `crypto.randomUUID` is unavailable. Pair checks cover duplicated image bytes, map replacement, missing recordings, pending provider requests and capture-time uncertainty. Distributed React, React DOM and Scheduler license texts are preserved in [`public/third-party-licenses.txt`](public/third-party-licenses.txt), which Vite copies into the production bundle.

## Temporary scene inspection

Choose **Camera frame** or **Spatial map**. The photo and route overlay share the original image's intrinsic pixel view box; the image is never cropped to fit a differently shaped container. Projection uses the backend-provided drawing-to-image homography. SVG arrow markers follow individual route segments rather than bisecting corners.

1. Open **Image tools** and upload a JPEG or PNG of up to 8 MiB and 12 megapixels. Optionally supply its actual capture time in the operator's local time zone.
2. Inspect the four marker detections and registration message. A candidate fit does not project a route. During mission preparation, select **Lock test view** to accept that frame as a temporary overlay reference.
3. Create a destination plan. Its route appears only when the route, scene and map geometry identities match and the test view is locked.
4. Select **Inspect image with MUSE** to send the explicit expected outcome and selected image to the configured provider. Read the scene-only verdict, model-reported observations and limitations.

A partially obscured locked view retains its test mapping and displays a warning. A changed view hides the previous overlay. A new complete marker view can be explicitly locked during preparation; missing markers never cause an automatic refit. The **Spatial map** remains a drawing preview rather than measured physical execution evidence.

## Recorded action comparison

The **Compare the result.** panel sits below the main scene. Its **Prepare a recorded pair** setup stays collapsed during preparation and opens automatically for a pending action review. It sends an explicit real provider request rather than a manual demo verdict.

1. Load a recording and select **Use current frame as BEFORE**. This image selection may happen during preparation or while an action review is pending.
2. Select **Upload AFTER in Image tools**, then **Upload recorded frame**. The new current frame becomes the selected AFTER image. Distinct frame identifiers and distinct image bytes are required.
3. Create and approve a plan, then run one simulated action if a review is not already pending. Read its server-supplied action and edit **Expected visual outcome** to describe the observable result.
4. Select **Review action with MUSE**. The request binds the current mission revision, pending review identifier, scene revision and both immutable frame identifiers. The backend validates the pair, compares it through MUSE and rechecks the bindings before applying any result.
5. Read the verdict and compare the visible before/after pair. **Expected, observed and provenance** expands the full expectation, observation, limitations, image hashes, map identity, plan/action/review identifiers, model, elapsed time and token usage when reported.

The labels BEFORE and AFTER are operator-selected roles. They do not verify capture order, connection to a physical execution or fresh live observation. A map identity or version mismatch blocks submission, and an identical image uploaded twice is rejected. Recorded evidence remains explicitly limited to simulation.

While MUSE is pending, the UI disables competing review and scene mutations but keeps **End simulation** available. A late result from changed mission or scene state is not applied. Provider failures display an error without substituting a demo decision. The last accepted review remains below the selection panel; **Replay** shows evidence attached to the selected historical event without mutation controls.

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

The [design system](../docs/DESIGN_SYSTEM.md) supersedes the earlier navy/cyan application direction. A slim full-height icon rail and clean header frame a dominant scene/map viewport, a right mission panel and a row of compact summary cards. White panels, generous spacing and quiet borders keep scene evidence and the next decision prominent. Orange identifies the active destination in navigation and primary operator actions; status colors remain semantic and always include text. The future AR-glasses companion retains an explicit concept label.

CSS Grid controls the workspace, scene, plan panel and companion cards. SVG view boxes control icons and arrows; text glyphs are not used to draw action arrows. The layout adapts from a tablet/desktop composition to stacked mobile panels without horizontal scrolling. Focus indicators, explicit button names, reduced-motion preferences and non-color status text support keyboard and assistive use.

The right-panel step list has a bounded, keyboard-focusable scroll area so longer routes do not bury approval and action controls. The current step scrolls within that list without moving the page. The expanded **Plan** view retains the complete list in normal page flow.

Original map artwork and raw runtime photographs remain outside Git and source packages. The schematic is drawn from the reviewed temporary geometry API. Replacing map geometry invalidates overlays from mismatched historical plans instead of drawing their routes on a new map.

Camera overlays use scene-specific contrast, including a light route casing and readable label backgrounds. The light dashboard palette must not reduce route legibility over recorded photographs. Preserve the intrinsic image aspect ratio and projective geometry when changing panel dimensions. Earlier screenshots and generated navy/cyan diagrams remain dated evidence rather than the current visual specification.
