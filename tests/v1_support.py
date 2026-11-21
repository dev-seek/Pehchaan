"""Shared fakes for the public API tests. No test here reaches a paid model."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import access, v1
from app.segmenter import to_wav
from app.server import app
from pehchaan.config import settings
from pehchaan.resolvers import JsonMemoryStore
from pehchaan_sdk import OpenAIProvider

PASSCODE = "correct-horse-battery"
GOOD = {"X-Demo-Passcode": PASSCODE}
TEXT = "Main Ravi Kumar bol raha hoon, mera number 9848012345 hai"
CONTEXT = {"contacts": [{"name": "Ravi Kumar", "number": "9848012345"}], "user": {"city": "Hyderabad"}}
WAV = to_wav(b"\x10\x20" * 16000, 16000)


class Fake:
    def __init__(self):
        self.calls, self.keys = [], []
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=TEXT)

    def _chat(self, **_):
        message = SimpleNamespace(content=json.dumps({"choice": "keep", "reason": "fake"}))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def fake(monkeypatch, tmp_path):
    client = Fake()

    class Patched(OpenAIProvider):
        def __init__(self, model=None, *, api_key=None, client_override=None):
            client.keys.append(api_key)
            super().__init__(model, api_key=api_key, client=client)

    monkeypatch.setattr(v1, "OpenAIProvider", Patched)
    monkeypatch.setattr(v1, "_memory", JsonMemoryStore(tmp_path / "memory"))
    monkeypatch.setitem(settings()["api"], "ledger_db", str(tmp_path / "ledger.sqlite3"))
    monkeypatch.setitem(settings()["api"], "calls_db", str(tmp_path / "calls.sqlite3"))
    monkeypatch.setitem(settings()["demo"], "access_db", str(tmp_path / "access.sqlite3"))
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DEMO_PASSCODE", PASSCODE)
    monkeypatch.delenv("PEHCHAAN_DEMO_PASSCODE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-server-key-not-for-customers")
    access._windows.clear()
    yield client
    access._windows.clear()


@pytest.fixture
def http(fake):
    return TestClient(app)
