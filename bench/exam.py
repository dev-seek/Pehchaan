"""
The final exam's rules, enforced in code rather than by memory. It runs on registered phone-line copies of the human
recordings. Each line runs once, the list of lines cannot change after the first run, the code must be committed, its
answer key must be readable by the scorer, and a failed API call stops the run before anything is scored.
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path

from pehchaan.config import settings

from .oracle import fact_correct

LOCK_NAME = "final_exam.lock.json"


def registered() -> dict:
    return settings()["exam"]["conditions"]


def is_exam(clips: str) -> bool:
    return clips in registered()


def _lock(results_dir: Path) -> dict | None:
    file = Path(results_dir) / LOCK_NAME
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else None


def check_exam_allowed(clips: str, simulate: bool, results_dir: Path, *, partial: bool = False) -> None:
    if simulate or not clips.startswith("test"):
        return
    if not is_exam(clips):
        raise SystemExit(f"The final exam runs only on a registered phone-line copy: {', '.join(registered())}. "
                         "Run: make exam-audio")
    if partial:
        raise SystemExit("The final exam runs on the whole clip set and every system, with no --limit or --systems.")
    lock = _lock(results_dir)
    if lock is None:
        return
    if lock["registered"] != registered():
        raise SystemExit("The registered exam lines changed after the first run. The exam cannot continue.")
    if clips in lock["runs"]:
        raise SystemExit(f"The final exam already ran on {clips}. It must not be repeated (docs/EVAL.md).")


def require_frozen(manifest: dict) -> None:
    if manifest["git_dirty"]:
        raise SystemExit("The exam needs committed code: there are uncommitted engine, bench or config changes.")


def labels_readable(scripts: Iterable[dict]) -> None:
    """Abort before any audio is sent if the scorer cannot read the answer key. Prints a count, never content."""
    entities = [(e, s["reference"]) for s in scripts for e in s["entities"]]
    unreadable = sum(1 for e, reference in entities if not fact_correct(e, reference))
    if unreadable:
        raise SystemExit(f"Scorer cannot read {unreadable} of {len(entities)} exam labels. Nothing was run.")


def require_complete(transcripts: dict, outputs: dict) -> None:
    """An outage must not become a score. Answers are cached, so a rerun only repeats the requests that failed."""
    failed = sum("error" in t for clip in transcripts.values() for t in clip.values())
    for clip in outputs.values():
        for output in clip.values():
            failed += bool(output.get("failed"))
            failed += sum(str(e.get("reason", "")).startswith("judge unavailable") for e in output.get("entities", []))
    if failed:
        raise SystemExit(f"{failed} model requests failed. Nothing was scored or locked. Run the exam command again.")


def record_exam(results_dir: Path, clips: str, run_dir: Path | str, manifest: dict) -> None:
    file = Path(results_dir) / LOCK_NAME
    lock = _lock(results_dir) or {"registered": registered(), "runs": {}}
    lock["runs"][clips] = {"completed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "run": str(run_dir), "manifest": manifest}
    file.write_text(json.dumps(lock, indent=2), encoding="utf-8")
