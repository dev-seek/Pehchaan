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

## What this result is not

The fresh set was written by the builder's coding agent, so it is a red-team check and not a benchmark. It does not change any number from the locked exam, which measured the engine without this layer.
