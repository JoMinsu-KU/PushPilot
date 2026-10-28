"""Authenticated loopback commissioning API; no simulation state is mutated."""
from contextlib import asynccontextmanager
import secrets
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from .models import ControlChange, Installation, LocalBaseInstallation, LocalContactInstallation, PlanarTeachingInstallation, Observation, Reconciliation, Review, RobotCommand, StrictModel
from .store import ControlError


class Hold(StrictModel):
    reason: str = Field(min_length=1, max_length=500)


def create_app(service, token: str, *, manage_lifecycle=True, external_review_validator=None, external_observation_validator=None):
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("A private local control token is required.")

    @asynccontextmanager
    async def lifespan(app):
        if manage_lifecycle:
            service.start()
        try:
            yield
        finally:
            if manage_lifecycle:
                service.stop()

    app = FastAPI(title="PushPilot Robot Commissioning", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.url.path != "/health":
            supplied = request.headers.get("X-PushPilot-Control-Token", "")
            if not secrets.compare_digest(supplied, token) or request.headers.get("origin"):
                return JSONResponse({"code": "CONTROL_AUTH_REQUIRED", "message": "Use the local authenticated commissioning client."}, status_code=401)
        if request.method == "POST":
            try:
                size = int(request.headers.get("content-length", "-1"))
            except ValueError:
                size = -1
            if not 0 <= size <= 65536 or request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"code": "BOUNDED_JSON_REQUIRED", "message": "Send a bounded JSON request with Content-Length."}, status_code=413)
        try:
            return await call_next(request)
        except Exception:
            # A failed request (including ledger I/O) must not terminate the API
            # or the independent receiver heartbeat. Never synthesize success.
            return JSONResponse({"code": "CONTROL_REQUEST_FAILED", "message": "Request failed. Inspect current status using the same request ID; do not resend motion with a new ID."}, status_code=503)

    @app.exception_handler(ControlError)
    async def control_error(request, error):
        return JSONResponse({"code": error.code, "message": str(error)}, status_code=error.status)

    @app.get("/health")
    def health():
        return {"service": "pushpilot.robot-control", "mode": "physical_commissioning" if service.physical else "mock",
                "worker_alive": bool(service.thread and service.thread.is_alive()), "automatic_replay": False}

    @app.get("/v1/status")
    def status():
        return service.status()

    @app.get("/v1/events")
    def events(after: int = Query(default=0, ge=0)):
        return {"events": service.journal.events(after)}

    @app.post("/v1/installation")
    def install(value: Installation | LocalBaseInstallation | LocalContactInstallation | PlanarTeachingInstallation):
        return service.install(value.model_dump(mode="json", by_alias=True))

    @app.post("/v1/arm")
    def arm(value: ControlChange):
        return service.arm(value.model_dump(mode="json"))

    @app.post("/v1/hold")
    def hold(value: Hold):
        return service.hold(value.reason)

    @app.post("/v1/observations")
    def observe(value: Observation):
        data = value.model_dump(mode="json")
        if value.source != "operator":
            if external_observation_validator is None:
                raise ControlError("PHYSICAL_OBSERVATION_BRIDGE_NOT_CONNECTED", "Automated observation provenance requires a configured physical-observation bridge.", 503)
            external_observation_validator(data)
        return service.observe(data)

    @app.post("/v1/commands", status_code=202)
    def submit(value: RobotCommand):
        return service.submit(value.model_dump(mode="json"))

    @app.get("/v1/commands/{request_id}")
    def command(request_id: UUID):
        return service.journal.get(str(request_id))

    @app.post("/v1/commands/{request_id}/cancel")
    def cancel(request_id: UUID):
        return service.cancel(str(request_id))

    @app.post("/v1/commands/{request_id}/review")
    def review(request_id: UUID, value: Review):
        data = value.model_dump(mode="json")
        if value.source == "external_meta_bridge":
            if external_review_validator is None:
                raise ControlError("PHYSICAL_META_BRIDGE_NOT_CONNECTED", "Self-reported model results cannot substitute for a bound physical-review integration.", 503)
            external_review_validator(str(request_id), data)
        return service.review(str(request_id), data)

    @app.post("/v1/commands/{request_id}/reconcile")
    def reconcile(request_id: UUID, value: Reconciliation):
        return service.reconcile(str(request_id), value.model_dump(mode="json"))

    return app
