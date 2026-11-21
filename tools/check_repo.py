#!/usr/bin/env python3
"""
Repository invariants. Run by `make check` before every commit, by every agent (Claude Code or Codex).
Fails loudly if the project drifted from its own rules, so switching agents mid-way cannot break consistency.

Checks:
  1. CLAUDE.md and AGENTS.md have identical bodies (both agents read the same rules)
  2. the test set still matches its SHA-256 lock (nobody tuned on / edited the exam)
  3. every active language pack loads, with no cross-pack conflicts
  4. every Python package folder has a docstring in __init__.py (self-explaining structure)
  5. no module grows past the size limit in docs/ENGINEERING.md (small, focused files)
  6. no secrets are tracked (.env is never committed)
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAX_MODULE_LINES = 300
PACKAGES = ["pehchaan", "bench", "tests"]


def body(path: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[1:]).strip()


def main() -> int:
    problems: list[str] = []

    if body(ROOT / "CLAUDE.md") != body(ROOT / "AGENTS.md"):
        problems.append("CLAUDE.md and AGENTS.md differ (below the title line). Edit both or copy one to the other.")

    test_file, lock = ROOT / "data/bench/test_scripts.jsonl", ROOT / "data/bench/test_scripts.sha256"
    if not lock.exists() or hashlib.sha256(test_file.read_bytes()).hexdigest() != lock.read_text().strip():
        problems.append("test set does not match its lock (data/bench/test_scripts.sha256). See docs/EVAL.md rules.")

    try:
        from pehchaan.languages import get_registry
        get_registry()
    except Exception as e:  # noqa: BLE001
        problems.append(f"language packs failed to load: {e}")

    for pkg_dir in (ROOT / "pehchaan").rglob("__init__.py"):
        text = pkg_dir.read_text(encoding="utf-8").lstrip()
        if not text.startswith('"""'):
            problems.append(f"{pkg_dir.relative_to(ROOT)} needs a docstring saying what the package is for")

    for pkg in PACKAGES:
        for f in (ROOT / pkg).rglob("*.py"):
            n = len(f.read_text(encoding="utf-8").splitlines())
            if n > MAX_MODULE_LINES:
                problems.append(f"{f.relative_to(ROOT)} has {n} lines (> {MAX_MODULE_LINES}); split it by concern")

    try:
        tracked = subprocess.run(["git", "ls-files", ".env"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if tracked:
            problems.append(".env is tracked by git: remove it (git rm --cached .env); it holds secrets")
    except FileNotFoundError:
        pass

    if problems:
        print("REPO CHECK FAILED:")
        for p in problems:
            print("  -", p)
        return 1
    print("repo check: all invariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
