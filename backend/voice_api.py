"""Bounded in-memory voice uploads, independent of mission creation and approval."""
from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.requests import ClientDisconnect

from backend.voice import MAX_AUDIO_BYTES, VoiceError

router = APIRouter(prefix="/api/v1/voice")
MAX_BODY_BYTES = MAX_AUDIO_BYTES + 16 * 1024
FIELDS = {"expected_revision", "capture_id", "audio_source", "language"}


def _error(error: VoiceError) -> HTTPException:
    return HTTPException(error.status_code, detail={"code": error.code, "message": str(error)})


class _MemoryMultipart:
    """Use the pinned parser directly so oversized uploads never spool to disk."""

    def __init__(self, boundary: bytes):
        self.file = bytearray()
        self.fields: dict[str, str] = {}
        self.seen: set[str] = set()
        self.finished = False
        self.name = ""
        self.value = bytearray()
        self.headers: dict[bytes, bytes] = {}
        self.header_name, self.header_value = bytearray(), bytearray()
        self.header_bytes = 0
        self.parser = MultipartParser(boundary, callbacks={
            "on_part_begin": self._part_begin, "on_header_field": self._header_field,
            "on_header_value": self._header_value, "on_header_end": self._header_end,
            "on_headers_finished": self._headers_finished, "on_part_data": self._part_data,
            "on_part_end": self._part_end, "on_end": self._end,
        })

    def _part_begin(self):
        self.headers, self.header_name, self.header_value = {}, bytearray(), bytearray()
        self.value, self.header_bytes = bytearray(), 0
        if len(self.seen) >= 5:
            raise VoiceError(422, "Upload one WAV file and the documented capture fields only.", "VOICE_UPLOAD_FIELDS")

    def _header_field(self, data: bytes, start: int, end: int):
        self.header_bytes += end - start
        if self.header_bytes > 4096:
            raise VoiceError(413, "Voice upload headers are too large.", "VOICE_UPLOAD_SIZE")
        self.header_name.extend(data[start:end])

    def _header_value(self, data: bytes, start: int, end: int):
        self.header_bytes += end - start
        if self.header_bytes > 4096:
            raise VoiceError(413, "Voice upload headers are too large.", "VOICE_UPLOAD_SIZE")
        self.header_value.extend(data[start:end])

    def _header_end(self):
        name = bytes(self.header_name).lower()
        if name in self.headers:
            raise VoiceError(422, "Voice upload contains duplicate headers.", "VOICE_UPLOAD_INVALID")
        self.headers[name] = bytes(self.header_value)
        self.header_name.clear()
        self.header_value.clear()

    def _headers_finished(self):
        disposition, options = parse_options_header(self.headers.get(b"content-disposition", b""))
        try:
            self.name = options.get(b"name", b"").decode("ascii")
        except UnicodeError:
            raise VoiceError(422, "Voice upload field names must match the documented contract.", "VOICE_UPLOAD_FIELDS") from None
        if disposition != b"form-data" or self.name not in FIELDS | {"file"} or self.name in self.seen:
            raise VoiceError(422, "Voice upload contains an unknown or duplicate field.", "VOICE_UPLOAD_FIELDS")
        if (self.name == "file") != (b"filename" in options):
            raise VoiceError(422, "The file field must contain one WAV file; metadata fields must contain text.", "VOICE_UPLOAD_FIELDS")
        self.seen.add(self.name)

    def _part_data(self, data: bytes, start: int, end: int):
        destination = self.file if self.name == "file" else self.value
        limit = MAX_AUDIO_BYTES if self.name == "file" else 256
        if len(destination) + end - start > limit:
            raise VoiceError(413, "Voice audio must be at most 1 MiB and capture metadata must be bounded.", "VOICE_UPLOAD_SIZE")
        destination.extend(data[start:end])

    def _part_end(self):
        if self.name != "file":
            try:
                self.fields[self.name] = self.value.decode("utf-8")
            except UnicodeError:
                raise VoiceError(422, "Voice capture fields must contain UTF-8 text.", "VOICE_UPLOAD_FIELDS") from None

    def _end(self):
        self.finished = True


async def _read_upload(request: Request) -> tuple[bytes, dict]:
    media_type, options = parse_options_header(request.headers.get("content-type", ""))
    boundary = options.get(b"boundary", b"")
    if media_type != b"multipart/form-data" or not 1 <= len(boundary) <= 70:
        raise VoiceError(415, "Send a multipart/form-data upload with a WAV file field.", "VOICE_UPLOAD_FORMAT")
    length = request.headers.get("content-length")
    if length and (not length.isascii() or not length.isdecimal() or len(length) > 12 or int(length) > MAX_BODY_BYTES):
        raise VoiceError(413, "Voice upload is too large. Record a shorter goal.", "VOICE_UPLOAD_SIZE")
    parser = _MemoryMultipart(boundary)
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                raise VoiceError(413, "Voice upload is too large. Record a shorter goal.", "VOICE_UPLOAD_SIZE")
            parser.parser.write(chunk)
        parser.parser.finalize()
        if not parser.finished or "file" not in parser.seen:
            raise VoiceError(422, "The voice upload is incomplete or missing its WAV file.", "VOICE_UPLOAD_INVALID")
        return bytes(parser.file), dict(parser.fields)
    except MultipartParseError:
        raise VoiceError(422, "The voice upload could not be parsed. Record again.", "VOICE_UPLOAD_INVALID") from None
    except ClientDisconnect:
        raise VoiceError(400, "Voice upload was cancelled. No goal was submitted.", "VOICE_REQUEST_CANCELLED") from None
    finally:
        parser.file.clear()
        parser.value.clear()


def _binding(request: Request, expected_revision: int) -> dict:
    snapshot = request.app.state.store.snapshot()
    if snapshot["state"] not in {"IDLE", "PLAN_READY"}:
        raise VoiceError(409, "New voice input is available only during non-executing preparation. Complete or terminate and reconcile the current mission first.", "VOICE_MISSION_ACTIVE")
    if snapshot["revision"] != expected_revision:
        raise VoiceError(409, "Workspace changed. Refresh it before recording a goal.", "VOICE_WORKSPACE_CHANGED")
    map_definition = request.app.state.store.map_definition
    return {"session_id": snapshot["session_id"], "workspace_revision": snapshot["revision"],
            "map": {"id": map_definition.id, "version": map_definition.version,
                    "geometry_hash": map_definition.geometry_hash}}


@router.get("")
def voice_status(request: Request):
    return request.app.state.voice.status()


@router.post("/transcriptions")
async def transcribe(request: Request):
    try:
        # This preliminary check prevents uploads/provider work in an active mission.
        snapshot = request.app.state.store.snapshot()
        _binding(request, snapshot["revision"])
        try:
            async with asyncio.timeout(15):
                data, fields = await _read_upload(request)
        except TimeoutError:
            raise VoiceError(408, "Voice upload timed out. Record again or use typed input.", "VOICE_UPLOAD_TIMEOUT") from None
        if not {"expected_revision", "capture_id", "audio_source"} <= fields.keys():
            raise VoiceError(422, "Include expected_revision, capture_id and audio_source with the WAV file.", "VOICE_UPLOAD_FIELDS")
        if not fields["expected_revision"].isascii() or not fields["expected_revision"].isdecimal():
            raise VoiceError(422, "expected_revision must be a non-negative integer.", "VOICE_UPLOAD_FIELDS")
        try:
            capture_id = str(UUID(fields["capture_id"]))
        except ValueError:
            raise VoiceError(422, "capture_id must be a UUID for this finite recording.", "VOICE_UPLOAD_FIELDS") from None
        audio_source = fields["audio_source"]
        if audio_source not in {"recorded_upload", "microphone"}:
            raise VoiceError(422, "audio_source must be recorded_upload or microphone; it is a client-reported source.", "VOICE_UPLOAD_FIELDS")
        language = fields.get("language") or None
        if language not in {None, "ko", "en"}:
            raise VoiceError(422, "Use ko or en as the language hint, or omit it.", "VOICE_LANGUAGE")
        revision = int(fields["expected_revision"])
        before = _binding(request, revision)
        if await request.is_disconnected():
            raise VoiceError(400, "Voice upload was cancelled. No goal was submitted.", "VOICE_REQUEST_CANCELLED")
        request.app.state.voice.invalidate_session(before["session_id"])
        result = await request.app.state.voice.transcribe(data, capture_id=capture_id,
                                                        audio_source=audio_source, language=language)
        del data
        after = _binding(request, revision)
        if before != after or await request.is_disconnected():
            raise VoiceError(409, "Voice result was superseded or cancelled. No goal was submitted.", "VOICE_WORKSPACE_CHANGED")
        return request.app.state.voice.remember_transcript(result, before)
    except VoiceError as error:
        raise _error(error) from None


@router.get("/transcriptions/{transcript_id}")
def transcript(request: Request, transcript_id: str):
    try:
        record = request.app.state.voice.get_transcript(transcript_id)
        current = _binding(request, record["binding"]["workspace_revision"])
        if current != record["binding"]:
            raise VoiceError(409, "This transcript belongs to a different workspace or map.", "VOICE_WORKSPACE_CHANGED")
        return record
    except VoiceError as error:
        raise _error(error) from None


@router.delete("/transcriptions/{transcript_id}")
def discard_transcript(request: Request, transcript_id: str):
    request.app.state.voice.discard_transcript(transcript_id)
    return {"discarded": True, "mission_submitted": False}
