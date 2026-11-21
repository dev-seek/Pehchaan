# Architecture

## In one picture
```
 phone call audio ─┬─► Speech-to-text WITH context keywords ──► transcript 1 (+ logprobs)   the input
                   └─► Speech-to-text WITHOUT keywords ───────► transcript 2               the second opinion
 what the phone knows (contacts, caller ID, SMS, city) ──► CallContext (C0..C4); global lists (brands, localities)
                                         │
                   ┌──────────── PEHCHAAN pipeline ───────────────────────────┐
                   │ prepare   tokens + confidences + language routing          │
                   │ propose   NumberResolver → MemoryResolver → NameResolver   │
                   │           (Judge only if ambiguous): every output is a     │
                   │           PROPOSAL, nothing is applied yet                 │
                   │ admit     AdmissionGate checks each proposal (see below)   │
                   │ output    rewritten text + 1 question per FLAGGED fact     │
                   └────────────────────────────────────────────────────────────┘
                            │                                   │
         corrected transcript + facts (+ `refused`)   "Kondapur ya Kothapur?" → answer → memory (names/places only)
```
Typed text works too (no audio): then there is no second opinion and the gate skips that one rule.

## Plain-words explanation
A speech model is a fast typist who doesn't know your city or your friends. It types "Konda poor", "Venkat row",
writes your phone number as "नाइन एट फोर…", and sometimes hears fourteen thousand as forty thousand.
Pehchaan is the assistant who checks the phone before trusting the typist: "Venkat row is Venkateswara Rao,
he's in your contacts. नाइन एट फोर… is 98480 12345, the caller ID matches. Forty thousand five hundred
conflicts with today's bank SMS (14,500), and the typist wasn't sure, so I'll ask." When it can't be sure, it asks
one short question in the caller's language. When you answer, it remembers names and places (never numbers).

## Package map (one folder = one concern; see docs/ENGINEERING.md)
| folder | job | key idea |
|---|---|---|
| `text/` | scripts to one Latin form; tokens with offsets | Hindi schwa deletion; Tamil/Malayalam fixes; loanword vowels (कॉल) |
| `languages/` | packs, registry, routing | ALL language words in `data/languages/*.yaml` |
| `sound/` | fingerprint + weighted distance | aspiration/vowel-length collapse; cheap swaps for easy mishearings; shortened names |
| `numbers/` | read spoken numbers; validity/repair rules | digit vs value readings; teen/ty; stutter repair; PIN city prefixes |
| `context/` | CallContext (C0-C4) + lexicons | per-call (trusted, small) vs global (strict) candidates |
| `asr/`, `judge/`, `openai_client.py` | OpenAI calls, cached | logprobs mapped to tokens; judge = Structured Outputs enum |
| `resolvers/` | proposals | `NumberResolver`, `MemoryResolver`, `NameResolver`, all one interface |
| `policy/` | admission | `AdmissionGate` + second-opinion evidence: decides what a proposal may change |
| `output/` | rewrite + clarifying questions | questions in the caller's dominant language |
| `pipeline.py` | wiring | dependencies injected: judge, memory store, registry |

## Language routing (how mixed Hindi + English + Telugu works)
There is no "pick one language pack" switch, because callers mix languages inside one sentence.
1. **Every active pack is merged** into one registry (`languages/registry.py`). Any layer asks "is `naain` a
   number word?" and the registry answers from Hindi, English and Telugu at once. If two packs disagree about a
   word, loading fails immediately (fail fast).
2. **Every token gets a language tag** (`languages/detect.py`). Indic script → the pack owning that script
   (Devanagari → hi, Telugu → te). Spelled acronyms in Indic script (एचडीएफसी) → decoded to "hdfc", tagged en.
   Latin words → the pack whose vocabulary contains them (hai/raha → hi, sir/number → en). Unknown → no vote.
3. **The utterance gets a profile**, e.g. `{hi: 0.62, en: 0.38}` = "code-mixed hi+en". The dominant language picks
   the language of the clarifying question. Everything else uses the merged registry, so mixing is never a problem.
4. **What is language-independent:** sound matching (works on 9 scripts), context, phone/PIN/amount rules, memory.

## Decision logic (names, places, brands): `resolvers/names.py`
- distance <= `verify_max_dist`: **CONFIRMED** (same sound; canonical spelling written)
- distance <= autofix (per-call 0.20 / global 0.12, +bonus if the ASR was unsure), clear winner, ASR not certain: **FIXED**
- close but ambiguous: **Judge** (keep / cand1-3 / flag); without a judge, a per-call candidate close enough: **FLAGGED**
- longer spans win near-ties ("HDFC बैंक" over "HDFC"); names never cross punctuation
## Admission gate: `policy/gate.py` (D-023)
A resolver only proposes. The gate applies five rules; a refused proposal is kept in `refused` with its rule, and
each entity carries `admission` ("admitted" or the rule that changed it).
- `critical_read_only`: PHONE / PIN / AMOUNT keep the value that was heard; a proposed change becomes a question
- `acronym_spelled`: "LIC" needs the letters L-I-C to be heard; a similar-sounding word ("लिख") is not evidence
- `common_word`: an everyday word ("delivery") stays a word unless this call's context names that entity and the word
  sits where an entity belongs
- `person_not_place`: a span marked as a place ("... wale") cannot become a contact's name
- `second_opinion` (D-022): if transcript 2 (no keywords) heard neither a context-confirmed name nor that number, ask
  instead of confirming. If both transcripts heard the same number, a mere resemblance to a context number does not
  cause a question

## Decision logic (numbers): `resolvers/numbers.py` (D-021: read-only)
Numbers are never rewritten. The resolver can only CONFIRM (matches context), KEEP, or FLAG.
- PHONE: matches a known number: CONFIRMED · wrong digit count, or a cue word ("number") followed by garbled or
  partial digits: FLAGGED (a repair, e.g. one digit off a known number, appears only as an option in the question)
- PIN: valid for the user's city: KEPT/CONFIRMED · wrong city prefix or digit count: FLAGGED
- AMOUNT: equals an SMS amount: CONFIRMED · a teen/ty variant of an SMS amount: FLAGGED with that amount as the option
- Memory refuses PHONE/PIN/AMOUNT too (`MemoryResolver`; the API answers HTTP 400)

## Latency (measured offline on real ASR text)
prepare ~0.2-2 ms · numbers <1 ms · memory <1 ms · names 4-25 ms (first call warms caches) · judge only when ambiguous
(gpt-4.1-mini ~0.9 s, measured on our key). The harness (everything after the ASR) has p50 about 2 ms on dev.
The product makes two speech-to-text calls per audio clip (keywords + plain, run in parallel).
