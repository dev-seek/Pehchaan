"""Measure loopback or staging action-check latency using invented callback calls."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pehchaan_live.contracts import Action, Turn
from pehchaan_live.settings import live_settings
from pehchaan_sdk.live import LiveClient, LiveUnavailable

from .score import quantile


async def sample(client: LiveClient, semaphore: asyncio.Semaphore) -> tuple[str, float, float | None]:
    async with semaphore:
        call_id = uuid4().hex
        start = perf_counter()
        try:
            original = await client.turn(Turn(call_id=call_id, turn_id="first", sequence=1,
                                              transcript="Order ID SYN-492; callback number 9000090010",
                                              step="callback"))
            first_ms = (perf_counter() - start) * 1000
            if original.outcome != "ask":
                return "unexpected_turn", first_ms, None
            start = perf_counter()
            await client.turn(Turn(call_id=call_id, turn_id="answer", sequence=2, transcript="9000090011",
                                   reply_to=original.question.id, step="callback"))
            result = await client.check(Action(
                call_id=call_id, turn_id="answer", action="update_callback",
                arguments={"order_id": "SYN-492", "callback_phone": "9000090011"}, idempotency_key="check-final",
            ))
            return result.outcome, first_ms, (perf_counter() - start) * 1000
        except LiveUnavailable:
            return "unavailable", (perf_counter() - start) * 1000, None
        finally:
            try:
                await client.delete_call(call_id)
            except LiveUnavailable:
                pass


async def load(url, call_count, concurrency):
    semaphore = asyncio.Semaphore(concurrency)
    async with LiveClient(url, os.environ["PEHCHAAN_V2_TOKEN"]) as client:
        outcomes = await asyncio.gather(*(sample(client, semaphore) for _ in range(call_count)))
    stats = Counter(outcome for outcome, _, _ in outcomes)
    turns = [first for outcome, first, _ in outcomes if outcome == "allow"]
    action = [last for _, _, last in outcomes if last is not None]
    p95 = quantile(action, 0.95)
    target = live_settings()["runtime"]["target_p95_ms"]
    return {
        "calls": call_count, "concurrency": concurrency, "outcomes": dict(stats),
        "turn_p50_ms": quantile(turns, 0.5), "turn_p95_ms": quantile(turns, 0.95),
        "answer_and_check_p50_ms": quantile(action, 0.5), "answer_and_check_p95_ms": p95,
        "target_p95_ms": target, "meets_target": stats["allow"] == call_count and p95 is not None and p95 <= target,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--calls", type=int, default=80, choices=range(1, 121), metavar="1–120")
    parser.add_argument("--concurrency", type=int, default=8, choices=range(1, 33), metavar="1–32")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(load(args.url, args.calls, args.concurrency))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
