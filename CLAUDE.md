# CLAUDE.md: instructions for any coding agent working on Pehchaan

You are joining a 28-hour solo hackathon build (BUILDERS '26, OpenAI x Equal AI, Hyderabad). Several Claude Code
and Codex accounts take turns on this repo. **The repo is the memory.** Nothing important may live only in chat.

## Read first, in this order (5 minutes)
1. `docs/00_START_HERE.md`: what works now, what is unverified, and **the next task**
2. `docs/ENGINEERING.md`: how code is written here (structure, principles, testing, agent rules): **binding**
3. `docs/PLAN.md`: phases, task list with acceptance tests, timeline to the Sunday 14:00 code freeze
4. `docs/ARCHITECTURE.md`: how the engine works (simple + technical), including language routing
5. `docs/EVAL.md`: how we measure; the honesty rules
6. `docs/DECISIONS.md`: why things are the way they are (do not silently undo a decision)
Also: `docs/GLOSSARY.md` (plain-English terms), `docs/API.md`, `docs/PITCH.md`, `docs/LOG.md`.

## The human
The builder is new to speech AI. Explain what you did in plain words, like to a smart 16-20 year old who knows LLMs.
Before a big or irreversible change, say what and why in two lines first. The builder speaks Hindi, Hinglish
and English (not Telugu): real-voice recordings exist only for those.

## Hard rules
1. **No hardcoding for a specific clip.** Never special-case a name/number seen in a test or dev clip. Fix the
   general cause (rule, language pack, lexicon, threshold in `config/settings.yaml`) and add a test in `tests/`.
2. **Never tune on the test set.** `data/bench/test_scripts.jsonl` is locked by `test_scripts.sha256`.
   Tune on `dev` only. Run `test_real` once at the end (Sunday morning) and log the run in `docs/LOG.md`.
3. **Knowledge lives in data, numbers live in config.** Language words: `data/languages/*.yaml`. Brands/places:
   `data/lexicons/`. Thresholds, costs, model names: `config/settings.yaml`. Code holds logic only.
4. **Simulated results are never reported as results** (`--simulate` exists only to test plumbing).
5. **Money and phone numbers are never changed automatically.** Context and memory never touch PHONE, PIN or AMOUNT; a suspected error becomes a FLAG (DECISIONS D-021).
6. Keep the engine fast: the LLM judge only for ambiguous cases. Report latency.
7. Follow `docs/ENGINEERING.md`. `make check` must be green before every commit.

## Commands
```bash
make setup         # venv + runtime and dev dependencies
make check         # lint + tests + repo invariants  <- before every commit
make check-api     # verify model names/logprobs on this key (tools/check_openai.py)
make bench-sim     # offline plumbing run of the benchmark (no API)
make gen           # regenerate scripts (refuses to change the locked test set)
make audio-dev     # TTS + phone-line effect for dev clips
make bench-dev     # real benchmark on dev clips (uses API; cached)
make gate          # regression gate: latest dev run vs the adopted baseline
make adopt NOTE="why"  # make a passing run the new baseline (deliberate, human step)
make serve         # http://localhost:8000 demo, /record to record the real test set
```

## Session protocol (every agent, every time)
- Start: `git pull`, read `docs/00_START_HERE.md`, run `make check`.
- Work on ONE task from the plan. Small commits: `git add -A && git commit -m "<what> <why>"`.
- After any engine change: `make check`, `make bench-sim` (and `make bench-dev` if the API is available, then
  `make gate`); read the report and the failures in `results/*/per_clip.jsonl`.
- **Before you stop (or when your context gets long):** update `docs/00_START_HERE.md` (status + next task),
  append a dated entry to `docs/LOG.md`, add new decisions to `docs/DECISIONS.md`, commit, push.
- Parallel accounts: only one agent edits `pehchaan/` + `bench/` at a time. UI work happens in `app/static/`
  against `docs/API.md`, so two agents can work at once without conflicts.
