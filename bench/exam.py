"""
The final exam's rules, enforced in code rather than by memory: it runs on the phone-line copy of the human
recordings, its answer key must be readable by the scorer, and it can complete only once.
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path

from .oracle import fact_correct

EXAM_CLIPS = "test_real_phone"
LOCK_NAME = "final_exam.lock.json"


def check_exam_allowed(clips: str, simulate: bool, results_dir: Path) -> None:
    if simulate or not clips.startswith("test"):
        return
    if clips != EXAM_CLIPS:
        raise SystemExit(f"The final exam runs only on the phone-line copy ('{EXAM_CLIPS}'). Run: make exam-audio")
    lock = Path(results_dir) / LOCK_NAME
    if lock.exists():
        raise SystemExit(f"The final exam already ran: see {lock}. It must not be repeated (docs/EVAL.md).")


def labels_readable(scripts: Iterable[dict]) -> None:
    """Abort before any audio is sent if the scorer cannot read the answer key. Prints a count, never content."""
    entities = [(e, s["reference"]) for s in scripts for e in s["entities"]]
    unreadable = sum(1 for e, reference in entities if not fact_correct(e, reference))
    if unreadable:
        raise SystemExit(f"Scorer cannot read {unreadable} of {len(entities)} exam labels. Nothing was run.")


def record_exam(results_dir: Path, run_dir: Path | str, manifest: dict) -> None:
    lock = Path(results_dir) / LOCK_NAME
    lock.write_text(json.dumps({"completed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "run": str(run_dir),
                                "manifest": manifest}, indent=2), encoding="utf-8")
