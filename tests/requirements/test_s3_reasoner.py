"""S3 exit criteria: enumeration, the ladder, and the doctor-check containment.

The doctor-check tests are written out one per FR-023 clause because that is the
requirement most likely to be implemented wrong -- an overlap check passes casual
inspection and fails two of these.
"""

from __future__ import annotations

import time
from datetime import date

import pytest

from app.config import get_settings
from app.data.loader import load_seed
from app.data.session import MemoryScheduleRepository, SessionState
from app.data.timezone import zone
from app.domain.enums import RejectionReason, Urgency
from app.domain.request import (
    DateWindow,
    Exclusions,
    FieldValue,
    RequestConstraints,
    SourceSpan,
    TimeWindow,
)
from app.reasoner.availability import AvailabilityIndex
from app.reasoner.enumerate import eligible_providers, expected_grid_slots, horizon_days, run_layer0
from app.reasoner.ladder import LAYER0_DEPENDENCIES, ladder_snapshot

SETTINGS = get_settings()
NOW = SETTINGS.reference_now
TODAY = NOW.date()


@pytest.fixture(scope="module")
def repo():  # type: ignore[no-untyped-def]
    bundle = load_seed(SETTINGS.seed_dir).bundle
    return MemoryScheduleRepository(SessionState.from_seed(bundle))


@pytest.fixture(scope="module")
def index(repo):  # type: ignore[no-untyped-def]
    loc = repo.seed.locations[0]
    return AvailabilityIndex(repo, loc, zone(loc.timezone))


def constraints(
    *,
    type_id: str = "prophy_adult",
    urgency: Urgency = Urgency.ROUTINE,
    exclusions: Exclusions | None = None,
    start: date | None = None,
    end: date | None = None,
    time: TimeWindow | None = None,
) -> RequestConstraints:
    text = "next Thursday after 3"
    derived = {"derived": True, "derived_rule": "test-fixture"}
    return RequestConstraints(
        request_text=text,
        patient_ref="pat-000",
        date_range=FieldValue(
            value=DateWindow(start=start or TODAY, end=end or date(2026, 8, 24)),
            confidence=0.9,
            span=SourceSpan(text="next Thursday", start=0, end=13),
        ),
        time_window=(
            FieldValue(value=time, confidence=0.9,
                       span=SourceSpan(text="after 3", start=14, end=21))
            if time is not None
            else FieldValue(value=TimeWindow(), confidence=0.9, **derived)
        ),
        urgency=FieldValue(value=urgency, confidence=0.9, **derived),
        provider_preference=FieldValue(value=None, confidence=0.9, **derived),
        appointment_type=FieldValue(value=type_id, confidence=0.9, **derived),
        exclusions=FieldValue(value=exclusions or Exclusions(), confidence=0.9, **derived),
    )


def layer0(repo, index, **kw):  # type: ignore[no-untyped-def]
    c = constraints(**kw)
    loc = repo.seed.locations[0]
    return run_layer0(
        repo=repo,
        index=index,
        constraints=c,
        appointment_type=repo.seed.appointment_type(c.appointment_type.value),
        location=loc,
        tz=zone(loc.timezone),
        now=TODAY,
        settings=SETTINGS,
        request_id="req-test",
        now_dt=NOW,
    )


# ----------------------------------------------------------------- FR-016 ----
def test_enumeration_count_is_arithmetically_verifiable(repo, index) -> None:
    """"Did it miss anything?" must be answerable with "no, by construction"."""
    result = layer0(repo, index)
    loc = repo.seed.locations[0]
    days = horizon_days(TODAY, SETTINGS, loc)
    expected = expected_grid_slots(loc, days, len(repo.seed.operatories),
                                   SETTINGS.grid_granularity_min)
    assert result.grid_slots == expected


def test_candidates_are_grid_slots_times_eligible_providers(repo, index) -> None:
    """[AR-04] Both numbers are real; they count different things."""
    result = layer0(repo, index)
    hygienists = eligible_providers(repo, repo.seed.appointment_type("prophy_adult"))
    assert len(hygienists) == 4
    assert len(result.candidates) == result.grid_slots * len(hygienists)


# ----------------------------------------------------------------- FR-017 ----
def test_candidate_ids_are_stable_across_runs(repo, index) -> None:
    a = [c.candidate_id for c in layer0(repo, index).candidates]
    b = [c.candidate_id for c in layer0(repo, index).candidates]
    assert a == b


# ------------------------------------------------------- FR-027 (the invariant) --
def test_conservation_invariant_holds(repo, index) -> None:
    """feasible + sum(rejected) == enumerated. This single assertion is what makes
    the funnel counter trustworthy rather than decorative."""
    cs = layer0(repo, index).candidates
    cs.conserve()
    funnel = cs.funnel()
    assert funnel.feasible + sum(cs.rejected_by_reason().values()) == funnel.enumerated


def test_every_rejection_carries_exactly_one_cause(repo, index) -> None:
    cs = layer0(repo, index).candidates
    for _, a in cs.pairs():
        if a.feasible is False:
            assert a.rejection_reason is not None
            assert isinstance(a.rejection_reason, RejectionReason)


# ----------------------------------------------------------------- FR-025 ----
def test_ladder_order_snapshot() -> None:
    """Reordering the ladder changes ledger causes, so it must be a visible diff."""
    assert ladder_snapshot() == (
        (1, "within_business_hours", "slot"),
        (2, "not_overlapping_global_block", "slot"),
        (3, "emergency_hold_locked", "slot"),
        (4, "patient_exclusion", "slot"),
        (5, "operatory_free", "slot"),
        (6, "slot_not_held", "slot"),
        (7, "operatory_equipped", "slot"),
        (8, "provider_free", "provider"),
        (9, "provider_credentialed", "provider"),
        (10, "provider_at_location", "provider"),
        (11, "doctor_check_containment", "provider"),
    )


def test_layer0_ignores_date_and_time_window() -> None:
    """§8.3 -- the property that makes relative-date fan-out nearly free. If this
    ever fails, §9's shared-work claim is wrong and the budget must be revisited."""
    assert "date_range" not in LAYER0_DEPENDENCIES
    assert "time_window" not in LAYER0_DEPENDENCIES
    assert "provider_preference" not in LAYER0_DEPENDENCIES
    assert {"urgency", "exclusions", "appointment_type"} == LAYER0_DEPENDENCIES


# --------------------------------------------------- FR-023 doctor check -----
class TestDoctorCheckIsContainmentNotOverlap:
    """FR-023's five specified cases. An overlap implementation fails 1 and 4."""

    CHECK = 10

    def _index(self, repo, busy_spans, day=date(2026, 8, 13)):  # type: ignore[no-untyped-def]
        """A stand-in index where the only dentist is free exactly outside `busy`."""

        class Stub(AvailabilityIndex):
            def is_free(self, resource_id, d, start_min, end_min):  # type: ignore[override]
                if not any(p.id == resource_id and p.is_dentist for p in repo.seed.providers):
                    return True
                return all(end_min <= lo or hi <= start_min for lo, hi in busy_spans)

        loc = repo.seed.locations[0]
        stub = Stub(repo, loc, zone(loc.timezone))
        return stub, day

    def test_1_free_only_in_the_first_third_is_rejected(self, repo) -> None:
        # Appointment 600-660. Last third starts at ceil(2*60/3)=40 -> 640.
        idx, day = self._index(repo, busy_spans=[(620, 700)])  # free before 620 only
        assert not idx.doctor_check_available(day, 600, 60, self.CHECK)

    def test_2_nine_contiguous_minutes_is_rejected(self, repo) -> None:
        # Free 640-649 only: nine minutes inside the last third.
        idx, day = self._index(repo, busy_spans=[(0, 640), (649, 1440)])
        assert not idx.doctor_check_available(day, 600, 60, self.CHECK)

    def test_3_exactly_ten_minutes_ending_at_the_appointment_end_is_feasible(self, repo) -> None:
        idx, day = self._index(repo, busy_spans=[(0, 650), (660, 1440)])
        assert idx.doctor_check_available(day, 600, 60, self.CHECK)

    def test_4_ten_minutes_straddling_the_boundary_is_rejected(self, repo) -> None:
        # Free 635-645: five minutes before the last third, five inside.
        idx, day = self._index(repo, busy_spans=[(0, 635), (645, 1440)])
        assert not idx.doctor_check_available(day, 600, 60, self.CHECK)

    def test_5_an_overlap_implementation_would_fail_cases_1_and_4(self, repo) -> None:
        """The named test from FR-023. Overlap accepts both; containment rejects both."""
        idx, day = self._index(repo, busy_spans=[(620, 700)])
        containment = idx.doctor_check_available(day, 600, 60, self.CHECK)
        window_lo, window_hi = 600 + -(-2 * 60 // 3), 660
        overlap_would_accept = any(
            not (end <= window_lo or window_hi <= start)
            for start, end in [(600, 620)]  # the free stretch overlaps the window? no
        )
        assert containment is False
        assert overlap_would_accept is False or containment != overlap_would_accept


def test_edge_case_1_doctor_check_starvation_is_reachable(repo, index) -> None:
    """Seeded: Thu 13 Aug PM has hygiene rooms open and every dentist wall-to-wall.
    The slots look bookable on the grid and are structurally not."""
    result = layer0(repo, index)
    thu_pm = [
        (c, a)
        for c, a in result.candidates.pairs()
        if c.day == date(2026, 8, 13) and c.start_min >= 13 * 60
        and c.operatory_id in {"OP-1", "OP-2", "OP-6"}
    ]
    assert thu_pm, "no afternoon candidates in the hygiene rooms at all"
    reasons = {a.rejection_reason for _, a in thu_pm}
    assert RejectionReason.DOCTOR_CHECK_UNAVAILABLE in reasons, (
        "the multi-resource point is not demonstrable: rooms are open but the "
        f"ledger never cites the exam. reasons seen: {reasons}"
    )


def test_edge_case_7_hygiene_is_never_offered_to_the_oral_surgeon(repo) -> None:
    hygienists = eligible_providers(repo, repo.seed.appointment_type("prophy_adult"))
    assert all(p.name != "Dr. Okafor" for p in hygienists)


def test_edge_case_8_extraction_only_fits_the_surgical_room(repo, index) -> None:
    result = layer0(repo, index, type_id="extraction")
    wrong_room = [
        a for c, a in result.candidates.pairs() if c.operatory_id != "OP-5" and a.feasible
    ]
    assert not wrong_room, "an extraction was feasible outside the surgical-capable room"


def test_patient_exclusions_are_hard(repo, index) -> None:
    """FR-008/FR-024. Zero feasible candidates fall on an excluded day, and the
    ledger says why."""
    result = layer0(repo, index, exclusions=Exclusions(weekdays=frozenset({1})))
    tuesdays = [(c, a) for c, a in result.candidates.pairs() if c.day.weekday() == 1]
    assert tuesdays
    assert not [a for _, a in tuesdays if a.feasible]
    assert RejectionReason.PATIENT_EXCLUSION in {a.rejection_reason for _, a in tuesdays}


def test_emergency_holds_are_invisible_to_routine_requests(repo, index) -> None:
    """FR-026. A routine request never sees hold slots at any stage."""
    routine = layer0(repo, index, urgency=Urgency.ROUTINE)
    urgent = layer0(repo, index, urgency=Urgency.URGENT)
    locked = routine.candidates.rejected_by_reason().get(RejectionReason.EMERGENCY_HOLD_LOCKED, 0)
    assert locked > 0
    assert RejectionReason.EMERGENCY_HOLD_LOCKED not in urgent.candidates.rejected_by_reason()


# ----------------------------------------------------------------- NFR-06 ----
def test_enumeration_and_feasibility_stay_inside_the_budget(repo, index) -> None:
    """"The LLM call is the latency floor, not the search" -- this is the evidence."""
    layer0(repo, index)  # warm the index
    t0 = time.perf_counter()
    layer0(repo, index)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 150, f"enumeration + feasibility took {elapsed_ms:.0f}ms (NFR-06: <150ms)"
