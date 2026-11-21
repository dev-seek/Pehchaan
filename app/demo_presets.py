"""Read the demo allowlist and expose only its packaged development and demo audio."""
from __future__ import annotations

import json
from pathlib import Path

from pehchaan.config import ROOT, path, settings


def catalog() -> dict[str, dict]:
    file = ROOT / settings()["demo"]["presets"]
    if not file.is_file():
        return {}
    rows = json.loads(file.read_text(encoding="utf-8"))
    return {row["id"]: row for row in rows}


def public_preset(preset: dict) -> dict:
    visible = ("id", "label", "voice_source", "context", "context_adv", "description", "initial_level")
    return {**{k: preset[k] for k in visible if k in preset}, "audio_url": f"/api/demo/presets/{preset['id']}/audio"}


def preset_audio(preset: dict) -> Path | None:
    file = (ROOT / preset["audio"]).resolve()
    allowed = ((path("audio") / "dev").resolve(), (ROOT / "data/demo").resolve())
    if not file.is_file() or not any(file.is_relative_to(directory) for directory in allowed):
        return None
    return file
