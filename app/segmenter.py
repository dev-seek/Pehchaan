"""Cut live 16-bit mono audio into phrases at natural pauses, so each phrase can be transcribed once it has ended."""

from __future__ import annotations

import io
import math
import wave
from array import array

FRAME_MS = 30


def to_wav(pcm: bytes, sample_rate: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(sample_rate)
        file.writeframes(pcm)
    return out.getvalue()


def _loudness(frame: bytes) -> float:
    samples = array("h")
    samples.frombytes(frame[: len(frame) - len(frame) % 2])
    return math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0


class Segmenter:
    """
    A frame counts as speech if it is well above the quietest level heard so far.
    A phrase ends after a pause, or at `max_s`. Stretches with no speech are dropped, so silence is never paid for.
    """

    def __init__(
        self, sample_rate: int, *, pause_ms: int, min_s: float, max_s: float, min_level: float, over_floor: float
    ):
        self.rate = sample_rate
        self.frame_bytes = 2 * sample_rate * FRAME_MS // 1000
        self.pause_frames = pause_ms // FRAME_MS
        self.min_frames = int(min_s * 1000 / FRAME_MS)
        self.max_frames = int(max_s * 1000 / FRAME_MS)
        self.min_level, self.over_floor = min_level, over_floor
        self.floor: float | None = None
        self._pending = bytearray()
        self._phrase = bytearray()
        self._frames = self._speech = self._quiet = 0

    def _is_speech(self, frame: bytes) -> bool:
        level = _loudness(frame)
        self.floor = level if self.floor is None else min(level + 1, self.floor * 1.002 + 0.01)
        return level >= max(self.min_level, self.floor * self.over_floor)

    def _finish(self) -> bytes | None:
        keep = len(self._phrase) - max(0, self._quiet - self.pause_frames // 2) * self.frame_bytes
        phrase = bytes(self._phrase[:keep]) if self._speech else None
        self._phrase.clear()
        self._frames = self._speech = self._quiet = 0
        return phrase

    def feed(self, pcm: bytes) -> list[bytes]:
        self._pending.extend(pcm)
        ready = []
        while len(self._pending) >= self.frame_bytes:
            frame = bytes(self._pending[: self.frame_bytes])
            del self._pending[: self.frame_bytes]
            speaking = self._is_speech(frame)
            if not speaking and not self._speech:
                continue  # nothing has been said yet
            self._phrase.extend(frame)
            self._frames += 1
            self._speech += int(speaking)
            self._quiet = 0 if speaking else self._quiet + 1
            paused = self._quiet >= self.pause_frames and self._frames >= self.min_frames
            if paused or self._frames >= self.max_frames:
                phrase = self._finish()
                if phrase:
                    ready.append(phrase)
        return ready

    def flush(self) -> bytes | None:
        self._pending.clear()
        return self._finish()
