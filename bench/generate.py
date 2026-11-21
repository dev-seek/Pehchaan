#!/usr/bin/env python3
"""
Generate the benchmark scripts (what will be spoken) with exact ground truth and per-call context.

    python -m bench.generate            # writes data/bench/dev_scripts.jsonl and test_scripts.jsonl

Design choices (see docs/EVAL.md):
  * Labels are exact by construction: code fills each {SLOT} with a spoken form AND a written form.
  * Dev and test use DIFFERENT templates and DIFFERENT names/localities (seeded split), so tuning on dev
    cannot memorise test entities.
  * Every script carries two contexts: `context` (realistic, C3) and `context_adv` (C4 trap: true entities
    removed, sound-alike decoys added, a decoy phone one digit off, a teen/ty-swapped SMS amount).
  * test_scripts.jsonl gets a SHA-256 lock file. If it ever changes, the lock check fails.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
import re

import yaml

from pehchaan.config import path, settings
from pehchaan.context import lexicon
from pehchaan.numbers import rules
from pehchaan.sound import distance
from pehchaan.text import normalize

from .verbalize import en_amount, en_digits, hi_amount, hi_digits, hinglish_amount

AMOUNT_KINDS = {  # (low, high, step, teen_bias)
    "emi": (2_000, 60_000, 50, 0.4), "rent": (8_000, 60_000, 500, 0.4), "cod": (199, 4_999, 1, 0.0),
    "refund": (149, 9_999, 1, 0.1), "txn": (500, 150_000, 1, 0.3), "loan": (50_000, 2_500_000, 10_000, 0.2),
    "premium": (2_000, 60_000, 1, 0.4), "transfer": (500, 100_000, 100, 0.3), "bill": (199, 2_999, 1, 0.0),
}
SMS_BODIES = {
    "bank": "Dear Customer, EMI of Rs {amt} for your loan is due. Pay via app. -{name}",
    "nbfc": "Your EMI of Rs {amt} is due. Avoid late charges. -{name}",
    "fintech": "Rs {amt} credited/debited on your account. -{name}",
    "insurance": "Premium of Rs {amt} for your policy is due this week. -{name}",
    "delivery": "Your order of Rs {amt} is out for delivery. -{name}",
    "ecom": "Refund of Rs {amt} initiated for your order. -{name}",
    "courier": "Shipment out for delivery, PIN {pin}. -{name}",
    "telecom": "Your bill of Rs {amt} is generated. -{name}",
}


def _split(items: list, rng: random.Random) -> tuple[list, list]:
    items = sorted(set(items))
    rng.shuffle(items)
    h = len(items) // 2
    return items[:h], items[h:]


def _phone(rng):
    return str(rng.choice("6789")) + "".join(str(rng.randint(0, 9)) for _ in range(9))


def _amount(kind, rng):
    lo, hi, step, teen_bias = AMOUNT_KINDS[kind]
    if rng.random() < teen_bias and lo <= 13_000:
        th = rng.randint(13, 19)
        return th * 1000 + rng.choice([0, 0, 500, 250, 750])
    return rng.randrange(lo, hi + 1, step)


def _near(target: str, pool: list[str], k: int, exclude: set[str]) -> list[str]:
    scored = sorted((distance(target, p), p) for p in pool if p not in exclude and p != target)
    return [p for _, p in scored[:k]]


def make_scripts(split: str, n: int, rng: random.Random, names: list[str], places: list[tuple[str, str]],
                 all_names: list[str]) -> list[dict]:
    templates = [t for t in yaml.safe_load(path("templates").read_text(encoding="utf-8")) if t["split"] == split]
    brands = lexicon.brands()
    out = []
    for i in range(n):
        t = templates[i % len(templates)] if i < len(templates) else rng.choice(templates)
        slots = set(re.findall(r"\{(\w+)\}", t["text"]))
        spoken, written, ents = t["text"], t["text"], []
        city, place = rng.choice(places)
        person = rng.choice(names)
        kinds = t.get("org_kinds") or [b.kind for b in brands]
        org = rng.choice([b for b in brands if b.kind in kinds])
        phone = _phone(rng)
        amount = _amount(t.get("amount_kind", "transfer"), rng)
        pin = lexicon.pin_prefixes(city)[0] + f"{rng.randint(0, 99):03d}"
        if "PERSON" in slots:
            spoken, written = spoken.replace("{PERSON}", person), written.replace("{PERSON}", person)
            ents.append({"type": "PERSON", "value": person})
        if "ORG" in slots:
            spoken, written = spoken.replace("{ORG}", org.name), written.replace("{ORG}", org.name)
            ents.append({"type": "ORG", "value": org.name})
        if "PLACE" in slots:
            spoken, written = spoken.replace("{PLACE}", place), written.replace("{PLACE}", place)
            ents.append({"type": "PLACE", "value": place, "city": city})
        if "AMOUNT" in slots:
            say = _spoken_amount(amount, t["lang"], rng)
            spoken, written = spoken.replace("{AMOUNT}", say), written.replace("{AMOUNT}", f"{amount}")
            ents.append({"type": "AMOUNT", "value": str(amount)})
        if "PHONE" in slots:
            say = _spoken_digits(phone, t["lang"], rng)
            spoken, written = spoken.replace("{PHONE}", say), written.replace("{PHONE}", phone)
            ents.append({"type": "PHONE", "value": phone})
        if "PIN" in slots:
            spoken, written = spoken.replace("{PIN}", en_digits(pin, rng, group=None)), written.replace("{PIN}", pin)
            ents.append({"type": "PIN", "value": pin})

        ctx = _context(rng, slots, city, person, org, place, phone, amount, pin, names, t)
        adv = _adversarial(rng, ctx, slots, person, org, place, phone, amount, city, all_names)
        sid = f"{split}_{i:03d}_{t['id']}"
        out.append({"script_id": sid, "split": split, "template_id": t["id"], "lang": t["lang"],
                    "domain": t["domain"], "spoken": spoken, "reference": written, "entities": ents,
                    "context": ctx, "context_adv": adv})
    return out


def _spoken_amount(amount: int, lang: str, rng: random.Random) -> str:
    """Hindi callers mostly say amounts in Hindi; everyone else mostly in English (Indian system)."""
    if lang == "hi" and rng.random() < 0.7:
        return hi_amount(amount, rng)
    if lang == "hl" and rng.random() < 0.6:
        return hinglish_amount(amount, rng)
    return en_amount(amount)


def _spoken_digits(digits: str, lang: str, rng: random.Random) -> str:
    """Phone numbers are mostly said digit by digit in English, sometimes in Hindi."""
    if lang == "hi" and rng.random() < 0.3:
        return hi_digits(digits)
    if lang == "hl" and rng.random() < 0.2:
        return normalize(hi_digits(digits))
    return en_digits(digits, rng)


def _context(rng, slots, city, person, org, place, phone, amount, pin, names, t) -> dict:
    brands = lexicon.brands()
    distract = rng.sample([x for x in names if x != person], k=rng.randint(10, 14))
    contacts = [{"name": x, "number": _phone(rng)} for x in distract]
    if "PERSON" in slots and rng.random() < 0.75:
        contacts.append({"name": person, "number": phone if ("PHONE" in slots and rng.random() < 0.6) else _phone(rng)})
    rng.shuffle(contacts)
    caller = {"number": phone if ("PHONE" in slots and rng.random() < 0.5) else _phone(rng)}
    if "ORG" in slots and rng.random() < 0.5:
        caller["cnap_name"] = org.name.upper()
    sms = []
    for b in rng.sample([b for b in brands if b.name != org.name], k=rng.randint(1, 3)):
        body = SMS_BODIES.get(b.kind, "Thank you for choosing us. -{name}")
        sms.append({"sender": f"VM-{b.sender_ids[0]}", "body": body.format(amt=f"{_amount('bill', rng):,}",
                                                                          pin="000000", name=b.name)})
    if "ORG" in slots and rng.random() < 0.75:
        body = SMS_BODIES.get(org.kind, "Update from {name}.")
        amt = amount if ("AMOUNT" in slots and rng.random() < 0.7) else _amount("bill", rng)
        sms.append({"sender": f"AD-{org.sender_ids[0]}", "body": body.format(amt=f"{amt:,}", pin=pin, name=org.name)})
    elif "PIN" in slots and rng.random() < 0.5:
        sms.append({"sender": "VM-DELHVY", "body": f"Shipment out for delivery, PIN {pin}. -Delhivery"})
    rng.shuffle(sms)
    places = [place] if ("PLACE" in slots and rng.random() < 0.3) else []
    return {"user": {"id": "bench_user", "city": city}, "caller": caller, "contacts": contacts, "sms": sms,
            "places": places, "domain": t["domain"]}


def _adversarial(rng, ctx, slots, person, org, place, phone, amount, city, all_names) -> dict:
    adv = copy.deepcopy(ctx)
    if "PERSON" in slots:
        adv["contacts"] = [c for c in adv["contacts"] if c["name"] != person]
        for d in _near(person, all_names, 2, {c["name"] for c in adv["contacts"]}):
            adv["contacts"].append({"name": d, "number": _phone(rng)})
    if "ORG" in slots:
        adv["caller"].pop("cnap_name", None)
        adv["sms"] = [s for s in adv["sms"] if org.name not in s["body"]]
        for d in _near(org.name, [b.name for b in lexicon.brands()], 2, set()):
            b = next(b for b in lexicon.brands() if b.name == d)
            adv["sms"].append({"sender": f"AD-{b.sender_ids[0]}", "body": f"Important update from {d}."})
    if "PLACE" in slots:
        adv["places"] = _near(place, lexicon.localities(city), 2, {place})
    if "PHONE" in slots:   # decoy: a known number exactly one digit away from the true one
        pos = rng.randrange(1, 10)
        decoy = phone[:pos] + str((int(phone[pos]) + rng.randint(1, 8)) % 10) + phone[pos + 1:]
        adv["caller"]["number"] = decoy
        for c in adv["contacts"]:
            if c.get("number") == phone:
                c["number"] = _phone(rng)
    if "AMOUNT" in slots:  # decoy: SMS mentions the teen/ty-swapped amount
        variants = rules.teen_ty_digit_variants(str(amount))
        decoy_amt = int(variants[0]) if variants else amount * 10
        adv["sms"] = [s for s in adv["sms"] if f"{amount:,}" not in s["body"]]
        adv["sms"].append({"sender": "AD-HDFCBK", "body": f"Dear Customer, EMI of Rs {decoy_amt:,} is due. -HDFC Bank"})
    return adv


def main():
    cfg = settings()
    rng = random.Random(cfg["bench"]["seed"])
    all_names = yaml.safe_load(path("pools").read_text(encoding="utf-8"))["names"]
    dev_names, test_names = _split(all_names, rng)
    places = [(c, loc) for c in lexicon.city_names() for loc in lexicon.localities(c)]
    dev_places, test_places = _split(places, rng)
    out_dir = path("bench")
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, names, plc, n in (("dev", dev_names, dev_places, cfg["bench"]["dev_scripts"]),
                                 ("test", test_names, test_places, cfg["bench"]["test_scripts"])):
        scripts = make_scripts(split, n, random.Random(f"{cfg['bench']['seed']}-{split}"), names, plc, all_names)
        f = out_dir / f"{split}_scripts.jsonl"
        f.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in scripts), encoding="utf-8")
        print(f"wrote {len(scripts)} scripts -> {f}")
    test_file = out_dir / "test_scripts.jsonl"
    lock = out_dir / "test_scripts.sha256"
    digest = hashlib.sha256(test_file.read_bytes()).hexdigest()
    if lock.exists() and lock.read_text().strip() != digest:
        raise SystemExit("TEST SET CHANGED but a lock exists. Do not regenerate the test set after recording. "
                         "If you really mean it, delete data/bench/test_scripts.sha256 and say why in docs/DECISIONS.md.")
    lock.write_text(digest + "\n")
    print(f"test set locked: sha256 {digest[:16]}...")


if __name__ == "__main__":
    main()
