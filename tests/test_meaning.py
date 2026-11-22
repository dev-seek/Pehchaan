"""A word that can be a number is only money if the conversation means money (D-051)."""

from __future__ import annotations

import pytest

from pehchaan.resolvers.memory import NullMemoryStore
from pehchaan_sdk import CustomTranscriptProvider, Pehchaan
from pehchaan_sdk.meaning import is_rejected, without_rejected

TELUGU_FAMILY = "మా తమ్ముళ్లు... పేరు కోటి అండ్ పల్లవి."
HINDI_FAMILY = "I have two brothers, एक का नाम अनुराग है और दूसरे वाले का नाम लाख है।"


class Reader:
    """Stands in for the LLM. Answers by the word, and records what it was asked."""

    def __init__(self, answers: dict[str, str] | None = None, fail: bool = False):
        self.answers, self.fail, self.asked, self.requests = answers or {}, fail, [], 0

    def read(self, text: str, words: list[str]) -> dict[int, dict]:
        self.requests += 1
        self.asked.append((text, words))
        if self.fail:
            raise TimeoutError("no answer")
        return {
            i: {
                "meaning": "other" if self.answers.get(w) == "same" else self.answers.get(w, "unsure"),
                "same_as_suggestion": self.answers.get(w) == "same",
                "reason": "from the conversation",
            }
            for i, w in enumerate(words)
        }


class RejectingJudge:
    """The engine's judge, turning down every candidate."""

    requests = 0

    def decide(self, sentence, span, etype, options, confidence):
        from pehchaan.judge.verifier import JudgeDecision

        self.requests += 1
        return JudgeDecision("keep", "not an entity")


def check(text: str, reader: Reader | None = None, judge=None, **context):
    sdk = Pehchaan(CustomTranscriptProvider(), judge=judge, memory=NullMemoryStore(), meaning=reader)
    return sdk.verify_transcript(text, context)


def amounts(result) -> list[str]:
    return [f.value for f in result.entities if f.type == "AMOUNT"]


@pytest.mark.parametrize(
    ("text", "word", "meaning", "fact"),
    [
        (TELUGU_FAMILY, "కోటి", "person", "PERSON"),
        (HINDI_FAMILY, "लाख", "person", "PERSON"),
        ("my brother's name is Crore", "Crore", "person", "PERSON"),
        ("Sau Bhagya mera dost hai", "Sau", "person", "PERSON"),
        ("main Koti mein hoon, wahan aa jao", "Koti", "place", "PLACE"),
        ("Koti bus stop pe milte hain", "Koti", "place", "PLACE"),
        ("నేను కోటి లో ఉన్నాను, అక్కడికి రా", "కోటి", "place", "PLACE"),
        ("hazaar baar bola hai tumhe", "hazaar", "other", None),
        ("lakh samjhaya par wo nahi maana", "lakh", "other", None),
    ],
)
def test_a_name_or_a_saying_never_becomes_money(text, word, meaning, fact):
    result = check(text, Reader({word: meaning}))
    assert result.verified_text == text
    assert not amounts(result) and result.clarifier_prompt is None
    found = [f for f in result.entities if f.heard == word]
    assert [f.type for f in found] == ([fact] if fact else [])
    assert all(f.status == "HEARD" and f.value == word for f in found)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("mujhe ek lakh rupaye transfer karne hain", "100000"),
        ("paanch hazaar bhej do", "5000"),
        ("loan ek crore ka chahiye", "10000000"),
        ("lakh rupaye ka loan chahiye", "100000"),
        ("కోటి రూపాయలు లోన్ కావాలి", "10000000"),
        ("refund of 2500 rupees please", "2500"),
        ("teen hazaar paanch sau dena hai", "3500"),
    ],
)
@pytest.mark.parametrize("reader", [None, Reader({})], ids=["no_llm", "llm"])
def test_real_money_is_read_exactly_as_before(text, value, reader):
    plain = Pehchaan(CustomTranscriptProvider(), judge=None, memory=NullMemoryStore(), meaning=None)
    assert amounts(check(text, reader)) == [value]
    assert check(text, reader).verified_text == plain.verify_transcript(text).verified_text


def test_the_llm_is_not_called_when_the_words_already_settle_it():
    reader = Reader({})
    check("mujhe ek lakh rupaye transfer karne hain", reader)
    check("lakh rupaye ka loan chahiye", reader)
    check("mera number 98480 12345 hai", reader)
    assert reader.requests == 0


def test_the_llm_can_keep_a_lone_word_as_money():
    result = check("lakh de do usko", Reader({"lakh": "money"}))
    assert amounts(result) == ["100000"] and "₹1,00,000" in result.verified_text


def test_all_words_go_in_one_llm_call_and_each_is_marked_where_it_was_said():
    reader = Reader({"Koti": "person", "lakh": "other"})
    check("Koti ne kaha lakh samjhaya", reader)
    assert reader.requests == 1
    text, words = reader.asked[0]
    assert words == ["Koti", "lakh"] and "[[0: Koti]]" in text and "[[1: lakh]]" in text


@pytest.mark.parametrize("reader", [None, Reader(fail=True)], ids=["no_llm", "llm_failed"])
def test_without_an_answer_the_words_stay_and_no_money_is_claimed(reader):
    result = check(TELUGU_FAMILY, reader)
    assert result.verified_text == TELUGU_FAMILY and not amounts(result)


@pytest.mark.parametrize("reader", [None, Reader(fail=True)], ids=["no_llm", "llm_failed"])
def test_without_an_answer_a_nearby_money_word_raises_a_question(reader):
    text = "lakh ka loan chahiye"
    result = check(text, reader)
    assert result.verified_text == text
    assert [(f.type, f.status, f.value) for f in result.entities] == [("AMOUNT", "FLAGGED", "lakh")]
    assert result.clarifier_prompt


def test_when_the_llm_is_unsure_it_asks_and_keeps_the_words():
    text = "usko lakh de do"
    result = check(text, Reader({"lakh": "unsure"}))
    assert result.verified_text == text
    assert [(f.status, f.value) for f in result.entities] == [("FLAGGED", "lakh")] and result.clarifier_prompt


def test_a_candidate_the_judge_rejected_is_not_reported_as_a_fact():
    text = "nuvvu ekkada unnav"
    result = check(text, judge=RejectingJudge())
    assert result.verified_text == text and result.entities == []


class ChoosingJudge:
    """The engine's judge, accepting the first candidate from a global list."""

    requests = 0

    def decide(self, sentence, span, etype, options, confidence):
        from pehchaan.judge.verifier import JudgeDecision

        self.requests += 1
        return JudgeDecision("cand1", "sounds close")


def test_a_real_place_is_not_rewritten_into_a_brand_that_sounds_like_it():
    text = "main Delhi se bol raha hoon"
    assert "Delhivery" in check(text, judge=ChoosingJudge()).verified_text
    result = check(text, Reader({"Delhi": "place"}), judge=ChoosingJudge())
    assert result.verified_text == text
    fact = result.entities[0]
    assert (fact.status, fact.value, fact.options) == ("FLAGGED", "Delhi", ["Delhivery"]) and result.clarifier_prompt


@pytest.mark.parametrize(
    "reader", [None, Reader(fail=True), Reader({"Delhi": "same"})], ids=["none", "failed", "agrees"]
)
def test_a_correction_stands_unless_the_call_clearly_means_the_heard_word(reader):
    assert "Delhivery" in check("main Delhi se bol raha hoon", reader, judge=ChoosingJudge()).verified_text


def test_rejected_facts_are_hidden_in_packaged_answers_without_touching_anything_else():
    keep = {"etype": "PERSON", "status": "KEPT", "source": "rule", "surface": "Ravi"}
    junk = {"etype": "ORG", "status": "KEPT", "source": "llm", "surface": "भर"}
    money = {"etype": "AMOUNT", "status": "KEPT", "source": "llm", "surface": "lakh"}
    assert is_rejected(junk) and not is_rejected(keep) and not is_rejected(money)
    packaged = {"main": {"text": "same", "entities": [junk, keep, money], "silent": 2}}
    assert without_rejected(packaged) == {"main": {"text": "same", "entities": [keep, money], "silent": 2}}


def test_time_spent_on_meaning_is_reported():
    result = check(TELUGU_FAMILY, Reader({"కోటి": "person"}))
    assert result.telemetry.meaning_calls == 1
    assert "meaning" in result.telemetry.stages_ms
    assert result.telemetry.harness_ms >= result.telemetry.stages_ms["meaning"]


def test_a_changed_answer_never_claims_exam_evidence():
    from pehchaan import CallContext, build_pipeline
    from pehchaan.config import settings
    from pehchaan_sdk.meaning import check_meaning

    engine = build_pipeline(judge=None, memory=NullMemoryStore()).run(
        TELUGU_FAMILY, CallContext.build({}, settings()["sdk"]["level"])
    )
    assert check_meaning(engine, Reader({"కోటి": "person"})).changed is True
    untouched = build_pipeline(judge=None, memory=NullMemoryStore()).run(
        "mera number 98480 12345 hai", CallContext.build({}, "C3")
    )
    assert check_meaning(untouched, Reader({})).changed is False
