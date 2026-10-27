<div align="center">

# Service composition

**One application backend. Explicit provider and equipment boundaries.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Voice input](VOICE_INPUT.md) · [Development](DEVELOPMENT.md) · [Deployment](../deploy/README.md)

</div>

---

**Status: temporary-map simulation and recorded-scene inspection are implemented.** One FastAPI/Uvicorn process serves the React/TypeScript bundle and API. SQLite stores mission state/events; private runtime files store frames, marker registrations, and MUSE scene inspections. A replaceable temporary graph supplies simulation routes. Scene inspection does not advance actions or replace demo action reviews. Voice, live camera capture, robot registration, and physical control remain unavailable.

## Initial deployment units

The application uses a browser frontend and **one backend process containing separate modules**. A frontend development server is optional local tooling; it is not needed on GX10. Provider, observation, and action boundaries remain distinct so later integrations do not create competing mission authorities.

| Unit | Responsibility | Initial scope |
|---|---|---|
| **Tablet browser** | English workspace, typed goals, graph route, recorded-frame upload/overlay, scene inspection and replay | React/TypeScript; microphone/transcript flow planned |
| **Application backend** | Revisioned mission/scene APIs, graph routing, goal interpretation, abstract actions and private frame inspection | FastAPI/Uvicorn, one worker; OpenCV/NumPy |
| **Meta Spark API** | Goal interpretation and independent recorded-scene inspection | Goal request verified; scene adapter implemented; integrated per-action image review remains unimplemented |
| **Meta Voice Transcribe API** | Recorded speech → original-language transcript | Planned; access and quality untested |
| **Application state storage** | Workspace, ordered events and idempotent receipts; separately private frames, hashes, locked views and inspections | SQLite plus private scene files; full provider envelope receipts planned |
| **Qualified equipment adapters** | Camera observations, local signal inhibition and measured robot action receipts | Deferred physical integration |

The backend serves compiled `frontend/dist` on the same origin as `/api`. Install `requirements.lock`, build locally using Node 24 and `npm ci && npm run build`, then run `python tools/serve.py`. GX10 needs Python 3.12+ for serving and no Node process. The browser receives application responses; it never receives the Meta credential.

## Backend modules

| Module | Owns | Boundary |
|---|---|---|
| **API and sessions** | Session/capture/request identities, validation, cancellation and response routing | Reject stale session/revision updates; expose only supported capabilities |
| **Speech adapter** | Finite audio upload, Meta transcription, provider errors and result normalization | Return text and provenance; never start a mission |
| **Audio normalization** | Bounded decoding/resampling and supported WAV validation before transcription | Honor audio retention/limits; lock codec dependencies when implemented |
| **Goal interpretation** | Accepted typed/transcribed text → structured symbolic goal and clarification | Interpret only the explicitly accepted revision |
| **Mission supervisor** | Approved-plan state, sequencing, stop/wait/reobserve/fault transitions and admission | Sole application authority for action transitions |
| **Observation adapters** | Source-labelled images, signal state, action state and timestamps | Preserve unknown/stale/occluded status |
| **MUSE review adapter** | Expected-versus-observed image review, prompt/schema versions and validated results | Advisory evidence subject to deterministic checks |
| **Action adapter** | Hardware-free bounded action simulation and corresponding result | Later physical implementation requires separate qualification |
| **Evidence and replay** | Immutable records and causal links among inputs, revisions, checks and decisions | Replaying evidence grants no execution authority |

The table describes implemented and future responsibilities. Mission/scene API validation, temporary graph routing, goal interpretation, supervision, simulated actions, SQLite events, recorded-frame marker registration, and MUSE scene inspection exist. Speech/audio normalization, live camera/local signal perception, per-action image review, and complete provider receipts remain future work. The synchronous goal adapter serializes simulator commands. Scene inspection awaits the provider outside its store lock and rejects a result if its frame/revision was superseded. Neither path is latency-sensitive physical signal inhibition.

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

The current mission uses graph-based simulated actions/signals and manually injected demo action reviews. A separate recorded-image inspection path is implemented, but it does not participate in those action gates. The following complete mission flow includes voice and per-action image services that remain future work:

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
| **Restart** | Reconstruct a non-executing review state; no auto-resume from old approvals, captures, GREEN observations or pending actions |

Provider request cancellation may not stop work already accepted by the provider. The application must invalidate the corresponding capture/revision locally and prevent late completion from gaining authority.

## GX10 boundary

Read-only GX10 inspection on October 27, 2026 found ARM64 Ubuntu 24.04.4 and Python 3.12.3, with no Node/npm on the inspected PATH. The application has not been installed or activated there. The isolated release/shared-state layout in [deployment](../deploy/README.md) remains unprovisioned. No frontend, backend, or voice work requires restarting POC web, Rodi, camera, or receiver services.

Choose HTTPS termination and a certificate trusted by the actual tablet with runtime deployment. Browser microphone capture must be tested at the actual deployed origin. TLS serving, codec dependencies and device capture are implementation gates, not configured capabilities today.

Final production geometry, robot coordinates, camera-to-BASE registration, qualified stop lines, live signal ROIs, and metric AR remain unqualified. The user-authorized temporary adapter supplies drawing routes and recorded-image board overlays only. It loads `PUSHPILOT_MAP_PATH`; geometry-hash changes invalidate incompatible plans/references. See [Temporary map](TEMPORARY_MAP.md). The glasses companion remains a labelled concept.

## Implementation gates

| Milestone | Complete when |
|---|---|
| **Select runtime — implemented** | React/Vite frontend, Python 3.12+ FastAPI/Uvicorn backend, locks and local launcher exist; host installation remains unverified |
| **Establish contracts — partial** | Revisioned goal/plan/action/demo-review DTOs and Pydantic request validation exist; voice/image bundle contracts remain planned |
| **Connect typed flow — implemented** | An approved symbolic mission runs through simulation and source-labelled SQLite events without hardware |
| **Add voice** | Real finite transcription plus editing, cancellation, text fallback and latest-revision approval passes the [voice acceptance gates](VOICE_INPUT.md#acceptance-gates-before-claiming-voice-support) |
| **Inspect recorded scenes — implemented** | Explicit frame-bound MUSE request returns USABLE/REOBSERVE/UNKNOWN, visible places, car visibility and paper-signal evidence without motion authority; actual results are recorded separately in [verification](VERIFICATION.md) |
| **Connect action image review — pending** | Fresh action-bound MUSE review and independent local findings replace neither one another nor the required physical receipts |
| **Verify simulation — offline tested** | RED wait, accepted GREEN, rejected demo review, reobservation, provider failure and restart have meaningful offline tests; actual image/voice integration is separate |
| **Prepare isolated delivery — partial** | Read-only host inspection and runtime selection completed; host installation, TLS, activation and rollback checks remain |

Physical qualification opens only after the map and installation are finalized. It is not implied by completing these software milestones.

---

[← Architecture](ARCHITECTURE.md) · [Voice input →](VOICE_INPUT.md) · [Roadmap](ROADMAP.md)
