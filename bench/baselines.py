"""Baseline B2: the 'obvious' approach - give an LLM the transcript and the context, ask it to fix it."""
from __future__ import annotations

import json

from pehchaan.config import settings
from pehchaan.context import CallContext
from pehchaan.openai_client import cached, structured_completion

SYSTEM = ("You fix speech-recognition errors in an Indian phone-call transcript. Use the provided context "
          "(contacts, caller ID, SMS, known brands and localities) to correct misheard names, places, brands, "
          "phone numbers and amounts. Change nothing else. Return the full corrected transcript.")
SCHEMA = {"type": "object", "properties": {"corrected": {"type": "string"}},
          "required": ["corrected"], "additionalProperties": False}


def naive_fix(transcript: str, ctx: CallContext) -> dict:
    cfg = settings()
    model = cfg["models"]["naive_fixer"]
    user = json.dumps({"transcript": transcript,
                       "context": {"entities": ctx.keyword_list(cfg["asr"]["keywords_max"]),
                                   "known_phone_numbers": sorted(ctx.phones),
                                   "amounts_in_sms": sorted(ctx.amounts)}}, ensure_ascii=False)
    answer, was_cached = cached("naive_llm", {"model": model, "system": SYSTEM, "user": user},
                                lambda: structured_completion(model, SYSTEM, user, "fix", SCHEMA,
                                                              cfg["verifier"]["timeout_s"]))
    return {"text": answer.get("corrected", transcript), "ms": answer.get("_ms", 0), "cached": was_cached}
