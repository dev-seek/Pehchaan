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

from .finish import finish_answer, run_engine
from .judge import KeyedJudge
from .knowledge import Compiled, as_hub
from .meaning import MeaningCheck
from .providers import AudioFile, AudioInput, CustomTranscriptProvider, OpenAIProvider, STTProvider
from .referee import MeaningReferee
from .types import ASRResult, CorrectionResult, Fact, Telemetry, VerifyResult

_AUTO = object()
STATUS_NAMES = {Status.FIXED: "FIXED", Status.CONFIRMED: "VERIFIED", Status.KEPT: "HEARD", Status.FLAGGED: "FLAGGED"}
ASK_FIRST = ("PHONE", "AMOUNT", "PIN", "PLACE", "PERSON", "ORG")  # money and numbers matter most when one question fits
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
    if entity.source == "meaning":
        return "meaning"
    return "numbers" if entity.etype.value in _NUMBERS else "names"


def _with_backers(fact: Fact, known: Compiled | None) -> Fact:
    """Say which company system holds this fact. The engine only knows the six fields the records were compiled into."""
    if known is None or fact.source not in ("context", "rule", "llm"):
        return fact
    names = known.backed_by(fact.type, [fact.value, *fact.options])
    if not names:
        return fact
    label = ", ".join(names)
    if "SMS says" in fact.reason:
        reason = fact.reason.replace("SMS says", f"{label} says")
    elif fact.status == "VERIFIED" and fact.source == "context":
        reason = f"matches the record in {label}"
    elif fact.status == "FIXED":
        reason = f"heard '{fact.heard}', corrected to the record in {label}"
    else:
        reason = fact.reason
    return fact.model_copy(update={"backed_by": names, "reason": reason})


def build_result(
    result: Result,
    *,
    model: str,
    second_model: str | None,
    stt_ms: int,
    judge,
    evidence: str,
    alt_text: str | None = None,
    known: Compiled | None = None,
    meaning: MeaningCheck | None = None,
) -> VerifyResult:
    stages = {k: v for k, v in result.timings_ms.items() if k != "total"}
    facts = [
        _with_backers(
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
            ),
            known,
        )
        for e in result.entities
    ]
    asked = sorted((f for f in facts if f.status == "FLAGGED" and f.question), key=lambda f: ASK_FIRST.index(f.type))
    return VerifyResult(
        verified_text=result.text_out,
        raw_text=result.text_in,
        alt_text=alt_text,
        entities=facts,
        understood=list(meaning.understood) if meaning else [],
        clarifier_prompt=asked[0].question if asked else None,
        telemetry=Telemetry(
            model=model,
            second_opinion_model=second_model,
            stt_ms=stt_ms,
            harness_ms=result.timings_ms["total"],
            stages_ms=stages,
            judge="on" if judge else "off",
            judge_calls=getattr(judge, "requests", 0),
            meaning_calls=meaning.calls if meaning else 0,
            knowledge_ms=known.report.ms if known else 0,
            evidence=evidence,
        ),
        knowledge=known.report if known else None,
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
        knowledge=None,
        meaning=_AUTO,
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
        client = getattr(self.judge, "client", None)
        self.meaning = (MeaningReferee(client) if client is not None else None) if meaning is _AUTO else meaning
        self.memory = memory if memory is not None else JsonMemoryStore(_state_dir() / "memory")
        self.ledger = Path(ledger) if ledger else _state_dir() / "learning.sqlite3"
        self._second = second_opinion
        self._learning = None
        self.knowledge = as_hub(knowledge)  # company systems: evidence for each call, never the truth

    def _default_judge(self):
        if isinstance(self.provider, OpenAIProvider) and self.provider.has_key:
            return KeyedJudge(self.provider.client)
        return None

    def _raw_context(self, extra: dict | None) -> dict:
        merged = {**{k: v for k, v in self.defaults.items() if v is not None}, **(extra or {})}
        user = dict(merged.get("user") or {})
        if merged.get("city"):
            user.setdefault("city", merged["city"])
        if merged.get("user_id"):
            user.setdefault("id", merged["user_id"])
        return {
            "user": user,
            "caller": merged.get("caller"),
            "customer_id": merged.get("customer_id"),
            "domain": merged.get("domain"),
            "contacts": [_contact(c) for c in merged.get("contacts") or []],
            "sms": [_message(m) for m in (merged.get("sms") or merged.get("recent_sms") or [])],
            "places": merged.get("places") or [],
        }

    def _prepare(self, extra: dict | None) -> tuple[CallContext, CallContext, Compiled | None]:
        """(context for the check, context whose names may be sent to the speech model, what company systems added)."""
        raw, level = self._raw_context(extra), settings()["sdk"]["level"]
        if self.knowledge is None:
            ctx = CallContext.build(raw, level)
            return ctx, ctx, None
        known = self.knowledge.gather(raw)
        return CallContext.build(known.context, level), CallContext.build(known.shareable, level), known

    def _judge_for(self, known: Compiled | None):
        return None if known is not None and known.has_private else self.judge  # the LLM would see private names

    def _meaning_for(self, known: Compiled | None):
        return None if known is not None and known.has_private else self.meaning  # the same privacy rule as the judge

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
        file = AudioFile.of(audio)
        ctx, shareable, known = self._prepare(context)
        judge = self._judge_for(known)
        wants_keywords = getattr(self.provider, "supports_keywords", False)
        keywords = shareable.keyword_list(settings()["asr"]["keywords_max"]) if wants_keywords else []
        second = self._second_provider()
        adjustments = {"language": language, "prompt": prompt} if language or prompt else {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            main_job = pool.submit(self.provider.transcribe, file, keywords or None, **adjustments)
            hint = {"language": language} if language else {}
            second_job = pool.submit(second.transcribe, file, None, **hint) if second is not None else None
            main: ASRResult = main_job.result()
            other: ASRResult | None = second_job.result() if second_job else None
        pipeline = build_pipeline(judge=judge, memory=self.memory)
        engine = run_engine(pipeline, main.text, ctx, main.tokens or None, other.text if other else None)
        guarded, meaning = finish_answer(engine, ctx.amounts, self._meaning_for(known), language)
        ran_meaning = meaning.changed or meaning.calls > 0  # the exam did not include this layer
        changed_setup = bool(adjustments) or guarded or ran_meaning or bool(known and known.used)
        return build_result(
            engine,
            model=main.model,
            second_model=other.model if other else None,
            stt_ms=max(main.latency_ms, other.latency_ms if other else 0),
            judge=judge,
            evidence=self._evidence(keywords, second, changed_setup),
            alt_text=other.text if other else None,
            known=known,
            meaning=meaning,
        )

    def verify_transcript(
        self,
        text: str,
        context: dict | None = None,
        alt_text: str | None = None,
        *,
        model: str = "external",
        language: str | None = None,
    ) -> VerifyResult:
        """Wrap the output of any speech model. `alt_text` is an optional second transcript of the same audio."""
        ctx, _, known = self._prepare(context)
        judge = self._judge_for(known)
        engine = run_engine(build_pipeline(judge=judge, memory=self.memory), text, ctx, None, alt_text)
        _, meaning = finish_answer(engine, ctx.amounts, self._meaning_for(known), language)
        return build_result(
            engine,
            model=model,
            second_model="supplied" if alt_text else None,
            stt_ms=0,
            judge=judge,
            evidence="unmeasured",
            alt_text=alt_text,
            known=known,
            meaning=meaning,
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
