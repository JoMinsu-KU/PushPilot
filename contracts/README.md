<sub>[PushPilot](../README.md) / Shared boundaries / Contracts</sub>

# Versioned workspace boundaries

**Keep the UI, provider, and simulator aligned without granting model output execution authority.**

[Architecture](../docs/ARCHITECTURE.md) · [Backend](../backend/README.md) · [Live intelligence](../docs/LIVE_INTELLIGENCE.md) · [Voice backend](../docs/VOICE_BACKEND.md)

> **Implemented:** [`workspace.ts`](workspace.ts) describes `pushpilot.workspace.v1`; [`scene.ts`](scene.ts) describes map/routes, optional route-display geometry and recorded-scene state; [`live-camera.ts`](live-camera.ts) describes ephemeral preview; [`action-review.ts`](action-review.ts) describes recorded-action evidence; [`live-intelligence.ts`](live-intelligence.ts) adds native-frame planning, action/signal operations and their selected evidence. Backend request models validate commands, with bounded manual parsers for map JSON and voice multipart uploads. These interfaces are not a standalone formal JSON Schema catalog. Physical observation qualification and hardware receipts remain future contracts.

## Current API

| Endpoint | Input beyond the command base | Result |
| :--- | :--- | :--- |
| `GET /api/health` | None | Simulation health and disconnected-hardware status. |
| `GET /api/v1/state` | None | Current workspace snapshot, capabilities, and event history. |
| `POST /api/v1/goals` | `text`, `provider: demo\|meta`, optional `source`, `planning_mode: live\|symbolic`, `transcript_id`, `route_constraints` | Select live image/graph planning or explicit legacy symbolic interpretation. Voice requires a current confirmed transcript receipt. |
| `POST /api/v1/plans/live` | `text`, `source`, optional `transcript_id`, `route_constraints` | Native-image MUSE route proposal; exact graph/constraint validation and separate plan approval. |
| `POST /api/v1/live-actions/advance` / `run` | None | Pin BEFORE and run one abstract action; `run` also compares a fresh AFTER, or reobserves an uncertain action without repeating it. |
| `POST /api/v1/live-actions/reviews` | `review_id`, `expected_visual` | Apply a validated MUSE result only to its server-bound live pair/action. |
| `POST /api/v1/live-actions/reobserve` | None | Renew an uncertain live review while retaining its original BEFORE frame. |
| `POST /api/v1/live-signals/reviews` / `wait` | None for one review; bounded `max_attempts`, `interval_seconds` for wait | Judge a configured approach-specific paper signal after a matching simulated stop; current valid GREEN can admit one simulated crossing. |
| `GET /api/v1/live-intelligence/operations` | None | Latest 100 durable operation records; pending, accepted, rejected or interrupted. |
| `GET /api/v1/live-evidence/frames/{id}/image` | None | Unchanged original JPEG from the private selected-frame ledger. |
| `POST /api/v1/approve` | `plan_id`, `plan_revision` | Approve exactly the current plan. |
| `POST /api/v1/advance` | None | Admit the next eligible abstract action. Crossing uses its own gate. |
| `POST /api/v1/signal` | `color: RED\|GREEN\|UNKNOWN`, optional `junction_id` | Inject a simulated observation bound to the applicable junction. |
| `POST /api/v1/reviews` | `review_id`, `verdict: PASS\|FAIL\|REOBSERVE\|UNKNOWN` | Inject an explicitly demo-sourced verdict for the pending review. |
| `POST /api/v1/action-reviews` | `review_id`, `expected_scene_revision`, `before_frame_id`, `after_frame_id`, `expected_visual` | Bind an actual recorded-image MUSE result to the pending simulated action; return its supervisor consequence. |
| `POST /api/v1/reobserve` | None | Bind a new simulated review without replaying movement. |
| `POST /api/v1/cancel` | None | Terminate the simulation; no hardware-stop guarantee. |
| `POST /api/v1/reset` | None | Clear non-active state while retaining evidence history. |

Every mission POST in this table requires `request_id`, a UUID, and `expected_revision`, a nonnegative integer. Successful mutations return the snapshot. Invalid request fields/types are rejected by backend validation; stale revisions or invalid transitions return HTTP 409. Provider failures return sanitized HTTP 502/503 errors; a failed replacement cannot leave the previous plan approvable.

The same request ID and identical payload return the original receipt without running the command again. Reusing that ID for different content is rejected. An original receipt may have an older revision than a later poll; consumers must not overwrite newer state with it.

`source: "voice"` now requires a current workspace/map-bound transcript receipt plus the explicitly accepted text. The backend preserves original versus confirmed text and still requires plan approval. Browser recording and transcript editing are not connected; the type does not claim a supported microphone.

`provider: "meta"` defaults to live planning when a camera URL is configured. Explicit `planning_mode: "symbolic"` requests text-only legacy interpretation. Without a configured camera, the omitted-mode default remains symbolic for compatibility; a failed live request never substitutes it. Live-backed plans reject manual signal injection and demo/recorded review verdicts. See [live intelligence](../docs/LIVE_INTELLIGENCE.md) for exact operation and evidence semantics.

## Independent map and scene API

| Endpoint | Input | Result |
| :--- | :--- | :--- |
| `GET /api/v1/map` | None | Sanitized temporary graph/drawing facts and geometry hash. |
| `POST /api/v1/maps/validate` | JSON `{definition: proposedMap}`; at most 1 MiB. | Read-only structure, reachability and signal-target audit; no installation, registration or mission mutation. |
| `GET /api/v1/scene` | None | Current recorded frame, detection, locked-view status, inspection and scene revision. |
| `POST /api/v1/scene/frames` | Multipart `file`; optional timezone-bearing `captured_at`. | New private JPEG/PNG frame, up to 8 MiB and 12 MP. |
| `GET /api/v1/scene/frames/{id}/image` | Immutable frame ID. | Private runtime image. |
| `POST /api/v1/scene/registration` | `expected_revision`, `frame_id`. | Explicitly lock a four-marker board-to-image candidate. |
| `POST /api/v1/scene/reviews` | `expected_revision`, `frame_id`, `expected`. | Explicit Meta scene inspection, not mission action review. |

Scene mutations use the **scene revision**, not the mission revision or command-idempotency contract. Frame IDs are 32 lowercase hexadecimal characters. A late/superseded inspection or stale registration is rejected. Registration status is unregistered/partial/candidate/locked/locked_partial/view_changed; a withheld homography cannot be interpreted as a valid projection. Scene inspection returns USABLE/REOBSERVE/UNKNOWN, visible places, car visibility, separate paper-signal evidence, limitations, and `motion_authority: false`. No scene endpoint advances the supervisor.

## Snapshot and evidence

The snapshot binds a session and revision to state, goal, current plan/step, map/version/geometry-hash route, approval, simulated stopped status, source-labelled signal/review, capabilities, next check and ordered events. Live-backed plans retain selected-native-frame planning evidence. Plans contain drawing points/distances and node IDs, never robot targets.

Optional `route.visualization` contains drawing-only push/crossing subdivisions and illustrative stop-line geometry. `PlanStep.route_segment_id` binds PUSH/CROSS steps to those subdivisions; it is not a motion command. Older plans without consistent bindings display their complete planned route without inferred progress. Signal snapshots include `freshness_limit_ms` from the supervisor TTL for display. A frontend color alone never admits an action; the backend validates its bound stopped context. See [route display](../docs/ROUTE_DISPLAY.md).

Plan and review identifiers prevent approval or judgment from applying to a different revision. Events retain stable IDs, sequence numbers, timestamps, source labels, state, and explanatory text. SQLite also retains exact request digests and idempotent command receipts. Reset does not remove the event history.

Mission capabilities keep `robot`, `camera`, `registered_ar` and frontend `voice` false. Backend `live_planning`, `live_action_review`, `muse_signal_review` and `voice_transcription` flags describe configured software availability, not successful inference, a configured target at every approach or physical qualification. `image_review` and `recorded_action_review` describe the separate recorded path. `muse_configured` means a backend key is configured, not verified access. Scene-store live_camera/robot flags remain false because that store still owns recordings. Demo verdicts cannot become Meta evidence by changing a UI label.

## Recorded-action evidence

The [action-review DTO](action-review.ts) binds the before/after image IDs and SHA-256 values, map identity, session/plan/action/review, input workspace/scene revisions, expected visual text and server-bound action. It records a validated PASS/FAIL/REOBSERVE/UNKNOWN result, explanation, limitations, prompt/schema/model versions, elapsed time and provider-reported token counts or null.

Its source is `meta`, input kind is `operator_selected_recorded_pair`, and scope is `simulated_action_review` with `simulation_only: true` and `motion_authority: false`. The operator-provided expected text does not replace the server's action binding. The after frame must be current, both frames must belong to the map, and stale/superseded results cannot satisfy another review. Exact requests are durably reserved to avoid duplicate provider dispatch. [Action reviews](../docs/ACTION_REVIEWS.md) documents the full lifecycle and error contract.

## Provider planning boundaries

The legacy Meta adapter's strict `pushpilot_goal_v1` response schema remains in `backend/meta.py`. It receives symbolic place labels/aliases, selects only a destination and permits the legacy deterministic router to prepare a symbolic plan. It does not receive a camera image or select a road path.

`backend/planning_provider.py` implements the separate native-frame/graph response: destination, English summary, exact `route_nodes`, clarification, structured constraints and scene assessment. Its allowed node/destination IDs come from the selected map. The backend compiles and checks that exact connected directed path and derives AR geometry locally; the model cannot change map coordinates or emit robot targets/commands. Prompt/result versions are `pushpilot.live-route.prompt.v2` and `pushpilot.live-route.result.v1`.

Live action and signal providers use `pushpilot.live-action.prompt.v1` / `pushpilot.live-action.result.v1` and `pushpilot.live-signal.prompt.v1` / `pushpilot.live-signal.result.v1`. The strict local validators reject malformed results independently of upstream schema claims. No model result supplies plan approval or physical motion authority, and no actual-provider failure falls back to a demo parser.

## Rules for later contracts

1. **Version the boundary.** Change consumers, fixtures, and validation together.
2. **Bind each result.** Retain the request, action, observation, and session context.
3. **Preserve independent sources.** Robot state, image, car pose, signal, audio, and model result can have different origins.
4. **Represent uncertainty.** Unknown, unavailable, invalid, and incomplete remain distinct from success.
5. **Separate clocks.** Capture/record timestamps support provenance; monotonic durations support local timeouts.
6. **Expose causes.** Keep the evidence and gate result that caused each transition.

## Voice candidates and original images

The [voice backend](../docs/VOICE_BACKEND.md) implements `GET /api/v1/voice`, finite multipart `POST /api/v1/voice/transcriptions`, and candidate `GET`/`DELETE /api/v1/voice/transcriptions/{transcript_id}`. Upload fields are `file`, `expected_revision`, `capture_id`, `audio_source` and optional `language`. It accepts bounded mono PCM16 WAV at 16/24 kHz, returns original-language text and a workspace/map-bound candidate, and retains no raw audio. The candidate registry is in RAM, bounded to 32 records/30 minutes. Browser capture/editing is still unconnected; original-versus-confirmed text is preserved when a live goal explicitly accepts a current receipt. No ASR confidence is invented.

Recorded-scene files bind original frame bytes/SHA-256, source, receive time, optional operator-provided capture time, map identity, registration reference and validated inspection. Recorded-action evidence adds its own pending-action binding, validated result, versions, elapsed time and reported usage; accepted events retain that record. Trusted physical capture/receipt linkage, crop lineage, qualified local findings and complete raw provider envelopes remain future work.

## Deliberately absent

The temporary definition contains drawing coordinates, graph edges, marker geometry and test-only board-to-image projection. Optional reviewed `signal_targets` bind an active-paper region to a specific junction and incoming node; the current map has none. The definition supplies no robot coordinates, camera-to-BASE transform, qualified stop/exit lines or swept footprint. Follow [map replacement](../docs/MAP_REPLACEMENT.md) and label private inputs under [Test inputs](../docs/TEST_INPUTS.md).

The simulator creates no native hardware receipts. Physical completion requires a separately implemented and qualified measured adapter. Credentials and model-generated executable commands do not belong in these contracts.

New goal submission requires non-executing preparation. Active missions, including signal waits and reviews, reject goal replacement. Completion/termination and explicit reconciliation precede replacement.

Run `python tools/dev.py check` and `python tools/dev.py test` with runtime dependencies installed. The first command checks syntax; API and mission tests exercise the actual Pydantic and supervisor rejection behavior.

---

[Prompt versioning](../prompts/README.md) · [Tests](../tests/README.md) · [Roadmap](../docs/ROADMAP.md)
