"""
Pehchaan SDK: put the frozen verification engine behind any speech-to-text model.

    from openai import OpenAI
    from pehchaan_sdk import wrap

    client = wrap(OpenAI(), city="Hyderabad", contacts=[{"name": "Ravi Kumar"}])    # or wrap(any_speech_function)

This package sits beside `pehchaan` on purpose. The engine stays byte-identical to the code that sat the locked exam.
"""

from .client import Pehchaan
from .knowledge import CsvSource, FunctionSource, HttpSource, Knowledge, KnowledgeHub, StaticSource, load_knowledge
from .live import LiveClient, LiveUnavailable
from .providers import AudioFile, CustomTranscriptProvider, OpenAIProvider, STTProvider
from .types import ASRResult, CorrectionResult, Fact, Telemetry, VerifyResult
from .wrap import VerifiedText, wrap

__all__ = [
    "ASRResult",
    "AudioFile",
    "CorrectionResult",
    "CsvSource",
    "CustomTranscriptProvider",
    "Fact",
    "FunctionSource",
    "HttpSource",
    "Knowledge",
    "KnowledgeHub",
    "LiveClient",
    "LiveUnavailable",
    "OpenAIProvider",
    "Pehchaan",
    "STTProvider",
    "StaticSource",
    "Telemetry",
    "VerifiedText",
    "VerifyResult",
    "load_knowledge",
    "wrap",
]
