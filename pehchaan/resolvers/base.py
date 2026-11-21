"""
The Resolver interface. Each resolver owns ONE kind of decision (numbers, learned memory, names) and returns
entities for the token spans it is responsible for. The pipeline runs resolvers in order; a span claimed by an
earlier resolver is never touched by a later one. New entity kinds = new resolver, no edits to existing ones.
"""
from __future__ import annotations

from typing import Protocol

from ..context import CallContext
from ..models import Entity, Utterance


class Resolver(Protocol):
    name: str

    def resolve(self, utt: Utterance, ctx: CallContext, claimed: set[int]) -> list[Entity]:
        """Return entities for unclaimed spans of `utt`. Must not modify `claimed` (the pipeline does that)."""
        ...
