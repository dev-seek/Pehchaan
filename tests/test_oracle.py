"""Tests for the independent scoring oracle (bench/oracle). No engine code is used."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from bench.oracle import audit_edits, fact_correct, name_present, read_numbers, same_name

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("text,want", [
    ("चौदा हज़ार सात सौ पचास रुपए", 14750),
    ("14 हज़ार 750", 14750),
    ("₹14,750", 14750),
    ("Rs 1,03,100", 103100),
    ("एक लाख तीन हज़ार एक सौ बारह", 103112),
    ("fourteen thousand two hundred fifty", 14250),
    ("chaudah hazaar saat sau pachaas", 14750),
    ("saade teen hazaar", 3500),
    ("paune do hazaar", 1750),
    ("sawa lakh", 125000),
    ("dedh sau", 150),
    ("ఇరవై ఐదు వేలు", 25000),
    ("اٹھارہ ہزار پانچ سو", 18500),
    ("thirty eight thousand five hundred", 38500),
    ("38 थाउज़ंड 500", 38500),
])
def test_values(text, want):
    assert float(want) in read_numbers(text).values


def test_chauda_followed_by_literal_is_not_14750():
    facts = read_numbers("चौदा 1,750")
    assert 14750.0 not in facts.values
    assert {14.0, 1750.0} <= facts.values


@pytest.mark.parametrize("text,digits", [
    ("double eight seven six four, two three one four nine।", "8876423149"),
    ("five six triple zero seven", "560007"),
    ("नौ आठ", "98"),
    ("नाइन एट", "98"),
    ("saat ek nau aath chhah aath chaar nau zeero teen", "7198684903"),
    ("88764 23149", "8876423149"),
    ("nine one double zero four, eight two five double two", "9100482522"),
])
def test_digit_runs(text, digits):
    assert digits in read_numbers(text).digit_strings


def test_phone_rules():
    phone = {"type": "PHONE", "value": "9876543210"}
    assert fact_correct(phone, "call +91 98765 43210 now")
    assert fact_correct(phone, "call 09876543210")
    assert not fact_correct(phone, "call 19876543210")        # substring of a longer run
    assert not fact_correct(phone, "call 9876543211")
    assert not fact_correct({"type": "PIN", "value": "560007"}, "pin 5600071")
    assert fact_correct({"type": "AMOUNT", "value": "14750"}, "चौदा हज़ार सात सौ पचास")
    assert not fact_correct({"type": "AMOUNT", "value": "14750"}, "चौदा 1,750 रुपए")


@pytest.mark.parametrize("a,b", [
    ("Kondapoor", "Kondapur"), ("कोंडापुर", "Kondapur"), ("एरागद्दा", "Erragadda"),
    ("नारायणगुड़ा", "Narayanguda"), ("मोहम्मद इरफ़ान", "Mohammed Irfan"), ("KR पुरम", "KR Puram"),
    ("के आर पुरम", "KR Puram"), ("एचडीएफसी बैंक", "HDFC Bank"), ("محمد عرفان", "Mohammed Irfan"),
    ("బాచుపల్లి", "Bachupally"),
])
def test_same_name_true(a, b):
    assert same_name(a, b) and same_name(b, a)


@pytest.mark.parametrize("a,b", [
    ("Kothapur", "Kondapur"), ("एरादग्दा", "Erragadda"), ("Neha Agarwal", "Narayanguda"),
    ("Priya", "Preeti"), ("Ravi", "Rani"),
])
def test_same_name_false(a, b):
    assert not same_name(a, b)


def test_name_present_in_text():
    assert name_present("Narayanguda", "मैं नारायणगुड़ा वाले flat के लिए")
    assert name_present("KR Puram", "address के आर पुरम pin")
    assert not name_present("Narayanguda", "मैं Neha Agarwal बोल रहा हूँ")
    assert not name_present("Kondapur", "Kothapur wale")


def test_audit_kinds():
    ents = [{"type": "ORG", "value": "Zepto"}]
    known = ["Delhivery", "Neha Agarwal", "Zepto"]
    one = lambda i, o: audit_edits(i, o, ents, known)           # noqa: E731
    assert one("तेरह हज़ार रुपये", "13000 रुपये")[0]["kind"] == "format"
    bad = one("चौदा हज़ार सात सौ पचास रुपए", "चौदा 1,750 रुपए")
    assert [(x["kind"], x["reason"]) for x in bad] == [("damage", "value_changed")]
    assert one("डिलीवरी बॉय", "Delhivery बॉय")[0]["reason"] == "invented_entity"
    assert one("नारायणगुड़ा वाले", "Neha Agarwal")[0]["reason"] == "invented_entity"
    assert one("जेप्टो से", "Zepto से")[0]["kind"] == "format"
    assert one("सैप्टो से", "Zepto से")[0]["kind"] == "repair"
    assert one("Kothapur wale", "Kondapur wale")[0]["reason"] == "rewrite"
    phone = [{"type": "PHONE", "value": "9876543210"}]
    assert audit_edits("no 98765 43211", "no 9876543210", phone, [])[0]["kind"] == "repair"
    assert audit_edits("no 98765 43211", "no 9876543299", phone, [])[0]["reason"] == "value_changed"


def test_dev_scripts_reference_and_spoken():
    path = ROOT / "data" / "bench" / "dev_scripts.jsonl"
    if not path.exists():
        pytest.skip("dev scripts not present")
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for e in row["entities"]:
            assert fact_correct(e, row["reference"]), (e, row["reference"])
            if e["type"] in ("PHONE", "PIN", "AMOUNT"):
                assert fact_correct(e, row["spoken"]), (e, row["spoken"])


def test_oracle_is_clean_room():
    for f in (ROOT / "bench" / "oracle").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert len(src.splitlines()) < 300, f
        assert not re.search(r"^\s*(from|import)\s+pehchaan", src, re.M), f
        assert not re.search(r"bench\.(score|verbalize|generate)|from \.\.(score|verbalize)", src), f


def test_real_consonant_or_first_vowel_change_is_a_different_name():
    from bench.oracle import same_name
    for a, b in [("Karan", "Kiran"), ("ग्लिंकिट", "Blinkit"), ("Rohit", "Mohit"), ("Tarnaka", "Karnaka")]:
        assert not same_name(a, b), (a, b)
    for a, b in [("Mohammed", "Muhammad"), ("Gachibowli", "Gachibauli"), ("Pooja", "Puja")]:
        assert same_name(a, b), (a, b)


def test_dropping_a_currency_word_next_to_the_same_amount_is_not_damage():
    from bench.oracle import audit_edits
    edits = audit_edits("14500 rupaye", "₹14,500", [{"type": "AMOUNT", "value": "14500"}], [])
    assert edits and all(e["kind"] == "format" for e in edits)


def test_alias_inside_a_labelled_name_is_not_an_invented_entity():
    from bench.oracle import audit_edits
    edits = audit_edits("बजाज फिनसर्व से", "Bajaj Finserv से", [{"type": "ORG", "value": "Bajaj Finserv"}],
                        ["Bajaj", "Bajaj Finserv"])
    assert not [e for e in edits if e["kind"] == "damage"]


def test_telugu_final_anusvara_reads_as_m():
    from bench.oracle import same_name
    assert same_name("మీనాక్షి సుందరం", "Meenakshi Sundaram")


def test_flag_is_credited_by_its_position_in_the_reference():
    from bench.oracle import flag_refers_to
    out, ref = "the flat in Basavanagudi is free today", "the flat in Kadugodi is free today"
    assert flag_refers_to("Basavanagudi", out, ref, "Kadugodi")
    assert not flag_refers_to("flat", "the flat in Kadugodi is free", "the flat in Kadugodi is free", "Kadugodi")


def test_telugu_loanword_spelling_of_bank_is_the_same_name():
    from bench.oracle import same_name
    assert same_name("యూనియన్ బ్యాంక్", "Union Bank")
    assert not same_name("యూనియన్ బ్యాంక్", "Indian Bank")
