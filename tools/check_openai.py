#!/usr/bin/env python3
"""
Minute-1 reality check for the OpenAI account (run this BEFORE building on any model name).

What it does, in plain words:
  1. Lists the models your key can actually use.
  2. Makes a short test sentence into audio with OpenAI text-to-speech (so you need no microphone).
  3. Sends that audio to every speech-to-text model we might use and prints what comes back,
     including the per-token confidence scores ("logprobs") where the model supports them.
  4. Tests "Structured Outputs" (forcing the model to answer with one of a fixed set of choices)
     on the candidate verifier models and measures how fast each one answers.
  5. Saves everything to .cache/check/report.json so the next agent session can read it.

Run:   python tools/check_openai.py
Needs: OPENAI_API_KEY in your environment or in a .env file in the repo root.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".cache" / "check"
OUT.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
try:
    from openai import OpenAI
except ImportError:
    sys.exit("Install the SDK first:  pip install -r requirements.txt")

if not os.environ.get("OPENAI_API_KEY"):
    sys.exit("OPENAI_API_KEY is not set. Put it in .env (copy .env.example).")

client = OpenAI()
report: dict = {"ran_at": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": {}}

ASR_CANDIDATES = ["gpt-transcribe", "gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1"]
LLM_CANDIDATES = ["gpt-6-luna", "gpt-5.4-mini", "gpt-4.1-mini", "gpt-4o-mini"]
TTS_CANDIDATES = ["gpt-4o-mini-tts", "tts-1"]

TEST_TEXT = (
    "Namaste sir, main Venkateswara Rao bol raha hoon HDFC Bank se, Kondapur branch. "
    "Aapki EMI chaudah hazaar paanch sau rupaye pending hai. "
    "Mera number hai nine eight four eight zero, one two three four five."
)
KEYWORDS = ["Venkateswara Rao", "HDFC Bank", "Kondapur"]


def step(name):
    def deco(fn):
        def run():
            print(f"\n=== {name} ===")
            t0 = time.time()
            try:
                res = fn()
                report["steps"][name] = {"ok": True, "result": res, "secs": round(time.time() - t0, 2)}
            except Exception as e:  # noqa: BLE001 - we want to see every failure
                print(f"  FAILED: {type(e).__name__}: {e}")
                report["steps"][name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        return run
    return deco


@step("1_models_available")
def check_models():
    ids = sorted(m.id for m in client.models.list())
    wanted = ASR_CANDIDATES + LLM_CANDIDATES + TTS_CANDIDATES
    found = {w: (w in ids) for w in wanted}
    for k, v in found.items():
        print(f"  {'YES' if v else 'no '}  {k}")
    interesting = [i for i in ids if any(s in i for s in ("transcribe", "tts", "luna", "mini", "realtime", "live"))]
    print(f"  (other related models on this key: {', '.join(interesting[:40])})")
    return {"found": found, "related": interesting}


@step("2_tts_sample")
def make_sample():
    last_err = None
    for model in TTS_CANDIDATES:
        try:
            kwargs = dict(model=model, voice="alloy", input=TEST_TEXT, response_format="mp3")
            if model != "tts-1":
                kwargs["instructions"] = "Speak like a polite bank caller from Hyderabad, natural Indian accent, normal pace."
            audio = client.audio.speech.create(**kwargs)
            path = OUT / "sample.mp3"
            audio.write_to_file(path)
            print(f"  wrote {path} using {model}")
            return {"model": model, "path": str(path)}
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  {model} failed: {e}")
    raise RuntimeError(f"no TTS model worked: {last_err}")


@step("3_asr_models")
def check_asr():
    sample = OUT / "sample.mp3"
    if not sample.exists():
        raise RuntimeError("no sample audio (step 2 failed)")
    results = {}
    for model in ASR_CANDIDATES:
        variants = [("plain", {})]
        if model in ("gpt-4o-transcribe", "gpt-4o-mini-transcribe"):
            variants = [("logprobs", {"include": ["logprobs"], "response_format": "json"})]
        if model == "gpt-transcribe":
            variants = [("plain", {}), ("keywords", {"keywords": KEYWORDS, "languages": ["hi", "en"]})]
        if model == "whisper-1":
            variants = [("verbose", {"response_format": "verbose_json", "timestamp_granularities": ["word", "segment"]})]
        for vname, extra in variants:
            key = f"{model}:{vname}"
            try:
                t0 = time.time()
                with open(sample, "rb") as f:
                    r = client.audio.transcriptions.create(model=model, file=f, **extra)
                ms = int((time.time() - t0) * 1000)
                d = r.model_dump() if hasattr(r, "model_dump") else {"text": str(r)}
                lp = d.get("logprobs") or []
                print(f"  {key:32s} {ms:5d} ms  logprobs={len(lp):3d}  text: {d.get('text','')[:160]}")
                if lp:
                    print(f"     first tokens: {[(x.get('token'), round(x.get('logprob', 0), 2)) for x in lp[:8]]}")
                results[key] = {"ms": ms, "text": d.get("text"), "n_logprobs": len(lp),
                                "logprob_example": lp[:5], "keys": sorted(d.keys())}
            except Exception as e:  # noqa: BLE001
                print(f"  {key:32s} FAILED: {e}")
                results[key] = {"error": str(e)}
    return results


@step("4_structured_outputs")
def check_llm():
    schema = {
        "name": "entity_decision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "choice": {"type": "string", "enum": ["keep", "cand1", "cand2", "cand3", "flag"]},
                "reason": {"type": "string"},
            },
            "required": ["choice", "reason"],
            "additionalProperties": False,
        },
    }
    msgs = [
        {"role": "system", "content": "You verify one entity in a phone-call transcript. Answer with the schema."},
        {"role": "user", "content": json.dumps({
            "sentence": "main Venkat row bol raha hoon HDFC Bank se",
            "span": "Venkat row",
            "candidates": {"cand1": "Venkateswara Rao (contact)", "cand2": "Venkatesh (contact)", "cand3": "Ravi Teja (contact)"},
        })},
    ]
    out = {}
    for model in LLM_CANDIDATES:
        try:
            t0 = time.time()
            r = client.chat.completions.create(model=model, messages=msgs,
                                               response_format={"type": "json_schema", "json_schema": schema})
            ms = int((time.time() - t0) * 1000)
            content = r.choices[0].message.content
            print(f"  {model:16s} {ms:5d} ms  -> {content}")
            out[model] = {"ms": ms, "content": content}
        except Exception as e:  # noqa: BLE001
            print(f"  {model:16s} FAILED: {e}")
            out[model] = {"error": str(e)}
    return out


for fn in (check_models, make_sample, check_asr, check_llm):
    fn()

(OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
print(f"\nSaved full report to {OUT / 'report.json'}")
print("Next: paste the printed output to Claude, or let your coding agent read .cache/check/report.json "
      "and update config/settings.yaml with the models that worked.")
