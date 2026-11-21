# EVAL: Pehchaan-Bench v0 and the honesty rules

## Data
| split | what | size | used for |
|---|---|---|---|
| dev | 30 scripts (hi, hl, en, te) x 2 TTS voices, phone-line degraded | ~60 clips | tuning, error analysis |
| test_real | 30 different scripts (hi 13, hl 10, en 7), **human voice** (recorded at /record) | ~30 clips | the headline numbers, run ONCE at the end |
| test_synth | optional TTS copy of the test scripts | ~30 clips | sanity only |
| C4 | every clip again with an adversarial context (no extra audio) | all clips | over-correction / robustness |

- **Exact labels by construction:** `bench/generate.py` fills each {SLOT} with a spoken form (for the voice) and a
  written form (ground truth). Digits are spelled out in the spoken text, so the label always matches the audio.
- **No leakage:** dev and test use different templates and different person names and localities (seeded 50/50 split).
- **Locked test set:** `data/bench/test_scripts.sha256`. The generator refuses to change the test set once locked.
- **Synthetic is not the truth:** TTS-made test cases can show failures that real speech would not (false alarms),
  so synthetic audio is for tuning only. Headline = human voice.

Languages: hi = Hindi in Devanagari with English words, hl = Hinglish in Latin letters, en = Indian English,
te = Telugu (dev only, synthetic: the recorder does not speak Telugu; DECISIONS D-012). Every report has a
per-language table.

## Context levels (ablation ladder, adapted from IndicContextEval's graded prompting)
C0 none · C1 domain description · C2 global lists (brands + city localities) · **C3 per-call context (the product)**
· C4 adversarial per-call context: true entities removed, sound-alike decoys added, a decoy phone one digit off,
a teen/ty-swapped amount in an SMS.

## Systems compared
| id | what | why it is there |
|---|---|---|
| B0_asr_plain | gpt-transcribe, no context | the raw model |
| B1_asr_keywords_C3/C4 | gpt-transcribe + OpenAI `keywords` from the same context | the strongest "smart team" baseline |
| B2_naive_llm_C3/C4 | an LLM rewrites the transcript using the context | the obvious hack; shows hallucination under C4 |
| P_C0/C2/C3/C4 | Pehchaan on gpt-4o-transcribe (with logprobs) | our system at each context level |
| P_on_B1_C3 | Pehchaan on top of the keyword-biased transcript | shows we add value even on top of keywords |

## Metrics (same scorer for all systems: `bench/score.py`)
- **Silent error rate (headline):** fraction of facts that are wrong AND not flagged. A flagged error costs one
  question; a silent one ships a wrong callback number.
- Entity accuracy (overall, by type, reachable vs unreachable), critical accuracy (phone/amount/PIN)
- Over-correction rate: right in the input, wrong in the output (must be ~0)
- Flag precision (how many questions were needed) and flags per clip (how naggy)
- WER (guardrail: we must not damage the rest), harness latency p50/p95, LLM calls per clip
- 95% bootstrap confidence intervals (1000 resamples over clips) for accuracy and silent error rate
Scoring tolerance: a name counts as correct if it is a pure spelling variant (phonetic distance <= 0.06, e.g.
Kondapoor = Kondapur), applied identically to every system.

## Rules
1. Tune on dev only. 2. Run test_real once, at the end, log it. 3. Never report `--simulate` runs as results.
4. Report CIs; with ~30 clips, differences inside overlapping CIs are "not proven".
5. If a result is bad, report it anyway, with the reason. Judges trust honest numbers.
