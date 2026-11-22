# START HERE: status and next task

**Pehchaan** ("recognition / identity") is a layer after any speech-to-text model on Indian phone calls. It makes
sure the *facts* in a transcript (who called, from which company, which place, which phone number, which PIN, how
much money) are checked, so **every fact is either right or it asks one short question. That is the goal: on the locked exam 16% still slip through silently.** It uses what the phone already knows (contacts,
caller ID, SMS, city) plus Indian sound and number rules, works on code-mixed speech, and learns confirmed names only
after testing them.
Track: BUILDERS '26 Track 2, "Voice AI for India", idea "Indian names and entities".

_Last updated: Sun 22 Nov 09:35 IST (before/after ladder on the site, new README, pip install fixed, D-054 to D-056). Live: https://52-24-174-127.sslip.io. Milestones: docs/PROGRESS.md._

## What works now
- Engine: text / languages / sound / numbers / context / asr / judge / resolvers / **policy** / output / pipeline
  (docs/ENGINEERING.md); language packs hi/en/te with code-mixed routing; sound matching across 9 scripts
- **Resolvers only propose; the AdmissionGate decides** (D-023): numbers are read-only (D-021), common words and
  acronyms are guarded (D-024), a second transcript without context keywords is the second opinion (D-022)
- **Live at https://52-24-174-127.sslip.io** (AWS `us-west-2`, `ENV=production`). `make deploy` ships committed code; `deploy/verify_live.mjs` checks it from outside.
- Live Playground has five demos: Compare, Your voice (connect, choose model and language, speak), Context, vs LLM and Learning.
  Benchmark Lab adds a language table. Integrate is one install, one line, and a snippet per provider (D-042 to D-046).
- Installable SDK `pehchaan_sdk` (`pip install "git+https://github.com/dev-seek/Pehchaan.git"`): `wrap(client_or_function)` and the `pehchaan` command (D-036, D-037, D-043).
- Languages: real voice for Hindi, Hinglish, English; synthetic for Telugu; partial for nine more; see docs/LANGUAGES.md (D-045).
- Public API: OpenAI drop-in `POST /v1/audio/transcriptions`, `/v1/verify-audio`, `/v1/verify-transcript`, `/v1/memory/confirm`,
  `WS /v1/stream`, `/v1/bench`, `/health`. Passcode or own key, rate limits, and audio limits (docs/API.md, D-038 to D-040).
- Independent oracle scorer + damage audit (D-020), run manifests, `make gate` / `make adopt` (D-026), exam guard (D-025)
- **Verified learning** (D-029): a confirmation is adopted only after it passes safety checks and a replay on 60 labelled
  calls; ledger and undo included. **Public lock** (D-030): locked by default, free offline samples, passcode for live audio
- Latest measured dev run (see `results/latest_dev.json`) (60 synthetic-voice clips, 164 facts, optimistic, tuned on):
  main system 97.6% accuracy [95-99], 1.2% silent errors, 0 damaged edits (was 12), 0.03 flags/clip; adversarial C4
  94.5%, 1.2% silent, 0 damaged (was 15). Intervals overlap: accuracy gain not proven; the damage drop is the clear gain.
  The rerun adds separate ASR and post-ASR timings. Full table and caveats in docs/EVAL.md.
- `make check` green (lint, tests, repo invariants). `make gate` passed with the adopted baseline.

## NOT verified / not done
- [ ] Exact money (D-052) and the context-blind meaning layer (D-053) came after the exam, so no exam number includes them. The layer passed `docs/MEANING_GATE.md` (32 to 12 on self-written attacks), and 12 still fail
- **The locked exam has run and cannot run again** (D-034, table in docs/EVAL.md). Standard line: Pehchaan 75.6% right, 15.9% silent. Noisy
  line: 54.9% right, 31.7% silent. The engine is frozen at tag `exam-freeze`; `make check` fails if it changes.
- [ ] Many exam facts are still wrong with no warning. The headline is a goal, and the line under it gives the measured 16%
- [ ] External speech providers are supported but unmeasured. Their answer shapes come from their docs and were not run live
- [ ] Partial languages have no accuracy number, and the probe sentences are not reviewed by native speakers
- [ ] Two silent AMOUNT errors remain on dev (dev_014, dev_020): both transcripts misheard the same way
- [ ] C4 English accuracy is 86.7%; flag precision 100% rests on very few flags (2 on main, 6 on C4)
- [ ] The site was driven in headless Chrome only. Real phones, Safari, Firefox, screen readers, recorded real-voice
  samples and a live run with the correct passcode are unchecked
- [ ] Sarvam TTS request shape (`tools/make_audio.py::tts_sarvam`); OpenAI TTS is the fallback
- Learning comes from human confirmations only: the engine does not invent rules or change its own thresholds

## NEXT TASK (details in docs/PLAN.md)
**Do not change the engine.** The build is released and verified on the live site. Then, in order: try the live mic on a real phone and in Safari, set a hard budget on the OpenAI project (the passcode is now the only lock on paid calls), rehearse the seven tabs from a phone hotspot, and after
the event revoke the AWS session and rotate the OpenAI key. Teardown:
`deploy/aws_teardown.sh`. Code freeze Sun 22 Nov 14:00 IST.

## How to run
```bash
make setup && cp .env.example .env    # add OPENAI_API_KEY (+ optional SARVAM_API_KEY)
make check && make bench-sim && make serve   # then, with an API key: make bench-dev && make gate
```

## Latest status (2026-11-22)
Exact money and the context-blind meaning layer are live, with a Meaning tab (D-052 to D-054). The sealed adversarial holdout has been used for build `cf1ff63`: unsafe 98 to 26, solved 75 to 108, asked or missed 62 to 101, 0 crashes (`docs/ADVERSARIAL.md`). Do not edit `pehchaan_sdk/referee.py` or `pehchaan_sdk/settle.py` without a new pre-written test, because that holdout is now spent. A small follow-up (D-055) came after the sealed run and was checked only on open and recorded sets.

Knowledge sources and the Company data tab are live at `725be94`, with saved calls per caller, no call-count limit and a free pasted-text check (D-049). `SUBMISSION.md` covers the four submission items. The platform is locked for the presentation, documented and browser-checked at 1440/390/320. No real CRM has been connected. Next task: rehearse the demo on a phone hotspot. Do not change the engine. After the event: revoke the AWS keys, rotate the OpenAI key and run `deploy/aws_teardown.sh`.
