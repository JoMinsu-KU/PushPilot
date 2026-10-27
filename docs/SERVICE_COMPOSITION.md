<div align="center">

# Service composition

**One application backend. Explicit provider and equipment boundaries.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Live intelligence](LIVE_INTELLIGENCE.md) · [Voice backend](VOICE_BACKEND.md) · [Development](DEVELOPMENT.md) · [Deployment](../deploy/README.md)

</div>

---

**Status: native-frame MUSE planning/action/signal services, finite voice uploads, simulation and recorded-image review are implemented.** One FastAPI/Uvicorn process serves the React/TypeScript bundle and API. SQLite stores mission decisions, command receipts and deliberate selected native-frame evidence; private scene files retain separate uploaded recordings. Preview polling remains an eight-frame RAM path. MUSE-selected graph paths and accepted bound reviews can change only simulated mission state. Browser microphone capture, qualified physical observation, robot registration and physical control remain unavailable; actual live action/signal recognition and voice access are still unverified.

## Initial deployment units

The application uses a browser frontend and **one backend process containing separate modules**. A frontend development server is optional local tooling; it is not needed on GX10. Provider, observation, and action boundaries remain distinct so later integrations do not create competing mission authorities.

| Unit | Responsibility | Initial scope |
|---|---|---|
| **Tablet browser** | English workspace, typed goals, graph route, recorded-frame upload/overlay, opt-in live preview, scene inspection and replay | React/TypeScript; microphone/transcript flow planned |
| **Application backend** | Revisioned APIs, native-frame/graph planning, action/signal reviews, finite audio intake, simulation and private evidence | FastAPI/Uvicorn, one worker; OpenCV/NumPy; no physical robot transport |
| **Standalone camera helper** | Explicit Linux camera ownership, native 1920 × 1080 MJPEG bytes and host-receive metadata over loopback | Independently started on GX10; no application deployment, persisted evidence or robot control |
| **Meta Spark API** | Native-frame/graph route proposals, live/recorded action review and stopped-signal judgment; legacy symbolic interpretation and separate scene inspection | Provider adapter code and offline tests; actual calls keep their exact source/prompt scope in [Meta evidence](META_API_CHECK.md) |
| **Meta Voice Transcribe API** | Finite supported PCM WAV → original-language transcript candidate | Backend adapter implemented; actual account access and quality untested |
| **Application state storage** | Workspace/events, request journal and deliberate native originals; separate scene files and ephemeral transcript candidates | SQLite plus private scene files; preview/audio/transcript candidates remain bounded RAM paths; complete raw provider-envelope export remains later work |
| **Qualified equipment adapters** | Action-bound camera observations and measured robot action/stop receipts | Deferred physical integration; live preview does not implement these |

The backend serves compiled `frontend/dist` on the same origin as `/api`. Install `requirements.lock`, build locally using Node 24 and `npm ci && npm run build`, then run `python tools/serve.py`. GX10 needs Python 3.12+ for serving and no Node process. The browser receives application responses; it never receives the Meta credential.

### Optional preview transport

The authorized development preview uses the standalone camera helper at GX10 loopback `127.0.0.1:8084`, an SSH local forward at client `127.0.0.1:8895`, and the Windows application on port `8893` with `--live-camera-url http://127.0.0.1:8895`. The application accepts only an explicit numeric loopback HTTP origin with a port; it does not start the helper or tunnel, open `/dev/video0`, or restart POC/Rodi/camera services. The helper has its own device lock and refuses a detected existing owner without terminating it. It requests 30 fps MJPEG and copies native JPEG bytes; no end-to-end frame-rate or latency result is implied.

`backend/live_camera.py` keeps at most eight frames in RAM. Polling does not call MUSE, persist evidence or mutate mission state. A deliberate `live_intelligence.py` operation separately selects unchanged originals and copies only those images into the private evidence ledger before dispatch. Metadata retains camera identity, epoch, sequence, native and evidence frame IDs, dimensions, hash, registration and age. Timestamps describe camera-host receive/dequeue, not sensor exposure. Upstream/transport/elapsed age count toward the 1,500 ms selection limit; repeated sequences cannot refresh it. Preview URLs may be privately browser-cached for 30 seconds. See [Live intelligence](LIVE_INTELLIGENCE.md) for durable evidence URLs and operation bindings.

Live registration is an explicit fresh-frame display lock requiring all four consistent markers. Epoch, camera identity, resolution or map changes require manual relocking. Temporary occlusion retains the fixed display transform with unverified alignment; it never refits. A distributed coherent shift across at least two markers on three newly accepted frames latches `view_changed` and withholds the overlay. This is not camera-to-BASE registration, proven physical calibration, measured car pose or a valid traffic signal. The dedicated `camera_preview_connected` health flag does not change the workspace's false qualified `camera`/`robot` capabilities. See [Live camera preview](LIVE_CAMERA.md) and its [contract](../contracts/live-camera.ts).

## Backend modules

| Module | Owns | Boundary |
|---|---|---|
| **API and sessions** | Session/capture/request identities, validation, cancellation and response routing | Reject stale session/revision updates; expose only supported capabilities |
| **Speech adapter** | Finite audio upload, Meta transcription, provider errors and result normalization | Return text and provenance; never start a mission |
| **Audio validation** | Bounded mono PCM16 WAV validation and canonical container rebuilding, preserving original samples | No general media decoder/resampler; unsupported containers/rates reject before dispatch |
| **Goal/route interpretation** | Accepted text plus selected native image/graph → destination, complete node sequence, constraints and clarification | Compile the exact validated path; separate declared start from measured vehicle pose; keep legacy symbolic mode explicit |
| **Mission supervisor** | Approved-plan state, sequencing, stop/wait/reobserve/fault transitions and admission | Sole application authority for action transitions |
| **Observation adapters** | Source-labelled images, signal state, action state and timestamps | Preserve unknown/stale/occluded status |
| **Live preview adapter** | Existing loopback helper polling, bounded RAM cache, preview age and fixed display registration | No recorded-store persistence, provider call, mission mutation or physical admission |
| **Live intelligence service** | Explicit original-frame selection, journal reservations, frame/action/stop binding, exact graph validation and finite run/wait helpers | Revalidate after inference; reject late/superseded results; no autonomous full-mission loop or physical execution |
| **MUSE review adapter** | Bound live/recorded comparisons and RED/GREEN/UNKNOWN judgment of a new approach-specific image after a simulated stop | Local checks validate provenance/bindings; no second local color classifier and no claimed physical stop |
| **Action adapter** | Hardware-free bounded action simulation and corresponding result | Later physical implementation requires separate qualification |
| **Evidence and replay** | Immutable records and causal links among inputs, revisions, checks and decisions | Replaying evidence grants no execution authority |

The modules above now implement finite voice uploads/candidates, native-frame planning, bound action comparisons and stopped-signal judgments alongside existing recorded paths. New inference runs outside workspace locks and completion rechecks the current request, revision, map and registered camera context. `/live-actions/run` performs one action or reobservation plus its review; `/live-signals/wait` makes at most three new stopped observations. The mission stays simulated and stopped while a signal result is pending. Physical stop/capture qualification, browser audio capture, actual ASR and live action/signal evaluation, and complete raw provider-envelope/export policy remain separate gates. An in-flight color-change interruption is outside this scenario.

The speech and Spark adapters may share a server-side configuration boundary and the same Meta API key. They have different request formats, validation and acceptance tests. Success in one adapter does not establish the other's availability.

## Two input paths, one reviewed goal

| Input path | Required flow |
|---|---|
| Typed, implemented | Edit goal → explicit submission → selected native-frame/graph MUSE plan or explicit demo/symbolic path → review/approval |
| Voice, backend implemented | Supported PCM WAV upload → backend transcription candidate → explicit confirmed text/receipt → live MUSE planning → review/approval; browser recording/editing UI remains unconnected |

After interpretation, both paths use the same mission contract and supervisor. Recording and transcription are not mission states that authorize robot movement. Session, capture, transcript, interpretation and plan revisions prevent a delayed recognition result from changing an already reviewed plan.

The initial input gate accepts new goals only during non-executing preparation. An active mission, including RED waiting and review, rejects new recording, text submission and goal edits. Starting a replacement goal requires explicit mission completion/termination and state reconciliation. A cancelled capture or delayed transcript cannot alter an active mission.

The finite-recording backend is implemented with bounded in-memory validation and candidates. Live streaming is later work with backend-managed authentication. Optional TTS is separate. See [Voice backend](VOICE_BACKEND.md) for current endpoints and format limits, and [Voice input](VOICE_INPUT.md) for the remaining UI/device gates.

## Voice and image service behavior

All current action/stop receipts remain simulated. A live-backed plan requires server-bound native image review and its dedicated stopped-signal path; it rejects manual colors and demo/recorded verdicts. Separate demo missions retain their explicit inputs. Independent scene inspection and preview polling cannot advance a mission. The full interaction below includes remaining browser capture/editing and future qualified physical receipts:

1. The browser captures an utterance or accepts typed text. Voice audio goes only to the application backend.
2. The speech adapter obtains a transcript. The operator checks or edits it and explicitly accepts one revision.
3. Spark receives the confirmed goal, selected original frame and selected graph, then proposes a complete path and constraints. The backend checks the exact path. Unresolved intent or scene uncertainty requires clarification.
4. The operator reviews and approves the current symbolic simulation plan.
5. The supervisor admits one bounded simulated action when its applicable gates pass.
6. Deliberately selected original BEFORE/AFTER frames and the simulated receipt feed MUSE review. Real model results remain labelled independently from image provenance and simulated actions.
7. The supervisor records why it continues, waits, reobserves or faults. The browser renders that state and its causal evidence.

At each intersection, the simulator records a mandatory STOP even on GREEN and requires its accepted review. The implemented live signal path then selects a new native image for the configured incoming approach, adds a projected target polygon and asks MUSE for RED/GREEN/UNKNOWN. RED/UNKNOWN waits; a current valid GREEN can admit one simulated crossing after receipt, plan/junction/approach, frame/age and response checks. No second local color classifier is required. Missing reviewed target metadata rejects before dispatch; the current map intentionally has none. The physical robot stop/continuation adapter and real signal-recognition evaluation remain unimplemented/unverified respectively. See [MUSE signal gate](MUSE_SIGNAL_GATE.md).

## Secrets, transport and evidence

| Concern | Design requirement |
|---|---|
| **Configuration** | Development uses ignored backend-local `.env`; release configuration and secrets live outside versioned source |
| **Browser microphone origin** | Trusted target-device HTTPS and secure-context/device preflight; a plain LAN HTTP origin cannot be assumed to allow recording |
| **Audio format** | Accept only bounded mono PCM16 WAV at 16/24 kHz; canonicalize its container without decoding other formats or resampling |
| **Provider authentication** | Use a fixed approved TLS origin; credential-bearing HTTP must not follow redirects to another origin |
| **Streaming later** | Follow the documented provider handshake; keep credentials and handshake payloads exclusively on the server |
| **Audio** | Bound duration/size and temporary memory; discard raw audio on completion, cancellation, failure or timeout by default |
| **Evidence** | Retain minimal transcript/revision causality and provider outcomes; exclude keys, authentication payloads and environment values |
| **Isolation** | Label robot, image, pose, signal, audio and model sources separately |
| **Live preview** | Opt-in loopback transport and bounded RAM; only explicit live-intelligence operations may select/copy unchanged originals into separate private evidence |
| **Restart** | Reconstruct a non-executing review state; no auto-resume from old approvals, captures, GREEN observations or pending actions |

Provider request cancellation may not stop work already accepted by the provider. The application must invalidate the corresponding capture/revision locally and prevent late completion from gaining authority.

## GX10 boundary

Read-only GX10 inspection on October 27, 2026 found ARM64 Ubuntu 24.04.4 and Python 3.12.3, with no Node/npm on the inspected PATH. The application has not been installed or activated there. The separately authorized standalone camera helper runs there for the development preview only; it is not the application backend or an activated application release. The isolated release/shared-state layout in [deployment](../deploy/README.md) remains unprovisioned. No frontend, backend, or voice work requires restarting POC web, Rodi, camera, or receiver services.

Choose HTTPS termination and a certificate trusted by the tablet. Browser capture must be tested at that origin and encode supported WAV, or add a separately reviewed conversion implementation. TLS and microphone capture remain implementation gates; the existing preview and finite-upload backend do not establish them.

Final production geometry, robot coordinates, camera-to-BASE registration, qualified stop lines, live signal ROIs, and metric AR remain unqualified. The user-authorized temporary adapter supplies drawing routes and test-only recorded/live display overlays. It loads `PUSHPILOT_MAP_PATH`; map identity changes invalidate incompatible plans/references. An available live image does not establish successful registration. See [Temporary map](TEMPORARY_MAP.md) and [Live camera preview](LIVE_CAMERA.md). The glasses companion remains a labelled concept.

## Implementation gates

| Milestone | Complete when |
|---|---|
| **Select runtime — implemented** | React/Vite frontend, Python 3.12+ FastAPI/Uvicorn backend, locks and local launcher exist; host installation remains unverified |
| **Establish contracts — implemented software boundaries** | Workspace/scene/recorded/live DTOs, bounded map/voice request validation and transcript binding exist; measured physical receipts/observations remain pending |
| **Connect typed flow — implemented** | An approved symbolic mission runs through simulation and source-labelled SQLite events without hardware |
| **Add voice — backend implemented, device/provider pending** | Finite PCM upload, Meta adapter and bound candidates exist; browser editing/capture and actual transcription must pass [voice gates](VOICE_INPUT.md#acceptance-gates-before-claiming-voice-support) |
| **Inspect recorded scenes — implemented** | Explicit frame-bound MUSE request returns USABLE/REOBSERVE/UNKNOWN, visible places, car visibility and paper-signal evidence without motion authority; actual results are recorded separately in [verification](VERIFICATION.md) |
| **Connect recorded action review — implemented** | Bound MUSE before/after result changes simulation with local gates preserved; [workflow and receipts](ACTION_REVIEWS.md) |
| **Connect live display preview — implemented, opt-in** | Standalone helper, loopback forwarding and an ephemeral display API are separate from mission evidence; physical calibration and preview performance remain unqualified |
| **Connect native-frame planning/review — implemented** | Exact MUSE node-path validation, immutable original selections and bound action comparison exist; actual evidence is separately recorded per operation/version |
| **Connect stopped-live MUSE signal review — software implemented** | Simulated stop receipt → new configured-approach native frame → MUSE judgment → validated simulated wait/admission. Real target/recognition and physical stopping remain pending. [Boundary](MUSE_SIGNAL_GATE.md) |
| **Connect fresh physical evidence — pending** | Trusted capture, action receipts and qualified local findings support the physical outcome; selected uploads do not establish this |
| **Verify simulation — offline tested** | RED wait, accepted GREEN, review rejection/uncertainty, provider failure and restart have offline tests; actual calls and physical quality use separate records |
| **Prepare isolated delivery — partial** | Read-only host inspection and runtime selection completed; host installation, TLS, activation and rollback checks remain |

Physical qualification opens only after the map and installation are finalized. It is not implied by completing these software milestones.

---

[← Architecture](ARCHITECTURE.md) · [Voice input →](VOICE_INPUT.md) · [Roadmap](ROADMAP.md)
