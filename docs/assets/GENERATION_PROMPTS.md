# Diagram generation prompts

**Retained design source, October 27, 2026:** these exact prompts document the earlier navy/cyan illustration stage. The later industrial light-dashboard [design system](../DESIGN_SYSTEM.md) defines the current interface. Original prompt text below is preserved unchanged.

The four PNG diagrams were generated on October 27, 2026 (Asia/Seoul) using the built-in image generation tool. The tool did not expose a model identifier. No API key, fallback CLI or source photograph was used. The prompts below are the exact generation inputs. Files were copied into this repository without pixel edits.

The diagrams are conceptual documentation. Their visible status labels and accompanying text distinguish proposed application behavior from implemented bootstrap tooling. They do not establish physical results or a deployed runtime. All four outputs were visually reviewed for copy, direction, authority boundaries and legibility.

## architecture-overview.png

```text
Use case: infographic-diagram.
Asset type: a production documentation image for the PushPilot GitHub repository.
Style: polished editorial technology infographic matching an English dark navy / electric cyan tablet product. Deep navy #071522 background, restrained cyan #00C8FF hairline accents, white #EDF5FF headings, muted blue-gray secondary text, subtly rounded panels, generous whitespace, precise large sans-serif typography. Professional and minimal, not a generic busy flowchart. Draw crisp minimal line icons. No photographs, no real map, no grid board, no vendor logo, no fake UI readings, no claims of working hardware. All copy must be English with exact spelling. Make every label large enough to read at 900px display width. Use only the specified short copy; do not invent extra metrics or captions. Opaque background, no watermark.
Create a wide landscape infographic, approximately 3:2.
Title: "PushPilot" and "The system at a glance". Top-right status pill: "PROPOSED ARCHITECTURE".
Composition: three main cards across the middle: left "Operator workspace" with "Goal • Approval • Review"; center and visually strongest "Mission supervisor" with "State + deterministic gates" and four small labels "Approval", "Freshness", "Signal", "Capability"; right "Action adapters" containing "Simulator first" and a visually muted dashed inset "Qualified robot later".
Above the center place a distinct "MUSE" card with "Goal interpretation" and "Fresh-image review". Below-left place an "Observations" card with "Images • Signal • Action results". Below-center place an "Evidence + replay" card with "Inputs • Reviews • Decisions" and "Visible in the workspace".
Precisely these connections: Operator workspace → Mission supervisor, labelled "Approved task"; MUSE ↔ Mission supervisor; Observations → Mission supervisor; Mission supervisor → Action adapters labelled "Accepted bounded action"; Action adapters → Observations labelled "Results"; Mission supervisor → Evidence + replay. Route the results connection around the outer right/bottom margin so it crosses no card or connector. No direct MUSE-to-action arrow. Few clean orthogonal connectors; no spaghetti.
Footer verbatim: "Design only. Application and device integrations are planned." Preserve the distinction that MUSE reviews and the supervisor admits execution. All components here are proposed, not live.
```

## interaction-loop.png

```text
Use case: infographic-diagram.
Asset type: a production documentation image for the PushPilot GitHub repository.
Style: polished editorial technology infographic matching an English dark navy / electric cyan tablet product. Deep navy #071522 background, restrained cyan #00C8FF hairline accents, white #EDF5FF headings, muted blue-gray secondary text, subtly rounded panels, generous whitespace, precise large sans-serif typography. Professional and minimal, not a generic busy flowchart. Draw crisp minimal line icons. No photographs, no real map, no grid board, no vendor logo, no fake UI readings, no claims of working hardware. All copy must be English with exact spelling. Make every label large enough to read at 900px display width. Use only the specified short copy; do not invent extra metrics or captions. Opaque background, no watermark.
Create a wide panoramic infographic approximately 2.5:1. Title "PushPilot" and "One loop. Visible decisions." Top-right pill "PROPOSED INTERACTION".
Exactly five equal large cards in one row connected left-to-right with small cyan arrows. Card copy verbatim:
"01" / "Observe" / "Fresh, source-labelled scene"
"02" / "Plan" / "Interpret the goal"
"03" / "Approve" / "Authorize the mission"
"04" / "Act" / "One bounded action"
"05" / "Verify" / "MUSE + local checks"
Use simple eye, plan, check, action/play and shield/eye line icons respectively. Below the row, one calm full-width caption band, not extra boxes: "Each action requires fresh evidence and accepted review before continuation."
Bottom-left footer "Conceptual workflow. Application implementation is planned."
Do not imply a human must reapprove every action: approval is for the mission, ongoing reviews gate continuation. Crisp readable large headings, no tiny paragraphs.
```

## evidence-loop.png

```text
Use case: infographic-diagram.
Asset type: a production documentation image for the PushPilot GitHub repository.
Style: polished editorial technology infographic matching an English dark navy / electric cyan tablet product. Deep navy #071522 background, restrained cyan #00C8FF hairline accents, white #EDF5FF headings, muted blue-gray secondary text, subtly rounded panels, generous whitespace, precise large sans-serif typography. Professional and minimal, not a generic busy flowchart. Draw crisp minimal line icons. No photographs, no real map, no grid board, no vendor logo, no fake UI readings, no claims of working hardware. All copy must be English with exact spelling. Make every label large enough to read at 900px display width. Use only the specified short copy; do not invent extra metrics or captions. Opaque background, no watermark.
Create a wide landscape infographic approximately 16:9. Title "PushPilot" and "Evidence behind every decision". Top-right pill "PROPOSED EVIDENCE FLOW".
Four spacious equal cards in one left-to-right row, connected with short cyan arrows. Exact copy:
Card 1: "01" / "Expected" / "Approved goal" / "Bounded action"
Card 2: "02" / "Observed" / "Action result" / "Fresh, source-labelled image"
Card 3: "03" / "Reviewed" / "MUSE judgment" / "Required local checks"
Card 4: "04" / "Decided" / "Mission supervisor" / "Continue • Wait" / "Reobserve • Fault"
Use restrained symbolic icons: target, camera, paired review/check, branching state.
Below, a single broad evidence strip titled "Recorded for replay", with the exact text "Mission + action IDs  •  Image hash  •  Prompt + model versions  •  Decision cause". A thin line links the row down to this strip, indicating records are retained.
Footer verbatim: "Design only. A model judgment cannot replace a verified stop, fresh signal or action receipt."
No fake timestamps, percentages, run results, or dashboard. Do not depict MUSE as directly commanding a robot. Large readable labels.
```

## delivery-flow.png

```text
Use case: infographic-diagram.
Asset type: a production documentation image for the PushPilot GitHub repository.
Style: polished editorial technology infographic matching an English dark navy / electric cyan tablet product. Deep navy #071522 background, restrained cyan #00C8FF hairline accents, white #EDF5FF headings, muted blue-gray secondary text, subtly rounded panels, generous whitespace, precise large sans-serif typography. Professional and minimal, not a generic busy flowchart. Draw crisp minimal line icons. No photographs, no real map, no grid board, no vendor logo, no fake UI readings, no claims of working hardware. All copy must be English with exact spelling. Make every label large enough to read at 900px display width. Use only the specified short copy; do not invent extra metrics or captions. Opaque background, no watermark.
Create a wide landscape infographic approximately 16:9. Title "PushPilot" and "From local source to GX10". Top-right pill "DELIVERY PLAN".
Four equal spacious cards across one row, connected with clean cyan arrows. Exact copy:
Card 1: "01" / "Local workspace" / "Source checks + tests"
Card 2: "02" / "Reviewed commit" / "Recorded on GitHub"
Card 3: "03" / "Source release" / "ZIP + hash manifest"
Card 4: "04" / "GX10 release" / "Future isolated runtime"
Use code, git-history, package, server icons. Place a subtle cyan bracket beneath cards 1-3 labelled "Available repository tooling". Make card 4 distinctly muted with a dashed outline and its own small pill "NOT DEPLOYED". Only the arrow from card 3 to card 4 is dashed, labelled "Future transfer + verification".
Below the main row, one small separated inset titled "Proposed host separation" containing just "releases/" and "shared/" in two compartments. Under shared use "Config • Secrets • Evidence • Logs". This is a proposal; no actual machine paths, usernames, IP addresses or ports.
Footer verbatim: "Packaging does not transfer files, start services or operate the robot."
No auto-deployment, CI success or active-host claim. All text English, no invented values.
```
