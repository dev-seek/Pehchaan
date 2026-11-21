# GLOSSARY: every term in this project, in plain words

- **ASR (speech-to-text):** the model that turns audio into text. We use OpenAI's (gpt-transcribe, gpt-4o-transcribe).
- **Transcript:** the text the ASR produced.
- **Entity / fact:** the important bits: a person's name, a company, a place, a phone number, a PIN, an amount.
- **Logprob / confidence:** for each piece of text, the ASR tells us how sure it was. 0 = totally sure,
  -2 = quite unsure. We use it to decide when it's safe to correct something.
- **Context:** what the phone already knows: contacts, caller ID, recent SMS, your city. The levels C0-C4 are
  "how much context we allowed" (C4 = a deliberately misleading context, to test that we don't get fooled).
- **Pronunciation key:** a simplified spelling that keeps only how a word sounds ("Kondapoor" and "कोंडापुर" both
  become `kondapur`).
- **Edit distance:** how many letter changes turn one word into another. Ours is "weighted": swapping sounds that
  are easy to mishear (t/d, v/w, vowels) counts less than swapping unrelated sounds.
- **Schwa deletion:** Hindi script writes a hidden "a" after consonants that people don't say (कमल is "kamal", not
  "kamala"). We remove it so written Hindi matches spoken Hindi.
- **Transliteration:** writing one script in another's letters (कोंडापुर -> kondaapur). Not translation.
- **FIXED / CONFIRMED / KEPT / FLAGGED:** what we did with each fact: changed it (with a reason) / proved it right
  with evidence / left it, no evidence either way / couldn't be sure, so we ask one question.
- **Over-correction:** we "fixed" something that was already right. The worst kind of mistake for a fixer.
- **Silent error:** a fact that is wrong and nobody was warned. Our headline metric: push it to near zero.
- **Flag precision:** of the questions we asked, how many were actually needed.
- **Verifier:** a small LLM that we ask only for genuinely unclear cases; it must answer from a fixed menu
  (keep / candidate 1-3 / flag) using Structured Outputs, so it can't ramble or invent.
- **Baseline:** the thing we compare against (raw ASR; ASR with keywords; "LLM please fix it").
- **Dev / test split:** dev = practice questions we can study; test = the final exam we never peek at.
- **Leakage:** when the exam questions leak into practice. We prevent it with different names, places and
  templates, and a locked test file.
- **Bootstrap CI (confidence interval):** we re-sample our clips 1000 times to see how much the score wobbles.
  "92% [87-98]" means the true score is very likely between 87 and 98.
- **WER (word error rate):** % of words wrong overall. A guardrail: our fixes must not make it worse.
- **TTS (text-to-speech):** makes audio from text. We use it to create practice clips quickly.
- **Phone-line degradation:** making clean audio sound like a real phone call (8 kHz, narrow band, noise).
- **Cache:** we save every API answer to disk, so re-running costs nothing and gives the same result.
- **Structured Outputs:** forcing an LLM to answer in an exact JSON shape (e.g. one of five allowed words).
- **Language pack:** one YAML file per language (`data/languages/hi.yaml`) with its number words, cue words,
  everyday words and question templates. Adding a language = adding a file.
- **Registry:** all active packs merged into one dictionary, so code-mixed sentences work.
- **Language routing / profile:** each word gets a language tag; the sentence gets shares like hi 62% / en 38%.
- **Code-mixed:** more than one language in one sentence (Hinglish, Tenglish).
- **Resolver:** one decision-maker for one kind of fact (numbers, memory, names). The pipeline runs them in order.
- **Protocol / interface:** a promise of which methods a part has (e.g. a Judge has `decide()`), so parts can be swapped.
- **Dependency injection:** handing a part its tools (judge, memory) instead of it creating them, so tests can use fakes.
- **Lint (ruff):** an automatic code-style and bug-pattern checker. `make check` runs it.
