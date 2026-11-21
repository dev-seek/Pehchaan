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
