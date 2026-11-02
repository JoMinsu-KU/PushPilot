"""Dedicated GUI HTTP boundary. No robot token or arbitrary URL reaches JS."""
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import time
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .service import ConsoleError
from backend.robot_control.taught_executor import ExecutionBlocked


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Versioned(Strict):
    request_id: str = Field(min_length=36, max_length=36)
    expected_revision: int = Field(ge=0)


class Login(Strict):
    token: str = Field(min_length=16, max_length=200)


class Reason(Versioned):
    reason: str = Field(min_length=10, max_length=500)


class Approval(Reason):
    reviewed_fields: list[str] = Field(min_length=5, max_length=5)


class Stop(Strict):
    request_id: str = Field(min_length=36, max_length=36)
    reason: str = Field(default="Operator Stop", min_length=1, max_length=500)


class Execute(Versioned):
    route: str = Field(pattern="^[BCD]$")
    step_id: str = Field(min_length=1, max_length=200)
    draft_id: str | None = Field(default=None, min_length=1, max_length=100)


class Draft(Versioned):
    route: str = Field(pattern="^[BCD]$")
    step_id: str = Field(min_length=1, max_length=200)
    stages: list[dict] = Field(min_length=1, max_length=64)
    expected_visual: str = Field(min_length=10, max_length=700)
    reason: str = Field(min_length=10, max_length=500)


def create_app(service, token, *, allowed_hosts, manage_lifecycle=True):
    if not isinstance(token, str) or not 16 <= len(token) <= 200:
        raise ValueError("Use a separate private console token.")
    allowed_hosts = frozenset(allowed_hosts)
    if not allowed_hosts or any("/" in h or "@" in h for h in allowed_hosts):
        raise ValueError("Explicit host:port allowlist is required.")
    sessions = {}
    static = Path(__file__).parent / "static"

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if manage_lifecycle:
                service.close()

    app = FastAPI(title="PushPilot Commissioning Console", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def boundary(request, call_next):
        host = request.headers.get("host", "")
        if host not in allowed_hosts:
            return JSONResponse({"code": "HOST_NOT_ALLOWED", "message": "등록된 콘솔 주소로 접속해 주세요."}, status_code=403)
        if request.method == "POST":
            # Safari/Chrome on an HTTP LAN still send exact Origin for fetch.
            if request.headers.get("origin") != "http://" + host:
                return JSONResponse({"code": "SAME_ORIGIN_REQUIRED", "message": "콘솔 화면에서 요청해 주세요."}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"code": "JSON_REQUIRED", "message": "JSON 요청이 필요합니다."}, status_code=415)
            try:
                length = int(request.headers.get("content-length", "-1"))
            except ValueError:
                length = -1
            if not 0 <= length <= 65536 or len(await request.body()) > 65536:
                return JSONResponse({"code": "BOUNDED_BODY_REQUIRED", "message": "요청 크기 제한을 초과했습니다."}, status_code=413)
        if request.url.path.startswith("/api/") and request.url.path != "/api/login":
            cookie = request.cookies.get("pp_console_session", "")
            expires = sessions.get(cookie, 0)
            if not expires or time.monotonic() >= expires:
                sessions.pop(cookie, None)
                return JSONResponse({"code": "CONSOLE_AUTH_REQUIRED", "message": "콘솔 접속 토큰을 입력해 주세요."}, status_code=401)
        try:
            response = await call_next(request)
        except Exception as error:
            # Never return provider messages, file paths or token contents.
            response = JSONResponse({"code": getattr(error, "code", "CONSOLE_REQUEST_FAILED"),
                "message": "요청 결과를 상태 화면에서 확인해 주세요. 이동 요청을 반복하지 마세요."}, status_code=503)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    @app.exception_handler(ConsoleError)
    async def console_error(request, error):
        return JSONResponse({"code": error.code, "message": error.message}, status_code=error.status)

    @app.exception_handler(ExecutionBlocked)
    async def execution_blocked(request, error):
        return JSONResponse({"code": error.code, "message": str(error)}, status_code=409)

    @app.post("/api/login")
    def login(command: Login):
        if not secrets.compare_digest(command.token, token):
            raise ConsoleError("CONSOLE_AUTH_REQUIRED", "접속 토큰을 확인해 주세요.", 401)
        # Fixed bound and absolute lifetime, no token in browser storage.
        now = time.monotonic()
        for key in [k for k, expiry in sessions.items() if expiry <= now]:
            sessions.pop(key, None)
        if len(sessions) >= 32:
            raise ConsoleError("SESSION_LIMIT", "접속 세션 수 제한입니다.", 429)
        key = secrets.token_urlsafe(32)
        sessions[key] = now + 8 * 3600
        result = JSONResponse({"authenticated": True})
        result.set_cookie("pp_console_session", key, httponly=True, samesite="strict", max_age=8 * 3600)
        return result

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/assets/font")
    def font():
        source = Path(__file__).resolve().parents[2] / "frontend/public/fonts/pretendard/PretendardVariable.woff2"
        return FileResponse(source, media_type="font/woff2")

    @app.get("/health")
    def health():
        return {"service": "pushpilot.commissioning-console", "automatic_execution": False}

    @app.get("/api/status")
    def status():
        return service.status()

    @app.get("/api/routes")
    def routes():
        return service.routes()

    @app.get("/api/export")
    def export():
        return JSONResponse(service.export(), headers={"Content-Disposition": 'attachment; filename="commissioning.private.json"'})

    @app.get("/api/camera")
    def camera():
        frame = service.camera()
        metadata = frame.get("metadata", {})
        metadata = metadata.get("frame") or metadata
        return Response(frame["jpeg"], media_type="image/jpeg", headers={"X-Frame-Id": str(metadata.get("id", "")),
            "X-Frame-Sha256": str(metadata.get("sha256", ""))})

    @app.get("/api/artifacts/{artifact_id}")
    def artifact(artifact_id: str):
        return Response(service.artifact(artifact_id), media_type="image/jpeg")

    @app.post("/api/session/acquire")
    def acquire(command: Versioned):
        return service.acquire(command.model_dump())

    @app.post("/api/session/release")
    def release(command: Versioned):
        return service.release(command.model_dump())

    @app.post("/api/drafts")
    def draft(command: Draft):
        return service.draft(command.model_dump())

    @app.post("/api/drafts/{draft_id}/approve")
    def approve(draft_id: str, command: Approval):
        return service.approve(draft_id, command.model_dump())

    @app.post("/api/execute")
    def execute(command: Execute):
        return service.execute(command.model_dump())

    @app.post("/api/observe")
    def observe(command: Versioned):
        return service.observe(command.model_dump())

    @app.post("/api/signal")
    def signal(command: Versioned):
        return service.signal(command.model_dump())

    @app.post("/api/review/ack")
    def acknowledge(command: Reason):
        return service.acknowledge(command.model_dump())

    @app.post("/api/stop")
    def stop(command: Stop):
        return service.stop(command.model_dump())

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
