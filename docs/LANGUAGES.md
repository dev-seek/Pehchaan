# Which languages does Pehchaan work in?

**Short answer: not every language.** It is tested on real voice in Hindi, Hinglish and Indian English. Telugu is built but
tested only on synthetic voices. Nine more Indian languages partly work: names, places and digit numbers, but not spoken
money. Urdu script and non-Indian languages are not supported.

## What is supported today

| Level | Languages | What you can honestly say |
|---|---|---|
| **Tested on real voice** | Hindi, Hinglish, Indian English | The locked exam scored 35 Hindi, 29 Hinglish and 18 English facts, from one speaker on a simulated phone line |
| **Built, synthetic voice only** | Telugu | Full language pack and synthetic-voice dev calls. No real-voice test, because the builder does not speak Telugu |
| **Partial** | Marathi, Tamil, Kannada, Malayalam, Bengali, Gujarati, Punjabi, Odia, Assamese | Names and digit numbers usually work. Places work or become a question. **Spoken money and number words are not read**, so they are kept as said and flagged |
| **Not supported** | Urdu in Perso-Arabic script, Arabic, Spanish and other non-Indian languages | Digit numbers may pass through. Do not rely on anything else |

The per-language table is on the site's Benchmark Lab. Its data is `data/published/language_support.json`.

## How we checked

`tools/language_probe.py` runs one invented call per language through the SDK, offline, and records what happened to the name,
place, digit phone number and two spoken amounts. A test fails if the published file stops matching a fresh run.

This is a **capability check, not an accuracy score**:

- It checks text, so it says nothing about how well a speech model hears that language.
- There is one sentence per language. They were machine-written and **have not been reviewed by native speakers**.
- A language in the Partial row has **no accuracy number at all**.

We also sent a short clip to `gpt-transcribe` with each language code. It accepted Tamil, Kannada, Malayalam, Bengali, Marathi,
Gujarati, Urdu, Spanish and Arabic. It **refused Punjabi, Odia and Assamese** (HTTP 400), so for those Pehchaan retries without a
language hint and lets the model detect the language. Accepting a code does not mean the model hears that language well.

## What happens if you try another language

Pass the language code so the safety rule can apply:

```python
client.audio.transcriptions.create(model="gpt-transcribe", file=audio, language="ta")
```

- **Money and phone numbers are never changed on a guess.** With no number rules for a language, spoken numbers keep the caller's
  exact words and become a question (`pehchaan_sdk/guard.py`).
- **Always declare Marathi.** It shares the Hindi script, so Pehchaan cannot tell the two apart from the text alone.
- Results for these languages are labelled `unmeasured`.

## What it takes to support a new language

Most of the work is data and testing, not new code.

1. **Language pack** in `data/languages/xx.yaml`: number words, multipliers such as lakh and crore, money cues, everyday words
   that must never become names, and question templates.
2. **Script handling**, only for a new script. Sound matching already covers nine Indian scripts. Urdu needs Perso-Arabic
   transliteration, and that is real engineering because the script drops most vowels.
3. **Local lists** in `data/lexicons/`: brands and places for that region.
4. **Speech settings** in `config/settings.yaml`, including which language hints the model accepts.
5. **Test sentences written or reviewed by a native speaker**, covering numbers, money and code-mixing.
6. **Real recordings**, ideally from several speakers and accents, on real phone lines.
7. **A new locked exam** for that language, run once on frozen code, before claiming any accuracy.

**Why this is not done yet.** Steps 1 to 4 change the engine that sat the exam, which is frozen at tag `exam-freeze` so the
published results stay valid. New packs come after the event, with a new exam. Marathi, Tamil and Bengali are sensible first
additions, because their scripts are already handled and most of the gap is number words.
