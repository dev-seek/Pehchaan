"""Replay identical action opportunities with the separately measured provider transcripts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pehchaan_live.contracts import Provider
from pehchaan_live.runtime import digest

from .calibration import search
from .dataset import Opportunity, load_split, policies_for, read
from .release import compare
from .replay import native, raw, replay


def _overlay(row: Opportunity, records: dict, track: str, line: str) -> Opportunity | None:
    key = (row.id, track, line)
    initial = records.get((*key, "initial"))
    correction = records.get((*key, "correction"))
    answer = records.get((*key, "readback"))
    plain = records.get((row.id, "plain", line, "initial"))
    if not initial or (row.correction is not None and not correction) or (row.reply is not None and not answer):
        return None
    alternative = plain if track == "hints" and plain and initial["audio_sha256"] == plain["audio_sha256"] else None
    speaker = Provider(name=initial["provider"], model=initial["model"], language=row.language)
    return row.model_copy(update={
        "transcript": initial["transcript"], "correction": correction["transcript"] if row.correction is not None else None,
        "reply": answer["transcript"] if row.reply is not None else None, "provider": speaker, "confidence": None, "noise": line,
        "alternative": alternative["transcript"] if alternative else None,
    })


def paired_replays(rows: list[Opportunity], records: list[dict]) -> dict:
    providers = sorted({record["provider"] for record in records if record.get("opportunity_id")})
    if len(providers) < 2:
        raise ValueError("a paired action comparison requires mapped records from two providers")
    by_provider = {provider: {} for provider in providers}
    for record in records:
        if not record.get("opportunity_id"):
            continue
        key = (record["opportunity_id"], record["track"], record["line"], record["turn_stage"])
        target = by_provider[record["provider"]]
        if key in target:
            raise ValueError("duplicate audio for the same provider, opportunity, case and turn")
        target[key] = record
    policy_set = policies_for(rows)
    development, _ = load_split("dev")
    candidate, _ = search(development, policies_for(development))
    calibrated = policy_set | {name: candidate.policies[name] for name in policy_set.keys() & candidate.policies.keys()}
    reports = {}
    conditions = sorted({(key[1], key[2]) for captured in by_provider.values() for key in captured})
    for track, line in conditions:
        common = [
            row for row in rows if all(_overlay(row, by_provider[provider], track, line) for provider in providers)
        ]
        if not common:
            continue
        for row in common:
            for stage in ("initial", "correction", "readback"):
                key = (row.id, track, line, stage)
                hashes = {store[key]["audio_sha256"] for store in by_provider.values() if key in store}
                if len(hashes) > 1:
                    raise ValueError("provider audio hashes differ within a paired opportunity")
        reports[f"{track}/{line}"] = {
            provider: _score(common, by_provider[provider], track, line, policy_set, calibrated)
            for provider in providers
        }
    if not reports:
        raise ValueError("no opportunities have all required turns captured by every provider")
    return {"policies": {name: digest(policy) for name, policy in calibrated.items()},
            "candidate": candidate.name, "paired_opportunity_reports": reports}


def _score(common, captured, track, line, stable, candidate):
    cases = [_overlay(row, captured, track, line) for row in common]
    result = compare(cases, {
        "raw_proposal": [raw(row) for row in cases],
        "native_reference": [native(row) for row in cases],
        "incumbent": [replay(row, stable[row.policy]) for row in cases],
        "calibrated": [replay(row, candidate[row.policy]) for row in cases],
    }, "calibrated")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--speech", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    speech = args.speech.read_bytes()
    result = paired_replays(read(args.scenarios), json.loads(speech)["records"])
    result.update(scenarios_sha256=hashlib.sha256(args.scenarios.read_bytes()).hexdigest(),
                  speech_results_sha256=hashlib.sha256(speech).hexdigest())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote paired provider action replay to {args.out}")


if __name__ == "__main__":
    main()
