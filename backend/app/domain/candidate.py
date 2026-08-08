"""[SD-1] The pipeline annotates. It never deletes.

``CandidateSet`` deliberately exposes no ``remove``, ``filter``, ``pop`` or
``__delitem__``. A stage cannot drop a candidate because the type does not offer the
operation -- which is the difference between a convention and a guarantee.

Two things fall out of that for free:

* the **rejection ledger** (FR-030), the most domain-credible surface in the product,
  because every casualty is still present with the single rule it first failed; and
* the **funnel counter** (FR-029), which is trustworthy precisely because
  ``conserve()`` asserts ``feasible + Σ rejected == enumerated`` after every stage,
  in every mode -- not only under test.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime

from app.domain.enums import AXIS_ORDER, Axis, RejectionReason, Urgency


@dataclass(frozen=True, slots=True)
class Candidate:
    """Identity. Fixed at enumeration and never mutated.

    ``start_min`` is minutes from local midnight -- the same coordinate system as
    ``BusinessHours``. The availability index translates into its own day-open-based
    frame internally, so no other module needs to know about that translation.
    """

    candidate_id: str
    day: date
    start: datetime  # timezone-aware
    start_min: int
    duration_min: int
    provider_id: str
    operatory_id: str

    @property
    def end_min(self) -> int:
        return self.start_min + self.duration_min

    @staticmethod
    def make_id(day: date, start_min: int, duration: int, provider: str, operatory: str) -> str:
        """Deterministic across runs and machines (FR-017).

        sha1 of the canonical tuple rather than ``hash()``, which is salted per
        process and would silently break byte-identical replay.
        """
        raw = f"{day.isoformat()}|{start_min}|{duration}|{provider}|{operatory}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class EfficiencySubterms:
    """Separately inspectable in the trace (FR-042). Sub-weights are fixed [A-12];
    the tuner exposes the four axes, not these."""

    fragmentation: float
    idle: float
    check_load: float
    operatory_balance: float

    def composite(self) -> float:
        return (
            0.40 * self.fragmentation
            + 0.25 * self.idle
            + 0.20 * self.check_load
            + 0.15 * self.operatory_balance
        )


@dataclass(frozen=True, slots=True)
class AxisValues:
    """Weight-independent. This is the whole basis of ADR-06: axis values are
    computed once, and every weight question afterwards is a dot product."""

    time_fit: float
    continuity: float
    efficiency: float
    prime_time: float
    subterms: EfficiencySubterms
    atoms: tuple[str, ...] = ()  # human-readable, one per axis, in AXIS_ORDER
    #: Parallel to ``atoms``: does this axis's phrasing name a shortfall? (FR-038)
    concessions: tuple[bool, ...] = ()

    def as_row(self) -> tuple[float, float, float, float]:
        return (self.time_fit, self.continuity, self.efficiency, self.prime_time)

    def value_of(self, axis: Axis) -> float:
        return self.as_row()[AXIS_ORDER.index(axis)]


@dataclass(slots=True)
class Annotations:
    """Written by stages, additively. Never cleared, never removed."""

    feasible: bool | None = None
    rejection_reason: RejectionReason | None = None
    rejected_by_rule: str | None = None
    tier: Urgency | None = None
    in_tier: bool = False
    axes: AxisValues | None = None
    score: float | None = None
    rank: int | None = None
    offered: bool = False
    overflow: bool = False
    doctor_check_provider_id: str | None = None
    emergency_hold_released: bool = False

    @property
    def decided(self) -> bool:
        return self.feasible is not None


@dataclass(frozen=True, slots=True)
class FunnelCounts:
    """The four live numbers (FR-029). They reconcile with the conservation
    invariant, which is what makes them worth showing."""

    grid_slots: int
    enumerated: int
    feasible: int
    in_tier: int
    offered: int


class ConservationError(AssertionError):
    """Raised when the funnel would be lying."""


class CandidateSet:
    __slots__ = ("_ann", "_candidates", "_grid_slots")

    def __init__(self, grid_slots: int = 0) -> None:
        self._candidates: list[Candidate] = []
        self._ann: dict[str, Annotations] = {}
        self._grid_slots = grid_slots

    # -- construction (enumeration only) ---------------------------------------
    def add(self, c: Candidate) -> None:
        self._candidates.append(c)
        self._ann[c.candidate_id] = Annotations()

    def set_grid_slots(self, n: int) -> None:
        self._grid_slots = n

    # -- annotation ------------------------------------------------------------
    def annotate(self, candidate_id: str, **kw: object) -> None:
        a = self._ann[candidate_id]
        for k, v in kw.items():
            setattr(a, k, v)

    def reject(self, candidate_id: str, reason: RejectionReason, rule: str) -> None:
        """Idempotent in effect: the FIRST rule to fail is the stated cause (FR-028),
        so a later rule cannot overwrite an earlier verdict."""
        a = self._ann[candidate_id]
        if a.decided:
            return
        a.feasible = False
        a.rejection_reason = reason
        a.rejected_by_rule = rule

    def mark_feasible(self, candidate_id: str) -> None:
        a = self._ann[candidate_id]
        if not a.decided:
            a.feasible = True

    # -- read ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._candidates)

    def __iter__(self) -> Iterator[Candidate]:
        return iter(self._candidates)

    def ann(self, candidate_id: str) -> Annotations:
        return self._ann[candidate_id]

    def get(self, candidate_id: str) -> Candidate:
        return next(c for c in self._candidates if c.candidate_id == candidate_id)

    def pairs(self) -> Iterator[tuple[Candidate, Annotations]]:
        for c in self._candidates:
            yield c, self._ann[c.candidate_id]

    def feasible(self) -> Iterator[tuple[Candidate, Annotations]]:
        for c, a in self.pairs():
            if a.feasible:
                yield c, a

    def in_tier(self) -> Iterator[tuple[Candidate, Annotations]]:
        for c, a in self.pairs():
            if a.in_tier:
                yield c, a

    def rejected_by_reason(self) -> dict[RejectionReason, int]:
        return dict(
            Counter(a.rejection_reason for _, a in self.pairs() if a.rejection_reason is not None)
        )

    # -- the invariant ---------------------------------------------------------
    def conserve(self) -> None:
        """FR-027. Runs after every stage from the ``@stage`` decorator."""
        pending = sum(1 for _, a in self.pairs() if not a.decided)
        if pending:
            raise ConservationError(
                f"{pending} of {len(self)} candidates left undecided by the ladder"
            )
        n_feasible = sum(1 for _, a in self.pairs() if a.feasible)
        n_rejected = sum(self.rejected_by_reason().values())
        if n_feasible + n_rejected != len(self):
            raise ConservationError(
                f"conservation violated: {n_feasible} feasible + {n_rejected} rejected "
                f"!= {len(self)} enumerated"
            )

    def funnel(self) -> FunnelCounts:
        return FunnelCounts(
            grid_slots=self._grid_slots,
            enumerated=len(self),
            feasible=sum(1 for _, a in self.pairs() if a.feasible),
            in_tier=sum(1 for _, a in self.pairs() if a.in_tier),
            offered=sum(1 for _, a in self.pairs() if a.offered),
        )


@dataclass(frozen=True, slots=True)
class RejectionGroup:
    """One row of the ledger: a cause, its count, and a sentence a person can read."""

    reason: RejectionReason
    count: int
    sentence: str
    examples: tuple[str, ...] = field(default=())
