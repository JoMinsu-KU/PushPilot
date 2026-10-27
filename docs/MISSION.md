<div align="center">

# The mission

**A small car. A visible plan. A decision at every intersection.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Voice input](VOICE_INPUT.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Roadmap](ROADMAP.md)

</div>

---

The intended demonstration begins at **PIZZA**. The operator states or types a destination, confirms the chosen text, reviews the understood goal and explicitly approves the mission. A robot pushes a wheel-less car across the tabletop, stops before each configured intersection, waits for a green paper signal and continues to the destination.

**This is the scenario specification, not a completed physical demonstration.** The current temporary-map adapter provides drawing-grounded PIZZA/BAKERY/BOOKSTORE/SCHOOL routes and abstract simulation. A recorded-image overlay is test-only. Production installation, robot coordinates, actual pushing, and turning remain unqualified.

The October 28 final-print design uses one proposed active paper signal for the central junction's designated PIZZA approach, with a fixed PIZZA start, initial map-east departure and mandatory passage through that controlled stop checkpoint. Junction, incoming approach and signal must be identified together; the final approach nodes and stop geometry remain pending. Proposed display names and the exact boundary are recorded in [the single-signal concept](MUSE_SIGNAL_GATE.md#single-signal-final-print-concept-october-28). The active temporary map is unchanged.

## Operator journey

| Phase | What the operator sees | What the system must establish |
|---|---|---|
| **Observe** | Scene source and available evidence | Which inputs are simulated, recorded or live |
| **Plan** | Understood goal, expected outcome and pending checks | A supported symbolic interpretation; no invented map grounding |
| **Approve** | A clear review action | Approval of the current mission version |
| **Act** | The current bounded action and progress | The selected adapter's action result |
| **Verify** | Expected/observed comparison and MUSE decision | Fresh imagery, accepted local checks and model review |

Each bounded action returns to verification. The current simulator accepts either an explicitly demo-sourced verdict or an action-bound MUSE review of operator-selected recorded images. Rejection and uncertainty change the next state. Recorded pairs are not fresh physical post-action evidence; see [Action reviews](ACTION_REVIEWS.md).

## Goal entry and approval

Voice input is part of the planned initial demo. The operator makes a bounded push-to-talk recording, the backend sends it to Meta Muse Voice Transcribe, and the workspace presents an editable transcript. The original provider text remains inspectable. Choosing `Use goal` submits the selected text to MUSE goal interpretation; it does not authorize execution.

Typed text enters the same interpretation and plan-review path. The English interface may display actual Korean or English transcript data. Permission denial, empty transcription, failed requests or cancellation leave typed entry available and cannot create or approve a mission. A late result from an older recording cannot replace newer input.

New typed or spoken goals are accepted only during non-executing preparation. While a mission is active, including signal waiting, observation review and crossing, reject recording, new goal submission and goal edits. A replacement goal follows explicit completion/termination and state reconciliation; capture cancellation does not stop the mission.

Only explicit tablet approval of the current interpreted mission version authorizes the mission to proceed through its deterministic gates. See [voice input](VOICE_INPUT.md) for the full proposed service and state contract. Microphone capture and transcription are planned, not implemented.

## The nominal sequence

```text
Voice recording or typed request
  → review/edit text and choose Use goal
  → MUSE interpretation and plan review
  → explicit approval of the PIZZA mission
  → bounded push
  → verify outcome
  → approach an intersection
  → stop before its stop line
  → verify stopping and send a new image to MUSE for signal judgment
      MUSE RED / UNKNOWN → remain stopped and observe again
      valid current MUSE GREEN + accepted binding checks → admit crossing
  → execute and review the qualified crossing actions
  → continue toward the destination
  → verify the destination outcome
```

The temporary adapter starts east-facing at PIZZA. Its default shortest drawing routes are PIZZA → C → S → BAKERY (232 mm, eight abstract steps), PIZZA → C → BOOKSTORE (148 mm, five steps), and PIZZA → C → S → SCHOOL (232 mm, eight steps). Each traversed junction receives PUSH approach, mandatory STOP, accepted action review, and separately scoped fresh simulated GREEN before CROSS. These drawing lengths and centerlines do not qualify the car/tool swept path or physical stop lines. The final production installation may change all of these details; see [Temporary map](TEMPORARY_MAP.md).

## Intersection policy

| Situation at the approach | Required behavior |
|---|---|
| Green before arrival | Stop first; then ask MUSE to judge a new image |
| MUSE reports RED after verified stopping | Wait without beginning the crossing |
| Card absent, obscured, ambiguous or stale | Treat entry as inhibited |
| Signal changes while waiting | Capture a new image and obtain another MUSE judgment |
| MUSE reports current GREEN and stop/request checks pass | Continue automatically through the admitted crossing |
| Application restarts while waiting or crossing | Return to review; do not restore permission from old observations |

The simulator automatically admits one crossing after an accepted mandatory-stop review and fresh simulated GREEN bound to that same junction, without another approval. It clears stop/signal authority before the next approach, which requires its own stop and review. The corresponding physical red-to-green continuation still requires a qualified robot adapter; no pendant or robot operation is supplied by this application.

For the intended live scenario, **MUSE judges RED/GREEN from the image while the robot is already stopped**. A separate local color classifier is not mandatory. Local checks validate the stop receipt, current junction/approach and plan, frame provenance/freshness and exact model-request binding. The dedicated live signal-review integration is not yet implemented; the current simulation signal controls and recorded-review APIs keep their existing meaning. See [MUSE signal gate](MUSE_SIGNAL_GATE.md).

The scenario concerns **stop-line admission**. Changing a card during an admitted crossing is not specified as an immediate interruption request. Any later in-flight stop requirement would need a separate controller-supported design and qualification.

## Pushing and turning

The car remains on the surface. It is not picked up or carried. Straight pushes and turns are distinct physical primitives that must be measured with the eventual vehicle, surface and tool.

A turn may require changing the contact point and applying an off-center push. Rotating the robot wrist alone does not establish that the car rotated correctly. After each bounded push or turn, vehicle evidence must be checked separately from the robot's endpoint result.

Tool clearance, observation poses, friction, slip, contact heights and usable turning space remain physical qualification work. The abstract simulator can test mission sequencing but cannot validate these properties.

## What completes an action?

The simulator advances through its simulated action receipt and a review accepted by the supervisor. That review is either an operator-injected demo verdict or a validated MUSE result bound to a selected recorded before/after pair and the exact pending action. PASS can satisfy the review gate, FAIL faults the simulation, and REOBSERVE/UNKNOWN requires a new observation binding without replaying the action. A model PASS cannot bypass RED/UNKNOWN/stale signal inhibition. Separate recorded-scene inspection cannot complete a step or supply its GREEN.

The future physical supervisor still needs three kinds of independently supported evidence:

1. **Action evidence:** the action adapter reports the result for the correct request/session.
2. **Local evidence:** stop/action receipts, capture provenance, freshness and current plan/junction/request bindings support accepting the applicable MUSE judgment; this does not require independent local color classification.
3. **Model evidence:** MUSE reviews fresh imagery and supports the expected-versus-observed outcome.

A successful robot movement cannot substitute for evidence that the car moved as intended. A confident model answer cannot substitute for a required local check. If the scene is hidden or the evidence conflicts, the next step is waiting, reobservation or a visible fault.

## What completes the mission?

Mission completion requires the approved destination outcome to be verified from the corresponding final observations and checks. The final geometry will define the destination region and acceptable pose. Until then, software tests must use clearly named symbolic completion conditions.

The demonstration should leave an inspectable sequence of the goal, actions, observations, model reviews, waits and final decision. A completed simulation must remain labelled as simulation.

## Interface direction

The primary surface is an **English tablet workspace** following the industrial light-dashboard [design system](DESIGN_SYSTEM.md): an off-white canvas, white panels, charcoal text, a narrow icon rail and restrained orange accents. The scene is the dominant viewport, with mission decisions beside it and compact summary cards below. Its key content is:

| View | Content |
|---|---|
| **Workspace** | Typed goal, scene/map, current action, recorded-image review, expected/observed comparison, MUSE decision and next check; voice/transcript entry remains planned |
| **Plan** | Current symbolic interpretation, approval state and action sequence |
| **Replay** | Source-aware timeline with images, actual review responses and transition causes |

The temporary recorded-image view can project the drawing route through an explicitly locked four-marker homography. Occlusion does not trigger refitting; changed or unverifiable views withhold the overlay. This test-only projection is separate from production metric AR and robot registration. The **glasses companion** remains a clearly labelled future concept. Hardware connection, microphone capture, transcription and wearable display behavior must only be shown as live capabilities when they are actually implemented and supported by evidence. Streaming transcription and spoken feedback are later extensions.

---

[← Architecture](ARCHITECTURE.md) · [Next: Meta intelligence →](META_INTELLIGENCE.md)
