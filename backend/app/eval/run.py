"""CLI entry point. Same function the HTTP route calls (ADR-12)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.config import get_settings
from app.eval.harness import run_evaluation


def render(card) -> str:  # type: ignore[no-untyped-def]
    L: list[str] = ["", "  Eval scorecard", "  " + "=" * 68]
    L.append(f"  seed digest   {card.seed_digest[:16]}")
    L.append(f"  cases         {card.cases}")
    L.append(f"  labeler       {card.labeler}")
    L.append("")
    L.append("  Extraction accuracy (FR-093) -- the pair of numbers that decides")
    L.append("  whether the model earns its latency here")
    llm = card.extraction_llm
    L.append(f"    {'field':<22} {'rules':>8}   {'LLM':>8}")
    for name, acc in card.extraction_rules["per_field"].items():
        lp = f"{llm['per_field'][name]['pct']:>7.1f}%" if llm else "      --"
        L.append(f"    {name:<22} {acc['pct']:>7.1f}%   {lp}")
    lo = f"{llm['overall_pct']:>7.1f}%" if llm else "      --"
    L.append(f"    {'OVERALL':<22} {card.extraction_rules['overall_pct']:>7.1f}%   {lo}")
    L.append("")
    L.append("  Ranking (FR-094)")
    r = card.ranking
    L.append(f"    top-1 agreement       {r['top1_pct']:>5.1f}%  ({r['top1']})")
    L.append(f"    top-3 hit rate        {r['top3_pct']:>5.1f}%  ({r['top3']})")
    L.append("")
    L.append("  Head-to-head vs naive first-available (FR-095)")
    b = card.baseline
    L.append(f"    ours  top-3          {b['ours']['top3_pct']:>5.1f}%")
    L.append(f"    naive top-3          {b['naive']['top3_pct']:>5.1f}%")
    L.append(
        f"    orphan min/case      ours {b['quality_ours']['orphan_minutes_per_case']:>6}"
        f"   naive {b['quality_naive']['orphan_minutes_per_case']:>6}"
    )
    L.append(
        f"    protected min/case   ours {b['quality_ours']['protected_minutes_per_case']:>6}"
        f"   naive {b['quality_naive']['protected_minutes_per_case']:>6}"
    )
    L.append("")
    L.append("  Per request class -- classes with no measurable gain are NAMED")
    for tag, v in b["per_class"].items():
        flag = "  <-- no measurable gain" if v["verdict"] == "no measurable gain" else ""
        L.append(
            f"    {tag:<22} ours {v['ours']}/{v['cases']}   naive {v['naive']}/{v['cases']}{flag}"
        )
    L.append("")
    L.append("  Latency (NFR-01)")
    L.append(
        f"    p50 {card.latency['p50_ms']}ms   p95 {card.latency['p95_ms']}ms"
        f"   ceiling {card.latency['ceiling_ms']}ms   "
        f"{'PASS' if card.latency['pass'] else 'FAIL'}"
    )
    L.append("")
    L.append("  Checks")
    det = card.determinism
    L.append(
        f"    determinism (FR-097)  "
        f"{'identical' if det['identical'] else 'DIFFERS: ' + ', '.join(det['differing'])}"
    )
    L.append(f"    read-aloud lint       {card.lint['violations']} violations")
    L.append("")

    failures = []
    for name, acc in card.extraction_rules["per_field"].items():
        failures += [f"{name}: {f}" for f in acc["failures"]]
    if failures:
        L.append(f"  Failing cases, by name ({len(failures)}) -- shown by default (FR-100)")
        for f in failures[:30]:
            L.append(f"    - {f}")
        if len(failures) > 30:
            L.append(f"    ... and {len(failures) - 30} more")
        L.append("")
    if card.ranking["misses"]:
        L.append(f"  Ranking misses: {', '.join(card.ranking['misses'])}")
        L.append("")

    L.append("  Disclosed limitations")
    for lim in card.limitations:
        L.append(f"    - {lim}")
    L.append("  " + "=" * 68)
    L.append(f"  {'PASS' if card.passed else 'FAIL'}")
    return "\n".join(L) + "\n"


def main() -> int:
    card = run_evaluation()
    sys.stdout.write(render(card))
    out = Path(get_settings().seed_dir).parents[1] / "eval" / "scorecard.json"
    out.write_text(json.dumps(card.as_dict(), indent=2, sort_keys=True) + "\n")
    sys.stdout.write(f"  written to {out}\n")
    return 0 if card.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
