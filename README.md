# Pehchaan: every fact in an Indian call, right or flagged

Speech-to-text gets the *words* of Indian phone calls mostly right and the *facts* wrong: "Venkat row" for
Venkateswara Rao, "Konda poor" for Kondapur, ₹40,500 for ₹14,500, an 11-digit phone number.
Pehchaan is a model-agnostic layer after any ASR. It uses what the phone already knows (contacts, caller ID,
SMS, city) and India-specific sound and number rules to **FIX**, **CONFIRM** or **FLAG** every fact, asks one
short question when unsure, and learns from every confirmation.

BUILDERS '26 (OpenAI x Equal AI) · Track 2: Voice AI for India.

## Results
Filled from `results/latest_test_real.json` (locked human-voice test set). See `docs/EVAL.md` for the method.

## Languages
Multilingual by design: all language knowledge is in `data/languages/*.yaml` (Hindi, English, Telugu today), merged
so code-mixed speech works. Sound matching covers 9 Indian scripts. Headline results: Hindi, Hinglish, English.

## Run it
```bash
make setup            # python venv + dependencies (pure Python; ffmpeg needed for audio tools)
cp .env.example .env  # add OPENAI_API_KEY (and optionally SARVAM_API_KEY)
make check            # lint + tests + repo invariants
make serve            # demo: http://localhost:8000   recorder: http://localhost:8000/record
make bench-dev        # benchmark on dev clips (after: make gen && make audio-dev)
```

## Repo map
`pehchaan/` engine (text, languages, sound, numbers, context, asr, judge, resolvers, output) · `bench/` benchmark ·
`tools/` API check, audio maker, repo checker · `app/` server + UI · `config/` all settings · `data/` languages,
lexicons, templates, scripts · `docs/` start-here, engineering, plan, architecture, eval, decisions, pitch.
