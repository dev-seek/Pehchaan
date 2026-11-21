"""Run manifest: the exact code, config, data and models behind a result, so any two runs can be compared honestly."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from pehchaan.config import ROOT, settings

TRACKED = {"engine": ("pehchaan", "*.py"), "scorer": ("bench/oracle", "*.py"), "language_packs": ("data/languages", "*"),
           "lexicons": ("data/lexicons", "*")}
ENGINE_SETTINGS = ("languages", "sound", "lexicon", "asr", "matching", "decisions", "policy", "numbers", "verifier", "memory")
ENGINE_MODELS = ("asr_plain", "asr_keywords", "asr_logprobs", "verifier", "naive_fixer")
FROZEN = ("engine", "scorer", "language_packs", "lexicons", "scorer_tables", "engine_config")


def _digest(files: list[Path]) -> str:
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(str(f.relative_to(ROOT)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _engine_config() -> str:
    """Only what can change an answer, so a website setting does not count as an engine change."""
    cfg = settings()
    chosen = {k: cfg[k] for k in ENGINE_SETTINGS} | {"models": {k: cfg["models"][k] for k in ENGINE_MODELS}}
    return hashlib.sha256(json.dumps(chosen, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def frozen_changes(exam: dict, now: dict) -> list[str]:
    """Which frozen parts differ from the code that sat the exam."""
    return [k for k in FROZEN if exam.get(k) != now.get(k)]


def run_manifest() -> dict:
    out = {name: _digest([f for f in (ROOT / folder).rglob(pattern) if f.is_file() and "__pycache__" not in f.parts])
           for name, (folder, pattern) in TRACKED.items()}
    out["scorer_tables"] = _digest([ROOT / "data/bench/oracle_numbers.yaml"])
    out["config"] = _digest([ROOT / "config/settings.yaml"])
    out["engine_config"] = _engine_config()
    out["git_commit"] = _git("rev-parse", "--short", "HEAD")
    out["git_dirty"] = bool(_git("status", "--porcelain", "--", "pehchaan", "bench", "config", "data/languages",
                                 "data/lexicons"))
    out["models"] = dict(settings()["models"])
    return out
