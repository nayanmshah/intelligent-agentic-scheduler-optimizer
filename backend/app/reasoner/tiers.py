"""Layer 1 -- the urgency gate. A gate, not a weight (FR-032).

Scored as a weight, urgency would price pain against convenience on the same axis,
and a sufficiently strong preference for convenience could outrank a genuine
emergency. Because tiering happens *before* any weight is applied, the property test
over 200 random weight vectors passes by construction: no weight vector is ever
consulted when comparing across tiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.candidate import CandidateSet
from app.domain.enums import Urgency
from app.domain.request import RequestConstraints

_TIER_HOURS = {Urgency.EMERGENCY: 24, Urgency.URGENT: 72}


@dataclass(frozen=True, slots=True)
class TierOutcome:
    tier: Urgency | None
    in_tier: int
    escalated: bool
    exhausted: bool  # nothing in any tier -> overflow


def tier_for(candidate_start: datetime, now: datetime, constraints: RequestConstraints) -> Urgency:
    """FR-033. Boundaries are inclusive of the tier they name.

    **The time-based tiers apply only when the request itself is urgent.** The gate
    exists to triage a patient in pain ahead of optimisation -- not to reorder a
    routine request around the calendar. Applying them unconditionally puts every
    slot inside 72 hours into the URGENT tier, so a request for Thursday gets
    answered with Wednesday and the requested day never even competes.
    """
    asked = constraints.urgency.value

    if asked.at_least(Urgency.URGENT):
        hours_out = (candidate_start - now).total_seconds() / 3600.0
        if hours_out <= _TIER_HOURS[Urgency.EMERGENCY]:
            return Urgency.EMERGENCY
        if hours_out <= _TIER_HOURS[Urgency.URGENT]:
            return Urgency.URGENT

    # Routine and flexible requests are tiered by *what was asked for*, which is what
    # makes "outside the days you asked about" a demotion rather than a promotion.
    if constraints.date_range.value.contains(candidate_start.date()):
        return Urgency.ROUTINE
    return Urgency.FLEXIBLE


def apply_gate(cs: CandidateSet, now: datetime, constraints: RequestConstraints) -> TierOutcome:
    """Assign tiers, then mark only the highest non-empty tier as in-play (FR-034)."""
    for c, a in cs.pairs():
        if a.feasible:
            a.tier = tier_for(c.start, now, constraints)

    for tier in (Urgency.EMERGENCY, Urgency.URGENT, Urgency.ROUTINE, Urgency.FLEXIBLE):
        members = [(c, a) for c, a in cs.pairs() if a.feasible and a.tier is tier]
        if not members:
            continue
        # A request never gets a tier more urgent than it asked for: an emergency-tier
        # slot is offered to a routine request only as an ordinary early option.
        for _, a in members:
            a.in_tier = True
        return TierOutcome(tier=tier, in_tier=len(members), escalated=False, exhausted=False)

    return TierOutcome(tier=None, in_tier=0, escalated=False, exhausted=True)
