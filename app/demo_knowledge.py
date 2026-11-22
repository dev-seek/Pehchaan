"""
The Company data demo: real connector code over invented records and packaged transcripts.

It costs nothing to run. No speech model or LLM is called, so its output is an illustration and never a benchmark result.
The transcripts are fixed, so a connected system changes Pehchaan's check but not what the speech model heard.
"""

from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from pehchaan import build_pipeline
from pehchaan.config import ROOT, settings
from pehchaan.context import CallContext
from pehchaan.resolvers import NullMemoryStore
from pehchaan_sdk.client import build_result
from pehchaan_sdk.finish import run_engine
from pehchaan_sdk.knowledge import FunctionSource, Knowledge, KnowledgeHub

from .access import is_public, rate_limit
from .demo_presets import catalog, sample_answers
from .demo_results import engine_spans

router = APIRouter(prefix="/api/demo/knowledge")
_OLD_DAYS_PAST_LIMIT = 30


class _Run(BaseModel):
    call: Annotated[str, Field(max_length=64)]
    sources: Annotated[list[str], Field(max_length=8)] = []
    fault: Annotated[str, Field(max_length=16)] = "none"


@lru_cache(maxsize=1)
def demo_data() -> dict:
    file = ROOT / settings()["knowledge"]["demo_records"]
    return json.loads(file.read_text(encoding="utf-8"))


def _call(call_id: str) -> dict:
    found = next((c for c in demo_data()["calls"] if c["preset"] == call_id), None)
    if found is None or call_id not in catalog() or call_id not in sample_answers():
        raise HTTPException(404, "This sample call is not available")
    return found


def _record(entry: dict, age_days: int | None = None) -> Knowledge:
    fields = {k: v for k, v in entry.items() if k != "age_days"}
    age = entry.get("age_days", 0) if age_days is None else age_days
    return Knowledge.of({**fields, "as_of": (date.today() - timedelta(days=age)).isoformat()})


def _hang(_call_key):
    """A system that does not answer in time. The wait is real, so the hub's real timeout is what handles it."""
    threading.Event().wait(settings()["knowledge"]["timeout_ms"] * 3 / 1000)


def _sources(call: dict, chosen: list[str], fault: str) -> list[FunctionSource]:
    rule = call["faults"].get(fault) or {}
    target = rule.get("source")
    records = {sid: dict(entry) for sid, entry in call["records"].items()}
    if fault in ("wrong", "disagree") and target:
        records[target] = {**records.get(target, {}), **rule.get("patch", {})}
    names = {s["id"]: s["name"] for s in demo_data()["sources"]}
    sources = []
    for sid in (s["id"] for s in demo_data()["sources"]):
        if sid not in chosen:
            continue
        if sid not in records:
            sources.append(FunctionSource(names[sid], lambda _key: None))  # connected, but holds nothing on this caller
            continue
        if fault == "down" and sid == target:
            sources.append(FunctionSource(names[sid], _hang))
            continue
        age = (
            settings()["knowledge"]["max_age_days"] + _OLD_DAYS_PAST_LIMIT if fault == "old" and sid == target else None
        )
        record = _record(records[sid], age)
        sources.append(FunctionSource(names[sid], lambda _key, value=record: value))
    return sources


def run_call(call_id: str, chosen: list[str], fault: str) -> dict:
    call = _call(call_id)
    known_ids = {s["id"] for s in demo_data()["sources"]}
    if not set(chosen) <= known_ids or fault not in {f["id"] for f in demo_data()["faults"]}:
        raise HTTPException(400, "Unknown system or fault")
    preset, model = catalog()[call_id], settings()["sdk"]["default_model"]
    answers = sample_answers()[call_id][model]
    base = {
        "caller": {"number": preset["context"]["caller"]["number"]},
        "domain": preset["context"].get("domain"),
        "user": {},
        "contacts": [],
        "sms": [],
        "places": [],
    }
    compiled = KnowledgeHub(_sources(call, chosen, fault)).gather(base)
    text, second = answers["main"]["text_in"], answers["base"]["text"]
    context = CallContext.build(compiled.context, settings()["sdk"]["level"])
    engine = run_engine(build_pipeline(judge=None, memory=NullMemoryStore()), text, context, None, second)
    facts = build_result(
        engine, model=model, second_model=model, stt_ms=0, judge=None, evidence="unmeasured", known=compiled
    ).entities
    entities = []
    for span in engine_spans(engine):
        fact = facts[int(span["id"])]
        entities.append({**span, "reason": fact.reason, "backed_by": fact.backed_by})
    questions = [
        {"entity_id": e["id"], "question": e["clarifier"]}
        for e in entities
        if e["status"] == "FLAGGED" and e["clarifier"]
    ]
    return {
        "simulated": True,
        "text": engine.text_out,
        "text_in": engine.text_in,
        "entities": entities,
        "questions": questions,
        "refused": engine.refused,
        "timings_ms": engine.timings_ms,
        "knowledge": compiled.report.model_dump(),
    }


@router.get("")
def list_demo():
    data = demo_data()
    calls = [
        {"id": c["preset"], "label": c["label"], "sources": list(c["records"]), "faults": ["none", *c["faults"]]}
        for c in data["calls"]
        if c["preset"] in catalog() and c["preset"] in sample_answers()
    ]
    return {"notice": data["notice"], "sources": data["sources"], "faults": data["faults"], "calls": calls}


@router.post("")
def run_demo(request: Request, payload: _Run):
    if is_public():
        rate_limit(request, "preset", settings()["demo"]["public_preset_runs_per_minute"])
    return run_call(payload.call, payload.sources, payload.fault)
