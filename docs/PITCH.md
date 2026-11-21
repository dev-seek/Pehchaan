# PITCH: story, slides, demo script, judge Q&A

## The name
**Pehchaan** = recognition / identity (Hindi). Equal AI itself began as *Equal Identity*, a consent-based identity
company. Our product makes sure the AI recognises *who* and *what* in every call.

## Language positioning (D-012)
"Multilingual by design: one fact layer, pluggable language packs. Measured on Hindi, Hinglish and Indian English
(including code-mixed speech); sound matching runs on 9 Indian scripts; a new language is a data file."
Demo moment: one contact resolved from Telugu, Hindi, Kannada and Latin spellings.

## One-liners
- "Speech AI gets the words right and the facts wrong. Pehchaan makes every fact in an Indian call right, or flagged."
- "We don't make the model better at Hindi. We make sure it never silently gets your name, your number or your money wrong."

## Slide 1: The expensive Indian pain
- Play a 6-second clip: caller says a name + locality + amount + number; show the raw transcript mangling them.
- Numbers (sources): small public test of whisper-1 on Indian audio: Indian names ~66% WER, addresses+PINs ~37%
  (synthetic, directional); a voice-AI team: 96% lab accuracy but production failing because errors concentrated
  on city names and tracking numbers; Lahaja benchmark: accuracy drops on named entities and for South/North-East
  speakers. Plus our own dev numbers: B0 silent error rate = __%.
- Why it matters for Equal: a call summary is only useful if "who called, from where, which number, how much" is right.

## Slide 2: What we built
"A drop-in layer between any speech model and the agent: it uses what the phone already knows (contacts, caller
ID, SMS) and India-specific sound and number rules to **fix, confirm or flag** every fact, and it learns from
every confirmation."

## Slide 3: How it works (the 5-stage diagram from ARCHITECTURE.md)
Numbers engine (lakh/crore/saade/teen-ty/stutters/PIN prefixes), sound-alike matching across scripts
(एचडीएफसी = HDFC), verifier LLM only for ambiguous cases (Structured Outputs), one-question clarifier, memory.

## Slide 4: Proof (Pehchaan-Bench): fill with REAL numbers
Table: B0, B1 (OpenAI keywords), B2 (LLM fix), Pehchaan C3, Pehchaan C4 (adversarial), on the locked real-voice
test set: entity accuracy (CI), **silent error rate (CI)**, over-correction, flags/clip, latency.
Call out: (1) silent errors __% to __%, (2) over-correction ~0 even under adversarial context where the naive
LLM fix hallucinates, (3) +__ ms median latency, LLM on only __% of utterances.

## Slide 5: What's next and who pays
Customer #1: Equal AI (consumer call assistant, 1M+ live calls/day). Next: voice agents for BFSI collections,
logistics, healthcare booking. Middleware priced per call-minute, a fraction of the ASR cost. Roadmap: streaming
mode, semantic end-of-turn for Indian speech, more languages, on-device context.

## 3-minute demo script
1. (20 s) Problem in one sentence + play the mangled clip.
2. (60 s) Live tab: same clip, side by side. Point at badges: FIXED name (from contacts), CONFIRMED amount
   (matches SMS), FLAGGED PIN with the one-line question.
3. (20 s) Memory loop: click confirm, run again, it's fixed instantly ("source: memory").
4. (40 s) Bench tab: the table. Say the headline numbers and the C4 trap result.
5. (20 s) Invite a judge to say their own name + locality + a phone number into the mic.
6. (20 s) Close with the one-liner + who pays.

## Judge Q&A prep
- **"Why not just pass keywords to the ASR?"** We do; that's baseline B1. Our layer adds value on top
  (P_on_B1_C3), handles numbers (keywords can't validate a PIN or a teen/ty amount), and flags instead of guessing.
- **"Why not just ask an LLM to fix it?"** Baseline B2. Under adversarial context it invents names/amounts;
  it's also slower and costlier on every utterance. We call the LLM only for ambiguous cases, with a fixed menu.
- **"Privacy?"** Context stays with the user's app; only the small candidate list for one span goes to the verifier;
  memory is per-user and deletable (`DELETE /api/memory/{user}`).
- **"Is the data synthetic?"** Dev is synthetic for speed; the headline test set is real human voice, locked
  before tuning (SHA-256 in the repo).
- **"Does it work on other models?"** It's model-agnostic: it takes any transcript; confidence is optional.
- **"Latency?"** Milliseconds for rules and matching; the verifier only on ambiguous spans.
