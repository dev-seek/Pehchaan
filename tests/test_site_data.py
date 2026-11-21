"""The three-tab site reads packaged data with no key. Nothing here reaches a paid model."""

from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient

from app.server import app
from pehchaan.config import ROOT, settings


@pytest.fixture
def public(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("DEMO_PASSCODE", raising=False)
    monkeypatch.delenv("PEHCHAAN_DEMO_PASSCODE", raising=False)
    return TestClient(app)


def test_every_sample_has_every_speech_model_without_a_credential(public):
    models = set(settings()["sdk"]["models"])
    presets = public.get("/api/demo/presets").json()
    assert presets
    for preset in presets:
        response = public.get(f"/api/demo/presets/{preset['id']}/models")
        assert response.status_code == 200
        answers = response.json()
        assert set(answers) == models
        for answer in answers.values():
            assert answer["base"]["text"] and answer["main"]["text"]
            assert isinstance(answer["keywords_used"], bool)


def test_only_keyword_capable_models_are_packaged_with_keywords(public):
    profiles = settings()["sdk"]["models"]
    preset = public.get("/api/demo/presets").json()[0]["id"]
    answers = public.get(f"/api/demo/presets/{preset}/models").json()
    for model, answer in answers.items():
        if not profiles[model]["keywords"]:
            assert answer["keywords_used"] is False


def test_unknown_sample_has_no_model_answers(public):
    assert public.get("/api/demo/presets/not-a-sample/models").status_code == 404


def test_benchmark_lab_data_is_free_and_measured(public):
    lab = public.get("/v1/bench").json()
    assert set(lab["model_profiles"]) == set(settings()["sdk"]["models"])
    assert lab["exam"]["standard"]["simulated"] is False
    assert lab["exam"]["noisy"]["simulated"] is False
    for line in lab["exam_paired"]["lines"].values():
        assert set(line) == {"C3", "C4"}


def test_each_demo_opens_on_the_call_that_really_shows_it(public):
    spec = importlib.util.spec_from_file_location("demo_highlights", ROOT / "tools" / "demo_highlights.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    published = public.get("/api/demo/highlights").json()
    assert published == tool.compute(public)
    assert all(published[tab] for tab in ("context", "llm", "learning"))
