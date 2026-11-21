"""
Pure rules about Indian numbers: validity, formatting, and known speech-recogniser repair patterns.
No I/O, no state: every function is trivially unit-testable.
"""
from __future__ import annotations

import re


def strip_phone_prefix(digits: str) -> str:
    """'919848012345' / '09848012345' -> '9848012345'."""
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits


def is_mobile(digits: str) -> bool:
    """Indian mobile number: 10 digits starting with 6, 7, 8 or 9."""
    return len(digits) == 10 and digits[0] in "6789"


def is_valid_pin(digits: str, city_prefixes: list[str]) -> bool:
    """6 digits, not starting with 0, and (if the city is known) starting with one of its prefixes."""
    return (len(digits) == 6 and digits[0] != "0"
            and (not city_prefixes or any(digits.startswith(p) for p in city_prefixes)))


def format_phone(digits: str) -> str:
    return f"{digits[:5]} {digits[5:]}" if len(digits) == 10 else digits


def plain_amount(value: float) -> str:
    """2500000.0 -> '2500000' (never scientific notation), 1500.5 -> '1500.5'."""
    return str(int(value)) if value == int(value) else repr(value)


def format_inr(value: float, symbol: bool = True) -> str:
    """Indian digit grouping: 1450000 -> '₹14,50,000'."""
    prefix = "₹" if symbol else ""
    if value != int(value):
        return f"{prefix}{value:g}"
    s = str(int(value))
    if len(s) <= 3:
        return prefix + s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return prefix + ",".join(groups + [tail])


def digit_edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def single_deletions(digits: str) -> set[str]:
    return {digits[:i] + digits[i + 1:] for i in range(len(digits))}


def stutter_repairs(digits: str) -> set[str]:
    """Remove one digit of a doubled pair: the most common way an ASR adds a digit ('5000084' -> '500084')."""
    return {digits[:i] + digits[i + 1:] for i in range(1, len(digits)) if digits[i] == digits[i - 1]}


def teen_ty_digit_variants(digits: str) -> list[str]:
    """When the ASR already wrote digits: 40500 <-> 14500 (fourteen / forty confusion in the leading group)."""
    out = []
    m = re.match(r"^([3-9])0(\d*)$", digits)
    if m:
        out.append("1" + m.group(1) + m.group(2))
    m = re.match(r"^1([3-9])(\d*)$", digits)
    if m:
        out.append(m.group(1) + "0" + m.group(2))
    return [o for o in out if o != digits]
