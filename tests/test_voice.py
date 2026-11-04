"""Self-authored waveform and mocked transports only; no microphone or API calls."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import io
import json
import math
import struct
import unittest
from uuid import uuid4
import wave

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.maps import MapDefinition
from backend.voice import (MAX_AUDIO_BYTES, MAX_RESPONSE_BYTES, MAX_TRANSCRIPTS, MetaVoiceProvider,
                           TRANSCRIPT_TTL_SECONDS, VoiceError, VoiceService, normalize_wav)
from backend.voice_api import MAX_BODY_BYTES, router


def wav(*, rate=24000, seconds=0.25, channels=1, width=2, silence=False) -> bytes:
    """Generate a test tone, not captured speech or a quality benchmark."""
    output = io.BytesIO()
    samples = bytearray()
    for index in range(round(rate * seconds)):
        value = 0 if silence else round(math.sin(index * math.tau * 440 / rate) * 1000)
        encoded = struct.pack("<h", value) if width == 2 else bytes([128 if silence else index % 256])
        samples.extend(encoded * channels)
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(width)
        target.setframerate(rate)
        target.writeframes(samples)
    return output.getvalue()


class StubVoice:
    def __init__(self, callback=None):
        self.calls = []
        self.callback = callback

    async def transcribe(self, audio, request_id, language):
        self.calls.append((audio, request_id, language))
        if self.callback:
            self.callback()
        return "피자집에서 학교로 가줘."


class StubPhysical:
    """A local coordinator snapshot, with no Native client or hardware methods."""

    def __init__(self, **state):
        self.lock = asyncio.Lock()
        self.task = None
        self.state = {"enabled": True, "state": "READY", "mission_id": None, "error": None, **state}

    def snapshot(self):
        return deepcopy(self.state)


class WaveValidationTests(unittest.TestCase):
    def assert_code(self, data, code):
        with self.assertRaises(VoiceError) as raised:
            normalize_wav(data)
        self.assertEqual(raised.exception.code, code)

    def test_supported_rates_rebuild_same_pcm(self):
        for rate in (16000, 24000):
            original = wav(rate=rate)
            result = normalize_wav(original)
            self.assertEqual(result.wav, original)
            self.assertEqual(result.duration_ms, 250)
            self.assertEqual(result.sample_rate_hz, rate)

    def test_ancillary_metadata_removed_without_resampling(self):
        original = wav()
        decorated = original[:12] + b"JUNK" + struct.pack("<I", 4) + b"test" + original[12:]
        decorated = decorated[:4] + struct.pack("<I", len(decorated) - 8) + decorated[8:]
        self.assertEqual(normalize_wav(decorated).wav, original)

    def test_browser_containers_and_wrong_pcm_rejected(self):
        for data in (b"\x1aE\xdf\xa3" + b"x" * 40, wav(channels=2), wav(width=1), wav(rate=48000)):
            self.assert_code(data, "VOICE_AUDIO_FORMAT")

    def test_duration_bounds(self):
        self.assert_code(wav(seconds=0.1), "VOICE_AUDIO_DURATION")
        self.assert_code(wav(seconds=20.1, rate=16000), "VOICE_AUDIO_DURATION")
        self.assertEqual(normalize_wav(wav(seconds=20, rate=24000)).duration_ms, 20000)

    def test_zero_and_constant_audio_rejected(self):
        self.assert_code(wav(silence=True), "VOICE_AUDIO_SILENCE")
        data = wav()
        self.assert_code(data[:44] + struct.pack("<h", 400) * ((len(data) - 44) // 2), "VOICE_AUDIO_SILENCE")

    def test_truncated_length_trailing_and_chunks_rejected(self):
        valid = wav()
        self.assert_code(valid[:-1], "VOICE_AUDIO_INVALID")
        self.assert_code(valid + b"extra", "VOICE_AUDIO_INVALID")
        malformed = valid[:40] + struct.pack("<I", len(valid) * 100) + valid[44:]
        self.assert_code(malformed, "VOICE_AUDIO_INVALID")

    def test_compressed_header_and_duplicate_format_rejected(self):
        valid = wav()
        self.assert_code(valid[:20] + struct.pack("<H", 3) + valid[22:], "VOICE_AUDIO_FORMAT")
        duplicate = valid[:36] + valid[12:36] + valid[36:]
        duplicate = duplicate[:4] + struct.pack("<I", len(duplicate) - 8) + duplicate[8:]
        self.assert_code(duplicate, "VOICE_AUDIO_INVALID")

    def test_file_bound_precedes_decode(self):
        self.assert_code(b"x" * (MAX_AUDIO_BYTES + 1), "VOICE_AUDIO_SIZE")


class VoiceProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_wire_format_and_original_language(self):
        captured = []

        def handler(request):
            captured.append(request)
            return httpx.Response(200, json={"transcript": "학교로 가줘.", "sessionId": "test", "turns": []})

        provider = MetaVoiceProvider("test-credential", transport=httpx.MockTransport(handler))
        result = await provider.transcribe(wav(), "test-request", "ko")
        self.assertEqual(result, "학교로 가줘.")
        request = captured[0]
        self.assertEqual(str(request.url), "https://api.meta.ai/v1/asr/transcribe?sessionId=test-request")
        self.assertEqual(request.headers["authorization"], "Bearer test-credential")
        self.assertIn(b'name="audio"', request.content)
        self.assertIn(b'name="request"', request.content)
        self.assertIn(b'"audioEncoding": "WAV"', request.content)
        self.assertIn(b'"mode": "PUSH_TO_TALK"', request.content)
        self.assertIn(b'"languageBias": ["Korean"]', request.content)
        self.assertNotIn(b"test-credential", request.content)

    async def test_redirect_never_sends_credentials_to_another_origin(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(307, headers={"location": "https://untrusted.invalid/voice"})

        provider = MetaVoiceProvider("private", transport=httpx.MockTransport(handler))
        with self.assertRaises(VoiceError) as raised:
            await provider.transcribe(wav(), "request", None)
        self.assertEqual(raised.exception.code, "VOICE_PROVIDER_REJECTED")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("private", str(raised.exception))

    async def test_bad_and_empty_provider_responses(self):
        for payload, code in (({}, "VOICE_PROVIDER_RESPONSE"), ({"transcript": 1}, "VOICE_PROVIDER_RESPONSE"),
                              ({"transcript": " "}, "VOICE_NO_SPEECH"), ({"transcript": "x" * 2001}, "VOICE_PROVIDER_RESPONSE")):
            provider = MetaVoiceProvider("private", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
            with self.assertRaises(VoiceError) as raised:
                await provider.transcribe(wav(), "request", None)
            self.assertEqual(raised.exception.code, code)

    async def test_oversized_response_and_timeout_sanitized(self):
        provider = MetaVoiceProvider("private", transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))))
        with self.assertRaises(VoiceError) as raised:
            await provider.transcribe(wav(), "request", None)
        self.assertEqual(raised.exception.code, "VOICE_PROVIDER_RESPONSE")

        def timeout(_):
            raise httpx.ReadTimeout("private upstream diagnostic")

        provider = MetaVoiceProvider("private", transport=httpx.MockTransport(timeout))
        with self.assertRaises(VoiceError) as raised:
            await provider.transcribe(wav(), "request", None)
        self.assertEqual(raised.exception.code, "VOICE_PROVIDER_TIMEOUT")
        self.assertNotIn("private", str(raised.exception))


class VoiceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_and_unsupported_audio_make_no_provider_call(self):
        with self.assertRaises(VoiceError) as raised:
            await VoiceService().transcribe(wav(), capture_id="test", audio_source="recorded_upload")
        self.assertEqual(raised.exception.code, "VOICE_NOT_CONFIGURED")
        provider = StubVoice()
        with self.assertRaises(VoiceError):
            await VoiceService(provider=provider).transcribe(wav(channels=2), capture_id="test", audio_source="recorded_upload")
        self.assertEqual(provider.calls, [])

    async def test_transcript_has_no_invented_confidence_language_or_mission(self):
        provider = StubVoice()
        service = VoiceService(provider=provider)
        result = await service.transcribe(wav(), capture_id="capture", audio_source="recorded_upload", language="ko")
        self.assertEqual(result["text"], "피자집에서 학교로 가줘.")
        self.assertIsNone(result["language"])
        self.assertEqual(result["language_hint"], "ko")
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse(result["mission_submitted"])
        self.assertFalse(result["audio_retained"])
        self.assertNotIn("confidence", result)
        self.assertEqual(service._transcripts, {})

    async def test_provider_errors_never_become_demo_transcript(self):
        class Broken:
            async def transcribe(self, *_):
                raise RuntimeError("private diagnostic")

        with self.assertRaises(VoiceError) as raised:
            await VoiceService(provider=Broken()).transcribe(wav(), capture_id="x", audio_source="recorded_upload")
        self.assertEqual(raised.exception.code, "VOICE_PROVIDER_FAILED")
        self.assertNotIn("private", str(raised.exception))

    async def test_concurrent_provider_request_rejected_without_second_dispatch(self):
        entered, release = asyncio.Event(), asyncio.Event()

        class Waiting:
            async def transcribe(self, *_):
                entered.set()
                await release.wait()
                return "Go to School."

        service = VoiceService(provider=Waiting())
        pending = asyncio.create_task(service.transcribe(wav(), capture_id="first", audio_source="recorded_upload"))
        await entered.wait()
        with self.assertRaises(VoiceError) as raised:
            await service.transcribe(wav(), capture_id="second", audio_source="recorded_upload")
        self.assertEqual(raised.exception.code, "VOICE_REQUEST_BUSY")
        release.set()
        await pending

    async def test_registry_ttl_copy_supersession_cancellation_and_bounds(self):
        now = [10.0]
        service = VoiceService(provider=StubVoice(), clock=lambda: now[0])
        result = await service.transcribe(wav(), capture_id="first", audio_source="recorded_upload")
        binding = {"session_id": "session", "workspace_revision": 4,
                   "map": {"id": "map", "version": "1", "geometry_hash": "hash"}}
        record = service.remember_transcript(result, binding)
        record["binding"]["map"]["id"] = "mutated"
        self.assertEqual(service.get_transcript(result["transcript_id"])["binding"]["map"]["id"], "map")
        replacement = {**result, "transcript_id": str(uuid4())}
        service.remember_transcript(replacement, binding)
        with self.assertRaises(VoiceError):
            service.get_transcript(result["transcript_id"])
        now[0] += TRANSCRIPT_TTL_SECONDS
        with self.assertRaises(VoiceError):
            service.get_transcript(replacement["transcript_id"])
        for index in range(MAX_TRANSCRIPTS + 2):
            item = {**result, "transcript_id": str(index)}
            service.remember_transcript(item, {**binding, "session_id": str(index)})
        self.assertEqual(len(service._transcripts), MAX_TRANSCRIPTS)
        with self.assertRaises(VoiceError):
            service.get_transcript("0")
        service.discard_transcript("2")
        with self.assertRaises(VoiceError):
            service.get_transcript("2")
        service.close()
        self.assertEqual(len(service._transcripts), 0)


class VoiceApiTests(unittest.TestCase):
    def setUp(self):
        class Store:
            map_definition = MapDefinition()
            state = {"session_id": "session", "revision": 4, "state": "IDLE"}

            def snapshot(self):
                return deepcopy(self.state)

        self.store = Store()
        self.provider = StubVoice()
        self.service = VoiceService(provider=self.provider)
        app = self.app = FastAPI()
        app.state.store, app.state.voice = self.store, self.service
        app.include_router(router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def upload(self, *, audio=None, fields=None):
        metadata = {"expected_revision": "4", "capture_id": str(uuid4()), "audio_source": "recorded_upload", "language": "ko"}
        metadata.update(fields or {})
        return self.client.post("/api/v1/voice/transcriptions", files={"file": ("private-name.wav", audio or wav(), "audio/wav")}, data=metadata)

    def test_api_returns_candidate_without_mutation_and_can_discard(self):
        before = self.store.snapshot()
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(result["binding"]["workspace_revision"], 4)
        self.assertEqual(result["binding"]["map"]["id"], self.store.map_definition.id)
        self.assertNotIn("private-name", response.text)
        path = "/api/v1/voice/transcriptions/" + result["transcript_id"]
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.delete(path).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 409)

    def test_active_mission_and_stale_revision_rejected_before_provider(self):
        self.store.state["state"] = "WAITING_SIGNAL"
        self.assertEqual(self.upload().status_code, 409)
        self.store.state["state"] = "IDLE"
        self.assertEqual(self.upload(fields={"expected_revision": "3"}).status_code, 409)
        self.assertEqual(self.provider.calls, [])

    def test_workspace_changed_during_provider_discards_late_result(self):
        self.provider.callback = lambda: self.store.state.update(state="READY", revision=5)
        response = self.upload()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.service._transcripts), 0)

    def test_active_held_and_unretired_robot_missions_reject_before_provider(self):
        physical = self.app.state.physical = StubPhysical()
        before = self.store.snapshot()
        for state in ("STARTING", "RUNNING", "WAITING_SIGNAL", "OBSERVING", "HOLD", "COMPLETE", "READY"):
            with self.subTest(state=state):
                physical.state.update(state=state, mission_id="retained-mission")
                response = self.upload()
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["detail"]["code"], "VOICE_PHYSICAL_MISSION_ACTIVE")
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.store.snapshot(), before)

    def test_busy_robot_lock_does_not_wait_or_dispatch(self):
        physical = self.app.state.physical = StubPhysical()
        asyncio.run(physical.lock.acquire())
        try:
            response = self.upload()
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"]["code"], "VOICE_PHYSICAL_STATUS_REQUIRED")
            self.assertEqual(self.provider.calls, [])
            self.assertTrue(physical.lock.locked())
        finally:
            physical.lock.release()

    def test_unknown_robot_state_worker_and_snapshot_failure_fail_closed(self):
        physical = self.app.state.physical = StubPhysical(state="UNKNOWN")
        self.assertEqual(self.upload().status_code, 409)
        physical.state.update(state="READY", error="UNRESOLVED")
        self.assertEqual(self.upload().status_code, 409)
        physical.state["error"] = None
        physical.task = type("RunningTask", (), {"done": lambda _self: False})()
        self.assertEqual(self.upload().status_code, 409)
        physical.task = None

        def unavailable():
            raise RuntimeError("Synthetic local snapshot failure")

        physical.snapshot = unavailable
        response = self.upload()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "VOICE_PHYSICAL_STATUS_REQUIRED")
        self.assertNotIn("Synthetic", response.text)
        self.assertEqual(self.provider.calls, [])

    def test_robot_started_during_asr_discards_candidate(self):
        physical = self.app.state.physical = StubPhysical()
        self.provider.callback = lambda: physical.state.update(state="WAITING_SIGNAL", mission_id="new-mission")
        before = self.store.snapshot()
        response = self.upload()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "VOICE_PHYSICAL_MISSION_ACTIVE")
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(len(self.service._transcripts), 0)
        self.assertEqual(self.store.snapshot(), before)

    def test_robot_hold_blocks_candidate_lookup_but_not_discard(self):
        physical = self.app.state.physical = StubPhysical()
        result = self.upload().json()
        path = "/api/v1/voice/transcriptions/" + result["transcript_id"]
        physical.state.update(state="HOLD", mission_id="retained-mission")
        self.assertEqual(self.client.get(path).status_code, 409)
        self.assertEqual(self.client.delete(path).status_code, 200)

    def test_disabled_physical_coordinator_keeps_simulation_voice_available(self):
        self.app.state.physical = StubPhysical(enabled=False, state="DISABLED")
        self.assertEqual(self.upload().status_code, 200)
        self.assertEqual(len(self.provider.calls), 1)

    def test_old_receipt_superseded_by_new_capture_or_revision(self):
        first = self.upload().json()
        second = self.upload().json()
        self.assertEqual(self.client.get("/api/v1/voice/transcriptions/" + first["transcript_id"]).status_code, 409)
        self.store.state["revision"] = 5
        self.assertEqual(self.client.get("/api/v1/voice/transcriptions/" + second["transcript_id"]).status_code, 409)

    def test_invalid_metadata_and_audio_rejected(self):
        for fields in ({"audio_source": "unknown"}, {"capture_id": "not-a-uuid"}, {"language": "unknown"},
                       {"expected_revision": "-1"}, {"extra": "value"}):
            self.assertEqual(self.upload(fields=fields).status_code, 422)
        self.assertEqual(self.upload(audio=wav(channels=2)).status_code, 415)
        self.assertEqual(self.provider.calls, [])

    def test_total_body_cap_and_malformed_multipart(self):
        response = self.client.post("/api/v1/voice/transcriptions", content=b"small",
                                    headers={"content-type": "multipart/form-data; boundary=voice", "content-length": str(MAX_BODY_BYTES + 1)})
        self.assertEqual(response.status_code, 413)
        response = self.client.post("/api/v1/voice/transcriptions", content=b"--voice\r\n",
                                    headers={"content-type": "multipart/form-data; boundary=voice"})
        self.assertEqual(response.status_code, 422)

    def test_chunked_upload_cap_and_non_ascii_revision(self):
        chunks = (b"x" * 65536 for _ in range(18))
        response = self.client.post("/api/v1/voice/transcriptions", content=chunks,
                                    headers={"content-type": "multipart/form-data; boundary=voice"})
        self.assertIn(response.status_code, (413, 422))
        self.assertEqual(self.upload(fields={"expected_revision": "\u2074"}).status_code, 422)
        self.assertEqual(self.provider.calls, [])

    def test_missing_metadata_and_non_multipart_do_not_dispatch(self):
        response = self.client.post("/api/v1/voice/transcriptions", files={"file": ("tone.wav", wav(), "audio/wav")})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/v1/voice/transcriptions", content=wav(), headers={"content-type": "audio/wav"})
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.provider.calls, [])

    def test_format_status_does_not_claim_connected_microphone_or_actual_access(self):
        result = self.client.get("/api/v1/voice").json()
        self.assertTrue(result["backend_implemented"])
        self.assertFalse(result["microphone_connected"])
        self.assertFalse(result["provider_access_verified"])
        self.assertEqual(result["accepted_audio"]["sample_rates_hz"], [16000, 24000])


class VoiceGoalPhysicalGuardTests(unittest.TestCase):
    """Exercise both accepted-transcript routes without cameras or providers."""

    def setUp(self):
        from backend.app import create_app
        from backend.settings import Settings

        self.app = create_app(Settings(db_path=":memory:"), automatic_signal_watch=False)
        self.client = self.enterContext(TestClient(self.app))
        self.physical = self.app.state.physical
        self.calls = []
        state = self.app.state.store.snapshot()
        definition = self.app.state.store.map_definition
        self.transcript_id = str(uuid4())
        self.app.state.voice.remember_transcript({"transcript_id": self.transcript_id,
            "text": "Go to School.", "audio_source": "microphone"},
            {"session_id": state["session_id"], "workspace_revision": state["revision"],
             "map": {"id": definition.id, "version": definition.version, "geometry_hash": definition.geometry_hash}})

        async def plan(payload):
            self.calls.append(payload)
            return {"accepted_for_test": True}, 200

        self.app.state.live_intelligence.plan = plan

    def goal(self, path):
        return self.client.post(path, json={"request_id": str(uuid4()),
            "expected_revision": self.app.state.store.snapshot()["revision"],
            "text": "Go to School.", "provider": "meta", "source": "voice",
            "transcript_id": self.transcript_id})

    def test_voice_goal_cannot_bypass_physical_guard_with_existing_receipt(self):
        before = self.app.state.store.snapshot()
        for path in ("/api/v1/goals", "/api/v1/plans/live"):
            for state in ("RUNNING", "WAITING_SIGNAL", "HOLD", "COMPLETE"):
                with self.subTest(path=path, state=state):
                    self.physical.status.update(enabled=True, state=state, mission_id="retained-mission")
                    response = self.goal(path)
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json()["detail"]["code"], "VOICE_PHYSICAL_MISSION_ACTIVE")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.app.state.store.snapshot(), before)

    def test_default_simulation_and_retired_ready_state_reach_normal_planning(self):
        for state, enabled in (("DISABLED", False), ("READY", True)):
            self.physical.status.update(enabled=enabled, state=state, mission_id=None, error=None)
            response = self.goal("/api/v1/goals")
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.calls), 2)

    def test_voice_goal_rejects_busy_coordinator_without_planning(self):
        asyncio.run(self.physical.lock.acquire())
        try:
            response = self.goal("/api/v1/plans/live")
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"]["code"], "VOICE_PHYSICAL_STATUS_REQUIRED")
            self.assertEqual(self.calls, [])
        finally:
            self.physical.lock.release()


if __name__ == "__main__":
    unittest.main()
