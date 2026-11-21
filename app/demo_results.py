"""Serialize a configured system's decisions and exact transcript highlights for the browser."""
from __future__ import annotations

from bench.score import score_clip
from pehchaan import build_pipeline
from pehchaan.context import CallContext
from pehchaan.pipeline import Result
from pehchaan.resolvers import NullMemoryStore

from .demo_state import MEMORY_TYPES


def baseline_spans(text: str, context: CallContext) -> list[dict]:
    """Locate the raw model's numbers and exact known names; leave its surface text intact."""
    result = build_pipeline(memory=NullMemoryStore()).run(text, context)
    entities = []
    for i, entity in enumerate(result.entities):
        span = result.spans.get(i)
        if span is None or (entity.etype.value in {"PERSON", "ORG", "PLACE"} and entity.surface != entity.value):
            continue
        entities.append({**span, **entity.to_dict(), "id": str(i), "start": span["input_start"], "end": span["input_end"],
                         "display": entity.surface, "value": entity.heard_value or entity.surface, "status": "KEPT",
                         "source": "transcript", "reason": "Appears in the model transcript.",
                         "admission": "admitted", "candidates": [], "clarifier": None})
    return entities


def engine_spans(result: Result) -> list[dict]:
    return [{**entity.to_dict(), "id": str(i), **result.spans[i]}
            for i, entity in enumerate(result.entities) if i in result.spans]


def asr_metadata(transcript: dict, role: str) -> dict:
    return {"role": role, **{key: transcript[key] for key in ("model", "latency_ms", "cached") if key in transcript}}


def serialize_result(output: dict, context: CallContext, source: dict, second: dict | None,
                     truth: dict | None = None) -> dict:
    engine = output.get("engine")
    entities = engine_spans(engine) if engine else baseline_spans(output["text"], context)
    questions = [{"entity_id": e["id"], "question": e["clarifier"],
                  "choices": list(dict.fromkeys(c["text"] for c in e["candidates"]
                                                if c.get("text") and (e["etype"] not in MEMORY_TYPES
                                                                      or c.get("etype", e["etype"]) == e["etype"])))}
                 for e in entities if engine and e["status"] == "FLAGGED" and e["clarifier"]]
    asr = [asr_metadata(source, "input")]
    if second is not None:
        asr.append(asr_metadata(second, "second_opinion"))
    result = {"text": output["text"], "text_in": output["in_text"], "entities": entities, "questions": questions,
              "timings_ms": engine.timings_ms if engine else {"total": output["harness_ms"] or 0}, "asr": asr,
              "llm_calls": output.get("verifier_calls", 0), "verifier_cache_hits": output.get("verifier_cache_hits", 0),
              "memory_hits": sum(e["source"] == "memory" for e in entities)}
    if engine:
        result.update(language=engine.language, refused=engine.refused, level=engine.level)
    if "rewrite_calls" in output:
        result.update(rewrite_calls=output["rewrite_calls"], rewrite_cached=output["rewrite_cached"])
    if truth:
        scored = score_clip(truth["entities"], truth["reference"], output["text"], output["in_text"], output["flags"],
                            output["known"])
        result["scored"] = {"entities": scored["entities"], "damaged_edits": scored["n_damage"],
                            "silent_errors": [e["type"] for e in scored["entities"] if not e["correct"] and not e["flagged"]]}
    return result
