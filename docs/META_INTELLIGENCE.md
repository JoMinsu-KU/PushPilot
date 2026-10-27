<div align="center">

# Meta intelligence

**The model's judgment must change the mission.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Mission](MISSION.md) · [Roadmap](ROADMAP.md)

</div>

---

PushPilot is designed to make MUSE's image-grounded understanding visible in the operator workflow: interpret the goal, compare expected and observed outcomes, surface uncertainty and determine what needs to be checked next.

**Goal interpretation and independent recorded-scene inspection are implemented.** Both use `muse-spark-1.3` at the fixed Meta chat-completions endpoint with strict response schemas and server-only credentials. Goal interpretation supports BAKERY, BOOKSTORE, or SCHOOL; unsupported, pickup, or ambiguous requests require clarification. The supervisor derives a temporary drawing route and abstract steps after validation. The model supplies neither coordinates, routes, robot commands, nor approval.

A real backend goal request on October 27, 2026 at 14:07 KST returned HTTP 200 in 3,880 ms and produced PLAN_READY. This verifies the stated text-goal path, separately from the earlier standalone [connection check](META_API_CHECK.md). It does not verify image judgment, voice, a live camera, or physical execution. Explicit plan approval is still required.

Planned [voice input](VOICE_INPUT.md) uses **Muse Voice Transcribe** for speech-to-text before the shared goal-understanding path. Transcription returns editable input; Muse Spark interprets the submitted goal and reviews images. Neither an audio recording nor a transcript is mission approval. The Spark goal adapter exists inside the [single backend](SERVICE_COMPOSITION.md); the Voice adapter remains planned.

## Where the model adds value

| Interaction | Intended input | Useful output | Mission consequence |
|---|---|---|---|
| **Understand the goal** | Operator request and available symbolic context | Supported destination interpretation and unresolved ambiguity | Present a reviewable goal or ask for clarification |
| **Review an action** | Intended action, before/after images and source-labelled observations | Grounded expected/observed comparison | Continue only when all required checks accept |
| **Handle uncertainty** | Obscured, contradictory or insufficient evidence | What cannot be established and what view/check is needed | Remain stopped and reobserve or enter review |
| **Review an approach** | Verified stopped state, relevant scene and signal evidence | Whether the scene supports the proposed entry conditions | Supplement deterministic traffic admission checks |

The model is not a decorative narrator over a predetermined success sequence. Two observations of the same intended action should be able to produce different next states when one supports success and the other does not.

## Recorded-scene inspection now

Upload a bounded JPEG/PNG, then explicitly request inspection with its scene revision, frame ID, and an expectation. The backend sends that immutable frame to MUSE and validates a separate scene result: **USABLE**, **REOBSERVE**, or **UNKNOWN**, a summary, visible places, `car_visible`, paper-signal color, and limitations. The prompt distinguishes a separate three-dimensional wheel-less car from a printed start/footprint, and an operator-placed signal card from tiny printed traffic-light decorations.

The stored result binds frame hash, map identity, and scene revision. A superseded frame or modified file cannot acquire a result. USABLE means the image supports scene inspection; it does not mean task completion, a fresh physical signal, accepted action review, or permission to move. This endpoint never advances the mission. See [verification](VERIFICATION.md) for actual provider observations rather than inferring success from adapter availability.

## Planned per-action image-review lifecycle

The mission still accepts operator-injected demo verdicts PASS, FAIL, REOBSERVE, and UNKNOWN. No image is sent to MUSE by that action-review path. Integrating actual action-bound imagery remains separate work:

1. The supervisor receives the result of a bounded action and establishes the observation window.
2. Observation adapters provide fresh source-labelled imagery and available local measurements.
3. The provider adapter sends the versioned prompt, expected outcome and immutable image references/content.
4. The response is parsed and validated against the pinned review contract.
5. The supervisor compares the review with required local checks.
6. The workspace shows the decision, its evidence and the next pending check.

Freshness is evaluated against the relevant action and observation context, not the time at which a cloud response eventually arrives. A late review must not authorize movement from an outdated scene or green signal.

## Review contract design

The future executable schema should distinguish these concerns rather than collapse them into a single confidence score:

| Concern | Required meaning |
|---|---|
| **Binding** | Which mission, action and observation bundle was reviewed |
| **Expected / observed** | The requested outcome and the outcome the images actually support |
| **Evidence** | Visible facts and the image/crop references supporting them |
| **Uncertainty** | Missing visibility, ambiguity or conflicting information |
| **Judgment** | Accepted, rejected, needs reobservation or unknown under the defined contract |
| **Next check** | A constrained information request, not an executable robot command |

These image-review requirements are not an existing provider wire schema. [`contracts/workspace.ts`](../contracts/workspace.ts) currently describes workspace state and demo-review DTOs. The goal provider schema/instruction are inline in `backend/meta.py`; recorded-scene schema/instruction are inline in `backend/scene.py`. A versioned prompt catalog and full action-image-review contract remain future work. Pair later versions with explicit templates and meaningful validation tests.

MUSE must not return authoritative robot coordinates, scripts or unrestricted recovery actions. A later recovery proposal interface would need its own constrained contract, validation and qualification.

## Deterministic authority remains explicit

The supervisor retains admission authority over source/freshness checks, stopping evidence, signal policy and adapter capability. Red, unknown or stale signal observations inhibit intersection entry even if a model review otherwise sounds positive.

Conversely, a rejected or uncertain model review must block continuation when review is required. The system cannot ignore an inconvenient real response and display a scripted acceptance instead.

Model response timing is unsuitable as a promise of immediate physical stopping. The signal observation path and controller behavior must be designed independently of semantic review latency.

## What the operator sees

The main workspace should answer five questions without requiring raw JSON:

| UI element | Question answered |
|---|---|
| **Goal understood** | What does the system think I asked? |
| **Scene evidence** | What image and source support this interpretation? |
| **Expected / Observed** | Did the outcome match the intended action? |
| **MUSE decision** | What did the actual model conclude, including uncertainty? |
| **Next check** | Why are we proceeding, waiting or observing again? |

Mission events retain interpreted summaries, sources, state changes, and command idempotency. Separate scene files retain original images, SHA-256, source, timestamps, map bindings, locked registration, and validated inspection fields/model. Complete provider envelopes, usage, timing, prompt/schema version receipts, and crop lineage remain future work. Unreported cost stays unknown.

## Failure handling and honest evaluation

The implemented goal adapter uses bounded request timeouts, disables credential-bearing redirects, validates the returned structure, and sanitizes provider failures. An actual-provider failure creates no demo fallback plan and invalidates an older pending plan. Offline tests inject malformed responses, HTTP failures, and timeouts; they do not use the operator's real key. The synchronous adapter serializes the current simulator command path. Future physical signal inhibition must remain independent of that latency.

Evaluation should measure whether image grounding changes decisions correctly, using independent labels rather than the model's own answer as ground truth.

- Freeze a held-out set before prompt tuning; keep tuning images separate.
- Pair the same intended action with different actual outcomes, including no movement, wrong movement and obscured evidence.
- Exercise red/green, absent card, stale frame, timeout, malformed response and local/model disagreement cases.
- Compare image-grounded review with a text-only or deterministic baseline in recorded/shadow evaluation.
- Report sample counts, failures and uncertainty outcomes alongside successes.

Physical gates must remain active during any physical evaluation. A baseline comparison does not justify weakening them.

## Evidence labels and privacy

Keep the input and execution sources separate from the model source. A **real MUSE call on a recorded image** demonstrates provider integration; it does not demonstrate a live robot mission. Mock responses must remain visibly mocked.

Store only reviewed input media and necessary request/result evidence. Keep credentials in ignored local or host-only secret configuration, never in prompts, source files or release bundles. A public demonstration should use media with known origin and appropriate rights, recorded in [third-party notices](../THIRD_PARTY_NOTICES.md) where applicable.

---

[← Mission](MISSION.md) · [Next: roadmap →](ROADMAP.md)
