"""Read the demo allowlist and expose only packaged development, demo and consented real-voice sample audio."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pehchaan.config import ROOT, path, settings
from pehchaan_sdk.meaning import without_rejected

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


@lru_cache(maxsize=1)
def sample_answers() -> dict:
    """What each speech model already said on each sample. Packaged, so reading it costs nothing."""
    file = ROOT / "data" / "published" / "sample_models.json"
    return without_rejected(json.loads(file.read_text(encoding="utf-8"))["samples"]) if file.exists() else {}


def real_lines(preset_id: str) -> dict | None:
    """What each system did on this real-voice sample at every phone-line quality. Packaged, so it costs nothing."""
    file = ROOT / "data" / "published" / "real_lines.json"
    lines = json.loads(file.read_text(encoding="utf-8"))["lines"] if file.exists() else {}
    answers = {line: without_rejected(samples[preset_id]) for line, samples in lines.items() if preset_id in samples}
    return answers or None


def line_audio(preset_id: str, line: str) -> Path | None:
    """The same recording through a named simulated line. Only lines listed in config can be read."""
    if line not in settings()["real_check"]["conditions"] or not any(s["id"] == preset_id for s in real_samples()):
        return None
    file = ROOT / "data" / "demo" / "audio" / f"real_{line}" / f"{preset_id}.wav"
    return file if file.is_file() else None


def public_preset(preset: dict) -> dict:
    fields = {k: preset[k] for k in _PUBLIC_FIELDS if k in preset}
    return {"kind": "synthetic", **fields, "audio_url": f"/api/demo/presets/{preset['id']}/audio"}


def preset_audio(preset: dict) -> Path | None:
    file = (ROOT / preset["audio"]).resolve()
    allowed = ((path("audio") / "dev").resolve(), (ROOT / "data/demo").resolve())
    if not file.is_file() or not any(file.is_relative_to(directory) for directory in allowed):
        return None
    return file
