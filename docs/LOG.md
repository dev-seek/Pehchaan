# LOG (append-only; every session adds an entry: time, who/which account, what, numbers, next)

## Sat 21 Nov ~12:15-14:00 · Claude (claude.ai planning session)
- Built Phase 0: engine (`pehchaan/`), benchmark (`bench/`), tools, app server + recorder + demo v0, brain docs.
- Verified OpenAI SDK 3.57 parameters offline (see DECISIONS D-003). Not yet run against the real API.
- Tests: 45 passing. Simulated plumbing run (NOT a result): over-correction found under the C4 trap, fixed (D-007).
- Next: P1.1 check-api, P1.2 dev audio, P1.3 record test set (see PLAN.md).

## Sat 21 Nov ~14:30-15:45 · Claude (claude.ai session)
- API check run by builder (Colab): all models OK; findings in DECISIONS D-015.
- v0.2 restructure (D-012..D-018): language packs + routing, package-per-concern, injected Judge/MemoryStore,
  Hinglish templates, real-voice test set hi/hl/en only (re-locked before any recording), per-language reports,
  ruff + repo invariants (`make check`), docs/ENGINEERING.md.
- Engine verified on the REAL transcripts from the API check: all 5 facts confirmed, phone "नाइन एट फोर…" read.
- Tests: 83 passing. Simulated bench (NOT a result): runs end to end; C4 trap risk noted in START_HERE.
- Next: P1.2 dev audio, P1.3 recording on laptop, P2.1 first real bench.

## 2026-11-21 (evening): Step A, safety + honest scoring, docs brought up to date
- Built: independent oracle scorer + damage audit (`bench/oracle/`, D-020); read-only numbers (D-021, supersedes
  D-007); second-opinion transcript (D-022); AdmissionGate with five rules (D-023, D-024); run manifests;
  exam guard on a phone-degraded copy (D-025); regression gate with human adoption (D-026); product wired to the
  main system (D-019). API gained `refused`, `heard_value`, `admission`; memory refuses PHONE/PIN/AMOUNT (HTTP 400).
- Run `results/dev_20261121_182109`: 60 synthetic-voice dev clips, 164 facts, one final scorer for every system.
  Main (`P_on_B1_C3`) before 98.2% acc / 1.8% silent / 12 damaged edits; after 97.6% [95-99] / 1.2% [0-3] / 0 damaged,
  0.03 flags/clip (100% precision, 2 flags). Adversarial (`P_on_B1_C4`) before 93.9% / 6.1% / 1.4% over-correction /
  0.52 flags/clip (0% precision) / 15 damaged; after 95.1% [91-98] / 1.2% / 0.0% / 0.10 flags/clip (100%, 6 flags) / 0.
  Baselines: plain ASR 82.3 / 17.7 silent; keyword C3 92.7 / 7.3, C4 86.0 / 14.0; naive LLM C3 83.5 / 16.5 (15
  damaged), C4 57.9 / 42.1 (58 damaged). Harness p50 about 2 ms; 0.23 LLM calls/clip.
- Honest limits: synthetic voices, tuned on dev, so optimistic; CIs overlap (accuracy change not proven; damage 12 to
  0 and fewer wrong questions under C4 are the clear gains); the 12 damaged edits were real ("डिलीवरी" to
  "Delhivery", "लिख" to "LIC"); two AMOUNT silent errors remain (dev_014, dev_020); second transcript is the same
  model family; C4 English 86.7%; two ASR calls per clip.
- Not done: `--phone-copy` never run or tested; public-deploy lock; no locked real-voice result exists.
- Docs: DECISIONS D-019..D-026 added; CLAUDE.md/AGENTS.md rule 5 and `make gate`/`make adopt`; ENGINEERING, ARCHITECTURE,
  EVAL, API, GLOSSARY, PITCH (claims softened, numbers labelled), PLAN, PROGRESS (new), START_HERE updated.
- Next: Step B (Demo UI, Call Summary & Action Card, live mic), then public-deploy lock, then Sunday exam.

## 2026-11-21 (evening IST) · Codex, Step B local judge demo

- Built Live Call Playground, Benchmark Lab, and API & Integration. The comparison runs the configured benchmark
  approaches on the same input and streams each approach as it finishes. The API alias preserves the existing
  multipart contract. The demo uses temporary audio, expiring in-process replay inputs, and explicit SQLite
  confirmations for names and places (D-027 and D-028).
- Rehearsed all four presets on localhost against the current engine. Delivery fixed Bommanahalli, with the model's
  currency-formatted PIN showing as a second amount. Bank showed ₹14,500 and callback 98005 12346. Telugu flagged a
  garbled callback and blocked its preview. Wrong-Context Trap flagged Basavanagudi. Entering Kadugodi and replaying
  produced one memory hit, zero verifier calls and roughly 4 ms of replay time.
- Chrome verification covered keyboard traversal, 320–1366 px layouts, permission denial, recording timer and cancel,
  typed and uploaded input, partial approach failure, context switching, missing benchmark JSON, and both copied
  examples against the live alias. A fresh MediaRecorder capture from Chrome's synthetic input reached real,
  uncached speech-to-text. Automated speaker playback through the physical microphone did not yield an intelligible
  callback number.
- `make check` passed 188 tests, lint and repo invariants. `make bench-sim` passed for plumbing only.
  Measured dev rerun `results/dev_20261121_185123` reused the recorded model answers and passed `make gate`. All 660
  scored outcomes matched the previous measured run. Main system p50/p95 ASR request time was 1029/1497 ms.
  Post-ASR Pehchaan p50/p95 was 1.85/5.04 ms. No baseline was adopted.
- UI/UX Pro Max was run via the Codex setup in a temporary folder. Used 21st comparison references and review.
  Neither adds app dependencies. The next milestones are the public-deploy lock and the one-time locked benchmark.

## 2026-11-21 (night IST) · Claude, verified learning, public lock, site and README

- Decided with the builder: headline "Every fact in an Indian call: right, or it asks" (not "zero silent errors", because
  dev still shows 1.2%); build real verified learning instead of claiming it; add real-voice samples recorded separately
  from the locked test.
- Verified learning (D-029). Held-out voice, scripted confirmations, judge off: no context 138 to 150 of 164 correct, silent
  23 to 11; brands and places 144 to 152, silent 17 to 9; full context 154 to 156, silent 7 to 5. 0 facts harmed. 36 of 36
  deliberately wrong confirmations blocked.
- Public lock (D-030). `/api/scripts` previously served the locked test scripts to anyone who could reach the server. It is
  now laptop-only. All four sample calls were replayed in public mode with an empty local cache and an invalid API key.
- Found through the demo: a spoken PIN displayed as rupees, hidden by a scorer blind spot, and a false question for a phone
  number after a comma (D-031). Fixed with tests. Dev metrics unchanged at `results/dev_20261121_192315`; gate passed;
  baseline re-adopted because the scorer changed.
- `/studio` records the six real-voice samples. They are not recorded yet. The locked test was not read or run.

## 2026-11-21 (late night IST) · Claude, site verification and learned-name safety

- Website redesign checked in headless Chrome at 1440, 390 and 320 px in locked public mode: all five pages, all four
  samples, every info button, and confirm, replay and undo. No console errors, failed requests, page overflow or external
  requests, and no request touched the locked test data. Not checked: real phones, Safari, Firefox, screen readers,
  real-voice samples (not recorded yet), and a live run with the correct passcode.
- Found by that run: learning could overwrite a real place name. Fixed with tests and a sixth gate rule (D-032).
- Home now runs one sample, chosen by `featured` in `data/demo/presets.json`, instead of trying them in turn.
- Dev rerun `results/dev_20261121_194904`: metrics unchanged, gate passed. Learning proof unchanged. Locked test not read or run.

## 2026-11-21 (night IST) · Claude, real-voice check, look-alike rule, publishing proof

- The builder recorded six real-voice samples. `make publish` had not packaged them (a fresh answer was never traced), so all
  six would have failed on the public site. Fixed with a test, and publishing now replays every sample offline or fails.
- Real voice, 21 facts: on clear and phone-line audio the base model got every fact right. On noisy lines and dropouts it did
  not (`data/published/real_voice.json`). The numbers include conditions where Pehchaan does not lead.
- Fixes and costs are in D-033. Locked test not read or run.
- A reader with no project context reviewed screenshots of the site. Fixed what clashed: the "no real-voice result" banner, the
  missing "who is this for", internal decision IDs, rule names without plain titles, and a cut-off Python example.
- Verified from a clean clone in locked public mode at 1440, 390 and 320 px: all 10 samples, all info buttons, and confirm,
  replay and undo, with no console errors or external requests. Real phones, Safari and Firefox are still unchecked.

## 2026-11-21 (night IST) · Claude, locked exam on two phone lines and four-model comparison
- Froze the engine at `550d36e` (tag `exam-freeze`), then ran the exam once per line: standard at 21:01:44, noisy at 21:03:41.
  30 real-voice clips, one speaker, 82 facts, no failed model requests, clean commit. Both lines are now locked.
- Standard line, normal hints: keywords 74.4% right and 25.6% silent, Pehchaan 75.6% right and 15.9% silent, 0.47 questions per
  call. Noisy line, normal hints: keywords 54.9% and 45.1%, Pehchaan 54.9% and 31.7%, 0.73 questions per call.
- Pehchaan mostly turns silent errors into questions. It barely raises the number of right facts, and about half its questions
  point at a real error. The unpaired 95% intervals overlap. A paired clip check, chosen after seeing the results, excludes zero.
- The dev result (97.6% right, 1.2% silent) did not carry over to real voice. Exam failures were not read, so the cause is unknown.
- Four-model comparison added (`make model-compare`): Pehchaan lowered silent errors on every model, on dev and on six real
  samples across three bad lines. It is not exam evidence.
- Found and fixed: Home labelled the exam numbers as "development calls" once an exam report existed.

## 2026-11-21 (night IST) · Claude, exam diagnostic (counts only, nothing tuned)
- Follows the entry above, which said exam failures were not read. A counts-only check has now run. No exam sentence or fact was
  printed, and the engine was not changed.
- Facts wrong in all seven systems: 13 of 82 on the standard line, 32 of 82 on the noisy line. PIN is the weakest type (3 of 7 and 5 of 7).
- Median word error for plain speech-to-text: 0.35 standard, 0.60 noisy. Speaking pace matches the six samples (median 1.59 against
  1.57 words per second), so there is no sign of broken recordings, but 3 exam clips are slower than any sample. The cause of the
  gap between the six samples and the exam is still unknown.

## 2026-11-21 (night IST) · Claude, drop-in product around the frozen engine
- Added the SDK, the OpenAI-compatible proxy, verify endpoints, memory confirm, the WebSocket stream and production limits. The engine is unchanged from `exam-freeze`.
- Rebuilt the site into three tabs. The headline figures are computed from the published paired results and scoped to normal hints. Damaged edits and the keyword share are stated on the page.
- Deployed to https://52-24-174-127.sslip.io. Secrets stay on the server.
- Checked in headless Chrome at 1440, 390 and 320 px: no overflow, no console errors, tooltips, all samples, all four models, confirm, replay and undo. The official OpenAI Python client, the SDK quickstart, and the paste and file panels were run against a local **stub** upstream. Those answers are plumbing checks only and are not results.
- Not checked: the paid proxy and paid live-audio stream on AWS (no key on the server yet), Safari, Firefox, real phones and screen readers.
- Live mic check on the deployed site: a real sample was fed through the browser audio path with a deliberately invalid key. Audio reached the phrase detector and the speech call, and the refusal was shown. This proves the plumbing, not a transcription.
- The stream pause moved from 600 ms to 400 ms (`api.stream`, not an engine setting). On the six real samples, 600 ms often missed natural pauses and cut phrases at the 10-second limit. No exam audio was used.
- The mic now starts inside the tap, because Safari and iPhones block audio started later. The per-call headline now compares Pehchaan with keywords alone, so it cannot credit Pehchaan with the keyword gain. Safari and real phones are still unverified.

## Sat 21 Nov 2026, late night IST: one-line harness, real demos, language honesty
- Added `wrap()`, the `pehchaan` command, `/v1/connect`, a `language` setting on every route, and the number guard for languages without rules. The engine is unchanged (`git diff exam-freeze` on engine paths is empty).
- Testing with the real OpenAI classes found that `AsyncOpenAI.create` hides its `async` behind a decorator. Fixed and covered by tests.
- Language probe: real voice for hi, hl, en; synthetic for te; partial for nine languages; unsupported for ur, ar, es. `gpt-transcribe` refused pa, or and as hints with HTTP 400, so those retry without a hint.
- Rebuilt the Playground into five demos, restored the headline with the measured line under it, put an info button inside every status badge, and shortened the pages.
- Found while testing the Learning tab: a wrong answer that sounds right can pass the learning checks (it replays cleanly and harms nothing). The tab says so, and undo is the safeguard.
- Driven in headless Chrome at 1440, 390 and 320 px. Not checked: Safari, Firefox, real phones, screen readers, and live calls to non-OpenAI speech providers.
- Released `7d024d2` to AWS. `deploy/verify_live.mjs` passed all 18 checks, including a paid proxy call and a real-audio stream. The deployed site was driven in Chrome at 1440, 390 and 320 px: connect, wrong passcode, paste, refuse, learn, replay, undo, with no console errors or overflow.
- On a clean server environment, `pip install` from GitHub, `wrap(OpenAI())`, `wrap(AsyncOpenAI())`, the `pehchaan` command and the `uvx` command all worked, with real paid transcription calls for the first three. Deepgram and Sarvam were checked only with their documented answer shapes, not their live APIs.
