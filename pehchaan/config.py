"""Load config/settings.yaml once. Override the path with env PEHCHAAN_CONFIG."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@lru_cache(maxsize=1)
def settings() -> dict:
    load_dotenv()
    path = Path(os.environ.get("PEHCHAAN_CONFIG", ROOT / "config" / "settings.yaml"))
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def path(key: str) -> Path:
    """Resolve a path from settings.paths relative to the repo root."""
    return ROOT / settings()["paths"][key]
