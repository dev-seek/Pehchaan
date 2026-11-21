"""Read the demo allowlist and expose only packaged development, demo and consented real-voice sample audio."""
from __future__ import annotations

import json
from pathlib import Path

from pehchaan.config import ROOT, path, settings

_PUBLIC_FIELDS = ("id", "label", "voice_source", "context", "context_adv", "description", "initial_level", "kind",
                  "language", "watch_for", "featured")


def _rows(file: Path) -> list[dict]:
    return json.loads(file.read_text(encoding="utf-8")) if file.is_file() else []


def real_samples() -> list[dict]:
    """Scripts for the voice studio. A sample appears on the site only after its recording exists."""
    return _rows(ROOT / settings()["demo"]["real_samples"])


def catalog() -> dict[str, dict]:
    rows = [*real_samples(), *_rows(ROOT / settings()["demo"]["presets"])]
    return {row["id"]: row for row in rows}


def public_preset(preset: dict) -> dict:
    fields = {k: preset[k] for k in _PUBLIC_FIELDS if k in preset}
    return {"kind": "synthetic", **fields, "audio_url": f"/api/demo/presets/{preset['id']}/audio"}


def preset_audio(preset: dict) -> Path | None:
    file = (ROOT / preset["audio"]).resolve()
    allowed = ((path("audio") / "dev").resolve(), (ROOT / "data/demo").resolve())
    if not file.is_file() or not any(file.is_relative_to(directory) for directory in allowed):
        return None
    return file
