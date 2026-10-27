<div align="center">

# Service composition

**One application backend. Explicit provider and equipment boundaries.**

[Documentation](README.md) · [Architecture](ARCHITECTURE.md) · [Voice input](VOICE_INPUT.md) · [Development](DEVELOPMENT.md) · [Deployment](../deploy/README.md)

</div>

---

**Status: proposed initial application composition.** The repository contains bootstrap/release tooling and an opt-in Spark connection checker. The tablet application, backend runtime, voice adapter and mission services are not implemented. Runtime frameworks, dependencies and startup commands remain implementation decisions.

## Initial deployment units

Start with a browser frontend and **one backend process containing separate modules**. This keeps the first demo deployable without creating a separate speech server or a fleet of internal services. Module boundaries must still be explicit so provider, observation and action adapters can be replaced independently.

| Unit | Responsibility | Initial scope |
|---|---|---|
| **Tablet browser** | English operator interface, typed goals, push-to-talk capture, editable transcript, plan approval, evidence and replay | Planned |
| **Application backend** | API, session identity, transcription orchestration, goal interpretation, supervisor, simulation and evidence | Planned, one process initially |
| **Meta Spark API** | Goal understanding and image-grounded MUSE review after each bounded action | Text connection checked separately; application/image integration planned |
| **Meta Voice Transcribe API** | Recorded speech → original-language transcript | Planned; access and quality untested |
| **Application state storage** | Immutable causal records, media references and replay inputs | Planned; engine and persistence format unselected |
| **Qualified equipment adapters** | Later camera observations, local signal inhibition and measured robot action receipts | Deferred physical integration |

Frontend asset hosting may use the backend or a separate static host once the runtime is selected. That hosting choice does not require a second mission authority. The browser receives application responses; it never receives the Meta credential.

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

The speech and Spark adapters may share a server-side configuration boundary and the same Meta API key. They have different request formats, validation and acceptance tests. Success in one adapter does not establish the other's availability.

## Two input paths, one reviewed goal

| Input path | Required flow |
|---|---|
| Typed | Edit goal → explicit submission → Spark interpretation → plan review/approval |
| Voice | Push-to-talk → backend transcription → editable transcript → `Use goal` → Spark interpretation → plan review/approval |

After interpretation, both paths use the same mission contract and supervisor. Recording and transcription are not mission states that authorize robot movement. Session, capture, transcript, interpretation and plan revisions prevent a delayed recognition result from changing an already reviewed plan.

The initial input gate accepts new goals only during non-executing preparation. An active mission, including RED waiting and review, rejects new recording, text submission and goal edits. Starting a replacement goal requires explicit mission completion/termination and state reconciliation. A cancelled capture or delayed transcript cannot alter an active mission.

The first speech implementation uses a finite recording. Live streaming is a later capability under the speech adapter, with backend-managed provider authentication. Optional TTS is separate; neither streaming nor TTS blocks the first application milestone. See [voice input](VOICE_INPUT.md) for the provider distinction, cancellation policy and acceptance gates.

## End-to-end service behavior

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

GX10 is the intended later runtime host. The isolated release/shared-state layout in [deployment](../deploy/README.md) remains a proposal, not a provisioned application environment. No voice work requires restarting POC web, Rodi, camera or receiver services.

Choose HTTPS termination and a certificate trusted by the actual tablet with runtime deployment. Browser microphone capture must be tested at the actual deployed origin. TLS serving, codec dependencies and device capture are implementation gates, not configured capabilities today.

Final road geometry, installed coordinates, camera registration, stop lines, signal ROIs and spatial AR are on hold. The initial application must run with symbolic locations, test imagery and a visibly simulated action adapter. A future glasses companion remains a labelled concept rather than a deployed client.

## Implementation gates

| Milestone | Complete when |
|---|---|
| **Select runtime** | Frameworks, manifests, locks, startup/configuration and verification commands are committed |
| **Establish contracts** | Sessions, captures, transcript revisions, goals, approvals, actions and reviews have validated causal identities |
| **Connect typed flow** | An approved symbolic mission runs through simulation and immutable evidence without hardware |
| **Add voice** | Real finite transcription plus editing, cancellation, text fallback and latest-revision approval passes the [voice acceptance gates](VOICE_INPUT.md#acceptance-gates-before-claiming-voice-support) |
| **Connect image review** | Real MUSE review uses stated test imagery and validates structured responses, timeouts and uncertainty |
| **Verify integrated demo** | RED wait, accepted GREEN, rejected review, reobservation, provider failure and restart produce traceable safe software transitions |
| **Prepare isolated delivery** | Host/runtime inspection, configuration and rollback checks support the first application deployment |

Physical qualification opens only after the map and installation are finalized. It is not implied by completing these software milestones.

---

[← Architecture](ARCHITECTURE.md) · [Voice input →](VOICE_INPUT.md) · [Roadmap](ROADMAP.md)
