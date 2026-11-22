#!/usr/bin/env python3
"""
Build the upload zip from the committed code, plus VIDEO.md.

  python tools/make_submission.py                       # draft: VIDEO.md says the link is pending
  python tools/make_submission.py --video <link>        # final zip
  python tools/make_submission.py --video <link> --live-passcode   # also adds REVIEWER_ACCESS.md

Only committed files go in, so .env, private notes, recordings and virtual environments cannot be included.
The passcode is read from ~/.pehchaan/demo_passcode, written only into the zip, and never printed.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LIVE = "https://52-24-174-127.sslip.io"
VIDEO_HOSTS = ("youtube.com", "youtu.be", "drive.google.com")
NEVER = re.compile(r"(^|/)(\.env|explanation\.md|pitch\.md|.*\.pem|test_real\w*_clips\.jsonl|adversarial_holdout\.json)$")
KEYS = re.compile(rb"sk-(proj-)?[A-Za-z0-9_-]{40,}|\b(AKIA|ASIA)[A-Z0-9]{16}\b|-----BEGIN [A-Z ]*PRIVATE KEY")


def video_page(link: str | None) -> str:
    if not link:
        return f"# Demo video\n\nThe link is being added.\n\nLive product: {LIVE}\n"
    host = (urlparse(link).hostname or "").removeprefix("www.")
    if urlparse(link).scheme != "https" or not any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS):
        sys.exit("The video link must be an https YouTube or Google Drive link.")
    return f"# Demo video\n\n**Watch the demo:** {link}\n\nLive product: {LIVE}\nSetup and journeys: `AGENTS.md`\n"


def access_page() -> str:
    code = (Path.home() / ".pehchaan/demo_passcode").read_text().strip()
    return (
        "# Reviewer access to the live site\n\n"
        f"Site: {LIVE}\n\nPasscode: `{code}`\n\n"
        "Open **Live Playground > Your voice > Connect** and enter it, or send it as the `X-Demo-Passcode` header.\n"
        "It turns on real speech, including the noisy-line test. Please use it only to review this submission.\n"
    )


def check(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        bad = [n for n in names if NEVER.search(n)]
        bad += [n for n in names if not n.endswith("/") and KEYS.search(archive.read(n))]
        missing = [n for n in ("AGENTS.md", ".env.example", "VIDEO.md", "PRESENTATION.pdf") if n not in names]
    if bad or missing:
        path.unlink()
        sys.exit(f"Zip refused. Must not contain: {bad}. Missing: {missing}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video")
    parser.add_argument("--live-passcode", action="store_true")
    args = parser.parse_args()
    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip():
        sys.exit("Commit your changes first: the zip is built from the last commit.")
    page = video_page(args.video)
    out = ROOT / "dist" / ("Pehchaan-submission.zip" if args.video else "Pehchaan-submission-DRAFT.zip")
    out.parent.mkdir(exist_ok=True)
    subprocess.run(["git", "archive", "--format=zip", "-o", str(out), "HEAD"], cwd=ROOT, check=True)
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("VIDEO.md", page)
        if args.live_passcode:
            archive.writestr("REVIEWER_ACCESS.md", access_page())
    check(out)
    print(f"{out} ({out.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    main()
