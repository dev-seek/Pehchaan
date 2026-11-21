"""End-to-end behaviour of the engine, without any API (fake judge, temp memory)."""
from pehchaan.models import Status

from .conftest import ExplodingJudge, FakeJudge, by_type

# real transcript from gpt-transcribe in tools/check_openai.py (21 Nov)
GPT_TRANSCRIBE_OUTPUT = ("नमस्ते सर, मैं वेंकटेश्वर राव बोल रहा हूँ HDFC बैंक से, कोंडापुर ब्रांच, आपकी EMI चौदह हज़ार "
                         "पाँच सौ रुपये पेंडिंग है, मेरा नंबर है नाइन एट फोर एट ज़ीरो वन टू थ्री फोर फाइव।")


def test_real_asr_output_all_facts_confirmed(run):
    r = run(GPT_TRANSCRIBE_OUTPUT)
    e = by_type(r)
    assert {k: v.status for k, v in e.items()} == {
        "PERSON": Status.CONFIRMED, "ORG": Status.CONFIRMED, "PLACE": Status.CONFIRMED,
        "AMOUNT": Status.CONFIRMED, "PHONE": Status.CONFIRMED}
    assert "98480 12345" in r.text_out and "HDFC Bank से" in r.text_out
    assert r.language["dominant"] == "hi"


def test_teen_ty_conflict_flagged_without_confidence(run):
    assert by_type(run("Aapki EMI 40,500 rupaye pending hai"))["AMOUNT"].status == Status.FLAGGED


def test_teen_ty_never_rewritten_even_when_asr_unsure(run):
    pieces = [{"token": "Aapki EMI ", "logprob": -0.01}, {"token": "40,500", "logprob": -2.3},
              {"token": " rupaye pending hai", "logprob": -0.02}]
    r = run("Aapki EMI 40,500 rupaye pending hai", pieces=pieces)
    amount = by_type(r)["AMOUNT"]
    assert amount.status == Status.FLAGGED and amount.value == "40500" and "40,500" in r.text_out
    assert amount.candidates[0]["text"] == "₹14,500"


def test_phone_confirmed_wrong_length_asked_and_unknown_kept(run):
    assert by_type(run("mera number nine eight four eight zero one two three four five"))["PHONE"].status == Status.CONFIRMED
    r = run("number hai 98480 123445")
    wrong = by_type(r)["PHONE"]
    assert wrong.status == Status.FLAGGED and wrong.value == "98480123445" and "98480 123445" in r.text_out
    assert wrong.candidates[0]["text"] == "98480 12345"
    assert by_type(run("number hai 77777 12345"))["PHONE"].status == Status.KEPT


def test_pin_with_extra_digit_asked_and_wrong_city_flagged(run):
    r = run("pin code 5000084")
    pin = by_type(r)["PIN"]
    assert pin.status == Status.FLAGGED and pin.value == "5000084" and "5000084" in r.text_out
    assert "500084" in [c["text"] for c in pin.candidates]
    assert by_type(run("pin code 400050"))["PIN"].status == Status.FLAGGED      # Mumbai PIN, Hyderabad user


def test_name_fixed_from_contacts_and_brand_short_name(run):
    r = run("main Venkat row bol raha hoon HDFC se")
    assert by_type(r)["PERSON"].value == "Venkateswara Rao" and by_type(r)["ORG"].value == "HDFC Bank"


def test_longer_span_wins(run):
    assert run("मैं HDFC बैंक से").text_out == "मैं HDFC Bank से"


def test_no_context_no_name_fix(run):
    r = run("main Venkat row bol raha hoon", level="C0")
    assert "PERSON" not in by_type(r) and r.text_out == "main Venkat row bol raha hoon"


def test_everyday_words_never_become_entities(run):
    r = run("haan ji kal call kar dena sir")
    assert r.entities == [] and r.text_out == "haan ji kal call kar dena sir"


def test_names_never_span_punctuation(run):
    context = {"user": {"id": "u", "city": "Hyderabad"}, "contacts": [{"name": "Neha Agarwal"}]}
    assert "PERSON" not in by_type(run("कल आना है, अगर टाइम हो", context=context))


def test_two_close_candidates_ask_the_caller_without_an_llm(run):
    context = {"user": {"id": "u"}, "contacts": [{"name": "Venkatesh"}, {"name": "Venkataraman"}]}
    judge = FakeJudge("cand1")
    person = by_type(run("main Venkat bol raha hoon", judge=judge, context=context))["PERSON"]
    assert judge.calls == [] and person.status == Status.FLAGGED and person.clarifier


def test_judge_only_for_unclear_single_candidate_and_its_choice_is_used(run):
    context = {"user": {"id": "u"}, "contacts": [{"name": "Venkatesh"}]}
    judge = FakeJudge("cand1")
    r = run("main Venkat bol raha hoon", judge=judge, context=context)
    assert len(judge.calls) == 1 and by_type(r)["PERSON"].source == "llm"
    clear = FakeJudge("cand1")
    run("main Venkatesh bol raha hoon", judge=clear, context=context)
    assert clear.calls == []                                       # exact match: no LLM call


def test_judge_failure_falls_back_to_flag(run):
    context = {"user": {"id": "u"}, "contacts": [{"name": "Venkatesh"}]}
    r = run("main Venkat bol raha hoon", judge=ExplodingJudge(), context=context)
    assert by_type(r)["PERSON"].status == Status.FLAGGED and r.questions


def test_memory_learns_a_correction(run, memory):
    memory.remember("demo_user", "Kotha poor", "Kondapur", "PLACE")
    place = by_type(run("parcel Kotha poor pahunch gaya", level="C0"))["PLACE"]
    assert place.status == Status.FIXED and place.source == "memory"


def test_clarifying_question_in_callers_language(run):
    r = run("pin code 400050 hai ji")
    assert r.questions and r.questions[0]["question"].startswith("Pin code")


def test_pin_before_a_comma_is_not_taken_for_money_by_a_cue_in_the_next_clause(run):
    r = run("एड्रेस नोट कीजिए पिन कोड फाइव सिक्स ट्रिपल ज़ीरो सेवन, पेमेंट एक हज़ार छह सौ छत्तीस रुपये कैश")
    pin = next(e for e in r.entities if e.etype.value == "PIN")
    amount = next(e for e in r.entities if e.etype.value == "AMOUNT")
    assert pin.value == "560007" and amount.value == "1636" and "₹5,60,007" not in r.text_out


def test_a_cue_before_a_comma_still_names_the_number(run):
    r = run("mera number hai, 9848012345")
    phones = [e for e in r.entities if e.etype.value == "PHONE"]
    assert [e.value for e in phones] == ["9848012345"] and not r.questions


def test_a_cue_with_no_number_still_asks_even_if_money_follows_in_the_next_clause(run):
    r = run("mera number hai, payment 500 rupaye")
    assert any(e.etype.value == "PHONE" and e.status.value == "FLAGGED" for e in r.entities)


def _agreeing(heard, contact):
    from pehchaan import CallContext, build_pipeline
    from pehchaan.resolvers import NullMemoryStore
    ctx = CallContext.build({"user": {"id": "u", "city": "Hyderabad"},
                             "contacts": [{"name": contact, "number": "9812034569"}]}, "C3")
    text = f"main {heard} bol raha hoon"
    return build_pipeline(memory=NullMemoryStore()).run(text, ctx, None, text)


def test_two_transcripts_that_agree_beat_a_similar_contact():
    result = _agreeing("Rohan Reddy", "Mohan Reddy")
    assert "Mohan" not in result.text_out and "Rohan Reddy" in result.text_out
    person = next(e for e in result.entities if e.etype.value == "PERSON")
    assert person.status.value == "FLAGGED" and person.admission == "second_opinion"
    assert [c["text"] for c in person.candidates][:2] == ["Rohan Reddy", "Mohan Reddy"]


def test_a_spelling_of_the_same_name_is_still_confirmed():
    result = _agreeing("मोहन रेड्डी", "Mohan Reddy")
    assert "Mohan Reddy" in result.text_out and not result.questions


def test_digits_mixed_with_lakh_and_thousand_are_read_as_money():
    from pehchaan.languages import get_registry
    from pehchaan.numbers import find_runs
    from pehchaan.text import tokenize
    def read(text):
        return [r.value_reading for r in find_runs(tokenize(text), get_registry())]
    assert read("refund of 2 lakh 40 thousand rupees") == [240000.0]
    assert read("3 crore 5 lakh 20 thousand 500") == [30520500.0]
    assert read("call 98480 12345") == [None]


def test_consonant_changes_separate_a_mishearing_from_a_different_name():
    from pehchaan.sound import consonant_changes
    assert consonant_changes("Rohan", "Mohan")[0] == 1              # an unrelated consonant: a different person
    assert consonant_changes("Narayanan", "Narasimhan") != (0, 0)
    assert consonant_changes("Venkat", "Venkateswara") == (0, 0)    # a shortened name is the same name
    assert consonant_changes("सौजन्या", "Sowjanya") == (0, 0)         # another script, same consonants
    assert consonant_changes("Somato", "Zomato") == (0, 0)          # s and z are easy to mishear
