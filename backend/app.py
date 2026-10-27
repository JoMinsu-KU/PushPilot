"""ASGI API and same-origin frontend host for the hardware-free workspace."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Literal
from uuid import UUID
from tempfile import TemporaryDirectory

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.core import CommandError, WorkspaceStore
from backend.meta import GoalProvider, MetaGoalProvider
from backend.settings import Settings
from backend.maps import MapDefinition
from backend.scene import SceneStore
from backend.scene_api import router as scene_router


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_revision: int = Field(ge=0, strict=True)


class GoalCommand(Command):
    text: str = Field(min_length=1, max_length=2000)
    provider: Literal["demo", "meta"] = "demo"
    source: Literal["typed", "voice"] = "typed"


class ApprovalCommand(Command):
    plan_id: UUID
    plan_revision: int = Field(ge=0, strict=True)


class SignalCommand(Command):
    color: Literal["RED", "GREEN", "UNKNOWN"]
    junction_id: str | None = Field(default=None, min_length=1, max_length=80)


class ReviewCommand(Command):
    review_id: UUID
    verdict: Literal["PASS", "FAIL", "REOBSERVE", "UNKNOWN"]


def create_app(settings: Settings | None = None, *, db_path: str | None = None,
               provider: GoalProvider | None = None) -> FastAPI:
    """Create an app without reading credentials or initializing a database yet."""
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configured = settings or (Settings(db_path=db_path) if db_path else Settings.from_environment())
        if db_path is not None:
            configured = replace(configured, db_path=db_path)
        application.state.store = WorkspaceStore(
            configured.db_path,
            provider=provider or MetaGoalProvider(configured.meta_api_key),
            muse_configured=bool(configured.meta_api_key),
            signal_ttl_seconds=configured.signal_ttl_seconds,
            map_definition=MapDefinition(configured.map_path),
        )
        temporary_scene = TemporaryDirectory() if configured.db_path == ":memory:" and configured.scene_dir is None else None
        scene_dir = configured.scene_dir or (temporary_scene.name if temporary_scene else str(Path(configured.db_path).parent / "scene"))
        application.state.scene = SceneStore(scene_dir, map_definition=application.state.store.map_definition,
                                           meta_api_key=configured.meta_api_key)
        application.state.frontend = Path(configured.frontend_dist).resolve()
        try:
            yield
        finally:
            application.state.scene.close()
            application.state.store.close()
            if temporary_scene:
                temporary_scene.cleanup()

    application = FastAPI(title="PushPilot Workspace", version="0.1.0", lifespan=lifespan,
                          docs_url=None, redoc_url=None)

    @application.exception_handler(CommandError)
    async def command_error(_request: Request, error: CommandError):
        return JSONResponse({"detail": error.message}, status_code=error.status)

    @application.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/api/health")
    def health():
        return {"status": "ok", "mode": "simulation", "schema_version": "pushpilot.workspace.v1",
                "hardware_connected": False}

    @application.get("/api/v1/state")
    def state(request: Request):
        return request.app.state.store.snapshot()

    def dispatch(request: Request, action: str, command: Command):
        payload, status = request.app.state.store.execute(action, command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.post("/api/v1/goals")
    def goal(request: Request, command: GoalCommand):
        return dispatch(request, "goals", command)

    @application.post("/api/v1/approve")
    def approve(request: Request, command: ApprovalCommand):
        return dispatch(request, "approve", command)

    @application.post("/api/v1/signal")
    def signal(request: Request, command: SignalCommand):
        return dispatch(request, "signal", command)

    @application.post("/api/v1/reviews")
    def review(request: Request, command: ReviewCommand):
        return dispatch(request, "reviews", command)

    @application.post("/api/v1/advance")
    def advance(request: Request, command: Command):
        return dispatch(request, "advance", command)

    @application.post("/api/v1/reobserve")
    def reobserve(request: Request, command: Command):
        return dispatch(request, "reobserve", command)

    @application.post("/api/v1/cancel")
    def cancel(request: Request, command: Command):
        return dispatch(request, "cancel", command)

    @application.post("/api/v1/reset")
    def reset(request: Request, command: Command):
        return dispatch(request, "reset", command)

    application.include_router(scene_router)

    @application.api_route("/api", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    @application.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unknown_api(path: str = ""):
        raise HTTPException(404, "Unknown API endpoint.")

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(request: Request, path: str):
        directory: Path = request.app.state.frontend
        target = (directory / path).resolve()
        if target.is_relative_to(directory) and target.is_file():
            return FileResponse(target)
        index = directory / "index.html"
        if not Path(path).suffix and index.is_file():
            return FileResponse(index)
        if not path:
            return JSONResponse({"service": "PushPilot", "mode": "simulation", "frontend": "Build frontend/dist to serve the operator workspace.", "health": "/api/health"})
        raise HTTPException(404, "Frontend asset not found.")

    return application


# Uvicorn discovers this object. Lifespan owns all configuration and I/O.
app = create_app()
