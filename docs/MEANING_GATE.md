# The meaning layer gate

Written and committed **before** the meaning layer was built. It decides whether the layer ships.

## What is compared

- **Baseline:** the build with the money fix, using the older word check. This is what stays live if the gate fails.
- **Candidate:** the same build plus the context-blind meaning layer.

## What it runs on

| Set | Calls | Note |
|---|---|---|
| Fresh attacks | `data/bench/meaning_attack.json` | Self-written, locked by SHA-256 before the layer existed, run once |
| Development calls, normal hints | 60 | Synthetic voices |
| Development calls, misleading hints | 60 | Synthetic voices |
| Real voice | 30 | Six samples on five simulated phone lines |

The locked 30-clip exam is never read or run.

## The rules

1. **No worse on recorded calls.** On each of the three recorded sets, the candidate has no more unsafe calls and no fewer solved calls.
2. **At least half the confidently wrong answers on fresh attacks.** Candidate unsafe calls × 2 ≤ baseline unsafe calls.
3. Both must hold. There is no tolerance, retry or re-tuning on the fresh set.
4. If it fails, or is not finished by **10:15 IST on 22 Nov 2026**, only the money fix stays live.

**Solved** means every labelled fact is right and nothing false is stated. **Unsafe** means something false was stated with no question.

The two saved runs are in `data/published/meaning_gate/`, so `python -m bench.meaning_gate verdict` reproduces the table.

## What this result is not

The fresh set was written by the builder's coding agent, so it is a red-team check and not a benchmark. It does not change any number from the locked exam, which measured the engine without this layer.

## Result (22 Nov 2026, candidate `f5070cd`, run once)

**Passed.** The layer was not edited after this run.

| Set | Solved: before → after | Confidently wrong: before → after |
|---|---|---|
| Fresh attacks (116) | 78 → 98 | **32 → 12** |
| Development, normal hints (60) | 47 → 49 | 2 → 2 |
| Development, misleading hints (60) | 26 → 26 | 2 → 2 |
| Real voice (30) | 17 → 17 | 4 → 3 |

**How far this goes:**

- Only the fresh attack result is unseen, and the same agent wrote those sentences. The recorded sets were used while building the layer, so they are a regression check.
- The money fix was written after this set was locked, with its money cases known. Both sides of the gate include that fix, so the gate is unaffected, but this set is not independent proof of the money fix.
- 12 fresh attacks still get a confident wrong answer. "federal government ka naya rule hai" was wrong in 3 of 3 later runs.
- The layer adds about 0.8 to 0.9 seconds and one gpt-4.1 call to a paid call with facts.
- It can set aside a real phone number that it reads as another kind of number. This happened once on a real-voice line. The number stays in the transcript and is listed in `understood`.

