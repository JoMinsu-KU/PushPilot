<sub>[PushPilot](../README.md) / Product / Design system</sub>

# The operator workspace design

**A calm industrial dashboard with the scene at its center.**

The user selected two industrial operations-dashboard references on October 27, 2026 and requested the closest practical match. This direction supersedes the earlier dark navy/electric cyan interface. The references guide composition, density, surfaces and interaction styling. PushPilot keeps its own identity, real mission content and evidence boundaries; unrelated production metrics, people and factory machinery are not product data.

## Composition

| Area | Direction |
| :--- | :--- |
| Canvas | Very light neutral gray, with generous outer spacing. |
| Navigation | Narrow full-height white icon rail, a compact PushPilot mark and a quiet separator. The active item uses a pale orange surface and orange icon. |
| Header | Clean white horizontal panel with the current view title and concise, truthful connection/mode information. |
| Main scene | The dominant surface. Show the recorded camera frame or temporary spatial map with a compact view switch and nearby image tools. Preserve the complete image. |
| Mission panel | Right column containing destination, route steps, checks and the next operator action. Keep primary controls visible with long routes. |
| Summary cards | A compact bottom row for real mission status, scene/evidence information and the future glasses-companion concept. |
| Plan and replay | Use the same surfaces, typography, restrained controls and evidence hierarchy as the workspace. |

Favor the reference's broad light surfaces and quiet separation over decorative outlines or glow. Keep related controls grouped and secondary preparation tools subordinate to the scene and mission.

## Color and typography

Use off-white for the page, white for cards, charcoal for headings and medium gray for supporting text. Thin light gray lines and soft shadows separate panels. Orange is the primary interaction accent for selected navigation, key emphasis and the main action. Avoid treating every border or icon as an accent.

Use a local system sans-serif stack. Headings are clear and moderately weighted; body text stays readable at tablet sizes. Small labels may be muted, but important source, warning and disabled-state text must remain legible. All authored UI copy, accessibility text and development material remain English.

Red, green and amber retain their semantic meaning for signal and review status. Always pair a color with a label or icon. A GREEN label without valid source and freshness does not establish crossing admission.

## Scene and AR overlays

The camera viewport has different contrast needs from the surrounding white dashboard. Route strokes need a contrasting casing and labels need readable backgrounds over both dark and bright photographs. Draw arrows with SVG geometry aligned to the route segments; never substitute text glyphs or let a corner marker imply a diagonal movement.

Keep the image and overlay in the same intrinsic coordinate system. Do not crop a recorded frame to fill a panel, distort its aspect ratio, or move annotations with independent CSS offsets. Route, map and registration identities must still match. A candidate fit remains a candidate, and a changed view withholds the old projection.

The spatial schematic remains a drawing preview. A planned path over a recorded photograph is a test overlay; neither view is measured robot motion or qualified metric AR.

## Interaction and source truth

Preserve **Observe → Plan → Approve → Act → Verify**. State, next check and the resulting action should be easy to locate. The light design changes presentation without changing mission admission or review behavior.

- Keep the exact-plan approval step and the server-owned revision/state boundaries.
- Label recorded/uploaded imagery, simulation, demo verdicts and actual provider calls independently.
- Keep MUSE scene inspection separate from action-bound verification and deterministic signal admission.
- Show unavailable voice, robot and live-camera capabilities honestly.
- Label AR glasses as a future companion concept. Do not imply a connected wearable or place fabricated hardware readings in summary cards.
- Keep errors, uncertainty, mandatory stop and red/unknown waiting states prominent enough to notice without relying on color.

## Responsive and implementation requirements

Use CSS Grid and flexible containers to keep the scene dominant beside the mission panel on wide screens. At narrower widths, stack panels in a clear reading order without horizontal page overflow. Long route lists may scroll within their own bounded region; the current step must not unexpectedly scroll the whole page. Keyboard focus stays visible, icon controls have accessible names, and reduced-motion preferences are respected.

Verify the camera and spatial views, plan, replay, preparation controls and waiting/review states at desktop, tablet and narrow mobile widths. Check route arrows, label clipping, button wrapping, disabled controls and image aspect ratio visually after layout changes.

The frontend remains React/TypeScript with a locally built Vite bundle. Python serves the static build and API on GX10; the redesign adds no remote font, runtime Node.js, graphics service or device dependency. Robot, camera and POC services do not need a restart for frontend design changes.

## Historical assets

Earlier navy/cyan screenshots, generated process diagrams and their original generation prompts remain historical design and verification records. Their colors do not override this specification. Captions must state the relevant design stage; a generated illustration is never a live product screenshot. Keep original print artwork and raw camera photographs outside Git and source packages.

[Frontend implementation](../frontend/README.md) · [Mission behavior](MISSION.md) · [Temporary map](TEMPORARY_MAP.md) · [Verification](VERIFICATION.md)
