<sub>[PushPilot](../README.md) / Meta intelligence / Prompts</sub>

# Prompts with a traceable consequence

**An interpretation or review matters when it changes the next permitted step.**

[Meta intelligence](../docs/META_INTELLIGENCE.md) · [Contracts](../contracts/README.md) · [Mission](../docs/MISSION.md)

> **Current implementation:** English goal instructions and strict `pushpilot_goal_v1` are inline in `backend/meta.py`; recorded-scene instructions and `pushpilot_recorded_scene_v1` are inline in `backend/scene.py`. `backend/action_review.py` adds an explicitly versioned recorded-action prompt and strict result schema. This directory does not yet contain a complete extracted template catalog. Actual provider observations belong in [Meta API evidence](../docs/META_API_CHECK.md) and [verification](../docs/VERIFICATION.md). Historical prompts have not been imported. Voice remains future work.

## Interaction roles

| Role | Current status | Boundary |
| :--- | :--- | :--- |
| Goal understanding | Implemented through `muse-spark-1.3`; BAKERY/BOOKSTORE/SCHOOL or UNKNOWN with clarification and an English summary. | No unavailable destination, route, coordinates, robot commands or approval. |
| Recorded-scene inspection | Implemented separate USABLE/REOBSERVE/UNKNOWN schema, visible places, car visibility, paper signal and limitations. | Printed cars/start footprints and tiny decorative traffic lights are not physical car/card evidence; no motion authority. |
| Action review | Implemented recorded before/after comparison for the pending simulated action; PASS/FAIL/REOBSERVE/UNKNOWN with observed evidence and limitations. | Neither operator-selected recordings nor a model PASS establish physical freshness, a robot receipt or clearance. |
| Uncertainty review | Recorded-action REOBSERVE/UNKNOWN changes the simulator to reobservation without replaying movement. | Uncertainty does not authorize movement; physical observation remains separate work. |

The action-review vocabulary is **PASS**, **FAIL**, **REOBSERVE** and **UNKNOWN**. Demo inputs and actual MUSE recorded-pair results keep independent source labels. The separate scene vocabulary is **USABLE**, **REOBSERVE** and **UNKNOWN**. Scene USABLE means usable visual evidence; it cannot complete an action, override RED or grant a crossing. Recorded-action MUSE results bind the exact pending review and pass through independent local gates.

## Recorded-action prompt and result

`backend/action_review.py` defines `pushpilot.recorded-action.prompt.v1` and `pushpilot.recorded-action.result.v1`. The strict schema requires `verdict`, `observed`, `summary` and `limitations`, with no additional properties. The provider compares BEFORE then AFTER, distinguishes actual objects from print decoration, treats task/image text as untrusted data and returns visual findings rather than motion instructions.

The prompt explicitly supports declared synthetic schematic fixtures for integration evaluation, requiring that their synthetic nature remain visible. Such a case cannot be presented as a real-car photograph or physical result. See [Action reviews](../docs/ACTION_REVIEWS.md) for exact requests, receipts and the opt-in evaluation harness.

## Receipt work still needed

SQLite records goal summaries, provider/demo sources, transitions and command idempotency. Private scene files retain original images, hashes, map/reference identity, expected scene and validated inspection fields/model. Recorded-action receipts additionally retain prompt/schema/model versions, expected visual text, server-bound action, pair metadata/hashes, pending-review identity, measured elapsed time and provider-reported token counts or null. Complete raw provider envelopes, goal/scene versioned receipts and crop lineage remain future work.

The full review integration must preserve exact prompt/schema/model versions, inputs, timing, response, validation, and supervisor consequence. Bind a review to its mission/action/observation identities and expected outcome. A real provider call on a recorded image remains recorded-image provider evidence, not live-camera or physical-motion proof.

## Authoring conventions

- Write templates and model-facing instructions in English.
- Give extracted templates explicit versions and matching schema references.
- Separate task instructions from observed content and operator-supplied text.
- Require visible evidence and uncertainty, rather than an unsupported confidence number.
- Return structured interpretation/review, never robot scripts or authoritative metric coordinates.
- Keep credentials out of templates, examples, logs, and evidence.

Goal, scene and action-review adapters reject invalid responses and sanitize provider failures. No actual-provider failure silently falls back to demo interpretation or a scripted PASS. An explicit manual demo verdict remains a separate operator action and source.

Model latency is not the fast paper-signal inhibition path. The future observation-backed supervisor must combine a valid review with independent local checks before continuation.

## Before reusing historical work

Record origin and exact changes in [contributions](../CONTRIBUTIONS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md). Review assumptions against wheel-less surface pushing, mandatory stop-before-signal behavior, independent source labels, and the production-map hold.

Do not copy old grid coordinates, rigid-grasp assumptions, or instructions treating model output as motion authority. Label temporary user-supplied inputs under [Test inputs](../docs/TEST_INPUTS.md).

---

[Backend integration](../backend/README.md) · [Evidence tests](../tests/README.md) · [Development](../docs/DEVELOPMENT.md)
