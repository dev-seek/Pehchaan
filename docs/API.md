# API contract (app/server.py). The UI and any client depend on this; change it only with a DECISIONS entry.

| method | path | body | returns |
|---|---|---|---|
| GET | `/api/health` | - | `{ok, models}` |
| GET | `/api/demo/contexts` | - | `{name: contextDict}` from `data/demo/contexts/*.json` |
| POST | `/api/process` | multipart: `audio` (file, optional) OR `text`; `context` (JSON string); `level` C0-C4; `user_id` | `{baseline:{text,model,latency_ms}|null, asr:{text,model,latency_ms}, pehchaan: Result, level}`. With audio, `asr` is the keyword transcript (the input) and `baseline` is the plain transcript (also the second opinion). With `text`, `baseline` is null. |
| GET | `/api/config` | - | `{mode, live_needs_passcode, live_available, studio}` for the website |
| GET | `/api/learning/proof` | - | held-out learning results from `data/published/learning_dev.json` |
| POST | `/api/memory/confirm` | JSON `{user_id, heard, canonical, etype}` | the learning **verdict** (below); laptop only. **HTTP 400** if `etype` is PHONE, PIN or AMOUNT (numbers are read-only, D-021) or unknown |
| GET | `/api/memory/{user_id}` | - | list of memory entries |
| DELETE | `/api/memory/{user_id}` | - | `{reset:true}` |
| GET | `/api/scripts?split=test` | - | scripts to record `[{script_id, lang, domain, spoken, recorded}]` |
| POST | `/api/record` | multipart `script_id`, `split`, `audio` | `{saved, bytes}` |
| GET | `/api/bench/available` | - | e.g. `["dev", "test_real", "dev_SIM"]` |
| GET | `/api/bench/latest?clips=dev` | - | summary JSON written by `bench.run` |

`POST /v1/pehchaan/transcribe` is an alias of `POST /api/process` with the same multipart and response contract.
Both are available in the interactive documentation at `/docs`.

`Result` (pehchaan): `{text_in, text_out, level, language:{dominant, label, shares}, entities:[Entity],
questions:[{entity, etype, question}], timings_ms:{prepare, numbers, memory, names, total}, llm_calls, refused:[Refused]}`
`Refused`: a proposal the admission gate stopped, with the rule that stopped it (critical_read_only, acronym_spelled,
common_word, person_not_place, second_opinion). Useful to explain why a fix did NOT happen.
`Entity`: `{etype, surface, start_tok, end_tok, value, display, status, source, reason, distance, asr_confidence,
candidates:[{text, source, distance?}], clarifier, heard_value, admission}`. status is FIXED | CONFIRMED | KEPT | FLAGGED.
`heard_value`: for PHONE / PIN / AMOUNT, the value read from the transcript before any proposal (null otherwise).
`admission`: "admitted", or the gate rule that changed this proposal. FIXED now only appears for names, places and
brands; a number is never FIXED. The UI must not say "learned" when memory refuses.

## Live demo

| Method and path | Request | Response |
|---|---|---|
| GET `/api/demo/presets` | - | Array of preset records with `id`, `label`, `voice_source`, `audio_url`, `description`, `initial_level`, `context` and `context_adv` |
| GET `/api/demo/presets/{id}/audio` | - | Allowlisted demo audio |
| POST `/api/demo/compare` | Multipart with one of `audio`, `preset` (ID), or `text`. Optional `context` and `context_adv` are JSON objects | Newline-delimited events with per-system results |
| POST `/api/demo/{run_id}/confirm` | JSON `{system_id, entity_id, canonical}` | the learning **verdict** for a flagged PERSON, ORG or PLACE in this session |
| POST `/api/demo/{run_id}/replay` | JSON `{system_id}` | Demo result with `replay_ms` and `memory_hits` |
| GET `/api/demo/learning` | - | This session's ledger, newest first: `{event_id, at, decision, heard, canonical, etype, active, checks, ...}` |
| POST `/api/demo/learning/{event_id}/rollback` | - | Undoes an adopted correction: `{event_id, undoes, heard, canonical}` |

Omitted context fields use the corresponding preset hints or empty objects for a live call. Empty objects
explicitly clear the corresponding hints. A context can contain `contacts`, `caller`, `sms`, `places`,
`user.city` and `domain`. The server supplies the session ID.

| Event | Fields |
|---|---|
| `started` | `run_id`, `main_system`, `systems` (each has `id`, `kind`, optional `level`), `mode` (audio, text, or preset), optional `preset` |
| `result` | `system_id`, `result` |
| `system_error` | `system_id`, `message` |
| `done` | `run_id` |

Each line is independent JSON with an `event` key. Read until `done` and keep earlier results if another system fails.
The demo result includes `text`, `text_in`, `entities`, `questions`, `timings_ms`, `asr`, `llm_calls`, `verifier_cache_hits`
and `memory_hits`. Entities have a run-and-system scoped `id`, output `start` and `end`, and `input_start` and `input_end`.
Offsets are half-open Unicode code-point ranges. Questions have `entity_id`, `question` and `choices`. Plain ASR and
rewrite cards annotate numbers and exact known name matches in the literal output. Other names may appear in that text
without a typed card entry. `scored` appears for labelled presets and gives independent per-fact outcomes for that clip.
Benchmark Lab is the source for accuracy and confidence intervals across clips.

`asr` lists model time, role and cache status per participating transcript. `timings_ms` contains processing stage
totals after ASR. `llm_calls` counts verifier API requests made by that result, with cached decisions counted separately.
Rewrite results expose `rewrite_calls` and `rewrite_cached`. Replay keeps the exact original speech-to-text inputs and
skips the verifier. Its `replay_ms` is server wall time for the replay, including worker wait.

The browser keeps the HTTP-only `pehchaan_demo_session` cookie. Confirm and replay require the matching session and
return 404 for expired or unavailable runs. Replay state is held in process memory for up to 15 minutes. Live audio
files are temporary and private-comparison model results bypass the benchmark disk cache. Default preset results can
use the benchmark cache. SQLite stores explicit name or place confirmations by session. Numbers remain review-only.

## Benchmark Lab

Reads `/api/bench/latest?clips=test_real_phone` first and falls back to `clips=dev` with a final-test-pending label.
Reports with `simulated: true` are excluded. New harness reports include `asr_ms_p50` and `asr_ms_p95` per system.
These summarize the longest participating ASR request per clip because the requests run in parallel. They exclude
worker queue wait, browser transfer, scoring and Pehchaan processing. The separate `harness_ms_p50` and
`harness_ms_p95` summarize post-ASR processing.

## Learning verdict (D-029)

`{event_id, heard, canonical, etype, adopted, checks:[{name, passed, detail}], clips_replayed, clips_changed, facts_helped,
facts_harmed, new_damage, ms}`. `adopted: false` is a normal HTTP 200 outcome and means nothing was learned. Checks:
`learnable_type`, `not_everyday_word`, `sounds_alike`, `no_conflict`, `repairs_this_call`, `no_regression`.

## Access (D-030)

The server is public-locked unless `PEHCHAAN_MODE=local`. In public mode the routes `/record`, `/studio`, `/api/scripts`,
`/api/record`, `/api/studio/*` and `/api/memory/*` return 404. A request that can reach a paid model (live audio, typed
text, or a sample with edited context) needs the `X-Demo-Passcode` header: 401 wrong passcode, 403 live audio turned off,
429 over the rate or daily limit. An unedited sample replays packaged answers and never reaches a paid API.
