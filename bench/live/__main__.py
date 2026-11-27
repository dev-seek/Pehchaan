"""Run the offline development, sealed release or policy-transfer action benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from pehchaan.config import ROOT
from pehchaan_live.runtime import digest

from .calibration import evaluate, search
from .dataset import check_splits, load_split, policies_for
from .release import compare, gate
from .replay import native, raw

SYNTHETIC = "Invented labelled action scenarios. No speech provider, customer outcome, or production latency was measured."


def _hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "release", "transfer"), default="dev")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    check_splits()
    rows, revision = load_split(args.split)
    policies = policies_for(rows)
    incumbent = evaluate(rows, policies, "incumbent")
    dev, development_revision = load_split("dev")
    chosen, trials = search(dev, policies_for(dev))
    calibrated = evaluate(rows, chosen.policies, chosen.name) if args.split != "transfer" else incumbent
    outputs = {"raw_proposal": [raw(row) for row in rows], "native_reference": [native(row) for row in rows],
               "incumbent": incumbent.outcomes, "calibrated": calibrated.outcomes}
    report = compare(rows, outputs, "calibrated")
    report.update({
        "evidence": SYNTHETIC, "split": args.split, "dataset_sha256": revision, "development_sha256": development_revision,
        "scorer_sha256": _hash(list(Path(__file__).parent.glob("*.py"))),
        "runtime_sha256": _hash(list((ROOT / "pehchaan_live").glob("*.py"))),
        "runtime_config_sha256": hashlib.sha256((ROOT / "config" / "live.yaml").read_bytes()).hexdigest(),
        "chosen_candidate": calibrated.name,
        "incumbent_policies": {name: {"version": policy.version, "sha256": digest(policy)} for name, policy in policies.items()},

        "policies": {name: {"version": policy.version, "sha256": digest(policy)} for name, policy in calibrated.policies.items()},
    })
    if args.split == "dev":
        report["search_trials"] = trials
    if args.split == "release":
        passed = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_live_runtime.py",
                                 "tests/test_live_api.py", "tests/test_live_bench.py"], stdout=sys.stderr, check=False).returncode == 0
        report["fixture_release_gate"] = gate(
            report, challenger="calibrated", baselines=("native_reference", "incumbent"), safety_passed=passed,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{args.split}: {len(rows)} opportunities. Wrote {args.out}")


if __name__ == "__main__":
    main()
