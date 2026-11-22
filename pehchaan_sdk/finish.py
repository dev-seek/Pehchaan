"""The checks every answer passes after the frozen engine, whichever route it came through."""

from __future__ import annotations

from pehchaan import Result

from .amounts import read_amounts
from .guard import protect_numbers
from .meaning import MeaningCheck
from .referee import read_meaning


def finish_answer(engine: Result, known_amounts, reader=None, language: str | None = None) -> tuple[bool, MeaningCheck]:
    """Guard unreadable numbers, compute exact money, then read meaning. Returns (numbers changed, meaning check)."""
    guarded = protect_numbers(engine, language)
    guarded |= read_amounts(engine, known_amounts)
    return guarded, read_meaning(engine, reader)
