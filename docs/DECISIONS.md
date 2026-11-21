# DECISIONS (append-only; newest at the bottom)

**D-001 Track and problem.** Track 2 (Voice AI for India), idea "Indian names and entities". Reasons: objective
A/B scoring ("same recordings on base vs your system"), less crowded than Track 1/3, it is Equal AI's core business
(1M+ live calls/day; summaries are only as good as the facts in them).

**D-002 Scope = facts in calls.** Entity classes: PERSON, ORG, PLACE, PHONE, PIN, AMOUNT. Every entity ends as
FIXED / CONFIRMED / KEPT / FLAGGED. Promise: no silent errors on facts. Out of scope: general WER, translation,
TTS, model training, full-duplex.

**D-003 Verified API facts (openai-python 3.57, Sat 12:20).** `include=["logprobs"]` only on gpt-4o-transcribe /
gpt-4o-mini-transcribe with response_format=json. gpt-transcribe supports `keywords` and `languages`.
gpt-realtime-whisper has no prompt in GA realtime sessions (OpenAI docs).

**D-004 No "Decisions API".** Verifier uses Chat Completions Structured Outputs (strict enum). Model is configurable.

**D-005 Data.** Synthetic dev (TTS x2 voices, phone-line degraded) + real-voice locked test + C4 adversarial
contexts. Dev/test disjoint templates and names. Test locked by SHA-256.

**D-006 Pure-Python number parser.** No pynini/WFST (C++ build risk). Tables in `numtables.py`.

**D-007 Money and phone numbers are never changed silently** unless the ASR itself was unsure (logprob below
`low_conf_logprob`). With no confidence or a confident ASR: FLAG and ask. Found by the C4 trap in the first
simulated run (over-correction 7.4% to 2.9%).

**D-008 YAML gotcha.** The key `on` parses as boolean True in YAML. System input key renamed to `input`.

**D-009 Hindi schwa deletion, left to right.** Needed so करना matches "karna", हैलो matches "hello" (stopwords), and
दिलसुखनगर -> dilsukhnagar. Compounds like राजेन्द्रनगर still come out slightly off; the distance tolerance absorbs it.

**D-010 Short brand names** (HDFC Bank -> "HDFC") are generated automatically, only when unique, at least 4
letters, and not an everyday word ("Yes Bank" gets no "Yes" shortcut).

**D-011 Names never span punctuation** ("है, अगर" sounded like "Neha Agarwal").

**D-012 Language scope (Sat 14:30).** The builder speaks Hindi, Hinglish and English, so the REAL-VOICE test set
uses only hi (Devanagari), hl (Hinglish in Latin letters) and en. Telugu stays in dev (synthetic voice, labelled).
Positioning: "multilingual by design (language packs, 9 scripts for sound matching); measured on hi/hl/en."
The test set was regenerated and re-locked BEFORE any recording (no leakage possible).

**D-013 Language packs + routing.** All language-specific words live in `data/languages/<code>.yaml`. Active packs
are MERGED (code-mixed speech needs all of them at once); conflicts fail fast. Per-token language tags + utterance
profile decide only the clarifying-question language. Adding a language = adding a YAML file.

**D-014 Structure (v0.2).** One folder per concern; resolvers behind one interface; Judge and MemoryStore are
protocols injected by `build_pipeline` (tests use fakes). Rules in docs/ENGINEERING.md, enforced by `make check`.

**D-015 API check results (Sat 14:29).** All candidate models exist on the key. gpt-transcribe and
gpt-4o-mini-transcribe write phone digits as English words in Devanagari ("नाइन एट फोर") -> handled by the en pack.
gpt-4o-transcribe returns logprobs and digits -> main Pehchaan input. Judge default gpt-4.1-mini (0.9 s);
gpt-6-luna (4.0 s) too slow for live calls.

**D-016 Longer span wins near-ties** (`matching.longer_span_bonus`): "HDFC बैंक" -> "HDFC Bank", not "HDFC Bank बैंक".

**D-017 Text cleanup for real ASR output:** Devanagari candra vowels (कॉल, कॉंडापूर), zero-width joiners (Kannada
acronyms), Malayalam chillu letters, Tamil de-aspiration and initial voiceless stops (ச -> s).

**D-018 Symmetric sound distance** for the public `distance()`: the shortened-name rule works in both directions.
