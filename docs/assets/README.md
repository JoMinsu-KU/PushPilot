# Documentation artwork

**PushPilot's navy/cyan visual language, with readable decisions and explicit status.**

[Repository](../../README.md) · [Architecture](../ARCHITECTURE.md) · [Generation prompts](GENERATION_PROMPTS.md) · [Voice revision prompts](VOICE_GENERATION_PROMPTS.md)

The repository uses a self-contained SVG cover and generated PNG process diagrams. The PNGs display directly as images, without a diagram renderer or build step. Select a diagram in its document to inspect the full-size asset. Essential technical meaning is also retained as ordinary English text and tables.

## Asset inventory

| Asset | Canvas | Use and origin |
|---|---|---|
| [`hero.svg`](hero.svg) | 1280 × 480 | Active repository cover; original code-native vector. |
| [`temporary-map-workspace.jpg`](temporary-map-workspace.jpg) | Browser screenshot | Current application: original spatial schematic, temporary Bakery route, source-labelled MUSE inspection and simulation controls; no supplied artwork or raw camera frame is visible. |
| [`workspace-simulation.jpg`](workspace-simulation.jpg) | Browser screenshot | Retained first-slice workspace before temporary-map integration; original illustrative scene and simulation labels. |
| [`interaction-loop.png`](interaction-loop.png) | 1983 × 793 | Main README: Observe → Plan → Approve → Act → Verify; AI-generated. |
| [`architecture-overview-voice.png`](architecture-overview-voice.png) | 1536 × 1024 | Active architecture: adds backend voice transcription, transcript review and credentials boundary; AI-generated edit. |
| [`voice-input-flow.png`](voice-input-flow.png) | 1774 × 887 | Voice: push-to-talk, transcription, editable text, MUSE interpretation and tablet approval; AI-generated. |
| [`architecture-overview.png`](architecture-overview.png) | 1536 × 1024 | Retained previous architecture, before voice became initial-demo scope; superseded in the architecture document. |
| [`evidence-loop.png`](evidence-loop.png) | 1672 × 941 | Architecture: expected, observed, reviewed and decided; AI-generated. |
| [`delivery-flow.png`](delivery-flow.png) | 1672 × 941 | Deployment: implemented source tooling and future GX10 delivery; AI-generated. |
| [`workflow.svg`](workflow.svg) | 1280 × 254 | Retained editable source from the initial documentation design; superseded in the main README. |

## Provenance

The SVGs were authored for this repository on October 27, 2026 as original geometric vectors. They embed no third-party photographs, stock illustrations, fonts or vendor logos. The workspace screenshots were captured from the running local application on the same date after browser verification. The first scene's robot, wheel-less car and glasses are original SVG illustrations; the current spatial schematic draws adapted map geometry with original presentation code. The current screenshot also shows an actual recorded-image MUSE result as text. Raw camera media and supplied map artwork remain outside the public repository. These are software/provider records, not physical-execution evidence.

The original four PNGs were generated on October 27, 2026 (Asia/Seoul) with the **built-in image generation tool**; their exact inputs remain in [GENERATION_PROMPTS.md](GENERATION_PROMPTS.md). A voice-enabled architecture revision and voice flow were added on the same date, with exact inputs in [VOICE_GENERATION_PROMPTS.md](VOICE_GENERATION_PROMPTS.md). The architecture revision uses the earlier repository-generated image as its sole edit target. No fallback CLI, API key or external reference image was used. Selected outputs were copied unchanged into this directory and visually reviewed for English spelling, arrows, authority boundaries, status and readability.

Every process illustration describes the intended design. It is not a camera observation, provider result, live deployment or evidence of physical execution. Proposed application components, a later qualified robot adapter and the undeployed GX10 runtime remain visibly labelled. The source-release tools are implemented; generating a diagram does not implement the system it depicts.

## Updating a diagram

- Keep the dark navy background, restrained electric cyan, white headings and large English labels.
- Preserve MUSE's interpretation/review role and the supervisor's deterministic admission authority.
- Keep approval scoped to the mission; per-action reviews gate continuation.
- Preserve planned, future and undeployed labels where applicable.
- Do not introduce map geometry, robot coordinates, invented metrics or fabricated success evidence.
- Regenerate a PNG with a targeted image-generation edit; review every changed label and connector.
- Update the exact prompt, alt text, surrounding explanation and provenance with the asset.
- Keep SVGs self-contained and maintain their accessible title/description.

No software or artwork license has been selected for this repository. Provenance is not a license grant.
