"""Export a private city GLB with clean asphalt, preserving all geometry and markings."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA256 = "8ecbdf4d4c0a5a58b502f5366a96bc37fa2ce2cbfec9af14896d63743ca49f78"
MODEL_SOURCE = ROOT / "frontend/public/models/private/pushpilot-city.glb"
MODEL_DESTINATION = MODEL_SOURCE.with_name("pushpilot-city-clean-roads.glb")
MAX_MODEL_BYTES = 32 * 1024 * 1024
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
ROAD_MATERIAL = "asphalt_photo"
ROAD_SRGB = (0x45, 0x4C, 0x50)


def _linear_srgb(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("The GLB JSON contains an ambiguous duplicate property.")
        result[key] = value
    return result


def _document(data: bytes) -> tuple[dict, int]:
    if not 20 <= len(data) <= MAX_MODEL_BYTES:
        raise ValueError("The source must be a bounded, complete GLB 2 file.")
    magic, version, total = struct.unpack_from("<III", data)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise ValueError("The source must be a complete GLB 2 file.")
    offset = 12
    chunks = []
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError("The GLB has an incomplete chunk header.")
        length, kind = struct.unpack_from("<II", data, offset)
        end = offset + 8 + length
        if length % 4 or end > len(data):
            raise ValueError("The GLB has an incomplete or unaligned chunk.")
        chunks.append((kind, offset + 8, end))
        offset = end
    if not chunks or chunks[0][0] != JSON_CHUNK or sum(kind == JSON_CHUNK for kind, _, _ in chunks) != 1:
        raise ValueError("The GLB must begin with exactly one JSON chunk.")
    if sum(kind == BIN_CHUNK for kind, _, _ in chunks) > 1:
        raise ValueError("The GLB contains ambiguous binary chunks.")
    if any(kind == BIN_CHUNK for kind, _, _ in chunks) and (len(chunks) < 2 or chunks[1][0] != BIN_CHUNK):
        raise ValueError("The embedded binary chunk must immediately follow the JSON chunk.")
    try:
        document = json.loads(data[chunks[0][1]:chunks[0][2]].decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("The GLB JSON chunk is invalid.") from error
    if not isinstance(document, dict) or not isinstance(document.get("asset"), dict) or document["asset"].get("version") != "2.0":
        raise ValueError("The source must declare a glTF 2.0 asset.")
    buffers = document.get("buffers", [])
    images = document.get("images", [])
    views = document.get("bufferViews", [])
    if any(not isinstance(items, list) or any(not isinstance(item, dict) for item in items) for items in (buffers, images, views)):
        raise ValueError("The embedded buffer and image declarations are invalid.")
    if len(buffers) > 1 or any("uri" in item for item in buffers + images):
        raise ValueError("The city model must be self-contained, without external image or buffer URIs.")
    binary_lengths = [end - start for kind, start, end in chunks if kind == BIN_CHUNK]
    declared = buffers[0].get("byteLength") if buffers else 0
    if type(declared) is not int or declared < 0 or (declared and not binary_lengths):
        raise ValueError("The embedded binary buffer is missing or invalid.")
    if binary_lengths and not declared <= binary_lengths[0] <= declared + 3:
        raise ValueError("The embedded binary chunk does not match its declared buffer length.")
    for view in views:
        start, length = view.get("byteOffset", 0), view.get("byteLength")
        if not buffers or view.get("buffer") != 0 or type(start) is not int or type(length) is not int or min(start, length) < 0 or start + length > declared:
            raise ValueError("An embedded buffer view is out of bounds.")
    for image in images:
        index = image.get("bufferView")
        if type(index) is not int or not 0 <= index < len(views):
            raise ValueError("A city texture is not embedded in a valid buffer view.")
    return document, chunks[0][2]


def clean_road_model(data: bytes, expected_sha256: str = MODEL_SHA256) -> bytes:
    """Change only the reviewed road material; retain every post-JSON chunk byte-for-byte."""
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("The city model differs from the reviewed user-supplied asset.")
    document, json_end = _document(data)
    materials = document.get("materials", [])
    if not isinstance(materials, list) or any(not isinstance(material, dict) for material in materials):
        raise ValueError("The city model has invalid material declarations.")
    roads = [material for material in materials if material.get("name") == ROAD_MATERIAL]
    if len(roads) != 1:
        raise ValueError("The city model must contain exactly one asphalt_photo material.")
    pbr = roads[0].get("pbrMetallicRoughness")
    if not isinstance(pbr, dict):
        raise ValueError("The reviewed asphalt material has no valid PBR definition.")
    pbr.pop("baseColorTexture", None)
    pbr["baseColorFactor"] = [*map(_linear_srgb, ROAD_SRGB), 1]
    pbr["roughnessFactor"] = 0.95
    pbr["metallicFactor"] = 0
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    remainder = data[json_end:]
    return struct.pack("<IIIII", 0x46546C67, 2, 20 + len(encoded) + len(remainder), len(encoded), JSON_CHUNK) + encoded + remainder


def _refuse_links(path: Path) -> None:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("City model paths through symbolic links are unsupported.")


def install(source: Path = MODEL_SOURCE, destination: Path = MODEL_DESTINATION, *, expected_sha256: str = MODEL_SHA256) -> dict:
    """Atomically create an idempotent derivative without replacing the original or another asset."""
    source, destination = Path(source), Path(destination)
    _refuse_links(source)
    _refuse_links(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("The clean-road output must be separate from the original city model.")
    if not source.is_file() or not 20 <= source.stat().st_size <= MAX_MODEL_BYTES:
        raise ValueError("The source must be a bounded city GLB file.")
    data = clean_road_model(source.read_bytes(), expected_sha256=expected_sha256)
    digest = hashlib.sha256(data).hexdigest()
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != data:
            raise ValueError("A different clean-road output already exists; preserve it for review.")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        _refuse_links(destination)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".city-roads-", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(data)
                temporary.flush()
                os.fsync(temporary.fileno())
            try:
                # Linking publishes complete bytes atomically and cannot clobber an existing file.
                os.link(temporary_path, destination)
            except FileExistsError:
                _refuse_links(destination)
                if not destination.is_file() or destination.read_bytes() != data:
                    raise ValueError("A different clean-road output appeared during installation.") from None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    return {"installed": str(destination), "bytes": len(data), "sha256": digest,
            "source_sha256": expected_sha256, "road_srgb": "#454c50", "road_roughness": 0.95,
            "geometry_changed": False, "source_preserved": True, "motion_authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", default=MODEL_SOURCE, help="Original private city GLB.")
    parser.add_argument("--output", type=Path, default=None, help="Separate clean-road GLB output.")
    arguments = parser.parse_args()
    output = arguments.output or arguments.source.with_name("pushpilot-city-clean-roads.glb")
    try:
        result = install(arguments.source, output)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Clean-road city export failed: {error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
