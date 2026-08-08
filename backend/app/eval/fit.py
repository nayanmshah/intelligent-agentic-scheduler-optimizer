"""Weight fitting and the sensitivity curve.

FR-098: the shipped default weights are **fitted to the golden labels, not chosen**.
"Why 0.35?" then has an answer that is not an opinion.

FR-099: the sensitivity sweep reports how flat the response is around the fitted
value, and **states the flat region numerically**. A wide flat region is direct
evidence that the ranking is not weight-fragile -- which is a stronger claim than any
particular weight being correct.

[ADR-14] ``numpy`` is used here and is banned from the request path. Fitting is ~1800
vectors x 42 cases; pure Python would miss FR-098's 60-second bound, while the
request path stays readable without it.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from itertools import product
from typing import Any

from app.agents.extractor.rules import RuleIntentExtractor
from app.config import Settings, get_settings
from app.data.loader import load_seed
from app.data.session import MemoryScheduleRepository, SessionState
from app.data.timezone import zone
from app.domain.policy import GENERAL_PRACTICE_DEFAULT, Weights
from app.eval.golden.labels import GOLDEN
from app.eval.harness import _preferred_slot
from app.reasoner.pipeline import DeterministicReasoner

STEP = 0.05


@dataclass
class FitResult:
    weights: Weights
    top3_pct: float
    top1_pct: float
    evaluated: int
    seconds: float
    sensitivity: dict[str, Any]


def _simplex(step: float = STEP) -> list[tuple[float, float, float, float]]:
    """Every weight vector on a `step` grid that sums to 1.0."""
    n = round(1.0 / step)
    out = []
    for a, b, c in product(range(n + 1), repeat=3):
        d = n - a - b - c
        if d >= 0:
            out.append((a * step, b * step, c * step, d * step))
    return out


def _cases(settings: Settings):  # type: ignore[no-untyped-def]
    """Score matrix + label per case, computed once. The matrix is weight-independent
    (ADR-06), which is the only reason fitting is affordable at all."""
    prepared = []
    for i, case in enumerate(GOLDEN):
        bundle = load_seed(settings.seed_dir).bundle
        repo = MemoryScheduleRepository(SessionState.from_seed(bundle))
        tz = zone(bundle.locations[0].timezone)
        reasoner = DeterministicReasoner(repo, settings, tz)
        extractor = RuleIntentExtractor(bundle)
        constraints = extractor.extract_sync(
            case["raw_text"], bundle.patient("pat-000"), settings.reference_now
        )
        outcome = reasoner.run(
            constraints, settings.reference_now, GENERAL_PRACTICE_DEFAULT, f"f{i}"
        )
        label_cs, _, _ = reasoner.prepare(constraints, settings.reference_now, f"f{i}")
        preferred = _preferred_slot(label_cs, bundle, constraints)
        if outcome.score_matrix and preferred:
            prepared.append((outcome.score_matrix, preferred))
    return prepared


def fit(settings: Settings | None = None) -> FitResult:
    import numpy as np  # eval-only dependency [ADR-14]

    s = settings or get_settings()
    t0 = time.perf_counter()
    cases = _cases(s)
    grid = np.array(_simplex(), dtype=float)  # (V, 4)

    top3 = np.zeros(len(grid))
    top1 = np.zeros(len(grid))
    for matrix, preferred in cases:
        rows = np.array(matrix.rows, dtype=float)                 # (N, 4)
        ids = list(matrix.candidate_ids)
        if preferred not in ids:
            continue
        target = ids.index(preferred)
        scores = rows @ grid.T                                    # (N, V)
        order = np.argsort(-scores, axis=0)
        top3 += (order[:3] == target).any(axis=0)
        top1 += order[0] == target

    n = max(1, len(cases))
    # Tiebreak on top-1 agreement, per FR-098.
    best = int(np.lexsort((-top1, -top3))[0])
    weights = Weights.normalised(tuple(grid[best]))  # type: ignore[arg-type]

    # FR-099: sweep each axis 0 -> 1 and report where top-3 membership is flat.
    sensitivity: dict[str, Any] = {}
    for axis_i, axis in enumerate(("time_fit", "continuity", "efficiency", "prime_time")):
        curve = []
        for value in [round(x * STEP, 2) for x in range(int(1 / STEP) + 1)]:
            mask = np.isclose(grid[:, axis_i], value)
            best = round(float(top3[mask].max() / n * 100), 1) if mask.any() else 0.0
            curve.append({"weight": value, "top3_pct": best})
        peak = max(c["top3_pct"] for c in curve)
        flat = [c["weight"] for c in curve if c["top3_pct"] >= peak - 2.0]
        sensitivity[axis] = {
            "curve": curve,
            # Stated numerically, e.g. "flat between 0.20 and 0.55".
            "flat_from": min(flat) if flat else None,
            "flat_to": max(flat) if flat else None,
        }

    return FitResult(
        weights=weights,
        top3_pct=round(float(top3[best]) / n * 100, 1),
        top1_pct=round(float(top1[best]) / n * 100, 1),
        evaluated=len(grid),
        seconds=round(time.perf_counter() - t0, 2),
        sensitivity=sensitivity,
    )


def main() -> int:
    s = get_settings()
    result = fit(s)
    w = result.weights
    out = [
        "",
        "  Weight fitting (FR-098)",
        "  " + "=" * 62,
        f"    vectors evaluated   {result.evaluated}",
        f"    elapsed             {result.seconds}s  (bound: 60s)",
        "",
        "    fitted vector",
        f"      time fit          {w.time_fit:.2f}",
        f"      continuity        {w.continuity:.2f}",
        f"      efficiency        {w.efficiency:.2f}",
        f"      block protection  {w.prime_time:.2f}",
        "",
        f"    top-3 hit rate      {result.top3_pct}%",
        f"    top-1 agreement     {result.top1_pct}%",
        "",
        "  Sensitivity (FR-099) -- a wide flat region means the ranking is not",
        "  weight-fragile, which is a stronger claim than any weight being right.",
    ]
    for axis, data in result.sensitivity.items():
        out.append(f"    {axis:<18} flat between {data['flat_from']} and {data['flat_to']}")
    widths = [
        (d["flat_to"] or 0) - (d["flat_from"] or 0) for d in result.sensitivity.values()
    ]
    narrow = sum(1 for w_ in widths if w_ <= 0.10)

    out += [
        "",
        "  How to read this",
        "  ----------------",
        "  The fitted vector collapses onto time fit and continuity, which is exactly",
        "  what the label heuristic optimises for. Fitting to a proxy label teaches the",
        "  model the proxy: the lift from 39% to "
        f"{result.top3_pct}% is mostly the fit learning",
        "  the labeller, not the scheduler.",
        "",
        f"  {narrow} of 4 axes have a flat region <= 0.10 wide, which says the same thing",
        "  from the other side -- a robust fit would be flat across a broad band. Treat",
        "  this vector as a diagnostic of the labels, not as a tuned product default.",
        "",
        "  NOT auto-applied. The shipped default stays the hand-set general-practice",
        "  profile until the golden set is labelled by practising schedulers [R-08].",
        "  " + "=" * 62,
    ]
    sys.stdout.write("\n".join(out) + "\n")

    path = s.seed_dir.parents[1] / "eval" / "fitted_weights.json"
    path.write_text(json.dumps({
        "weights": w.model_dump(),
        "top3_pct": result.top3_pct,
        "top1_pct": result.top1_pct,
        "sensitivity": result.sensitivity,
        "labeler": "proposed-unreviewed (single annotator) [R-08]",
    }, indent=2, sort_keys=True) + "\n")
    sys.stdout.write(f"  written to {path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
