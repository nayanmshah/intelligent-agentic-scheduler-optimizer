"""Deterministic tiebreak, epsilon-band co-equality, and top-3 diversity.

Three near-identical options are functionally one option, and offering them as three
wastes the patient's only real choice (FR-050). Meanwhile a 1/2/3 ordering imposed on
scores 0.01 apart is a false precision the operator will read as meaningful, so the
epsilon band presents those as co-equal with *differentiating* reasons instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.candidate import Annotations, Candidate, CandidateSet


@dataclass(frozen=True, slots=True)
class Selection:
    offered: tuple[str, ...]
    coequal_groups: dict[str, int]
    limited_availability: bool
    suppressed: int


def tiebreak_key(pair: tuple[Candidate, Annotations]) -> tuple:  # type: ignore[type-arg]
    """FR-048: earlier -> higher continuity -> lower fragmentation -> lower room id.

    Terminating in ``operatory_id`` guarantees totality: two candidates cannot tie all
    the way down, so ordering can never depend on list order or hash iteration.
    """
    cand, ann = pair
    axes = ann.axes
    return (
        cand.start,
        -(axes.continuity if axes else 0.0),
        -(axes.subterms.fragmentation if axes else 0.0),
        cand.operatory_id,
        cand.provider_id,
    )


def select_top3(
    cs: CandidateSet, epsilon: float, diversity_window_min: int, want: int = 3
) -> Selection:
    ranked = sorted(
        ((c, a) for c, a in cs.in_tier() if a.score is not None),
        key=lambda p: (-(p[1].score or 0.0), tiebreak_key(p)),
    )
    if not ranked:
        return Selection((), {}, False, 0)

    chosen: list[tuple[Candidate, Annotations]] = []
    suppressed = 0

    def too_similar(c: Candidate) -> bool:
        for other, _ in chosen:
            if (
                other.provider_id == c.provider_id
                and other.day == c.day
                and abs(other.start_min - c.start_min) < diversity_window_min
            ):
                return True
        return False

    for pair in ranked:
        if len(chosen) >= want:
            break
        if too_similar(pair[0]):
            suppressed += 1
            continue
        chosen.append(pair)

    # Relax suppression rather than return fewer than three -- but relax it in
    # stages. Naively re-adding whatever was suppressed hands back the exact
    # near-duplicates the constraint exists to remove: three offers with the same
    # provider ten minutes apart is one option wearing three hats.
    if len(chosen) < want:
        picked = {c.candidate_id for c, _ in chosen}
        for window in (diversity_window_min // 2, 10, 0):
            for pair in ranked:
                if len(chosen) >= want:
                    break
                cand = pair[0]
                if cand.candidate_id in picked:
                    continue
                clash = any(
                    other.provider_id == cand.provider_id
                    and other.day == cand.day
                    and abs(other.start_min - cand.start_min) < window
                    for other, _ in chosen
                )
                if not clash:
                    chosen.append(pair)
                    picked.add(cand.candidate_id)
            if len(chosen) >= want:
                break

    spread_ok = len({c.day for c, _ in chosen}) >= 2 or len({c.provider_id for c, _ in chosen}) >= 2
    # Fewer than three options *is* limited availability, and a single option is the
    # most limited case there is. Requiring `len(chosen) > 1` inverted that: the one
    # result an operator most needs warned about was the one never flagged.
    limited = len(chosen) < want or not spread_ok

    groups: dict[str, int] = {}
    group = 0
    for i, (cand, ann) in enumerate(chosen):
        if i and abs((ann.score or 0.0) - (chosen[i - 1][1].score or 0.0)) > epsilon:
            group += 1
        groups[cand.candidate_id] = group

    for rank, (_cand, ann) in enumerate(chosen, start=1):
        ann.rank = rank
        ann.offered = True

    return Selection(
        offered=tuple(c.candidate_id for c, _ in chosen),
        coequal_groups=groups,
        limited_availability=limited,
        suppressed=suppressed,
    )


def nearest_overflow(cs: CandidateSet, want: int = 3) -> tuple[str, ...]:
    """FR-035/FR-038. When the top tier yields nothing, the soonest feasible options
    are offered anyway -- labelled, never silently mixed in. The system must never
    answer a patient in pain with an empty screen."""
    feasible = sorted(cs.feasible(), key=lambda p: (p[0].start, p[0].operatory_id))
    picked: list[str] = []
    seen_days: set[date] = set()
    for cand, ann in feasible:
        if len(picked) >= want:
            break
        if cand.day in seen_days and len(picked) >= 1:
            continue
        seen_days.add(cand.day)
        ann.overflow = True
        ann.offered = True
        picked.append(cand.candidate_id)
    return tuple(picked)
