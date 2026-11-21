# API contract (app/server.py). The UI and any client depend on this; change it only with a DECISIONS entry.

| method | path | body | returns |
|---|---|---|---|
| GET | `/api/health` | - | `{ok, models}` |
| GET | `/api/demo/contexts` | - | `{name: contextDict}` from `data/demo/contexts/*.json` |
| POST | `/api/process` | multipart: `audio` (file, optional) OR `text`; `context` (JSON string); `level` C0-C4; `user_id` | `{baseline:{text,model,latency_ms}|null, asr:{text,model,latency_ms}, pehchaan: Result, level}` |
| POST | `/api/memory/confirm` | JSON `{user_id, heard, canonical, etype}` | stored memory entry |
| GET | `/api/memory/{user_id}` | - | list of memory entries |
| DELETE | `/api/memory/{user_id}` | - | `{reset:true}` |
| GET | `/api/scripts?split=test` | - | scripts to record `[{script_id, lang, domain, spoken, recorded}]` |
| POST | `/api/record` | multipart `script_id`, `split`, `audio` | `{saved, bytes}` |
| GET | `/api/bench/available` | - | e.g. `["dev", "test_real", "dev_SIM"]` |
| GET | `/api/bench/latest?clips=dev` | - | summary JSON written by `bench.run` |

`Result` (pehchaan): `{text_in, text_out, level, language:{dominant, label, shares}, entities:[Entity],
questions:[{entity, etype, question}], timings_ms:{prepare, numbers, memory, names, total}, llm_calls}`
`Entity`: `{etype, surface, start_tok, end_tok, value, display, status, source, reason, distance, asr_confidence,
candidates:[{text, source, distance?}], clarifier}`. status is FIXED | CONFIRMED | KEPT | FLAGGED.
