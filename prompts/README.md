<sub>[PushPilot](../README.md) / Meta intelligence / Prompts</sub>

# Prompts with a traceable consequence

**A review matters when its evidence changes the mission's next step.**

[Meta intelligence](../docs/META_INTELLIGENCE.md) · [Contracts](../contracts/README.md) · [Mission](../docs/MISSION.md)

> **Status: planned.** No executable prompt template, provider adapter, or live model call is included here yet. Historical prompts have not been imported.

## Planned interaction roles

| Role | Expected reasoning | Boundary |
| :--- | :--- | :--- |
| Goal understanding | Ground the request in the available symbolic task and identify ambiguity. | Do not invent unavailable destinations or capabilities. |
| Scene understanding | Describe visible task evidence and occlusion. | Do not infer an unseen car position or signal color as fact. |
| Action review | Compare expected and observed outcomes using action-bound images. | A commanded motion is not proof of successful car movement. |
| Uncertainty review | Explain insufficient or contradictory evidence and request another observation. | Uncertainty does not authorize movement. |

The expected action-review outcomes are **PASS**, **FAIL**, **REOBSERVE**, and **UNKNOWN**. These names describe the intended interface; the executable schema will arrive with the provider adapter. The supervisor combines a validated review with deterministic local gates before continuing.

## Every review needs a receipt

Preserve the exact prompt version and response-schema version, selected model, request timing, actual response, validation result, and supervisor consequence. Bind the review to immutable image hashes and lineage, the mission/action identifiers, and the expected outcome.

A provider call using a recorded image is actual provider evidence and recorded-image evidence. It is not a live-camera or physical-motion test. Mock responses remain explicitly mocked in records and in the operator UI.

## Authoring conventions

- Write templates and model-facing instructions in English.
- Give each template an explicit version and matching response-schema reference.
- Separate task instructions from observed image content and operator-supplied text.
- Require visible evidence and an uncertainty explanation rather than unsupported confidence alone.
- Return structured interpretation and review, never robot scripts or authoritative metric coordinates.
- Keep credentials out of templates, examples, request logs, and committed evidence.

After a bounded action, the future adapter supplies newly captured imagery, task context, and the expected result. Invalid, stale, contradictory, or uncertain responses lead to waiting or reobservation. Model latency is not the fast signal-inhibition path.

## Before reusing a historical prompt

Record its origin and exact changes in [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md). Review assumptions against the current **wheel-less pushing** mission, mandatory stop-before-signal behavior, independent source labels, and active map hold.

Do not copy old grid coordinates, rigid-grasp assumptions, or a prompt that treats a model answer as direct motion authority.

---

[Backend integration](../backend/README.md) · [Evidence tests](../tests/README.md) · [Development](../docs/DEVELOPMENT.md)
