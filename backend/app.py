"""ASGI simulation API, frontend host and optional preview-only live camera."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
import os
from pathlib import Path
from typing import Literal
from uuid import UUID
from tempfile import TemporaryDirectory

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.core import CommandError, WorkspaceStore
from backend.meta import GoalProvider, MetaGoalProvider
from backend.settings import Settings
from backend.maps import MapDefinition
from backend.scene import SceneError, SceneStore
from backend.scene_api import router as scene_router
from backend.action_review import ActionReviewProvider, ActionReviewService
from backend.live_camera import LiveCamera


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


class RecordedActionReviewCommand(Command):
    review_id: UUID
    expected_scene_revision: int = Field(ge=0, strict=True)
    before_frame_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    after_frame_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    expected_visual: str = Field(min_length=1, max_length=1000)


class LiveRegistrationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    epoch: str = Field(pattern=r"^[a-f0-9]{32}$")
    frame_id: str = Field(pattern=r"^[a-f0-9]{32}$")


def create_app(settings: Settings | None = None, *, db_path: str | None = None,
               provider: GoalProvider | None = None,
               action_review_provider: ActionReviewProvider | None = None,
               live_camera_url: str | None = None) -> FastAPI:
    """Create an app without reading credentials or initializing a database yet."""
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configured = settings or (Settings(db_path=db_path) if db_path else Settings.from_environment())
        if db_path is not None:
            configured = replace(configured, db_path=db_path)
        map_definition = MapDefinition(configured.map_path)
        application.state.store = WorkspaceStore(
            configured.db_path,
            provider=provider or MetaGoalProvider(configured.meta_api_key, map_definition),
            muse_configured=bool(configured.meta_api_key),
            signal_ttl_seconds=configured.signal_ttl_seconds,
            map_definition=map_definition,
        )
        temporary_scene = TemporaryDirectory() if configured.db_path == ":memory:" and configured.scene_dir is None else None
        scene_dir = configured.scene_dir or (temporary_scene.name if temporary_scene else str(Path(configured.db_path).parent / "scene"))
        application.state.scene = SceneStore(scene_dir, map_definition=application.state.store.map_definition,
                                           meta_api_key=configured.meta_api_key)
        application.state.action_reviews = ActionReviewService(application.state.store, application.state.scene,
                                                               api_key=configured.meta_api_key, provider=action_review_provider)
        application.state.frontend = Path(configured.frontend_dist).resolve()
        application.state.live_camera = LiveCamera(
            live_camera_url if live_camera_url is not None else os.environ.get("PUSHPILOT_LIVE_CAMERA_URL", ""),
            application.state.store.map_definition, application.state.scene._detect,
            application.state.scene._candidate,
        )
        application.state.live_camera.start()
        try:
            yield
        finally:
            application.state.live_camera.close()
            application.state.scene.close()
            application.state.store.close()
            if temporary_scene:
                temporary_scene.cleanup()

    application = FastAPI(title="PushPilot Workspace", version="0.1.0", lifespan=lifespan,
                          docs_url=None, redoc_url=None)

    @application.exception_handler(CommandError)
    async def command_error(_request: Request, error: CommandError):
        return JSONResponse({"detail": error.message}, status_code=error.status)

    @application.exception_handler(SceneError)
    async def recorded_error(_request: Request, error: SceneError):
        return JSONResponse({"detail": {"code": error.code, "message": str(error)}}, status_code=error.status_code)

    @application.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if (request.url.path.startswith("/api/v1/live-camera/frames/")
                and request.url.path.endswith("/image") and response.status_code == 200):
            # Unique frame URLs permit decode-before-swap without another fetch.
            # Private browser caching does not persist frames in SceneStore.
            response.headers["Cache-Control"] = "private, max-age=30, immutable"
        elif request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/api/health")
    def health(request: Request):
        preview = request.app.state.live_camera.snapshot()
        return {"status": "ok", "mode": "simulation", "schema_version": "pushpilot.workspace.v1",
                "hardware_connected": False, "robot_connected": False,
                "camera_preview_connected": preview["state"] == "live"}

    @application.get("/api/v1/live-camera")
    def live_camera(request: Request):
        return request.app.state.live_camera.snapshot()

    @application.get("/api/v1/live-camera/frames/{frame_id}/image")
    def live_camera_image(request: Request, frame_id: str):
        return Response(request.app.state.live_camera.image(frame_id), media_type="image/jpeg")

    @application.post("/api/v1/live-camera/registration")
    def live_camera_registration(request: Request, command: LiveRegistrationCommand):
        return request.app.state.live_camera.register(command.epoch, command.frame_id)

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

    @application.post("/api/v1/action-reviews")
    async def action_review(request: Request, command: RecordedActionReviewCommand):
        payload, status = await request.app.state.action_reviews.review(command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

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
