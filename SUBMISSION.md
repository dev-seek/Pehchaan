# Pehchaan: submission note

Pehchaan is a checking layer for Indian speech-to-text. It checks names, places, phone numbers, PIN codes and money, then fixes,
confirms or asks. It never changes money, a PIN or a phone number by itself.

## 1. Working demo on fresh input

**https://52-24-174-127.sslip.io**

- **No key needed:** open **Your voice**, choose **Use an example** or paste any transcript, and choose **Check transcript**.
  Rules and sound matching run on your text with no paid model.
- **Your own audio:** connect your OpenAI key, or the demo passcode given with this submission, then speak or upload a clip.
- **Learning on fresh input:** answer a flagged name, then choose **Check this call again**. The fix applies to that caller only.
- **Sample calls:** Compare, Context, Company data, vs LLM and Learning all work with no key.

## 2. Source code

**https://github.com/dev-seek/Pehchaan**. The README covers setup, the API and how it works. `make check` runs the tests and repo checks.

## 3. Evidence of results

**Baseline comparison.** A locked test of 30 real-voice clips: one speaker, a simulated phone line, 82 labelled facts, run once per
line on frozen code. A silent error is a wrong fact with no warning.

| Phone line | Speech alone | With keywords | With Pehchaan | Money, phone and PIN silent errors, keywords to Pehchaan |
|---|---|---|---|---|
| Standard | 36 | 21 | **13** | 8 to 3 |
| Noisy | 53 | 37 | **26** | 17 to 8 |

- Keywords are an OpenAI feature and give the large accuracy gain. Pehchaan's gain is fewer silent errors.
- Correct facts barely change: 61 to 62 on the standard line, 45 to 45 on the noisy line. Pehchaan mostly asks.
- 16% of facts on the standard line are still silently wrong, and only half of Pehchaan's questions caught a real error.
- With deliberately misleading hints, the drop in silent errors is 24-27%.
- The 95% ranges for keywords and Pehchaan overlap when compared separately. The same-clip comparison is above zero, but it was
  chosen after seeing the results.
- The exam speaker also recorded the six check clips, and one safety rule (D-033) was shaped by that voice's errors. No exam clip
  was seen while building it.
- Raw results: `data/published/` and `GET /v1/bench`.

**Outputs on new data.** The demo accepts any new transcript or recording.

**Data persists.** A call that names a caller is saved as text with its facts. Saved calls and lessons survive a server restart and
a new release, and can be deleted.

## 4. Honest note

**Built for this hackathon:** the verification engine, sound matching across scripts, Indian number reading, the safety gate, the
learning checks, the benchmark and independent scorer, the SDK, the API, the connectors and the website. I directed the work and
made the product and evaluation decisions. AI coding agents (Claude Code and Codex) wrote much of the code.

**Reused:** OpenAI speech models, `gpt-4.1-mini` and text-to-speech; FastAPI, Uvicorn, Pydantic, PyYAML,
RapidFuzz, jiwer, indic-transliteration and ffmpeg; Caddy, AWS and sslip.io; Noto fonts.

**Simulated:**

- The phone line. The voice is real, and the line effect is added by software.
- The development set and all Telugu audio use synthetic voices.
- Misleading context is a stress test we built.
- The learning proof uses scripted confirmations.
- The Company data tab uses invented customers and simulated systems. No real company system is connected.

**Limits:** the test has one speaker. Other accents are unmeasured. Speech providers other than OpenAI have not been run live.

**Data and permission:** the real recordings are the builder's own voice. Names, numbers and customers in the scripts are invented.
Brand and place names are public. No customer or third-party personal data was used.
