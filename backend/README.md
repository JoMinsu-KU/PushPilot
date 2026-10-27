<sub>[PushPilot](../README.md) / Application / Backend</sub>

# The mission supervisor

**A durable simulation workspace with explicit approval and review gates.**

[Architecture](../docs/ARCHITECTURE.md) · [Services](../docs/SERVICE_COMPOSITION.md) · [Live preview](../docs/LIVE_CAMERA.md) · [Contracts](../contracts/workspace.ts) · [Deployment](../deploy/README.md)

> **Implemented: temporary-map simulation, recorded-image review and opt-in live camera preview.** FastAPI serves a revisioned operator API and the built frontend from one origin. SQLite preserves state, decisions and command receipts. Every action receipt and signal remains simulated. Bound MUSE before/after review can affect the simulated supervisor; separate scene inspection and the ephemeral live preview cannot. None grants physical motion authority. Voice capture remains unimplemented.

## What runs today

| Component | Current behavior |
| :--- | :--- |
| Mission supervisor | Replaceable Little Town graph; east-facing PIZZA start to BAKERY, BOOKSTORE, or SCHOOL, with route-specific PUSH, STOP, CROSS, and VERIFY actions. |
| Admission gate | A mandatory simulated full stop, accepted action review and fresh junction-scoped simulated GREEN admit one crossing. |
| Demo review | The operator injects PASS, FAIL, UNKNOWN or REOBSERVE with an exact observation binding. This is labelled `demo`, never MUSE image evidence. |
| MUSE action review | `backend/action_review.py` compares an operator-selected recorded before/after pair, binds it to the pending action and applies a validated result through supervisor gates. |
| MUSE goal adapter | Explicit `provider: meta` goal requests call Muse Spark 1.3. No provider request runs at startup; failures do not fall back to demo interpretation. |
| Temporary map | Validated drawing facts and canonical geometry hash; deterministic shortest paths and turn descriptions. No robot coordinate transform. |
| Scene inspection | Uploaded/recorded images, ArUco detection, explicit test registration, and opt-in MUSE inspection in a separate non-authoritative store. |
| Live preview | `backend/live_camera.py` polls an explicitly configured, already running loopback helper. Up to eight native JPEG frames and a display-only registration remain in RAM, separate from recorded evidence. |
| Evidence store | Chronological, append-only events plus exact request-ID/payload receipts. Reset retains the timeline. |
| Same-origin host | Serves `frontend/dist` when built. Unknown `/api` routes return JSON 404 rather than an HTML application page. |
| Unavailable capabilities | Robot control, qualified control-camera observations, production registered AR, voice and fresh physical action review are unavailable. Recorded-image review is explicitly operator selected; live preview is display-only. |

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

The authorized development arrangement uses `tools/camera_preview.py` on GX10 at `127.0.0.1:8084`, SSH forwarding to client `127.0.0.1:8895`, and the Windows application on port `8893`:

```sh
python tools/serve.py --port 8893 --live-camera-url http://127.0.0.1:8895
```

The helper must be separately authorized and started. It requests native 1920 × 1080 MJPEG at 30 fps, copies JPEG bytes without re-encoding, uses a device lock and refuses a detected existing camera owner without terminating it. Requested fps is not measured browser throughput. Only this standalone helper runs on GX10; the application is not deployed there. See [Live camera preview](../docs/LIVE_CAMERA.md) for its launch and transport boundary.

The preview snapshot identifies live source, camera identity/epoch, sequence, unique frame ID, dimensions, SHA-256 and host receive/dequeue time. That time is not sensor exposure time. Reported upstream age plus transport and elapsed application time determine freshness; the limit is 1,500 ms and a repeated sequence does not reset age. At most eight frames are cached in application RAM, with no raw-preview persistence in `SceneStore` or SQLite. Individual image responses permit 30 seconds of private browser caching.

Explicit registration requires a fresh selected frame and a consistent current four-marker view. Camera identity/epoch, dimensions or map identity changes require manual relocking. Temporary marker occlusion retains the fixed homography as `locked_occluded`, with current alignment unverified. A coherent, distributed shift in at least two markers across three new frames latches `view_changed` and withholds the overlay; no automatic refit occurs. These checks establish neither successful physical calibration nor camera-to-BASE geometry.

The dedicated health field `camera_preview_connected` reports a live preview separately from workspace `camera` and `robot` capability flags. Those remain false because qualified control observations and robot transport are unsupported. Preview requests do not mutate a mission, send images to MUSE, feed action review, supply a traffic signal or update robot state. They have their own [DTO](../contracts/live-camera.ts), outside recorded-scene revisions and evidence.

## Temporary-map missions

| Destination | Drawing-node route | Drawing distance | Reviewed actions |
| :--- | :--- | ---: | ---: |
| BOOKSTORE | PIZZA → C → BOOKSTORE | 148 mm | 5 |
| BAKERY | PIZZA → C → S → BAKERY | 232 mm | 8 |
| SCHOOL | PIZZA → C → S → SCHOOL | 232 mm | 8 |

The start is constrained to face east; routes are deterministic shortest paths under that initial-heading assumption. Drawing distances are not qualified TCP travel distances.

1. Submit one supported destination. Demo interpretation accepts English/Korean aliases; ambiguous or unsupported goals need clarification. Actual MUSE interpretation is opt-in.
2. Approve the exact plan ID/revision and temporary-map identity.
3. For each junction, run the approach PUSH and review it, then run a mandatory STOP and review it even if GREEN was observed earlier.
4. RED or UNKNOWN waits. A fresh simulated GREEN bound to this junction automatically admits CROSS after its stop gate is satisfied.
5. Review CROSS. Its stop/signal bindings are cleared, so the next junction requires its own independent stop, review, and fresh signal.
6. Run and review the final PUSH, then VERIFY the simulated destination outcome.

Map replacement invalidates pending approval. Approval, advance, and automatic crossing admission reject a mismatched map ID/version/hash. Old unmapped prepared plans migrate to IDLE; active missions still enter restart recovery without replay.

A GREEN observation expires after **30 seconds in this demonstrator**. This is a software demonstration setting, not a measured physical tolerance. A later RED does not undo an already admitted bounded crossing. Its result still requires review before the next action.

UNKNOWN and REOBSERVE inhibit motion and require a new observation binding. FAIL faults the mission. Cancel prevents further simulated action; it is not a hardware emergency stop. Reset is rejected during active execution/review/signal waiting until the mission is explicitly cancelled.

## HTTP boundary

The definitive DTO and command contract is [workspace.ts](../contracts/workspace.ts).

| Request | Purpose |
| :--- | :--- |
| `GET /api/health` | Equipment-free process health. |
| `GET /api/v1/map` | Temporary geometry, graph, source flags, and geometry hash. |
| `GET /api/v1/scene` | Independent recorded-image and test-overlay inspection state. |
| `GET /api/v1/live-camera` | Independent ephemeral preview state, source/freshness metadata and display-registration status. |
| `GET /api/v1/live-camera/frames/{frame_id}/image` | Native JPEG from the bounded RAM cache; expired frame IDs return 404. |
| `POST /api/v1/live-camera/registration` | Explicit fresh display lock using `{epoch, frame_id}`; no mission mutation. |
| `GET /api/v1/state` | Current snapshot, capabilities, and chronological evidence. |
| `POST /api/v1/goals` | Interpret a typed or future confirmed voice goal. |
| `POST /api/v1/approve` | Bind approval to a plan ID and revision. |
| `POST /api/v1/advance` | Run the next permitted bounded simulated action. |
| `POST /api/v1/signal` | Inject a clearly simulated RED/GREEN/UNKNOWN observation. |
| `POST /api/v1/reviews` | Inject a demo verdict for the exact pending review ID. |
| `POST /api/v1/action-reviews` | Compare an immutable recorded pair with MUSE for the pending simulated review; [exact workflow and receipt](../docs/ACTION_REVIEWS.md). |
| `POST /api/v1/reobserve` | Replace an uncertain observation binding without movement. |
| `POST /api/v1/cancel` / `reset` | Explicit termination and reconciliation. |

Each mission mutation includes a UUID `request_id` and current `expected_revision`. Stale commands and request-ID reuse with changed payloads return HTTP 409. Exact retries return their original receipt, which may contain an older snapshot; fetch state to reconcile after an interrupted connection. Typed/voice goals cannot replace an active or waiting mission. Provider failures return sanitized errors without a demo fallback. Action-image review additionally reserves the request durably, sends provider work outside store locks, then rechecks mission/scene/map/frame identity. Recorded-scene mutations have their own revision contract. Live display registration instead binds its transient epoch/frame identity and does not create a mission receipt.

## Restart behavior

An active mission reopens as `RECOVERY_REQUIRED`. Approval, stop verification, signal binding, and pending review are cleared; no movement or queued command is replayed. The operator must inspect evidence and explicitly reset. A previously observed signal is also cleared when restarting an inactive workspace.

SQLite commits the state, event append, and command receipt together. Evidence remains append-only through cancel and reset. This first store is intended for a single local demonstration workspace; authentication, multiple operators, retention/export policy, and production migration are later work.

## Still to implement

- Bounded push-to-talk upload, format validation, and Meta voice transcription, following the [voice design](../docs/VOICE_INPUT.md).
- Connect fresh physical post-action capture and independent measurements. Recorded-pair action review already affects simulation; its selected uploads do not prove capture chronology or hardware completion.
- Qualified local signal observation/inhibition, separate from model latency.
- Production map and metric AR registration, contact geometry, physical pushing/turning, robot transport, and independent physical verification. Test-only camera-to-drawing overlays are already available for uploaded frames and an explicitly locked live display.

The model interprets intent and reviews supplied recorded evidence. Deterministic gates own state transitions; model text never supplies executable robot code or authoritative metric coordinates.

## Validate offline

```sh
python tools/dev.py check
python tools/dev.py test
```

The backend tests inject isolated temporary databases and offline providers. They cover stale approval/revision, review binding, mandatory stops, RED waiting/GREEN admission, stale and junction-scoped signals, uncertainty/failure, idempotency, restart reconciliation, route geometry/hash changes, static/API routing, and provider-failure isolation. Separate scene tests cover marker detection and registration using synthetic images. They never inspect the real `.env`, call Meta, or contact equipment.

---

[Operator frontend](../frontend/README.md) · [MUSE prompts](../prompts/README.md) · [Development](../docs/DEVELOPMENT.md)
