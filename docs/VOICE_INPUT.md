<div align="center">

# Voice input

**Say the goal. Check the words. Review the plan.**

[Documentation](README.md) · [Voice backend](VOICE_BACKEND.md) · [Live intelligence](LIVE_INTELLIGENCE.md) · [Services](SERVICE_COMPOSITION.md)

</div>

---

**Status: the finite-upload transcription backend is implemented; browser microphone capture remains disconnected.** The backend accepts bounded mono PCM WAV, calls the Meta Voice adapter and returns an original-language, workspace/map-bound transcript candidate for explicit acceptance. It has offline tests, not actual-provider or microphone verification. The workspace's microphone entry still opens **Not connected** guidance with a disabled **Hold to speak** control and typed fallback; it requests no microphone permission and sends no recording. Browser capture, transcript editing and the complete spoken-goal interaction still need implementation and device checks. Historical Spark connection checks do not establish voice access or recognition quality. See the [exact upload/candidate contract](VOICE_BACKEND.md).

## Visible goal and voice entry

A compact glass **Your goal** bar sits beneath the selected map title, above camera controls. Its text is the current accepted `goal.text`, independently labelled **Typed** or **Voice** from `goal.source`; an unsent editor draft does not replace it. Selecting the text opens the complete original request through bounded pages. The current plan can be inspected during execution while goal editing remains restricted to preparation.

The microphone opens **Voice input**, explaining the future hold → speak → review-text → create-plan sequence. Its capture button remains disabled and explicitly disconnected. **Type a goal** preserves the existing text/MUSE workflow and explicit plan approval. This interface is not a connected speech recognizer or an invented transcript.

## The first voice experience

[![Planned voice input: push-to-talk recording passes through the backend and dedicated Meta transcription adapter; the operator checks and edits the transcript before accepting a goal; Spark interpretation and explicit tablet plan approval precede any admitted action.](assets/voice-input-flow.png)](assets/voice-input-flow.png)

*Proposed interaction, not a connected microphone or an executed mission. Select the image for the full-size view.*

The planned capture implementation uses a **finite push-to-talk recording**. The operator records a goal, receives a transcript, corrects it when necessary and chooses **Use goal**. Only that explicit action submits the accepted text for MUSE goal interpretation. The resulting plan still needs explicit tablet approval before the mission supervisor may admit an action.

| Stage | Operator sees | Application responsibility |
|---|---|---|
| **Record** | `Record goal`, recording state and `Stop recording` | Request microphone permission, bound recording duration/size and allow cancellation |
| **Transcribe** | `Transcribing…` and a cancel action | Upload the finite recording through the backend; retain capture identity |
| **Check words** | Editable transcript, `Record again` and `Use goal` | Preserve the original transcription separately from operator edits |
| **Interpret** | Structured goal and any clarification needed | Submit only the explicitly accepted transcript revision to Spark |
| **Review plan** | Proposed behavior, evidence and `Approve simulation` | Bind approval to the current mission interpretation and plan revision |
| **Act and verify** | Current action, checks and review outcome | Apply the same deterministic gates used for typed goals |

Typing remains available whenever goal entry is allowed. A microphone denial, unavailable audio device or provider failure must leave a useful text-entry path in that goal-entry state.

### Input eligibility and device setup

The initial application accepts new typed or spoken goals only in a non-executing preparation state. Disable recording, transcript submission and goal edits while a mission is active, including RED waiting, observation review and crossing. A replacement goal requires an explicitly completed or terminated mission and non-executing state reconciliation. Cancelling a voice capture does not terminate or stop a mission.

Before recording, check `isSecureContext` and microphone API/device availability. The actual tablet deployment needs HTTPS trusted by that device; a plain HTTP LAN address is not the local-development `localhost` exception. Permission denial, an unavailable device or an unsuitable origin should show an actionable English status and preserve eligible text entry. See [browser microphone requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

### Language and display

All interface controls, accessibility labels, errors and developer-authored text are English. The operator may speak Korean or English. The raw utterance and returned transcript are user data: preserve their original language and do not label an English rewrite as the original transcript.

An accepted Korean transcript may be interpreted into the application's English goal summary and symbolic destination. Show that interpretation as a separate result for review. Ambiguous locations require clarification; no map coordinates are inferred from speech.

## Provider boundary

The implemented backend adapter targets **Meta Muse Voice Transcribe**, model `muse-voice-transcribe-1.0`, whose documentation lists Korean and English. This is not a claim of verified account access or language accuracy. The finite-recording path uses the documented authenticated HTTP API; streaming remains deferred. The dedicated voice model is preferred over Spark 1.3 audio understanding, whose documented support has limitations. See [Meta speech-to-text](https://dev.meta.ai/docs/speech-to-text) and [Spark audio limitations](https://dev.meta.ai/docs/video-understanding).

| Boundary | Current implementation / remaining UI | Later option |
|---|---|---|
| Browser → application | Bounded upload endpoint implemented; microphone capture/encoder unconnected | Browser audio chunks to the application |
| Application → Meta | `POST /v1/asr/transcribe`, Bearer authentication | `/v1/asr/realtime` WebSocket with the documented authentication handshake |
| Accepted text → goal understanding | Explicit transcript receipt plus confirmed text through native-frame/graph MUSE planning | Same approval boundary |

The `/v1/asr/...` paths in this table are **provider paths**. PushPilot implements `POST /api/v1/voice/transcriptions` and separate candidate/status endpoints described in [Voice backend](VOICE_BACKEND.md). The future Meta real-time WebSocket uses its documented handshake authentication; an `Authorization` header is ignored for that path. Server credentials must never be placed in the browser or proxied to it as a usable provider token.

The implemented path requires RIFF/WAVE containing mono 16-bit integer PCM at 16 or 24 kHz, 0.2–20 seconds and at most 1 MiB. It validates the container/sample bounds and rebuilds the WAV header without ancillary metadata while preserving the PCM samples. It does not decode WebM/Opus, MP4/AAC, MP3, stereo or other rates and does not resample. The future browser must encode supported PCM WAV, or a separately reviewed pinned converter must be added. Unsupported formats fail before dispatch. See [file transcription requirements](https://dev.meta.ai/docs/speech-to-text).

Use the existing backend-only `META_API_KEY` from the ignored repository-local `.env` during development. Do not expose it through frontend build variables, browser storage, URLs, transcripts, prompts, logs or replay. A real transcription call must separately establish that the key has voice access; a successful Spark call is insufficient.

Configure a fixed approved provider origin and require TLS. Credential-bearing HTTP requests must not follow redirects to another origin. Apply equivalent origin and connection checks before a future WebSocket handshake, and never log its credential payload.

### Recognition is not confidence or speech output

The documented transcription API does not provide ASR confidence scores. Do not display an invented percentage or substitute Spark's opinion for recognizer confidence. An editable transcript and explicit acceptance are the first safeguards against recognition mistakes.

Text-to-speech is a separate, optional capability. It is not provided by Muse Voice Transcribe. The first demo does not require another voice vendor, key or standalone speech service; optional browser speech synthesis needs device-specific validation before inclusion.

## Implemented backend and remaining interaction records

The implemented [backend contract](VOICE_BACKEND.md) uses finite upload `capture_id`, a provider `request_id`, generated `transcript_id`, source/format metadata and the exact initiating workspace/session/map binding. Candidates expire after 30 minutes, are bounded to 32 in RAM and contain no retained audio. A confirmed live goal validates `transcript_id` and preserves the original transcript separately from accepted edited text; it does not approve the plan.

The table below retains the broader interaction design. A separate transcript-revision editor and full browser confirmation UI are still future work; names such as `transcript_revision_id` are not claims of implemented fields.

| Record | Required relationship |
|---|---|
| Capture | `session_id`, `capture_id`, capture time, audio format, duration/size, microphone or fixture source |
| Transcription request/result | Capture identity, `request_id`, provider/model, timing, outcome and returned text |
| Transcript revision | `transcript_revision_id`, original result reference, edited text and revision cause |
| Goal acceptance | Exact transcript revision, explicit operator action and idempotency identity |
| Mission interpretation | Accepted goal reference, interpretation revision and clarification outcome |
| Plan approval | Current mission/plan revision and explicit operator approval event |

Audio source and provider source are independent. **A real Meta request on a recorded fixture proves provider behavior on that recording; it does not prove live microphone capture or physical robot execution.** Mock transcriptions remain visibly marked as simulated.

### Cancellation and changing intent

- Cancelling a recording or transcription invalidates that capture for acceptance. A late result may be retained as a cancelled diagnostic outcome, but must not overwrite the active transcript or create a mission.
- A newer capture or transcript revision supersedes older candidates. Results arriving out of order must be matched by identity before display or use.
- `Record again` creates a new capture, not a duplicate mission. Repeated delivery of one `Use goal` event must not create additional missions.
- In eligible non-executing preparation, editing an accepted goal creates a new interpretation/plan revision and invalidates approval of the previous revision. Active missions reject this operation.
- A late transcript cannot modify an active mission or regain authority after mission completion, cancellation or restart.
- A transcription retry is not permission to retry a physical action. Voice acceptance never supplies execution authority by itself.

## Safety and retention

Voice is an input modality for goals. A recognized word such as “stop” must not be presented as a physical emergency stop. Cloud transcription and review have variable latency; the hardware stop path is separately qualified. UI cancellation or HOLD must describe its actual software effect.

Keep raw audio only in bounded temporary memory by default and discard it after success, failure, cancellation or timeout. Enforce upload and provider time limits. Persistent raw audio retention requires a separate explicit design decision; this plan does not enable it.

Retain the minimum causal evidence needed to explain the accepted goal: capture metadata, original transcription, operator revision, provider/model and outcome, accepted revision and resulting interpretation. Avoid indiscriminate payload logging. Never retain authentication headers, environment values or WebSocket credential payloads in evidence.

## Acceptance gates before claiming voice support

| Gate | Required evidence |
|---|---|
| Device capture | Actual target browser/device permission, record, stop and cancel behavior; unavailable microphone leaves typed entry usable |
| Browser origin and audio | Trusted target-device HTTPS, secure-context preflight and verified normalization to the provider's accepted WAV format |
| Real provider | Opt-in finite-recording request to the documented model with no secret exposure; failure and timeout behavior retained |
| Language | Korean and English examples, original transcript preservation and operator correction before acceptance |
| Causality | Cancelled, late and reordered results cannot replace the active revision or create duplicate missions |
| Approval | No mission submission before `Use goal`; no action admission before approval of the latest plan |
| Active mission | Typed and spoken goal creation/editing are rejected during execution, RED waiting and review; late results cannot change the active mission |
| Sources | Fixture, live capture, simulated result and real provider call remain distinguishable |
| Retention | Audio expires under every terminal outcome; evidence contains no keys or credential payloads |
| End-to-end | Spoken goal → editable transcript → interpretation → approved simulated mission, with traceable revisions |

Streaming transcription and optional spoken feedback follow only after this finite-recording path passes. None of these gates proves map registration, signal perception or physical pushing.

---

[← Documentation](README.md) · [Service composition →](SERVICE_COMPOSITION.md)
