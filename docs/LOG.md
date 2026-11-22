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

## Sun 22 Nov 2026, early morning IST: final release checks
- Released `78792d4`. Correction to the previous entry: the real paid calls were `wrap(OpenAI())`, `wrap(AsyncOpenAI())` and the `pehchaan` command on audio. The `uvx` run checked a text transcript, which needs no key.
- On the deployed site, a real voice sample was injected through the browser mic path: 14.4 s of audio, 3 phrases, 2 facts, 1 question and a final result. A file upload sent `language=mr`, a real mouse hover opened the status help, and the Integrate stream snippet reached `final`.
- A real `google-cloud-speech` response object is read correctly (constructed locally, no Google API call). Deepgram, Sarvam, Google and Azure have still not been called live.
- A failed or rate-limited sample now shows the reason and a Try again button. Phone tab labels no longer clip.
- Risk for the demo: everyone on one network shares 15 live requests per hour, and each spoken phrase uses one. Present from a phone hotspot.

## 2026-11-22: Knowledge sources added
Added `pehchaan_sdk/knowledge`, the free simulated Company data tab, and `tests/test_knowledge.py`. `make check` passes with 383 tests and the engine diff against `exam-freeze` is empty. NOT yet done: browser check of the new tab at 1440/390/320, API/README docs, and release to AWS. The live site does not have this feature yet.

## 2026-11-22: Company data released
Released `52fbde0`. Real-server tests found and fixed two connector bugs (a records path that pointed at a list, and slow HTTP reported as an error). Chrome checks at 1440/390/320 show no errors or overflow on any tab, and every failure mode of the new tab was driven. `deploy/verify_live.mjs --free` passes and the live health check reports the engine matches the exam. Not run: a real CRM, Safari, Firefox, real phones, screen readers. While writing the private notes, the published exam report showed flag precision of 50% (14 questions, 7 needed, standard line) and harness p95 of about 1.5 s when the judge runs. Quote those rather than the dev figures.

## 2026-11-22: Private sources keep their numbers local
Released `1adde56`. `hub.context_for()` was including a private source's phones, PINs and amounts, so a test was added and they now stay on the customer's machine. `deploy/verify_live.mjs --free` passes, the security group is 80/443, and the engine still matches the exam.

## 2026-11-22: Final platform check before the lock
Released `725be94`. Checked three reported bugs and all were real: Hindi and Telugu depended on device fonts, demo wording differed from the controls, and tabs replaced the chosen sample. Fixed all three. Removed the call-count caps (D-049), added saved calls with caller ids, per-caller teaching, a free pasted-text path, real calls on every phone line (D-050) and `SUBMISSION.md`. `make check` is green and the engine diff from `exam-freeze` is empty. Chrome at 1440/390/320 on the live site drove every new flow with no errors, overflow or third-party requests. A saved call and its lesson survived a redeploy. One paid audio call was saved and listed (speech 1.5 s, check 3.2 s because the judge ran), and `deploy/verify_live.mjs` passed its paid proxy and stream checks. Not run: Safari, Firefox, real phones, screen readers, a real company system, non-OpenAI speech providers.

## 2026-11-22: Meaning check for names read as money
Two live tests showed a brother named Koti rewritten as ₹1,00,00,000 and "का नाम" reported as a company. Causes: number words never reached the judge, and judge-rejected candidates were still reported. Added `pehchaan_sdk/meaning.py` (D-051) outside the frozen engine. Engine diff against `exam-freeze` is empty. NOT verified: real recorded calls containing these words, or languages beyond Hindi, Hinglish, English and Telugu. The 24 test sentences were written for this check and are not a benchmark.
Released `376cb8a`. On the live site with the passcode, both reported sentences now show the word as a person with no rupee amount, real money still reads correctly, and the full browser flow passes with no console or network problems.
Released `2072afe`. Three synthetic-voice audio calls through the live audio route: the Telugu and Hindi family sentences show a person with no rupee amount, and a real one-lakh transfer still reads as money. No recorded human call with these words has been tested.

## 2026-11-22: Exact money fix
The stress test showed decimal money was wrong on the live site ("2.5 lakh" became ₹7,00,000). Added exact arithmetic outside the frozen engine (D-052). 483 tests pass, the engine diff against `exam-freeze` is empty, and 0 of 150 recorded calls changed. The fresh attack set and ship rules were committed first in `812a9b7`.

## 2026-11-22: Context-blind meaning layer
Locked 116 fresh attacks and the ship rules in `812a9b7`, then built the layer. The first recorded-call check found a real flaw (a garbled place dropped as ordinary words), fixed on development data only. The candidate `f5070cd` then passed on its single run: fresh confidently wrong answers 32 to 12, solved 78 to 98, and no recorded set worse. Added the Meaning tab with saved answers, each measured over three runs. "federal government" is still wrong and is shown as a miss.
Released `4dfb84c`. On the live site: the free checks pass, passcode text calls return the set-aside facts, three synthetic-voice audio calls read names and money correctly, and the full browser flow passes in headless Chrome. The Meaning tab has no page overflow at 1440, 390 and 320 px. Real phones and Safari are still unchecked.
Released `fc77a17`. Every live answer route now shares the same checks. On the live site, a synthetic-voice call through the mic stream and the older process route both read "2.5 lakh" as ₹2,50,000. Calls that ran the meaning layer are labelled unmeasured. Real phones, Safari, a human voice on the new sentences and paid calls under load are still unchecked.

## 2026-11-22 08:35 IST: plan fixed before the one sealed run

Candidate build: `cf1ff63`, compared with live `453c13d`. The crash fix `9a66eef` is already released and is part of this comparison.
Recorded sets on this build, as printed before the sealed run: development normal 49 solved, 2 unsafe; development misleading 26 solved, 2 unsafe; real voice 17 solved, 3 unsafe. These sit exactly on the bar. One real-voice clip (courier, dropouts line) moved between 3 and 4 unsafe across runs of earlier builds, so this pass is not a robust margin. The recorded sets are not rerun on this build to look for a better number.
If any rule in `docs/ADVERSARIAL.md` fails, `cf1ff63` is reverted, `9a66eef` stays live, and the result is reported as it is. The holdout is not rerun.

## 2026-11-22 08:50 IST: sealed adversarial result
The one sealed run of `cf1ff63` against live `453c13d` passed: unsafe 98 to 26 of 235, solved 75 to 108, asked or missed 62 to 101, 0 crashes. Every direct engine call now goes through the safe wrapper. `bench/stress.py` feeds random, hostile and broken-LLM input through the answer path with no cost.
A follow-up (D-055) restored Koti as a person after the sealed run, so the sealed figure does not cover it. Recorded real voice measured 3, 4 and 3 unsafe across three runs on the final code, so that line is unstable by one clip.

## 2026-11-22 09:05 IST: release blocked by expired AWS session
`bench/stress.py` ran 100,000 random, hostile and broken-LLM inputs on the final code: 0 crashes and no number the code had not read. A production-mode copy on the dev machine passed real text, proxy audio, verify-audio and stream calls, 14 hostile requests with no server error, and the Meaning tab at 1440, 390 and 320 px. The release could not run because the AWS session token expired, so the live site still runs `9a66eef`.

## 2026-11-22 09:30 IST: before and after on the site, README rewritten
Fresh AWS keys arrived and `0841e1f` was released and verified live, including real text, audio and a real WebSocket stream. The frozen engine was scored once on the sealed calls as a reference (178 false answers), and the hero and Benchmark Lab now show 178, 98, 26. A clean `pip install` crashed on the first call because `data/meaning` was not in the wheel. That is fixed and tested (D-056). The README now leads with examples, the before and after, and a one-line path for other builders.


## 2026-11-22 09:35 IST: final end-to-end check on the live site
Released `ced530f`. On the live URL: the free checks passed; real text, proxy audio, verify-audio and a real WebSocket stream returned the expected facts; 14 hostile requests caused no server error; the full browser flow passed; and Home, Benchmark Lab, How it works and Integrate had no overflow or console errors at 1440, 390 and 320 px in headless Chrome. A clean install from GitHub ran its first call. Real phones and Safari are still unchecked.

## 2026-11-22 09:40 IST: locked release
Live runs `7ba4cab`, which adds only layout fixes to `ced530f`: six step cards, and the Benchmark Lab table fitting at 320 px. All live checks were repeated on it and passed. The first visit takes about 2 seconds to load the hero numbers from `us-west-2`. Still unchecked: real phones, Safari, Firefox and screen readers. The repo has no licence yet, which is the builder's decision before other teams reuse it.

## 2026-11-22 12:10 IST: noisy-line test in Your voice (D-057)
Added "Put it on a worse phone line" after a recording or upload. It runs the clear and noisy copies at once and shows speech alone against Pehchaan, fact by fact.

Check on the 6 packaged real clips (one speaker, 21 human-labelled facts, their contexts filled in, one run per line; a bug-finding check, not the exam). Silent errors, speech alone to Pehchaan, scored with human labels: Noisy 4 to 1, Very noisy 13 to 2, Dropouts 13 to 4. Pehchaan was worse on 0 of 18 runs. The on-screen reference gave 3 to 0, 12 to 1 and 11 to 3. Noise is random, so a repeat will differ.

Browser flow passed at 1440, 390 and 320 px with real speech fed through the page's microphone path. Chrome's fake audio device produced silence here, so `getUserMedia` was replaced by a decoded recording. No human spoke into a physical microphone for this check.

## 2026-11-22 12:15 IST: noisy-line test released and checked live
Live runs `ddb710c`. On the live URL: free checks, real text, proxy, audio and WebSocket stream, 19 hostile line-test requests with 0 unexpected answers, 8 parallel runs (6 served, 2 refused as busy, no server error), and the full browser flow at 1440, 390 and 320 px.

Second run of the 6 packaged clips, human labels, speech alone to Pehchaan: Noisy 6 to 1, Very noisy 7 to 1, Dropouts 13 to 2. Pehchaan was worse on 0 of 18 runs. The first run is in the entry above, and the gap between them is the random noise.

The on-screen demo sentence does not always show a difference. With two synthetic voices, 8 runs per line, a visible catch appeared in 4 of 8 on Dropouts, 2 of 8 on Noisy and 1 of 8 on Very noisy, and Pehchaan was worse in 0 of 24.

## 2026-11-22 12:55 IST: submission package
Added `make demo` (no API key, labelled mock speech), rewrote the top of `AGENTS.md` for reviewers, and built the five-slide `PRESENTATION.pdf` from `docs/deck/deck.html`. A blank Ubuntu 24.04 container following `AGENTS.md` found that `/health` and the tests crashed with no `git` installed, so the manifest no longer needs git.
