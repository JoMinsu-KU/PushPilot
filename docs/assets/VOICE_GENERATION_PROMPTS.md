# Voice diagram generation prompts

**Retained design source, October 27, 2026:** these exact prompts document the earlier navy/cyan illustration stage. The later industrial light-dashboard [design system](../DESIGN_SYSTEM.md) defines the current interface. Original prompt text below is preserved unchanged.

Two documentation assets were created on October 27, 2026 (Asia/Seoul) with the built-in image generation tool. The model identifier was not exposed. No API key or fallback CLI was used.

`architecture-overview-voice.png` is an image-generation edit using the repository's existing generated `architecture-overview.png` as its sole edit target. The original remains available as the previous design. `voice-input-flow.png` is a new generated image without an input image. Selected outputs were copied into this repository without pixel edits.

Both images describe planned voice and application behavior. No microphone, transcription API or robot was used to generate or validate them. The exact inputs follow.

## architecture-overview-voice.png

```text
Use case: infographic-diagram / targeted architecture revision.
Input image 1 is the EDIT TARGET: the existing PushPilot architecture. Preserve its dark navy #071522 background, restrained cyan outlines, large white headings, muted blue-gray body type, geometric line icons and professional editorial tone. Revise the diagram to explicitly include backend voice transcription. This is a conceptual documentation image, not a product screenshot. All copy English, no new metrics, no real map, no vendor logos or watermark.
Use a wide 3:2 landscape canvas. Keep the header "PushPilot" / "The system at a glance" and status pill "PROPOSED ARCHITECTURE". Rebalance spacing to use seven large readable cards with very few orthogonal connectors:
- Above center: "MUSE", "Goal interpretation", "Fresh-image review".
- Middle left: "Operator workspace", "Text or voice goal", "Transcript review + plan approval".
- Middle center, strongest border: "Mission supervisor", "State + deterministic gates", with the four labels "Approval", "Freshness", "Signal", "Capability".
- Middle right: "Action adapters", with "Simulator first" and muted dashed inset "Qualified robot later".
- Bottom left: "Voice adapter (backend)", "Muse Voice Transcribe", "Draft transcript only", and a small key icon with "Server-side credentials".
- Bottom center: "Evidence + replay", "Inputs • Reviews • Decisions", "Visible in the workspace".
- Bottom right: "Observations", "Images • Signal • Results".
Precisely these relationships: Operator workspace → Mission supervisor labelled "Goal + approval"; Operator workspace ↔ Voice adapter, with compact labels "Audio" downward and "Transcript" upward; MUSE ↔ Mission supervisor; Mission supervisor → Action adapters labelled "Accepted action"; Action adapters → Observations; Observations → Mission supervisor; Mission supervisor → Evidence + replay. Route the Observations-to-supervisor connector through whitespace between rows so it crosses no card. Do not invent connections from Voice or MUSE to Action adapters. An utterance or transcript cannot authorize motion.
Preserve large readable fonts and unclipped labels. Footer exactly: "Proposed design. Voice, image review and mission runtime are not yet implemented." The standalone successful text API probe does not mean any of these runtime components work.
```

## voice-input-flow.png

```text
Use case: infographic-diagram.
Asset type: PushPilot voice-input architecture documentation. Create a wide landscape approximately 2:1 image matching an English dark navy/electric cyan tablet product: opaque navy #071522, restrained cyan #00C8FF outlines, white #EDF5FF large sans-serif headings, muted blue-gray secondary type, spacious rounded cards, crisp line icons, subtle texture, professional and minimal. No photos, real map, vendor logos, fake readings or watermark.
Title "PushPilot" / "From voice to an approved goal". Top-right pill "PLANNED VOICE INPUT".
Exactly five equally sized cards left-to-right connected by small cyan arrows. Exact text:
Card1 "01" / "Speak" / "Push to talk"
Card2 "02" / "Transcribe" / "Backend → Meta Voice"
Card3 "03" / "Confirm text" / "Review or edit"
Card4 "04" / "Interpret" / "MUSE goal + plan"
Card5 "05" / "Approve" / "Tablet mission approval"
Use microphone, waveform-to-text, editable document, brain/goal and check icons respectively. Beneath cards a clear full-width band: "Audio and transcripts do not authorize motion." Beneath that, two quiet small labels, "Meta key stays on the backend" and "Text entry remains available".
Footer: "Design only. Microphone capture and voice API integration are not yet implemented."
Readability at 900px content width is essential; no tiny paragraphs. Do not add robot-motion arrows after a microphone, do not label speech-to-text as TTS, and do not imply hardware or a live provider connection.
```
