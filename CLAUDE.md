# CLAUDE.md: set up, run and review Pehchaan, then how to work on it

**Live site:** https://52-24-174-127.sslip.io
**Source:** https://github.com/dev-seek/Pehchaan
**Demo video:** `VIDEO.md`. **Slides:** `PRESENTATION.pdf`. **Honest note on what is built, reused and simulated:** `SUBMISSION.md`.

**Pehchaan** is a checking layer that sits after any speech-to-text model on Indian phone calls. It checks the facts in
the transcript (names, places, phone numbers, PIN codes, money). Each fact is either right, or the system asks one short
question. It never changes money, a phone number or a PIN by itself.

# Part 1: Run and review the product

You can review it in two ways. The live site needs no setup. The local run below needs no API key.

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.10 or newer (built and tested on 3.12) | server and engine |
| make | any | the commands below |
| ffmpeg | any recent version (tested on 9.0) | checks uploaded audio, adds the phone-line effect |
| Chrome, Edge or Firefox | recent | the web app; the mic needs `localhost` or HTTPS |

No database server, Node, Docker, build step or background worker is needed. SQLite files are created automatically.

```bash
# Ubuntu or Debian
sudo apt-get update && sudo apt-get install -y python3 python3-venv make ffmpeg
# macOS
brew install python@3.12 ffmpeg
```

## Install, check and start (about 2 minutes, no keys)

```bash
make setup     # creates .venv and installs everything
make check     # lint, 619 tests and repo checks. Expect: "repo check: all invariants hold"
make demo      # starts the whole product on http://localhost:8000
```

- There is one process: the API, the WebSocket and the web app are all served on port 8000.
- There is nothing to seed. Sample calls, results and demo data ship in `data/demo` and `data/published`.
- Use another port with `make demo PORT=8010`. Reach it from another machine with `make demo HOST=0.0.0.0`.
- Check it is up: `curl http://localhost:8000/health` returns `"status":"ok"` and `"engine_matches_exam":true`.

## Environment variables

Nothing is required. To use real speech, run `cp .env.example .env` and set `OPENAI_API_KEY`.

| Variable | Needed? | What it does |
|---|---|---|
| `OPENAI_API_KEY` | Optional | Real speech, the meaning check and the LLM judge. Without it, speech is mocked |
| `DEMO_PASSCODE` | Optional | Passcode for live routes. `make demo` uses `review-demo` |
| `PEHCHAAN_MOCK_SPEECH` | Set by `make demo` | `1` uses the labelled mock when no key is set. Ignored in production |
| `PEHCHAAN_MODE` | Set by `make demo` | `public` is what visitors get. `local` adds developer tools |
| `ENV` | Production only | `production` is set on the real server and turns the mock off |
| `SARVAM_API_KEY`, `DEEPGRAM_API_KEY` | Optional | Synthetic dev audio and the Deepgram example only |

**Mock mode.** With no key, speech returns one fixed, invented line and the screen says so. Everything after speech is
the real engine. The noisy-line test needs real speech, so in mock mode it says that and stops.

## Test logins

| User | How to log in | What they can do |
|---|---|---|
| Visitor | No login | Every sample demo, pasted transcripts, Benchmark Lab, Integrate |
| Reviewer, local | Passcode `review-demo` under **Your voice > Connect** | Mic and file upload with mock speech, saved calls, teaching |
| Reviewer, live site | Passcode in `REVIEWER_ACCESS.md`, if the zip includes it | Real speech on the live site, including the noisy-line test |
| Developer with a key | Paste an OpenAI key under **Connect** | Real speech on your own key. The key is not stored |
| API client | Header `X-Demo-Passcode` or `X-OpenAI-Key` | Every `/v1` route |

## Journeys to try

Open http://localhost:8000 (or the live site) and go to **Live Playground**.

1. **See the difference on a real call (no login).** On **Compare**, choose **Courier at the door**, then the **Very
   noisy** line. The same call appears with and without Pehchaan, and a line says what Pehchaan caught.
2. **Check a transcript (no login).** Open **Your voice > Paste text**, press **Use an example**, then **Check
   transcript**. Expect: `Ravi Kumaar` becomes **Ravi Kumar**. The number `9848012346` is **not changed**, and it asks
   `Number ek baar confirm kar dijiye, 98480 12345?`. `Thadugodi` is flagged with `Kadugodi` as an option.
3. **Teach it once.** On that result, choose **Kadugodi** and confirm. It tests the answer on 60 labelled calls, then
   says **Learned**. Press **Check this call again**: the place is now Kadugodi. Press **New caller** and run the
   example again: it still asks, because learning is per caller.
4. **Speak.** Under **Connect**, enter the passcode. Press **Give me a line to read**, **Start speaking**, then
   **Stop**. With a key you see your own words. In mock mode you see the fixed line, labelled as mock.
5. **Prove it on a noisy line (real speech).** After a recording, pick **Dropouts** and press **Add noise and run
   both**. Play both copies and read the fact table. The noise is random, and the screen says so when there was nothing
   to catch.
6. **Explore the other demos (no login).** **Meaning** reads what a caller meant, for example Koti the person against
   one crore. **Context** adds knowledge step by step. **Company data** connects simulated company systems. **vs LLM**
   compares a simple "fix this transcript" LLM. **Learning** shows a question that stops being asked.
7. **See the evidence.** **Benchmark Lab** has the locked exam, line-quality curve, models and languages.
8. **Integrate.** The **Integrate** page has the one-line setup. From this folder:

```bash
# Check a transcript. No key needed.
curl -s http://localhost:8000/v1/verify-transcript -H 'content-type: application/json' -d '{"text":"Main Ravi Kumaar bol raha hoon, mera number 9848012346 hai","context":{"contacts":[{"name":"Ravi Kumar","number":"9848012345"}]}}'

# Send audio. A wrong or missing passcode gets 401.
curl -s http://localhost:8000/v1/verify-audio -H 'X-Demo-Passcode: review-demo' -F audio=@"$(ls data/demo/audio/*.wav | head -1)"

# The installed command line tool
.venv/bin/python -m pehchaan_sdk.cli --text "Main Ravi Kumaar bol raha hoon" --contact "Ravi Kumar"
```

API reference: http://localhost:8000/docs and `docs/API.md`.

## What is simulated, mocked or not finished

- **Simulated:** the phone line in tests and demos (real voice, software line effect), all Telugu and development
  audio, the Company data systems and customers, misleading-context tests, and learning-proof confirmations.
- **Mocked:** speech, only when no key is set.
- **Limits of the evidence:** the locked exam is 30 clips from one speaker. It measured the core engine, before the
  money fix and meaning layer were added. External speech providers are supported but not benchmarked.
- **Not finished:** real telephony, real customer systems, automatic threshold tuning per customer, and testing on
  Safari and real phones.

## How it gets better over time

Decision thresholds live in `config/settings.yaml`, not in code. Today, an answer from a caller is learned only after it
passes a replay on 60 labelled calls, and `make gate` blocks a release that does worse than the adopted baseline. The next
step is to use each answered question as a label and tune thresholds per customer through the same replay gate. That
tuning is planned and is not built yet.

---

# Part 2: Working on the code (skip this when reviewing)

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
