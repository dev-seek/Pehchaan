# START HERE: status and next task

**Pehchaan** ("recognition / identity") is a layer after any speech-to-text model on Indian phone calls. It makes
sure the *facts* in a transcript (who called, from which company, which place, which phone number, which PIN, how
much money) are **right, or flagged with one short question.** It uses what the phone already knows (contacts,
caller ID, SMS, city) plus Indian sound and number rules, works on code-mixed speech, and learns confirmed names only
after testing them.
Track: BUILDERS '26 Track 2, "Voice AI for India", idea "Indian names and entities".

_Last updated: Sat 21 Nov night IST (verified learning, public lock, site redesign). Milestones: docs/PROGRESS.md._

## What works now
- Engine: text / languages / sound / numbers / context / asr / judge / resolvers / **policy** / output / pipeline
  (docs/ENGINEERING.md); language packs hi/en/te with code-mixed routing; sound matching across 9 scripts
- **Resolvers only propose; the AdmissionGate decides** (D-023): numbers are read-only (D-021), common words and
  acronyms are guarded (D-024), a second transcript without context keywords is the second opinion (D-022)
- `make serve` opens the site: Home, Try it, How it works, Proof, API, with an info button on every term. Try it shows
  the base model and Pehchaan side by side, with call hints, evidence, callback preview, and confirm, replay and undo.
- Proof reads the measured harness report. The API page has working Python and curl examples for
  `/v1/pehchaan/transcribe`, the same multipart contract as `/api/process` (docs/API.md).
- Independent oracle scorer + damage audit (D-020), run manifests, `make gate` / `make adopt` (D-026), exam guard (D-025)
- **Verified learning** (D-029): a confirmation is adopted only after it passes safety checks and a replay on 60 labelled
  calls; ledger and undo included. **Public lock** (D-030): locked by default, free offline samples, passcode for live audio
- Latest measured dev run (see `results/latest_dev.json`) (60 synthetic-voice clips, 164 facts, optimistic, tuned on):
  main system 97.6% accuracy [95-99], 1.2% silent errors, 0 damaged edits (was 12), 0.03 flags/clip; adversarial C4
  94.5%, 1.2% silent, 0 damaged (was 15). Intervals overlap: accuracy gain not proven; the damage drop is the clear gain.
  The rerun adds separate ASR and post-ASR timings. Full table and caveats in docs/EVAL.md.
- `make check` green (lint, tests, repo invariants). `make gate` passed with the adopted baseline.

## NOT verified / not done
- [ ] **No result from the locked real-voice test exists.** Do not quote dev numbers as real-voice results
- [ ] The public URL is not deployed yet
- [ ] Two silent AMOUNT errors remain on dev (dev_014, dev_020): both transcripts misheard the same way
- [ ] C4 English accuracy is 86.7%; flag precision 100% rests on very few flags (2 on main, 6 on C4)
- [ ] The site was driven in headless Chrome only. Real phones, Safari, Firefox, screen readers, recorded real-voice
  samples and a live run with the correct passcode are unchecked
- [ ] Sarvam TTS request shape (`tools/make_audio.py::tts_sarvam`); OpenAI TTS is the fallback
- Learning comes from human confirmations only: the engine does not invent rules or change its own thresholds

## NEXT TASK (details in docs/PLAN.md)
**Builder decides when to run the one-time exam on a frozen engine** (`make exam-audio`, then `make bench-test-FINAL-ONCE`
exactly once, and log it). Do not tune on the six real-voice samples any more: they found bugs (D-033), so they are a
regression check. Tune on dev only. Code freeze Sun 22 Nov 14:00 IST.
After any engine change: `make check`, `make bench-dev`, `make gate`, `make learning-proof`, `make real-check`, `make publish`.

## How to run
```bash
make setup && cp .env.example .env    # add OPENAI_API_KEY (+ optional SARVAM_API_KEY)
make check && make bench-sim && make serve   # then, with an API key: make bench-dev && make gate
```
