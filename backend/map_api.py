"""Read-only validation of a proposed replacement drawing map."""
from __future__ import annotations

import json
import math

from fastapi import APIRouter, HTTPException, Request

from .maps import MapDefinition


router = APIRouter(prefix="/api/v1/maps")
MAX_MAP_BYTES = 1024 * 1024
COLLECTION_LIMITS = {"nodes": 500, "edges": 2000, "markers": 50, "building_panels": 500,
                     "signal_targets": 500, "destinations": 500}
STARTUP_TEMPLATE = "python tools/serve.py --map-path <reviewed-map.json> --state-path <private-workspace.sqlite3>"


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object keys are unsupported.")
        result[key] = value
    return result


def _constant(_value: str):
    raise ValueError("Nonfinite JSON numbers are unsupported.")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite JSON numbers are unsupported.")
    return result


def validate_definition(data: dict) -> dict:
    """Return a preview only; never update active map or evidence bindings."""
    if not isinstance(data, dict):
        raise ValueError("The definition field must contain a map object.")
    for key, limit in COLLECTION_LIMITS.items():
        values = data.get(key, [])
        if not isinstance(values, list) or len(values) > limit:
            raise ValueError(f"The map {key} collection must be a list of at most {limit} entries.")
    definition = MapDefinition.from_data(data)
    audit = definition.planning_audit()
    warnings = ["Drawing geometry does not qualify physical pushing, turning, stopping, or camera-to-robot coordinates.",
                "A replacement requires new map-bound plans and explicit camera display registration."]
    if not audit["configured_signal_target_count"]:
        warnings.append("No approach-specific signal targets are configured; MUSE stopped-signal review remains unavailable.")
    if not definition.camera_registration_supported:
        warnings.append("This spatial-only map does not support live camera registration or live-image planning. No marker positions were inferred.")
    if audit["unreachable_within_route_limit"]:
        warnings.append("One or more destinations cannot be reached by a simple directed path within the route node limit.")
    return {"schema_version": "pushpilot.map-validation.v1", "valid": audit["status"] == "passed",
            "mode": "preview_only", "installed": False,
            "map": {"id": definition.id, "version": definition.version, "geometry_hash": definition.geometry_hash,
                    "title": data["title"], "temporary": True, "physical_execution_enabled": False,
                    "camera_registration_supported": definition.camera_registration_supported},
            "counts": {"nodes": audit["node_count"], "edges": len(data.get("edges", [])),
                       "directed_edges": audit["directed_edge_count"], "destinations": len(audit["destinations"]),
                       "signal_targets": audit["configured_signal_target_count"]},
            "routing": {"declared_start": audit["declared_start"], "max_route_nodes": audit["max_route_nodes"],
                        "destinations": audit["destinations"],
                        "unreachable_within_route_limit": audit["unreachable_within_route_limit"]},
            "warnings": warnings,
            "startup": {"command_template": STARTUP_TEMPLATE, "requires_application_restart": True,
                        "restarts_camera_or_robot": False},
            "equipment_contacted": False}


@router.post("/validate")
async def validate_map(request: Request):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise _error(415, "MAP_CONTENT_TYPE", "Map validation accepts application/json only.")
    length = request.headers.get("content-length")
    if length and (not length.isascii() or not length.isdecimal() or len(length) > 10 or int(length) > MAX_MAP_BYTES):
        raise _error(413, "MAP_SIZE", "A map validation request must contain at most 1 MiB.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_MAP_BYTES:
            raise _error(413, "MAP_SIZE", "A map validation request must contain at most 1 MiB.")
        body.extend(chunk)
    try:
        payload = json.loads(body.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                             parse_constant=_constant, parse_float=_finite_float)
    except (UnicodeError, ValueError, RecursionError):
        raise _error(400, "MAP_JSON", "Supply a bounded UTF-8 JSON object with unique keys and finite numbers.") from None
    if not isinstance(payload, dict) or set(payload) != {"definition"}:
        raise _error(422, "MAP_REQUEST", "Supply only the definition field containing the proposed map object.")
    try:
        return validate_definition(payload["definition"])
    except ValueError as error:
        raise _error(422, "MAP_DEFINITION", str(error)) from None
    except (TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise _error(422, "MAP_DEFINITION", "The supplied map definition contains malformed fields.") from None
