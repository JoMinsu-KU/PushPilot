<div align="center">

# The mission

**A small car. A visible plan. A decision at every intersection.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Voice input](VOICE_INPUT.md) · [Meta intelligence](META_INTELLIGENCE.md) · [Roadmap](ROADMAP.md)

</div>

---

The intended demonstration begins at **PIZZA**. The operator states or types a destination, confirms the chosen text, reviews the understood goal and explicitly approves the mission. A robot pushes a wheel-less car across the tabletop, stops before each configured intersection, waits for a green paper signal and continues to the destination.

**This is the scenario specification, not a completed physical demonstration.** PIZZA and destinations remain symbolic until the final map and installation are available. Current software work uses abstract actions and explicit simulation.

## Operator journey

| Phase | What the operator sees | What the system must establish |
|---|---|---|
| **Observe** | Scene source and available evidence | Which inputs are simulated, recorded or live |
| **Plan** | Understood goal, expected outcome and pending checks | A supported symbolic interpretation; no invented map grounding |
| **Approve** | A clear review action | Approval of the current mission version |
| **Act** | The current bounded action and progress | The selected adapter's action result |
| **Verify** | Expected/observed comparison and MUSE decision | Fresh imagery, accepted local checks and model review |

Each bounded action returns to verification. The workspace must make a rejected or uncertain review visibly change what happens next.

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
  → verify stopping and observe the signal
      RED / UNKNOWN → remain stopped and observe again
      fresh GREEN + accepted checks → admit crossing
  → execute and review the qualified crossing actions
  → continue toward the destination
  → verify the destination outcome
```

The final map will determine which intersections have signals, how approaches are defined and where the stop/exit boundaries lie. No specific route, coordinate or turn count is fixed here.

## Intersection policy

| Situation at the approach | Required behavior |
|---|---|
| Green before arrival | Stop first; then evaluate the signal |
| Red after verified stopping | Wait without beginning the crossing |
| Card absent, obscured, ambiguous or stale | Treat entry as inhibited |
| Green becomes visible while waiting | Obtain fresh observations and accepted checks before entry |
| Checks accept the stopped state and fresh green | Continue automatically through the admitted crossing |
| Application restarts while waiting or crossing | Return to review; do not restore permission from old observations |

The simulator automatically admits one crossing after an accepted mandatory-stop review and fresh simulated GREEN, without another approval. The corresponding physical red-to-green continuation still requires a qualified robot adapter; no pendant or robot operation is supplied by this application.

The scenario concerns **stop-line admission**. Changing a card during an admitted crossing is not specified as an immediate interruption request. Any later in-flight stop requirement would need a separate controller-supported design and qualification.

## Pushing and turning

The car remains on the surface. It is not picked up or carried. Straight pushes and turns are distinct physical primitives that must be measured with the eventual vehicle, surface and tool.

A turn may require changing the contact point and applying an off-center push. Rotating the robot wrist alone does not establish that the car rotated correctly. After each bounded push or turn, vehicle evidence must be checked separately from the robot's endpoint result.

Tool clearance, observation poses, friction, slip, contact heights and usable turning space remain physical qualification work. The abstract simulator can test mission sequencing but cannot validate these properties.

## What completes an action?

The future supervisor needs three kinds of evidence:

1. **Action evidence:** the action adapter reports the result for the correct request/session.
2. **Local evidence:** applicable freshness, signal and outcome checks support the expected state.
3. **Model evidence:** MUSE reviews fresh imagery and supports the expected-versus-observed outcome.

A successful robot movement cannot substitute for evidence that the car moved as intended. A confident model answer cannot substitute for a required local check. If the scene is hidden or the evidence conflicts, the next step is waiting, reobservation or a visible fault.

## What completes the mission?

Mission completion requires the approved destination outcome to be verified from the corresponding final observations and checks. The final geometry will define the destination region and acceptable pose. Until then, software tests must use clearly named symbolic completion conditions.

The demonstration should leave an inspectable sequence of the goal, actions, observations, model reviews, waits and final decision. A completed simulation must remain labelled as simulation.

## Interface direction

The primary surface is an **English tablet workspace** in dark navy and electric cyan. Its key content is:

| View | Content |
|---|---|
| **Workspace** | Push-to-talk or typed goal, editable transcript, scene placeholder, current action, expected/observed comparison, MUSE decision and next check |
| **Plan** | Current symbolic interpretation, approval state and action sequence |
| **Replay** | Source-aware timeline with images, actual review responses and transition causes |

Spatial AR route alignment is deferred with map registration. The **glasses companion** remains a clearly labelled future concept. Hardware connection, microphone capture, transcription and wearable display behavior must only be shown as live capabilities when they are actually implemented and supported by evidence. Streaming transcription and spoken feedback are later extensions.

---

[← Architecture](ARCHITECTURE.md) · [Next: Meta intelligence →](META_INTELLIGENCE.md)
