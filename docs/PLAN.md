# PLAN: from now to code freeze (Sun 22 Nov, 14:00 IST)

Principle: **measure first, then improve what the measurements say is broken.** Core first, extras on top.
Each task has an acceptance test (AT): a task is done only when its AT passes and it is committed + logged.

## Phase 0: Readiness (DONE, Sat ~15:45, v0.2)
Repo, brain files, engine (restructured, language packs + routing), benchmark, tests, recorder, API, demo v0.
AT: `make check` green; `make bench-sim` runs. P1.1 (API check) also DONE: see DECISIONS D-015.

## Step A: safety + honest scoring (DONE, Sat 21 Nov evening)
Oracle scorer + damage audit (D-020), read-only numbers (D-021), second opinion (D-022), admission gate and guards
(D-023, D-024), run manifests, exam guard (D-025), regression gate (D-026), product wired to the main system (D-019).
AT: `make check` green; dev run `results/dev_20261121_182109` shows 0 damaged edits. **Step B is next** (see below).

## Phase 1: Reality check + data (Sat 14:00-15:30)
| id | task | AT |
|---|---|---|
| P1.1 | `make check-api`; set working model names in settings.yaml (`asr_logprobs` must return logprobs) | report.json shows logprobs > 0 for asr_logprobs; verifier answers valid JSON |
| P1.2 | `make audio-dev`: 30 dev scripts x 2 voices = 60 clips; listen-check 10; delete mispronounced; rebuild manifest | `data/bench/dev_clips.jsonl` >= 50 clips |
| P1.3 | Human records 30 test lines at `/record` **on a laptop** (browser mic; not Colab), about 25 min. Then `make index-recordings` | `data/bench/test_real_clips.jsonl` >= 25 clips. **Do not run the benchmark on them yet.** |

## Phase 2: First real numbers (Sat 15:30-16:15)
| id | task | AT |
|---|---|---|
| P2.1 | `make bench-dev` | `results/latest_dev.json` exists |
| P2.2 | GO/NO-GO: compare **B0/B1 entity accuracy** with P_C3 | Decision written in DECISIONS.md |

**GO/NO-GO rule:** if baseline (B1_asr_keywords_C3) entity accuracy on dev is **>= 95% and its silent error rate
<= 3%**, the problem is already solved by keywords; switch to Plan B (semantic end-of-turn for Indian speech,
see bottom). Otherwise GO: the gap is our product.

## Phase 3: Error-analysis loop on DEV ONLY (Sat 16:15-20:30)
Repeat: run `make bench-dev`, open `results/<run>/per_clip.jsonl`, group failures by cause, fix the biggest
**general** cause, add a unit test, re-run, log the before/after numbers in LOG.md. Typical causes and fixes:
| failure pattern | where to fix |
|---|---|
| a correct entity was changed (over-correction / damage) | `policy/gate.py` rules, `matching.*` and `decisions.*` in settings, judge prompt in `judge/verifier.py` |
| a name in context was not matched | `sound/distance.py` rules and costs, `resolvers/matching.py` windows |
| ASR wrote a number in a format we do not parse | `data/languages/*.yaml` number words, `numbers/spoken.py`, `numbers/rules.py` |
| a common word became an entity | `policy/gate.py` common_word rule, `data/lexicons/brands.yaml`, language packs |
| too many questions (flags/clip high, flag precision low) | `decisions.flag_max_dist`, `policy.second_opinion_max_dist` |
| judge wrong | `judge/verifier.py` prompt; try another model in settings |
| scorer disagrees with a human reading of a clip | `bench/oracle/` and `data/bench/oracle_numbers.yaml` (never share tables with the engine) |
After every dev run: `make gate`. Adopt (`make adopt NOTE="why"`) only on purpose.
Priority order of features if time remains: (a) verifier ON and tuned, (b) dates/times ("kal shaam 5 baje"),
(c) order IDs / UPI IDs, (d) more localities (Chennai, Mumbai, Delhi) in `localities.yaml`.

## Phase 4: Demo product (Sat 20:30-23:59), starts with Step B
| id | task | AT |
|---|---|---|
| **Step B** | Local judge demo and Benchmark Lab. Side-by-side call summaries, four presets, live mic, context views, evidence, confirmation and replay, measured reports, and API examples. | Browser rehearsal and measured dev gate recorded in docs/LOG.md. The trap lets a judge confirm the place and replay with a memory hit and zero verifier calls. |
| **Step C** | Public-deploy lock: protect recording/script endpoints, sanitise paths, passcode + rate limit | NOT done yet; required before any public URL |

Older breakdown:
| id | task | AT |
|---|---|---|
| P4.1 | Polish `app/static/index.html`: Tab 1 Live (mic/upload, side-by-side, Fix/Confirm/Flag badges, latency, memory loop), Tab 2 Bench (table + CIs + by-type) | 20-second memory loop works live: flag, confirm, re-run, auto-fixed (source=memory) |
| P4.2 | Preload 3 "stage clips" (dev clips that show a fix, a flag and a confirm) in the UI | one click plays each |
| P4.3 | Deploy (AWS App Runner / EC2 / Lightsail; or run on laptop + ngrok as fallback) | public URL loads |
| P4.4 | Record a 90-second backup demo video | file saved |
Sleep 01:00-05:30. Non-negotiable.

## Phase 5: Final numbers + story (Sun 06:30-11:30)
| id | task | AT |
|---|---|---|
| P5.0 | `make exam-audio` (phone-line copy of the recordings; never run or unit-tested yet) | `test_real_phone` clips exist |
| P5.1 | **Run `make bench-test-FINAL-ONCE` exactly once** (`test_real_phone`). Log it. Never tune after this. | exam lock file + LOG entry |
| P5.2 | Slides (4-5) from docs/PITCH.md with the real numbers | deck exported |
| P5.3 | README.md: what, why, results table, how to run | judges can run it |

## Phase 6: Rehearse and freeze (Sun 11:30-13:30)
Rehearse the 3-minute demo 3 times. Final commit + push by 13:30 (30-minute buffer before the 14:00 freeze).

## Plan B (only if GO/NO-GO says so)
Semantic end-of-turn detector for Indian speech: fillers/backchannels ("haan haan", "matlab", "ek second") must
not end the caller's turn. Same bench pattern: recordings, base VAD vs ours, premature cut-off rate.

## Stretch (only after Phase 5 is safe)
Streaming mode (process partial transcripts), semantic VAD hook, Tamil/Kannada number words, on-device context.
