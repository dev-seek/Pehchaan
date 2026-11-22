"""
Crash test of the whole answer path (D-054). No network and no cost.

    python -m bench.stress [inputs per seed] [seeds]

Half the calls run with no LLM. The other half use an LLM that replies at random or with broken data. Two things are
counted: calls that crashed, and numbers stated that the deterministic code never read from the words.
"""

from __future__ import annotations

import json
import random
import sys
import time
from types import SimpleNamespace

from pehchaan import build_pipeline
from pehchaan.config import ROOT
from pehchaan.resolvers.memory import NullMemoryStore
from pehchaan_sdk import CustomTranscriptProvider, Pehchaan
from pehchaan_sdk.amounts import read_amounts
from pehchaan_sdk.finish import run_engine
from pehchaan_sdk.guard import protect_numbers
from pehchaan_sdk.referee import KINDS, ROLES, MeaningReferee

NUMBERS = ("AMOUNT", "PHONE", "PIN")
_BROKEN = ("not json", '{"marks": 5}', '{"marks": [{"id": "x"}]}', '{"marks": [{"id": 0, "kind": "money"}]}')


class ChaosLLM:
    """Replies with any valid reading, or with something broken."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_):
        pick = self.rng.random()
        if pick < 0.08:
            raise TimeoutError
        marks = [
            {
                "id": self.rng.randrange(-1, 9),
                "kind": self.rng.choice([*KINDS, "nonsense"]),
                "role": self.rng.choice([*ROLES, "nonsense"]),
                "reads_right": self.rng.random() < 0.6,
            }
            for _ in range(self.rng.randrange(8))
        ]
        content = self.rng.choice(_BROKEN) if pick < 0.2 else json.dumps({"marks": marks, "checks": []})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def computed_by_code(sdk: Pehchaan, text: str, raw: dict) -> set[tuple[str, str]]:
    """Every number the deterministic code read from these words, before any meaning check."""
    context = sdk._prepare(raw)[0]
    engine = run_engine(build_pipeline(judge=None, memory=NullMemoryStore()), text, context)
    protect_numbers(engine, None)
    read_amounts(engine, context.amounts)
    return {(e.etype.value, str(e.value)) for e in engine.entities if e.etype.value in NUMBERS}


def _text(rng: random.Random, pool: dict) -> str:
    words, numbers, hostile = pool["words"], pool["numbers"], pool["hostile"]
    size, pick = rng.randint(1, 30), rng.random()
    if pick < 0.5:
        return " ".join(rng.choice(words + numbers + hostile) for _ in range(size))
    if pick < 0.7:
        return "".join(rng.choice(numbers + words + hostile) for _ in range(size))
    if pick < 0.8:
        return rng.choice(["9", "1", "12345"]) * rng.randint(30, 500) + rng.choice(
            [" lakh", " crore", "k", " rupaye", ""]
        )
    if pick < 0.9:
        blocks = (range(32, 127), range(0x900, 0x980), range(0xC00, 0xC80))
        return "".join(chr(rng.choice(rng.choice(blocks))) for _ in range(size * 3))
    return f"{rng.choice(numbers)}{rng.choice(['k', 'L', ' lakh', ' crore', 'cr', ' hazaar'])} {rng.choice(words)}"


def run(per_seed: int, seeds: int) -> dict:
    pool = json.loads((ROOT / "data/bench/stress_inputs.json").read_text(encoding="utf-8"))
    crashes, invented, slowest, started = 0, 0, 0.0, time.time()
    for seed in range(seeds):
        rng = random.Random(seed)
        plain = Pehchaan(CustomTranscriptProvider(), judge=None, memory=NullMemoryStore(), meaning=None)
        chaos = Pehchaan(
            CustomTranscriptProvider(), judge=None, memory=NullMemoryStore(), meaning=MeaningReferee(ChaosLLM(rng))
        )
        for i in range(per_seed):
            text, raw, sdk = _text(rng, pool), rng.choice(pool["contexts"]), chaos if i % 2 else plain
            began = time.perf_counter()
            try:
                answer = sdk.verify_transcript(text, raw)
                answer.model_dump_json()
                if sdk is chaos:
                    stated = {(f.type, f.value) for f in answer.entities if f.type in NUMBERS and f.status != "FLAGGED"}
                    invented += bool(stated - computed_by_code(plain, text, raw))
            except Exception:  # noqa: BLE001 - a crash is what is being counted
                crashes += 1
            slowest = max(slowest, time.perf_counter() - began)
    total = per_seed * seeds
    return {
        "inputs": total,
        "crashed": crashes,
        "survived": total - crashes,
        "calls_with_a_number_the_code_never_read": invented,
        "slowest_ms": round(slowest * 1000),
        "seconds": round(time.time() - started),
    }


if __name__ == "__main__":
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    summary = run(size, count)
    (ROOT / "data/published/stress.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary))
