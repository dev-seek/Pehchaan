"""
The one object an application needs.

    from pehchaan_sdk import Pehchaan
    p = Pehchaan(city="Hyderabad", contacts=[{"name": "Ravi Kumar", "number": "9848012345"}])
    result = p.verify_transcript("text from any speech model")

The engine underneath is the frozen `pehchaan` package. This file only feeds it and shapes its answer.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pehchaan import CallContext, Result, Status, build_pipeline
from pehchaan.config import settings
from pehchaan.resolvers import JsonMemoryStore

from .judge import KeyedJudge
from .providers import AudioFile, AudioInput, CustomTranscriptProvider, OpenAIProvider, STTProvider
from .types import ASRResult, CorrectionResult, Fact, Telemetry, VerifyResult

_AUTO = object()
STATUS_NAMES = {Status.FIXED: "FIXED", Status.CONFIRMED: "VERIFIED", Status.KEPT: "HEARD", Status.FLAGGED: "FLAGGED"}
ASK_FIRST = (
    "PHONE",
    "AMOUNT",
    "PIN",
    "PLACE",
    "PERSON",
    "ORG",
)  # money and numbers matter most when only one question fits
_NUMBERS = frozenset({"PHONE", "PIN", "AMOUNT"})


def _state_dir() -> Path:
    return Path(settings()["sdk"]["state_dir"]).expanduser()


def _contact(item) -> dict:
    return {"name": item} if isinstance(item, str) else dict(item)


def _message(item) -> dict:
    return {"sender": "", "body": item} if isinstance(item, str) else dict(item)


def _stage(entity) -> str:
    if entity.source == "memory":
        return "memory"
    return "numbers" if entity.etype.value in _NUMBERS else "names"


def build_result(
    result: Result,
    *,
    model: str,
    second_model: str | None,
    stt_ms: int,
    judge,
    evidence: str,
    alt_text: str | None = None,
) -> VerifyResult:
    stages = {k: v for k, v in result.timings_ms.items() if k != "total"}
    facts = [
        Fact(
            type=e.etype.value,
            status=STATUS_NAMES[e.status],
            heard=e.surface,
            value=str(e.value),
            reason=e.reason,
            source=e.source,
            latency_ms=stages.get(_stage(e)),
            question=e.clarifier,
            options=[c["text"] for c in e.candidates] if e.status == Status.FLAGGED else [],
        )
        for e in result.entities
    ]
    asked = sorted((f for f in facts if f.status == "FLAGGED" and f.question), key=lambda f: ASK_FIRST.index(f.type))
    return VerifyResult(
        verified_text=result.text_out,
        raw_text=result.text_in,
        alt_text=alt_text,
        entities=facts,
        clarifier_prompt=asked[0].question if asked else None,
        telemetry=Telemetry(
            model=model,
            second_opinion_model=second_model,
            stt_ms=stt_ms,
            harness_ms=result.timings_ms["total"],
            stages_ms=stages,
            judge="on" if judge else "off",
            judge_calls=getattr(judge, "requests", 0),
            evidence=evidence,
        ),
    )


class Pehchaan:
    """Verify facts in a call transcript. Phone numbers, PINs and money are never changed, only flagged."""

    def __init__(
        self,
        provider: STTProvider | None = None,
        *,
        city: str | None = None,
        contacts: list | None = None,
        recent_sms: list | None = None,
        places: list[str] | None = None,
        caller: dict | None = None,
        domain: str | None = None,
        user_id: str | None = None,
        judge=_AUTO,
        memory=None,
        ledger: Path | None = None,
        second_opinion: STTProvider | None = None,
    ):
        self.provider = provider if provider is not None else OpenAIProvider()
        self.defaults = {
            "city": city,
            "contacts": contacts,
            "recent_sms": recent_sms,
            "places": places,
            "caller": caller,
            "domain": domain,
            "user_id": user_id,
        }
        self.judge = self._default_judge() if judge is _AUTO else judge
        self.memory = memory if memory is not None else JsonMemoryStore(_state_dir() / "memory")
        self.ledger = Path(ledger) if ledger else _state_dir() / "learning.sqlite3"
        self._second = second_opinion
        self._learning = None

    def _default_judge(self):
        if isinstance(self.provider, OpenAIProvider) and self.provider.has_key:
            return KeyedJudge(self.provider.client)
        return None

    def _context(self, extra: dict | None) -> CallContext:
        merged = {**{k: v for k, v in self.defaults.items() if v is not None}, **(extra or {})}
        user = dict(merged.get("user") or {})
        if merged.get("city"):
            user.setdefault("city", merged["city"])
        if merged.get("user_id"):
            user.setdefault("id", merged["user_id"])
        raw = {
            "user": user,
            "caller": merged.get("caller"),
            "domain": merged.get("domain"),
            "contacts": [_contact(c) for c in merged.get("contacts") or []],
            "sms": [_message(m) for m in (merged.get("sms") or merged.get("recent_sms") or [])],
            "places": merged.get("places") or [],
        }
        return CallContext.build(raw, settings()["sdk"]["level"])

    def _second_provider(self) -> STTProvider | None:
        if self._second is not None:
            return self._second
        return self.provider.second_opinion() if isinstance(self.provider, OpenAIProvider) else None

    def _evidence(self, keywords: list[str], second: STTProvider | None, adjusted: bool) -> str:
        if not isinstance(self.provider, OpenAIProvider) or second is None or adjusted or self._second is not None:
            return "unmeasured"
        return self.provider.profile["evidence"] if keywords or not self.provider.supports_keywords else "unmeasured"

    def verify_audio(
        self, audio: AudioInput, context: dict | None = None, *, language: str | None = None, prompt: str | None = None
    ) -> VerifyResult:
        """Run the chosen speech model, then the frozen harness."""
        file, ctx = AudioFile.of(audio), self._context(context)
        wants_keywords = getattr(self.provider, "supports_keywords", False)
        keywords = ctx.keyword_list(settings()["asr"]["keywords_max"]) if wants_keywords else []
        second = self._second_provider()
        adjustments = {"language": language, "prompt": prompt} if language or prompt else {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            main_job = pool.submit(self.provider.transcribe, file, keywords or None, **adjustments)
            second_job = pool.submit(second.transcribe, file, None) if second is not None else None
            main: ASRResult = main_job.result()
            other: ASRResult | None = second_job.result() if second_job else None
        engine = build_pipeline(judge=self.judge, memory=self.memory).run(
            main.text, ctx, main.tokens or None, other.text if other else None
        )
        return build_result(
            engine,
            model=main.model,
            second_model=other.model if other else None,
            stt_ms=max(main.latency_ms, other.latency_ms if other else 0),
            judge=self.judge,
            evidence=self._evidence(keywords, second, bool(adjustments)),
            alt_text=other.text if other else None,
        )

    def verify_transcript(
        self, text: str, context: dict | None = None, alt_text: str | None = None, *, model: str = "external"
    ) -> VerifyResult:
        """Wrap the output of any speech model. `alt_text` is an optional second transcript of the same audio."""
        engine = build_pipeline(judge=self.judge, memory=self.memory).run(text, self._context(context), None, alt_text)
        return build_result(
            engine,
            model=model,
            second_model="supplied" if alt_text else None,
            stt_ms=0,
            judge=self.judge,
            evidence="unmeasured",
            alt_text=alt_text,
        )

    def confirm_correction(
        self, user_id: str, heard: str, corrected: str, entity_type: str, call: dict | None = None
    ) -> CorrectionResult:
        """A human confirmed a name. It is remembered only if it passes the verified-learning checks (D-029)."""
        if self._learning is None:
            from bench.learning import LearningLoop

            self._learning = LearningLoop(self.memory, self.ledger)
        verdict = self._learning.propose(user_id, heard, corrected, entity_type, call)
        return CorrectionResult(
            adopted=verdict["adopted"],
            heard=heard,
            corrected=corrected,
            entity_type=entity_type,
            checks=verdict["checks"],
            event_id=verdict["event_id"],
        )


__all__ = ["CustomTranscriptProvider", "OpenAIProvider", "Pehchaan", "build_result"]
