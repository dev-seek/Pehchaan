"""Run manifest: the exact code, config, data and models behind a result, so any two runs can be compared honestly."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from pehchaan.config import ROOT, settings

TRACKED = {"engine": ("pehchaan", "*.py"), "scorer": ("bench/oracle", "*.py"), "language_packs": ("data/languages", "*"),
           "lexicons": ("data/lexicons", "*")}


def _digest(files: list[Path]) -> str:
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(str(f.relative_to(ROOT)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def run_manifest() -> dict:
    out = {name: _digest([f for f in (ROOT / folder).rglob(pattern) if f.is_file() and "__pycache__" not in f.parts])
           for name, (folder, pattern) in TRACKED.items()}
    out["scorer_tables"] = _digest([ROOT / "data/bench/oracle_numbers.yaml"])
    out["config"] = _digest([ROOT / "config/settings.yaml"])
    out["git_commit"] = _git("rev-parse", "--short", "HEAD")
    out["git_dirty"] = bool(_git("status", "--porcelain", "--", "pehchaan", "bench", "config", "data/languages",
                                 "data/lexicons"))
    out["models"] = dict(settings()["models"])
    return out
