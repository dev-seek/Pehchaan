"""Company systems feed each call as evidence. They can confirm or question a fact and can never rewrite it."""

from __future__ import annotations

import json
import threading
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.demo_knowledge import demo_data, run_call
from app.demo_presets import catalog, sample_answers
from app.server import app
from pehchaan import build_pipeline
from pehchaan.config import settings
from pehchaan.context import CallContext
from pehchaan.resolvers import NullMemoryStore
from pehchaan_sdk import CsvSource, FunctionSource, HttpSource, Knowledge, KnowledgeHub, Pehchaan, StaticSource
from pehchaan_sdk.knowledge import CallKey, compile_knowledge
from pehchaan_sdk.knowledge.compiler import Answer
from pehchaan_sdk.knowledge.plugins import build_source
from pehchaan_sdk.knowledge.sources import pick, read_fields
from pehchaan_sdk.providers import CustomTranscriptProvider

CALLER = {"caller": {"number": "9848012345"}}
TODAY = date(2026, 11, 22)


def engine(**options) -> Pehchaan:
    return Pehchaan(CustomTranscriptProvider(), judge=None, memory=NullMemoryStore(), **options)


def answer(name="crm", private=False, **fields) -> Answer:
    return Answer(name, "ok", records=[Knowledge(**fields)], private=private)


def test_records_become_the_six_fields_the_engine_reads():
    done = compile_knowledge(
        CALLER,
        [answer(people=["Ravi Kumar"], places=["Kondapur"], phones=["+91 98480 11111"],
                amounts={"emi": 14500}, pins=["500084"], companies=["HDFC Bank"], city="Hyderabad")],
        today=TODAY,
    )
    ctx = CallContext.build(done.context, "C3")
    assert 14500.0 in ctx.amounts and "500084" in ctx.pins and "9848011111" in ctx.phones
    assert {("Ravi Kumar", "PERSON"), ("Kondapur", "PLACE"), ("HDFC Bank", "ORG")} <= {
        (c.text, c.etype.value) for c in ctx.candidates if c.per_call}
    assert ctx.city == "Hyderabad"


def test_money_and_phone_are_never_rewritten_by_a_record():
    source = StaticSource("billing", {"9848012345": {"amounts": {"due": 40500}, "phones": ["9848012346"]}})
    result = engine(knowledge=source).verify_transcript("your emi is 14500 rupees, call 9848012345", CALLER)
    assert "14500" in result.verified_text.replace(",", "") and "9848012345" in result.verified_text.replace(" ", "")


def test_a_teen_ty_record_raises_a_question_when_nothing_else_settles_it():
    source = StaticSource("billing", {"9848012345": {"amounts": {"due": 40500}}})
    result = engine(knowledge=source).verify_transcript("your emi is 14500 rupees", CALLER)
    amount = next(f for f in result.entities if f.type == "AMOUNT")
    assert amount.status == "FLAGGED" and amount.value == "14500" and amount.backed_by == ["billing"]


def test_a_matching_record_verifies_and_is_credited():
    source = StaticSource("billing", {"9848012345": {"amounts": {"due": 14500}}})
    result = engine(knowledge=source).verify_transcript("your emi is 14500 rupees", CALLER)
    amount = next(f for f in result.entities if f.type == "AMOUNT")
    assert amount.status == "VERIFIED" and amount.backed_by == ["billing"] and "billing" in amount.reason
    assert result.knowledge.sources[0].status == "ok" and result.telemetry.evidence == "unmeasured"


def test_two_sources_that_disagree_cancel_out():
    done = compile_knowledge(CALLER, [answer("a", amounts={"due": 14500}), answer("b", amounts={"due": 14900})], today=TODAY)
    assert not CallContext.build(done.context, "C3").amounts
    assert done.report.conflicts == ["due: 14500 vs 14900"]


def test_an_old_record_stops_counting_for_money_and_places():
    old = (TODAY - timedelta(days=settings()["knowledge"]["max_age_days"] + 1)).isoformat()
    done = compile_knowledge(CALLER, [answer(amounts=[14500], places=["Kondapur"], people=["Ravi"], as_of=old)], today=TODAY)
    ctx = CallContext.build(done.context, "C3")
    assert not ctx.amounts and "Kondapur" not in [c.text for c in ctx.candidates]
    assert "Ravi" in [c.text for c in ctx.candidates]


def test_an_unreadable_date_counts_as_old():
    done = compile_knowledge(CALLER, [answer(amounts=[14500], as_of="last year")], today=TODAY)
    assert not CallContext.build(done.context, "C3").amounts


def test_several_records_on_one_number_cannot_vouch_for_money():
    two = Answer("crm", "ok", records=[Knowledge(amounts=[100]), Knowledge(amounts=[200])])
    assert not CallContext.build(compile_knowledge(CALLER, [two], today=TODAY).context, "C3").amounts


@pytest.mark.parametrize("bad", ["abc", -5, 0, float("inf"), True, "1e99"])
def test_malformed_amounts_are_dropped(bad):
    done = compile_knowledge(CALLER, [answer(amounts=[bad])], today=TODAY)
    assert not CallContext.build(done.context, "C3").amounts and done.report.sources[0].dropped


def test_an_unknown_company_is_reported_not_guessed():
    done = compile_knowledge(CALLER, [answer(companies=["Sharma Invented Traders"])], today=TODAY)
    assert done.report.sources[0].dropped[0].reason == "not a brand the engine knows"


def test_a_big_crm_dump_is_capped():
    many = [f"Person {chr(65 + i % 26)}{chr(65 + i // 26)}" for i in range(200)]
    done = compile_knowledge(CALLER, [answer(people=many)], today=TODAY)
    assert sum("name" in c for c in done.context["contacts"]) == settings()["knowledge"]["max_names"]


def test_the_calls_own_data_is_kept_and_not_credited_to_a_source():
    base = {**CALLER, "contacts": [{"name": "Ravi Kumar"}]}
    done = compile_knowledge(base, [answer(people=["Ravi Kumar"])], today=TODAY)
    assert done.context["contacts"][0] == {"name": "Ravi Kumar"} and done.backed_by("PERSON", ["Ravi Kumar"]) == []


def test_a_private_source_never_reaches_the_speech_model_or_the_judge():
    calls = {}

    class Listening(CustomTranscriptProvider):
        supports_keywords = True

        def transcribe(self, audio, *, keywords=None, **kwargs):
            calls["keywords"] = list(keywords or [])
            return super().transcribe(audio, keywords=keywords, **kwargs)

    hub = KnowledgeHub([StaticSource("vault", {"9848012345": {"people": ["Secret Name"], "amounts": [14500]}}, private=True)])
    done = hub.gather({**CALLER, "contacts": [], "places": [], "sms": []})
    assert "Secret Name" not in CallContext.build(done.shareable, "C3").keyword_list(50)
    assert done.has_private
    p = Pehchaan(CustomTranscriptProvider(), judge=object(), memory=NullMemoryStore(), knowledge=hub)
    assert p._judge_for(done) is None


def test_keywords_never_carry_phone_numbers_or_amounts():
    hub = KnowledgeHub([StaticSource("crm", {"9848012345": {"people": ["Ravi"], "amounts": [14500], "phones": ["9848011111"]}})])
    words = CallContext.build(hub.gather({**CALLER}).shareable, "C3").keyword_list(50)
    assert "Ravi" in words and not any(ch.isdigit() for word in words for ch in word)


def test_a_slow_source_is_skipped_inside_the_budget():
    release = threading.Event()
    slow = FunctionSource("slow", lambda _c: release.wait(5))
    quick = StaticSource("quick", {"9848012345": {"people": ["Ravi"]}})
    started = time.perf_counter()
    done = KnowledgeHub([slow, quick], timeout_ms=60).gather({**CALLER})
    release.set()
    assert time.perf_counter() - started < 1
    assert {s.name: s.status for s in done.report.sources} == {"slow": "timeout", "quick": "ok"}


def test_a_broken_source_never_breaks_the_call_or_leaks_its_error():
    def boom(_call):
        raise RuntimeError("https://user:secret@crm.example/x")

    result = engine(knowledge=FunctionSource("crm", boom)).verify_transcript("hello", CALLER)
    assert result.knowledge.sources[0].status == "error" and "secret" not in result.model_dump_json()


@pytest.mark.parametrize("reply", [{"nonsense": 1}, 42, {"amounts": object()}])
def test_a_source_that_returns_garbage_is_an_error_not_a_crash(reply):
    done = KnowledgeHub([FunctionSource("crm", lambda _c: reply)]).gather({**CALLER})
    assert done.report.sources[0].status == "error"


def test_one_value_where_a_list_belongs_is_accepted():
    assert Knowledge.of({"people": "Ravi", "amounts": 14500}).people == ["Ravi"]


def test_a_failing_source_is_rested_then_tried_again():
    calls = []

    def boom(_call):
        calls.append(1)
        raise RuntimeError

    hub = KnowledgeHub([FunctionSource("crm", boom)])
    for _ in range(settings()["knowledge"]["breaker_failures"] + 2):
        last = hub.gather({**CALLER})
    assert len(calls) == settings()["knowledge"]["breaker_failures"] and last.report.sources[0].status == "skipped"
    hub._resting_until.clear()
    hub.gather({**CALLER})
    assert len(calls) == settings()["knowledge"]["breaker_failures"] + 1


def test_a_live_call_asks_once():
    calls = []
    hub = KnowledgeHub([FunctionSource("crm", lambda _c: calls.append(1) or {"people": ["Ravi"]})])
    hub.gather({**CALLER})
    hub.gather({**CALLER})
    assert len(calls) == 1


def test_no_key_means_no_lookup_and_an_empty_hub_is_harmless():
    called = []
    assert KnowledgeHub([FunctionSource("crm", lambda c: called.append(c))]).gather({}).report.sources[0].status == "skipped"
    assert not called
    assert KnowledgeHub([]).gather({**CALLER}).report.sources == []


def test_two_sources_cannot_share_a_name():
    with pytest.raises(ValueError):
        KnowledgeHub([StaticSource("a", {}), StaticSource("a", {})])


def test_field_maps_walk_json():
    doc = {"records": [{"Name": "Ravi", "Emi": 100}, {"Name": "Asha"}], "updated": "2026-11-01"}
    assert pick(doc, "records.*.Name") == ["Ravi", "Asha"]
    got = read_fields(doc, {"people": "records.*.Name", "amounts.emi": "records.0.Emi", "as_of": "updated"})
    assert got.people == ["Ravi", "Asha"] and got.amounts == {"emi": 100} and got.as_of == "2026-11-01"


def test_csv_source_finds_a_customer(tmp_path):
    file = tmp_path / "orders.csv"
    file.write_text("phone,area,due\n+91 98480 12345,Kondapur,1636\n9000000000,Other,5\n", encoding="utf-8")
    source = CsvSource("orders", file, key="phone", fields={"places": "area", "amounts.due": "due"})
    got = source.fetch(CallKey(phone="9848012345"))
    assert got[0].places == ["Kondapur"] and got[0].amounts == {"due": "1636"}


def test_http_source_refuses_plain_http_to_another_host():
    with pytest.raises(ValueError):
        HttpSource("crm", "http://crm.example.in/c?phone={phone}", fields={"people": "name"})


def test_http_source_escapes_the_key_into_the_url():
    source = HttpSource("crm", "https://crm.example.in/c?id={customer_id}", fields={"people": "name"})
    assert source._url(CallKey(customer_id="a&admin=1")).endswith("a%26admin%3D1")


def test_config_secret_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CRM_TOKEN", "t0ken")
    spec = {"type": "http", "name": "crm", "url": "https://crm.example.in/{phone}",
            "headers": {"Authorization": "${CRM_TOKEN}"}, "fields": {"people": "name"}}
    assert build_source(spec).headers["Authorization"] == "t0ken"
    monkeypatch.delenv("CRM_TOKEN")
    with pytest.raises(ValueError):
        build_source(spec)


# ---- the simulated demo ----
def test_demo_engine_matches_the_packaged_answer_wherever_no_judge_was_used():
    model = settings()["sdk"]["default_model"]
    for call in demo_data()["calls"]:
        answers = sample_answers()[call["preset"]][model]
        context = CallContext.build(catalog()[call["preset"]]["context"], "C3")
        out = build_pipeline(judge=None, memory=NullMemoryStore()).run(
            answers["main"]["text_in"], context, None, answers["base"]["text"])
        if answers["main"]["llm_calls"] or answers["main"]["verifier_cache_hits"]:
            continue  # the packaged answer used the LLM judge, and this free demo never calls it
        assert out.text_out == answers["main"]["text"]


@pytest.mark.parametrize("call", [c["preset"] for c in demo_data()["calls"]])
def test_demo_never_changes_a_number_in_any_failure(call):
    plain = {(e["etype"], str(e["value"])) for e in run_call(call, [], "none")["entities"]
             if e["etype"] in ("PHONE", "PIN", "AMOUNT")}
    sources = [s["id"] for s in demo_data()["sources"]]
    for fault in demo_data()["faults"]:
        got = {(e["etype"], str(e["value"])) for e in run_call(call, sources, fault["id"])["entities"]
               if e["etype"] in ("PHONE", "PIN", "AMOUNT")}
        assert got == plain


def test_demo_is_free_labelled_and_reachable_without_a_credential(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("DEMO_PASSCODE", raising=False)
    monkeypatch.delenv("PEHCHAAN_DEMO_PASSCODE", raising=False)
    client = TestClient(app)
    listing = client.get("/api/demo/knowledge").json()
    assert "Simulated" in listing["notice"] and listing["calls"]
    body = {"call": listing["calls"][0]["id"], "sources": ["crm", "billing"], "fault": "none"}
    answer_ = client.post("/api/demo/knowledge", json=body)
    assert answer_.status_code == 200 and answer_.json()["simulated"] is True
    assert client.post("/api/demo/knowledge", json={**body, "call": "nope"}).status_code == 404
    assert client.post("/api/demo/knowledge", json={**body, "sources": ["nope"]}).status_code == 400


def test_demo_records_use_no_real_company_as_a_source():
    text = json.dumps(demo_data()["sources"]).lower()
    assert not any(brand in text for brand in ("salesforce", "hubspot", "zendesk", "hdfc", "kotak", "icici", "sbi"))
