# START HERE: status and next task

**Pehchaan** ("recognition / identity") is a layer after any speech-to-text model on Indian phone calls. It makes
sure the *facts* in a transcript (who called, from which company, which place, which phone number, which PIN, how
much money) are **right, or flagged with one short question.** It uses what the phone already knows (contacts,
caller ID, SMS, city) plus Indian sound and number rules, works on code-mixed speech, and remembers confirmed names.
Track: BUILDERS '26 Track 2, "Voice AI for India", idea "Indian names and entities".

_Last updated: Sat 21 Nov evening IST (Step A done). Milestones: docs/PROGRESS.md._

## What works now
- Engine: text / languages / sound / numbers / context / asr / judge / resolvers / **policy** / output / pipeline
  (docs/ENGINEERING.md); language packs hi/en/te with code-mixed routing; sound matching across 9 scripts
- **Resolvers only propose; the AdmissionGate decides** (D-023): numbers are read-only (D-021), common words and
  acronyms are guarded (D-024), a second transcript without context keywords is the second opinion (D-022)
- Product (`make serve`) runs the main system: keyword transcript as input, plain transcript as second opinion
  (D-019); two speech-to-text calls per clip. API shows `refused`, `heard_value`, `admission` (docs/API.md); memory
  refuses PHONE/PIN/AMOUNT (HTTP 400) and the UI no longer says "learned" when it refuses
- Independent oracle scorer + damage audit (D-020), run manifests, `make gate` / `make adopt` (D-026), exam guard (D-025)
- Latest honest dev run `results/dev_20261121_182109` (60 synthetic-voice clips, 164 facts, optimistic, tuned on):
  main system 97.6% accuracy [95-99], 1.2% silent errors, 0 damaged edits (was 12), 0.03 flags/clip; adversarial C4
  95.1%, 1.2% silent, 0 damaged (was 15). Intervals overlap: accuracy gain not proven; the damage drop is the clear gain.
  Full table and caveats: docs/EVAL.md
- `make check` green (lint + tests + repo invariants)

## NOT verified / not done
- [ ] **No result from the locked real-voice test exists.** Do not quote dev numbers as real-voice results
- [ ] `tools/make_audio.py --phone-copy` (builds `test_real_phone`) was never run and has no unit test
- [ ] Public-deploy lock (recording/script endpoints, path sanitising, passcode/rate limit) is NOT done
- [ ] Two silent AMOUNT errors remain on dev (dev_014, dev_020): both transcripts misheard the same way
- [ ] C4 English accuracy is 86.7%; flag precision 100% rests on very few flags (2 on main, 6 on C4)
- [ ] Sarvam TTS request shape (`tools/make_audio.py::tts_sarvam`); OpenAI TTS is the fallback
- Not self-learning: memory is a per-user lookup (names/places) whose value is not evaluated

## NEXT TASK (details in docs/PLAN.md)
**Step B: Demo UI.** Side-by-side "Call Summary & Action Card" (Base vs Pehchaan Fixed / Verified / Flagged),
1-tap Memory Confirm then Replay Auto-Fix, plus live mic mode. Work in `app/static/` against docs/API.md.
Then the public-deploy lock. Phase 5 on Sunday morning: `make exam-audio`, then `make bench-test-FINAL-ONCE`
exactly once, and log it. Code freeze Sun 22 Nov 14:00 IST.
After any engine change: `make check`, `make bench-dev`, `make gate`. Adopt a baseline only on purpose.

## How to run
```bash
make setup && cp .env.example .env    # add OPENAI_API_KEY (+ optional SARVAM_API_KEY)
make check && make bench-sim && make serve   # then, with an API key: make bench-dev && make gate
```
