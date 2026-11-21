"""Real calls on worse phone lines: packaged, free, and identical to the published check."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.server import app
from pehchaan.config import ROOT

PUBLISHED = json.loads((ROOT / "data/published/real_voice.json").read_text(encoding="utf-8"))
LINES = ("clean", "phone", "noisy", "very_noisy", "dropouts")
SYSTEMS = {"base": "B0_asr_plain", "keywords": "B1_asr_keywords_C3", "main": "P_on_B1_C3"}


@pytest.fixture
def public(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return TestClient(app)


@pytest.mark.parametrize("sample", list(PUBLISHED["clean"]["silent_by_clip"]))
def test_every_line_matches_the_published_check(public, sample):
    answers = public.get(f"/api/demo/presets/{sample}/lines").json()
    assert tuple(answers) == LINES
    for line in LINES:
        for name, system in SYSTEMS.items():
            assert answers[line][name]["scored"]["silent_errors"] == PUBLISHED[line]["silent_by_clip"][sample][system]


def test_each_line_has_its_own_audio(public):
    clear = public.get("/api/demo/presets/real-hl-food/audio")
    noisy = public.get("/api/demo/presets/real-hl-food/audio", params={"line": "very_noisy"})
    assert clear.status_code == noisy.status_code == 200
    assert clear.content != noisy.content


@pytest.mark.parametrize("line", ["../real", "exam", "test_real_phone"])
def test_only_named_lines_can_be_read(public, line):
    assert public.get("/api/demo/presets/real-hl-food/audio", params={"line": line}).status_code == 404


def test_a_synthetic_sample_has_no_line_versions(public):
    assert public.get("/api/demo/presets/delivery/lines").status_code == 404
    assert public.get("/api/demo/presets/delivery/audio", params={"line": "noisy"}).status_code == 404
