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

## Result (one run, build `cf1ff63` against live `453c13d`)

| 235 sealed calls | Before | After |
|---|---|---|
| Unsafe (a false value stated with no question) | 98 | 26 |
| Solved | 75 | 108 |
| Asked or missed | 62 | 101 |
| Crashed | 0 | 0 |
| Median added time | 1.94 s | 2.04 s |

All ship rules passed. The comparison covers the crash and number fixes (`9a66eef`) and the role-aware reading (`cf1ff63`) together. On the open set the number fixes alone moved unsafe from 104 to 103, so nearly all of the gain comes from the reading.

- **The cost is more questions.** 39 more calls now end in a question or a missing fact.
- **Recorded calls sit exactly on the bar:** 49 solved and 2 unsafe, 26 and 2, 17 and 3. One real-voice clip moved between 3 and 4 unsafe across earlier builds, so this is not a wide margin.
- **A call can now use two LLM calls.** The second runs only when the first objects to a number. On the open set, 27 of 28 objections were to a value that was not in the truth.
- **26 calls still state something false.** Words that sound like brands remain the weakest category.

## One change after the sealed run

The packaged examples then showed a regression that the holdout does not measure: "mera bhai Koti kal ghar aayega" no longer stated a false crore, but the reader called Koti an everyday word instead of a person. The cause was showing `code read: 10000000` beside a single number word. That hint is now left out for a lone word with no digits (D-055).

The holdout was **not** rerun, so 98 to 26 describes `cf1ff63`, not this small follow-up. On the open sets the follow-up measured 95 solved and 36 unsafe of 233 (93 and 36 before it). Three runs of the recorded sets gave 49 solved and 2 unsafe, 26 and 2, and 17 solved with 3, 4 and 3 unsafe. The real-voice line is unstable on one clip where both transcripts mishear the same phone digit. Before the meaning layer that set had 4 unsafe.

