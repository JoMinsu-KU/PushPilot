<sub>[PushPilot](../README.md) / Application / Backend</sub>

# The mission supervisor

**A durable simulation workspace with explicit approval and review gates.**

[Architecture](../docs/ARCHITECTURE.md) · [Live intelligence](../docs/LIVE_INTELLIGENCE.md) · [Voice backend](../docs/VOICE_BACKEND.md) · [Contracts](../contracts/README.md) · [Deployment](../deploy/README.md)

> **Implemented in code: simulation, explicit native-frame MUSE planning/action/signal services, recorded-image review and finite voice transcription uploads.** FastAPI serves a revisioned operator API and the built frontend from one origin. SQLite preserves state, deliberate selected image evidence, decisions and command receipts. Action and stop receipts remain simulated; images and model judgments retain separate sources. Preview polling itself cannot advance a mission. Browser microphone capture is disconnected. Offline checks and [actual provider records](../docs/META_API_CHECK.md) have separate scopes; real-car action/signal accuracy, ASR access and physical execution remain unverified.

## What runs today

| Component | Current behavior |
| :--- | :--- |
| Mission supervisor | Selected drawing graph with route-specific PUSH, STOP, CROSS and VERIFY steps. Receipts are server-created simulation data, never hardware completion. |
| Live planning | `planning_provider.py` sends the exact goal, unchanged native JPEG, selected graph and frame registration context to Muse Spark 1.3. `live_intelligence.py` validates and compiles the exact proposed node sequence and constraints. |
| Admission gate | Mandatory simulated full stop, accepted bound review and current junction/approach MUSE GREEN can admit one crossing. No local color classifier. Missing reviewed signal-target metadata rejects before dispatch. |
| Live action review | `live_review_provider.py` compares server-bound native BEFORE/AFTER frames following one simulated action; the supervisor rechecks the original request/action/map/view binding before applying a result. |
| Bounded orchestration | `/live-actions/run` combines one action/reobservation with review and can start a configured post-STOP signal watch. `/wait` allows three judgments; background `/watch` defaults to 30 judgments/300 seconds with explicit cancellation and no startup resume. GREEN leaves CROSS pending review. |
| Demo/recorded review | Explicit demo missions retain manually injected verdicts and colors. `action_review.py` supports operator-selected recorded pairs. Neither path may advance a live-backed plan. |
| Symbolic goal adapter | `meta.py` preserves explicit text-only destination interpretation for offline/symbolic requests. No request runs at startup and a failed live call never falls back to it. |
| Temporary map | Validated drawing facts/hash, generic directed path compilation, constraints and derived maneuver descriptions; `/maps/validate` previews a replacement without installing it. No robot coordinate transform. |
| Scene inspection | Uploaded/recorded images, ArUco detection, explicit test registration, and opt-in MUSE inspection in a separate non-authoritative store. |
| Live preview | `backend/live_camera.py` polls an explicitly configured, already running loopback helper. Up to eight native JPEG frames and a display-only registration remain in RAM, separate from recorded evidence. |
| Voice backend | `voice.py` and `voice_api.py` validate finite mono PCM WAV in RAM, request Meta transcription and retain bounded workspace-bound transcript candidates. No browser capture, actual voice-access verification or automatic goal submission. |
| Evidence store | Chronological events, exact request-ID/payload receipts and a private selected-native-frame ledger with pending/accepted/rejected/interrupted operation records. Reset retains history. |
| Same-origin host | Serves `frontend/dist` when built. Unknown `/api` routes return JSON 404 rather than an HTML application page. |
| Unavailable capabilities | Robot control/stop verification, measured vehicle pose, production metric AR, browser microphone capture and qualified physical action review. Actual live-model recognition and voice access remain unverified. |

The temporary graph describes drawing centerlines. Its route is a simulation plan, not an installed robot trajectory, measured vehicle pose, or physical reachability result. Production geometry, physical stop lines, contact turning, and camera-to-BASE registration remain unqualified.

## Run on a developer machine or GX10

Install the repository's pinned Python dependencies and build the frontend on a developer machine as described in the [development guide](../docs/DEVELOPMENT.md). GX10 serves the prebuilt static frontend and does not need Node.js.

From the repository root:

```sh
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080 --workers 1
```

Use **one application worker**. The workspace is one serialized demonstration session, not a multi-tenant or multi-process authority service. The [launcher](../tools/README.md) provides the project-level run interface.

| Setting | Default / purpose |
| :--- | :--- |
| `PUSHPILOT_STATE_PATH` | `runtime/workspace.sqlite3`; set to a persistent shared-state location for a release. |
| `PUSHPILOT_FRONTEND_DIST` | `frontend/dist`; optionally override the built asset directory. |
| `PUSHPILOT_MAP_PATH` | `backend/data/little-town-temporary.json`; replaceable reviewed temporary drawing adapter. |
| `PUSHPILOT_SCENE_DIR` | Optional private image/inspection/registration directory; defaults beside the workspace database. |
| `PUSHPILOT_LIVE_CAMERA_URL` | Optional process-environment numeric loopback HTTP origin with explicit port, or `tools/serve.py --live-camera-url`; absent by default. Connects only to an existing preview helper. |
| `META_API_KEY` | Optional backend-only credential from process environment or the repository's ignored `.env`. |

Configuration, local credential reads, and database initialization happen in ASGI lifespan, not at module import. Default startup contacts no robot, camera or provider. An explicit live-preview URL starts a poller for that existing loopback helper; it does not open a camera device, start a helper/tunnel or restart a service. No startup path calls MUSE or a robot. The key is never returned to the browser. Keep `.env`, databases, and operational evidence out of Git and source releases.

## Optional live camera preview

The deployed GX10 application connects directly to the independent camera helper at `127.0.0.1:8084`. The Windows development alternative uses SSH forwarding to client `127.0.0.1:8895` and an application on port `8893`:

```sh
python tools/serve.py --port 8893 --live-camera-url http://127.0.0.1:8895
```

The helper must be separately authorized and started. It requests native 1920 × 1080 MJPEG at 30 fps, copies JPEG bytes without re-encoding, uses a device lock and refuses a detected existing camera owner without terminating it. Requested fps is not measured browser throughput. The frontend/API application was separately deployed to GX10 on October 28; application startup does not own or restart the helper. See [Live camera preview](../docs/LIVE_CAMERA.md) for its launch and transport boundary.

The preview snapshot identifies live source, camera identity/epoch, sequence, unique frame ID, dimensions, SHA-256 and host receive/dequeue time. That time is not sensor exposure time. Reported upstream age plus transport and elapsed application time determine freshness; the limit is 1,500 ms and a repeated sequence does not reset age. At most eight frames are cached in application RAM, with no raw-preview persistence in `SceneStore` or SQLite. Individual image responses permit 30 seconds of private browser caching.

Explicit registration requires a fresh selected frame and a consistent current four-marker view. Camera identity/epoch, dimensions or map identity changes require manual relocking. Temporary marker occlusion retains the fixed homography as `locked_occluded`, with current alignment unverified. A coherent, distributed shift in at least two markers across three new frames latches `view_changed` and withholds the overlay; no automatic refit occurs. These checks establish neither successful physical calibration nor camera-to-BASE geometry.

The dedicated health field `camera_preview_connected` reports preview separately from workspace `camera` and `robot` flags, which remain false for qualified control observations and robot transport. Preview requests do not mutate a mission, send images to MUSE or persist evidence. Explicit live-intelligence commands separately select original frames and copy only those observations into the private SQLite ledger. Their source is real camera input, but their action/stop receipts and state transitions remain simulation. See the [preview DTO](../contracts/live-camera.ts) and [live-intelligence DTO](../contracts/live-intelligence.ts).

## Temporary-map missions

The following table preserves the default legacy demo/symbolic routes. It does not restrict live MUSE selection to the same departure or path.

| Destination | Drawing-node route | Drawing distance | Reviewed actions |
| :--- | :--- | ---: | ---: |
| BOOKSTORE | PIZZA → C → BOOKSTORE | 148 mm | 5 |
| BAKERY | PIZZA → C → S → BAKERY | 232 mm | 8 |
| SCHOOL | PIZZA → C → S → SCHOOL | 232 mm | 8 |

The legacy router uses the configured east-facing start and deterministic shortest paths. Live planning may select another registered departure or a longer valid path to satisfy the user's direction/via/avoid request. For example, the existing temporary map also permits PIZZA → W → SW → SCHOOL. The configured start is a scenario declaration, not an observed physical vehicle pose. Drawing distances are not qualified TCP travel distances.

1. Submit a supported goal. With `provider: "meta"`, a configured live-camera path defaults to native-image/graph planning. `planning_mode: "live"` requires it explicitly; `planning_mode: "symbolic"` selects legacy text-only destination interpretation. Without a configured camera, the omitted-mode legacy default remains symbolic. Voice confirmation requires a current transcript receipt and the live path.
2. Approve the exact plan ID/revision and temporary-map identity.
3. For each junction, run the approach PUSH and review it, then run a mandatory STOP and review it even if GREEN was observed earlier.
4. RED or UNKNOWN waits. A valid current MUSE GREEN bound to the live plan's stopped junction/approach admits CROSS after local checks. An explicit demo mission instead uses clearly labelled injected simulation colors.
5. Review CROSS. Its stop/signal bindings are cleared, so the next junction requires its own independent stop, review, and fresh signal.
6. Run and review the final PUSH, then VERIFY the simulated destination outcome.

Map replacement invalidates pending approval. Approval, advance, and automatic crossing admission reject a mismatched map ID/version/hash. Old unmapped prepared plans migrate to IDLE; active missions still enter restart recovery without replay.

A GREEN observation expires after **30 seconds in this demonstrator**. This is a software demonstration setting, not a measured physical tolerance. A later RED does not undo an already admitted bounded crossing. Its result still requires review before the next action.

UNKNOWN and REOBSERVE inhibit motion and require a new observation binding. FAIL faults the mission. Cancel prevents further simulated action; it is not a hardware emergency stop. Reset is rejected during active execution/review/signal waiting until the mission is explicitly cancelled.

## HTTP boundary

Shared boundaries are recorded in [workspace.ts](../contracts/workspace.ts), [live-intelligence.ts](../contracts/live-intelligence.ts) and the [voice backend contract](../docs/VOICE_BACKEND.md).

| Request | Purpose |
| :--- | :--- |
| `GET /api/health` | Equipment-free process health. |
| `GET /api/v1/map` | Temporary geometry, graph, source flags, and geometry hash. |
| `POST /api/v1/maps/validate` | Read-only validation/audit of a bounded proposed map definition; does not install it. |
| `GET /api/v1/scene` | Independent recorded-image and test-overlay inspection state. |
| `GET /api/v1/live-camera` | Independent ephemeral preview state, source/freshness metadata and display-registration status. |
| `GET /api/v1/live-camera/frames/{frame_id}/image` | Native JPEG from the bounded RAM cache; expired frame IDs return 404. |
| `POST /api/v1/live-camera/registration` | Explicit fresh display lock using `{epoch, frame_id}`; no mission mutation. |
| `GET /api/v1/state` | Current snapshot, capabilities, and chronological evidence. |
| `POST /api/v1/goals` | Typed or confirmed voice goal; explicit live/symbolic planning selection. |
| `POST /api/v1/plans/live` | Require native-image/graph MUSE planning with optional route constraints. |
| `POST /api/v1/live-actions/advance` / `run` | Pin BEFORE and run one simulated action; `run` also requests its fresh-image review. |
| `POST /api/v1/live-actions/reviews` / `reobserve` | Review the bound pair or renew an uncertain observation without repeating movement. |
| `POST /api/v1/live-signals/reviews` / `wait` | One post-stop MUSE judgment or a finite observation cycle. |
| `POST /api/v1/live-signals/watch` / `watch/stop`; `GET /api/v1/live-signals/watch` | Start/stop/inspect a bounded background observation task; default 30 judgments/2-second interval/300-second budget, capped at 60/10/900. No physical stop command or restart resume. |
| `GET /api/v1/live-intelligence/operations` | Inspect the latest 100 durable operation records. |
| `GET /api/v1/live-evidence/frames/{id}/image` | Original deliberately selected JPEG from the private evidence ledger. |
| `GET /api/v1/voice` | Backend configuration and supported upload bounds; no microphone connection claim. |
| `POST /api/v1/voice/transcriptions` | Finite PCM WAV multipart upload; return an editable transcript candidate, not a goal. |
| `GET /api/v1/voice/transcriptions/{id}` / `DELETE /api/v1/voice/transcriptions/{id}` | Inspect or discard a current unexpired workspace-bound candidate. |
| `POST /api/v1/approve` | Bind approval to a plan ID and revision. |
| `POST /api/v1/advance` | Run the next permitted bounded simulated action. |
| `POST /api/v1/signal` | Inject a clearly simulated RED/GREEN/UNKNOWN observation for an explicit demo/symbolic plan; live-backed plans reject it. |
| `POST /api/v1/reviews` | Inject a demo verdict for an eligible demo review; live-backed plans reject it. |
| `POST /api/v1/action-reviews` | Compare an immutable recorded pair with MUSE for the pending simulated review; [exact workflow and receipt](../docs/ACTION_REVIEWS.md). |
| `POST /api/v1/reobserve` | Replace an uncertain observation binding without movement. |
| `POST /api/v1/cancel` / `reset` | Explicit termination and reconciliation. |

Each mission mutation includes a UUID `request_id` and current `expected_revision`. Stale commands and changed-payload request-ID reuse return HTTP 409. Exact retries return their original receipt, which may contain an older snapshot; fetch current state after an interrupted connection. Goals cannot replace an active or waiting mission. Provider failures return sanitized errors without a demo fallback. Inference runs outside store locks and commits only after context revalidation. Recorded-scene mutations use their own revision contract; live display registration uses its transient epoch/frame identity. Map validation is read-only. Voice uploads have capture/revision fields and a separate bounded in-memory transcript lifecycle; they do not create mission receipts or submit a goal.

## Restart behavior

An active mission reopens as `RECOVERY_REQUIRED`. Approval, stop verification, signal binding, and pending review are cleared; no movement or queued command is replayed. The operator must inspect evidence and explicitly reset. A previously observed signal is also cleared when restarting an inactive workspace.

SQLite commits the state, event append, and command receipt together. Evidence remains append-only through cancel and reset. This first store is intended for a single local demonstration workspace; authentication, multiple operators, retention/export policy, and production migration are later work.

## Remaining integration and qualification

- Connect actual browser push-to-talk capture, editable transcript confirmation and cancellation on trusted tablet HTTPS; verify actual Meta voice access with Korean/English recordings. The [finite-upload backend](../docs/VOICE_BACKEND.md) is already implemented.
- Exercise new native-frame planning/action/signal endpoints against the actual provider and installation. Offline transports do not establish recognition quality or latency. Configure reviewed approach-specific paper-signal targets; the current temporary map intentionally has none.
- Connect independently qualified physical action and stop receipts, capture chronology and measured outcomes. Current live image reviews follow simulated receipts and cannot prove robot completion, physical stopping or arrival.
- Wire the dedicated live operation controls through the tablet's complete interaction, retaining clear source and failure states. The existing frontend route geometry is reusable; an autonomous full-mission runner is not implemented.
- Production map and metric AR registration, contact geometry, physical pushing/turning, robot transport, and independent physical verification. Test-only camera-to-drawing overlays are already available for uploaded frames and an explicitly locked live display.

The model selects drawing-graph routes and judges supplied image evidence. Deterministic gates own simulation transitions; model text never supplies executable robot code or authoritative robot coordinates. The verified GX10 application release and independently running camera helper retain separate lifetimes; [deployment verification](../docs/VERIFICATION.md#gx10-application-deployment-october-28) records the installation and startup scope.

## Validate offline

```sh
python tools/dev.py check
python tools/dev.py test
```

The backend tests inject isolated databases, synthetic images/audio and offline HTTP/provider transports. They cover approval/revision and request binding, native frame/hash preservation and ordering, mandatory stops, scoped signal admission, failure/uncertainty, bounded orchestration, journal/restart behavior, map constraints/replacement validation and finite voice uploads/candidate lifecycle. These checks never read the real `.env`, call Meta or contact equipment. They are not real-provider or physical success evidence.

---

[Operator frontend](../frontend/README.md) · [MUSE prompts](../prompts/README.md) · [Development](../docs/DEVELOPMENT.md)
