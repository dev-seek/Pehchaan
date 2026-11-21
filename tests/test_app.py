"""API smoke tests (no OpenAI calls: text input only)."""
import json

from fastapi.testclient import TestClient

from app.server import app

from .conftest import DEMO_CONTEXT

client = TestClient(app)


def test_health_and_pages():
    assert client.get("/api/health").json()["ok"]
    assert client.get("/").status_code == 200 and client.get("/record").status_code == 200


def test_process_text_returns_entities_and_language():
    r = client.post("/api/process", data={"text": "main Venkat row bol raha hoon HDFC se",
                                          "context": json.dumps(DEMO_CONTEXT), "level": "C3", "user_id": "t_api"})
    body = r.json()
    assert r.status_code == 200 and body["pehchaan"]["language"]["dominant"] == "hi"
    assert {e["etype"] for e in body["pehchaan"]["entities"]} == {"PERSON", "ORG"}


def test_bad_inputs_fail_fast_with_400():
    assert client.post("/api/process", data={"text": "x", "level": "C9"}).status_code == 400
    assert client.post("/api/process", data={"text": "x", "context": "{not json"}).status_code == 400
    assert client.post("/api/memory/confirm", json={"user_id": "t", "heard": "a", "canonical": "b",
                                                    "etype": "NOPE"}).status_code == 400


def test_memory_roundtrip():
    client.delete("/api/memory/t_api_mem")
    client.post("/api/memory/confirm", json={"user_id": "t_api_mem", "heard": "Kotha poor", "canonical": "Kondapur",
                                             "etype": "PLACE"})
    assert client.get("/api/memory/t_api_mem").json()[0]["canonical"] == "Kondapur"
    client.delete("/api/memory/t_api_mem")
    assert client.get("/api/memory/t_api_mem").json() == []


def test_test_scripts_listed_for_recording():
    rows = client.get("/api/scripts?split=test").json()
    assert len(rows) == 30 and {r["lang"] for r in rows} <= {"hi", "hl", "en"}
