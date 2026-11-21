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
