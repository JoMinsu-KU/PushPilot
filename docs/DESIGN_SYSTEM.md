<sub>[PushPilot](../README.md) / Product / Design system</sub>

# The operator workspace design

**One fixed spatial stage, with rounded translucent information layered over it.**

The user selected two industrial operations-dashboard references on October 27, 2026 and then rejected the first implementation as insufficiently similar, too toy-like and too dependent on scrolling. This specification supersedes that implementation and the earlier navy/cyan direction. A light palette alone is not a reference match: composition, surface depth, information density and restraint must match the reference's visual logic.

The supplied references are photographs of monitors, with perspective distortion. The dimensions below are implementation targets, not measurements claimed from the photographs. Prioritize landscape tablet viewports of 1194 × 834, 1366 × 1024 and 1024 × 768 CSS pixels, then check wider desktop and compact layouts. These are browser-layout targets, not claims about the exact usable viewport of every 11-inch or 13-inch tablet. PushPilot keeps its own identity and actual mission data. Reference factory equipment, people, percentages and production orders must not be copied into the product as data. This revision records the requested direction; it is not a user design-approval record.

## What the references actually do

| Reference characteristic | Required translation to PushPilot |
| :--- | :--- |
| A broad, continuous architectural scene occupies most of the first reference. | The scene is the workspace, not one card among a vertical sequence of cards. Preserve a large uninterrupted central viewing area. |
| Softly rounded, milky information panels float in front of that scene. | Place mission, selected-item and compact summary information on translucent scene overlays. The scene must remain perceptible behind these surfaces. |
| A thin icon rail and a shallow header frame the content. | Keep navigation compact, quiet and fixed. Do not spend the viewport on repeated headings, banners or nested toolbars. |
| Large corners, diffuse shadows and low-contrast edges create depth. | Use generous corner radii and restrained glass surfaces. Flat white boxes with tiny corners are insufficient. |
| Technical line work and realistic, desaturated objects establish an industrial tone. | Use credible architectural line work or the real recorded camera image. Avoid cartoon buildings, oversized vehicle icons and decorative pseudo-3D props. |
| The overview reference has clear information hierarchy and short, aligned rows. | Use exact mission state, current action, next check and evidence source. Avoid adding charts or large metrics merely to fill space. |

The rejected screen treated the map as a bordered diagram inside a white card, then appended registration details, MUSE text and large summary cards below it. That is a document layout. The reference is a spatial interface: the scene remains the visual anchor while information is layered over it. The correction must change this hierarchy, not just border colors.

## Fixed viewport composition

The application fits one viewport without vertical page scrolling or vertically scrolling panels. The user explicitly allows horizontal paging and carousels. At normal browser zoom, all essential operational information and the next permitted action must be visible simultaneously. More content uses a different view, horizontal pages or a bounded dialog; it does not extend the workspace vertically. The document itself must not overflow sideways. Horizontal movement belongs to an intentional, labelled page or carousel region with visible navigation.

| Region | Landscape tablet and desktop starting target | Visual role |
| :--- | :--- | :--- |
| Application shell | `100dvh`, viewport width, 12–16 px outer inset, 10–14 px gaps | A single stable frame; no browser-sized document below it. |
| Navigation rail | 64–76 px wide, full available height | Compact mark, consistent 20–22 px outline icons, quiet active surface; floats over the scene rather than occupying an opaque strip beside it. |
| Header | 64–76 px high, 22–28 px radius | Current view title, compact view switch and concise mode/source status, with the scene visible behind its glass surface. |
| Scene stage | The full application grid, underneath navigation, header and cards | A broad, continuous backdrop. Do not reserve a blank right column behind the mission overlay. Stage corners approximately 28–34 px. |
| Mission overlay | Approximately 280–340 px wide, inset 16–22 px from the stage's right edge | Rounded translucent panel; destination, current route context, next check and primary action. Reduce width or use a pane switch on compact tablets before obscuring the scene. |
| Scene heading and controls | Top-left inset 20–28 px; one compact row | Scene title, Camera / Spatial map switch, Board focus / Full frame control and image tools. Avoid multiple full-width toolbar rows. |
| Selected-item overlay | Approximately 250–300 px wide, positioned away from the path | Short contextual details for the selected location or action. Show only when useful. |
| Bottom summaries | A short row inside the stage, 116–150 px high | Two or three compact translucent cards, with horizontal paging where needed. Keep the scene behind them visible; do not append a new section below the stage. |

These values are starting ranges, not rigid sizes that override readability. Camera imagery extends beneath the glass rail, header and cards so those surfaces have a real visual backdrop. The mission overlay and summaries may overlap map imagery, while the start, goal, route turns and current action need clear viewing space. Check these points in the actual viewport rather than assuming transparency makes all underlying detail inspectable. Keep Full frame available for the complete camera context. Never move a camera annotation with an unrelated CSS offset to make room.

Do not add a large full-width goal card above the scene. Show the current goal as concise scene context, with an explicit edit/open affordance during permitted preparation. Goal entry belongs in a bounded preparation view or dialog. Do not display the same destination, route, source and explanation in several panels.

## Rounded glass surfaces

Use a slightly cool, off-white shell and a warm, pale architectural scene or neutral tabletop backdrop. The board should feel placed in one calm spatial environment rather than floating inside several bordered boxes. Information panels have a perceptibly different material from the base scene. In board-focus mode, mask the surrounding desk or floor with a restrained neutral tabletop tone; do not invent surrounding objects or use an unrelated decorative scene.

| Token | Starting value or range |
| :--- | :--- |
| Shell | `#f2f3f6` to `#f6f6f8` |
| Primary text | `#242526` to `#303233` |
| Supporting text | Dark operational gray, approximately `#52636e`; quieter metadata may use a lighter tone where still readable |
| Accent | Restrained burnt orange, approximately `#e8733c` |
| Main panel radius | 24–30 px |
| Small card radius | 18–24 px |
| Small control radius | 12–16 px; fully rounded only for compact segmented controls |
| Mission/status glass fill | White gradient at approximately 59% → 45% opacity, over the actual scene |
| Navigation rail fill | White at approximately 38% opacity, over the actual scene |
| Header fill | White at approximately 45% opacity, over the actual scene |
| Backdrop treatment | 12 px blur and 105% saturation on the glass overlays only |
| Edge | One subtle white highlight or low-opacity neutral border |
| Shadow | Broad and diffuse, around `0 12px 36px rgba(32, 38, 42, .06)` |

These are the current implementation's material choices, derived from the reference's character rather than claims about the original designer's CSS. Lower alpha alone cannot create glass if the underlying scene is absent. Keep the actual camera backdrop under the surfaces and use darker operational text instead of making the entire panel opaque. Do not apply `opacity` to a panel parent, because that also fades its text and controls. Where backdrop filtering is unavailable, use a softly opaque off-white fallback that preserves contrast. Avoid several nested borders, hard drop shadows, glossy gradients, neon route glows and decorative accent outlines. Do not animate blur or large shadows.

The 12 px blur belongs to the glass material, not the camera image. The image element, its parent scene and the page have no blur/filter or opacity treatment. Preserve the original image URL and SVG coordinate system; do not create a smaller canvas copy, recompress the image or resample its board geometry for this design. Ordinary browser sizing does not add source detail. Scene content under a glass panel is intentionally softened and partially covered, so this is not a claim that every underlying pixel remains fully inspectable or that image quality has been enhanced.

The route uses one controlled accent and a quiet contrasting casing. Traffic red, green and amber retain their real semantic role and always have a label. Do not use green to imply a connected robot, a fresh signal or a measured pose when those facts are absent.

Route progress uses distinct line treatment for completed, current and remaining portions, supported by direction arrows and a concise text legend. Keep the current junction's mandatory stop, signal wait and review context anchored to map-derived drawing geometry. A highlighted segment means the supervisor selected that simulated action; it is not a live car-position marker or proof of motion. Stop lines are illustrative until independently qualified. Preserve the selected source and simulation labels when live video and simulated progress appear together. See [Route display](ROUTE_DISPLAY.md).

## Typography, icons and tone

Use **Pretendard Variable v1.3.9** throughout the interface, self-hosted from the application with system sans-serif fallbacks. The unmodified full WOFF2 includes Korean and Latin text support and is preloaded from the same origin; do not add a CDN dependency. Declare the upstream variable weight range of 45–920, while favoring regular or medium weights with short, direct labels. Keep monospace formatting for JSON and other machine-readable evidence. Font provenance and the bundled SIL Open Font License 1.1 are recorded in the [font directory](../frontend/public/fonts/pretendard/README.md).

Suggested desktop sizes are 24–30 px for the workspace heading, 21–25 px for the mission destination, 14–16 px for actionable body text and 12–13 px for secondary metadata. Do not solve fit by shrinking important copy to microtext. Text over glass still needs readable contrast. Check wrapping and panel fit after font changes rather than assuming equal glyph widths across fallback fonts.

Use one consistent set of fine outline icons, typically 1.5–1.8 px strokes at a 20–22 px size. Icons support a label or a known navigation pattern; they are not illustrations. Limit uppercase to short metadata where it helps. Avoid excessive pills, dot badges, emoji, repeated chevrons and decorative identity numbers.

The spatial view should read as a measured drawing preview: thin structural lines, restrained material fills, soft contact shadows and quiet labels. If perspective is used, apply one coherent scene transform and keep geometry, route and hit targets aligned. A perspective illustration is still a drawing preview, not recovered 3D geometry or a calibrated world model. Do not add unrelated factory machines to imitate the reference's complexity.

Remove or subordinate decorative car and glasses renderings that resemble toys or occupy space needed for mission information. A glasses companion remains a small, explicitly labelled concept. No fabricated operator portrait, job title, production percentage or hardware telemetry is allowed.

All authored UI copy, accessibility text, source code and development documentation remain English.

## No-vertical-scroll information architecture

The no-vertical-scroll requirement applies to Workspace, Plan, Replay, image tools and review dialogs. Horizontal paging and carousels are allowed. It is not satisfied by hiding an overflowing page or clipping essential content.

- **Workspace:** show the current action, one preceding/next context item, the signal or review wait when relevant, next check and the primary action. The complete action list opens in Plan. Secondary summary cards may form a horizontal carousel with visible previous/next controls and a page indicator.
- **Plan:** show a fixed number of route steps with explicit previous/next page controls and an action count. The selected/current action stays identifiable. Avoid an eight-row timeline squeezed into the mission overlay.
- **Replay:** show a bounded event list and explicit pagination, with one selected event and its evidence in a second pane. Do not append an unbounded history.
- **Scene details:** show source, registration status and one concise inspection outcome. Full MUSE text, frame identity and limitations belong in a detail view with bounded sections or pages.
- **Action review:** show before/after images and the verdict first. Expected outcome, reasoning and immutable receipt details use tabs or short paged sections. All pages retain source and authority labels.
- **Preparation:** use a dialog or dedicated pane for goal entry, frame upload, registration and provider options. Separate these tasks into tabs rather than exposing every control in the default scene.

Visible text may be intentionally summarized only when a clear control opens the complete text. Do not silently truncate warnings, uncertainty, approval scope or the next action. Dialogs must fit the viewport without vertical scrolling, with keyboard-accessible tab/page controls and a visible close action. Keyboard focus must remain visible and return to the opening control. Horizontal carousel interaction must work with explicit buttons and keyboard navigation as well as a pointer or touch gesture.

On compact tablets, reduce the summary count before reducing legibility. On narrow screens, switch between Scene, Mission and Evidence panes instead of stacking all desktop panels. The current state and next permitted action remain visible in the active pane. Do not reproduce a miniature desktop dashboard on a phone or make a vertical page to accommodate it.

## Scene projection and source truth

Preserve **Observe → Plan → Approve → Act → Verify**. Presentation changes must not change mission admission, revision checks or review behavior.

Place names, destination choices and start labels come from the selected map's metadata. Never position a route from a hardcoded shop name, infer a road edge from its action-list index or reuse a previous map's geometry after replacement. New plans bind steps to backend-supplied display segment identifiers. Older plans without those bindings show a planned route without invented execution progress. The optional `start_heading` supports a replacement drawing without changing frontend code; all supported roads remain cardinal in the current adapter.

Keep the raw recorded image and its camera overlay in the same intrinsic coordinate system. Camera is the default view. Preserve the original perspective, image pixels, aspect ratio and overlay geometry; Full frame displays the complete recorded image. Do not crop, rectify or distort the evidence frame merely to imitate the reference. Draw directional arrows with SVG geometry aligned to individual route segments; a corner marker must not imply a diagonal move. Route, map and registration identities must match. A candidate remains a candidate; a changed view withholds the old projection.

### Camera and board focus

The default presentation is Camera, with independent Live and Recorded sources. Prefer Live when its opt-in preview service is configured; keep Recorded selectable and explicitly labelled. Keep natural camera perspective and image detail while reducing visual clutter with an optional display mask:

| Mode | Presentation and boundary |
| :--- | :--- |
| Camera · Full frame | The complete selected live or recorded image, with correctly projected test overlays when that source's display registration is valid. Source and age stay visible. |
| Camera · Board focus | The same camera perspective and geometry, with pixels outside the registered board polygon masked by a neutral tabletop backdrop. The board is not rectified or resampled. |
| Spatial map | The deterministic drawing preview with its route, independent of camera-image resolution. It is not evidence of actual object position. |

Board focus uses the same valid board-to-image geometry as the overlay, with map identity/version/hash, frame identity and view checks intact. It masks the image background without changing the board's perspective, original pixels or overlay alignment. It cannot recover hidden surfaces, remove occlusion, add source detail or improve physical accuracy.

Apply the mask only when the locked registration still matches the selected map and frame. Do not fit a new registration merely to obtain a cleaner presentation. If registration is missing, invalid, mismatched or changed, withhold the mask, fall back to the full Camera frame, and display a concise unavailable reason. The operator must be able to select Full frame whenever Board focus is available.

Live preview has its own explicit display lock and does not reuse a recorded reference. Its source plate exposes live age, stale state and registration uncertainty. A temporarily occluded fixed live reference may be retained as unverified display alignment; a confirmed view/identity change withholds it until an explicit relock. Do not disguise a stale preview as recorded evidence or turn live display into automatic MUSE input. See [Live camera](LIVE_CAMERA.md) for the separate lifecycle and capability contract.

Keep original image bytes, frame identifiers and hashes unchanged for MUSE input, action-pair selection, immutable evidence and replay. Do not substitute the display mask or a screenshot for captured evidence. Board focus cannot establish camera-to-BASE registration, car pose, metric accuracy, signal freshness, action completion or motion authority.

The spatial schematic is a drawing preview. A route over a recorded photograph is a test overlay. Neither is measured robot motion or qualified metric AR. Keep source labels independent and legible without flooding the main stage with caveats:

- Recorded/uploaded image, simulation, demo verdict and actual MUSE call are distinct sources.
- MUSE scene inspection is distinct from action-bound verification and deterministic signal admission.
- Robot, live-preview and voice availability must reflect implementation reality. Preview connection is distinct from a qualified robot-camera observation capability.
- A recorded-pair action review may affect the simulated mission only through the existing deterministic supervisor. It does not establish fresh physical evidence or motion authority.
- Exact-plan approval and server-owned state boundaries remain intact.
- Mandatory stopping, red/unknown waiting, faults and uncertainty remain prominent, with words and icons as well as color.

Use one concise persistent mode/source line and contextual detail controls. Do not repeat a technical disclaimer below every card, and do not remove it entirely to create an attractive but misleading screenshot.

## Visual acceptance gates

Verify actual rendered screens rather than assuming that CSS tokens match the reference. Save the viewport screenshot, not a long full-page screenshot, as the main design evidence.

| Check | Pass condition |
| :--- | :--- |
| Fixed tablet stage | At 1194 × 834, 1366 × 1024 and 1024 × 768, document dimensions do not exceed the viewport and no panel offers vertical scrolling. Intentional horizontal pages remain bounded and navigable. |
| Wider desktop | At 1440 × 900 and 1280 × 800, the scene remains dominant and panels do not expand into sparse, oversized blocks. |
| Compact layout | At 390 × 844, pane switching keeps the current state and next action readable without a vertical stack or document overflow. Horizontal paging remains explicit. |
| Scene hierarchy | The first impression is a continuous spatial scene with rounded floating information, not a form or a grid of unrelated white cards. |
| Material | The actual scene extends behind the rail, header and mission/status glass. Its colors and structure are perceptible through the overlays, while darker text and controls remain readable. No blank reserved column substitutes for the scene. |
| Operational hierarchy | State, current action, next check and the one primary action are findable immediately. Secondary tools do not compete with them. |
| Route visibility | Start, destination, turns, direction arrows and current action are visible and aligned in Camera Board focus, Full frame and the drawing preview. |
| Progress and waits | Completed/current/remaining route portions and mandatory stop, signal or review context are distinguishable without relying on color alone. Labels state simulation; no moving car pose is invented. |
| Replaceable map | Names and route geometry follow the selected map; mismatched old plans/registrations are withheld, and legacy plans without segment bindings remain planned-only. |
| Board-focus integrity | Valid locked registration enables the display mask; missing, changed or mismatched registration produces the full Camera fallback. Camera perspective, overlay geometry and the raw evidence frame remain unchanged. |
| Camera presentation | The original image URL and SVG coordinates are retained. No global blur, image opacity, canvas recompression or board resampling is introduced by the glass layout. Only overlay backdrops receive the material treatment. |
| Real states | Preparation, approval, mandatory stop, red/unknown wait, review, fault and completion fit the same frame without lost controls. |
| Long content | Long goals, model reasoning, route lists and replay history use explicit bounded navigation. No warning or action is silently clipped. |
| Interaction | Keyboard focus, dialogs, tabs, pagination and reduced-motion preferences work; there are no decorative controls that promise unavailable behavior. |

Test no-vertical-scroll behavior by checking document dimensions and elements whose `scrollHeight` exceeds their client height. Check width overflow separately: only an explicitly designed horizontal carousel/page region may have more content than its client width, with navigation exposing that content. Fix content distribution rather than setting `overflow: hidden` over unreadable content. A successful build and a lack of horizontal overflow alone do not satisfy this design requirement.

These visual and interaction checks have a stated scope in verification. They do not by themselves establish full accessibility conformance, perfect readability over every possible camera scene or complete visibility underneath overlays.

The frontend remains React/TypeScript with a locally built Vite bundle. GX10 serves the compiled frontend with Python. This direction requires no remote font, runtime Node.js, graphics service or device dependency. Use restrained CSS effects and deterministic SVG where suitable. Frontend changes do not require restarting robot, camera or POC services.

## Visible goal entry

The current goal entry is a compact glass bar beneath a small map-context row. A quiet microphone control and **Your goal** label frame the accepted original query, with a separate Typed/Voice source badge. The right mission card continues to show the interpreted destination and plan, so the user's words remain distinct from model interpretation. Selecting the query opens bounded full-text pages. The voice panel clearly states **Not connected**, keeps capture disabled and offers text entry; no decorative waveform or listening animation implies an active microphone. The bar, camera controls and route legend keep separate vertical space without changing source-image geometry.

## Historical assets

Earlier navy/cyan illustrations and the first flat light-dashboard screenshot remain historical design records. Their captions must identify that stage; they do not establish compliance with this revision. A generated illustration is never a live product screenshot. Keep original print artwork and raw camera photographs outside Git and source packages.

[Frontend implementation](../frontend/README.md) · [Mission behavior](MISSION.md) · [Temporary map](TEMPORARY_MAP.md) · [Verification](VERIFICATION.md)
