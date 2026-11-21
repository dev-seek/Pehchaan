"""The HTTP connector against a real local server: lists of rows, slow systems and redirects."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pehchaan_sdk import HttpSource, KnowledgeHub
from pehchaan_sdk.knowledge import CallKey

CALLER = {"caller": {"number": "9848012345"}}


class _Crm(BaseHTTPRequestHandler):
    hits: list[str] = []

    def log_message(self, *_args):
        pass

    def do_GET(self):
        type(self).hits.append(self.path)
        if self.path.startswith("/moved"):
            self.send_response(302)
            self.send_header("Location", "/stolen")
            self.end_headers()
            return
        if self.path.startswith("/slow"):
            time.sleep(0.6)
        body = json.dumps({"records": [{"Name": "Ravi Kumar", "Emi": 14500}]}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def crm():
    _Crm.hits = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Crm)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_a_path_to_a_list_reads_each_row(crm):
    source = HttpSource("crm", f"{crm}/c?phone={{phone}}", records="records", fields={"people": "Name", "amounts.emi": "Emi"})
    got = source.fetch(CallKey(phone="9848012345"))
    assert got[0].people == ["Ravi Kumar"] and got[0].amounts == {"emi": 14500}


def test_a_slow_system_is_reported_as_a_timeout(crm):
    source = HttpSource("crm", f"{crm}/slow?phone={{phone}}", fields={"people": "records.*.Name"})
    assert KnowledgeHub([source]).gather({**CALLER}).report.sources[0].status == "timeout"


def test_a_redirect_is_never_followed(crm):
    source = HttpSource("crm", f"{crm}/moved?phone={{phone}}", headers={"Authorization": "k"}, fields={"people": "name"})
    assert KnowledgeHub([source]).gather({**CALLER}).report.sources[0].status == "error"
    assert not any(hit.startswith("/stolen") for hit in _Crm.hits)
