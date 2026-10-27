<sub>[PushPilot](../README.md) / Shared boundaries / Contracts</sub>

# Versioned workspace boundaries

**Keep the UI, provider, and simulator aligned without granting model output execution authority.**

[Architecture](../docs/ARCHITECTURE.md) · [Backend](../backend/README.md) · [Voice input](../docs/VOICE_INPUT.md) · [Model interaction](../docs/META_INTELLIGENCE.md)

> **Implemented:** [`workspace.ts`](workspace.ts) describes `pushpilot.workspace.v1`; [`scene.ts`](scene.ts) describes temporary map/routes, optional `pushpilot.route-display.v1` geometry and `pushpilot.scene.v1`; [`live-camera.ts`](live-camera.ts) describes the independent ephemeral preview; [`action-review.ts`](action-review.ts) describes recorded-action requests and evidence. Pydantic models in `backend/app.py` and `backend/scene_api.py` validate requests. These source interfaces are not a formal standalone JSON Schema catalog. Voice, trusted physical observation bundles and hardware receipts remain future contracts.

## Current API

| Endpoint | Input beyond the command base | Result |
| :--- | :--- | :--- |
| `GET /api/health` | None | Simulation health and disconnected-hardware status. |
| `GET /api/v1/state` | None | Current workspace snapshot, capabilities, and event history. |
| `POST /api/v1/goals` | `text`, `provider: demo\|meta`, optional `source` | Interpret typed text and prepare a supported symbolic plan or clarification. |
| `POST /api/v1/approve` | `plan_id`, `plan_revision` | Approve exactly the current plan. |
| `POST /api/v1/advance` | None | Admit the next eligible abstract action. Crossing uses its own gate. |
| `POST /api/v1/signal` | `color: RED\|GREEN\|UNKNOWN`, optional `junction_id` | Inject a simulated observation bound to the applicable junction. |
| `POST /api/v1/reviews` | `review_id`, `verdict: PASS\|FAIL\|REOBSERVE\|UNKNOWN` | Inject an explicitly demo-sourced verdict for the pending review. |
| `POST /api/v1/action-reviews` | `review_id`, `expected_scene_revision`, `before_frame_id`, `after_frame_id`, `expected_visual` | Bind an actual recorded-image MUSE result to the pending simulated action; return its supervisor consequence. |
| `POST /api/v1/reobserve` | None | Bind a new simulated review without replaying movement. |
| `POST /api/v1/cancel` | None | Terminate the simulation; no hardware-stop guarantee. |
| `POST /api/v1/reset` | None | Clear non-active state while retaining evidence history. |

Every mission POST in this table requires `request_id`, a UUID, and `expected_revision`, a nonnegative integer. Successful mutations return the snapshot. Invalid request fields/types are rejected by Pydantic; stale revisions or invalid transitions return HTTP 409. Provider failures return a sanitized HTTP 502 error and invalidate the old pending plan.

The same request ID and identical payload return the original receipt without running the command again. Reusing that ID for different content is rejected. An original receipt may have an older revision than a later poll; consumers must not overwrite newer state with it.

`source: voice` exists in the DTO vocabulary but is rejected by the current backend until transcription is implemented. Its presence in a type is not a supported capture capability.

## Independent map and scene API

| Endpoint | Input | Result |
| :--- | :--- | :--- |
| `GET /api/v1/map` | None | Sanitized temporary graph/drawing facts and geometry hash. |
| `GET /api/v1/scene` | None | Current recorded frame, detection, locked-view status, inspection and scene revision. |
| `POST /api/v1/scene/frames` | Multipart `file`; optional timezone-bearing `captured_at`. | New private JPEG/PNG frame, up to 8 MiB and 12 MP. |
| `GET /api/v1/scene/frames/{id}/image` | Immutable frame ID. | Private runtime image. |
| `POST /api/v1/scene/registration` | `expected_revision`, `frame_id`. | Explicitly lock a four-marker board-to-image candidate. |
| `POST /api/v1/scene/reviews` | `expected_revision`, `frame_id`, `expected`. | Explicit Meta scene inspection, not mission action review. |

Scene mutations use the **scene revision**, not the mission revision or command-idempotency contract. Frame IDs are 32 lowercase hexadecimal characters. A late/superseded inspection or stale registration is rejected. Registration status is unregistered/partial/candidate/locked/locked_partial/view_changed; a withheld homography cannot be interpreted as a valid projection. Scene inspection returns USABLE/REOBSERVE/UNKNOWN, visible places, car visibility, separate paper-signal evidence, limitations, and `motion_authority: false`. No scene endpoint advances the supervisor.

## Snapshot and evidence

The snapshot binds a session and revision to state, goal, current plan/step, map/version/geometry-hash route, approval, stopped status, junction-scoped simulated signal, demo action review, capabilities, next check, and ordered events. Plans contain temporary drawing points/distances and node IDs, never robot targets.

Optional `route.visualization` contains drawing-only push/crossing subdivisions and illustrative stop-line geometry. `PlanStep.route_segment_id` binds PUSH/CROSS steps to those subdivisions; it is not a motion command. Older plans without consistent bindings display their complete planned route without inferred progress. Signal snapshots include `freshness_limit_ms` from the configured supervisor TTL for informational display. Colors never admit an action. See [route display](../docs/ROUTE_DISPLAY.md).

Plan and review identifiers prevent approval or judgment from applying to a different revision. Events retain stable IDs, sequence numbers, timestamps, source labels, state, and explanatory text. SQLite also retains exact request digests and idempotent command receipts. Reset does not remove the event history.

Mission capabilities keep `robot`, `camera`, `registered_ar` and `voice` false. `image_review` and `recorded_action_review` indicate that the operator-selected recorded-pair path is implemented; they do not indicate live capture, physical freshness or provider success. `muse_configured` indicates configuration availability, not successful inference. Scene capabilities keep live_camera/robot false. Demo verdicts cannot become Meta evidence by changing a UI label.

## Recorded-action evidence

The [action-review DTO](action-review.ts) binds the before/after image IDs and SHA-256 values, map identity, session/plan/action/review, input workspace/scene revisions, expected visual text and server-bound action. It records a validated PASS/FAIL/REOBSERVE/UNKNOWN result, explanation, limitations, prompt/schema/model versions, elapsed time and provider-reported token counts or null.

Its source is `meta`, input kind is `operator_selected_recorded_pair`, and scope is `simulated_action_review` with `simulation_only: true` and `motion_authority: false`. The operator-provided expected text does not replace the server's action binding. The after frame must be current, both frames must belong to the map, and stale/superseded results cannot satisfy another review. Exact requests are durably reserved to avoid duplicate provider dispatch. [Action reviews](../docs/ACTION_REVIEWS.md) documents the full lifecycle and error contract.

## Provider goal boundary

The Meta adapter's strict `pushpilot_goal_v1` response schema is inline in `backend/meta.py`. Its destination enum comes from the selected map's allowed destination IDs plus `UNKNOWN`; it also requires an English `summary` and `requires_clarification`, with no additional properties. Start/destination labels and aliases are supplied as symbolic map metadata. The adapter validates the result before the supervisor can prepare a deterministic temporary-graph plan.

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

Recorded-scene files bind original frame bytes/SHA-256, source, receive time, optional operator-provided capture time, map identity, registration reference and validated inspection. Recorded-action evidence adds its own pending-action binding, validated result, versions, elapsed time and reported usage; accepted events retain that record. Trusted physical capture/receipt linkage, crop lineage, qualified local findings and complete raw provider envelopes remain future work.

## Deliberately absent

The temporary definition contains drawing coordinates, graph edges, marker geometry, and test-only board-to-image projection. It defines no robot coordinates, camera-to-BASE transform, qualified stop/exit lines, swept footprint, or live signal ROIs. Follow [Temporary map](../docs/TEMPORARY_MAP.md) and label private inputs under [Test inputs](../docs/TEST_INPUTS.md).

The simulator creates no native hardware receipts. Physical completion requires a separately implemented and qualified measured adapter. Credentials and model-generated executable commands do not belong in these contracts.

New goal submission requires non-executing preparation. Active missions, including signal waits and reviews, reject goal replacement. Completion/termination and explicit reconciliation precede replacement.

Run `python tools/dev.py check` and `python tools/dev.py test` with runtime dependencies installed. The first command checks syntax; API and mission tests exercise the actual Pydantic and supervisor rejection behavior.

---

[Prompt versioning](../prompts/README.md) · [Tests](../tests/README.md) · [Roadmap](../docs/ROADMAP.md)
