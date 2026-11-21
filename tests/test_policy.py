"""The admission gate's promises, tested at the boundary: even a buggy resolver cannot break them."""
import pytest

from pehchaan import CallContext
from pehchaan.languages import get_registry
from pehchaan.models import Entity, EType, Status
from pehchaan.pipeline import Pipeline

from .conftest import by_type


class RogueResolver:
    """Simulates a resolver bug: it silently replaces whatever number it finds."""
    name = "rogue"

    def __init__(self, etype, heard, proposed, status=Status.FIXED):
        self.etype, self.heard, self.proposed, self.status = etype, heard, proposed, status

    def resolve(self, utt, ctx, claimed):
        i = next(k for k, t in enumerate(utt.tokens) if t.raw == self.heard)
        return [Entity(etype=self.etype, surface=self.heard, start_tok=i, end_tok=i + 1, value=self.proposed,
                       heard_value=self.heard, display=self.proposed, status=self.status, source="context",
                       reason="rogue")]


@pytest.mark.parametrize("etype,heard,proposed", [(EType.PHONE, "9848012345", "9848012346"),
                                                  (EType.PIN, "500084", "500081"), (EType.AMOUNT, "40500", "14500")])
@pytest.mark.parametrize("status", [Status.FIXED, Status.CONFIRMED, Status.KEPT])
def test_gate_blocks_any_change_to_a_critical_value(etype, heard, proposed, status):
    pipe = Pipeline([RogueResolver(etype, heard, proposed, status)], get_registry())
    r = pipe.run(f"value {heard} here", CallContext.build({}, "C0"))
    assert heard in r.text_out and proposed not in r.text_out
    assert r.entities[0].status == Status.FLAGGED and r.entities[0].value == heard
    assert r.refused and r.refused[0]["rule"] == "critical_read_only"


def test_critical_proposal_without_a_heard_value_fails_fast():
    class Broken(RogueResolver):
        def resolve(self, utt, ctx, claimed):
            found = super().resolve(utt, ctx, claimed)
            found[0].heard_value = None
            return found
    with pytest.raises(ValueError, match="heard_value"):
        Pipeline([Broken(EType.PHONE, "9848012345", "9848012346")], get_registry()).run(
            "value 9848012345 here", CallContext.build({}, "C0"))


DELIVERY = {"user": {"id": "u", "city": "Hyderabad"}, "sms": [{"sender": "VM-DELHVY", "body": "Out for delivery"}]}


@pytest.mark.parametrize("text", ["कैश ऑन डिलीवरी", "डिलीवरी ब्वॉय आ गया", "your parcel was delivered today"])
def test_common_word_never_becomes_a_brand(run, text):
    r = run(text, context=DELIVERY)
    assert "Delhivery" not in r.text_out and "ORG" not in by_type(r)


def test_brand_homophone_allowed_with_call_evidence_in_entity_position(run):
    r = run("मैं डिलीवरी से बोल रहा हूँ", context=DELIVERY)
    assert by_type(r)["ORG"].value == "Delhivery"


def test_same_homophone_without_call_evidence_stays_a_word(run):
    r = run("मैं डिलीवरी से बोल रहा हूँ", context={"user": {"id": "u", "city": "Hyderabad"}})
    assert "Delhivery" not in r.text_out


def test_acronym_brand_needs_its_spelled_letters(run):
    context = {"user": {"id": "u", "city": "Hyderabad"}, "sms": [{"sender": "VM-LICIND", "body": "Premium due"}]}
    assert "LIC" not in run("एड्रेस लिख लीजिए", context=context).text_out
    assert by_type(run("मैं एलआईसी से बोल रहा हूँ", context=context))["ORG"].value == "LIC"


def test_place_is_not_replaced_by_an_unrelated_contact(run):
    context = {"user": {"id": "u", "city": "Hyderabad"}, "contacts": [{"name": "Neha Agarwal"}],
               "places": ["Narayanguda"]}
    r = run("मैं नारायणगुड़ा वाले फ्लैट के लिए", context=context)
    assert "Neha" not in r.text_out and by_type(r).get("PLACE") is not None


@pytest.mark.parametrize("text", ["mera number 98480123 hai", "phone number 984801234567 hai"])
def test_wrong_phone_length_is_asked_and_never_altered(run, text):
    r = run(text)
    assert by_type(r)["PHONE"].status == Status.FLAGGED and r.text_out == text and r.questions


@pytest.mark.parametrize("text", ["pin code 50008 hai", "pin code 5000812 hai"])
def test_wrong_pin_length_is_asked_and_never_altered(run, text):
    r = run(text)
    assert by_type(r)["PIN"].status == Status.FLAGGED and r.text_out == text and r.questions


@pytest.mark.parametrize("text,etype", [("नंबर 4155 A00800", "PHONE"), ("mera number A00800 hai", "PHONE"),
                                         ("मेरा नंबर है", "PHONE"), ("pin code hai", "PIN")])
def test_cue_without_a_readable_number_asks(run, text, etype):
    r = run(text)
    assert by_type(r)[etype].status == Status.FLAGGED and r.text_out == text and r.questions


def test_cue_in_an_ordinary_sentence_does_not_ask(run):
    assert run("mera number aapke paas pehle se save hai").questions == []


def test_unknown_word_before_a_multiplier_is_asked_not_rewritten(run):
    text = "EMI जुगनू हज़ार सात सौ रुपये"
    r = run(text)
    assert by_type(r)["AMOUNT"].status == Status.FLAGGED and r.text_out == text


def test_hindi_spelling_variant_reads_the_full_amount(run):
    assert by_type(run("EMI चौदा हज़ार सात सौ पचास रुपये"))["AMOUNT"].value == "14750"


@pytest.mark.parametrize("etype", ["PHONE", "PIN", "AMOUNT"])
def test_memory_refuses_to_learn_a_number(memory, etype):
    with pytest.raises(ValueError, match="read-only"):
        memory.remember("u", "40500", "14500", etype)


def test_ambiguous_question_is_three_words(run):
    context = {"user": {"id": "u"}, "contacts": [{"name": "Venkatesh"}, {"name": "Venkataraman"}]}
    question = by_type(run("main Venkat bol raha hoon", context=context))["PERSON"].clarifier
    assert len(question.split()) == 3 and "Venkatesh" in question and "Venkataraman" in question


def test_brand_made_of_common_words_survives_when_the_whole_phrase_matches(run):
    context = {"user": {"id": "u", "city": "Hyderabad"}}
    assert by_type(run("main Yes Bank se bol raha hoon", context=context))["ORG"].value == "Yes Bank"


def _with_opinion(text, opinion, context, memory):
    from pehchaan import build_pipeline
    return build_pipeline(memory=memory).run(text, CallContext.build(context, "C3"), second_opinion=opinion)


KADUGODI = {"user": {"id": "u", "city": "Bengaluru"}, "places": ["Basavanagudi"]}


def test_context_echo_is_asked_when_a_context_free_transcript_heard_something_else(memory):
    r = _with_opinion("the flat in Basavanagudi is free", "the flat in Kadugodi is free", KADUGODI, memory)
    assert by_type(r)["PLACE"].status == Status.FLAGGED and by_type(r)["PLACE"].admission == "second_opinion"


def test_name_is_confirmed_when_both_transcripts_heard_it(memory):
    r = _with_opinion("the flat in Basavanagudi is free", "the flat in बसवनगुडी is free", KADUGODI, memory)
    assert by_type(r)["PLACE"].status == Status.CONFIRMED


def test_transcripts_disagreeing_on_an_amount_ask_and_keep_the_heard_value(memory):
    r = _with_opinion("EMI 14725 rupaye hai", "EMI 14750 rupaye hai", {"user": {"id": "u"}}, memory)
    amount = by_type(r)["AMOUNT"]
    assert amount.status == Status.FLAGGED and amount.value == "14725" and "14725" in r.text_out
    assert amount.candidates[0]["text"] == "14750"


def test_transcripts_agreeing_on_a_number_stay_quiet(memory):
    r = _with_opinion("EMI 14,725 rupaye hai", "EMI चौदह हज़ार सात सौ पच्चीस रुपये", {"user": {"id": "u"}}, memory)
    assert by_type(r)["AMOUNT"].status == Status.KEPT


SMS_40250 = {"user": {"id": "u"}, "sms": [{"sender": "VM-HDFCBK", "body": "EMI of Rs 40,250 is due"}]}


def test_context_near_miss_is_asked_when_there_is_no_independent_transcript(memory):
    r = _with_opinion("EMI fourteen thousand two hundred fifty rupees", None, SMS_40250, memory)
    assert by_type(r)["AMOUNT"].status == Status.FLAGGED


def test_context_near_miss_is_withdrawn_when_a_context_free_transcript_heard_the_same_number(memory):
    text = "EMI fourteen thousand two hundred fifty rupees"
    r = _with_opinion(text, "EMI 14,250 rupees", SMS_40250, memory)
    amount = by_type(r)["AMOUNT"]
    assert amount.status == Status.KEPT and amount.value == "14250" and not r.questions


def test_context_near_miss_stays_a_question_when_the_transcripts_disagree(memory):
    r = _with_opinion("EMI fourteen thousand two hundred fifty rupees", "EMI 40,250 rupees", SMS_40250, memory)
    assert by_type(r)["AMOUNT"].status == Status.FLAGGED


def test_stray_number_words_after_a_cue_ask(run):
    r = run("mera number ek ek kuch hai", context={"user": {"id": "u"}})
    assert by_type(r)["PHONE"].status == Status.FLAGGED


def test_large_amount_value_is_never_in_scientific_notation(run):
    assert by_type(run("loan 25 lakh rupaye hai"))["AMOUNT"].value == "2500000"


def test_garbled_telugu_number_after_the_cue_asks(run):
    r = run("డ్రైవర్ నంబర్ నంబై ఒక్క ఒక్క వాడు", context={"user": {"id": "u"}})
    assert by_type(r)["PHONE"].status == Status.FLAGGED
