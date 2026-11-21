# START HERE: status and next task

**Pehchaan** ("recognition / identity") is a layer after any speech-to-text model on Indian phone calls. It makes
sure the *facts* in a transcript (who called, from which company, which place, which phone number, which PIN, how
much money) are **right, or flagged with one short question.** It uses what the phone already knows (contacts,
caller ID, SMS, city) plus Indian sound and number rules, works on code-mixed speech, and learns from confirmations.
Track: BUILDERS '26 Track 2, "Voice AI for India", idea "Indian names and entities".

_Last updated: Sat 21 Nov ~15:45 IST (v0.2 restructure)._

## What works now (`make check` green: lint + 83 tests + repo invariants)
- Clean package structure (docs/ENGINEERING.md): text / languages / sound / numbers / context / asr / judge /
  resolvers / output / pipeline, dependencies injected (Judge, MemoryStore, registry)
- Language packs `data/languages/{hi,en,te}.yaml` + merged registry + per-utterance routing (code-mixed aware)
- Handles what OpenAI ASR really writes (from our API check): English digits in Hindi script ("नाइन एट फोर"),
  Hindi number words, acronyms in Hindi script (एचडीएफसी, ईएमआई), loanword vowels (कॉंडापूर), whisper misspellings
- Sound matching across 9 Indian scripts (Hindi, Telugu, Kannada, Tamil, Malayalam, Bengali, Gujarati, ...)
- Resolvers: numbers (phone/PIN/amount, validation + repairs), memory (learned fixes), names (sound-alike + judge)
- Benchmark: 30 dev scripts (hi/hl/en/te, synthetic voice) + 30 LOCKED test scripts (hi/hl/en only: real voice),
  10 systems, per-type and per-language results, bootstrap CIs; app with /record page and demo v0

## Verified with the real API (tools/check_openai.py, 21 Nov)
All models available. gpt-4o-transcribe returns logprobs (main input). gpt-transcribe supports keywords (baseline
B1). Judge latency: gpt-4.1-mini 0.9 s (default), gpt-5.4-mini 1.0 s, gpt-4o-mini 2.2 s, gpt-6-luna 4.0 s.

## NOT verified yet
- [ ] Sarvam TTS request shape / speaker names (`tools/make_audio.py::tts_sarvam`); OpenAI TTS is the fallback
- [ ] Engine behaviour on real phone-quality audio (first real benchmark run)
- [ ] Known risk to watch: under the C4 trap, "fix when ASR unsure" for phones/amounts could pick a decoy if
      real logprobs are low on correct digits. Measure on dev; tighten `matching.low_conf_logprob` if needed.

## NEXT TASKS (details + acceptance tests in docs/PLAN.md)
1. P1.2 `make audio-dev` (60 dev clips; can run in Colab), listen to ~10, delete bad ones, re-run
2. P1.3 Human records the 30 test lines on a LAPTOP (`make serve` → http://localhost:8000/record), then
   `make index-recordings`. Do NOT benchmark them yet.
3. P2.1 `make bench-dev` → apply the GO/NO-GO rule in PLAN.md
4. P3 error-analysis loop on dev

## How to run
```bash
make setup && cp .env.example .env    # add OPENAI_API_KEY (+ optional SARVAM_API_KEY)
make check && make bench-sim && make serve
```
