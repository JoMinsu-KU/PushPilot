"""Private recorded-frame endpoints. No camera or robot control endpoints exist."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .scene import MAX_IMAGE_BYTES, SceneError

router = APIRouter(prefix="/api/v1")


class RegistrationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=0)
    frame_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class InspectionCommand(RegistrationCommand):
    expected: str = Field(min_length=1, max_length=1000)


def _error(error: SceneError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail={"code": error.code, "message": str(error)})


@router.get("/map")
def temporary_map(request: Request):
    return request.app.state.scene.map_definition.snapshot()


@router.get("/scene")
def scene_state(request: Request):
    return request.app.state.scene.snapshot()


@router.post("/scene/frames")
async def upload_frame(request: Request, file: UploadFile = File(...), captured_at: str | None = Form(None)):
    try:
        content_length = request.headers.get("content-length")
        if content_length and (not content_length.isdigit() or int(content_length) > MAX_IMAGE_BYTES + 65536):
            raise SceneError(413, "Recorded images must contain at most 8 MiB.", "IMAGE_SIZE")
        data = await file.read(MAX_IMAGE_BYTES + 1)
        return request.app.state.scene.ingest(data, captured_at=captured_at, source="uploaded")
    except SceneError as error:
        raise _error(error) from None
    finally:
        await file.close()


@router.get("/scene/frames/{frame_id}/image")
def frame_image(request: Request, frame_id: str):
    try:
        path, media_type = request.app.state.scene.frame_file(frame_id)
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})
    except SceneError as error:
        raise _error(error) from None


@router.post("/scene/registration")
def register_view(request: Request, command: RegistrationCommand):
    try:
        return request.app.state.scene.register(command.expected_revision, command.frame_id)
    except SceneError as error:
        raise _error(error) from None


@router.post("/scene/reviews")
async def inspect_scene(request: Request, command: InspectionCommand):
    try:
        return await request.app.state.scene.inspect(command.expected_revision, command.frame_id, command.expected)
    except SceneError as error:
        raise _error(error) from None
