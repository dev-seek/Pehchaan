import pytest

from pehchaan.numbers import find_runs, rules
from pehchaan.text import tokenize


def first_run(text, registry):
    runs = find_runs(tokenize(text), registry)
    assert runs, text
    return runs[0]


@pytest.mark.parametrize("text,value", [
    ("chaudah hazaar paanch sau", 14500), ("चौदह हज़ार पाँच सौ", 14500), ("fourteen thousand five hundred", 14500),
    ("saade teen lakh", 350000), ("dedh lakh", 150000), ("dhai hazaar", 2500), ("1,25,000", 125000),
    ("two lakh fifty thousand", 250000), ("paune do lakh", 175000), ("పద్నాలుగు వేల ఐదు వందలు", 14500),
])
def test_amount_values(registry, text, value):
    assert first_run(text, registry).value_reading == value


@pytest.mark.parametrize("text,digits", [
    ("nine eight four eight zero one two three four five", "9848012345"),
    ("nine eight double four eight zero one two three four", "9844801234"),
    ("ninety eight four eight zero one two three four five", "9848012345"),
    ("98480 12345", "9848012345"),
    ("नौ आठ चार आठ शून्य एक दो तीन चार पाँच", "9848012345"),
    ("नाइन एट फोर एट ज़ीरो वन टू थ्री फोर फाइव", "9848012345"),
])
def test_digit_readings(registry, text, digits):
    assert first_run(text, registry).digit_reading == digits


def test_weak_words_alone_are_not_numbers(registry):
    assert find_runs(tokenize("de do na bhai"), registry) == []


def test_teen_ty(registry):
    assert 14500 in first_run("forty thousand five hundred", registry).teen_ty_alternatives
    assert "14500" in rules.teen_ty_digit_variants("40500")


def test_rules():
    assert rules.format_inr(1450000) == "₹14,50,000" and rules.format_inr(500) == "₹500"
    assert rules.is_mobile("9848012345") and not rules.is_mobile("5848012345")
    assert rules.is_valid_pin("500084", ["500"]) and not rules.is_valid_pin("400050", ["500"])
    assert rules.stutter_repairs("5000084") == {"500084"}
