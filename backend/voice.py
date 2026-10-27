"""Finite, ephemeral Meta transcription; returned words never authorize a mission."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
import json
import struct
import threading
import time
from typing import Callable, Protocol
from uuid import uuid4
import wave

import httpx

MAX_AUDIO_BYTES = 1024 * 1024
MAX_AUDIO_SECONDS = 20
MIN_AUDIO_SECONDS = 0.2
MAX_RESPONSE_BYTES = 64 * 1024
TRANSCRIPT_TTL_SECONDS = 1800
MAX_TRANSCRIPTS = 32
SUPPORTED_SAMPLE_RATES = (16000, 24000)
LANGUAGE_HINTS = {"ko": "Korean", "en": "English"}


class VoiceError(Exception):
    """Operator-safe error; do not include provider bodies or local credentials."""

    def __init__(self, status_code: int, message: str, code: str):
        self.status_code, self.code = status_code, code
        super().__init__(message)


@dataclass(frozen=True)
class VoiceAudio:
    wav: bytes = field(repr=False)
    duration_ms: int
    sample_rate_hz: int
    input_bytes: int


def normalize_wav(data: bytes) -> VoiceAudio:
    """Validate finite PCM and rebuild its WAV container without ancillary metadata.

    The first slice intentionally has no general media decoder or resampler. Browser
    capture must emit the documented format; other containers fail before dispatch.
    """
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise VoiceError(413, "Record a shorter goal; audio must contain at most 1 MiB.", "VOICE_AUDIO_SIZE")
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise VoiceError(415, "Upload mono 16-bit PCM WAV at 16 or 24 kHz. WebM, MP4 and MP3 are not supported.", "VOICE_AUDIO_FORMAT")
    if struct.unpack_from("<I", data, 4)[0] + 8 != len(data):
        raise VoiceError(422, "The WAV container is truncated or has trailing bytes. Record again.", "VOICE_AUDIO_INVALID")
    offset, chunks, fmt_count, pcm_count = 12, 0, 0, 0
    while offset < len(data):
        if offset + 8 > len(data) or chunks >= 64:
            raise VoiceError(422, "The WAV container is malformed. Record again.", "VOICE_AUDIO_INVALID")
        chunk_id = data[offset:offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        end = offset + 8 + chunk_size
        if end > len(data) or end + (chunk_size % 2) > len(data):
            raise VoiceError(422, "The WAV audio is truncated. Record again.", "VOICE_AUDIO_INVALID")
        if chunk_id == b"fmt ":
            fmt_count += 1
            if chunk_size != 16:
                raise VoiceError(415, "Use standard mono PCM16 WAV, without an extensible or compressed format.", "VOICE_AUDIO_FORMAT")
            encoding, channels, rate, byte_rate, alignment, bits = struct.unpack_from("<HHIIHH", data, offset + 8)
            if encoding != 1 or channels != 1 or bits != 16 or rate not in SUPPORTED_SAMPLE_RATES:
                raise VoiceError(415, "Use mono 16-bit PCM WAV at 16 or 24 kHz. Convert other audio before upload.", "VOICE_AUDIO_FORMAT")
            if byte_rate != rate * 2 or alignment != 2:
                raise VoiceError(422, "The WAV sample layout is inconsistent. Record again.", "VOICE_AUDIO_INVALID")
        if chunk_id == b"data":
            pcm_count += 1
            if chunk_size % 2:
                raise VoiceError(422, "The WAV sample data is incomplete. Record again.", "VOICE_AUDIO_INVALID")
        offset = end + (chunk_size % 2)
        chunks += 1
    if fmt_count != 1 or pcm_count != 1:
        raise VoiceError(422, "The WAV must contain one format and one audio segment.", "VOICE_AUDIO_INVALID")
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            frames, rate = source.getnframes(), source.getframerate()
            pcm = source.readframes(frames)
        if len(pcm) != frames * 2:
            raise ValueError("Incomplete samples")
    except (wave.Error, EOFError, ValueError, struct.error):
        raise VoiceError(422, "The WAV audio could not be decoded. Record again.", "VOICE_AUDIO_INVALID") from None
    duration = frames / rate
    if not MIN_AUDIO_SECONDS <= duration <= MAX_AUDIO_SECONDS:
        raise VoiceError(422, "Record between 0.2 and 20 seconds, then upload the complete goal.", "VOICE_AUDIO_DURATION")
    samples = struct.iter_unpack("<h", pcm)
    first = next(samples)[0]
    if not any(sample[0] != first for sample in samples):
        raise VoiceError(422, "No changing audio samples were recorded. Check the microphone and record again.", "VOICE_AUDIO_SILENCE")
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(pcm)
    return VoiceAudio(output.getvalue(), round(duration * 1000), rate, len(data))


class VoiceProvider(Protocol):
    async def transcribe(self, wav: bytes, request_id: str, language: str | None) -> str: ...


class MetaVoiceProvider:
    """Documented non-streaming ASR multipart transport with a fixed TLS origin."""

    endpoint = "https://api.meta.ai/v1/asr/transcribe"
    model = "muse-voice-transcribe-1.0"

    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self._api_key, self._transport = api_key, transport

    async def transcribe(self, wav: bytes, request_id: str, language: str | None) -> str:
        if not self._api_key:
            raise VoiceError(503, "Meta voice transcription is not configured on the backend. Use typed input.", "VOICE_NOT_CONFIGURED")
        settings = {"model": self.model, "mode": "PUSH_TO_TALK", "audioEncoding": "WAV"}
        if language is not None:
            if language not in LANGUAGE_HINTS:
                raise VoiceError(422, "Use ko or en as the language hint, or omit it.", "VOICE_LANGUAGE")
            settings["languageBias"] = [LANGUAGE_HINTS[language]]
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=False,
                                         trust_env=False, transport=self._transport) as client:
                async with client.stream(
                    "POST", self.endpoint, params={"sessionId": request_id},
                    headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
                    files={"request": (None, json.dumps(settings), "application/json"),
                           "audio": ("goal.wav", wav, "audio/wav")},
                ) as response:
                    if response.status_code == 429:
                        raise VoiceError(503, "Meta voice transcription is busy. Try again later or use typed input.", "VOICE_PROVIDER_BUSY")
                    if response.status_code != 200:
                        raise VoiceError(502, "Meta rejected the transcription request. Use typed input or check backend voice access.", "VOICE_PROVIDER_REJECTED")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise VoiceError(502, "Meta returned an oversized transcription response.", "VOICE_PROVIDER_RESPONSE")
                        body.extend(chunk)
            result = json.loads(body)
            text = result.get("transcript") if isinstance(result, dict) else None
            if not isinstance(text, str) or len(text) > 2000 or "\x00" in text:
                raise VoiceError(502, "Meta returned an invalid transcription response.", "VOICE_PROVIDER_RESPONSE")
            if not text.strip():
                raise VoiceError(422, "No speech was transcribed. Record again or type the goal.", "VOICE_NO_SPEECH")
            return text.strip()
        except VoiceError:
            raise
        except httpx.TimeoutException:
            raise VoiceError(504, "Meta voice transcription timed out. Record again or use typed input.", "VOICE_PROVIDER_TIMEOUT") from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise VoiceError(502, "Meta voice transcription failed. No goal was submitted.", "VOICE_PROVIDER_FAILED") from None


class VoiceService:
    """Keep only bounded transcript candidates in RAM; no audio or mission writes."""

    def __init__(self, api_key: str = "", *, provider: VoiceProvider | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self._configured = bool(api_key) or provider is not None
        self._provider = provider or MetaVoiceProvider(api_key)
        self._clock = clock
        self._busy = asyncio.Lock()
        self._registry_lock = threading.RLock()
        self._transcripts: OrderedDict[str, tuple[float, dict]] = OrderedDict()

    def status(self) -> dict:
        return {"schema_version": "pushpilot.voice.v1", "backend_implemented": True,
                "configured": self._configured, "provider": "meta", "model": MetaVoiceProvider.model,
                "provider_access_verified": False, "microphone_connected": False,
                "streaming": False, "tts": False, "requires_confirmation": True,
                "accepted_audio": {"container": "WAV", "encoding": "PCM_S16LE", "channels": 1,
                                   "sample_rates_hz": list(SUPPORTED_SAMPLE_RATES)},
                "limits": {"max_audio_bytes": MAX_AUDIO_BYTES, "max_duration_seconds": MAX_AUDIO_SECONDS,
                           "min_duration_seconds": MIN_AUDIO_SECONDS, "transcript_ttl_seconds": TRANSCRIPT_TTL_SECONDS},
                "audio_retention": "request_memory_only"}

    async def transcribe(self, data: bytes, *, capture_id: str, audio_source: str,
                         language: str | None = None) -> dict:
        if not self._configured:
            raise VoiceError(503, "Meta voice transcription is not configured on the backend. Use typed input.", "VOICE_NOT_CONFIGURED")
        if language is not None and language not in LANGUAGE_HINTS:
            raise VoiceError(422, "Use ko or en as the language hint, or omit it.", "VOICE_LANGUAGE")
        audio = normalize_wav(data)
        if self._busy.locked():
            raise VoiceError(429, "Another transcription is running. Wait or cancel it before recording again.", "VOICE_REQUEST_BUSY")
        async with self._busy:
            request_id = str(uuid4())
            try:
                text = await asyncio.wait_for(self._provider.transcribe(audio.wav, request_id, language), timeout=35)
            except VoiceError:
                raise
            except (TimeoutError, httpx.TimeoutException):
                raise VoiceError(504, "Meta voice transcription timed out. No goal was submitted.", "VOICE_PROVIDER_TIMEOUT") from None
            except Exception:
                raise VoiceError(502, "Meta voice transcription failed. No goal was submitted.", "VOICE_PROVIDER_FAILED") from None
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000 or "\x00" in text:
                raise VoiceError(502, "The voice provider returned an invalid transcript.", "VOICE_PROVIDER_RESPONSE")
            return {"schema_version": "pushpilot.voice-transcript.v1", "request_id": request_id,
                    "capture_id": capture_id, "transcript_id": str(uuid4()), "text": text.strip(),
                    "language": None, "language_hint": language, "source": "voice", "audio_source": audio_source,
                    "provider": "meta", "model": MetaVoiceProvider.model, "requires_confirmation": True,
                    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "audio": {"duration_ms": audio.duration_ms, "sample_rate_hz": audio.sample_rate_hz,
                              "channels": 1, "encoding": "PCM_S16LE", "input_bytes": audio.input_bytes},
                    "audio_retained": False, "mission_submitted": False}

    def _expire(self) -> None:
        now = self._clock()
        for key, (expiry, _) in list(self._transcripts.items()):
            if expiry <= now:
                del self._transcripts[key]

    def remember_transcript(self, result: dict, binding: dict) -> dict:
        """Supersede older candidates in this workspace; never store raw audio."""
        with self._registry_lock:
            self._expire()
            for key, (_, previous) in list(self._transcripts.items()):
                if previous["binding"]["session_id"] == binding["session_id"]:
                    del self._transcripts[key]
            record = {**deepcopy(result), "binding": deepcopy(binding),
                      "expires_in_seconds": TRANSCRIPT_TTL_SECONDS}
            self._transcripts[result["transcript_id"]] = (self._clock() + TRANSCRIPT_TTL_SECONDS, record)
            while len(self._transcripts) > MAX_TRANSCRIPTS:
                self._transcripts.popitem(last=False)
            return deepcopy(record)

    def invalidate_session(self, session_id: str) -> None:
        """A new submitted recording supersedes earlier unaccepted candidates."""
        with self._registry_lock:
            for key, (_, previous) in list(self._transcripts.items()):
                if previous["binding"]["session_id"] == session_id:
                    del self._transcripts[key]

    def get_transcript(self, transcript_id: str) -> dict:
        with self._registry_lock:
            self._expire()
            entry = self._transcripts.get(transcript_id)
            if entry is None:
                raise VoiceError(409, "This transcript expired, was cancelled or was superseded. Record again.", "VOICE_TRANSCRIPT_EXPIRED")
            record = deepcopy(entry[1])
            record["expires_in_seconds"] = max(0, int(entry[0] - self._clock()))
            return record

    def discard_transcript(self, transcript_id: str) -> None:
        with self._registry_lock:
            self._transcripts.pop(transcript_id, None)

    def close(self) -> None:
        with self._registry_lock:
            self._transcripts.clear()
