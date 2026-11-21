"""
Ready-made connectors. Each takes a `fields` map from Pehchaan's words to the company's own field names:

    fields = {"people": "records.*.Name", "phones": "records.*.Phone", "amounts.emi": "loan.emi", "as_of": "updated_at"}

A dotted path walks JSON and `*` means every item of a list. `amounts.emi` labels the number, so two systems can be compared.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from ipaddress import ip_address
from pathlib import Path
from threading import Lock

from pehchaan.config import settings

from .records import LISTS, NUMBERS, CallKey, Knowledge


def pick(document, path: str) -> list:
    """Every value at a dotted path. A missing path gives an empty list."""
    found = [document]
    for part in path.split("."):
        following = []
        for item in found:
            if part == "*" and isinstance(item, list):
                following.extend(item)
            elif isinstance(item, dict) and part in item:
                following.append(item[part])
            elif isinstance(item, list) and part.isdigit() and int(part) < len(item):
                following.append(item[int(part)])
        found = following
    return [v for v in found if v not in (None, "")]


def read_fields(document, mapping: dict[str, str]) -> Knowledge | None:
    """Apply a `fields` map to one JSON object or row."""
    out: dict = {}
    for target, path in mapping.items():
        values = pick(document, path)
        if not values:
            continue
        kind, _, label = target.partition(".")
        if kind in LISTS:
            out.setdefault(kind, []).extend(values)
        elif kind in NUMBERS:
            if label:
                out.setdefault(kind, {})[label] = values[0]
            else:
                out.setdefault(kind, []).extend(values)
        elif kind in ("city", "as_of"):
            out[kind] = str(values[0])
        else:
            raise ValueError(f"unknown field target {target!r}")
    return Knowledge.of(out) if out else None


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value))[-10:]


class FunctionSource:
    """Wrap any function: `FunctionSource("bank", lambda call: {"amounts": {"emi": 14500}})`."""

    def __init__(self, name: str, function: Callable[[CallKey], object], *, private: bool = False):
        self.name, self.function, self.private = name, function, private

    def fetch(self, call: CallKey):
        return self.function(call)


class StaticSource:
    """A table in memory, keyed by phone number or customer id. Useful for tests and demos."""

    def __init__(self, name: str, table: dict, *, private: bool = False):
        self.name, self.private = name, private
        self.table = {(_digits(k) if len(_digits(k)) == 10 else str(k)): v for k, v in table.items()}

    def fetch(self, call: CallKey):
        return self.table.get(call.phone) or self.table.get(str(call.customer_id))


class CsvSource:
    """A CSV export. Rows match on the `key` column. It reloads when the file changes."""

    def __init__(self, name: str, file: str | Path, *, key: str, fields: dict[str, str], private: bool = False):
        self.name, self.file, self.key, self.fields, self.private = name, Path(file), key, fields, private
        self._rows: dict[str, list[dict]] = {}
        self._stamp = None
        self._lock = Lock()

    def _load(self) -> dict[str, list[dict]]:
        with self._lock:
            stamp = self.file.stat().st_mtime_ns
            if stamp != self._stamp:
                rows: dict[str, list[dict]] = {}
                with self.file.open(encoding="utf-8-sig", newline="") as handle:
                    for row in csv.DictReader(handle):
                        value = str(row.get(self.key) or "").strip()
                        key = _digits(value) if len(_digits(value)) == 10 else value
                        rows.setdefault(key, []).append(row)
                self._rows, self._stamp = rows, stamp
            return self._rows

    def fetch(self, call: CallKey):
        rows = self._load()
        hits = rows.get(call.phone or "") or rows.get(str(call.customer_id)) or []
        return [r for r in (read_fields(row, self.fields) for row in hits) if r]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect could carry the customer's API key to another host, so it is treated as a failure."""

    def redirect_request(self, *_args, **_kwargs):
        return None


def _is_local(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


class HttpSource:
    """
    Any REST API: a CRM, a bank core, an order system. Runs inside YOUR app, so your credentials never reach Pehchaan's server.

        HttpSource("crm", "https://crm.example.in/customers?phone={phone}", headers={"Authorization": "Bearer ..."},
                   fields={"people": "records.*.Name", "amounts.emi": "records.0.Emi"})
    """

    def __init__(
        self,
        name: str,
        url: str,
        *,
        fields: dict[str, str],
        headers: dict | None = None,
        records: str | None = None,
        private: bool = False,
    ):
        parts = urllib.parse.urlsplit(url.replace("{phone}", "0").replace("{customer_id}", "0"))
        if parts.scheme != "https" and not (parts.scheme == "http" and _is_local(parts.hostname or "")):
            raise ValueError("a knowledge source URL must use https (plain http is allowed only on localhost)")
        self.name, self.url, self.fields, self.private = name, url, fields, private
        self.headers, self.records = dict(headers or {}), records
        self._opener = urllib.request.build_opener(_NoRedirect)

    def _url(self, call: CallKey) -> str:
        quote = lambda value: urllib.parse.quote(str(value or ""), safe="")  # noqa: E731
        return self.url.replace("{phone}", quote(call.phone)).replace("{customer_id}", quote(call.customer_id))

    def fetch(self, call: CallKey):
        cfg = settings()["knowledge"]
        request = urllib.request.Request(self._url(call), headers={"Accept": "application/json", **self.headers})
        with self._opener.open(request, timeout=cfg["timeout_ms"] / 1000) as response:
            body = response.read(cfg["max_response_bytes"] + 1)
        if len(body) > cfg["max_response_bytes"]:
            raise ValueError("the response is too large")
        document = json.loads(body)
        rows = pick(document, self.records) if self.records else [document]
        return [r for r in (read_fields(row, self.fields) for row in rows) if r]
