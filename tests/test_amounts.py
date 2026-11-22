"""Decimals, attached units and 'sawa lakh' are computed exactly, or the caller is asked (D-052)."""

from __future__ import annotations

import pytest

from pehchaan.resolvers.memory import NullMemoryStore
from pehchaan_sdk import CustomTranscriptProvider, Pehchaan


def check(text: str, **context):
    return Pehchaan(CustomTranscriptProvider(), judge=None, memory=NullMemoryStore(), meaning=None).verify_transcript(
        text, context
    )


def amounts(result) -> list[str]:
    return [f.value for f in result.entities if f.type == "AMOUNT" and f.status != "FLAGGED"]


@pytest.mark.parametrize(
    ("text", "value", "shown"),
    [
        ("2.5 lakh transfer kar do", "250000", "₹2,50,000"),
        ("3.75 lakhs ka car loan hai", "375000", "₹3,75,000"),
        ("1.5 cr ka flat hai", "15000000", "₹1,50,00,000"),
        ("Rs 2.5 crore ka plot hai", "25000000", "₹2,50,00,000"),
        ("12.5k ka bill aaya hai", "12500", "₹12,500"),
        ("5k bhej do abhi", "5000", "₹5,000"),
        ("2lakh chahiye mujhe", "200000", "₹2,00,000"),
        ("₹2.5L ka loan hai", "250000", "₹2,50,000"),
        ("Rs 149.50 debit hua", "149.5", "₹149.5"),
        ("one point five lakh rupees", "150000", "1,50,000"),
        ("two point seven five lakh chahiye", "275000", "₹2,75,000"),
        ("sawa lakh ka loan hai", "125000", "₹1,25,000"),
        ("paune lakh ka bill hai", "75000", "₹75,000"),
        ("sawa sau de do", "125", "₹125"),
        ("do hazaar sawa sau dena hai", "2125", "₹2,125"),
    ],
)
def test_the_amount_is_computed_exactly(text, value, shown):
    result = check(text)
    assert amounts(result) == [value]
    assert shown in result.verified_text


@pytest.mark.parametrize(
    "text",
    [
        "version 2.5 install karo",
        "2BHK flat hai",
        "5th floor pe aao",
        "meeting point 5 baje",
        "IP 10.0.0.1 hai",
        "5L petrol dalwa do",
    ],
)
def test_things_that_are_not_money_stay_untouched(text):
    result = check(text)
    assert result.verified_text == text and not amounts(result)


@pytest.mark.parametrize(
    ("text", "value"),
    [("dhai lakh rupaye", "250000"), ("sawa do lakh dena hai", "225000"), ("saade teen hazaar ka bill", "3500")],
)
def test_forms_the_engine_already_reads_keep_their_value(text, value):
    assert amounts(check(text)) == [value]


def test_an_amount_that_cannot_be_read_exactly_keeps_the_words_and_asks():
    text = "saade lakh ka loan hai"
    result = check(text)
    assert result.verified_text == text and not amounts(result)
    assert [f.status for f in result.entities if f.type == "AMOUNT"] == ["FLAGGED"] and result.clarifier_prompt


def test_a_decimal_followed_by_more_number_words_is_a_question():
    text = "2.5 lakh bees hazaar dena hai"
    result = check(text)
    assert result.verified_text == text and not amounts(result)
    assert [f.status for f in result.entities if f.type == "AMOUNT"] == ["FLAGGED"]


def test_a_recomputed_amount_can_match_an_sms():
    result = check("2.5 lakh transfer hua", sms=["Rs 250000 debited"])
    assert [(f.value, f.status) for f in result.entities if f.type == "AMOUNT"] == [("250000", "VERIFIED")]


def test_phones_and_pins_are_never_touched():
    result = check("mera number 98480 12345 hai, pincode 500032")
    assert {(f.type, f.value) for f in result.entities} == {("PHONE", "9848012345"), ("PIN", "500032")}


def test_the_older_process_route_gets_the_same_exact_money(monkeypatch):
    from fastapi.testclient import TestClient

    import app.server as server

    monkeypatch.setattr(server, "_meaning_reader", lambda judge: None)
    response = TestClient(server.app).post("/api/process", data={"text": "2.5 lakh transfer kar do"})
    assert response.status_code == 200
    assert [e["value"] for e in response.json()["pehchaan"]["entities"]] == ["250000"]
