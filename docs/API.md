# API contract (app/server.py). The UI and any client depend on this; change it only with a DECISIONS entry.

| method | path | body | returns |
|---|---|---|---|
| GET | `/api/health` | - | `{ok, models}` |
| GET | `/api/demo/contexts` | - | `{name: contextDict}` from `data/demo/contexts/*.json` |
| POST | `/api/process` | multipart: `audio` (file, optional) OR `text`; `context` (JSON string); `level` C0-C4; `user_id` | `{baseline:{text,model,latency_ms}|null, asr:{text,model,latency_ms}, pehchaan: Result, level}`. With audio, `asr` is the keyword transcript (the input) and `baseline` is the plain transcript (also the second opinion). With `text`, `baseline` is null. |
| POST | `/api/memory/confirm` | JSON `{user_id, heard, canonical, etype}` | stored memory entry. **HTTP 400** if `etype` is PHONE, PIN or AMOUNT (numbers are read-only, D-021) or unknown |
| GET | `/api/memory/{user_id}` | - | list of memory entries |
| DELETE | `/api/memory/{user_id}` | - | `{reset:true}` |
| GET | `/api/scripts?split=test` | - | scripts to record `[{script_id, lang, domain, spoken, recorded}]` |
| POST | `/api/record` | multipart `script_id`, `split`, `audio` | `{saved, bytes}` |
| GET | `/api/bench/available` | - | e.g. `["dev", "test_real", "dev_SIM"]` |
| GET | `/api/bench/latest?clips=dev` | - | summary JSON written by `bench.run` |

`Result` (pehchaan): `{text_in, text_out, level, language:{dominant, label, shares}, entities:[Entity],
questions:[{entity, etype, question}], timings_ms:{prepare, numbers, memory, names, total}, llm_calls, refused:[Refused]}`
`Refused`: a proposal the admission gate stopped, with the rule that stopped it (critical_read_only, acronym_spelled,
common_word, person_not_place, second_opinion). Useful to explain why a fix did NOT happen.
`Entity`: `{etype, surface, start_tok, end_tok, value, display, status, source, reason, distance, asr_confidence,
candidates:[{text, source, distance?}], clarifier, heard_value, admission}`. status is FIXED | CONFIRMED | KEPT | FLAGGED.
`heard_value`: for PHONE / PIN / AMOUNT, the value read from the transcript before any proposal (null otherwise).
`admission`: "admitted", or the gate rule that changed this proposal. FIXED now only appears for names, places and
brands; a number is never FIXED. The UI must not say "learned" when memory refuses.
