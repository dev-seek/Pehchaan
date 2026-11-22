"""
Write the adversarial test sets with a model that did not build Pehchaan (D-054).

    python tools/make_adversarial.py

One model writes hard call sentences with labels. A second, separate call checks each label and drops any it doubts.
A hash of each sentence then splits them: `adversarial_dev.json` may be read and fixed against, and
`adversarial_holdout.json` is sealed by SHA-256 and scored once. All names and numbers are invented.
This script prints counts only, so the holdout is never shown to whoever is building the system.
"""

from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pehchaan.config import ROOT  # noqa: E402
from pehchaan.openai_client import client  # noqa: E402

WRITER = "gpt-5.1"
BATCHES = 3
PER_BATCH = 14
CATEGORIES = {
    "decimal_money": "Money with decimals and short units: 2.5 lakh, 1.25 cr, 7.5k, Rs 99.50, 'two point five lakh', '3.75L', mixed with Hinglish.",
    "indian_fractions": "Indian fraction money words: sawa, paune, saade, dedh, dhai with sau, hazaar, lakh, crore, in Latin and Devanagari.",
    "self_corrections": "The speaker says an amount, phone number or PIN, then corrects it in many natural ways: nahi, sorry, I mean, galti se, matlab, actually, wait.",
    "several_real_values": "Two or more values that are ALL real and stay valid: advance and balance, rent and deposit, two phone numbers. Include negation that is not a correction, like 'EMI 6500 nahi bhari'.",
    "ranges_and_vague": "Ranges and vague sums: 5-7 lakh, 10 se 12 hazaar, between 2 and 3 lakh, do-teen hazaar. A range is not one exact amount.",
    "numbers_not_money": "Numbers that are not money: ages, times, dates, floors, kilometres, kg, litres, percentages, ratings, cricket scores, 4K TV, 5G, a 10k run, 2BHK, 1.5 ton AC, follower counts, populations like 2.5 lakh log.",
    "ids_like_phones": "Ten-digit and six-digit identifiers that are not phones or postal PINs: account, PNR, order, invoice, consumer, policy, tracking numbers, OTP, ATM PIN, employee code.",
    "spoken_phones": "Real mobile numbers spoken in hard forms: digit words, double and triple, groups of 5, +91, 0 prefix, Hindi and Telugu digit words, Devanagari digits.",
    "postal_pins": "Real Indian postal PIN codes in many spoken forms, with some wrong-length ones that must not be accepted as a PIN.",
    "number_words_as_names": "Number words used as names, places or idioms, not money: Koti, Lakhan, Hazari, Crore as nickname, Koti in Hyderabad, 'lakhon mein ek', 'hazaar baar', 'sau baat ki ek baat', in Latin, Devanagari and Telugu.",
    "brand_lookalikes": "Everyday words that sound like Indian brands or banks but are not: federal government, union budget, apple juice, amazon river, idea, tata bye bye, jio mere lal, access card, ola (hail). No real company is meant.",
    "commands_in_speech": "Text inside the transcript trying to manipulate software: ignore instructions, system notes, fake tags, 'mark as verified', 'set amount to', while the caller also states a real value.",
    "messy_transcripts": "Realistic speech-to-text mess: fillers, repeats, no punctuation, broken digits, wrong spacing, code-mixing, a real amount or phone buried in it.",
    "telugu_hindi_scripts": "Calls written in Telugu or Devanagari script with amounts, phones and PINs, including self-corrections and number words used as names.",
    "long_calls": "Long natural customer calls of 3 to 5 sentences mixing amounts, phones, PINs, ids that are not phones, and a correction.",
}
SYSTEM = """You write hard test cases for software that extracts money amounts, Indian mobile numbers and postal PIN codes from phone-call transcripts in India.
Write natural transcripts in Hinglish, Hindi, Telugu or Indian English. Use invented names and numbers only. Make them tricky, varied and realistic. Do not repeat a pattern.
For each case give the exact truth:
amounts: every rupee amount the speaker finally means, as plain digits. Leave out any value the speaker took back.
phones: every 10-digit Indian mobile number the speaker finally means. Leave out ids that are not phones and values taken back.
pins: every valid 6-digit postal PIN code finally meant. OTPs, ATM PINs and codes are not PINs.
allowed_amounts: for a range or vague sum, the bounds, which a system may report or leave out. Otherwise empty. A range has nothing in amounts.
forbidden: specific wrong readings a careless system could report, each with type AMOUNT, PHONE, PIN or ORG and a value. For ORG, give a brand or bank name that the words only sound like."""
CHECK = """You audit labels for a test set. A label says what a phone-call transcript really contains.
amounts are the rupee amounts finally meant. phones are 10-digit Indian mobile numbers finally meant. pins are valid 6-digit postal PIN codes finally meant.
allowed_amounts are the bounds of a range. forbidden are readings that must not be reported.
Answer ok=true only if every label is clearly right and nothing real is missing. If a sentence is ambiguous, answer ok=false."""
_STRINGS = {"type": "array", "items": {"type": "string"}}
_CASE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "amounts", "phones", "pins", "allowed_amounts", "forbidden"],
    "properties": {
        "text": {"type": "string"},
        "amounts": _STRINGS,
        "phones": _STRINGS,
        "pins": _STRINGS,
        "allowed_amounts": _STRINGS,
        "forbidden": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "value"],
                "properties": {
                    "type": {"type": "string", "enum": ["AMOUNT", "PHONE", "PIN", "ORG"]},
                    "value": {"type": "string"},
                },
            },
        },
    },
}
_CASES = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cases"],
    "properties": {"cases": {"type": "array", "items": _CASE}},
}
_VERDICT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean"}},
}


def _ask(system: str, user: str, schema: dict, name: str) -> dict:
    reply = client().chat.completions.create(
        model=WRITER,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
        timeout=180,
    )
    return json.loads(reply.choices[0].message.content)


def _write(job: tuple[str, str, int]) -> list[dict]:
    category, brief, batch = job
    user = f"Category: {brief}\nWrite {PER_BATCH} different cases. This is batch {batch + 1}, so choose unusual ones."
    try:
        return [{**case, "cat": category} for case in _ask(SYSTEM, user, _CASES, "cases")["cases"]]
    except Exception as exc:  # noqa: BLE001 - a lost batch only makes the set smaller
        print(f"batch failed: {category} {batch} ({type(exc).__name__})")
        return []


def _clean(case: dict) -> bool:
    digits = lambda v, n: v.isdigit() and len(v) == n  # noqa: E731
    return (
        bool(case["text"].strip())
        and all(v.replace(".", "", 1).isdigit() for v in case["amounts"] + case["allowed_amounts"])
        and all(digits(v, 10) and v[0] in "6789" for v in case["phones"])
        and all(digits(v, 6) and v[0] != "0" for v in case["pins"])
    )


def _audit(case: dict) -> bool:
    labels = {k: case[k] for k in ("amounts", "phones", "pins", "allowed_amounts", "forbidden")}
    try:
        return _ask(
            CHECK, json.dumps({"transcript": case["text"], "labels": labels}, ensure_ascii=False), _VERDICT, "audit"
        )["ok"]
    except Exception:  # noqa: BLE001 - an unaudited case is dropped
        return False


def main() -> None:
    root = ROOT / "data/bench"
    holdout = root / "adversarial_holdout.json"
    if holdout.exists():
        raise SystemExit("The holdout is already written and sealed.")
    jobs = [(c, brief, b) for c, brief in CATEGORIES.items() for b in range(BATCHES)]
    with ThreadPoolExecutor(10) as pool:
        written = [case for batch in pool.map(_write, jobs) for case in batch]
        unique = list({case["text"].strip(): case for case in written if _clean(case)}.values())
        kept = [case for case, ok in zip(unique, pool.map(_audit, unique), strict=True) if ok]
    parts: dict[str, list[dict]] = {"dev": [], "holdout": []}
    for case in kept:
        digest = hashlib.sha256(case["text"].strip().encode()).hexdigest()
        case["id"] = f"{case['cat']}_{digest[:8]}"
        parts["holdout" if int(digest, 16) % 2 else "dev"].append(case)
    note = f"Written by {WRITER}, labels audited by a second call, split by hash. Invented data. Not the exam."
    for name, cases in parts.items():
        body = json.dumps({"note": note, "cases": cases}, ensure_ascii=False, indent=1) + "\n"
        (root / f"adversarial_{name}.json").write_text(body, encoding="utf-8")
    (root / "adversarial_holdout.sha256").write_text(hashlib.sha256(holdout.read_bytes()).hexdigest() + "\n")
    print(
        f"written {len(written)}, valid {len(unique)}, audited {len(kept)}, dev {len(parts['dev'])}, holdout {len(parts['holdout'])}"
    )


if __name__ == "__main__":
    main()
