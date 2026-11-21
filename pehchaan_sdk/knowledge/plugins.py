"""
Plugins: connect company systems from a config file, and let any package add a new connector type.

    # knowledge.yaml
    sources:
      - {type: http, name: crm, url: "https://crm.example.in/c?phone={phone}", headers: {Authorization: "${CRM_TOKEN}"},
         fields: {people: "records.*.Name", amounts.emi: "records.0.Emi"}}
      - {type: csv, name: orders, file: orders.csv, key: phone, fields: {places: city_area, pins: pincode}}

A package adds a type by declaring an entry point:

    [project.entry-points."pehchaan.knowledge"]
    mycrm = "my_package:MyCrmSource"
"""

from __future__ import annotations

import os
import re
from importlib.metadata import entry_points
from pathlib import Path

import yaml

from .hub import KnowledgeHub
from .sources import CsvSource, HttpSource

GROUP = "pehchaan.knowledge"
BUILT_IN = {"http": HttpSource, "csv": CsvSource}
_ENV = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(value):
    """`${CRM_TOKEN}` reads the environment, so secrets stay out of the config file."""
    if isinstance(value, str):

        def read(match: re.Match) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise ValueError(f"environment variable {name} is not set")
            return os.environ[name]

        return _ENV.sub(read, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def connector_types() -> dict:
    """Built-in connectors plus every installed plugin."""
    found = dict(BUILT_IN)
    for entry in entry_points(group=GROUP):
        found.setdefault(entry.name, entry)
    return found


def build_source(spec: dict):
    options = _expand(dict(spec))
    kind, name = options.pop("type", None), options.pop("name", None)
    if not kind or not name:
        raise ValueError("every knowledge source needs a type and a name")
    known = connector_types()
    if kind not in known:
        raise ValueError(f"unknown knowledge source type {kind!r}. Available: {', '.join(sorted(known))}")
    factory = known[kind]
    factory = factory.load() if hasattr(factory, "load") else factory
    if kind == "http":
        return factory(name, options.pop("url"), **options)
    if kind == "csv":
        return factory(name, options.pop("file"), **options)
    return factory(name, **options)


def load_knowledge(file: str | Path) -> KnowledgeHub:
    """Build a hub from a YAML file."""
    config = yaml.safe_load(Path(file).read_text(encoding="utf-8")) or {}
    return KnowledgeHub([build_source(spec) for spec in config.get("sources") or []])
