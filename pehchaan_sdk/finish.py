"""The steps every answer takes around the frozen engine, whichever route it came through."""

from __future__ import annotations

import logging

from pehchaan import Result

from .amounts import read_amounts
from .guard import protect_numbers
from .meaning import MeaningCheck
from .referee import read_meaning

_logger = logging.getLogger(__name__)


def run_engine(pipeline, text: str, context, tokens=None, second: str | None = None) -> Result:
    """A number too large for any real call makes the frozen engine overflow. The call then returns its words, no facts."""
    try:
        return pipeline.run(text, context, tokens, second)
    except OverflowError:
        _logger.warning("a number in this call is too large to read")
        refused = [{"rule": "number_too_large", "reason": "A number is too large to be real, so no fact was claimed."}]
        return Result(text, text, context.level, {}, timings_ms={"total": 0.0}, refused=refused)


def finish_answer(
    engine: Result, known_amounts, reader=None, language: str | None = None, earlier: str | None = None
) -> tuple[bool, MeaningCheck]:
    """Guard unreadable numbers, compute exact money, then read meaning. Returns (numbers changed, meaning check)."""
    guarded = protect_numbers(engine, language)
    guarded |= read_amounts(engine, known_amounts)
    return guarded, read_meaning(engine, reader, earlier)
