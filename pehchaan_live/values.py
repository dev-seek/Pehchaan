"""Interpret complete caller spans using only the declared normalization."""

import re
import unicodedata
from datetime import date
from decimal import Decimal

from pehchaan.languages import get_registry
from pehchaan.numbers.rules import is_mobile, is_valid_pin
from pehchaan.numbers.spoken import digit_reading
from pehchaan.text.normalize import tokenize

from .policy import FieldRule

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,63}")
INTERNATIONAL_PHONE = re.compile(r"\+[1-9][0-9]{7,14}")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
TIME = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
MONEY = re.compile(r"([A-Z]{3}) ([0-9]{1,15}(?:\.[0-9]{1,6})?)")
GROUPED_INR = re.compile(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})+,[0-9]{3})(?:\.[0-9]{1,6})?")


def _digits(value: str) -> str:
    if re.fullmatch(r"[0-9]+(?: [0-9]+)*", value):
        return value.replace(" ", "")
    if not all(char.isalpha() or char.isspace() or unicodedata.category(char).startswith("M") for char in value):
        return ""
    tokens = tokenize(value)
    registry = get_registry()
    words = [token.norm for token in tokens]
    repeat = False
    for word in words:
        if registry.repeater(word) and not repeat:
            repeat = True
            continue
        digit = registry.number_value(word)
        if digit is None or digit > 9:
            return ""
        repeat = False
    return digit_reading(words, registry) if not repeat else ""


def _number(value: str, rule: FieldRule, is_spoken: bool) -> str | None:
    if rule.constraints["region"] == "E164":
        return value if INTERNATIONAL_PHONE.fullmatch(value) else None
    if is_spoken and rule.normalization == "spoken_digits":
        value = _digits(value)
    if not re.fullmatch(r"[0-9]+", value):
        return None
    valid = is_mobile(value) if rule.type == "phone" else is_valid_pin(value, [])
    return value if valid else None


def _money(value: str, rule: FieldRule, is_spoken: bool) -> str | None:
    if is_spoken and rule.normalization == "money_format" and rule.constraints["currency"] == "INR":
        if value.startswith("₹"):
            value = "INR " + value[1:].lstrip()
        if value.startswith("INR ") and GROUPED_INR.fullmatch(value[4:]):
            value = value.replace(",", "")
    match = MONEY.fullmatch(value)
    if not match or match[1] != rule.constraints["currency"]:
        return None
    if len(match[2].partition(".")[2]) > rule.constraints.get("max_scale", 2):
        return None
    return f"{match[1]} {format(Decimal(match[2]).normalize(), 'f')}"


def _date(value: str) -> str | None:
    if DATE.fullmatch(value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    return None


def _text(value: str) -> bool:
    return (any(char.isalnum() for char in value)
            and all(char.isalnum() or char in " '-’." or unicodedata.category(char).startswith("M") for char in value))


def canonical(value: str, rule: FieldRule, *, is_spoken: bool = False) -> str | None:
    if not rule.supported or not 0 < len(value) <= 240:
        return None
    if is_spoken:
        value = value.strip()
    elif value != value.strip():
        return None
    if rule.normalization == "casefold":
        value = value.casefold()
    match rule.type:
        case "phone" | "postal_code":
            return _number(value, rule, is_spoken)
        case "decimal":
            return _money(value, rule, is_spoken)
        case "date":
            return _date(value)
        case "time":
            return value if TIME.fullmatch(value) else None
        case "identifier":
            return value if IDENTIFIER.fullmatch(value) else None
        case "enum":
            choices = rule.constraints["choices"]
            if rule.normalization == "casefold":
                choices = [choice.casefold() for choice in choices]
            return value if value in choices else None
        case "text":
            return value if _text(value) else None
    return None
