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
