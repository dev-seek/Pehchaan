# EVAL: Pehchaan-Bench v0 and the honesty rules

## Data
| split | what | size | used for |
|---|---|---|---|
| dev | 30 scripts (hi, hl, en, te) x 2 TTS voices, phone-line degraded: the **60-clip multi-voice (synthetic) dev set**, 164 facts | 60 clips | tuning, error analysis |
| test_real | 30 different scripts (hi 13, hl 10, en 7), **human voice**, one speaker (recorded at /record, clean laptop mic) | ~30 clips | source of the exam copy |
| test_real_phone | `test_real` with the phone-line effect (`make exam-audio`) | ~30 clips | **the Final Exam**: run ONCE (see Exam rules) |
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

## The scorer: an independent oracle (D-020)
`bench/oracle/` decides whether each fact is right using its own number reader and word tables
(`data/bench/oracle_numbers.yaml`). It shares no code or word list with the engine, so an engine bug cannot also
hide in the scorer. All systems are scored by the same final oracle; numbers from older scorers are not comparable.
- **Damage audit:** every edit from input text to output text is classified as **format** (same meaning, new
  spelling), **repair** (wrong to right) or **damage** (right to wrong). Damaged edits must be 0.
- **Flag credit:** a wrong fact that was flagged is not a silent error: a question was asked. It counts as "flagged",
  not "correct".
- **Run manifest** (`bench/manifest.py`): each run records digests of engine, scorer, packs, lexicons, config and
  models, so you can tell why two runs differ.

## Metrics (same scorer for all systems: `bench/score.py` + `bench/oracle/`)
- **Silent error rate (headline):** fraction of facts that are wrong AND not flagged. A flagged error costs one
  question; a silent one ships a wrong callback number.
- Entity accuracy (overall, by type, reachable vs unreachable), critical accuracy (phone/amount/PIN)
- Over-correction rate: right in the input, wrong in the output (must be ~0)
- Flag precision (how many questions were needed) and flags per clip (how naggy)
- WER (guardrail: we must not damage the rest), harness latency p50/p95, LLM calls per clip
- 95% bootstrap confidence intervals (1000 resamples over clips) for accuracy and silent error rate
Scoring tolerance: a name counts as correct if it is a pure spelling variant (phonetic distance <= 0.06, e.g.
Kondapoor = Kondapur), applied identically to every system.

## Regression gate (`make gate`, D-026)
After `make bench-dev`, `make gate` compares the run with `data/bench/baseline_dev.json`. It FAILS if the change
worsens silent errors, over-correction or damaged edits, makes a fact that was OK silently wrong, or raises flags per
clip by more than `bench.gate.flags_per_clip_tolerance` (config). `make adopt NOTE="why"` then makes the run the new
baseline. Adoption is a deliberate human step; git history is the rollback. Dev only: the exam never enters the gate.

## Exam rules (Final Exam, D-025)
Runs only on `test_real_phone`, once: `make exam-audio`, then `make bench-test-FINAL-ONCE`. `bench/exam.py` refuses
any other test clip set and refuses a second run (lock file). Never tune after it. **No exam result exists yet.**
`tools/make_audio.py --phone-copy` is written but has never been run and has no unit test.

## Latest honest dev results (run `results/dev_20261121_182109`; 60 synthetic clips, 164 facts)
| System | Accuracy | Silent errors | Critical acc. | Over-correction | Flags/clip (precision) | Damaged edits |
|---|---|---|---|---|---|---|
| Main, before (`P_on_B1_C3`) | 98.2% | 1.8% | - | 0.0% | 0.00 | 12 |
| Main, after | 97.6% [95-99] | 1.2% [0-3] | 94.4% | 0.0% | 0.03 (100%) | 0 |
| Adversarial, before (`P_on_B1_C4`) | 93.9% | 6.1% | - | 1.4% | 0.52 (0%) | 15 |
| Adversarial, after | 95.1% [91-98] | 1.2% [0-3] | 94.4% | 0.0% | 0.10 (100%) | 0 |
Baselines: plain ASR 82.3% / 17.7% silent; keyword ASR C3 92.7 / 7.3, C4 86.0 / 14.0; naive LLM fixer C3 83.5 / 16.5
(15 damaged edits), C4 57.9 / 42.1 (58 damaged edits). Harness p50 about 2 ms; 0.23 LLM calls per clip (main).

**Read these numbers with care:**
- Dev clips are synthetic voices and thresholds were tuned on them, so they are optimistic. This is NOT a real-voice result.
- Confidence intervals overlap: the accuracy changes are not proven. The clear gains are damage (12 to 0 on main) and
  far fewer wrong questions under C4.
- The 12 damaged edits before were real: ordinary words turned into brands ("डिलीवरी" to "Delhivery", "लिख" to "LIC").
- Two silent errors remain, both AMOUNT (dev_014, dev_020, one voice): both transcripts misheard the number the same
  way. The second transcript is the same model family, so it is not fully independent evidence.
- Flag precision of 100% rests on very few flags (2 on main, 6 on C4). C4 English accuracy is 86.7%.
- The product makes two speech-to-text calls per clip.

## Disclosure labels (use these exact words next to any number)
- "60-clip multi-voice dev set (synthetic voices, tuned on)"
- "30-clip single-speaker real-voice test (simulated phone line)": the exam, once it exists. One speaker, so it says
  little about other accents or voices.

## Rules
1. Tune on dev only. 2. Run test_real once, at the end, log it. 3. Never report `--simulate` runs as results.
4. Report CIs; with ~30 clips, differences inside overlapping CIs are "not proven".
   Never present dev numbers as real-voice results. Pehchaan is not self-learning (see PROGRESS.md).
5. If a result is bad, report it anyway, with the reason. Judges trust honest numbers.
