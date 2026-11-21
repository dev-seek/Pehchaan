"""Independent scoring oracle: reads numbers and matches names without the engine's code.

Public API: read_numbers, fact_correct, same_name, loosely_same, name_present, audit_edits, flag_refers_to.
"""
from __future__ import annotations

from .edits import audit_edits, flag_refers_to
from .names import loosely_same, name_present, same_name
from .numbers import NumberFacts, number_fact, read_numbers


def fact_correct(entity: dict, text: str) -> bool:
    """Does text state this labelled entity ({"type", "value"}) correctly?"""
    if entity["type"] in ("PHONE", "PIN", "AMOUNT"):
        return number_fact(entity, text)
    return name_present(str(entity["value"]), text)


__all__ = ["NumberFacts", "audit_edits", "fact_correct", "flag_refers_to", "loosely_same", "name_present", "number_fact",
           "read_numbers", "same_name"]
