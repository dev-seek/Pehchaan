# Live action benchmark

The primary outcome is wrong protected actions allowed per 1,000 eligible tool opportunities. Each opportunity has an
independent label for the exact argument object or expected deferral. The scorer also records correct completions and
those after clarification, missed fields, unnecessary questions, deferrals, p50/p95 added latency and model cost per
1,000 checks. Eligible opportunities include actions that should be refused. Completion rates use only opportunities
where a correct action was possible.

## Run the offline replays

```bash
.venv/bin/python -m bench.live --split dev --out results/live-dev.json
.venv/bin/python -m bench.live --split release --out results/live-release.json
.venv/bin/python -m bench.live --split transfer --out results/live-transfer.json
```

The invented development and release fixtures have 48 opportunities and 24 source groups apiece. Transfer has 18
opportunities and nine groups. The parcel pickup workflow is held out, with only its declared policy supplied to the
runtime. Source groups, scenario families and action field values are disjoint. The release and transfer files have
SHA-256 seals. The partner's release set needs independent custody and fresh labels before tuning.

The scenarios cover misleading business context, transcripts agreeing on a wrong value, omissions, corrections,
interruptions and premature tool calls. Baselines accept the prewritten proposal or emulate the native validator and
readback disposition specified by the scenario author. In a pilot the platform supplies its current flow. Reports pin
policy, scorer and dataset digests. They include paired 95% intervals clustered by source group and breakdowns by field,
workflow, language, noise and provider.

The bounded search varies source agreement and confidence floors within pinned provider/model/version scopes.
Candidates must keep completion within 3 percentage points and satisfy the question, deferral, cost and latency
budgets. The release gate requires a minimum 25% reduction in wrong allows versus the strongest comparison,
a positive lower bound on the paired reduction, the completion constraint and a passing safety suite. The initial
search kept the incumbent. The fixture release gate held because the incumbent already had zero wrong allows on
the release fixtures. Sparse slices need more data to support a decision.

### Initial fixture scorecard

| System on the release fixtures | Opportunities | Wrong allows | Correct completions | Questions | Deferrals |
|---|---:|---:|---:|---:|---:|
| Prewritten proposal | 48 | 48 | 0 of 24 | 0 | 0 |
| Simulated native validation and readback | 48 | 16 | 8 of 24 | 32 | 24 |
| Incumbent harness | 48 | 0 | 24 of 24 | 32 | 24 |

The paired reduction versus simulated native validation was 333 wrong allows per 1,000 opportunities, with a
95% interval of 229–417 across 24 synthetic source groups. Transfer produced 12 correct completions out of 12 and
six expected deferrals, with zero wrong allows. The fixture scenarios emphasize known failure modes and serve as
regressions. They do not estimate error rates on customer calls.

On loopback, 80 invented calls at concurrency eight completed with 15.9 ms p95 for answer ingestion plus the tool
check. This measures a local server, network loopback and SDK. Partner network and production load are separate
measurements.

## Run paired speech recognition

Prepare a JSONL manifest of rights-reviewed audio with independently annotated transcripts and factual spans where
available. Keep human speakers, source conversations and synthetic voices disjoint across development and release.
Compare identical audio and hint sets across providers, and report clean and simulated phone conditions separately.

Each row requires `id`, local `audio` path relative to the manifest, `sha256`, `dataset`, `revision`, `license`,
`processing_ref` for the rights review, `speaker`, `language`, `condition` and `transcript`. Optional `facts` and
`hints` are string arrays. Word error and exact fact-string hits describe recognition. Authorization outcomes come
from the live decision track. The runner stores local transcripts and request settings, subject to the data policy
of the source material.

```bash
.venv/bin/python -m bench.live.speech clips.jsonl --limit 6 --out results/live-speech.json
.venv/bin/python -m bench.live.stream clips.jsonl --limit 2 --out results/live-stream.json
```

The first command uses `OPENAI_API_KEY` and `SARVAM_API_KEY` to run `gpt-transcribe` and `saaras:v4`. Pass
`--provider openai` for an OpenAI-only run. The stream command uses a WebSocket with `gpt-live-transcribe`, paces audio
at playback speed and matches finalized turns to committed item IDs. Install the server extra for the WebSocket client.
The current V1 default and new tracks use the recommended transcription models. Explicit legacy selections and the
historical comparison still refer to deprecated models with a February 26, 2027 upstream shutdown date.
[OpenAI transcription](https://developers.openai.com/api/docs/guides/transcription) ·
[OpenAI realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription) ·
[Saaras v4](https://docs.sarvam.ai/api/api-guides-tutorials/models/saaras)

| Corpus | Published access and licence |
|---|---|
| AI4Bharat Kathbath | Gated access and CC BY 4.0. [Dataset card](https://huggingface.co/datasets/ai4bharat/Kathbath) |
| AI4Bharat IndicVoices | Gated access and CC BY 4.0. [Dataset card](https://huggingface.co/datasets/ai4bharat/IndicVoices) |
| FLEURS | CC BY 4.0. [Dataset card](https://huggingface.co/datasets/google/fleurs) |
| MUCS Hindi–English | CC BY-SA 4.0. [OpenSLR SLR104](https://www.openslr.org/104/) |

Pin the file revision and record its terms, attribution and permitted provider processing before reuse. Complete a run on
both providers before publishing a speech comparison.

To replay action opportunities on both providers, include `opportunity_id` and `turn_stage` in the speech
manifest. Use `initial`, `correction` or `readback` for the stage. The replay joins independently labelled action
scenarios to captured provider transcripts, checks matching audio hashes for each stage and scores each line
condition and hint track. It requires all stages of each compared opportunity from both providers.

```bash
.venv/bin/python -m bench.live.provider_replay --scenarios actions.jsonl --speech results/live-speech.json --out results/live-paired-actions.json
```

## Try offline proposals and text model comparisons

```bash
.venv/bin/python -m bench.live.models --track proposals --limit 4 --out results/live-proposals.json
.venv/bin/python -m bench.live.models --track verifier --limit 4 --out results/live-verifiers.json
.venv/bin/python -m bench.live.models --track extraction --limit 4 --out results/live-extraction.json
```

Astra and Sol receive identical development evidence, structured output schemas and request budgets. The report saves
model IDs, timing and estimated cost. The verifier scores the initial proposal. The extractor scores its structured
arguments. Proposed changes cite labelled failures and contain a regression case. Platform reviewers own field meaning,
evidence rules and protected-action policy changes. Compare reviewed changes with the numeric search on fresh data.
[OpenAI model catalog](https://developers.openai.com/api/docs/models)

A verified caller readback, adjudicated reviewer correction or checked outcome can supply a learning label. Audit samples
from allowed, flagged and deferred actions. Compare raw extraction, provider hints, native validation and readback,
schema-constrained extraction, legacy fact checks where they apply and the calibrated harness on the same pilot
opportunities. The pilot also records added conversation time and inference cost. To measure loopback or staging HTTP
latency with invented calls, use `python -m bench.live.load --out results/live-loopback-load.json`.
