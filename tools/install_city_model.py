"""Install the explicitly supplied private city GLB without extracting source or executing scripts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODEL_ENTRY = "web/PushPilot_city_web.glb"
MODEL_SHA256 = "8ecbdf4d4c0a5a58b502f5366a96bc37fa2ce2cbfec9af14896d63743ca49f78"
MAX_MODEL_BYTES = 32 * 1024 * 1024
MODEL_DESTINATION = ROOT / "frontend/public/models/private/pushpilot-city.glb"


def read_model(package: Path, *, expected_sha256: str = MODEL_SHA256) -> bytes:
    """Read only one fixed archive entry and reject a different or externally linked model."""
    with zipfile.ZipFile(package) as archive:
        matches = [entry for entry in archive.infolist() if entry.filename == MODEL_ENTRY]
        if len(matches) != 1 or not 20 <= matches[0].file_size <= MAX_MODEL_BYTES:
            raise ValueError("The package must contain one bounded city GLB at the expected path.")
        data = archive.read(matches[0])
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("The city model differs from the reviewed user-supplied asset.")
    magic, version, total = struct.unpack_from("<III", data)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise ValueError("The city asset is not a complete GLB 2 file.")
    length, kind = struct.unpack_from("<II", data, 12)
    if kind != 0x4E4F534A or length > len(data) - 20:
        raise ValueError("The city model has no valid embedded GLB JSON chunk.")
    document = json.loads(data[20:20 + length].decode("utf-8"))
    if any("uri" in item for key in ("images", "buffers") for item in document.get(key, [])):
        raise ValueError("The city model must embed its textures and geometry, without external URLs.")
    return data


def install(package: Path, destination: Path = MODEL_DESTINATION) -> dict:
    data = read_model(package)
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("Model installation through symbolic links is unsupported.")
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("A different model already exists; preserve it and review replacement separately.")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".city-", suffix=".tmp", delete=False) as temporary:
            temporary.write(data)
            temporary_path = Path(temporary.name)
        try:
            temporary_path.replace(destination)
        finally:
            temporary_path.unlink(missing_ok=True)
    return {"installed": str(destination), "bytes": len(data), "sha256": MODEL_SHA256,
            "source": "user_supplied_private_artwork", "scripts_executed": False, "motion_authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="Path to the supplied PushPilot city ZIP.")
    arguments = parser.parse_args()
    try:
        result = install(arguments.package)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        parser.exit(1, f"City model installation failed: {error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
