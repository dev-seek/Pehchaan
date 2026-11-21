"""A confirmed correction becomes automatic only if it survives the learning gate."""
from __future__ import annotations

import pytest

from bench.learning import Candidate, LearningLoop, evaluate, replay
from pehchaan.resolvers import JsonMemoryStore

CONTEXT = {"user": {"id": "u", "city": "Hyderabad"}}
CLIP = {"clip_id": "c1", "text": "parcel Kothaguda pahunch gaya, delivery kal hogi", "level": "C0", "context": CONTEXT,
        "second_opinion": None, "entities": [{"type": "PLACE", "value": "Kothaguda"}], "reference": "parcel Kothaguda"}
CALL = {"text": "parcel Kondaapoor pahunch gaya", "level": "C0", "context": CONTEXT, "second_opinion": None}
GOOD = ("Kondaapoor", "Kondapur", "PLACE")


@pytest.fixture
def loop(tmp_path):
    return LearningLoop(JsonMemoryStore(tmp_path / "memory"), tmp_path / "ledger.sqlite3", corpus=[CLIP])


def failed(verdict):
    return {c["name"] for c in verdict["checks"] if c["passed"] is False}


def test_a_good_correction_is_adopted_and_used(loop):
    verdict = loop.propose("u", *GOOD, call=CALL)
    assert verdict["adopted"] and verdict["clips_replayed"] == 1 and verdict["facts_harmed"] == 0
    assert loop.store.load("u")[0]["canonical"] == "Kondapur"


def test_numbers_can_never_be_learned(loop):
    verdict = loop.propose("u", "14500", "40500", "AMOUNT")
    assert not verdict["adopted"] and "learnable_type" in failed(verdict) and loop.store.load("u") == []


def test_everyday_word_is_refused(loop):
    verdict = loop.propose("u", "delivery", "Delhivery", "ORG")
    assert not verdict["adopted"] and "not_everyday_word" in failed(verdict)


def test_a_tap_on_an_unrelated_name_is_refused(loop):
    verdict = loop.propose("u", "Kondaapoor", "Neha Agarwal", "PLACE")
    assert not verdict["adopted"] and "sounds_alike" in failed(verdict)


def test_a_correction_that_harms_a_labelled_call_is_refused():
    clip = {**CLIP, "text": "parcel Chandapur pahunch gaya", "entities": [{"type": "PLACE", "value": "Chandapur"}]}
    harmful = Candidate("Chandapur", "Chandanagar", "PLACE")     # the heard place is in no list, so only replay can catch it
    verdict = evaluate(harmful, [], [clip])
    assert not verdict["adopted"] and "no_regression" in failed(verdict) and verdict["facts_harmed"] == 1


def test_a_correction_that_does_not_apply_to_the_call_is_refused(loop):
    verdict = loop.propose("u", "Banjaara", "Banjara", "PLACE", call=CALL)
    assert not verdict["adopted"] and "repairs_this_call" in failed(verdict)


def test_conflicting_memory_must_be_undone_first(loop):
    assert loop.propose("u", *GOOD, call=CALL)["adopted"]
    verdict = loop.propose("u", "Kondaapoor", "Kondapuram", "PLACE", call=CALL)
    assert not verdict["adopted"] and "no_conflict" in failed(verdict)


def test_no_corpus_means_no_adoption(tmp_path):
    empty = LearningLoop(JsonMemoryStore(tmp_path / "m"), tmp_path / "l.sqlite3", corpus=[])
    assert not empty.propose("u", *GOOD)["adopted"]


def test_rollback_removes_the_memory_and_keeps_the_history(loop):
    event = loop.propose("u", *GOOD, call=CALL)["event_id"]
    loop.rollback("u", event)
    assert loop.store.load("u") == []
    history = loop.history("u")
    assert [h["decision"] for h in history] == ["rolled_back", "adopted"] and not history[1]["active"]
    with pytest.raises(KeyError):
        loop.rollback("u", event)


def test_one_user_cannot_roll_back_another_users_memory(loop):
    event = loop.propose("u", *GOOD, call=CALL)["event_id"]
    with pytest.raises(KeyError):
        loop.rollback("someone-else", event)
    assert loop.store.load("u")


def test_shipped_corpus_is_dev_only():
    from bench.learning import load_corpus
    corpus = load_corpus()
    assert corpus and all(c["clip_id"].startswith("dev_") for c in corpus)


def _say(second_opinion):
    clip = {"text": "flat Kondapur mein hai", "level": "C2", "context": CONTEXT, "second_opinion": second_opinion}
    return replay(clip, [Candidate("Kondapur", "Kothaguda", "PLACE").entry()])[0]


def test_a_learned_fix_cannot_erase_a_real_place_the_caller_said():
    result = _say("flat Kondapur mein hai")
    assert "Kondapur" in result.text_out and "Kothaguda" not in result.text_out
    assert any(r["rule"] == "known_name_heard" for r in result.refused)


def test_a_learned_fix_on_a_known_name_needs_independent_evidence():
    assert "Kothaguda" not in _say(None).text_out


def test_a_learned_fix_still_repairs_a_context_echo():
    assert "Kothaguda" in _say("flat Thadugoda mein hai").text_out
