"""Scorecard metrics.

The design rule throughout: **a scorecard that shows only aggregates is not a
scorecard.** Aggregates hide exactly the systematic failures worth fixing, so every
metric here can name its failing cases and the report surfaces them by default
(FR-100).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any

FIELDS = (
    "date_range",
    "time_window",
    "urgency",
    "provider_preference",
    "appointment_type",
    "exclusions",
)


@dataclass
class FieldAccuracy:
    correct: int = 0
    total: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def pct(self) -> float:
        return 100.0 * self.correct / self.total if self.total else 0.0

    def record(self, ok: bool, case_id: str, detail: str = "") -> None:
        self.total += 1
        if ok:
            self.correct += 1
        else:
            self.failures.append(f"{case_id}{f' ({detail})' if detail else ''}")


@dataclass
class ExtractionScore:
    """FR-093. Reported per field **for both implementations**, side by side.

    That pair of columns is the entire evidence for "would replacing this with plain
    code change decision quality?" -- without it, using a model here is a preference
    rather than a finding.
    """

    per_field: dict[str, FieldAccuracy] = field(
        default_factory=lambda: {f: FieldAccuracy() for f in FIELDS}
    )

    @property
    def overall_pct(self) -> float:
        correct = sum(a.correct for a in self.per_field.values())
        total = sum(a.total for a in self.per_field.values())
        return 100.0 * correct / total if total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall_pct": round(self.overall_pct, 1),
            "per_field": {
                name: {
                    "pct": round(acc.pct, 1),
                    "correct": acc.correct,
                    "total": acc.total,
                    "failures": acc.failures,
                }
                for name, acc in self.per_field.items()
            },
        }


@dataclass
class RankingScore:
    """FR-094. Both reported with denominators, never as bare percentages."""

    top1_hits: int = 0
    top3_hits: int = 0
    total: int = 0
    misses: list[str] = field(default_factory=list)

    def record(self, preferred: str | None, offered: list[str], case_id: str) -> None:
        if preferred is None:
            return
        self.total += 1
        if offered and offered[0] == preferred:
            self.top1_hits += 1
        if preferred in offered:
            self.top3_hits += 1
        else:
            self.misses.append(case_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "top1_pct": round(100.0 * self.top1_hits / self.total, 1) if self.total else 0.0,
            "top3_pct": round(100.0 * self.top3_hits / self.total, 1) if self.total else 0.0,
            "top1": f"{self.top1_hits}/{self.total}",
            "top3": f"{self.top3_hits}/{self.total}",
            "misses": self.misses,
        }


@dataclass
class ScheduleQuality:
    """FR-095. Minutes and counts, never dollars.

    The harness measures orphan-gap minutes created and protected-block minutes
    consumed. A revenue figure derived from synthetic data and an invented fee
    schedule would be unfalsifiable; a practice's own fee schedule is what converts
    minutes into money, and that conversion belongs to the practice.
    """

    orphan_minutes: int = 0
    protected_minutes: int = 0
    cases: int = 0

    def as_dict(self) -> dict[str, Any]:
        n = max(1, self.cases)
        return {
            "orphan_minutes_total": self.orphan_minutes,
            "orphan_minutes_per_case": round(self.orphan_minutes / n, 1),
            "protected_minutes_total": self.protected_minutes,
            "protected_minutes_per_case": round(self.protected_minutes / n, 1),
        }


@dataclass
class Latency:
    samples: list[float] = field(default_factory=list)

    def record(self, ms: float) -> None:
        self.samples.append(ms)

    def as_dict(self, ceiling_ms: float) -> dict[str, Any]:
        if not self.samples:
            return {"p50_ms": 0.0, "p95_ms": 0.0, "pass": True}
        ordered = sorted(self.samples)
        p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
        return {
            "p50_ms": round(median(ordered), 1),
            "p95_ms": round(p95, 1),
            "ceiling_ms": ceiling_ms,
            "pass": p95 < ceiling_ms,
        }
