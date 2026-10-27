<sub>[PushPilot](../README.md) / Shared boundaries / Contracts</sub>

# Contracts before adapters

**Keep the interface stable while the UI, provider, simulator, and future robot evolve.**

[Architecture](../docs/ARCHITECTURE.md) · [Backend](../backend/README.md) · [Voice input](../docs/VOICE_INPUT.md) · [Model interaction](../docs/META_INTELLIGENCE.md)

> **Status: planned.** This directory does not yet contain executable wire schemas. The inventory below defines intended ownership, not an implemented API.

## Contract inventory

| Family | Information it should bind | Principal consumers |
| :--- | :--- | :--- |
| Voice capture and transcription | Capture/session/request identifiers, input revision, source, bounded audio metadata, status, original transcript, final-result flag and provider/model provenance. | UI, backend voice adapter, evidence |
| Confirmed goal and intent | Voice or typed input source, selected text revision, operator confirmation, grounded symbolic destination and unresolved ambiguity. | UI, supervisor, MUSE adapter |
| Mission and action | Identity, state, approved abstract plan, one requested action, completion status. | Supervisor, simulator, UI |
| Observation bundle | Capture time, independent source labels, immutable image references, visibility and local findings. | Observer, MUSE adapter, evidence |
| Intersection admission | Verified stop, signal identity and freshness, local result, accepted review, admission scope. | Supervisor, signal observer |
| MUSE request and review | Prompt/model/schema versions, exact inputs, expected and observed outcome, uncertainty, decision. | Provider, supervisor, replay |
| Evidence and replay | Immutable record identity, causal links, request/result references, transition reason. | Evidence store, UI |
| Capability status | What is configured, connected, simulated, unsupported, or unavailable. | Adapters, UI |

## Rules shared by every boundary

1. **Version the contract.** Introduce schema changes with consumers, fixtures, and validation together.
2. **Bind the result.** A result belongs to a specific request, action, observation, and session context.
3. **Preserve independent sources.** Robot state, image, car pose, signal, and model result may each have different origins.
4. **Represent uncertainty.** Unknown, unavailable, invalid, and incomplete information remain distinct from success.
5. **Separate clocks.** Capture/record timestamps support provenance; monotonic durations support local timeouts.
6. **Expose causes.** State transitions reference the evidence and gate outcome that caused them.

## Voice-to-goal boundary

Define separate records for audio capture, provider transcription, an operator-edited transcript revision, confirmed goal submission and mission approval. A final transcription result means the transcription request is complete; it does not confirm the user's intent or approve a mission.

The first provider request is batch `POST` file transcription. Bind the transcript to its capture/session/request and the input revision that initiated it. Mark cancellation and supersession so late results cannot replace newer voice or typed input. Preserve the original provider text, actual provider/model identifiers, response metadata and the confirmed revision's causal link.

Record transcript source independently from the eventual goal interpretation. The provider does not supply an ASR confidence value in the currently reviewed response shape; absence remains unknown rather than an invented numerical score. English or Korean transcript content is user input data, while field names and UI copy are English.

Streaming events, continuous listening and speech synthesis are outside the initial wire-contract scope. See [voice input](../docs/VOICE_INPUT.md) and [service composition](../docs/SERVICE_COMPOSITION.md) for the planned batch path.

## Deliberately absent

The map is on hold. Do not establish active coordinates, road graphs, installed signal ROIs, stop/exit lines, or AR transforms here. Symbolic locations and abstract actions are sufficient for the first application.

The simulator must never create fake native hardware receipts. A future physical adapter needs its own measured implementation and qualification. Raw robot scripts, credentials, and executable model-generated commands do not belong in a review contract.

Goal-entry eligibility is a supervisor-owned contract: capture, typed submission and goal revision require non-executing preparation. Active missions, including signal waits and reviews, reject new goal changes. Capture cancellation and late results cannot modify active mission authority.

## Introducing a schema

Add representative valid, invalid, stale, and mismatched examples with each schema. Validate at the intake boundary before a value can alter mission state. Document compatibility and test the consequences of rejection, not only successful parsing.

From the repository root:

```sh
python tools/dev.py check
python tools/dev.py test
```

The bootstrap checker parses JSON syntax only. It is not a schema validator and does not validate any of the planned contracts above.

---

[Prompt versioning](../prompts/README.md) · [Test boundaries](../tests/README.md) · [Roadmap](../docs/ROADMAP.md)
