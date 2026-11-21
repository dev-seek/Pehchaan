# PITCH: story, slides, demo script, judge Q&A

## The name
**Pehchaan** = recognition / identity (Hindi). Equal AI itself began as *Equal Identity*, a consent-based identity
company. Our product makes sure the AI recognises *who* and *what* in every call.

## Language positioning (D-012)
"Multilingual by design: one fact layer, pluggable language packs. Measured on Hindi, Hinglish and Indian English
(including code-mixed speech); sound matching runs on 9 Indian scripts; a new language is a data file."
Demo moment: one contact resolved from Telugu, Hindi, Kannada and Latin spellings.

## One-liners
- **Headline: "Every fact in an Indian call: right, or it asks."**
- "Speech AI gets the words right and the facts wrong. Pehchaan makes every fact in an Indian call right, or it asks."
- "We don't make the model better at Hindi. We make sure it never silently gets your name, your number or your money wrong."

## Slide 1: The expensive Indian pain
- Play a 6-second clip: caller says a name + locality + amount + number; show the raw transcript mangling them.
- Numbers (sources): small public test of whisper-1 on Indian audio: Indian names ~66% WER, addresses+PINs ~37%
  (synthetic, directional); a voice-AI team: 96% lab accuracy but production failing because errors concentrated
  on city names and tracking numbers; Lahaja benchmark: accuracy drops on named entities and for South/North-East
  speakers. Plus our own dev numbers (60 synthetic-voice clips, tuned on, so optimistic): plain ASR silent error rate 17.7%.
- Why it matters for Equal: a call summary is only useful if "who called, from where, which number, how much" is right.

## Slide 2: What we built
"A drop-in layer between any speech model and the agent: it uses what the phone already knows (contacts, caller
ID, SMS) and India-specific sound and number rules to **fix, confirm or flag** every fact. Names and places are fixed from context;
phone numbers, PINs and amounts are never changed automatically, only confirmed or flagged with one question. A
confirmed name is learned only after it passes a replay on labelled calls."

## Slide 3: How it works (the 5-stage diagram from ARCHITECTURE.md)
Numbers engine (lakh/crore/saade/teen-ty/stutters/PIN prefixes) that reads and checks but never rewrites, sound-alike
matching across scripts (एचडीएफसी = HDFC), verifier LLM only for ambiguous cases (Structured Outputs), a second
transcript made without context as a second opinion, an admission gate that every fix must pass, one-question
clarifier, verified learning (names and places only, replayed before adoption, reversible).

## Slide 4: Proof (Pehchaan-Bench): fill with REAL numbers
Only show numbers that exist, with their label (docs/EVAL.md). Today that is the 60-clip multi-voice dev set
(synthetic voices, tuned on): plain ASR 17.7% silent errors, keyword ASR 7.3%, Pehchaan 1.2% [0-3]; under the
adversarial context (C4) the naive LLM fixer falls to 57.9% accuracy (58 damaged edits) while Pehchaan holds 94.5%
with 0 damaged edits. Say plainly: intervals overlap, so the accuracy gain is not proven; the clear win is
**0 damaged edits** (12 before) and few, correct questions. Harness latency p50 about 2 ms; LLM on 0.23 calls/clip.
The exam row ("30-clip single-speaker real-voice test (simulated phone line)") stays EMPTY until the one exam run.

## Slide 5: What's next and who pays
Customer #1: Equal AI (consumer call assistant, 1M+ live calls/day). Next: voice agents for BFSI collections,
logistics, healthcare booking. Middleware priced per call-minute, a fraction of the ASR cost. Roadmap: streaming
mode, semantic end-of-turn for Indian speech, more languages, on-device context.

## 3-minute demo script
1. (20 s) Problem in one sentence + play the mangled clip.
2. (60 s) Playground. Use Delivery for the Bommanahalli fix and Bank EMI + Phone for the verified installment and callback.
   Telugu Callback Flag asks for the number again and blocks the callback preview.
3. (20 s) Use Wrong-Context Trap. Play the line that says Kadugodi, show the incorrect hint, and type **Kadugodi**
   under **Or type the correct name or place**. Show the six checks passing, then choose **Replay the same call**. Show
   the memory hit, zero LLM calls, and replay time.
4. (40 s) Proof page: the table. Say the headline numbers and the C4 trap result.
5. (20 s) Invite a judge to say their own name + locality + a phone number into the mic.
6. (20 s) Close with the one-liner + who pays.

## Judge Q&A prep
- **"Why not just pass keywords to the ASR?"** We do; that's baseline B1. Our layer adds value on top
  (P_on_B1_C3), handles numbers (keywords can't validate a PIN or a teen/ty amount; we never change them, we flag), and asks instead of guessing.
- **"Why not just ask an LLM to fix it?"** Baseline B2. Under adversarial context it invents names/amounts;
  it's also slower and costlier on every utterance. We call the LLM only for ambiguous cases, with a fixed menu.
- **"Privacy?"** Context stays with the user's app; only the small candidate list for one span goes to the verifier;
  memory is per-user, every learned fix can be undone, and it can be deleted.
- **"Is the data synthetic?"** Dev is synthetic for speed and we tuned on it, so say its numbers are optimistic. The
  exam set is real human voice, ONE speaker, with a simulated phone line, locked before tuning (SHA-256 in the repo),
  run once. Be upfront that it is one voice.
- **"Is it self-learning?"** It learns from human confirmations, with evidence. Each answer is a candidate, replayed on 60
  labelled calls, then adopted or rejected, logged and reversible. On a voice it never heard, with no context, correct facts
  went from 138 to 150 of 164 with 0 harmed, and 36 of 36 deliberately wrong answers were blocked. Be upfront: these were
  scripted confirmations on dev data, the gain with full context is small (154 to 156), and it does not invent its own rules.
- **"Does it work on other models?"** It's model-agnostic: it takes any transcript; confidence is optional.
- **"Latency?"** Milliseconds for rules and matching; the verifier only on ambiguous spans.
