# Voice backend

**Implemented for finite uploads; actual microphone and Meta voice access are not verified.** This service returns an editable transcript candidate. It does not submit a goal, generate a plan, approve a plan or control a robot. Browser capture remains disconnected until its separate implementation and device checks pass.

The backend uses the existing server-only `META_API_KEY`. Do not add a frontend environment variable or another vendor key for this adapter. A successful Spark image or text call does not establish permission to use Muse Voice Transcribe.

## Application endpoints

| Endpoint | Behavior |
|---|---|
| `GET /api/v1/voice` | Configuration, supported audio and bounds; never claims microphone connection or verified provider access |
| `POST /api/v1/voice/transcriptions` | Parse a bounded recording in RAM, validate it, request Meta transcription, return a workspace-bound candidate |
| `GET /api/v1/voice/transcriptions/{transcript_id}` | Inspect an unexpired candidate only while its workspace revision and map binding still match |
| `DELETE /api/v1/voice/transcriptions/{transcript_id}` | Discard a candidate; does not terminate a mission or stop a robot |

The upload is `multipart/form-data` with these fields:

| Field | Value |
|---|---|
| `file` | One RIFF/WAVE file containing mono signed 16-bit integer PCM at 16,000 or 24,000 Hz |
| `expected_revision` | Current non-negative workspace revision |
| `capture_id` | A new UUID for this finite recording |
| `audio_source` | `microphone` or `recorded_upload`, explicitly a client-reported provenance label |
| `language` | Optional `ko` or `en` language hint; omit it for automatic recognition |

New recordings are accepted only in `IDLE` or `PLAN_READY`. The API checks preparation state before reading the upload and checks the explicit revision, session and map before and after the provider request. A late result cannot replace a mission that changed while transcription was running.

Recordings must last **0.2–20 seconds** and contain at most **1 MiB**. The complete multipart body is limited to 1 MiB plus 16 KiB of framing and metadata, with a 15-second upload deadline. Headers, field count and text fields have separate bounds. The pinned multipart parser consumes the request stream directly; it does not use a temporary upload file or spool larger files to disk. The service admits one provider request at a time and rejects a second concurrent request.

This slice validates RIFF length, chunk bounds, one standard PCM format, one complete audio segment, sample layout and duration. It rejects zero or constant sample data. This check detects a dead/silent recording, not reliable speech activity or recognition quality. It rebuilds a canonical WAV container with the same PCM samples and strips ancillary metadata. **It does not decode WebM/Opus, MP4/AAC, MP3, stereo, float PCM or arbitrary sample rates, and it does not resample.** The future browser must emit supported PCM WAV through its capture encoder, or add a reviewed, pinned conversion implementation. An unsupported file fails with an actionable English error before dispatch.

## Candidate response and explicit acceptance

A response contains the original-language `text`, `capture_id`, provider `request_id`, generated `transcript_id`, source labels, audio duration/format metadata and `requires_confirmation: true`. No audio bytes, upload filename, provider authorization or invented confidence score are returned. `language` is `null`: the current documented finite API does not return a detected-language field. `language_hint` records only the hint the client requested; it is not a language-detection result.

The backend retains only candidate text and metadata in a bounded in-memory registry: **30 minutes maximum, 32 records maximum**. A new submitted recording supersedes older unaccepted candidates in the same workspace session. Deletion, expiry, capacity eviction and application restart invalidate a candidate. There is no persistent audio, transcript database or automatic replay in this service. Accepted-goal evidence is handled separately by the mission layer.

The immutable binding is:

```json
{
  "session_id": "current-workspace-session",
  "workspace_revision": 4,
  "map": {
    "id": "current-map",
    "version": "current-version",
    "geometry_hash": "current-geometry-hash"
  }
}
```

An explicit goal submission can reference `transcript_id` with `source: "voice"` after the operator checks or edits the words. The goal layer must validate this binding under its command serialization, preserve the original transcription separately from the accepted edited text, and still require approval of the resulting plan. A candidate alone never creates or changes a mission. Transport cancellation cannot guarantee that Meta has not already processed the recording; a cancelled/disconnected request is prevented from registering a usable late candidate locally.

## Verified provider protocol

The transport follows Meta's official [speech-to-text guide](https://dev.meta.ai/docs/speech-to-text), reviewed on October 27, 2026. It sends a finite multipart request to the fixed TLS endpoint `POST https://api.meta.ai/v1/asr/transcribe`, with Bearer authentication, a JSON `request` part and an `audio` WAV part. The request selects model `muse-voice-transcribe-1.0`, `mode: "PUSH_TO_TALK"` and `audioEncoding: "WAV"`. An optional documented `languageBias` uses `Korean` or `English`. The provider session ID is the backend-generated request UUID.

Credential-bearing requests do not follow redirects or use environment proxy settings. The client uses bounded connection/response timeouts, a 35-second application request deadline and a 64 KiB decoded provider-response limit. Rejections, rate limits, timeouts, malformed responses and empty transcripts return sanitized errors. The service never substitutes demo text or retries a paid request automatically. No audio, transcript, provider body or authorization header is logged by the adapter.

Streaming ASR and TTS are outside this slice. The frontend's microphone state must remain disconnected until capture, editing, cancellation and explicit acceptance have been implemented and checked on the actual device. Target tablets need trusted HTTPS for browser microphone access.

## Offline verification and tomorrow's device checks

`tests/test_voice.py` uses generated sine-wave fixtures and mocked HTTP/provider transports only. It checks supported sample preservation, metadata stripping, malformed/truncated/compressed/stereo/rate/duration/size rejection, silence, fixed multipart provider fields, redirect refusal, bounded provider responses, sanitized errors, concurrency, preparation/revision gates, late-result rejection, registry expiry/supersession/deletion and absence of mission mutation. These tests establish software behavior, not recognition quality or actual voice access.

Before claiming connected voice input, verify on the target browser:

1. Trusted HTTPS, device permission, record/stop/cancel and typed fallback.
2. Supported mono PCM WAV encoding without unexpected duration/size changes.
3. Opt-in real Meta requests with Korean and English recordings, preserving the original words and allowing corrections.
4. Capture supersession, late completion, original-versus-edited transcript evidence and explicit latest-revision goal submission.
5. No goal submission during an active mission and no action without separate plan approval.

[Voice input](VOICE_INPUT.md) · [Service composition](SERVICE_COMPOSITION.md)
