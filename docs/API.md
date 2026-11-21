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
common_word, person_not_place, second_opinion, known_name_heard). Useful to explain why a fix did NOT happen.
`Entity`: `{etype, surface, start_tok, end_tok, value, display, status, source, reason, distance, asr_confidence,
candidates:[{text, source, distance?}], clarifier, heard_value, admission}`. status is FIXED | CONFIRMED | KEPT | FLAGGED.
`heard_value`: for PHONE / PIN / AMOUNT, the value read from the transcript before any proposal (null otherwise).
`admission`: "admitted", or the gate rule that changed this proposal. FIXED now only appears for names, places and
brands; a number is never FIXED. The UI must not say "learned" when memory refuses.

## One-line SDK and connect

`pehchaan_sdk.wrap(target, *, second=None, **context)` wraps an OpenAI-style client or any function that returns a transcript.
Answers keep their shape, with the checked text and `.pehchaan`. Streams and subtitle formats are refused rather than passed
through unchecked. The `pehchaan` command checks one audio file or `--text` transcript.

| Method and path | Request | Response |
|---|---|---|
| POST `/v1/connect` | `X-Demo-Passcode` or `X-OpenAI-Key` | `{ok, kind, key_checked, models:[{id, keywords, evidence}], limits:{per_hour, left_this_hour, max_seconds}}`. Free, and not a live request. 401 bad credential, 403 no usable speech model |
| GET `/api/demo/highlights` | - | The packaged call that best shows each demo: `{context, llm, learning}` |

`language` (for example `hi`, `ta`, `hi-IN`) is accepted by `/v1/audio/transcriptions`, `/v1/verify-audio`,
`/v1/verify-transcript` and the WebSocket `start` message. See docs/LANGUAGES.md. `/v1/bench` also returns `languages`.

## Live demo

| Method and path | Request | Response |
|---|---|---|
| GET `/api/demo/presets` | - | Array of preset records with `id`, `label`, `voice_source`, `audio_url`, `description`, `initial_level`, `context` and `context_adv` |
| GET `/api/demo/presets/{id}/audio` | - | Allowlisted demo audio |
| GET `/api/demo/presets/{id}/models` | - | Packaged answers per speech model: `{model: {keywords_used, second_opinion_model, base, main}}`. Free |
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

Reads `GET /v1/bench`: both locked exam lines, the paired counts, the line-quality check, the four-model comparison and the
model profiles. Reports with `simulated: true` are excluded. `asr_ms_*` summarize the longest participating ASR request per
clip. `harness_ms_*` summarize post-ASR processing.

## Learning verdict (D-029)

`{event_id, heard, canonical, etype, adopted, checks:[{name, passed, detail}], clips_replayed, clips_changed, facts_helped,
facts_harmed, new_damage, ms}`. `adopted: false` is a normal HTTP 200 outcome and means nothing was learned. Checks:
`learnable_type`, `not_everyday_word`, `sounds_alike`, `no_conflict`, `repairs_this_call`, `no_regression`.

## Access (D-030)

The server is public-locked unless `PEHCHAAN_MODE=local`. In public mode the routes `/record`, `/studio`, `/api/scripts`,
`/api/record`, `/api/studio/*` and `/api/memory/*` return 404. A request that can reach a paid model (live audio, typed
text, or a sample with edited context) needs the `X-Demo-Passcode` header: 401 wrong passcode, 403 live audio turned off,
429 over the rate or daily limit. An unedited sample replays packaged answers and never reaches a paid API.

## Public API v1 (live at https://52-24-174-127.sslip.io, interactive docs at `/docs`)

| Method and path | Request | Response |
|---|---|---|
| POST `/v1/audio/transcriptions` | OpenAI multipart (`file`, `model`, ...). Optional `X-Pehchaan-Context` JSON header | OpenAI JSON `text`, plus `pehchaan: {entities, flags, clarifier_prompt, telemetry, raw_text, alt_text}` |
| POST `/v1/verify-audio` | Multipart `audio`, optional `context` (JSON string), `model` | `VerifyResult` |
| POST `/v1/verify-transcript` | JSON `{text, context?, alt_text?, model?}` | `VerifyResult` |
| POST `/v1/memory/confirm` | JSON `{user_id, heard, corrected, entity_type}`, gated | `CorrectionResult`. Memory is scoped to the credential |
| WS `/v1/stream` | See below | `ready`, `phrase`, `fact`, `clarifier`, `final`, `error` |
| GET `/v1/bench`, `/health` | - | Published results; service status with `engine_matches_exam` |

`VerifyResult`: `{verified_text, raw_text, alt_text, entities: [Fact], clarifier_prompt, telemetry}`.
`Fact`: `{type, status, heard, value, reason, source, latency_ms, question, options}`. `status` is FIXED, VERIFIED, HEARD or FLAGGED.
`telemetry.evidence` says what covers this setup: `exam`, `dev` or `unmeasured`. `latency_ms` on a fact is the time of the
engine stage that decided it, not a separate per-fact timer.

**Credentials:** `X-Demo-Passcode`, `X-OpenAI-Key`, or `Authorization: Bearer <passcode or sk-key>`. A caller's own key is
used for that caller's calls only, is never stored, and has its own daily bucket.

**Limits (`ENV=production`):** 15 live requests per IP per hour, 150 per day, 30 seconds and 5 MB per clip.

**Stream:** send `{"type":"start","mode":"audio"|"transcript","auth":{"passcode":"..."}|{"openai_key":"..."},"context":{},"model":"..."}`.
Then send 16 kHz mono PCM16 binary frames, or `{"type":"transcript","text":"...","is_final":true,"alt_text":"..."}`. End with
`{"type":"stop"}`. Results arrive per phrase, after a pause, not per word. Each audio phrase counts as one live request. The
`final` message re-checks the joined transcript. Close codes: 4400, 4401, 4403, 4408, 4413, 4429.
