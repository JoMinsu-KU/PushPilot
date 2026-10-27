<sub>[PushPilot](../README.md) / Application / Backend</sub>

# The mission supervisor

**A durable, hardware-free workspace with explicit approval and review gates.**

[Architecture](../docs/ARCHITECTURE.md) · [Services](../docs/SERVICE_COMPOSITION.md) · [Contracts](../contracts/workspace.ts) · [Deployment](../deploy/README.md)

> **Implemented: temporary-map simulation and recorded-image inspection.** FastAPI serves a revisioned operator API and the built frontend from one origin. SQLite preserves state, decisions, and command receipts. Every mission action and signal result is explicitly simulated. Separate recorded-image inspection can call MUSE but grants no motion authority; voice capture remains unimplemented.

## What runs today

| Component | Current behavior |
| :--- | :--- |
| Mission supervisor | Replaceable Little Town graph; east-facing PIZZA start to BAKERY, BOOKSTORE, or SCHOOL, with route-specific PUSH, STOP, CROSS, and VERIFY actions. |
| Admission gate | A mandatory simulated full stop, accepted demo stop review, and fresh simulated GREEN admit one crossing. |
| Review | The operator injects PASS, FAIL, UNKNOWN, or REOBSERVE with an exact observation binding. This is labelled `demo`, never MUSE image evidence. |
| MUSE goal adapter | Explicit `provider: meta` goal requests call Muse Spark 1.3. No provider request runs at startup; failures do not fall back to demo interpretation. |
| Temporary map | Validated drawing facts and canonical geometry hash; deterministic shortest paths and turn descriptions. No robot coordinate transform. |
| Scene inspection | Uploaded/recorded images, ArUco detection, explicit test registration, and opt-in MUSE inspection in a separate non-authoritative store. |
| Evidence store | Chronological, append-only events plus exact request-ID/payload receipts. Reset retains the timeline. |
| Same-origin host | Serves `frontend/dist` when built. Unknown `/api` routes return JSON 404 rather than an HTML application page. |
| Unavailable capabilities | Robot, live camera, production registered AR, voice, and automatic mission image review are unavailable. Recorded-image scene inspection is separate. |

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
| `META_API_KEY` | Optional backend-only credential from process environment or the repository's ignored `.env`. |

Configuration, local credential reads, and database initialization happen in ASGI lifespan, not at module import. No startup path contacts a robot, camera, or provider. The key is never returned to the browser. Keep `.env`, databases, and operational evidence out of Git and source releases.

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
| `GET /api/v1/state` | Current snapshot, capabilities, and chronological evidence. |
| `POST /api/v1/goals` | Interpret a typed or future confirmed voice goal. |
| `POST /api/v1/approve` | Bind approval to a plan ID and revision. |
| `POST /api/v1/advance` | Run the next permitted bounded simulated action. |
| `POST /api/v1/signal` | Inject a clearly simulated RED/GREEN/UNKNOWN observation. |
| `POST /api/v1/reviews` | Inject a demo verdict for the exact pending review ID. |
| `POST /api/v1/reobserve` | Replace an uncertain observation binding without movement. |
| `POST /api/v1/cancel` / `reset` | Explicit termination and reconciliation. |

Each mutation includes a UUID `request_id` and current `expected_revision`. Stale commands and request-ID reuse with changed payloads return HTTP 409. Exact retries return their original receipt, which may contain an older snapshot; fetch state to reconcile after an interrupted connection. Typed/voice goals cannot replace an active or waiting mission. Provider failures return a sanitized HTTP 502 and preserve failure evidence.

## Restart behavior

An active mission reopens as `RECOVERY_REQUIRED`. Approval, stop verification, signal binding, and pending review are cleared; no movement or queued command is replayed. The operator must inspect evidence and explicitly reset. A previously observed signal is also cleared when restarting an inactive workspace.

SQLite commits the state, event append, and command receipt together. Evidence remains append-only through cancel and reset. This first store is intended for a single local demonstration workspace; authentication, multiple operators, retention/export policy, and production migration are later work.

## Still to implement

- Bounded push-to-talk upload, format validation, and Meta voice transcription, following the [voice design](../docs/VOICE_INPUT.md).
- Bind actual fresh-image MUSE review to each mission action. Current scene inspection is intentionally separate and cannot authorize simulated or physical continuation.
- Qualified local signal observation/inhibition, separate from model latency.
- Production map and metric AR registration, contact geometry, physical pushing/turning, robot transport, and independent physical verification. Test-only camera-to-drawing overlays are already available for uploaded frames.

The model interprets intent and eventually reviews scene evidence. Deterministic gates own state transitions; model text never supplies executable robot code or authoritative metric coordinates.

## Validate offline

```sh
python tools/dev.py check
python tools/dev.py test
```

The backend tests inject isolated temporary databases and offline providers. They cover stale approval/revision, review binding, mandatory stops, RED waiting/GREEN admission, stale and junction-scoped signals, uncertainty/failure, idempotency, restart reconciliation, route geometry/hash changes, static/API routing, and provider-failure isolation. Separate scene tests cover marker detection and registration using synthetic images. They never inspect the real `.env`, call Meta, or contact equipment.

---

[Operator frontend](../frontend/README.md) · [MUSE prompts](../prompts/README.md) · [Development](../docs/DEVELOPMENT.md)
