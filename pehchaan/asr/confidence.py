"""
Map ASR token confidences (logprobs) back onto our tokens.

OpenAI returns sub-word pieces ("न", "म", "स्त", "े", " सर") each with a logprob (0 = certain, -2 = unsure).
We locate each piece in the transcript text, then a token's confidence = the LOWEST logprob of the pieces that
overlap it (a word is only as reliable as its least reliable piece). If text and pieces disagree, we return
None for everything: the engine then simply runs without confidence, it never crashes on it.
"""
from __future__ import annotations


def piece_spans(text: str, pieces: list[dict]) -> list[tuple[int, int, float]]:
    """[(start, end, logprob)] for every ASR piece found in order in `text`."""
    spans, pos = [], 0
    for p in pieces:
        piece, lp = p.get("token") or "", p.get("logprob")
        if not piece:
            continue
        idx = text.find(piece, pos)
        if idx < 0 and piece.strip():
            piece = piece.strip()
            idx = text.find(piece, pos)
        if idx < 0:
            continue
        if lp is not None:
            spans.append((idx, idx + len(piece), float(lp)))
        pos = idx + len(piece)
    return spans


def token_confidences(token_ranges: list[tuple[int, int]], pieces: list[dict], text: str) -> list[float | None]:
    spans = piece_spans(text, pieces or [])
    if not spans:
        return [None] * len(token_ranges)
    out: list[float | None] = []
    for s, e in token_ranges:
        overlapping = [lp for a, b, lp in spans if a < e and b > s]
        out.append(min(overlapping) if overlapping else None)
    return out
