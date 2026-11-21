"""On a public URL nothing private is reachable and nothing can spend credits without the passcode."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import access
from app.server import app
from pehchaan.config import settings
from pehchaan.openai_client import OfflineMiss, cached, offline_answers


@pytest.fixture
def public(monkeypatch, tmp_path):
    monkeypatch.setenv("PEHCHAAN_MODE", "public")
    monkeypatch.delenv("PEHCHAAN_DEMO_PASSCODE", raising=False)
    monkeypatch.setitem(settings()["demo"], "access_db", str(tmp_path / "access.sqlite3"))
    access._windows.clear()
    yield TestClient(app)
    access._windows.clear()


@pytest.mark.parametrize("method,url", [
    ("get", "/record"), ("get", "/studio"), ("get", "/api/scripts"), ("post", "/api/record"),
    ("get", "/api/studio/samples"), ("post", "/api/memory/confirm"), ("get", "/api/memory/u"), ("delete", "/api/memory/u"),
])
def test_private_routes_do_not_exist_in_public(public, method, url):
    assert getattr(public, method)(url).status_code == 404


def test_the_app_is_locked_when_no_mode_is_set(monkeypatch):
    monkeypatch.delenv("PEHCHAAN_MODE")
    assert access.is_public()


def test_live_is_off_without_a_configured_passcode(public):
    assert public.post("/api/process", data={"text": "hello"}).status_code == 403
    assert public.post("/api/demo/compare", data={"text": "hello"}).status_code == 403


def test_live_needs_the_right_passcode(public, monkeypatch):
    monkeypatch.setenv("PEHCHAAN_DEMO_PASSCODE", "open-sesame")
    assert public.post("/api/process", data={"text": "hello"}).status_code == 401
    assert public.post("/api/process", data={"text": "hello"}, headers={"x-demo-passcode": "nope"}).status_code == 401
    assert public.post("/api/process", data={"text": "hello"}, headers={"x-demo-passcode": "open-sesame"}).status_code == 200


def test_a_sample_with_edited_context_counts_as_live(public):
    reply = public.post("/api/demo/compare", data={"preset": "bank-emi", "context": "{}"})
    assert reply.status_code == 403


def test_daily_budget_is_a_hard_stop(public, monkeypatch):
    monkeypatch.setenv("PEHCHAAN_DEMO_PASSCODE", "pw")
    monkeypatch.setitem(settings()["demo"], "public_live_runs_per_day", 1)
    head = {"x-demo-passcode": "pw"}
    assert public.post("/api/process", data={"text": "hello"}, headers=head).status_code == 200
    assert public.post("/api/process", data={"text": "hello"}, headers=head).status_code == 429


def test_passcode_guessing_is_rate_limited(public, monkeypatch):
    monkeypatch.setenv("PEHCHAAN_DEMO_PASSCODE", "pw")
    monkeypatch.setitem(settings()["demo"], "public_passcode_tries_per_minute", 2)
    codes = [public.post("/api/process", data={"text": "x"}, headers={"x-demo-passcode": "bad"}).status_code for _ in range(3)]
    assert codes == [401, 401, 429]


def test_offline_block_never_calls_the_api():
    def paid():
        raise AssertionError("a paid call was attempted")

    with offline_answers(), pytest.raises(OfflineMiss):
        cached("asr", {"never": "cached", "id": "offline-test"}, paid)


def test_bench_rejects_unknown_result_sets(public):
    assert public.get("/api/bench/latest?clips=../../secret").status_code == 404
