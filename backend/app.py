"""ASGI simulation API, frontend host and optional preview-only live camera."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
import os
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5
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
from backend.live_intelligence import LiveIntelligenceService
from backend.voice import VoiceService
from backend.voice_api import router as voice_router
from backend.map_api import router as map_router
from backend.signal_watch import SignalWatchService
from backend.display_registration import DisplayRegistrationService
from backend.physical_mission import PhysicalMissionService
from backend.physical_api import router as physical_router


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_revision: int = Field(ge=0, strict=True)


class RouteConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    departure: Literal["any", "north", "east", "south", "west"] = "any"
    first_turn: Literal["any", "left", "right", "straight"] = "any"
    via_nodes: list[str] = Field(default_factory=list, max_length=64)
    avoid_nodes: list[str] = Field(default_factory=list, max_length=64)


class GoalCommand(Command):
    text: str = Field(min_length=1, max_length=2000)
    provider: Literal["demo", "meta"] = "demo"
    source: Literal["typed", "voice"] = "typed"
    planning_mode: Literal["live", "symbolic"] | None = None
    transcript_id: str | None = Field(default=None, min_length=1, max_length=80)
    route_constraints: RouteConstraints | None = None


class LiveActionReviewCommand(Command):
    review_id: UUID
    expected_visual: str = Field(min_length=1, max_length=1000)


class LiveGoalCommand(GoalCommand):
    provider: Literal["meta"] = "meta"


class SignalWaitCommand(Command):
    max_attempts: int = Field(default=3, ge=1, le=3, strict=True)
    interval_seconds: float = Field(default=2.0, ge=0.5, le=10, strict=True)


class SignalWatchCommand(Command):
    max_attempts: int = Field(default=30, ge=1, le=60, strict=True)
    interval_seconds: float = Field(default=2.0, ge=0.5, le=10, strict=True)
    max_duration_seconds: float = Field(default=300.0, ge=1, le=900, strict=True)


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


class LiveResumeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    epoch: str = Field(pattern=r"^[a-f0-9]{32}$")


def create_app(settings: Settings | None = None, *, db_path: str | None = None,
               provider: GoalProvider | None = None,
               action_review_provider: ActionReviewProvider | None = None,
               planning_provider=None, live_review_provider=None, voice_provider=None,
               automatic_signal_watch: bool = True,
               live_camera_url: str | None = None, physical_driver=None) -> FastAPI:
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
        application.state.display_registration = DisplayRegistrationService(application.state.store, application.state.live_camera)
        application.state.voice = VoiceService(api_key=configured.meta_api_key, provider=voice_provider)
        application.state.live_intelligence = LiveIntelligenceService(
            application.state.store, application.state.live_camera, api_key=configured.meta_api_key,
            planning_provider=planning_provider, review_provider=live_review_provider,
            voice=application.state.voice,
        )
        application.state.store.live_planning_enabled = bool(application.state.live_camera.url)
        application.state.store.voice_backend_enabled = bool(configured.meta_api_key)
        application.state.signal_watch = SignalWatchService(application.state.store, application.state.live_intelligence)
        application.state.automatic_signal_watch = automatic_signal_watch
        driver = physical_driver
        if driver is None and configured.physical_config_path:
            from backend.robot_control.mission_driver import ConfigBackedMissionDriver
            from backend.robot_control.mission_observer import MissionObserver
            driver = ConfigBackedMissionDriver(configured.physical_config_path,
                observer_callback=MissionObserver(configured.meta_api_key))
        application.state.physical = PhysicalMissionService(application.state.store,
            Path(scene_dir) / "physical-mission", driver=driver)
        await application.state.physical.refresh_readiness()
        application.state.physical.start_monitor()
        try:
            yield
        finally:
            await application.state.physical.close()
            await application.state.signal_watch.close()
            application.state.live_camera.close()
            application.state.voice.close()
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
        snapshot = request.app.state.live_camera.snapshot()
        snapshot["saved_reference_available"] = request.app.state.display_registration.available()
        return snapshot

    @application.get("/api/v1/live-camera/frames/{frame_id}/image")
    def live_camera_image(request: Request, frame_id: str):
        return Response(request.app.state.live_camera.image(frame_id), media_type="image/jpeg")

    @application.post("/api/v1/live-camera/registration")
    def live_camera_registration(request: Request, command: LiveRegistrationCommand):
        return request.app.state.display_registration.register(command.epoch, command.frame_id)

    @application.post("/api/v1/live-camera/registration/resume")
    def live_camera_resume(request: Request, command: LiveResumeCommand):
        return request.app.state.display_registration.resume(command.epoch)

    @application.get("/api/v1/state")
    def state(request: Request):
        return request.app.state.store.snapshot()

    def dispatch(request: Request, action: str, command: Command):
        payload, status = request.app.state.store.execute(action, command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.post("/api/v1/goals")
    async def goal(request: Request, command: GoalCommand):
        use_live = command.planning_mode == "live" or (command.planning_mode is None and command.provider == "meta" and bool(request.app.state.live_camera.url))
        if use_live or command.source == "voice":
            if command.provider != "meta":
                raise CommandError("Confirmed voice and live-image plans use the MUSE provider.", 422)
            return await live_plan(request, command)
        if command.route_constraints is not None:
            raise CommandError("Route constraints require live MUSE planning; symbolic mode interprets only a destination.", 422)
        return dispatch(request, "goals", command)

    @application.post("/api/v1/plans/live")
    async def live_plan(request: Request, command: LiveGoalCommand):
        if command.provider != "meta":
            raise CommandError("Select the MUSE provider for live-image planning.", 422)
        payload, status = await request.app.state.live_intelligence.plan(command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.get("/api/v1/live-intelligence/operations")
    def live_operations(request: Request):
        return request.app.state.live_intelligence.operations()

    @application.get("/api/v1/live-evidence/frames/{frame_id}/image")
    def live_evidence_image(request: Request, frame_id: str):
        return Response(request.app.state.live_intelligence.frame(frame_id), media_type="image/jpeg")

    @application.post("/api/v1/live-actions/advance")
    def live_advance(request: Request, command: Command):
        payload, status = request.app.state.live_intelligence.advance(command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.post("/api/v1/live-actions/reviews")
    async def live_action_review(request: Request, command: LiveActionReviewCommand):
        payload, status = await request.app.state.live_intelligence.review_action(command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.post("/api/v1/live-actions/run")
    async def live_run(request: Request, command: Command):
        payload, status = await request.app.state.live_intelligence.run(command.model_dump(mode="json"))
        if (request.app.state.automatic_signal_watch and status == 200 and payload["state"] == "WAITING_SIGNAL"
                and (payload.get("plan") or {}).get("planning")):
            # A configured stop can watch automatically after its accepted review.
            # Missing real target metadata keeps the reviewed simulation stopped.
            try:
                payload, status = await request.app.state.signal_watch.start({
                    "request_id": str(uuid5(command.request_id, "automatic-post-stop-watch")),
                    "expected_revision": payload["revision"],
                })
            except (CommandError, SceneError):
                pass
        return JSONResponse(payload, status_code=status)

    @application.post("/api/v1/live-actions/reobserve")
    def live_reobserve(request: Request, command: Command):
        payload, status = request.app.state.live_intelligence.reobserve(command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.post("/api/v1/live-signals/reviews")
    async def live_signal_review(request: Request, command: Command):
        payload, status = await request.app.state.live_intelligence.review_signal(command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.post("/api/v1/live-signals/wait")
    async def live_signal_wait(request: Request, command: SignalWaitCommand):
        payload, status = await request.app.state.live_intelligence.wait_signal(command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.post("/api/v1/live-signals/watch")
    async def live_signal_watch(request: Request, command: SignalWatchCommand):
        payload, status = await request.app.state.signal_watch.start(command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.post("/api/v1/live-signals/watch/stop")
    async def live_signal_watch_stop(request: Request, command: Command):
        payload, status = await request.app.state.signal_watch.stop(command.model_dump(mode="json"))
        return JSONResponse(payload, status_code=status)

    @application.get("/api/v1/live-signals/watch")
    def live_signal_watch_status(request: Request):
        return {"signal_watch": request.app.state.store.snapshot().get("signal_watch"), "motion_authority": False}

    @application.post("/api/v1/approve")
    def approve(request: Request, command: ApprovalCommand):
        with request.app.state.store._lock:
            # A replay returns the original receipt without admitting new work.
            prior = request.app.state.store._db.execute("SELECT id FROM requests WHERE id=?", (str(command.request_id),)).fetchone()
            if prior is None:
                request.app.state.live_intelligence.require_current_live_view(request.app.state.store._load())
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
        if (request.app.state.store.snapshot().get("plan") or {}).get("planning"):
            return live_advance(request, command)
        return dispatch(request, "advance", command)

    @application.post("/api/v1/reobserve")
    def reobserve(request: Request, command: Command):
        if (request.app.state.store.snapshot().get("plan") or {}).get("planning"):
            return live_reobserve(request, command)
        return dispatch(request, "reobserve", command)

    @application.post("/api/v1/cancel")
    def cancel(request: Request, command: Command):
        return dispatch(request, "cancel", command)

    @application.post("/api/v1/reset")
    def reset(request: Request, command: Command):
        return dispatch(request, "reset", command)

    application.include_router(scene_router)
    application.include_router(voice_router)
    application.include_router(map_router)
    application.include_router(physical_router)

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
