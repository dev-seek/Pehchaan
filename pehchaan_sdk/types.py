"""The typed answers the SDK and the REST API return. No logic lives here."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .knowledge.records import KnowledgeReport

FactStatus = Literal["FIXED", "VERIFIED", "HEARD", "FLAGGED"]
FactType = Literal["PERSON", "ORG", "PLACE", "PHONE", "PIN", "AMOUNT"]
Evidence = Literal["exam", "dev", "unmeasured"]


class ASRResult(BaseModel):
    """What any speech-to-text model must give back."""

    text: str
    tokens: list[dict] = Field(default_factory=list, description="Optional per-token confidences")
    model: str = "external"
    latency_ms: int = 0


class Fact(BaseModel):
    type: FactType
    status: FactStatus = Field(
        description="FIXED changed it. VERIFIED matched independent evidence. "
        "HEARD left it as transcribed with no evidence. FLAGGED needs a question."
    )
    heard: str = Field(description="What the speech model wrote")
    value: str = Field(description="The final value")
    reason: str
    source: str
    latency_ms: float | None = Field(default=None, description="Time of the engine stage that decided this fact")
    question: str | None = None
    options: list[str] = Field(default_factory=list)
    backed_by: list[str] = Field(default_factory=list, description="Connected company systems that hold this fact")


class Telemetry(BaseModel):
    model: str
    second_opinion_model: str | None = None
    stt_ms: int = 0
    harness_ms: float = 0
    stages_ms: dict[str, float] = Field(default_factory=dict)
    judge: Literal["on", "off"] = "off"
    judge_calls: int = 0
    knowledge_ms: float = Field(default=0, description="Time spent asking connected company systems")
    evidence: Evidence = Field(
        description="exam: this exact setup sat the locked exam. dev: measured on development "
        "clips only. unmeasured: no benchmark covers this setup."
    )


class VerifyResult(BaseModel):
    verified_text: str
    raw_text: str
    alt_text: str | None = Field(default=None, description="The second transcript, when one was used")
    entities: list[Fact]
    clarifier_prompt: str | None = Field(default=None, description="One short question, ready for TTS or a voice agent")
    telemetry: Telemetry
    call_id: str | None = Field(default=None, description="Set when the hosted API saved this call for a named caller")
    knowledge: KnowledgeReport | None = Field(default=None, description="What each connected company system contributed")


class CorrectionResult(BaseModel):
    adopted: bool = Field(description="True only if every safety check and the replay passed")
    heard: str
    corrected: str
    entity_type: str
    checks: list[dict]
    event_id: int | None = None
