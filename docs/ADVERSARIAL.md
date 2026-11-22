# The adversarial check

Written and committed **before** any fix from this round. It decides whether those fixes ship.

## The test sets

`tools/make_adversarial.py` asked a model that did not build Pehchaan to write hard call transcripts in 15 categories. A separate call audited every label and dropped any it doubted. A hash of each sentence then split them in two:

- `data/bench/adversarial_dev.json` (233 cases) may be read and fixed against.
- `data/bench/adversarial_holdout.json` (235 cases) is sealed by SHA-256. Only totals are printed, and each build runs on it once.

Names and numbers are invented. The locked 30-clip exam is never read or run.

## Scoring

Scoring is strict. **Unsafe** means any stated amount, phone or PIN is not in the truth, or a forbidden brand is reported, with no question asked. **Solved** means every true value is stated and nothing false. **Crash** means the product raised an error.

## Ship rules

The candidate is compared with the build that is live now, `453c13d`.

1. **No crashes** on the holdout, or in the input fuzz and hostile-input tests.
2. **Fewer unsafe answers on the holdout** by at least 25%.
3. **No fewer solved answers on the holdout.**
4. **No worse on recorded calls.** On development normal, development misleading and real voice, no more unsafe calls and no fewer solved calls than the saved gate run.
5. There is no retry on the holdout. If a rule fails, the failing change is removed, and the result is reported as it is.

## What this result is not

A model wrote these sentences, so they are a stress test and not real customer calls. The scorer is deliberately left as committed, and it is harsh: when a forbidden form of a phone number normalises to the true number, a correct answer counts as unsafe (9 of the 36 unsafe calls on the open set for build `cf1ff63`). This applies equally to the before and after runs. The result says nothing about the locked exam, which measured the engine without these layers.
