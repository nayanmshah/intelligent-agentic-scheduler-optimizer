"""Characterization tests for the scoring curves and the tier boundaries.

Written in response to a mutation run: the suite scored **35.7%** against the decision
core, and `axes.py` alone had 119 surviving mutants. The existing tests assert the
pipeline's *shape* -- three offers, four contributions, a reason line on each -- and
almost never its arithmetic. So a scoring constant could be wrong, or a boundary
inclusive when it should be exclusive, and every test still passed.

These pin the numbers. They are deliberately table-driven and deliberately boring:
the point is that changing a constant in `axes.py` or `tiers.py` must break something.

**These are characterization tests, not correctness proofs.** They assert what the
curve *is*, which makes a change visible and deliberate. If a practice wants a
different curve, this file is the place that says so out loud.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.candidate import Candidate
from app.domain.enums import Urgency
from app.domain.request import (
    DateWindow,
    Exclusions,
    FieldValue,
    RequestConstraints,
    TimeWindow,
)
from app.reasoner.scoring import axes
from app.reasoner.tiers import tier_for

LA = ZoneInfo("America/Los_Angeles")
TODAY = date(2026, 8, 10)
DERIVED = {"derived": True, "derived_rule": "test-fixture"}


def constraints(
    *,
    window: TimeWindow | None = None,
    start: date = TODAY,
    end: date = date(2026, 8, 24),
    urgency: Urgency = Urgency.ROUTINE,
) -> RequestConstraints:
    return RequestConstraints(
        request_text="fixture",
        patient_ref="pat-000",
        date_range=FieldValue(
            value=DateWindow(start=start, end=end), confidence=0.9, **DERIVED
        ),
        time_window=FieldValue(value=window or TimeWindow(), confidence=0.9, **DERIVED),
        urgency=FieldValue(value=urgency, confidence=0.9, **DERIVED),
        provider_preference=FieldValue(value=None, confidence=0.9, **DERIVED),
        appointment_type=FieldValue(value="prophy_adult", confidence=0.9, **DERIVED),
        exclusions=FieldValue(value=Exclusions(), confidence=0.9, **DERIVED),
    )


def candidate(day: date, start_min: int) -> Candidate:
    return Candidate(
        candidate_id="c1",
        day=day,
        start=datetime.combine(day, datetime.min.time(), tzinfo=LA)
        + timedelta(minutes=start_min),
        start_min=start_min,
        duration_min=40,
        provider_id="prov-sarah",
        operatory_id="OP-1",
    )


# ================================================================== FR-040 ====
# The time-fit curve is piecewise: a slot 20 minutes outside the window is not the
# same as one two hours outside. Each row below is a point on that curve, including
# both sides of every boundary -- which is where an inclusive/exclusive slip hides.

WINDOW = TimeWindow(start_min=600, end_min=660)  # 10:00-11:00


@pytest.mark.parametrize(
    ("start_min", "expected", "why"),
    [
        (600, 1.00, "exactly at the window start, same day"),
        (660, 1.00, "exactly at the window end"),
        (630, 1.00, "inside"),
        (630 - 0, 1.00, "inside"),
        # 1..30 minutes out -> NEAR
        (599, axes.NEAR_VALUE, "1 minute early is NEAR, not perfect"),
        (570, axes.NEAR_VALUE, "30 minutes out is the last NEAR minute"),
        (690, axes.NEAR_VALUE, "30 minutes late is NEAR too"),
        # 31..60 -> MID
        (569, axes.MID_VALUE, "31 minutes out crosses into MID"),
        (540, axes.MID_VALUE, "60 minutes out is the last MID minute"),
        # 61..120 -> linear taper 0.6 -> 0.0
        (539, axes.MID_VALUE * (1 - 1 / 60), "61 minutes out begins the taper"),
        (510, axes.MID_VALUE * (1 - 30 / 60), "90 minutes out is mid-taper"),
        (480, 0.0, "120 minutes out is the taper's end"),
        # beyond
        (479, 0.0, "past 120 minutes the axis is exhausted"),
    ],
)
def test_the_time_fit_curve_has_the_shape_it_claims(
    start_min: int, expected: float, why: str
) -> None:
    result = axes.score_time_fit(candidate(TODAY, start_min), constraints(window=WINDOW), TODAY)
    assert result.value == pytest.approx(expected, abs=1e-9), why


def test_a_slot_inside_the_window_decays_slightly_with_distance_in_days() -> None:
    """Sooner is better, but only slightly -- capped, so a good slot next week still
    beats a poor one tomorrow. Without this, "soonest" quietly becomes the objective.
    """
    inside = TimeWindow(start_min=600, end_min=660)
    for days, expected in [(0, 1.0), (1, 0.99), (5, 0.95), (10, 0.90), (30, 0.90)]:
        day = TODAY + timedelta(days=days)
        r = axes.score_time_fit(
            candidate(day, 630), constraints(window=inside, end=day), TODAY
        )
        assert r.value == pytest.approx(expected, abs=1e-9), f"{days} days out"

    assert axes.SOONER_CAP == 0.10, "the decay cap is load-bearing for the claim above"


def test_a_day_outside_the_requested_range_is_demoted_not_merely_noted() -> None:
    """The demotion is multiplicative, so a perfect time on the wrong day still loses
    to a decent time on the right one."""
    outside_day = date(2026, 8, 26)  # past the requested end
    c = constraints(window=WINDOW, end=date(2026, 8, 24))

    # Compare like with like: the same slot 16 days out carries the sooner-decay
    # whether or not it is in range, so the demotion is what is left over.
    in_range_same_distance = constraints(window=WINDOW, end=outside_day)
    base = axes.score_time_fit(candidate(outside_day, 630), in_range_same_distance, TODAY)
    off_day = axes.score_time_fit(candidate(outside_day, 630), c, TODAY)

    assert off_day.value == pytest.approx(base.value * axes.MID_VALUE, abs=1e-9)
    assert off_day.value < base.value, "being on the wrong day must cost something"
    assert off_day.atom == "outside the days you asked about"
    assert off_day.concessive, "a wrong-day offer must be able to lead with the gap"


def test_only_a_miss_is_marked_as_a_concession() -> None:
    """The flag drives sentence order (FR-038). If everything were concessive the
    ordering would be meaningless."""
    c = constraints(window=WINDOW)
    assert not axes.score_time_fit(candidate(TODAY, 630), c, TODAY).concessive
    assert axes.score_time_fit(candidate(TODAY, 500), c, TODAY).concessive


# ================================================================== FR-041 ====
# Continuity tiers. The gaps between these numbers are the policy.


def test_the_continuity_tiers_are_ordered_and_distinct() -> None:
    assert axes.TIER_SAME > axes.TIER_POD > axes.TIER_SEEN > axes.TIER_NEW
    assert (axes.TIER_SAME, axes.TIER_POD, axes.TIER_SEEN, axes.TIER_NEW) == (
        1.0, 0.7, 0.4, 0.15,
    )


# ================================================================== FR-033 ====
# Tier boundaries are inclusive of the tier they name, and time-based tiers apply
# ONLY to an urgent request -- otherwise a request for Thursday is answered with
# Wednesday because Wednesday happens to fall inside 72 hours.

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=LA)


@pytest.mark.parametrize(
    ("hours_out", "expected"),
    [
        (0.5, Urgency.EMERGENCY),
        (24.0, Urgency.EMERGENCY),   # inclusive
        (24.01, Urgency.URGENT),
        (72.0, Urgency.URGENT),      # inclusive
        (72.01, Urgency.ROUTINE),    # falls through to what was asked for
    ],
)
def test_an_urgent_request_is_tiered_by_the_clock(hours_out: float, expected: Urgency) -> None:
    start = NOW + timedelta(hours=hours_out)
    tier = tier_for(start, NOW, constraints(urgency=Urgency.URGENT, end=date(2026, 8, 24)))
    assert tier is expected, f"{hours_out}h out"


@pytest.mark.parametrize("hours_out", [0.5, 24.0, 48.0, 72.0])
def test_a_routine_request_is_never_promoted_by_the_clock(hours_out: float) -> None:
    """The regression this encodes: applying time tiers unconditionally put every slot
    inside 72 hours into URGENT, so the day the patient actually asked for never
    competed."""
    start = NOW + timedelta(hours=hours_out)
    tier = tier_for(start, NOW, constraints(urgency=Urgency.ROUTINE, end=date(2026, 8, 24)))
    assert tier is Urgency.ROUTINE, f"a routine request was promoted at {hours_out}h"


def test_a_routine_slot_outside_the_requested_days_is_demoted_to_flexible() -> None:
    """What makes "outside the days you asked about" a demotion rather than a
    promotion for being soon."""
    start = datetime(2026, 8, 26, 10, 0, tzinfo=LA)
    tier = tier_for(start, NOW, constraints(urgency=Urgency.ROUTINE, end=date(2026, 8, 24)))
    assert tier is Urgency.FLEXIBLE


def test_the_tier_thresholds_are_the_documented_ones() -> None:
    """24h and 72h appear in the PRD, the architecture doc and the demo script. If
    they change, this is the test that makes it a decision rather than a diff."""
    from app.reasoner.tiers import _TIER_HOURS

    assert _TIER_HOURS[Urgency.EMERGENCY] == 24
    assert _TIER_HOURS[Urgency.URGENT] == 72


# ================================================================== FR-041 ====
# Continuity branch by branch. These decide which provider is preferred *and* what
# the offer card says about them, and every branch survived mutation.

from app.domain.entities import LastSeen, Patient, Provider  # noqa: E402
from app.domain.enums import Role  # noqa: E402


def provider(pid: str, *, pod: str | None = None, name: str | None = None) -> Provider:
    return Provider(
        id=pid, name=name or pid.replace("prov-", "").title(), role=Role.HYGIENIST,
        credentials=frozenset({"RDH"}), pod=pod,
    )


def patient(**kw) -> Patient:  # type: ignore[no-untyped-def]
    base = dict(id="pat-1", name="Test Patient", age_band="adult")
    base.update(kw)
    return Patient(**base)  # type: ignore[arg-type]


def hygiene_type():  # type: ignore[no-untyped-def]
    from app.domain.entities import AppointmentType

    return AppointmentType(
        id="prophy_adult", name="Adult cleaning", duration_min=40,
        required_credentials=frozenset({"RDH"}), production_value=1,
    )


def continuity(offered: Provider, pat: Patient | None, *, preference: str | None = None,
               roster: dict[str, Provider] | None = None):  # type: ignore[no-untyped-def]
    c = constraints()
    if preference is not None:
        c = c.model_copy(
            update={"provider_preference": FieldValue(
                value=preference, confidence=0.9, **DERIVED)}
        )
    return axes.score_continuity(
        candidate(TODAY, 600), offered, pat, hygiene_type(), c,
        roster or {p.id: p for p in [offered]},
    )


def test_the_provider_the_patient_named_beats_their_assigned_one() -> None:
    """AR-05. Without this, "drop the provider preference" is a no-op counterfactual --
    the axis would keep measuring affinity to someone the patient did not ask for."""
    asked_for = provider("prov-maya")
    pat = patient(assigned_hygienist_id="prov-sarah")

    r = continuity(asked_for, pat, preference="prov-maya",
                   roster={"prov-maya": asked_for, "prov-sarah": provider("prov-sarah")})
    assert r.value == axes.TIER_SAME
    assert r.atom == "the provider you asked for"
    assert not r.concessive


def test_the_usual_hygienist_is_the_target_for_a_hygiene_visit() -> None:
    sarah = provider("prov-sarah")
    r = continuity(sarah, patient(assigned_hygienist_id="prov-sarah"))
    assert r.value == axes.TIER_SAME
    assert r.atom == "your usual hygienist"


def test_who_they_saw_last_time_outranks_the_assignment() -> None:
    """A patient's actual history is a better signal than the roster field."""
    nia = provider("prov-nia")
    pat = patient(
        assigned_hygienist_id="prov-sarah",
        last_seen_by_type={"prophy_adult": LastSeen(provider_id="prov-nia", on=TODAY)},
    )
    r = continuity(nia, pat)
    assert r.value == axes.TIER_SAME
    assert r.atom == "the provider you saw last time"


def test_the_same_pod_scores_above_a_stranger_and_names_who_is_missing() -> None:
    sarah = provider("prov-sarah", pod="A")
    maya = provider("prov-maya", pod="A")
    r = continuity(maya, patient(assigned_hygienist_id="prov-sarah"),
                   roster={"prov-sarah": sarah, "prov-maya": maya})
    assert r.value == axes.TIER_POD
    assert axes.TIER_NEW < r.value < axes.TIER_SAME
    # Name the provider the patient *wanted*, never the one being offered.
    assert "Sarah" in r.caveat and "Maya" not in r.caveat
    assert r.concessive


def test_a_provider_seen_before_for_another_treatment_outranks_a_stranger() -> None:
    sarah, jo = provider("prov-sarah"), provider("prov-jo")
    pat = patient(
        assigned_hygienist_id="prov-sarah",
        last_seen_by_type={"perio_maint": LastSeen(provider_id="prov-jo", on=TODAY)},
    )
    r = continuity(jo, pat, roster={"prov-sarah": sarah, "prov-jo": jo})
    assert r.value == axes.TIER_SEEN
    assert r.concessive


def test_a_stranger_scores_lowest_and_says_who_was_wanted() -> None:
    sarah, jo = provider("prov-sarah"), provider("prov-jo")
    r = continuity(jo, patient(assigned_hygienist_id="prov-sarah"),
                   roster={"prov-sarah": sarah, "prov-jo": jo})
    assert r.value == axes.TIER_NEW
    assert "Sarah" in r.caveat
    assert r.concessive


def test_with_no_history_at_all_new_is_information_not_a_shortfall() -> None:
    """Nothing to fall short of, so this must NOT lead the sentence as a concession."""
    r = continuity(provider("prov-jo"), patient())
    assert r.value == axes.TIER_NEW
    assert not r.concessive, "a first-time patient was told the provider is a downgrade"


def test_continuity_survives_a_patient_we_know_nothing_about() -> None:
    r = continuity(provider("prov-jo"), None)
    assert r.value == axes.TIER_NEW
    assert not r.concessive


# ================================================================== FR-043 ====
# Orphan minutes. This is the arithmetic behind the product's headline claim -- "11x
# fewer orphan minutes than first-available" -- and it survived mutation entirely.
#
# The rule: a gap the booking leaves behind counts as orphaned only when it is too
# short to book anything into. Booking at the edge of a free stretch creates none;
# booking in the middle of it creates two.

from app.reasoner.availability import DayGrid  # noqa: E402

TURNOVER = 10
MIN_BOOKABLE = 30


def grid(busy: list[tuple[int, int]], open_min: int = 480, close_min: int = 1020) -> DayGrid:
    """A day with the given busy intervals, as the prefix sum the index uses."""
    prefix = [0]
    for minute in range(open_min, close_min):
        occupied = any(s <= minute < e for s, e in busy)
        prefix.append(prefix[-1] + (1 if occupied else 0))
    return DayGrid(open_min=open_min, close_min=close_min, prefix=tuple(prefix), version=0)


def orphans(free_from: int, free_to: int, book_at: int, duration: int = 40) -> int:
    """Orphan minutes created by booking inside a single free stretch."""
    busy = [(480, free_from), (free_to, 1020)]
    cand = candidate(TODAY, book_at)
    cand = Candidate(
        candidate_id="c", day=TODAY, start=cand.start, start_min=book_at,
        duration_min=duration, provider_id="prov-sarah", operatory_id="OP-1",
    )
    return axes._orphan_minutes(grid(busy), cand, TURNOVER, MIN_BOOKABLE)


def test_booking_at_the_start_of_a_free_stretch_orphans_nothing() -> None:
    """A 90-minute stretch, a 40-minute appointment placed flush at the front: the
    40 minutes left behind are still bookable, so nothing is wasted."""
    assert orphans(free_from=600, free_to=690, book_at=600) == 0


def test_booking_in_the_middle_of_a_free_stretch_orphans_both_sides() -> None:
    """The entire efficiency case in one assertion. Placing the same appointment 20
    minutes later strands 20 minutes in front and 20 behind -- neither bookable."""
    created = orphans(free_from=600, free_to=690, book_at=620)
    assert created > 0, "a middle placement wasted nothing, so the axis measures nothing"
    assert created == 20 + 20


def test_the_orphan_threshold_is_exactly_one_bookable_appointment() -> None:
    """Both sides of the boundary that separates "tight" from "wasted".

    A leftover of exactly ``min_bookable + turnover`` can still take an appointment,
    so it is not waste. One minute less cannot, so all of it is. Counting the first
    as waste would make the axis pessimistic everywhere; counting the second as fine
    would make it blind to the thing it exists to measure.
    """
    threshold = MIN_BOOKABLE + TURNOVER  # 40

    # Booking flush at the front leaves exactly `threshold` minutes behind.
    assert orphans(free_from=600, free_to=600 + 40 + TURNOVER + threshold, book_at=600) == 0

    # One minute less, and the whole remainder is stranded.
    assert orphans(
        free_from=600, free_to=600 + 40 + TURNOVER + threshold - 1, book_at=600
    ) == threshold - 1


def test_fragmentation_falls_as_orphan_minutes_rise() -> None:
    """The subterm the contribution bar renders. It must move in the right direction
    and bottom out rather than go negative."""
    from app.reasoner.scoring.axes import ORPHAN_CEILING_MIN

    assert ORPHAN_CEILING_MIN == 60
    for orphan, expected in [(0, 1.0), (30, 0.5), (60, 0.0), (120, 0.0)]:
        assert max(0.0, 1.0 - orphan / ORPHAN_CEILING_MIN) == pytest.approx(expected)
