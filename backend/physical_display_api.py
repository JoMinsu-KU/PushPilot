"""GET-only presentation endpoint; no command path or motion authority."""
from fastapi import APIRouter, Request

from backend.physical_display import unavailable

router = APIRouter(prefix="/api/v1/physical")


@router.get("/display")
def display(request: Request):
    try:
        service = getattr(request.app.state, "physical_display", None)
        return service.snapshot() if service is not None else unavailable()
    except Exception:
        # An optional display cache must not fail the control/status endpoints.
        return unavailable()
