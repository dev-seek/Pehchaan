"""Saved calls, per-caller learning, free text checks and the removal of call-count limits (D-049)."""
from __future__ import annotations

import sqlite3

from app.call_log import CallLog
from pehchaan.config import ROOT, settings
from tests.v1_support import GOOD, TEXT, WAV

KEY_A = {"X-OpenAI-Key": "sk-customer-key-aaaaaaaaaaaa"}
KEY_B = {"X-OpenAI-Key": "sk-customer-key-bbbbbbbbbbbb"}
HEARD = "The location is Thadugodi"


def check(http, text=TEXT, caller=None, headers=GOOD):
    context = {"user": {"id": caller, "city": "Bengaluru"}} if caller else None
    reply = http.post("/v1/verify-transcript", json={"text": text, "context": context}, headers=headers)
    assert reply.status_code == 200, reply.text
    return reply.json()


def saved(http, caller, headers=GOOD):
    return http.get("/v1/calls", params={"caller": caller}, headers=headers).json()


def teach(http, caller, call_id=None, headers=GOOD):
    body = {"user_id": caller, "heard": "Thadugodi", "corrected": "Kadugodi", "entity_type": "PLACE", "call_id": call_id}
    return http.post("/v1/memory/confirm", json=body, headers=headers).json()


def test_passcode_and_own_key_have_no_call_count_limit(http):
    for headers in (GOOD, KEY_A):
        assert all(check(http, headers=headers)["verified_text"] for _ in range(30))


def test_own_key_is_never_counted_even_when_a_limit_is_configured(http, monkeypatch):
    monkeypatch.setitem(settings()["api"], "per_ip_per_hour", 1)
    monkeypatch.setitem(settings()["demo"], "public_live_runs_per_day", 1)
    assert all(check(http, headers=KEY_A) for _ in range(3))


def test_a_correct_passcode_is_not_slowed_by_the_guessing_limit(http, monkeypatch):
    monkeypatch.setitem(settings()["demo"], "public_passcode_tries_per_minute", 2)
    assert all(check(http) for _ in range(5))
    wrong = {"X-Demo-Passcode": "wrong"}
    codes = [http.post("/v1/verify-transcript", json={"text": TEXT}, headers=wrong).status_code for _ in range(3)]
    assert codes == [401, 401, 429]


def test_pasted_text_works_with_no_credential_and_spends_nothing(http, fake):
    answer = check(http, headers={})
    assert answer["telemetry"]["judge"] == "off"
    assert not fake.calls and fake.keys == []


def test_teaching_with_no_credential_is_slowed_so_it_cannot_tie_up_the_server(http, monkeypatch):
    monkeypatch.setitem(settings()["api"], "free_teach_per_minute", 1)
    body = {"user_id": "caller-a", "heard": "Thadugodi", "corrected": "Kadugodi", "entity_type": "PLACE"}
    codes = [http.post("/v1/memory/confirm", json=body).status_code for _ in range(2)]
    assert codes == [200, 429]
    assert http.post("/v1/memory/confirm", json=body, headers=GOOD).status_code == 200


def test_audio_still_needs_a_credential(http, fake):
    files = {"audio": ("a.wav", WAV, "audio/wav")}
    assert http.post("/v1/verify-audio", files=files).status_code == 401
    assert not fake.calls


def test_a_call_is_saved_only_when_it_names_a_caller(http):
    assert check(http)["call_id"] is None
    call_id = check(http, caller="caller-1")["call_id"]
    row = saved(http, "caller-1")["calls"][0]
    assert row["id"] == call_id and row["result"]["raw_text"] == TEXT


def test_saved_calls_survive_a_new_process_and_hold_no_key_or_audio(http):
    check(http, caller="caller-1", headers=KEY_A)
    file = ROOT / settings()["api"]["calls_db"]
    assert len(CallLog(file, 10).calls(_tenant(http), "caller-1", 10)) == 1
    db = sqlite3.connect(file)
    try:
        columns = {row[1] for row in db.execute("PRAGMA table_info(calls)")}
        dump = "\n".join(str(row) for row in db.execute("SELECT * FROM calls"))
    finally:
        db.close()
    assert not columns & {"audio", "key", "openai_key"}
    assert KEY_A["X-OpenAI-Key"] not in dump


def _tenant(http):
    from app.access import Credential

    return Credential("byok", KEY_A["X-OpenAI-Key"]).tenant


def test_one_customer_cannot_read_or_delete_anothers_calls(http):
    call_id = check(http, caller="same-name", headers=KEY_A)["call_id"]
    assert saved(http, "same-name", KEY_B)["calls"] == []
    assert http.delete(f"/v1/calls/{call_id}", headers=KEY_B).status_code == 404
    assert http.delete(f"/v1/calls/{call_id}", headers=KEY_A).status_code == 200
    assert saved(http, "same-name", KEY_A)["calls"] == []


def test_listing_needs_a_caller_id(http):
    assert http.get("/v1/calls", headers=GOOD).status_code == 422


def test_a_confirmed_name_helps_that_caller_only(http):
    call_id = check(http, HEARD, caller="caller-a")["call_id"]
    assert teach(http, "caller-a", call_id)["adopted"] is True
    assert "Kadugodi" in check(http, HEARD, caller="caller-a")["verified_text"]
    assert "Kadugodi" not in check(http, HEARD, caller="caller-b")["verified_text"]
    assert [x["canonical"] for x in saved(http, "caller-a")["learned"]] == ["Kadugodi"]
    assert saved(http, "caller-b")["learned"] == []


def test_one_confirmation_covers_the_same_sound_in_another_script(http):
    teach(http, "caller-a")
    assert "Kadugodi" in check(http, "लोकेशन थडुगोडी है", caller="caller-a")["verified_text"]


def test_recheck_replays_a_saved_call_with_what_was_learned(http, fake):
    first = check(http, HEARD, caller="caller-a")
    teach(http, "caller-a", first["call_id"])
    again = http.post(f"/v1/calls/{first['call_id']}/recheck", headers=GOOD).json()
    assert "Kadugodi" in again["verified_text"] and again["call_id"] != first["call_id"]
    assert not fake.calls


def test_recheck_keeps_the_calls_language(http, monkeypatch):
    from pehchaan_sdk import Pehchaan

    seen, real = [], Pehchaan.verify_transcript

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get("language"))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Pehchaan, "verify_transcript", spy)
    body = {"text": "બે હજાર રૂપિયા", "context": {"user": {"id": "caller-g"}}, "language": "gu"}
    call_id = http.post("/v1/verify-transcript", json=body, headers=GOOD).json()["call_id"]
    http.post(f"/v1/calls/{call_id}/recheck", headers=GOOD)
    assert seen == ["gu", "gu"]


def test_forgetting_a_caller_removes_calls_and_lessons(http):
    teach(http, "caller-a", check(http, HEARD, caller="caller-a")["call_id"])
    assert http.delete("/v1/calls", params={"caller": "caller-a"}, headers=GOOD).status_code == 200
    assert saved(http, "caller-a") == {"caller": "caller-a", "calls": [], "learned": []}
    assert "Kadugodi" not in check(http, HEARD)["verified_text"]


def test_a_full_log_never_breaks_a_call(http, monkeypatch):
    monkeypatch.setitem(settings()["api"], "calls_max_mb", 0)
    check(http, caller="caller-1")
    answer = check(http, caller="caller-1")
    assert answer["verified_text"] and answer["call_id"] is None
