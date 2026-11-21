# ENGINEERING: how code is written in this repo (binding for every human and agent)

The goal is a codebase that any Claude Code or Codex session can open cold and extend safely in minutes.
`make check` enforces the mechanical parts; this file explains the rest.

## 1. Structure: one folder = one concern
| folder | owns | must NOT contain |
|---|---|---|
| `pehchaan/text/` | scripts, transliteration, normalisation, tokens | any language-specific word list |
| `pehchaan/languages/` | language packs, merged registry, language routing | entity decisions |
| `pehchaan/sound/` | fingerprints, sound distance | knowledge of contacts/brands |
| `pehchaan/numbers/` | reading spoken numbers; pure validity/repair rules | context lookups |
| `pehchaan/context/` | what the phone knows (per call + global lexicons) | matching logic |
| `pehchaan/asr/`, `judge/`, `openai_client.py` | everything that talks to OpenAI | business rules |
| `pehchaan/resolvers/` | decisions: numbers, memory, names | I/O except via injected interfaces |
| `pehchaan/output/` | rewritten text, clarifying questions | decisions |
| `bench/` | data generation, running, scoring, reports | engine logic (import it instead) |
| `app/` | HTTP API + static UI | engine logic |
| `data/` | ALL knowledge: languages, lexicons, templates, scripts | code |
| `config/settings.yaml` | ALL tunable numbers and model names | data lists |

## 2. Principles, applied here (not as theory)
- **Single responsibility (SRP):** one module = one job, one resolver = one kind of fact. If a docstring needs "and"
  to describe a module, split it. Size limit: 300 lines per module (checked); aim for functions under ~40 lines.
- **Open/closed (OCP):** extend by adding, not by editing:
  - new language: add `data/languages/<code>.yaml`, list it in `settings.yaml languages.active`. No code change.
  - new brand/locality: edit `data/lexicons/*.yaml`. No code change.
  - new fact type (e.g. DATE, OTP): add a rule to `NumberResolver._rules` or a new resolver in `pipeline.build_pipeline`.
- **Liskov / interfaces (LSP, ISP):** every resolver satisfies `resolvers.base.Resolver`; any judge satisfies
  `judge.Judge`; any memory satisfies `resolvers.memory.MemoryStore`. Small interfaces, one method each where possible.
- **Dependency inversion (DIP):** the pipeline receives its judge, memory store and registry (`build_pipeline(...)`).
  Tests inject `FakeJudge` / temp memory; production injects `OpenAIJudge` / `JsonMemoryStore`.
- **DRY:** one source of truth per fact. Number words live only in language packs (the speech generator reads
  them too); thresholds only in settings; the scorer reuses the engine's number reader.
- **KISS / YAGNI:** pure Python, no frameworks beyond FastAPI, no databases until a JSON file is not enough, no
  abstraction without a second real user. Do not add languages, layers or dependencies "for later".
- **Composition over inheritance:** the pipeline is a list of resolvers; there are no class hierarchies.
- **Fail fast:** malformed packs, conflicting number words, unknown context levels, unknown entity types and bad
  API input raise immediately with a precise message. Never swallow an error silently; the ONE deliberate
  exception is a judge/API outage during a call, which falls back to FLAG (a call must never crash).

## 3. Naming
Modules and functions say what they do: `find_runs`, `stutter_repairs`, `build_utterance`, `decode_spelled_acronym`.
No abbreviations except domain ones (ASR, PIN, INR). Booleans read as questions (`is_mobile`, `is_everyday`).
Every package `__init__.py` starts with a docstring explaining the package (checked).

## 4. Testing (the agent's verification loop)
- Tests mirror packages: `test_text.py`, `test_languages.py`, `test_sound.py`, `test_numbers.py`, `test_pipeline.py`,
  `test_bench.py`, `test_app.py`. They never call OpenAI (fakes in `tests/conftest.py`).
- **Bug fix = failing test first**, then the fix. A behaviour change without a test is not done.
- Real ASR outputs we observed become regression tests (see `GPT_TRANSCRIBE_OUTPUT` in test_pipeline.py).
- `make check` = ruff lint + all tests + `tools/check_repo.py` invariants. Must be green before every commit.

## 5. Rules for AI coding agents (Claude Code, Codex, any account)
1. **One task per session**, from `docs/00_START_HERE.md`. Do not rewrite unrelated files.
2. **Interface first:** if a change crosses folders, state the function signature / API shape in your plan first;
   API changes also update `docs/API.md`.
3. **No speculative work:** no new libraries, abstractions or refactors outside the task. A new dependency
   needs a DECISIONS entry.
4. **No clip-specific hacks** (see CLAUDE.md hard rules). Generalise, then test.
5. **Leave the repo better documented than you found it:** update START_HERE, LOG, DECISIONS before stopping.
6. Run `make check` before committing; commit small with a "what + why" message.
