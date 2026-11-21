# PROGRESS: milestone tracker (update after every milestone)

Last updated: Sat 21 Nov 2026, night IST. Code freeze: Sun 22 Nov 14:00 IST.

## Done
- Engine v0.2: language packs + routing, sound matching on 9 scripts, resolvers, injected judge/memory
- Benchmark: 30 dev scripts x 2 voices (60 synthetic clips), 30 locked test scripts, real-voice recordings indexed
- Step A (safety + honest scoring): independent oracle + damage audit (D-020), read-only numbers (D-021), second
  opinion (D-022), admission gate + guards (D-023, D-024), run manifests, exam guard (D-025), regression gate (D-026)
- Product wired to the main system `P_on_B1_C3` (D-019); API exposes `refused`, `heard_value`, `admission`
- First honest dev run: `results/dev_20261121_182109` (damaged edits 12 to 0; see EVAL.md for limits)
- Local judge demo (Step B), measured Benchmark Lab, and API examples. The dev rerun adds ASR timings and passes
  the regression gate (`results/dev_20261121_185123`). Rehearsal outcomes are in docs/LOG.md.
- Verified learning with ledger and undo, measured on a held-out voice (D-029)
- Public lock: private routes hidden, free offline samples, passcode and budget for live audio (D-030)
- PIN-as-money bug fixed in engine and scorer (D-031); README rewritten

- Website redesign (Home, Try it, How it works, Proof, API, with info tooltips), driven in headless Chrome at three widths
- A learned correction can no longer overwrite a real name the caller said (D-032)

- Six real-voice samples recorded and packaged. Measured on five line qualities (`make real-check`, Proof page)
- Look-alike contact rule, mixed amounts and phone-plus-amount reading fixed (D-033). Phone-line tool now has a test

- Engine frozen at `exam-freeze`. Locked exam run once on both lines (D-034). Four-model comparison added (D-035)
- Installable SDK, OpenAI drop-in proxy, verify endpoints, WebSocket stream, production limits (D-036 to D-040)
- Three-tab site with model picker, paste mode, live mic, exam tables and line-quality curve (D-041)
- Deployed on AWS `us-west-2`: https://52-24-174-127.sslip.io

## In progress
- Paid end-to-end check on AWS. It needs the builder to install the OpenAI key on the server.

## Next
1. **Builder:** run `bash deploy/set_secrets.sh` from the repo. It installs the key without printing it and runs all checks
2. Try the live mic on a real phone and in Safari. Rehearse before the 14:00 freeze

## Known gaps (do not hide these)
- The locked exam is one speaker on a simulated phone line. Pehchaan's gain is mostly asking; right facts barely move.
- Dev numbers are synthetic and tuned on: optimistic, and they did not carry over to the exam.
- External speech providers are supported but unmeasured.
- The six real-voice samples are one speaker and 21 facts, and they were used to find bugs (D-033), so they are not evidence of a rate.
- Two silent AMOUNT errors remain on dev (both transcripts misheard the same way; same model family).
- Learning comes from human confirmations only. The engine does not invent rules or change its own thresholds. The
  held-out proof uses scripted confirmations on dev data, and its gain on the main system is small (154 to 156 of 164).
- The public rate limit sees a proxy as one client, so behind a load balancer it acts as a shared limit.
