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

`pehchaan_sdk.wrap(target, *, second=None, llm=None, **context)` wraps an OpenAI-style client or any function that returns a transcript. OpenAI speech clients read meaning with themselves. For any other speech model pass `llm=OpenAI()`; without it the code-only checks run and the transcript goes to no LLM.
Answers keep their shape, with the checked text and `.pehchaan`. Streams and subtitle formats are refused rather than passed
through unchecked. The `pehchaan` command checks one audio file or `--text` transcript.

| Method and path | Request | Response |
|---|---|---|
| POST `/v1/connect` | `X-Demo-Passcode` or `X-OpenAI-Key` | `{ok, kind, key_checked, models:[{id, keywords, evidence}], limits:{per_hour, left_this_hour, max_seconds}}`. Free, and not a live request. 401 bad credential, 403 no usable speech model |
| GET `/api/demo/highlights` | - | The packaged call that best shows each demo: `{context, llm, learning}` |

`language` (for example `hi`, `ta`, `hi-IN`) is accepted by `/v1/audio/transcriptions`, `/v1/verify-audio`,
`/v1/verify-transcript` and the WebSocket `start` message. See docs/LANGUAGES.md. `/v1/bench` also returns `languages`.

## Company data (D-047)

`wrap(..., knowledge=[...])` and `Pehchaan(..., knowledge=[...])` connect company systems. Each runs in the customer's own
process, so its credentials never reach Pehchaan's server. A source is anything with `name` and `fetch(call)`, where `call`
holds `phone`, `customer_id`, `city` and `domain`. It returns a `Knowledge` record or dict with `people`, `companies`,
`places`, `phones`, `amounts`, `pins`, `city` and `as_of`.

| Connector | Use |
|---|---|
| `HttpSource(name, url, fields=..., headers=..., records=...)` | Any REST API. HTTPS only, except localhost. Redirects are refused. |
| `CsvSource(name, file, key=..., fields=...)` | A CSV export. Reloads when the file changes. |
| `FunctionSource(name, function)` | Your own database or client code. |
| `StaticSource(name, table)` | A table in memory, for tests. |
| `load_knowledge("knowledge.yaml")` | Builds these from a file. `${VAR}` reads a secret from the environment. |
| Entry point `pehchaan.knowledge` | A package adds its own connector type. |

Lookups run in parallel inside `knowledge.timeout_ms` (250). A slow or broken source is skipped, and repeated failures rest it.
Records are evidence only: old, malformed, ambiguous, disputed or excess values are dropped and listed in `result.knowledge`.
Each fact gets `backed_by`. Used through the SDK, records never reach Pehchaan's server: only names, places and brands go to the
speech provider as keywords, and candidate names go to the LLM judge. With `private=True`, a source's names reach neither. For
the REST API or stream, send `hub.context_for({"caller": {"number": "..."}})` as the context. That sends the compiled names,
phones, PINs and amounts to Pehchaan's server, except anything from a private source. A call that used company data is labelled
`unmeasured`.

| Method and path | Request | Response |
|---|---|---|
| GET `/api/demo/knowledge` | - | The simulated systems, failures and calls |
| POST `/api/demo/knowledge` | `{call, sources:[ids], fault}` | Facts, backers and source reports. Free, invented records, never a benchmark result. |

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
429 when the server is busy or after too many wrong passcodes. An unedited sample replays packaged answers and never reaches a paid API.

## Public API v1 (live at https://52-24-174-127.sslip.io, interactive docs at `/docs`)

| Method and path | Request | Response |
|---|---|---|
| POST `/v1/audio/transcriptions` | OpenAI multipart (`file`, `model`, ...). Optional `X-Pehchaan-Context` JSON header | OpenAI JSON `text`, plus `pehchaan: {entities, flags, clarifier_prompt, telemetry, raw_text, alt_text}` |
| POST `/v1/verify-audio` | Multipart `audio`, optional `context` (JSON string), `model` | `VerifyResult` |
| POST `/v1/verify-transcript` | JSON `{text, context?, alt_text?, model?}` | `VerifyResult` |
| POST `/v1/memory/confirm` | JSON `{user_id, heard, corrected, entity_type}`, gated | `CorrectionResult`. Memory is scoped to the credential |
| WS `/v1/stream` | See below | `ready`, `phrase`, `fact`, `clarifier`, `final`, `error` |
| GET `/v1/bench`, `/health` | - | Published results; service status with `engine_matches_exam` |

`VerifyResult`: `{verified_text, raw_text, alt_text, entities: [Fact], understood, clarifier_prompt, telemetry}`.
`Fact`: `{type, status, heard, value, reason, source, latency_ms, question, options}`. `status` is FIXED, VERIFIED, HEARD or FLAGGED.
`telemetry.evidence` says what covers this setup: `exam`, `dev` or `unmeasured`. `latency_ms` on a fact is the time of the
engine stage that decided it, not a separate per-fact timer.

**Credentials:** `X-Demo-Passcode`, `X-OpenAI-Key`, or `Authorization: Bearer <passcode or sk-key>`. A caller's own key is
used for that caller's calls only and is never stored. With no credential, `/v1/verify-transcript`, `/v1/memory/confirm` and
`/v1/calls` still work, using rules and sound matching only, so no paid model can run.

**Limits (`ENV=production`):** the number of calls is not limited. Each clip is limited to 30 seconds and 5 MB. Wrong passcodes
are limited to 8 per minute per address. At most 12 runs and 12 streams are active at once, so a busy server answers 429.

**Saved calls (D-049):** a call is saved when its context names a caller (`context.user.id`). Text, facts, timings and the context
are kept. Audio and keys are not. Rows belong to one credential: everyone using the demo passcode shares one space, and everyone
with no credential shares another, so use an unguessable caller id. `GET /v1/calls?caller=` lists a caller's calls and what was
learned. `DELETE /v1/calls/{id}` removes one. `DELETE /v1/calls?caller=` forgets the caller and their lessons.
`POST /v1/calls/{id}/recheck` replays the saved transcript with what that caller taught, with no speech model.
`POST /v1/memory/confirm` takes an optional `call_id`, and the answer must then actually repair that call.

**Stream:** send `{"type":"start","mode":"audio"|"transcript","auth":{"passcode":"..."}|{"openai_key":"..."},"context":{},"model":"..."}`.
Then send 16 kHz mono PCM16 binary frames, or `{"type":"transcript","text":"...","is_final":true,"alt_text":"..."}`. End with
`{"type":"stop"}`. Results arrive per phrase, after a pause, not per word. The
`final` message re-checks the joined transcript. Close codes: 4400, 4401, 4403, 4408, 4413, 4429.

## Noisy-line test (D-057)

`POST /v1/line-test` takes multipart `audio`, `line` (`noisy`, `very_noisy` or `dropouts`), and optional `context`, `model`, `language`. It needs the passcode or your own key and costs two verified calls. It returns `clear`, `noisy`, `clear_alone`, `noisy_alone`, `noisy_audio` (a WAV data URL), `noisy_score` and `facts`. Facts are the ones both systems stated on the clear copy. Audio is not stored and no call is saved.

## Meaning check

With an LLM, one context-blind call reads what each claimed span means and whether the call still relies on it (D-053, D-054). A second short call runs only if the first objects to a computed number. `telemetry.meaning_calls` counts these calls and `telemetry.stages_ms.meaning` is its time. It runs on calls that have facts, and it adds about 0.85 s. `understood` lists words set aside, as `{heard, read_as, meaning, note}`, where `meaning` is `corrected_by_caller`, `only_mentioned`, `other_number`, `everyday_word` or `command_in_speech`. Without a key, or if the call fails, the older word check runs: the caller's words are kept and no lone number word is claimed as money. Decimal and sawa amounts are computed in code on every path (D-052).

Every live route applies the same checks after the engine (`pehchaan_sdk/finish.py`). A call that ran the meaning layer reports `evidence: unmeasured`, because the exam did not include it. `POST /api/demo/compare` with custom text or audio is the exception: it replays the frozen benchmark systems for comparison, and the site only sends it packaged samples.
