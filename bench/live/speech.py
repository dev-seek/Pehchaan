"""Run paired speech recognition on rights-reviewed, locally available audio manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from time import perf_counter
from typing import Literal

import httpx
from jiwer import wer
from pydantic import Field

from pehchaan.config import load_dotenv
from pehchaan_live.contracts import Contract
from pehchaan_live.settings import live_settings
from pehchaan_sdk.providers import OpenAIProvider


class Clip(Contract):
    id: str
    audio: str
    sha256: str
    dataset: str
    revision: str
    license: str
    processing_ref: str
    speaker: str
    language: str
    condition: str
    transcript: str
    opportunity_id: str | None = None
    turn_stage: Literal["initial", "correction", "readback"] = "initial"
    facts: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)


def normalize(text: str) -> str:
    # Preserve combining marks in Indic scripts and punctuation internal to typed amounts and dates.
    return " ".join(re.sub(r"(?<!\w)[.,;!?]+|[.,;!?]+(?!\w)", "", text.casefold()).split())


def _clip_rows(manifest: Path, limit: int) -> list[tuple[Clip, Path]]:
    rows = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        clip = Clip.model_validate_json(line)
        audio = manifest.parent / clip.audio
        if (len(clip.hints) > 50 or any(not 0 < len(hint) <= 64 for hint in clip.hints)
                or not all((clip.dataset, clip.revision, clip.license, clip.processing_ref, clip.speaker,
                            clip.condition, clip.transcript))
                or hashlib.sha256(audio.read_bytes()).hexdigest() != clip.sha256):
            raise ValueError(f"invalid pinned clip metadata or audio for {clip.id}")
        rows.append((clip, audio))
        if len(rows) == limit:
            break
    if not rows or len({clip.id for clip, _ in rows}) != len(rows):
        raise ValueError("clip manifest must include distinct clip IDs")
    return rows


def _openai(audio: Path, clip: Clip, hints: list[str]) -> str:
    model = live_settings()["benchmark"]["openai_model"]
    return OpenAIProvider(model).transcribe(audio, hints, language=clip.language).text


def _sarvam(audio: Path, clip: Clip, hints: list[str]) -> str:
    config = live_settings()["benchmark"]
    fields = {"model": config["sarvam_model"], "mode": "transcribe"}
    if hints:
        fields["keyterms"] = json.dumps(hints, ensure_ascii=False)
    with audio.open("rb") as handle:
        result = httpx.post(
            "https://api.sarvam.ai/speech-to-text", headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]},
            data=fields, files={"file": (audio.name, handle)}, timeout=30,
        )
    result.raise_for_status()
    return result.json()["transcript"]


def collect(manifest: Path, providers: list[str], limit: int) -> dict:
    load_dotenv()
    key_names = {"openai": "OPENAI_API_KEY", "sarvam": "SARVAM_API_KEY"}
    missing = [key_names[provider] for provider in providers if not os.getenv(key_names[provider])]
    if missing:
        raise ValueError("missing credentials: " + ", ".join(missing))
    config = live_settings()["benchmark"]
    providers_by_name = {"openai": _openai, "sarvam": _sarvam}
    records = []
    for clip, audio in _clip_rows(manifest, limit):
        for provider in providers:
            for track in ("plain", "hints") if clip.hints else ("plain",):
                start = perf_counter()
                hints = clip.hints if track == "hints" else []
                text = providers_by_name[provider](audio, clip, hints)
                actual = normalize(text)
                records.append({
                    "sample": clip.id, "audio_sha256": clip.sha256, "dataset": clip.dataset, "revision": clip.revision,
                    "speaker": clip.speaker, "language": clip.language, "line": clip.condition, "provider": provider,
                    "license": clip.license, "processing_ref": clip.processing_ref,
                    "opportunity_id": clip.opportunity_id, "turn_stage": clip.turn_stage,
                    "model": config[f"{provider}_model"], "track": track, "keyterms": hints,
                    "request_settings": {"mode": "transcribe", "language": "auto"} if provider == "sarvam"
                    else {"language_hint": clip.language},
                    "word_error_rate": wer(normalize(clip.transcript), actual), "fact_count": len(clip.facts),
                    "exact_facts": sum(bool(re.search(r"(?<!\w)" + re.escape(normalize(fact)) + r"(?!\w)", actual))
                                       for fact in clip.facts if normalize(fact)),
                    "latency_ms": (perf_counter() - start) * 1000, "transcript": text,
                })
    return {"manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(), "records": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--provider", choices=("openai", "sarvam"), action="append")
    parser.add_argument("--limit", type=int, default=6, choices=range(1, 31), metavar="1–30")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    providers = list(dict.fromkeys(args.provider or ["openai", "sarvam"]))
    try:
        report = collect(args.manifest, providers, args.limit)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(report['records'])} recognition results to {args.out}")


if __name__ == "__main__":
    main()
