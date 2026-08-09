"""The write path and the timezone boundary.

Both were documented as verified and neither had a single test. A QA pass found the
claims before a user did, which is the only acceptable order.

**Why these two together.** They are the places where a bug is silent. A ranking bug
shows up as a bad suggestion an operator can override; a double-booking shows up as two
patients in one chair, and a DST bug shows up on one Sunday morning a year.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.config import get_settings
from app.data.loader import load_seed
from app.data.repository import BookingIntent
from app.data.session import MemoryScheduleRepository, SessionState
from app.data.timezone import (
    NonexistentLocalTime,
    business_days,
    day_length_minutes,
    is_ambiguous,
    is_nonexistent,
    to_instant,
    to_local,
)

SETTINGS = get_settings()
LA = ZoneInfo("America/Los_Angeles")

# 2026: DST starts Sunday 8 March, ends Sunday 1 November.
SPRING_FORWARD = date(2026, 3, 8)
FALL_BACK = date(2026, 11, 1)
ORDINARY = date(2026, 8, 12)

#: A weekday inside the bookable window, used for every write-path test.
DAY = date(2026, 8, 24)


@pytest.fixture
def repo():  # type: ignore[no-untyped-def]
    """A fresh session per test -- the write path mutates, so isolation is the point."""
    bundle = load_seed(SETTINGS.seed_dir).bundle
    return MemoryScheduleRepository(SessionState.from_seed(bundle))


def free_slot(repo, day: date, duration: int = 60) -> tuple[int, str, str]:
    """Find a genuinely empty (minute, operatory, provider) on ``day``.

    Derived from the repository rather than hardcoded: the seed is regenerable, and a
    test that hardcodes 08:00 fails for the wrong reason the moment the generator
    places something there -- which is exactly what happened when these were written.
    """
    for op in (o.id for o in repo.seed.operatories):
        for prov in (p.id for p in repo.seed.providers):
            taken = [
                (to_local(a.start, LA)[1], to_local(a.start, LA)[1] + a.duration_min)
                for a in repo.appointments_on(day)
                if a.operatory_id == op or a.provider_id == prov
            ]
            for minute in range(8 * 60, 17 * 60 - duration, 10):
                end = minute + duration
                if all(end <= s or minute >= e for s, e in taken):
                    return minute, op, prov
    raise AssertionError(f"no free slot on {day} -- the fixture cannot test a booking")


def intent(repo, day: date, start_min: int, *, request_id="req-1", **kw):  # type: ignore[no-untyped-def]
    defaults = dict(
        candidate_id="cand-1",
        duration_min=60,
        provider_id="prov-sarah",
        operatory_id="OP-1",
        patient_id="pat-000",
        type_id="prophy_adult",
        request_id=request_id,
    )
    defaults.update(kw)
    return BookingIntent(
        start=to_instant(day, start_min, LA),
        **defaults,  # type: ignore[arg-type]
    )


# ================================================================== ADR-18 ====
# The conditional write. Check-then-write cannot fail at one seat and double-books
# at two -- the worst possible pairing of severity and undetectability.


def test_a_booking_succeeds_when_the_cell_version_still_matches(repo) -> None:
    day = DAY
    start, op, prov = free_slot(repo, day)
    expect = repo.version_of(op, day)

    result = repo.commit_booking(
        intent(repo, day, start, operatory_id=op, provider_id=prov), expect
    )

    assert result.ok, result.error
    assert result.appointment is not None
    assert result.appointment.operatory_id == op


def test_a_stale_version_loses_and_is_told_so(repo) -> None:
    """The compare-and-set itself. This is the whole reason the write is conditional:
    a caller that re-verified against an older view of the world must not win."""
    day = DAY
    start, op, prov = free_slot(repo, day)
    stale = repo.version_of(op, day)

    # Somebody else changes the cell in between.
    repo.invalidate(op, day)

    result = repo.commit_booking(
        intent(repo, day, start, operatory_id=op, provider_id=prov), stale
    )

    assert not result.ok
    assert result.error == "SLOT_TAKEN"
    assert result.appointment is None


def test_the_version_moves_after_a_successful_booking(repo) -> None:
    """Otherwise a second caller holding the same version would also win, and the
    compare-and-set would be decorative."""
    day = DAY
    start, op, prov = free_slot(repo, day)
    before = repo.version_of(op, day)

    assert repo.commit_booking(
        intent(repo, day, start, operatory_id=op, provider_id=prov), before
    ).ok
    assert repo.version_of(op, day) != before


def test_two_callers_holding_the_same_version_cannot_both_book(repo) -> None:
    """The double-booking scenario, played out. Both read the same version, both
    submit; exactly one may win."""
    day = DAY
    start, op, prov = free_slot(repo, day)
    shared = repo.version_of(op, day)

    kw = {"operatory_id": op, "provider_id": prov}
    first = repo.commit_booking(intent(repo, day, start, request_id="req-a", **kw), shared)
    second = repo.commit_booking(intent(repo, day, start, request_id="req-b", **kw), shared)

    assert first.ok
    assert not second.ok, "two bookings were accepted for one slot"
    assert second.error == "SLOT_TAKEN"


def test_an_overlapping_room_booking_is_refused(repo) -> None:
    """Version matching is necessary, not sufficient: a fresh version says nothing
    about whether the minutes are free."""
    day = DAY
    start, op, prov = free_slot(repo, day)
    assert repo.commit_booking(
        intent(repo, day, start, operatory_id=op, provider_id=prov), repo.version_of(op, day)
    ).ok

    other = next(p.id for p in repo.seed.providers if p.id != prov)
    overlap = repo.commit_booking(
        intent(repo, day, start + 30, request_id="req-b", operatory_id=op, provider_id=other),
        repo.version_of(op, day),
    )
    assert not overlap.ok
    assert overlap.error == "SLOT_TAKEN"


def test_a_provider_cannot_be_in_two_rooms_at_once(repo) -> None:
    """The room is free and the version is current, and it is still not bookable --
    the provider is the constraint. A room-only check would miss this."""
    day = DAY
    start, op, prov = free_slot(repo, day)
    assert repo.commit_booking(
        intent(repo, day, start, operatory_id=op, provider_id=prov), repo.version_of(op, day)
    ).ok

    other_room = next(o.id for o in repo.seed.operatories if o.id != op)
    same_provider_other_room = repo.commit_booking(
        intent(repo, day, start, request_id="req-b", operatory_id=other_room, provider_id=prov),
        repo.version_of(other_room, day),
    )
    assert not same_provider_other_room.ok
    assert same_provider_other_room.error == "SLOT_TAKEN"


def test_a_non_overlapping_booking_in_the_same_room_is_allowed(repo) -> None:
    """The negative control. Without this the tests above would pass on a repository
    that refused everything."""
    day = DAY
    start, op, prov = free_slot(repo, day)
    assert repo.commit_booking(
        intent(repo, day, start, operatory_id=op, provider_id=prov), repo.version_of(op, day)
    ).ok

    later_start, later_op, later_prov = free_slot(repo, day)
    later = repo.commit_booking(
        intent(repo, day, later_start, request_id="req-b",
               operatory_id=later_op, provider_id=later_prov),
        repo.version_of(later_op, day),
    )
    assert later.ok, later.error


def test_committing_releases_that_request_s_holds_and_leaves_others_alone(repo) -> None:
    """A hold that outlives its booking silently removes capacity for its whole TTL."""
    from app.domain.entities import Hold

    day = DAY
    start, op, prov = free_slot(repo, day)
    now = SETTINGS.reference_now
    for rid in ("req-1", "req-other"):
        repo.place_hold(
            Hold(
                id=f"hold-{rid}", candidate_id="cand-1", request_id=rid,
                operatory_id=op, provider_id=prov,
                start=to_instant(day, start, LA), duration_min=60,
                expires_at=now + timedelta(minutes=5),
            )
        )

    assert repo.commit_booking(
        intent(repo, day, start, operatory_id=op, provider_id=prov), repo.version_of(op, day)
    ).ok

    remaining = {h.request_id for h in repo.holds()}
    assert "req-1" not in remaining, "the booked request's hold outlived its booking"
    assert "req-other" in remaining, "an unrelated request's hold was released"


# ================================================================== NFR-32 ====
# DST. Neither transition falls inside the seeded window, which is exactly why these
# are written down: the bug is invisible until the one Sunday it is not.


def test_a_spring_forward_day_is_23_hours_long(repo) -> None:
    assert day_length_minutes(SPRING_FORWARD, LA) == 23 * 60


def test_a_fall_back_day_is_25_hours_long(repo) -> None:
    assert day_length_minutes(FALL_BACK, LA) == 25 * 60


def test_an_ordinary_day_is_24_hours_long(repo) -> None:
    """The control. Any code assuming 1440 is right ~363 days a year, which is what
    makes the other two so easy to ship."""
    assert day_length_minutes(ORDINARY, LA) == 24 * 60


def test_the_hour_that_does_not_exist_is_detected(repo) -> None:
    """02:00-02:59 on the spring-forward day never happens. Offering an appointment
    inside it produces a confirmation for a time the patient cannot attend."""
    assert is_nonexistent(SPRING_FORWARD, 2 * 60 + 30, LA)
    assert not is_nonexistent(SPRING_FORWARD, 9 * 60, LA)
    assert not is_nonexistent(ORDINARY, 2 * 60 + 30, LA)


def test_the_hour_that_happens_twice_is_detected(repo) -> None:
    """01:00-01:59 on the fall-back day occurs twice. "1:30am" identifies two distinct
    instants, an hour apart."""
    assert is_ambiguous(FALL_BACK, 1 * 60 + 30, LA)
    assert not is_ambiguous(FALL_BACK, 9 * 60, LA)
    assert not is_ambiguous(ORDINARY, 1 * 60 + 30, LA)


def test_local_and_utc_round_trip_across_both_transitions(repo) -> None:
    """The conversion boundary is one module (NFR-32) precisely so this can be
    asserted in one place. Business hours are used, so no ambiguous or nonexistent
    time is involved -- a normal appointment must survive a DST day untouched."""
    for day in (SPRING_FORWARD, FALL_BACK, ORDINARY):
        for minute in (8 * 60, 12 * 60, 16 * 60 + 40):
            utc = to_instant(day, minute, LA)
            assert utc.tzinfo is not None, "the boundary produced a naive datetime"
            back_day, back_minute = to_local(utc, LA)
            assert (back_day, back_minute) == (day, minute)


def test_business_days_skips_weekends(repo) -> None:
    days = business_days(date(2026, 8, 10), date(2026, 8, 16))
    assert days == [date(2026, 8, d) for d in (10, 11, 12, 13, 14)]


def test_every_datetime_leaving_the_boundary_is_aware(repo) -> None:
    """NFR-32's whole point. A naive value crossing this line is the bug class the
    structural guard exists to prevent, so the runtime behaviour is asserted too."""
    assert to_instant(ORDINARY, 9 * 60, LA).utcoffset() is not None
    with pytest.raises(ValueError, match="requires a timezone-aware"):
        to_local(datetime(2026, 8, 12, 9, 0), LA)


def test_booking_a_time_that_does_not_exist_raises_rather_than_shifting(repo) -> None:
    """``strict`` is the default for exactly this reason. Silently shifting a
    spring-forward appointment puts it an hour off with nobody noticing until the
    patient arrives."""
    with pytest.raises(NonexistentLocalTime):
        to_instant(SPRING_FORWARD, 2 * 60 + 30, LA)

    # Opting out is explicit, and still produces an aware value.
    assert to_instant(SPRING_FORWARD, 2 * 60 + 30, LA, strict=False).utcoffset() is not None
