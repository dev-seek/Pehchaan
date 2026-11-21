"""Connect what a company already knows about its customers (CRM, bank core, orders) as evidence for each call."""

from .compiler import Compiled, compile_knowledge
from .hub import KnowledgeHub, KnowledgeSource, as_hub
from .plugins import connector_types, load_knowledge
from .records import CallKey, Knowledge, KnowledgeReport, SourceReport
from .sources import CsvSource, FunctionSource, HttpSource, StaticSource

__all__ = [
    "CallKey",
    "Compiled",
    "CsvSource",
    "FunctionSource",
    "HttpSource",
    "Knowledge",
    "KnowledgeHub",
    "KnowledgeReport",
    "KnowledgeSource",
    "SourceReport",
    "StaticSource",
    "as_hub",
    "compile_knowledge",
    "connector_types",
    "load_knowledge",
]
