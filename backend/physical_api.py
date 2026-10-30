"""Same-origin physical controls; the hardware token stays on the server."""
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/v1/physical")


class PhysicalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_revision: int = Field(ge=0, strict=True)


class StartCommand(PhysicalCommand):
    workspace_session_id: str = Field(min_length=1, max_length=100)
    plan_id: str = Field(min_length=1, max_length=100)
    plan_revision: int = Field(ge=0, strict=True)
    destination: str = Field(min_length=1, max_length=100)
    route_nodes: list[str] = Field(min_length=2, max_length=128)
    map_id: str = Field(min_length=1, max_length=100)
    map_version: str = Field(min_length=1, max_length=100)
    map_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResetCommand(PhysicalCommand):
    mission_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=10, max_length=500)


def same_origin(request):
    origin = request.headers.get("origin")
    parsed = urlsplit(origin or "")
    if (not origin or parsed.scheme != request.url.scheme or parsed.netloc != request.headers.get("host")
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or request.headers.get("sec-fetch-site") not in {None, "same-origin"}):
        raise HTTPException(403, "Physical controls require a same-origin browser request.")


@router.get("/status")
def status(request: Request):
    return request.app.state.physical.snapshot()


@router.post("/start")
async def start(command: StartCommand, request: Request):
    same_origin(request)
    return await request.app.state.physical.start(command.model_dump(mode="json"))


@router.post("/stop")
async def stop(command: PhysicalCommand, request: Request):
    same_origin(request)
    return await request.app.state.physical.stop(command.model_dump(mode="json"))


@router.post("/reset")
async def reset(command: ResetCommand, request: Request):
    same_origin(request)
    return await request.app.state.physical.reset(command.model_dump(mode="json"))


@router.post("/resume")
async def resume(command: ResetCommand, request: Request):
    same_origin(request)
    return await request.app.state.physical.resume(command.model_dump(mode="json"))


@router.post('/continue-c19')
async def continue_c19(command: ResetCommand, request: Request):
    same_origin(request)
    return await request.app.state.physical.resume({**command.model_dump(mode='json'), 'omit_c19_review': True})
