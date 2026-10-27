<sub>[PushPilot](../README.md) / Shared boundaries / Contracts</sub>

# Versioned workspace boundaries

**Keep the UI, provider, and simulator aligned without granting model output execution authority.**

[Architecture](../docs/ARCHITECTURE.md) · [Backend](../backend/README.md) · [Voice input](../docs/VOICE_INPUT.md) · [Model interaction](../docs/META_INTELLIGENCE.md)

> **Implemented:** [`workspace.ts`](workspace.ts) describes frontend DTOs for `pushpilot.workspace.v1`. Pydantic models in [`backend/app.py`](../backend/app.py) validate API requests. These are not a formal standalone JSON Schema catalog. Voice, image bundles, physical receipts, and registered coordinates remain future contracts.

## Current API

| Endpoint | Input beyond the command base | Result |
| :--- | :--- | :--- |
| `GET /api/health` | None | Simulation health and disconnected-hardware status. |
| `GET /api/v1/state` | None | Current workspace snapshot, capabilities, and event history. |
| `POST /api/v1/goals` | `text`, `provider: demo\|meta`, optional `source` | Interpret typed text and prepare a supported symbolic plan or clarification. |
| `POST /api/v1/approve` | `plan_id`, `plan_revision` | Approve exactly the current plan. |
| `POST /api/v1/advance` | None | Admit the next eligible abstract action. Crossing uses its own gate. |
| `POST /api/v1/signal` | `color: RED\|GREEN\|UNKNOWN` | Inject an explicitly simulated signal observation. |
| `POST /api/v1/reviews` | `review_id`, `verdict: PASS\|FAIL\|REOBSERVE\|UNKNOWN` | Inject an explicitly demo-sourced verdict for the pending review. |
| `POST /api/v1/reobserve` | None | Bind a new simulated review without replaying movement. |
| `POST /api/v1/cancel` | None | Terminate the simulation; no hardware-stop guarantee. |
| `POST /api/v1/reset` | None | Clear non-active state while retaining evidence history. |

Every POST requires `request_id`, a UUID, and `expected_revision`, a nonnegative integer. Successful mutations return the snapshot. Invalid request fields/types are rejected by Pydantic; stale revisions or invalid transitions return HTTP 409. Provider failures return a sanitized HTTP 502 error and invalidate the old pending plan.

The same request ID and identical payload return the original receipt without running the command again. Reusing that ID for different content is rejected. An original receipt may have an older revision than a later poll; consumers must not overwrite newer state with it.

`source: voice` exists in the DTO vocabulary but is rejected by the current backend until transcription is implemented. Its presence in a type is not a supported capture capability.

## Snapshot and evidence

The snapshot binds a session and revision to state, the accepted goal, current plan/step, approval, stopped status, simulated signal, pending review, next check, capabilities, and ordered events.

Plan and review identifiers prevent approval or judgment from applying to a different revision. Events retain stable IDs, sequence numbers, timestamps, source labels, state, and explanatory text. SQLite also retains exact request digests and idempotent command receipts. Reset does not remove the event history.

The current `capabilities` response always reports `robot`, `camera`, `registered_ar`, `voice`, and `image_review` as false. `muse_configured` reports server configuration availability; it does not establish provider access or image-review support. Demo reviews cannot become Meta evidence by changing a UI label.

## Provider goal boundary

The Meta adapter's strict `pushpilot_goal_v1` response schema is inline in `backend/meta.py`. It requires `destination: BAKERY\|UNKNOWN`, an English `summary`, and `requires_clarification`, with no additional properties. The adapter validates the result before the supervisor can prepare the fixed symbolic plan.

The model supplies an interpretation, not plan approval, metric coordinates, road routes, or robot commands. A failed actual-provider request does not fall back to the demo parser.

## Rules for later contracts

1. **Version the boundary.** Change consumers, fixtures, and validation together.
2. **Bind each result.** Retain the request, action, observation, and session context.
3. **Preserve independent sources.** Robot state, image, car pose, signal, audio, and model result can have different origins.
4. **Represent uncertainty.** Unknown, unavailable, invalid, and incomplete remain distinct from success.
5. **Separate clocks.** Capture/record timestamps support provenance; monotonic durations support local timeouts.
6. **Expose causes.** Keep the evidence and gate result that caused each transition.

## Planned voice and image records

Define separate records for capture, transcription, edited transcript revision, confirmed goal, and mission approval. Bind finite batch transcription to its capture/session/request and initiating input revision. Cancellation or supersession invalidates late results. Preserve original provider text and actual provenance without inventing ASR confidence. Original Korean or English text is user data.

Image-review records must bind immutable media hashes/crop lineage, capture timing, expected action outcome, visibility/uncertainty, local findings, exact provider inputs/results, and prompt/schema/model versions. The current event timeline does not yet implement that full receipt.

## Deliberately absent

No active map coordinates, road graphs, installed signal ROIs, stop/exit lines, or AR transforms are defined. Label temporary user-provided scenes under [Test inputs](../docs/TEST_INPUTS.md).

The simulator creates no native hardware receipts. Physical completion requires a separately implemented and qualified measured adapter. Credentials and model-generated executable commands do not belong in these contracts.

New goal submission requires non-executing preparation. Active missions, including signal waits and reviews, reject goal replacement. Completion/termination and explicit reconciliation precede replacement.

Run `python tools/dev.py check` and `python tools/dev.py test` with runtime dependencies installed. The first command checks syntax; API and mission tests exercise the actual Pydantic and supervisor rejection behavior.

---

[Prompt versioning](../prompts/README.md) · [Tests](../tests/README.md) · [Roadmap](../docs/ROADMAP.md)
