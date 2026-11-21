"""
Check one call from the terminal.

    pehchaan call.wav --city Hyderabad --contact "Ravi Kumar"     # needs OPENAI_API_KEY
    pehchaan --text "Main Ravi Kumaar bol raha hoon" --contact "Ravi Kumar"    # any transcript, no key needed
"""

from __future__ import annotations

import argparse
import json
import sys

from pehchaan.config import settings

from .client import Pehchaan
from .providers import CustomTranscriptProvider, OpenAIProvider

MARKS = {"VERIFIED": "verified", "FIXED": "fixed", "HEARD": "heard", "FLAGGED": "ask"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pehchaan", description="Check the facts in a call transcript.")
    parser.add_argument("audio", nargs="?", help="audio file to transcribe and check")
    parser.add_argument("--text", help="check this transcript instead of an audio file")
    parser.add_argument(
        "--model", default=settings()["sdk"]["default_model"], choices=sorted(settings()["sdk"]["models"])
    )
    parser.add_argument("--city")
    parser.add_argument("--contact", action="append", default=[], metavar="NAME", help="a known contact (repeatable)")
    parser.add_argument("--place", action="append", default=[], metavar="PLACE", help="a known place (repeatable)")
    parser.add_argument("--language", help="language code, for example ta. Omit for Hindi, English and Telugu")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    return parser


def _show(result) -> None:
    print(result.verified_text)
    for fact in result.entities:
        changed = f"  (heard {fact.heard})" if fact.heard != fact.value else ""
        print(f"  {MARKS[fact.status]:<9}{fact.type:<8}{fact.value}{changed}")
    if result.clarifier_prompt:
        print(f"Ask: {result.clarifier_prompt}")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if bool(args.audio) == bool(args.text):
        parser.error("give an audio file or --text")
    context = {"city": args.city, "contacts": args.contact or None, "places": args.place or None}
    try:
        if args.text:
            result = Pehchaan(CustomTranscriptProvider(), judge=None, **context).verify_transcript(
                args.text, language=args.language
            )
        else:
            result = Pehchaan(OpenAIProvider(args.model), **context).verify_audio(args.audio, language=args.language)
    except FileNotFoundError:
        print(f"pehchaan: no such file: {args.audio}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"pehchaan: {type(exc).__name__}. Check OPENAI_API_KEY and the audio file.", file=sys.stderr)
        return 1
    print(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2) if args.json else "",
        end="\n" if args.json else "",
    )
    if not args.json:
        _show(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
