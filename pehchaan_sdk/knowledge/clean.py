"""Decide whether one value from a company system is well formed, and give each fact one comparable form."""

from __future__ import annotations

import math
import re

from pehchaan.numbers import rules

AMOUNT_IN_TEXT = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)", re.I)  # the form the engine reads from a message
PIN_IN_TEXT = re.compile(r"(?<!\d)([1-9]\d{5})(?!\d)")
MAX_AMOUNT = 1e9


def fact_key(kind: str, value: str) -> str:
    """One spelling per fact, so "98480 12345" and "+919848012345" count as the same number."""
    if kind in ("PHONE", "PIN"):
        digits = re.sub(r"\D", "", str(value))
        return rules.strip_phone_prefix(digits) if kind == "PHONE" else digits
    if kind == "AMOUNT":
        try:
            return rules.plain_amount(float(re.sub(r"[^\d.]", "", str(value))))
        except ValueError:
            return str(value)
    return " ".join(str(value).casefold().split())


def clean_name(value, limit: int) -> str | None:
    text = " ".join(str(value).split())
    if not text or len(text) > limit or not text.isprintable():
        return None
    if any(ch.isdecimal() for ch in text) or not any(ch.isalpha() for ch in text):
        return None
    return text


def clean_phone(value) -> str | None:
    digits = rules.strip_phone_prefix(re.sub(r"\D", "", str(value)))
    return digits if rules.is_mobile(digits) else None


def clean_pin(value) -> str | None:
    digits = re.sub(r"\D", "", str(value))
    return digits if rules.is_valid_pin(digits, []) else None


def clean_amount(value) -> str | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None
    if not math.isfinite(number) or number <= 0 or number >= MAX_AMOUNT:
        return None
    return rules.plain_amount(number)
