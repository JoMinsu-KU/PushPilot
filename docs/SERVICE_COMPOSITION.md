<div align="center">

# Service composition

**One application backend. Explicit provider and equipment boundaries.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Live preview](LIVE_CAMERA.md) · [Voice input](VOICE_INPUT.md) · [Development](DEVELOPMENT.md) · [Deployment](../deploy/README.md)

</div>

---

**Status: temporary-map simulation, recorded-image review and an opt-in live camera preview are implemented.** One FastAPI/Uvicorn process serves the React/TypeScript bundle and API. SQLite stores mission state/events and action-review receipts; private runtime files store recorded images, marker registrations and independent scene inspections. A replaceable graph supplies simulation routes. Action-bound recorded pairs can change the simulated mission through local gates; scene-only inspection and the memory-only live preview cannot. Voice, qualified physical observation, robot registration and physical control remain unavailable.

## Initial deployment units

The application uses a browser frontend and **one backend process containing separate modules**. A frontend development server is optional local tooling; it is not needed on GX10. Provider, observation, and action boundaries remain distinct so later integrations do not create competing mission authorities.

| Unit | Responsibility | Initial scope |
|---|---|---|
| **Tablet browser** | English workspace, typed goals, graph route, recorded-frame upload/overlay, opt-in live preview, scene inspection and replay | React/TypeScript; microphone/transcript flow planned |
| **Application backend** | Revisioned mission/scene APIs, graph routing, goal interpretation, abstract actions, private frame inspection and a separate transient preview API | FastAPI/Uvicorn, one worker; OpenCV/NumPy |
| **Standalone camera helper** | Explicit Linux camera ownership, native 1920 × 1080 MJPEG bytes and host-receive metadata over loopback | Independently started on GX10; no application deployment, persisted evidence or robot control |
| **Meta Spark API** | Goal interpretation, independent scene inspection and bound recorded-action comparison | Actual goal/scene cases and three synthetic action-review cases recorded in [Meta evidence](META_API_CHECK.md) |
| **Meta Voice Transcribe API** | Recorded speech → original-language transcript | Planned; access and quality untested |
| **Application state storage** | Workspace, ordered events and idempotent receipts; separately private frames, hashes, locked views and inspections | SQLite plus private scene files; full provider envelope receipts planned |
| **Qualified equipment adapters** | Action-bound camera observations, local signal inhibition and measured robot action receipts | Deferred physical integration; live preview does not implement these |

The backend serves compiled `frontend/dist` on the same origin as `/api`. Install `requirements.lock`, build locally using Node 24 and `npm ci && npm run build`, then run `python tools/serve.py`. GX10 needs Python 3.12+ for serving and no Node process. The browser receives application responses; it never receives the Meta credential.

### Optional preview transport

The authorized development preview uses the standalone camera helper at GX10 loopback `127.0.0.1:8084`, an SSH local forward at client `127.0.0.1:8895`, and the Windows application on port `8893` with `--live-camera-url http://127.0.0.1:8895`. The application accepts only an explicit numeric loopback HTTP origin with a port; it does not start the helper or tunnel, open `/dev/video0`, or restart POC/Rodi/camera services. The helper has its own device lock and refuses a detected existing owner without terminating it. It requests 30 fps MJPEG and copies native JPEG bytes; no end-to-end frame-rate or latency result is implied.

`backend/live_camera.py` keeps at most eight frames in RAM, separate from `SceneStore`, MUSE input, action-review receipts and mission state. Snapshot metadata includes live source, camera identity, epoch, sequence, unique frame ID, image dimensions, SHA-256 and age. Timestamps describe camera-host receive/dequeue time, not sensor exposure. Reported upstream age, transport time and subsequent elapsed time count toward the 1,500 ms preview limit; receiving the same sequence again cannot refresh it. The backend does not persist raw preview frames. Unique frame URLs may be cached privately by the browser for 30 seconds.

Live registration is an explicit fresh-frame display lock requiring all four consistent markers. Epoch, camera identity, resolution or map changes require manual relocking. Temporary occlusion retains the fixed display transform with unverified alignment; it never refits. A distributed coherent shift across at least two markers on three newly accepted frames latches `view_changed` and withholds the overlay. This is not camera-to-BASE registration, proven physical calibration, measured car pose or a valid traffic signal. The dedicated `camera_preview_connected` health flag does not change the workspace's false qualified `camera`/`robot` capabilities. See [Live camera preview](LIVE_CAMERA.md) and its [contract](../contracts/live-camera.ts).

## Backend modules

| Module | Owns | Boundary |
|---|---|---|
| **API and sessions** | Session/capture/request identities, validation, cancellation and response routing | Reject stale session/revision updates; expose only supported capabilities |
| **Speech adapter** | Finite audio upload, Meta transcription, provider errors and result normalization | Return text and provenance; never start a mission |
| **Audio normalization** | Bounded decoding/resampling and supported WAV validation before transcription | Honor audio retention/limits; lock codec dependencies when implemented |
| **Goal interpretation** | Accepted typed/transcribed text → structured symbolic goal and clarification | Interpret only the explicitly accepted revision |
| **Mission supervisor** | Approved-plan state, sequencing, stop/wait/reobserve/fault transitions and admission | Sole application authority for action transitions |
| **Observation adapters** | Source-labelled images, signal state, action state and timestamps | Preserve unknown/stale/occluded status |
| **Live preview adapter** | Existing loopback helper polling, bounded RAM cache, preview age and fixed display registration | No recorded-store persistence, provider call, mission mutation or physical admission |
| **MUSE review adapter** | Expected-versus-observed image review, prompt/schema versions and validated results | Advisory evidence subject to deterministic checks |
| **Action adapter** | Hardware-free bounded action simulation and corresponding result | Later physical implementation requires separate qualification |
| **Evidence and replay** | Immutable records and causal links among inputs, revisions, checks and decisions | Replaying evidence grants no execution authority |

The table includes implemented and future responsibilities. API validation, temporary graph routing, goal interpretation, supervision, simulation, SQLite evidence, test image registration, scene inspection, action-bound recorded review and opt-in live preview exist. Speech/audio normalization, action-bound live capture, local signal perception, qualified physical observation and complete unified provider receipts remain later work. The synchronous goal adapter serializes simulator commands. Scene inspection and action review await providers outside store locks, then reject superseded bindings. No provider path is latency-sensitive physical signal inhibition.

The speech and Spark adapters may share a server-side configuration boundary and the same Meta API key. They have different request formats, validation and acceptance tests. Success in one adapter does not establish the other's availability.

## Two input paths, one reviewed goal

| Input path | Required flow |
|---|---|
| Typed, implemented | Edit goal → explicit submission → selected demo parser or backend Spark interpreter → plan review/approval |
| Voice, planned | Push-to-talk → backend transcription → editable transcript → `Use goal` → Spark interpretation → plan review/approval |

After interpretation, both paths use the same mission contract and supervisor. Recording and transcription are not mission states that authorize robot movement. Session, capture, transcript, interpretation and plan revisions prevent a delayed recognition result from changing an already reviewed plan.

The initial input gate accepts new goals only during non-executing preparation. An active mission, including RED waiting and review, rejects new recording, text submission and goal edits. Starting a replacement goal requires explicit mission completion/termination and state reconciliation. A cancelled capture or delayed transcript cannot alter an active mission.

The first speech implementation uses a finite recording. Live streaming is a later capability under the speech adapter, with backend-managed provider authentication. Optional TTS is separate; neither streaming nor TTS blocks the first application milestone. See [voice input](VOICE_INPUT.md) for the provider distinction, cancellation policy and acceptance gates.

## Intended voice and image service behavior

The current mission uses graph-based simulated actions/signals. Its pending action can accept either a labelled demo verdict or a validated actual MUSE comparison of operator-selected recorded images. Independent scene inspection and the live display preview do not participate in those action gates. The complete future flow below also includes voice and action-bound fresh physical imagery that remain unimplemented:

1. The browser captures an utterance or accepts typed text. Voice audio goes only to the application backend.
2. The speech adapter obtains a transcript. The operator checks or edits it and explicitly accepts one revision.
3. Spark interprets the accepted goal. Unresolved intent returns to clarification; it does not become an action.
4. The operator reviews and approves the current symbolic simulation plan.
5. The supervisor admits one bounded simulated action when its applicable gates pass.
6. Source-labelled results and fresh test imagery feed local checks and MUSE review. Real model calls remain labelled independently from simulated actions or recorded imagery.
7. The supervisor records why it continues, waits, reobserves or faults. The browser renders that state and its causal evidence.

At every configured intersection, the intended physical scenario requires a verified full stop even on GREEN. RED, UNKNOWN, stale or obscured signal observations inhibit entry. The eventual local signal path and physical action qualification remain separate from cloud transcription and MUSE response latency.

## Secrets, transport and evidence

| Concern | Design requirement |
|---|---|
| **Configuration** | Development uses ignored backend-local `.env`; release configuration and secrets live outside versioned source |
| **Browser microphone origin** | Trusted target-device HTTPS and secure-context/device preflight; a plain LAN HTTP origin cannot be assumed to allow recording |
| **Audio format** | Validate/normalize to the provider's accepted mono 16-bit PCM WAV at 16 or 24 kHz; preserve bounded processing and retention |
| **Provider authentication** | Use a fixed approved TLS origin; credential-bearing HTTP must not follow redirects to another origin |
| **Streaming later** | Follow the documented provider handshake; keep credentials and handshake payloads exclusively on the server |
| **Audio** | Bound duration/size and temporary memory; discard raw audio on completion, cancellation, failure or timeout by default |
| **Evidence** | Retain minimal transcript/revision causality and provider outcomes; exclude keys, authentication payloads and environment values |
| **Isolation** | Label robot, image, pose, signal, audio and model sources separately |
| **Live preview** | Opt-in loopback transport and bounded memory; no raw-frame persistence in scene/evidence stores or silent promotion to MUSE/action evidence |
| **Restart** | Reconstruct a non-executing review state; no auto-resume from old approvals, captures, GREEN observations or pending actions |

Provider request cancellation may not stop work already accepted by the provider. The application must invalidate the corresponding capture/revision locally and prevent late completion from gaining authority.

## GX10 boundary

Read-only GX10 inspection on October 27, 2026 found ARM64 Ubuntu 24.04.4 and Python 3.12.3, with no Node/npm on the inspected PATH. The application has not been installed or activated there. The separately authorized standalone camera helper runs there for the development preview only; it is not the application backend or an activated application release. The isolated release/shared-state layout in [deployment](../deploy/README.md) remains unprovisioned. No frontend, backend, or voice work requires restarting POC web, Rodi, camera, or receiver services.

Choose HTTPS termination and a certificate trusted by the actual tablet with runtime deployment. Browser microphone capture must be tested at the actual deployed origin. TLS serving, speech-codec dependencies and microphone capture remain implementation gates; the separate camera preview does not establish them.

Final production geometry, robot coordinates, camera-to-BASE registration, qualified stop lines, live signal ROIs, and metric AR remain unqualified. The user-authorized temporary adapter supplies drawing routes and test-only recorded/live display overlays. It loads `PUSHPILOT_MAP_PATH`; map identity changes invalidate incompatible plans/references. An available live image does not establish successful registration. See [Temporary map](TEMPORARY_MAP.md) and [Live camera preview](LIVE_CAMERA.md). The glasses companion remains a labelled concept.

## Implementation gates

| Milestone | Complete when |
|---|---|
| **Select runtime — implemented** | React/Vite frontend, Python 3.12+ FastAPI/Uvicorn backend, locks and local launcher exist; host installation remains unverified |
| **Establish contracts — partial** | Revisioned workspace/scene/recorded-action DTOs and Pydantic validation exist; voice and physical receipt/observation contracts remain planned |
| **Connect typed flow — implemented** | An approved symbolic mission runs through simulation and source-labelled SQLite events without hardware |
| **Add voice** | Real finite transcription plus editing, cancellation, text fallback and latest-revision approval passes the [voice acceptance gates](VOICE_INPUT.md#acceptance-gates-before-claiming-voice-support) |
| **Inspect recorded scenes — implemented** | Explicit frame-bound MUSE request returns USABLE/REOBSERVE/UNKNOWN, visible places, car visibility and paper-signal evidence without motion authority; actual results are recorded separately in [verification](VERIFICATION.md) |
| **Connect recorded action review — implemented** | Bound MUSE before/after result changes simulation with local gates preserved; [workflow and receipts](ACTION_REVIEWS.md) |
| **Connect live display preview — implemented, opt-in** | Standalone helper, loopback forwarding and an ephemeral display API are separate from mission evidence; physical calibration and preview performance remain unqualified |
| **Connect fresh physical evidence — pending** | Trusted capture, action receipts and qualified local findings support the physical outcome; selected uploads do not establish this |
| **Verify simulation — offline tested** | RED wait, accepted GREEN, review rejection/uncertainty, provider failure and restart have offline tests; actual calls and physical quality use separate records |
| **Prepare isolated delivery — partial** | Read-only host inspection and runtime selection completed; host installation, TLS, activation and rollback checks remain |

Physical qualification opens only after the map and installation are finalized. It is not implied by completing these software milestones.

---

[← Architecture](ARCHITECTURE.md) · [Voice input →](VOICE_INPUT.md) · [Roadmap](ROADMAP.md)
