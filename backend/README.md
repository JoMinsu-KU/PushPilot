<sub>[PushPilot](../README.md) / Application / Backend</sub>

# The mission supervisor

**From sight to action, with durable state and explicit execution gates.**

[Architecture](../docs/ARCHITECTURE.md) · [Services](../docs/SERVICE_COMPOSITION.md) · [Contracts](../contracts/README.md) · [Development](../docs/DEVELOPMENT.md)

The current source supports **equipment-free simulation by default** and an **explicitly configured physical site trial**. One FastAPI/Uvicorn worker serves the compiled English tablet workspace and API. Observe → Plan → Approve → Act → Verify remains the product loop; model output never supplies executable robot code or authoritative TCP coordinates.

As of **November 2, 2026**, B/Office Building, C/Villa and D/Hanok have taught recipes and dated physical arrival records. The active release is `delivery_only`: C ends at C26 with destination/zone review and empty-tool START return. Numeric alignment and parallel parking are deferred. Current-site execution is not general unattended repeatability qualification. See [current status](../docs/CURRENT_STATUS.md), [measured routes](../docs/MEASURED_ROUTE_CATALOGUE.md) and [known limitations](../docs/KNOWN_LIMITATIONS.md).

## What runs

| Component | Responsibility |
|---|---|
| **Simulation workspace** | `core.py` and SQLite compile graph PUSH/STOP/CROSS/VERIFY, approval, simulated receipts, review/wait/recovery and exact command idempotency. |
| **Map and route interpretation** | `maps.py` and `planning_provider.py` validate MUSE's exact selected directed path and departure/turn/via/avoid constraints. Route prompt v3 uses the selected map's vocabulary. |
| **Native-frame intelligence** | `live_intelligence.py` explicitly selects unchanged originals, binds action/stop context, journals inference and runs finite simulation action/signal helpers. |
| **Physical coordinator** | `physical_mission.py` owns separate lifecycle/revision, source-bound start/stop/reset/resume and actual execution telemetry. |
| **Site-trial driver** | `robot_control/site_trial_driver.py` and mission modules execute private taught BASE primitives, exact-source checks, Native completion, coordinate clearance/recontact and applicable MUSE observation. |
| **Physical display** | GET-only collector reads actual journals/receipts. Its Spatial vehicle is an execution estimate, not measured car tracking or a command source. |
| **Recorded scene/review** | `scene.py` and `action_review.py` own uploaded images, test display registration, independent inspection and selected-pair simulation review. |
| **Live preview** | `live_camera.py` polls an existing loopback camera helper, keeps at most eight frames in RAM and owns a separate display lock. |
| **Voice backend** | `voice.py`/`voice_api.py` validate finite mono PCM WAV, request transcription and retain bounded workspace/map-bound candidates; browser capture/editor pending. |

The City drawing is `seoul-city-a3` v`2026-10-28.4`, with Pizza-front departure and Office/Villa/Hanok frontage paths. `PUSHPILOT_MAP_PATH` selects it explicitly for a deployment. Source-default Little Town remains the equipment-free compatibility adapter; old Bakery/Bookstore/School examples are documented in [Temporary map](../docs/TEMPORARY_MAP.md).

Drawing graph, board-to-image display registration, Spatial display fit and taught BASE execution are separate. A graph point or AR line never becomes a TCP target. Physical mode requires private source-bound prerequisites unavailable in a clean public clone.

## Run the default application

Install pinned dependencies and build the frontend as described in [Development](../docs/DEVELOPMENT.md), then run from the repository root:

```sh
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080 --workers 1
```

GX10 serves the prebuilt bundle and needs no Node process. Use **one worker**: this is one serialized demonstration workspace, not a multi-process authority service.

| Setting | Purpose |
|---|---|
| `PUSHPILOT_STATE_PATH` | Private persistent workspace SQLite; default `runtime/workspace.sqlite3` |
| `PUSHPILOT_FRONTEND_DIST` | Built assets, default `frontend/dist` |
| `PUSHPILOT_MAP_PATH` | Reviewed map JSON; default `backend/data/little-town-temporary.json` |
| `PUSHPILOT_SCENE_DIR` | Private image/reference/inspection storage, default beside workspace state |
| `PUSHPILOT_LIVE_CAMERA_URL` | Explicit numeric-loopback HTTP origin/port of an already running helper |
| `PUSHPILOT_PHYSICAL_CONFIG` | Explicit private site-trial configuration; absent by default |
| `META_API_KEY` | Server-only process environment or ignored local `.env` credential |

With no optional equipment configuration, startup contacts no robot, camera or provider. A preview URL starts polling the existing helper, not a camera process or tunnel. An explicit physical configuration constructs the site-trial driver and readiness/status access; those equipment checks are distinct from movement dispatch. Startup never approves or automatically runs a physical mission. Configuration and private state load in ASGI lifespan, not module import.

Do not point a development instance at a live private configuration merely to inspect the UI. Reproduce Robot mode only through the [deployment prerequisites](../deploy/ROBOT_CONTROL.md) and [robot operations](../docs/ROBOT_OPERATIONS.md), with private runtime source verified against the public manifest. The browser never receives the hardware or Meta token.

## API boundaries

| Surface | Responsibility |
|---|---|
| `/api/health`, `/api/v1/state` | Health and revisioned simulation workspace; legacy false hardware flags do not describe the separate physical service |
| `/api/v1/map`, `/maps/validate` | Selected sanitized drawing graph and read-only replacement audit; no installation or calibration |
| `/api/v1/goals`, `/plans/live`, `/approve` | Goal interpretation, exact graph route and current-plan approval |
| `/api/v1/advance`, `/reviews`, `/signal`, `/action-reviews` | Explicitly sourced simulation action/demo/recorded behavior |
| `/api/v1/live-actions/*`, `/live-signals/*` | Bound native-image simulation review and finite wait/watch, separate from the physical worker |
| `/api/v1/scene/*`, `/live-camera/*`, `/live-evidence/*` | Recorded evidence, ephemeral preview/display lock and deliberately selected native originals |
| `/api/v1/voice/*` | Finite upload/status/candidate operations, not mission approval |
| `/api/v1/physical/status`, `/display` | Separate physical state and GET-only display DTO |
| `/api/v1/physical/start`, `/stop`, `/reset`, `/resume`, `/prepare-boundary`, `/continue-c19` | Same-origin physical controls, each with its own checked lifecycle semantics |

The [contract index](../contracts/README.md) lists exact physical fields and recovery distinctions. Physical commands use physical revision; start additionally binds workspace session, plan/revision, selected map/hash, destination and route nodes. Simulation commands keep their own UUID/revision idempotency. Scene, preview and voice operations have different binding contracts; they are not interchangeable command authority.

Live-frame planning and recorded/native action-review inference release their stores during provider work and recheck context afterward. The still-exposed **symbolic Meta goal branch** is a different path: its synchronous dispatch/provider call can block the event loop and retain the workspace lock. That reviewed limitation remains unresolved; this documentation update does not implement its repair. [Review follow-up](../docs/REVIEW_FOLLOW_UP.md) tracks it alongside Stop idempotency and request/UI concurrency. Stale/superseded results, malformed output and actual provider errors cannot fall back to a fabricated demo acceptance. A copied old receipt may have an older revision than the latest state; it must not overwrite a newer poll.

## Review and signal policy

Simulation live plans use their dedicated native-frame review/signal APIs and reject manual/recorded bypasses. Explicit demo missions retain clearly labelled injected colors/verdicts. Independent scene inspection cannot complete an action.

The physical site trial combines Native endpoint evidence with applicable MUSE car/signal review after coordinate withdrawal. One accepted stopped GREEN admits measured recontact and continuation under `single_departure`; no second color wait occurs after recontact. A new mission needs new admission. C4/C6 detail crops, C14 reference lineage, qualitative C17, configured C19 omission and C26 destination-only arrival have narrow documented scope. `clear_problem: null` is preserved as unknown, not rewritten false. See [prompts](../prompts/README.md).

Simulation watch defaults to 30 judgments, two-second intervals and a 300-second total budget; these limits do not establish the physical signal timer. Requested physical 120-second behavior needs exact deployed-configuration evidence. Native read/freshness, provider and wrist completion are separate clocks. The separate host's legal-idle Native recovery is implemented and deployed: `native_wait` blocks dispatch until two new stationary samples are available. One actual idle timeout recovered without reconnect or motion replay; non-idle/unknown-outcome limits remain. [Recovery record](../docs/HOST_NATIVE_RECOVERY.md)

## Preview and evidence

The independently running GX10 camera helper uses loopback `8084`; the web app uses `8080`. Windows development can use app `8893` with helper forward `8895`. Preview requests original JPEGs without re-encoding, maintains source/sequence/hash/receive-age metadata and uses bounded RAM. The current browser transport shares exact-original-JPEG Blob URLs with a 250 ms request target, not a measured throughput guarantee. Repeated sequences continue aging; stale display can withhold AR.

An explicit fixed four-marker lock is board-to-image display registration. Temporary occlusion retains the reference without refitting; coherent view change withholds it. Camera identity/epoch, dimensions and map changes invalidate incompatible display references. A display lock is not a physical calibration or a car pose. [Live camera](../docs/LIVE_CAMERA.md) and [Camera recovery](../docs/CAMERA_PREVIEW_RECOVERY.md) document the transport.

Workspace and physical evidence keep separate identities and source labels. Native journals, selected original images, model versions/results, scoped crop lineage and decision causes are private runtime data. Reset preserves history; failures and unknown outcomes are not relabelled. Unknown car travel, usage or cost remains unknown.

## Stop, restart and recovery

The coordinator starts no worker automatically after restart. Unknown/ambiguous movement is never automatically resent. Physical `stop` requests the supported software hold; it is not a hardware emergency stop. Physical `reset` retires an ended mission after checks; it does not perform START return. Explicit review continuation, C11 boundary preparation and session-scoped START precision binding each require exact evidence and never grant general recovery. [Robot operations](../docs/ROBOT_OPERATIONS.md) is the unified guide.

## Validate offline

```sh
python tools/dev.py check
python tools/dev.py test
```

Offline tests inject isolated state, synthetic images/audio and mock provider/equipment transports; they do not read the real `.env`, call Meta or contact a robot. The initial November 2 publication recorded 1,177 backend tests run/five skipped and 126 frontend tests. The later Native recovery checkpoint `bcac769` recorded 1,199 backend tests/five skipped and 143 frontend tests, with zero failures and a passing build. These counts establish software checks, not perception accuracy or physical repeatability. [Verification](../docs/VERIFICATION.md) preserves counts/results by source and date.

---

[Frontend](../frontend/README.md) · [Prompts](../prompts/README.md) · [Known limitations](../docs/KNOWN_LIMITATIONS.md)
