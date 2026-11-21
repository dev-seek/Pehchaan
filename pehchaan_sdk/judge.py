"""The engine's LLM judge with a client of its own, so a customer's key pays for its own call and nothing is cached."""

from __future__ import annotations

import json
import time

from pehchaan.config import settings
from pehchaan.judge.verifier import CHOICES, SCHEMA, SYSTEM_PROMPT, JudgeDecision


class KeyedJudge:
    """Same model, prompt, schema and candidates as `pehchaan.judge.OpenAIJudge`. A test holds the two equal."""

    def __init__(self, client):
        cfg = settings()
        self.client = client
        self.model = cfg["models"]["verifier"]
        self.timeout_s = cfg["verifier"]["timeout_s"]
        self.requests = 0

    def decide(
        self, sentence: str, span: str, etype: str, options: list[dict], asr_confidence: float | None
    ) -> JudgeDecision:
        user = json.dumps(
            {
                "sentence": sentence,
                "heard_span": span,
                "entity_type": etype,
                "asr_confidence_logprob": asr_confidence,
                "candidates": {
                    f"cand{i + 1}": {"text": o["text"], "from": o["source"], "sound_distance_0_to_1": o["distance"]}
                    for i, o in enumerate(options[:3])
                },
            },
            ensure_ascii=False,
        )
        started = time.perf_counter()
        self.requests += 1
        reply = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "entity_decision", "strict": True, "schema": SCHEMA},
            },
            timeout=self.timeout_s,
        )
        answer = json.loads(reply.choices[0].message.content)
        choice = answer.get("choice") if answer.get("choice") in CHOICES else "keep"
        return JudgeDecision(choice, answer.get("reason", ""), int((time.perf_counter() - started) * 1000), False)
