<sub>[PushPilot](../README.md) / Shared boundaries / Contracts</sub>

# Versioned workspace boundaries

**Keep UI, provider, simulation and physical execution aligned through separate, versioned authority boundaries.**

[Architecture](../docs/ARCHITECTURE.md) · [Backend](../backend/README.md) · [Live intelligence](../docs/LIVE_INTELLIGENCE.md) · [Voice backend](../docs/VOICE_BACKEND.md)

> **Implemented:** [`workspace.ts`](workspace.ts) describes `pushpilot.workspace.v1`; [`scene.ts`](scene.ts) describes map/routes, optional route-display geometry and recorded-scene state; [`live-camera.ts`](live-camera.ts) describes ephemeral preview; [`action-review.ts`](action-review.ts) describes recorded-action evidence; [`live-intelligence.ts`](live-intelligence.ts) adds native-frame planning, action/signal operations and their selected evidence; [`voice.ts`](voice.ts) describes finite microphone phases and workspace-bound transcript candidates. Backend request models validate commands, with bounded manual parsers for map JSON and voice multipart uploads. These interfaces are not a standalone formal JSON Schema catalog. [`physical.ts`](physical.ts) describes the separate `pushpilot.physical.v1` service; [`physical-display.ts`](physical-display.ts) describes the GET-only `pushpilot.physical-display.v1` presentation cache. These implemented site-trial interfaces do not establish general physical qualification.

## Workspace and simulation API

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

`source: "voice"` requires a current workspace/map-bound transcript receipt plus explicitly accepted text. The backend preserves original versus confirmed text and still requires plan approval. The implemented browser captures finite PCM WAV, displays microphone RMS/processing state and permits edits before explicit **Create a plan**. Neither a transcript nor that planning action approves a mission. Actual iPad microphone/Safari behavior, trusted HTTPS and account ASR access remain unverified.

`provider: "meta"` defaults to live planning when a camera URL is configured. Explicit `planning_mode: "symbolic"` requests text-only legacy interpretation. Without a configured camera, the omitted-mode default remains symbolic for compatibility; a failed live request never substitutes it. Live-backed plans reject manual signal injection and demo/recorded review verdicts. See [live intelligence](../docs/LIVE_INTELLIGENCE.md) for exact operation and evidence semantics.

## Physical API: separate revision and source binding

These routes are prefixed `/api/v1/physical`. The current service is opt-in through private `PUSHPILOT_PHYSICAL_CONFIG`; absence means unavailable, not a simulation fallback. Physical `expected_revision` comes from `/physical/status`, not `/state`. Mutating routes require a same-origin browser `Origin`/Host binding; the hardware token remains server-side.

| Endpoint | Input beyond physical command base | Behavior |
|---|---|---|
| `GET /status` | None | Actual connection, mission/progress, signal, review activity, blockers, capabilities and telemetry |
| `GET /display` | None | GET-only receipt-driven display/Spatial estimate; `motion_authority: false` |
| `POST /start` | `workspace_session_id`, `plan_id`, `plan_revision`, `destination`, `route_nodes`, `map_id`, `map_version`, `map_hash` | Bind the current live MUSE plan in PLAN_READY and begin the eligible private taught recipe through explicit Robot approval/start |
| `POST /stop` | None | Request supported software hold; no hardware emergency-stop guarantee |
| `POST /reset` | `mission_id`, `reason` (10–500 characters) | Retire an eligible ended mission while preserving evidence; does not return the robot |
| `POST /resume` | `mission_id`, `reason` | Explicit checked continuation from a known completed review boundary; no completed contact replay |
| `POST /prepare-boundary` | `mission_id`, `reason` | Prepare the narrow C11 recovery boundary with source/camera/MUSE/IK checks; no route action |
| `POST /continue-c19` | `mission_id`, `reason` | Explicit C19 review omission from its exact eligible hold; preserve original NO_PROGRESS and record omission, never PASS |

The command base is UUID `request_id` plus strict non-negative `expected_revision`; unknown fields reject. Start requires the exact current live MUSE plan in **PLAN_READY**: the tablet's **Start robot mission** is its approval/start action. Do not call simulation `/approve` first; that separate operation changes the workspace state. Stop deliberately remains deliverable while status revisions advance during movement. Requests/recovery remain mission and exact source bound. Start accepts no TCP positions or executable model commands. Read [robot operations](../docs/ROBOT_OPERATIONS.md), [C11 recovery](../docs/C11_BOUNDARY_RECOVERY.md) and [START reference](../docs/SESSION_START_REFERENCE.md) before treating a reset, preparation, reconnect or resume as interchangeable.

`PhysicalStatus` reports actual executor receipt progress, optional Native TCP travel (`distance_source: native_tcp`) and independent `car.arrived`/`aligned` fields. Absence of measured travel stays null; drawing distance must not fill it. `parking_alignment` requires explicit true, and the current delivery-only release defers parking. `PhysicalDisplay` carries producer epoch/sequence, mission/plan/map binding and confirmed-only estimate updates. Its vehicle is always `estimated: true`; display intent or elapsed time cannot invent measured car motion. This optional cache cannot dispatch commands or fail the control endpoint.

Process restart does not automatically start a worker, resend unknown movement or restore an old signal admission. The one-time physical GREEN policy differs from the generic per-junction simulation gates. A new mission needs new admission; existing stop/Native/session guards remain active after recontact. [Current status](../docs/CURRENT_STATUS.md) and [known limitations](../docs/KNOWN_LIMITATIONS.md) describe qualification and unresolved idle-timeout behavior.

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

Legacy mission capabilities keep `robot`, `camera`, `registered_ar` and `voice` false; they are not a live microphone/device-permission report. Backend `live_planning`, `live_action_review`, `muse_signal_review` and `voice_transcription` flags describe configured software availability, not successful inference, a configured target at every approach or physical qualification. Voice readiness additionally checks the secure origin, eligible preparation and actual capture state; `/voice` does not claim device connection or verified provider access. `image_review` and `recorded_action_review` describe the separate recorded path. `muse_configured` means a backend key is configured, not verified access. Scene-store live_camera/robot flags remain false because that store still owns recordings. Demo verdicts cannot become Meta evidence by changing a UI label.

## Recorded-action evidence

The [action-review DTO](action-review.ts) binds the before/after image IDs and SHA-256 values, map identity, session/plan/action/review, input workspace/scene revisions, expected visual text and server-bound action. It records a validated PASS/FAIL/REOBSERVE/UNKNOWN result, explanation, limitations, prompt/schema/model versions, elapsed time and provider-reported token counts or null.

Its source is `meta`, input kind is `operator_selected_recorded_pair`, and scope is `simulated_action_review` with `simulation_only: true` and `motion_authority: false`. The operator-provided expected text does not replace the server's action binding. The after frame must be current, both frames must belong to the map, and stale/superseded results cannot satisfy another review. Exact requests are durably reserved to avoid duplicate provider dispatch. [Action reviews](../docs/ACTION_REVIEWS.md) documents the full lifecycle and error contract.

## Provider planning boundaries

The legacy Meta adapter's strict `pushpilot_goal_v1` response schema remains in `backend/meta.py`. It receives symbolic place labels/aliases, selects only a destination and permits the legacy deterministic router to prepare a symbolic plan. It does not receive a camera image or select a road path.

`backend/planning_provider.py` implements the separate native-frame/graph response: destination, English summary, exact `route_nodes`, clarification, structured constraints and scene assessment. Its allowed node/destination IDs come from the selected map. The backend compiles and checks that exact connected directed path and derives AR geometry locally; the model cannot change map coordinates or emit robot targets/commands. Prompt/result versions are `pushpilot.live-route.prompt.v3` and `pushpilot.live-route.result.v1`. The selected map owns the allowed destination/node vocabulary; City and Little Town do not share a fixed hard-coded place list.

Live action and signal providers use `pushpilot.live-action.prompt.v1` / `pushpilot.live-action.result.v1` and `pushpilot.live-signal.prompt.v1` / `pushpilot.live-signal.result.v1`. The strict local validators reject malformed results independently of upstream schema claims. No model result supplies plan approval or physical motion authority, and no actual-provider failure falls back to a demo parser.

## Rules for later contracts

1. **Version the boundary.** Change consumers, fixtures, and validation together.
2. **Bind each result.** Retain the request, action, observation, and session context.
3. **Preserve independent sources.** Robot state, image, car pose, signal, audio, and model result can have different origins.
4. **Represent uncertainty.** Unknown, unavailable, invalid, and incomplete remain distinct from success.
5. **Separate clocks.** Capture/record timestamps support provenance; monotonic durations support local timeouts.
6. **Expose causes.** Keep the evidence and gate result that caused each transition.

## Voice candidates and original images

The [voice backend](../docs/VOICE_BACKEND.md) implements `GET /api/v1/voice`, finite multipart `POST /api/v1/voice/transcriptions`, and candidate `GET`/`DELETE /api/v1/voice/transcriptions/{transcript_id}`. Upload fields are `file`, `expected_revision`, `capture_id`, `audio_source` and optional `language`. It accepts mono PCM16 WAV at 16/24 kHz, 0.2–20 seconds and at most 1 MiB, returns original-language text and a workspace/map-bound candidate, and retains no raw audio. The candidate registry is in RAM, bounded to 32 records/30 minutes. The browser encodes 16 kHz mono WAV from bounded Web Audio capture, stops on the second tap or at 20 seconds, displays measured RMS bars and an indeterminate pending spinner, and exposes an editable candidate. Explicit **Create a plan** sends `source: "voice"`, `transcript_id` and confirmed text; accepted live-goal evidence preserves original-versus-confirmed text. No ASR confidence, automatic plan approval or motion authority is invented.

The finite controller matches capture ID, exact session/revision/map binding and expiry, and rejects cancelled/late/superseded results. Recording resources and transient audio are released without browser storage; candidate discard is best effort and server expiry remains authoritative. Voice-only server preparation checks also reject physical active/HOLD/unretired missions, a busy coordinator or unavailable local snapshot before/after ASR and on lookup/acceptance. The guard does no Native IO and does not hold a coordinator lock across inference. Actual device/provider checks remain outstanding. [`deploy/ipad-https`](../deploy/ipad-https/README.md) contains only an unactivated LAN HTTPS candidate; no certificate-trust or Safari verification is implied.

Recorded-scene files bind original frame bytes/SHA-256, source, receive time, optional operator-provided capture time, map identity, registration reference and validated inspection. Recorded-action evidence adds its own pending-action binding, validated result, versions, elapsed time and reported usage; accepted events retain that record. The physical trial separately records Native/action linkage and its selected original/crop lineage. This does not upgrade recorded uploads into trusted post-action captures. General calibration/measurement qualification and a complete unified provider-envelope/export policy remain open.

## Deliberately absent

The temporary definition contains drawing coordinates, graph edges, marker geometry and test-only board-to-image projection. Optional reviewed `signal_targets` bind an active-paper region to a specific junction and incoming node; the bundled drawing adapter has no reviewed active-paper signal targets; the private physical signal configuration is separate. The definition supplies no robot coordinates, camera-to-BASE transform, qualified stop/exit lines or swept footprint. Follow [map replacement](../docs/MAP_REPLACEMENT.md) and label private inputs under [Test inputs](../docs/TEST_INPUTS.md).

The simulator creates no Native hardware receipts. The separate physical site-trial driver uses exact-source Native completion and applicable MUSE observation; its existence does not establish general physical repeatability. Credentials and model-generated executable commands do not belong in these contracts.

Workspace goal submission requires its non-executing preparation state; active simulation, including signal waits and reviews, rejects replacement. The tablet separately disables goal editing during an active Robot mission. The November 4 voice-only guard additionally rejects active/HOLD/unretired physical intent before capture acceptance, transcription lookup and spoken-goal submission. Direct typed/live goal APIs retain the original cross-service limitation; this change is not a global replacement lock. New Robot intent must follow explicit completion/termination and reconciliation, including retirement of a retained COMPLETE mission before another spoken goal.

Run `python tools/dev.py check` and `python tools/dev.py test` with runtime dependencies installed. The first command checks syntax; API and mission tests exercise the actual Pydantic and supervisor rejection behavior.

---

[Prompt versioning](../prompts/README.md) · [Tests](../tests/README.md) · [Roadmap](../docs/ROADMAP.md)
