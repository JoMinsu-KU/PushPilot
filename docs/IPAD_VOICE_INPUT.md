# Speak. Review the words. Create a plan.

The November 4 frontend adds finite microphone input to the existing glass goal bar. Tap the microphone to record, then tap it again to finish. The orange bars follow actual RMS amplitude with a display gain; silence stays at the baseline. Capture ends after at most 20 seconds. An indeterminate spinner represents upload and Meta transcription, not an invented completion percentage. A successful response appears as the original-language sentence in the same bar.

Tap the sentence to review or edit it, then explicitly choose **Create a plan**. This submits the current `transcript_id`, original recording identity and accepted edited words through the existing live MUSE planning path. The source remains `voice`; original transcription and confirmed text remain distinct. A transcript never approves a plan or starts a robot. Existing approval colors, completion markers, robot geometry, signal admission and execution remain unchanged.

## Input and lifecycle boundaries

AudioContext creation/resume and the microphone request begin only in the user's click handler. AudioWorklet collects/downmixes PCM; a bounded ScriptProcessor fallback is available when worklets fail. Deterministic fractional-bin averaging converts the actual device rate to mono 16 kHz PCM16 WAV, bounded to 640,044 bytes including its header. The existing backend independently validates duration, format and upload bounds before provider dispatch. This is a speech-input resampler, not a music-quality guarantee.

Permission, capture and transcription each have finite bounds. Cancel, another workspace/session/map/revision, active-input navigation, page backgrounding or unmount releases microphone resources and aborts the current request. A late permission grant is cleaned up; a late transcription cannot replace a newer capture. Once a candidate is ready, temporary navigation may retain it until explicit Discard, supersession or expiry. It remains exact-bound and requires a new explicit acceptance. No raw audio is persisted by this feature, and no request is automatically retried. Cancellation cannot guarantee that a provider has not already processed an in-flight recording.

Recordings remain separate from camera/MUSE visual observations. No camera pixels, registration, ROI, robot coordinates, speed or motion settings change. Voice is goal entry, not a voice emergency-stop implementation. No confidence score, streaming transcript or TTS is fabricated.

## Workspace and robot state

The frontend records only in eligible non-executing preparation, on Workspace with inline input or the Voice input panel. Other goal/approval actions and visual-inference tools are blocked while capture/transcription is active. The voice API also checks the physical coordinator's local state before/after transcription and at explicit voice-goal acceptance; it performs no Native IO and holds no lock across ASR. Active, held, unresolved or retained missions, including a retained COMPLETE record, require the normal explicit retirement/reset workflow first. This feature does not reset a mission automatically. General typed-goal cross-service locking remains a separate earlier limitation.

## iPad HTTPS prerequisite

`http://192.168.10.31:8080` is not a secure microphone origin on an iPad. The frontend displays a typed-input fallback rather than faking a recording. [The LAN HTTPS candidate](../deploy/ipad-https/README.md) describes a same-origin proxy at `https://192.168.10.31:8443`, without changing the existing app process or exposing a public tunnel. It requires a separately provisioned certificate and explicit device-owner trust enrollment. Do not bypass a certificate warning.

Source implementation and offline verification do not establish an active HTTPS service, trusted iPad certificate, successful real microphone capture or actual MUSE Voice access. Those device/provider checks remain outstanding until separately performed and recorded. Keys stay exclusively on the backend; the standalone UI fixture never contacts Meta or equipment.

## Verification

The frontend tests exercise actual WAV headers/sample conversion, worklet downmix/flush/limits, cleanup, permission failures, fallback, source-bound upload, cancellation/late responses, expiry, editing and explicit acceptance. SSR checks the real recording/loading/candidate/error components. Backend tests use generated PCM and mocked providers, including an active mission appearing while transcription is in flight. These checks are software evidence, not recognition accuracy or physical-route qualification.

The static deployment must include **`voice-recorder.worklet.js`** alongside the normal entry and content-hashed chunks. It is a required same-origin public asset; an index/chunk-only archive is incomplete for the primary recorder path. Self-hosted Pretendard and private city asset requirements remain unchanged.

[Voice backend](VOICE_BACKEND.md) · [Original interaction design](VOICE_INPUT.md) · [Robot operations](ROBOT_OPERATIONS.md)
