"""Render a benchmark summary as a Markdown report (systems x metrics, by type, by language)."""
from __future__ import annotations


def _pct(x):
    return "-" if x is None else f"{100 * x:.1f}%"


def _ci(ci):
    return "" if not ci else f" [{100 * ci[0]:.0f}-{100 * ci[1]:.0f}]"


def report_md(summary: dict) -> str:
    lines = [f"# Pehchaan-Bench: {summary['clips']}{'  (SIMULATED ASR - NOT A RESULT)' if summary['simulated'] else ''}",
             f"{summary['n_clips']} clips - {summary['ran_at']}", "",
             "| system | entity acc (95% CI) | silent errors (95% CI) | critical acc | over-correction | "
             "flag precision | flags/clip | reachable acc | unreachable acc | WER | harness p50 ms | LLM calls/clip |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sid, s in summary["systems"].items():
        wer_s = "-" if s["wer"] is None else f"{s['wer']:.3f}"
        lines.append(f"| {sid} | {_pct(s['entity_accuracy'])}{_ci(s['ci95']['entity_accuracy'])} | "
                     f"{_pct(s['silent_error_rate'])}{_ci(s['ci95']['silent_error_rate'])} | {_pct(s['critical_accuracy'])} | "
                     f"{_pct(s['over_correction_rate'])} | {_pct(s['flag_precision'])} | {s['flags_per_clip']:.2f} | "
                     f"{_pct(s['accuracy_reachable'])} | {_pct(s['accuracy_unreachable'])} | {wer_s} | "
                     f"{s.get('harness_ms_p50', '-')} | {s['llm_calls_per_clip']:.2f} |")
    lines += ["", "## Accuracy by entity type", "", "| system | " + " | ".join(
        sorted({t for s in summary["systems"].values() for t in s["by_type"]})) + " |"]
    types = sorted({t for s in summary["systems"].values() for t in s["by_type"]})
    lines.append("|---|" + "---|" * len(types))
    for sid, s in summary["systems"].items():
        lines.append(f"| {sid} | " + " | ".join(
            f"{_pct(s['by_type'][t]['accuracy'])} (n={s['by_type'][t]['n']})" if t in s["by_type"] else "-"
            for t in types) + " |")
    lines += ["", "## Damage audit (changes the system made that were not warranted)", "",
              "| system | damaged edits | clips affected | by reason |", "|---|---|---|---|"]
    for sid, s in summary["systems"].items():
        why = ", ".join(f"{k} {v}" for k, v in sorted(s.get("damage_by_reason", {}).items())) or "-"
        lines.append(f"| {sid} | {s.get('damaged_edits', 0)} | {s.get('clips_with_damage', 0)} of {s['clips']} | {why} |")
    langs = sorted({lg for s in summary["systems"].values() for lg in s.get("by_lang", {})})
    if langs:
        lines += ["", "## By language (entity accuracy / silent errors)", "",
                  "| system | " + " | ".join(langs) + " |", "|---|" + "---|" * len(langs)]
        for sid, s in summary["systems"].items():
            cells = []
            for lg in langs:
                b = s.get("by_lang", {}).get(lg)
                cells.append(f"{_pct(b['accuracy'])} / {_pct(b['silent_error_rate'])} (n={b['n']})" if b else "-")
            lines.append(f"| {sid} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
