"""Speech-to-text adapters (OpenAI) and mapping of token confidences onto our tokens."""
from .confidence import piece_spans, token_confidences
from .transcriber import transcribe

__all__ = ["transcribe", "token_confidences", "piece_spans"]
