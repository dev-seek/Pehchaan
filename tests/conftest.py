"""Shared test fixtures. Tests never call OpenAI: the judge is a fake, memory lives in a temp folder."""
from __future__ import annotations

import json

import pytest

from pehchaan import CallContext, build_pipeline
from pehchaan.config import ROOT
from pehchaan.judge import JudgeDecision
from pehchaan.languages import get_registry
from pehchaan.resolvers import JsonMemoryStore

DEMO_CONTEXT = json.loads((ROOT / "data/demo/contexts/hdfc_emi_hyderabad.json").read_text(encoding="utf-8"))


class FakeJudge:
    """Records every call and answers with a fixed choice."""

    def __init__(self, choice: str = "keep"):
        self.choice = choice
        self.calls: list[dict] = []

    def decide(self, sentence, span, etype, options, asr_confidence):
        self.calls.append({"span": span, "etype": etype, "options": options})
        return JudgeDecision(self.choice, "fake judge")


class ExplodingJudge:
    def decide(self, *args, **kwargs):
        raise TimeoutError("API down")


@pytest.fixture
def registry():
    return get_registry()


@pytest.fixture
def memory(tmp_path):
    return JsonMemoryStore(tmp_path / "memory")


@pytest.fixture
def run(memory):
    """run(text, level='C3', judge=None, context=DEMO_CONTEXT, pieces=None) -> Result"""
    def _run(text, level="C3", judge=None, context=None, pieces=None):
        ctx = CallContext.build(context if context is not None else DEMO_CONTEXT, level)
        return build_pipeline(judge=judge, memory=memory).run(text, ctx, pieces)
    return _run


def by_type(result):
    return {e.etype.value: e for e in result.entities}
