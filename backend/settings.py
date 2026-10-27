"""Server-only settings. Importing this module does not inspect local secrets."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    db_path: str = str(ROOT / "runtime" / "workspace.sqlite3")
    meta_api_key: str = field(default="", repr=False)
    signal_ttl_seconds: float = 30.0
    frontend_dist: str = str(ROOT / "frontend" / "dist")

    @classmethod
    def from_environment(cls) -> "Settings":
        """Read the optional local credential only when the ASGI server starts."""
        values: dict[str, str] = {}
        env_path = ROOT / ".env"
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8-sig").splitlines():
                key, separator, value = line.strip().partition("=")
                if separator and key in {"META_API_KEY", "PUSHPILOT_STATE_PATH"}:
                    values[key] = value.strip().strip("\"'")
        return cls(
            db_path=os.environ.get("PUSHPILOT_STATE_PATH", values.get("PUSHPILOT_STATE_PATH", cls.db_path)),
            meta_api_key=os.environ.get("META_API_KEY", values.get("META_API_KEY", "")),
            frontend_dist=os.environ.get("PUSHPILOT_FRONTEND_DIST", cls.frontend_dist),
        )
