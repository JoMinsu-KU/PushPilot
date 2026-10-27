<div align="center">

# Meta intelligence

**Interpret intent. Compare the evidence. Make the consequence visible.**

[Documentation](README.md) · [Action reviews](ACTION_REVIEWS.md) · [Architecture](ARCHITECTURE.md) · [Mission](MISSION.md) · [Roadmap](ROADMAP.md)

</div>

---

PushPilot uses **Muse Spark 1.3** for typed-goal interpretation, independent recorded-scene inspection and action-bound recorded-image review. All requests originate in the backend, use strict response schemas and keep credentials out of the browser. The model returns structured meaning and uncertainty; the mission supervisor retains transition authority.

## Actual application cases

| Case | Model result | Application consequence |
|---|---|---|
| `Push the car from Pizza to the Bookstore.` | Supported destination BOOKSTORE and an English interpretation | Supervisor derived the temporary route and entered PLAN_READY; approval still pending. |
| Recorded 1920 × 1080 Little Town photograph | Four printed shops, no separate physical car, paper signal UNKNOWN | Stored an independent scene result, without advancing a mission. |

These actual calls are documented in [Meta API evidence](META_API_CHECK.md). They establish the stated integration on the stated input. They do not establish a general accuracy rate, physical task completion or live-camera behavior. New action-review checks and their precise sources belong in [verification](VERIFICATION.md).

An additional actual-provider run compared three original **synthetic schematic** before/after pairs for the same expected approach: depicted movement returned PASS → READY, no progress returned FAIL → FAULT, and occlusion returned REOBSERVE → REOBSERVE. There was one call per condition. This demonstrates the model-to-supervisor consequence on designed inputs, not real-car image accuracy. The [API record](META_API_CHECK.md) retains per-call timing and reported tokens.

## Three distinct model boundaries

| Boundary | Input | Output | Authority |
|---|---|---|---|
| **Goal interpretation** | Operator text and available symbolic task context | BAKERY, BOOKSTORE, SCHOOL or UNKNOWN, summary and clarification flag | May prepare a reviewable plan; never approves it. |
| **Scene inspection** | One immutable recorded frame and an inspection expectation | USABLE, REOBSERVE or UNKNOWN; visible places, car visibility, paper signal and limitations | Stores scene evidence; never advances a mission or supplies its GREEN. |
| **Action review** | Current bounded action, expected outcome and an operator-selected before/after frame pair | PASS, FAIL, REOBSERVE or UNKNOWN with an expected/observed explanation | May satisfy or reject the pending simulated review through the supervisor; never bypasses local gates or proves physical freshness. |

A scene being USABLE does not mean an action passed. A recorded action PASS is not an actual robot receipt. Each response retains its own source and binding.

## Action-bound review

The integrated path connects actual image judgment to the simulator's next state. Its lifecycle is:

1. A bounded simulated action completes and creates a pending review binding.
2. The operator selects immutable before/after recorded frames. The UI labels their source and selection explicitly.
3. The backend binds the request to the current mission, action, review, map and frame identities.
4. Muse Spark compares the expected outcome with the supplied visual evidence under a strict contract.
5. The backend validates the response and rechecks that the request still belongs to the pending review.
6. The supervisor applies PASS, FAIL, REOBSERVE or UNKNOWN while retaining its independent gates.
7. The workspace shows expected versus observed, uncertainty, review source and the resulting next check.

PASS may accept the review. FAIL faults the simulation. REOBSERVE or UNKNOWN requires another observation binding without resending the action. Even an accepted STOP review cannot enter an intersection on RED, UNKNOWN or stale simulated GREEN. See [Action reviews](ACTION_REVIEWS.md) for the executable API and operator workflow.

**Recorded pairs do not establish fresh post-action physical evidence.** Operator-provided capture times and the order of uploads are provenance, not independent proof that a frame was captured after a real command. A live capture/receipt path and physical qualification remain separate work.

## Independent recorded-scene inspection

Upload a bounded JPEG/PNG and explicitly request inspection of its scene revision and frame ID. The prompt distinguishes a separate three-dimensional wheel-less car from a printed start/footprint, and an operator-placed signal card from decorative printed traffic lights.

The result binds frame hash, map identity and scene revision. A superseded frame or modified file cannot acquire an accepted result. USABLE means the image supports the requested scene inspection. It is neither action completion nor a fresh physical signal. The endpoint does not advance the supervisor.

## Why judgment and gates are separate

Two outcomes of the same intended action should lead to different decisions when one supports success and the other does not. The model supplies that semantic comparison. The supervisor enforces the conditions the image answer cannot supply:

- Explicit approval of the current plan and matching map identity.
- A valid action result and the exact pending review binding.
- Independent stop and junction-scoped signal gates.
- A supported adapter and non-executing recovery after restart.
- Rejection of stale/superseded requests and changed-payload request-ID reuse.

Model responses cannot contain executable robot scripts, authoritative coordinates or unrestricted recovery commands. Cloud response timing cannot promise immediate stopping. The future local paper-signal inhibition path must operate independently of semantic-review latency.

A provider timeout, malformed output or failure is exposed rather than replaced with a scripted acceptance. The separate Demo controls deliberately inject operator-sourced verdicts; their labels and evidence remain different from actual Meta responses.

## What the operator sees

| UI element | Question answered |
|---|---|
| **Goal understood** | What does the system think I asked? |
| **Scene evidence** | Which image and source support the interpretation? |
| **Expected / Observed** | Does the supplied evidence support this action's outcome? |
| **MUSE decision** | What did the model conclude, including uncertainty? |
| **Next check** | Why are we continuing, waiting or observing again? |

The event timeline retains the decision cause. Private frame storage preserves original bytes and hashes. Review records retain the implemented contract's inputs and validated result; consult [Action reviews](ACTION_REVIEWS.md) for the actual receipt fields. Complete goal/scene provider envelopes, crop lineage and a unified export/retention policy remain later work. Missing usage or cost is unknown, never zero.

## Evaluation still needed

Software rejection tests and injected provider results verify the pipeline's behavior. Actual visual correctness needs independent labels and repeatable recorded/physical input:

- Freeze held-out images before prompt tuning and keep their origin explicit.
- Pair the same expected action with success, no progress, wrong movement and occlusion.
- Separate synthetic fixtures, recorded real scenes and physical runs in every result.
- Test missing paper cards, contradictory evidence, failures and uncertain views.
- Compare model review with a stated baseline without weakening physical admission gates.
- Report sample counts, false continuation, uncertainty, latency and reported usage with failures.

A synthetic example can demonstrate a provider/state boundary. It cannot demonstrate real-car performance. A single successful response cannot establish average latency or accuracy.

## Planned voice path and privacy

Planned [voice input](VOICE_INPUT.md) uses Meta Muse Voice Transcribe before the shared goal-understanding path. The operator reviews/edits the transcript and separately approves the resulting mission. Neither audio nor transcription grants motion authority. Capture, normalization and the Voice provider adapter remain unimplemented.

Keep input media and credentials in ignored private runtime storage. Do not place keys in prompts, evidence, logs or release bundles. Public demonstrations need media with known origin and rights, recorded in [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).

---

[← Mission](MISSION.md) · [Action review workflow →](ACTION_REVIEWS.md)
