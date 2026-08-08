"""The four axes.

Each scorer returns ``(value, atom_text)`` -- the number and the words for the number
have a **single origin**. That is the mechanism behind SD-2: there is no code path by
which an explanation could describe a component that did not contribute.

No numeric weight literal appears in this package; a structural test enforces it
(FR-046). The tunable constants live in ``Settings``, and the axis *weights* live in
``WeightProfile``. Shape parameters that define an axis (where the time-fit taper
begins, what counts as an orphan gap) are named constants here because they are part
of the axis's definition, not of practice policy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.domain.candidate import Candidate, EfficiencySubterms
from app.domain.entities import AppointmentType, Patient, Provider, ScheduleBlock
from app.domain.request import RequestConstraints
from app.reasoner.availability import AvailabilityIndex

# Axis shape, per FR-040 and [A-10]. These describe the curve, not the policy.
NEAR_BOUNDARY_MIN = 30
MID_BOUNDARY_MIN = 60
FAR_BOUNDARY_MIN = 120
NEAR_VALUE = 0.85
MID_VALUE = 0.6
SOONER_STEP = 0.01
SOONER_CAP = 0.10

# Continuity tiers, per FR-041.
TIER_SAME = 1.0
TIER_POD = 0.7
TIER_SEEN = 0.4
TIER_NEW = 0.15

ORPHAN_CEILING_MIN = 60


@dataclass(frozen=True, slots=True)
class AxisResult:
    value: float
    atom: str
    #: How this axis phrases itself when it is the *downside* rather than a reason
    #: the slot won. Supplied by the axis because only the axis knows what it was
    #: comparing against -- a generic caveat writer named the offered provider and
    #: produced "though it is not Maya" on an offer with Maya.
    caveat: str = ""
    #: True when ``atom`` names a *shortfall* rather than a reason the slot won.
    #: Ranking atoms purely by weighted contribution buries exactly these: an axis
    #: that scored badly is the one the operator must hear about, and it sorts last.
    concessive: bool = False


def score_time_fit(
    cand: Candidate, constraints: RequestConstraints, today: date
) -> AxisResult:
    """Piecewise, not binary (FR-040). A slot 20 minutes outside the window is not
    the same as one two hours outside, and a binary axis would say it was."""
    window = constraints.time_window.value
    miss = window.distance_outside(cand.start_min)

    concessive = miss > 0
    if miss == 0:
        days_out = (cand.day - today).days
        value = 1.0 - min(SOONER_CAP, SOONER_STEP * days_out)
        atom = "in the window you asked for"
    elif miss <= NEAR_BOUNDARY_MIN:
        value = NEAR_VALUE
        atom = f"{miss} minutes either side of the time you asked for"
    elif miss <= MID_BOUNDARY_MIN:
        value = MID_VALUE
        atom = "about an hour from the time you asked for"
    elif miss <= FAR_BOUNDARY_MIN:
        # Linear taper 0.6 -> 0.0 across 60 -> 120 minutes [A-10].
        span = FAR_BOUNDARY_MIN - MID_BOUNDARY_MIN
        value = MID_VALUE * (1.0 - (miss - MID_BOUNDARY_MIN) / span)
        atom = "a couple of hours from the time you asked for"
    else:
        value = 0.0
        atom = "well outside the time you asked for"

    if not constraints.date_range.value.contains(cand.day):
        value *= MID_VALUE
        atom = "outside the days you asked about"
        concessive = True
    return AxisResult(max(0.0, min(1.0, value)), atom,
                      caveat="though it is not the time you asked for",
                      concessive=concessive)


def score_continuity(
    cand: Candidate,
    provider: Provider,
    patient: Patient | None,
    appointment_type: AppointmentType,
    constraints: RequestConstraints,
    providers: dict[str, Provider],
) -> AxisResult:
    """Tiered, and type-dependent through the multiplier applied at weight time.

    [AR-05] A stated provider preference *overrides the target*: continuity then
    measures affinity to the provider the patient named, not to their assigned one.
    Without that, "drop the provider preference" would be a no-op counterfactual.
    """
    preferred = constraints.provider_preference.value
    target_id: str | None = preferred
    label = "the provider you asked for"

    if target_id is None and patient is not None:
        seen = patient.last_seen_by_type.get(appointment_type.id)
        if seen is not None:
            target_id, label = seen.provider_id, "the provider you saw last time"
        elif appointment_type.required_credentials & {"RDH"}:
            target_id, label = patient.assigned_hygienist_id, "your usual hygienist"
        else:
            target_id, label = patient.assigned_dentist_id, "your usual dentist"

    if target_id is None:
        # No usual provider to fall short of, so "new to you" is information, not a
        # shortfall.
        return AxisResult(TIER_NEW, "a provider who is new to you",
                          caveat="though this provider is new to you")
    if provider.id == target_id:
        return AxisResult(TIER_SAME, label, caveat="")

    target = providers.get(target_id)
    # Name the provider the patient wanted, never the one being offered.
    wanted = target.name.split()[-1] if target is not None else "your usual provider"
    if target is not None and target.pod and target.pod == provider.pod:
        return AxisResult(TIER_POD, "someone on the same team as your usual provider",
                          caveat=f"though it is not {wanted}", concessive=True)
    if patient is not None and any(
        s.provider_id == provider.id for s in patient.last_seen_by_type.values()
    ):
        return AxisResult(TIER_SEEN, "a provider you have seen before",
                          caveat=f"though it is not {wanted}", concessive=True)
    return AxisResult(TIER_NEW, "a provider who is new to you",
                      caveat=f"though it is not {wanted}", concessive=True)


def score_efficiency(
    cand: Candidate,
    index: AvailabilityIndex,
    turnover: int,
    min_bookable: int,
    operatory_ids: tuple[str, ...],
) -> tuple[float, str, EfficiencySubterms]:
    """Composite of four sub-terms (FR-042), each separately inspectable."""
    grid = index.cell(cand.operatory_id, cand.day)
    if grid is None:
        sub = EfficiencySubterms(0.0, 0.0, 0.0, 0.0)
        return 0.0, "no effect on the shape of the day", sub

    orphan = _orphan_minutes(grid, cand, turnover, min_bookable)
    fragmentation = max(0.0, 1.0 - orphan / ORPHAN_CEILING_MIN)

    span = grid.close_min - grid.open_min
    idle = 1.0 - (index.busy_minutes(cand.provider_id, cand.day) / span if span else 0.0)

    check_load = _check_slack(index, cand)

    loads = [index.busy_minutes(o, cand.day) for o in operatory_ids]
    spread = (max(loads) - min(loads)) / span if span and loads else 0.0
    balance = max(0.0, 1.0 - spread)

    sub = EfficiencySubterms(fragmentation, idle, check_load, balance)
    value = sub.composite()

    if orphan == 0:
        atom = "it fills a gap between two existing appointments exactly"
    elif fragmentation < MID_VALUE:
        atom = "it would leave an awkward gap in the day"
    else:
        atom = "it fits the shape of the day well"
    return value, atom, sub


def _orphan_minutes(grid, cand: Candidate, turnover: int, min_bookable: int) -> int:  # type: ignore[no-untyped-def]
    """Minutes of newly-created gap too short to book anything into (FR-043).

    Booking in the middle of a 90-minute stretch creates two 30-minute orphans;
    booking at its edge creates none. That difference is the entire efficiency case.
    """
    lo, hi = grid.open_min, grid.close_min
    start, end = cand.start_min, cand.start_min + cand.duration_min + turnover

    before = 0
    probe = start - 1
    while probe >= lo and grid.free(probe, probe + 1):
        before += 1
        probe -= 1
    after = 0
    probe = end
    while probe < hi and grid.free(probe, probe + 1):
        after += 1
        probe += 1

    orphan = 0
    if 0 < before < min_bookable + turnover:
        orphan += before
    if 0 < after < min_bookable + turnover:
        orphan += after
    return orphan


def _check_slack(index: AvailabilityIndex, cand: Candidate) -> float:
    """Feasible-but-tight is not the same as good (FR-044)."""
    free_dentists = sum(
        1
        for d in index.dentists
        if index.is_free(d.id, cand.day, cand.start_min, cand.start_min + cand.duration_min)
    )
    total = max(1, len(index.dentists))
    return free_dentists / total


def score_prime_time(
    cand: Candidate,
    appointment_type: AppointmentType,
    patient: Patient | None,
    blocks: Sequence[ScheduleBlock],
) -> AxisResult:
    """Negative-going (FR-045). The schedule has a shape the practice wants, and the
    optimizer defends that shape rather than rediscovering it on every request."""
    end = cand.start_min + cand.duration_min
    worst = 1.0
    atom = "it does not disturb the protected part of the day"

    for b in blocks:
        if b.scope_ref not in (None, cand.operatory_id):
            continue
        overlap = min(end, b.end_min) - max(cand.start_min, b.start_min)
        if overlap <= 0:
            continue
        fraction = overlap / cand.duration_min

        if b.kind.value == "restorative_block":
            floor = b.min_production_value or 0
            if appointment_type.production_value < floor:
                worst = min(worst, 1.0 - fraction)
                atom = "it uses time the practice keeps for longer treatments"
        elif b.kind.value == "pedo_after_school":
            # A school-age patient at 3-5pm is not penalised -- the block is *for* them.
            if patient is not None and not patient.is_school_age:
                worst = min(worst, 1.0 - fraction)
                atom = "it uses time the practice keeps for after-school visits"
    return AxisResult(max(0.0, worst), atom,
                      caveat="though it uses a busier part of the day",
                      concessive=worst < 1.0)
