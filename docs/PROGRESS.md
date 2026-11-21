# PROGRESS: milestone tracker (update after every milestone)

Last updated: Sat 21 Nov 2026, evening IST. Code freeze: Sun 22 Nov 14:00 IST.

## Done
- Engine v0.2: language packs + routing, sound matching on 9 scripts, resolvers, injected judge/memory
- Benchmark: 30 dev scripts x 2 voices (60 synthetic clips), 30 locked test scripts, real-voice recordings indexed
- Step A (safety + honest scoring): independent oracle + damage audit (D-020), read-only numbers (D-021), second
  opinion (D-022), admission gate + guards (D-023, D-024), run manifests, exam guard (D-025), regression gate (D-026)
- Product wired to the main system `P_on_B1_C3` (D-019); API exposes `refused`, `heard_value`, `admission`
- First honest dev run: `results/dev_20261121_182109` (damaged edits 12 to 0; see EVAL.md for limits)
- Local judge demo (Step B), measured Benchmark Lab, and API examples. The dev rerun adds ASR timings and passes
  the regression gate (`results/dev_20261121_185123`). Rehearsal outcomes are in docs/LOG.md.

## In progress
- Localhost rehearsal and preparation for the public-deploy lock.

## Next
1. **Step C:** public-deploy lock for recording/script endpoints, path sanitising, passcode and rate limit
2. Sunday morning (Phase 5): `make exam-audio`, then `make bench-test-FINAL-ONCE` exactly once and log it
3. Slides and README with real, labelled numbers. Rehearse before the 14:00 freeze.

## Known gaps (do not hide these)
- No result from the locked real-voice test exists yet. Dev numbers are synthetic and tuned on: optimistic.
- `tools/make_audio.py --phone-copy` has never been run and has no unit test.
- Two silent AMOUNT errors remain on dev (both transcripts misheard the same way; same model family).
- Pehchaan is NOT self-learning: nothing generates candidate improvements; memory is a per-user lookup (names and
  places only) whose value is not evaluated. It does have real harness parts: proposal vs admission, an independent
  acceptance check, run manifests, and a regression gate with human adoption and git rollback.
