# Current illustration generation record

**November 2, 2026 · English artwork · Built-in image generation tool**

[Artwork inventory](README.md) · [Current status](../CURRENT_STATUS.md) · [Original generation record](GENERATION_PROMPTS.md) · [Earlier voice revision](VOICE_GENERATION_PROMPTS.md)

These seven original illustrations refresh the public documentation while retaining **From sight to action** and **Observe → Plan → Approve → Act → Verify**. Meta MUSE is prominent as the intelligence for intent, route reasoning, signal judgment and visual outcome review. Deterministic admission, taught BASE execution and Native robot completion remain separate responsibilities.

The outputs are explanatory artwork, not actual application screenshots, camera frames, provider verdicts or proof of physical success. The workspace uses invented generic buildings and an illustrative route; it is not the installed map or its coordinate registration. The original supplied industrial-reference photographs, private map artwork, raw camera media and private model files were not submitted as generation references.

All new images used the built-in image generation tool. No fallback CLI or separately configured image API was used. The tool did not expose a model identifier. Each selected PNG was copied unchanged into this directory and reviewed for labels, arrows, status boundaries and readability. No programmatic raster editing was performed. See [current-assets.json](current-assets.json) for dimensions and SHA-256 hashes.

The workspace and architecture each received one targeted edit using only their own initial generated draft as the reference image. The architecture edit corrected a receipt connector; the workspace edit removed wheels and made Meta MUSE more prominent. Drafts remain outside the public repository. Exact initial and edit prompts follow.

## Workspace concept

Output: [`workspace-concept-current.png`](workspace-concept-current.png)

### Initial generation prompt

```text
Use case: ui-mockup / product-concept illustration.
Create a beautiful PushPilot GitHub hero illustration preserving its original AR-guided tabletop pushing concept and tagline "From sight to action". This is explicitly an ORIGINAL CONCEPT ILLUSTRATION, not an actual screenshot, camera image or success evidence. Do not copy supplied artwork or a real city model.
Wide landscape editorial hero, straight-on screen-like composition with no monitor bezel or perspective distortion. Current product visual language: off-white continuous tabletop background, large rounded translucent glass overlays, charcoal Pretendard-like sans-serif, diffuse shadows, restrained warm orange controls; no dark blue neon, no toy dashboard clutter, no stock-photo humans.
Show an original clean miniature tabletop city layout from a gentle oblique natural camera perspective, with four distinct generic building blocks around a simple central road junction. Place names: Villa upper-left, Hanok upper-right, Pizza lower-left, Office Building lower-right. Use clean charcoal-grey roads and muted original low-detail buildings, not printed photographic textures.
A small white wheel-less car rests on the road in front of Pizza. At the lower-left edge, only part of a restrained orange robot arm and a red soft pushing pad are visible behind the car; it PUSHES on the surface, never grasps or lifts. Keep the robot secondary, the scene and understandable AR plan dominant.
A single clear planned AR path starts at the car, travels RIGHT along the south road, turns UP at the central approach, then LEFT to the road in front of Villa. Thin muted blue-grey path, crisp arrowheads oriented along that path, warm-orange destination ring. Do not run the path through buildings. A small standing two-color paper traffic signal is at the right of the northbound junction approach.
Overlay a narrow translucent icon rail on the left and a large rounded translucent mission card at the right. Keep scene legible through glass, no opaque solid white blocks.
Use only this UI text: top-left "PushPilot"; below it "From sight to action"; top-right small "CONCEPT ILLUSTRATION"; mission card "A shared plan." then "Pizza → Villa" then small "Awaiting approval"; bottom glass strip "Observe · Plan · Approve · Act · Verify".
No live/connected labels, no timestamps, no completion percentages, no camera-quality or hardware claims. No other text. Emphasize mature, quiet industrial software design rather than game graphics.
```

### Targeted edit prompt

The sole reference was this illustration's initial generated draft.

```text
Use case: precise-object-edit. Input image is the EDIT TARGET: the original generated PushPilot light/glass tabletop concept illustration.
Keep the overall composition, all four buildings and their labels, robot location, pushing contact, road geometry, every AR arrow, destination ring, typography, soft lighting and the "CONCEPT ILLUSTRATION" label unchanged.
Make these targeted changes only:
1. The white car must be a SOLID WHEEL-LESS MODEL. Remove both visible dark circular wheels and any wheel wells, replacing them with continuous white lower body. It rests and slides flat on the road; no wheels anywhere.
2. In the generous empty upper-middle sky space, add a refined frosted-glass badge with a restrained orange outline and exact heading "Meta MUSE", and smaller subtext "Intent · Route · Visual review". Make this badge readable and prominent, without overlapping the PushPilot title, building labels or mission card.
3. Inside the existing right mission card, keep "A shared plan.", "Pizza → Villa" and "Awaiting approval". Add one tasteful small line below: "MUSE route proposal".
Do not change any other content. Do not introduce live/connected/success claims, metrics, extra text, screenshots or vendor logos. Preserve mature glass-dashboard design.
```

## Meta MUSE intelligence

Output: [`muse-intelligence-current.png`](muse-intelligence-current.png)

### Initial generation prompt

```text
Use case: infographic-diagram.
Create a refined English PushPilot documentation graphic making Meta MUSE the unmistakable intelligence at the heart of the product. Keep original "From sight to action" concept. Wide landscape, industrial light/off-white #F2F4F5 canvas, softly rounded frosted-white cards, charcoal text, strong but restrained warm-orange #E88350 emphasis around the central MUSE card, subtle shadows, spacious layout, large crisp Pretendard-like sans-serif lettering. No navy/cyan, photographs, fake metrics, success rates or invented vendor logos.
Title "PushPilot". Subtitle "From sight to action". Main heading "Meta intelligence. Visible decisions."
Three-column flow:
LEFT, one tall glass source card titled "Grounded input" with three simple line-icon rows "Operator goal", "Original images", "Selected map graph".
CENTER, the visually largest and strongest card, warm-orange outline and gentle warm glow, titled "Meta MUSE". Below it exactly "Understand intent" / "Reason over routes" / "Judge visual evidence". This is the focal point.
RIGHT, one tall glass result card titled "Structured judgment" with three clear rows "Plan the route", "Read the signal", "Review the outcome".
One simple arrow Grounded input → Meta MUSE; one simple arrow Meta MUSE → Structured judgment. No crossing connectors.
Below these cards, one long glass card titled "Mission supervisor + coordinate executor" with exact subtext "Validate the judgment · Admit the action · Verify the receipt".
A clear down arrow from Structured judgment into this lower card. A subtle return line from lower card to Grounded input labelled "New evidence" may run around the left outer margin, never through cards.
Footer exactly "MUSE makes the evidence understandable. The supervisor decides when motion may proceed."
No direct MUSE-to-robot-coordinate arrow. No claims of measured vehicle pose or qualified repeatability. No other copy.
```

## Current architecture

Output: [`architecture-current.png`](architecture-current.png)

### Initial generation prompt

```text
Use case: infographic-diagram.
Create a polished, precise English documentation architecture image for PushPilot. Preserve the original product concept and tagline "From sight to action". This is an architecture illustration, never a screenshot or evidence of hardware reliability.
Style: industrial light dashboard, off-white #F2F4F5 canvas, large softly rounded frosted-glass white cards, charcoal #263238 text, quiet grey connectors, restrained warm orange #E88350 accents, generous negative space, subtle soft shadows. Crisp Pretendard-like sans-serif lettering. No dark navy theme, no cyan neon, no 3D monitor mockup, no photos, no maps, no invented metrics or logos. Wide landscape, large labels readable at 1000px.
Title "PushPilot". Subtitle "From sight to action". Small top-right label "CURRENT SOFTWARE ARCHITECTURE".
Use exactly these labelled cards in a clean 3-column composition:
Top left: "Tablet workspace" / "Goal · Plan · Approve".
Top middle, strongest card: "Mission supervisor" / "State · Checks · Holds".
Top right: "Execution adapters", with two visibly separated rows "Simulation" and "Site-trial executor".
Below execution adapters: "Rodi + Native" / "Commands · Verified receipts".
Below left: "Camera + MUSE" / "Original images · Visual review".
Bottom middle: "Evidence + replay" / "Inputs · Receipts · Decisions".
Small left-side secondary card under Tablet workspace: "Voice adapter" / "Backend ready · Browser pending".
Precise arrows: Tablet workspace → Mission supervisor labelled "Approved task"; Mission supervisor → Execution adapters labelled "Admitted action"; only Site-trial executor → Rodi + Native; Rodi + Native → Mission supervisor labelled "Receipts", routed at outer right margin; Camera + MUSE → Mission supervisor labelled "Visual judgment"; Mission supervisor → Evidence + replay; Evidence + replay → Tablet workspace routed at outer bottom/left. Voice adapter stays secondary and may have a small dotted connection to Tablet workspace labelled "UI pending". No direct Camera/MUSE → robot arrow. No crossed connectors.
Footer exactly: "MUSE reviews. The supervisor admits. Taught BASE coordinates drive motion."
Second footer line exactly: "Current-site trials are not repeatability qualification."
```

### Targeted edit prompt

The sole reference was this illustration's initial generated draft.

```text
Use case: precise-object-edit. Input image is the EDIT TARGET: the existing PushPilot light/glass architecture illustration.
Preserve the complete image, every card, all typography, exact text, colors, spacing and other connectors.
Make exactly one semantic connector correction:
REMOVE the far-right outer loop that goes from "Rodi + Native" up into the "Simulation" row. Remove its "Receipts" label and its arrowhead. Hardware receipts must not point into Simulation.
The existing inner connector from the LEFT edge of "Rodi + Native" to the RIGHT edge of "Mission supervisor" already has the correct direction. Keep that connector and add the small label "Receipts" beside its horizontal segment.
Keep every other connection unchanged. No new cards or copy, no layout change, no crossed lines.
```

## Interaction loop

Output: [`interaction-current.png`](interaction-current.png)

### Initial generation prompt

```text
Use case: infographic-diagram. Create an English PushPilot repository illustration. Wide landscape, clean industrial light dashboard, off-white #F2F4F5 background, spacious rounded frosted-glass white cards, charcoal text, warm orange #E88350 accents and quiet grey arrows. Large crisp Pretendard-like sans-serif typography, restrained soft shadows, beautiful professional editorial layout. Preserve original concept, no navy/cyan theme, no photographs, fake screenshots, hardware readiness indicators or invented metrics.
Title "PushPilot". Subtitle "From sight to action".
Main heading "One loop. Visible decisions."
Five equally sized cards in one clear left-to-right row, with simple line icons and exactly this copy:
"01" / "Observe" / "Inspect the scene"
"02" / "Plan" / "Interpret the goal"
"03" / "Approve" / "Confirm the mission"
"04" / "Act" / "Execute a bounded unit"
"05" / "Verify" / "Review the outcome"
One thin warm-orange arrow between each card. A clean returning line from Verify underneath the row goes back to Observe, labelled "Continue · Wait · Reobserve · Hold". It must not cross any card.
Below, one slim glass strip with exact text "Coordinate motion → Clear the view → MUSE review".
Footer exactly "Native receipts confirm the tool. Visual evidence checks the car."
Small footer note "Conceptual workflow · step-specific review rules remain explicit".
No extra text, no legends, no maps. Treat MUSE as reviewer, not the robot controller.
```

## Evidence loop

Output: [`evidence-current.png`](evidence-current.png)

### Initial generation prompt

```text
Use case: infographic-diagram. Create a precise English PushPilot evidence infographic. Preserve the original concept "From sight to action": a tool reaching its endpoint is not enough to prove the car reached its goal. Wide landscape, current industrial light style: off-white canvas, softly rounded white frosted-glass cards, charcoal text, restrained orange lines and highlights, soft shadows, spacious balanced layout, large clear Pretendard-like sans-serif. No navy/cyan, no photos, fake screenshots, extra logos or performance metrics.
Title "PushPilot". Subtitle "From sight to action". Main heading "Evidence behind every decision".
Four equal main cards across the image with arrows left to right:
"01 · Expected" / "Approved goal" / "Bounded coordinate unit"
"02 · Observed" / "Native endpoint receipt" / "Original images after withdrawal"
"03 · Reviewed" / "MUSE judgment" / "Required local checks"
"04 · Decided" / "Continue · Wait" / "Reobserve · Hold"
Below all four cards, one long glass bar linked by thin vertical lines from the four cards, titled "Recorded for replay" with exact subtext "Mission + action IDs · Image hashes · Prompt versions · Decision cause".
Footer exactly "Robot completion and vehicle outcome remain separate evidence."
Second footer exactly "Preserve original failures. Never replay an unknown motion."
Avoid any image that looks like a real camera observation or measured successful run. Keep every word readable; no unnecessary arrows or panels.
```

## GX10 delivery

Output: [`delivery-current.png`](delivery-current.png)

### Initial generation prompt

```text
Use case: infographic-diagram. Create a precise English PushPilot deployment infographic in its current industrial light/glass visual language. Wide landscape off-white #F2F4F5 background, white translucent softly rounded cards, charcoal #263238 text, warm orange #E88350 accents, thin neutral connectors, clear Pretendard-like sans-serif, generous whitespace and diffuse shadows. No dark blue/cyan, no stock photos or fake metrics.
Title "PushPilot". Subtitle "From sight to action". Heading "Build locally. Serve on GX10."
Across the top place exactly four cards linked left to right:
"01 · Local workspace" / "Source · Tests · Frontend build"
"02 · Reviewed commit" / "GitHub main"
"03 · Source release" / "Archive · Hash manifest"
"04 · GX10 release" / "Verify · Deliberately activate"
Below the GX10 release card, a wide glass panel titled "Separate runtime services" containing three simple labelled tiles "Web application", "Camera helper", "Robot API + Rodi host". Do not make these a linear dependency chain.
Below the release pipeline, a lower-left panel titled "Public source" with "Code · Docs · Tests".
Lower-middle/right panel titled "Private runtime" with "Credentials · Artwork · Models" on one line, "Taught coordinates · Profiles · Evidence" on next line.
Subtle visual separation of public source vs private runtime; no connector suggesting private files are uploaded to GitHub. Existing release folders and shared data can be shown only as small labels "releases/" and "shared/" inside the runtime area.
Footer exactly "Publishing code does not activate a robot mission."
Second footer "A release keeps private state separate and never replays pending commands."
No NOT DEPLOYED badge, no future deployment claim, no claims that software tests qualify hardware. Do not add copy beyond the specified text.
```

## Voice input

Output: [`voice-current.png`](voice-current.png)

### Initial generation prompt

```text
Use case: infographic-diagram. Create an English PushPilot voice-input architecture illustration in current industrial light dashboard styling. Preserve the product concept "From sight to action" and explicit plan approval. Wide landscape off-white background, spacious rounded frosted-white cards, charcoal type, restrained orange accents, neutral connectors and soft shadows. Clear large Pretendard-like sans-serif, no navy/cyan, photographs, vendor logos, fake UI or invented recognition statistics.
Title "PushPilot". Subtitle "From sight to action". Heading "Voice becomes a reviewable goal".
A clean left-to-right sequence of five cards:
"01 · Capture" / "Push-to-talk" / small badge "Browser pending"
"02 · Transcribe" / "Bounded WAV upload" / "Meta voice adapter" / small badge "Backend implemented"
"03 · Confirm text" / "Review · Edit · Submit" / small badge "Browser pending"
"04 · Interpret" / "MUSE goal + route" / small badge "Implemented"
"05 · Approve" / "Tablet mission approval" / small badge "Required"
Use solid subdued arrows to explain the intended sequence and dotted arrows at the pending browser boundaries. Keep badges visually distinct, pending grey and implemented soft orange; do not imply actual voice device testing or current microphone capture.
A secondary strip below exactly "Typed goals remain available."
Footer exactly "Credentials stay on the backend. A transcript never authorizes motion."
Second footer exactly "Actual ASR access and recognition quality remain unverified."
Do not add any other words.
```

No software or artwork license has been selected. Provenance records the work; it does not grant third-party redistribution rights.
