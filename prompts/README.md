<sub>[PushPilot](../README.md) / Meta intelligence / Prompts</sub>

# Prompts with a traceable consequence

**An interpretation or review matters when it changes the next permitted step.**

[Meta intelligence](../docs/META_INTELLIGENCE.md) · [Contracts](../contracts/README.md) · [Mission](../docs/MISSION.md)

> **Current implementation:** the English goal instruction and strict `pushpilot_goal_v1` response schema are inline in [`backend/meta.py`](../backend/meta.py). The application has made a real backend goal request. This directory does not yet contain a versioned template catalog. Historical prompts have not been imported; image-review and voice prompts remain future work.

## Interaction roles

| Role | Current status | Boundary |
| :--- | :--- | :--- |
| Goal understanding | Implemented through `muse-spark-1.3`; BAKERY or UNKNOWN with clarification and an English summary. | No unavailable destination, route, coordinates, robot commands or approval. |
| Scene understanding | Planned. | Do not infer an unseen vehicle position or signal color as fact. |
| Action review | Planned; current simulator uses explicit operator-injected demo verdicts. | A commanded tool motion is not proof of vehicle movement. |
| Uncertainty review | Planned image-grounded explanation and constrained next check. | Uncertainty does not authorize movement. |

The current demo-review vocabulary is **PASS**, **FAIL**, **REOBSERVE**, and **UNKNOWN**. These are simulator API values, not proof that a MUSE image request occurred. Future image review requires its own executable schema and media binding.

## Receipt work still needed

The SQLite event history records goal summaries, provider/demo source labels, transitions, and command idempotency. It does not yet preserve the complete provider response, usage, latency, immutable image content/hash lineage, or an explicit prompt-version receipt.

The full review integration must preserve exact prompt/schema/model versions, inputs, timing, response, validation, and supervisor consequence. Bind a review to its mission/action/observation identities and expected outcome. A real provider call on a recorded image remains recorded-image provider evidence, not live-camera or physical-motion proof.

## Authoring conventions

- Write templates and model-facing instructions in English.
- Give extracted templates explicit versions and matching schema references.
- Separate task instructions from observed content and operator-supplied text.
- Require visible evidence and uncertainty, rather than an unsupported confidence number.
- Return structured interpretation/review, never robot scripts or authoritative metric coordinates.
- Keep credentials out of templates, examples, logs, and evidence.

The existing goal adapter rejects invalid responses and sanitizes provider failures. It does not fall back to demo interpretation after an actual-provider failure. Later image-review integration must likewise preserve rejection and uncertainty rather than replacing them with scripted acceptance.

Model latency is not the fast paper-signal inhibition path. The future observation-backed supervisor must combine a valid review with independent local checks before continuation.

## Before reusing historical work

Record origin and exact changes in [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md). Review assumptions against wheel-less surface pushing, mandatory stop-before-signal behavior, independent source labels, and the production-map hold.

Do not copy old grid coordinates, rigid-grasp assumptions, or instructions treating model output as motion authority. Label temporary user-supplied inputs under [Test inputs](../docs/TEST_INPUTS.md).

---

[Backend integration](../backend/README.md) · [Evidence tests](../tests/README.md) · [Development](../docs/DEVELOPMENT.md)
