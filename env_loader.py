"""Load key=value pairs from settings.env into os.environ (without overwriting)."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.env"


def load_settings(path: Path | None = None) -> Path | None:
    settings = path or SETTINGS_FILE
    if not settings.exists():
        return None
    for raw in settings.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value
    return settings


# auto-load on import
load_settings()
