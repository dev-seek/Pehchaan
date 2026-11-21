"""
Pehchaan SDK: put the frozen verification engine behind any speech-to-text model.

    from pehchaan_sdk import Pehchaan

    p = Pehchaan(city="Hyderabad", contacts=[{"name": "Ravi Kumar"}])
    print(p.verify_transcript("text from any speech model").verified_text)

This package sits beside `pehchaan` on purpose. The engine stays byte-identical to the code that sat the locked exam.
"""

from .client import Pehchaan
from .providers import AudioFile, CustomTranscriptProvider, OpenAIProvider, STTProvider
from .types import ASRResult, CorrectionResult, Fact, Telemetry, VerifyResult

__all__ = [
    "ASRResult",
    "AudioFile",
    "CorrectionResult",
    "CustomTranscriptProvider",
    "Fact",
    "OpenAIProvider",
    "Pehchaan",
    "STTProvider",
    "Telemetry",
    "VerifyResult",
]
