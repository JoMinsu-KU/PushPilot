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

`http://192.168.10.31:8080` is not a secure microphone origin on an iPad. The frontend displays a typed-input fallback rather than faking a recording. [The LAN HTTPS example](../deploy/ipad-https/README.md) describes a same-origin proxy at `https://192.168.10.31:8443`, without exposing a public tunnel. Device-owner certificate installation and full SSL trust remain necessary for each new device. Do not bypass a certificate warning.

Source implementation and offline verification alone do not establish successful real microphone capture or actual MUSE Voice access. The separate operational/device HTTPS checks below passed; microphone/provider checks remain outstanding. Keys stay exclusively on the backend; the standalone UI fixture never contacts Meta or equipment.

## Verification

The frontend tests exercise actual WAV headers/sample conversion, worklet downmix/flush/limits, cleanup, permission failures, fallback, source-bound upload, cancellation/late responses, expiry, editing and explicit acceptance. SSR checks the real recording/loading/candidate/error components. Backend tests use generated PCM and mocked providers, including an active mission appearing while transcription is in flight. These checks are software evidence, not recognition accuracy or physical-route qualification.

The static deployment must include **`voice-recorder.worklet.js`** alongside the normal entry and content-hashed chunks. It is a required same-origin public asset; an index/chunk-only archive is incomplete for the primary recorder path. Self-hosted Pretendard and private city asset requirements remain unchanged.

## Operational activation · November 4, 2026

Operational session (7) activated source `d293dfd3a1aad647199032c00fae46350d20a955` as web release `20261104-ipad-voice-d293dfd`. Only the voice-specific import/check in `backend/app.py`, updated `backend/voice_api.py`, new `backend/goal_input_guard.py` and six frontend payload files were applied over the existing operational release. Its extra commissioning modules, private model/font assets, configuration and persisted evidence were retained. This source publication excludes private runtime artifacts and certificate material.

The owner-authorized LAN HTTPS proxy uses the official Caddy 2.11.8 ARM64 artifact with published checksum verification. Both example-unit binary paths were adapted to the private installed binary. Exact-version Caddy adaptation and user-unit verification passed. The only added listener is the designated LAN TCP 8443 address; no public tunnel, admin listener, HTTP redirect listener or UDP listener was added. Only the public root certificate was transferred through authenticated SCP. CA keys remain server-private.

Certificate-validating HTTPS requests returned 200 with the expected MIME type and SHA-256 for all six frontend payload files, including the top-level worklet. Entry hash: `a3e9a0f9b9d303a3d5c4c03d294d81b62f30aa121f670173395104ae76e60d7a`; worklet hash: `fee9387b845d224afd1abbc820674ea757e1c8e19f70a303f27f34fbd78c5fd4`. The operational voice suite passed 35 tests; five trusted-loopback forwarded scheme/Host same-origin cases passed offline. Existing Origin checks were retained.

The owner explicitly confirmed certificate installation, full SSL trust and warning-free access to the HTTPS application on the actual iPad. This is device TLS evidence, not a recording or provider-access test. Actual iPad permission, capture/stop/cancel, audio quality, MUSE transcription and spoken-goal acceptance remain unverified.

The previous physical mission remains COMPLETE 31/31 with the same mission identity and status fields. The application restart added exactly one normal SERVICE_OPENED revision with `automatic_resume: false`; private motion configuration hashes and robot API/RODI process identities were preserved. An empty voice POST returned `409 VOICE_PHYSICAL_MISSION_ACTIVE` before provider dispatch, with workspace/physical state unchanged. No motion, automatic reset/retirement or camera activation was performed. Original camera-JPEG byte comparison was not performed because the camera helper was off.

The visible **Plan the next mission** / **Create a new robot plan** workspace actions do not retire the separate retained physical mission. Normal physical retirement requires independently verified START under the established operational workflow. Do not suggest those workspace buttons bypass this prerequisite or automatically start hardware to enable a microphone test.

The proxy currently runs in the retained login session with an untimed connection anchor. Boot/linger/automatic-start policies were not changed; continued availability after that login session ends or the host reboots is not established. The reusable files in `deploy/ipad-https/` remain examples, not a self-activating deployment script. Operator-private activation records retain exact runtime identities and checks separately from public source.

[Voice backend](VOICE_BACKEND.md) · [Original interaction design](VOICE_INPUT.md) · [Robot operations](ROBOT_OPERATIONS.md)
