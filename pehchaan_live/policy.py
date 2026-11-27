"""Load versioned field, workflow and evidence rules owned by the platform."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from .contracts import Contract, Identifier, Value

TYPES = {"text", "identifier", "phone", "postal_code", "decimal", "date", "time", "enum"}
CONSTRAINTS = {
    "phone": {"region"}, "postal_code": {"region"}, "decimal": {"currency", "max_scale"},
    "enum": {"choices"},
}
NORMALIZATIONS = {
    "text": {"literal", "casefold"}, "identifier": {"literal", "casefold"},
    "enum": {"literal", "casefold"}, "phone": {"literal", "spoken_digits"},
    "postal_code": {"literal", "spoken_digits"}, "decimal": {"literal", "money_format"},
}
POLICY_DIR = Path(__file__).resolve().parents[1] / "data" / "policies"


class FieldRule(Contract):
    type: Identifier
    cues: list[Value] = Field(min_length=1, max_length=12)
    question: Value
    evidence: Literal["transcript", "agreement", "readback"] = "transcript"
    normalization: Identifier = "literal"
    constraints: dict[Identifier, object] = Field(default_factory=dict, max_length=12)
    fallback: Literal["ask", "review"] = "ask"

    @property
    def supported(self) -> bool:
        if self.type not in TYPES or self.normalization not in NORMALIZATIONS.get(self.type, {"literal"}):
            return False
        if self.constraints.keys() - CONSTRAINTS.get(self.type, set()):
            return False
        if self.type == "phone":
            return self.constraints.get("region") in ("IN", "E164")
        if self.type == "postal_code":
            return self.constraints.get("region") == "IN"
        if self.type == "decimal":
            currency, scale = self.constraints.get("currency"), self.constraints.get("max_scale", 2)
            return (isinstance(currency, str) and len(currency) == 3 and currency.isascii()
                    and currency.isalpha() and currency.isupper() and type(scale) is int and 0 <= scale <= 6)
        if self.type == "enum":
            choices = self.constraints.get("choices")
            return (isinstance(choices, list) and 0 < len(choices) <= 32
                    and all(isinstance(choice, str) and 0 < len(choice) <= 240 for choice in choices))
        return True


class ActionRule(Contract):
    required: list[Identifier] = Field(min_length=1, max_length=32)
    optional: list[Identifier] = Field(default_factory=list, max_length=32)
    fallback: Literal["ask", "review"] = "ask"


class Calibration(Contract):
    agreement_for: list[Identifier] = Field(default_factory=list, max_length=32)
    confidence_floors: dict[str, float] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def scoped_confidence(self):
        for key, value in self.confidence_floors.items():
            if len(key.split("/")) != 3 or not all(key.split("/")) or not 0 <= value <= 1:
                raise ValueError("confidence floors require provider/model/version and a value in [0, 1]")
        return self


class Policy(Contract):
    id: Identifier
    version: Identifier
    fields: dict[Identifier, FieldRule] = Field(min_length=1, max_length=32)
    actions: dict[Identifier, ActionRule] = Field(min_length=1, max_length=32)
    steps: dict[Identifier, Identifier] = Field(default_factory=dict, max_length=32)
    defer_phrases: list[Value] = Field(default_factory=list, max_length=40)
    evidence_seconds: int = Field(default=90, ge=1, le=600)
    calibration: Calibration = Field(default_factory=Calibration)

    @model_validator(mode="after")
    def check_references(self):
        field_cues: set[str] = set()
        for rule in self.fields.values():
            cues = {cue.casefold() for cue in rule.cues}
            if len(cues) != len(rule.cues) or cues & field_cues:
                raise ValueError("field cues must uniquely identify a field")
            field_cues |= cues
        for action in self.actions.values():
            names = action.required + action.optional
            if len(names) > 32 or len(set(names)) != len(names) or set(names) - self.fields.keys():
                raise ValueError("action fields must be unique and declared")
        if set(self.steps.values()) - self.actions.keys():
            raise ValueError("a workflow step refers to an unknown action")
        if set(self.calibration.agreement_for) - self.fields.keys():
            raise ValueError("calibration refers to an unknown field")
        return self


def load_policy(path: Path) -> Policy:
    return Policy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=8)
def reference_policy(name: str) -> Policy:
    if name not in {"delivery", "appointment"}:
        raise ValueError(f"unknown reference policy {name}")
    return load_policy(POLICY_DIR / f"{name}.yaml")
