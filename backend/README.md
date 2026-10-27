<sub>[PushPilot](../README.md) / Application / Backend</sub>

# The mission supervisor

**A durable, hardware-free workspace with explicit approval and review gates.**

[Architecture](../docs/ARCHITECTURE.md) · [Services](../docs/SERVICE_COMPOSITION.md) · [Contracts](../contracts/workspace.ts) · [Deployment](../deploy/README.md)

> **Implemented: first simulation slice.** FastAPI serves a revisioned operator API and the built frontend from one origin. SQLite preserves state, decisions, and command receipts. Every action result is explicitly simulated; image review and voice capture remain unimplemented.

## What runs today

| Component | Current behavior |
| :--- | :--- |
| Mission supervisor | One symbolic PIZZA → BAKERY mission; approved PUSH, STOP, CROSS, and VERIFY actions. |
| Admission gate | A mandatory simulated full stop, accepted demo stop review, and fresh simulated GREEN admit one crossing. |
| Review | The operator injects PASS, FAIL, UNKNOWN, or REOBSERVE with an exact observation binding. This is labelled `demo`, never MUSE image evidence. |
| MUSE goal adapter | Explicit `provider: meta` goal requests call Muse Spark 1.3. No provider request runs at startup; failures do not fall back to demo interpretation. |
| Evidence store | Chronological, append-only events plus exact request-ID/payload receipts. Reset retains the timeline. |
| Same-origin host | Serves `frontend/dist` when built. Unknown `/api` routes return JSON 404 rather than an HTML application page. |
| Unavailable capabilities | Robot, camera, registered AR, voice, and image review are reported as unavailable. |

The symbolic plan is a contract demonstration, not a road graph, installed route, vehicle pose, or physical reachability result. The map hold remains in effect.

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
| `META_API_KEY` | Optional backend-only credential from process environment or the repository's ignored `.env`. |

Configuration, local credential reads, and database initialization happen in ASGI lifespan, not at module import. No startup path contacts a robot, camera, or provider. The key is never returned to the browser. Keep `.env`, databases, and operational evidence out of Git and source releases.

## The first mission

1. Submit a typed goal. Demo interpretation recognizes the symbolic bakery destination; other goals need clarification. Actual MUSE interpretation is opt-in.
2. Review and approve the exact plan ID and revision.
3. Advance one bounded simulated PUSH and record its demo review.
4. Advance STOP. A simulated full-stop result is recorded even if GREEN was observed earlier. Its review must be accepted before entry.
5. RED or UNKNOWN waits. Fresh simulated GREEN automatically admits CROSS after the stop gate is satisfied; another PLAY or advance command is unnecessary.
6. Review CROSS, advance VERIFY, and review the final outcome to complete the simulation.

A GREEN observation expires after **30 seconds in this demonstrator**. This is a software demonstration setting, not a measured physical tolerance. A later RED does not undo an already admitted bounded crossing. Its result still requires review before the next action.

UNKNOWN and REOBSERVE inhibit motion and require a new observation binding. FAIL faults the mission. Cancel prevents further simulated action; it is not a hardware emergency stop. Reset is rejected during active execution/review/signal waiting until the mission is explicitly cancelled.

## HTTP boundary

The definitive DTO and command contract is [workspace.ts](../contracts/workspace.ts).

| Request | Purpose |
| :--- | :--- |
| `GET /api/health` | Equipment-free process health. |
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
- Source-labelled image intake and actual fresh-image MUSE review with image hashes and provider-result bindings.
- Qualified local signal observation/inhibition, separate from model latency.
- Installed-map registration, AR alignment, contact geometry, physical pushing/turning, robot transport, and independent physical verification.

The model interprets intent and eventually reviews scene evidence. Deterministic gates own state transitions; model text never supplies executable robot code or authoritative metric coordinates.

## Validate offline

```sh
python tools/dev.py check
python tools/dev.py test
```

The backend tests inject isolated temporary databases and offline providers. They cover stale approval/revision, review binding, mandatory stops, RED waiting/GREEN admission, stale signals, uncertainty/failure, idempotency, restart reconciliation, static/API routing, and provider-failure isolation. They never inspect the real `.env`, call Meta, or contact equipment.

---

[Operator frontend](../frontend/README.md) · [MUSE prompts](../prompts/README.md) · [Development](../docs/DEVELOPMENT.md)
