<div align="center">

# Service composition

**One application backend. Explicit provider and equipment boundaries.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Current status](CURRENT_STATUS.md) · [Development](DEVELOPMENT.md)

</div>

---

As of **November 2, 2026**, the same React/TypeScript and FastAPI application supports default equipment-free simulation and an explicitly configured Robot site trial. The original reviewed loop remains **Observe → Plan → Approve → Act → Verify**. The browser, application, camera helper, commissioning API and persistent receiver have distinct lifetimes; a frontend deployment is not a request to restart equipment services.

## Running units

| Unit | Responsibility | State and authority |
|---|---|---|
| **Tablet browser** | English From/To workspace, glass overlays, Camera/Spatial, explicit execution controls, sequence, signal and replay | Renders backend data. Spatial vehicle is an execution estimate, not car tracking. Browser microphone remains disconnected. |
| **Application backend** | One FastAPI/Uvicorn worker serves the compiled frontend and `/api`, simulation supervisor, physical coordinator, MUSE/voice adapters and evidence | Separate workspace and physical revisions. Starting the process does not authorize motion. |
| **Commissioning API** | Robot profile/command admission, status and source-bound hardware operations | Independent loopback service; the hardware token stays on the server. |
| **Rodi receiver host** | Persistent pendant protocol, exact command/sequence/session binding and Native completion checks | Independent receiver journal. Unknown outcomes block replay. |
| **Camera helper** | Owns its selected device and supplies native JPEG bytes/receive metadata over loopback | Independent device lock and process; no mission authority or automatic application-owned restart. |
| **Meta Spark API** | Selected-image/graph interpretation, scene/action/arrival review and stopped signal observations | Structured judgment, not TCP targets or scripts. Actual failures remain failures. |
| **Meta Voice adapter** | Finite supported PCM WAV to original-language transcript candidate | Backend implemented; ASR access, device capture and complete browser interaction unverified. |

GX10 serves compiled frontend assets without a Node runtime. The deployed application uses port `8080`, the independent preview helper uses loopback `8084`, and the commissioning API uses loopback `8897`; the Rodi listener uses `19507`. These are installation references, not instructions to start a second copy. Windows development may use application `8893` and a helper forward `8895`. See [deployment](../deploy/README.md) for activation and private prerequisites.

## Modules inside the web application

| Module | Owns | Boundary |
|---|---|---|
| `core.py`, workspace API/store | Approved graph simulation, actions, stops, wait/review/recovery and command idempotency | Abstract receipts remain simulated even when MUSE sees real frames. |
| `maps.py`, `planning_provider.py` | Selected directed graph, map-driven labels, v3 MUSE route proposal, departure/turn/via/avoid validation and drawing geometry | No graph-to-TCP conversion or model-generated coordinates. |
| `live_camera.py` | Existing helper polling, eight-frame RAM cache and fixed display registration | Preview alone never calls MUSE or advances a mission. |
| `live_intelligence.py` and live providers | Explicit original selections, frame/action/stop bindings, durable inference reservations and simulation run/wait/watch | Does not own the physical worker. Simulated signal watch is a separate service. |
| `physical_mission.py`, `physical_api.py` | Configured site-trial lifecycle, same-origin start/stop/reset/resume, independent state/revision and telemetry | No worker auto-resume on restart. Reset does not move the robot. |
| `robot_control/site_trial_driver.py` and mission modules | Taught B/C/D recipes, source/profile checks, coordinate contact/release/recontact, Native receipts and applicable MUSE review | Private geometry required. Active mode is delivery_only; numeric alignment/parking are deferred. |
| `physical_display.py`, `physical_display_api.py` | GET-only cached physical presentation from actual journals/receipts | No command path or motion authority; missing data remains unavailable. |
| `scene.py`, `action_review.py` | Separate recorded-scene inspection and selected recorded-pair simulation review | Recorded images do not establish fresh physical capture. |
| `voice.py`, `voice_api.py` | Bounded PCM validation, finite transcription and session/map-bound candidates | No automatic goal submission or approval; browser capture/editor pending. |

The physical start command binds the current live MUSE plan in workspace **PLAN_READY**, its session/plan revision, destination, route nodes, map identity/hash and **physical** revision. In Robot mode, **Start robot mission** is the explicit approval/start action; do not call the simulation `/approve` first. The private driver chooses the corresponding taught recipe. The graph is the visible intent/route interface; the BASE packet is the execution source. Replacing the print or changing the drawing cannot silently relocate a robot path.

## State and evidence ownership

| Store | Retains | Kept separate from |
|---|---|---|
| Workspace SQLite | Goal/plan, simulation state/events, exact request-ID receipts | Physical command authority |
| Selected-native ledger | Deliberately selected unchanged images, hashes, bindings and inference outcomes | Transient preview polling |
| Recorded-scene files | Uploaded original media, marker reference and independent inspection | Trusted post-action physical chronology |
| Physical coordinator/driver journals | Mission, issued/completed receipts, signal admission, actual reviews, errors and recovery causes | Display estimates and demo values |
| Receiver journals | Controller session/sequence/profile, command transmission and Native evidence | MUSE claims about vehicle motion |
| Optional physical display cache | Source-labelled phase, confirmed progress and receipt-driven Spatial estimate | Control/status endpoint reliability |
| Voice candidate RAM | At most 32 candidates for 30 minutes, no retained audio | Durable mission approval |

Raw images, private controller runtime, profiles, route coordinates, operational state and secrets stay outside Git. Reset preserves historical evidence. Replaying an old receipt for inspection cannot dispatch movement, and an unknown command cannot be resent automatically.

## Signal and observation lifecycle

The current physical northbound approach withdraws to the far-RIGHT stopped observation pose. MUSE judges the two-face paper signal with a black cover on a cable tie. Two distinct source images and the stopped-car context support the judgment; narrow exposed rims/small tremor may be accepted when coverage is otherwise clear, while a substantial mask shift or broad exposure remains UNKNOWN/WAIT.

The configured `single_departure` sequence is **accepted stopped GREEN → measured recontact → continuation**, with no second color wait. A new mission needs new admission. Contact and recontact remain coordinate based. C4/C6 detail crops, C14 wider reference lineage, qualitative C17, explicit C19 omission and C26 destination-only arrival have documented scope; they do not turn every uncertainty into success. See [prompts](../prompts/README.md), [single signal departure](SINGLE_SIGNAL_DEPARTURE.md) and [C endpoint](C26_DELIVERY_ENDPOINT.md).

The simulation `/live-signals/watch` defaults to a 300-second total budget and is unrelated to the requested physical 120-second wait. Provider, Native freshness, receiver read and wrist-completion clocks also differ. The separate host's [legal-idle Native recovery](HOST_NATIVE_RECOVERY.md) is implemented and deployed: permitted IDLE exchanges retain the session while `native_wait` blocks dispatch and two new stationary measurements are acquired. One actual idle timeout recovered without reconnect or motion/profile dispatch. Non-idle failures and actual disconnect/PLAY preparation retain their [operational boundaries](ROBOT_OPERATIONS.md).

## Two inputs, one reviewed goal

Typed input is connected to planning and approval. Finite voice upload/transcription is implemented in the same backend, using the server-held Meta credential. A transcript candidate must be explicitly accepted and bound to the current workspace/map before MUSE planning. Browser push-to-talk, supported PCM encoding, transcript editing and trusted tablet HTTPS remain acceptance work. Realtime ASR and TTS are deferred; a second speech server is not required for the finite backend.

New goals belong to non-executing preparation. Simulation APIs reject replacement outside their preparation states, and the tablet disables goal editing while a Robot mission is active, including signal waiting and review. The workspace/voice APIs currently validate workspace state rather than independently locking against the separate physical coordinator; Robot UI protection is not a cross-service API lock. Late results still require the original workspace/session/map binding and cannot grant plan approval. See [Voice input](VOICE_INPUT.md) and [Voice backend](VOICE_BACKEND.md).

## Verification and delivery

The public source includes offline tests and dated physical/provider summaries, not private operating prerequisites. Initial November 2 source `7aa7753` recorded 1,177 backend tests/five skips and 126 frontend tests; later recovery source `bcac769` recorded 1,199 backend tests/five skips and 143 frontend tests, with zero failures and a passing build. These are software checks; actual arrival records and incomplete repeatability qualification retain separate labels in [verification](VERIFICATION.md) and the [evidence index](evidence/README.md).

Build locally, package committed source plus matching compiled assets, verify an isolated release and deliberately activate it. Do not restore old profiles, mailboxes or pending actions during deployment. [Current status](CURRENT_STATUS.md) and [known limitations](KNOWN_LIMITATIONS.md) identify remaining work.

---

[Architecture](ARCHITECTURE.md) · [Robot operations](ROBOT_OPERATIONS.md) · [Development](DEVELOPMENT.md)
