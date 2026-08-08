"""Session state and the in-memory ``ScheduleRepository``.

Two decisions here are load-bearing beyond v1.0:

* **Per-``(resource, day)`` versions** (ADR-16). A single global counter works fine at
  one location and is quadratic at many -- every write would rebuild every cell.
* **``commit_booking`` is conditional** (ADR-18). Check-then-write cannot fail at one
  seat and double-books at two, which is the worst pairing of severity and
  undetectability. Costing nothing single-seat, it is a compare-and-set here and a
  unique constraint in a database.
"""

from __future__ import annotations

import copy
import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.data.repository import BookingIntent, CommitResult
from app.data.timezone import to_local, zone
from app.domain.entities import Appointment, Hold, ScheduleBlock, SeedBundle
from app.domain.enums import OfferState
from app.domain.policy import GENERAL_PRACTICE_DEFAULT, WeightProfile


@dataclass
class SessionState:
    """The in-memory copy that bookings mutate. Committed seed JSON is never written
    at runtime (FR-070): after any number of bookings, `git status` on the seed data
    is clean."""

    seed: SeedBundle
    appointments: list[Appointment]
    holds: list[Hold] = field(default_factory=list)
    active_profile: WeightProfile = GENERAL_PRACTICE_DEFAULT
    versions: dict[tuple[str, date], int] = field(default_factory=lambda: defaultdict(int))
    origin_states: dict[str, OfferState] = field(default_factory=dict)  # [AR-09]
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    @classmethod
    def from_seed(cls, seed: SeedBundle) -> SessionState:
        return cls(seed=seed, appointments=list(seed.appointments))

    def reset(self) -> None:
        """Restore the reference dataset. Traces deliberately survive (FR-072): an
        evaluator will want to reset the schedule and still inspect a decision made
        before the reset, and coupling the two would destroy the audit trail on every
        reset."""
        self.appointments = list(self.seed.appointments)
        self.holds.clear()
        self.active_profile = GENERAL_PRACTICE_DEFAULT
        self.versions.clear()
        self.origin_states.clear()

    def next_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids):05d}"


class MemoryScheduleRepository:
    """v1.0 implementation of ``ScheduleRepository`` (NFR-29)."""

    def __init__(self, state: SessionState) -> None:
        self._state = state
        self._tz = zone(state.seed.locations[0].timezone)
        self._by_day: dict[date, list[Appointment]] | None = None

    # -- reads -----------------------------------------------------------------
    @property
    def seed(self) -> SeedBundle:
        return self._state.seed

    @property
    def state(self) -> SessionState:
        return self._state

    def _index(self) -> dict[date, list[Appointment]]:
        if self._by_day is None:
            grouped: dict[date, list[Appointment]] = defaultdict(list)
            for a in self._state.appointments:
                grouped[to_local(a.start, self._tz)[0]].append(a)
            self._by_day = grouped
        return self._by_day

    def appointments_on(self, day: date) -> tuple[Appointment, ...]:
        return tuple(self._index().get(day, ()))

    def blocks_on(self, day: date) -> tuple[ScheduleBlock, ...]:
        return tuple(b for b in self._state.seed.blocks if b.applies_on(day))

    def holds(self) -> tuple[Hold, ...]:
        return tuple(self._state.holds)

    def version_of(self, resource_id: str, day: date) -> int:
        return self._state.versions[(resource_id, day)]

    def invalidate(self, resource_id: str, day: date) -> None:
        """Public because in production changes arrive from outside -- a cancellation
        in the practice-management system, a provider calling in sick. The index must
        not care who caused a change."""
        self._state.versions[(resource_id, day)] += 1
        self._by_day = None

    # -- the conditional write -------------------------------------------------
    def commit_booking(self, intent: BookingIntent, expect: int) -> CommitResult:
        day, start_min = to_local(intent.start, self._tz)
        if self.version_of(intent.operatory_id, day) != expect:
            # Somebody else changed this cell between re-verification and commit.
            return CommitResult(ok=False, error="SLOT_TAKEN")

        end_min = start_min + intent.duration_min
        for a in self.appointments_on(day):
            a_start = to_local(a.start, self._tz)[1]
            a_end = a_start + a.duration_min
            clash = start_min < a_end and a_start < end_min
            if clash and a.operatory_id == intent.operatory_id:
                return CommitResult(ok=False, error="SLOT_TAKEN")
            if clash and a.provider_id == intent.provider_id:
                return CommitResult(ok=False, error="SLOT_TAKEN")

        appt = Appointment(
            id=self._state.next_id("booked"),
            start=intent.start,
            duration_min=intent.duration_min,
            patient_id=intent.patient_id,
            provider_id=intent.provider_id,
            operatory_id=intent.operatory_id,
            type_id=intent.type_id,
            status="scheduled",
        )
        self._state.appointments.append(appt)
        self.invalidate(intent.operatory_id, day)
        self.invalidate(intent.provider_id, day)
        self._state.holds = [h for h in self._state.holds if h.request_id != intent.request_id]
        return CommitResult(ok=True, appointment=appt)

    # -- holds (an overlay, not indexed) [AR-03] -------------------------------
    def place_hold(self, hold: Hold) -> None:
        self._state.holds.append(hold)

    def release_holds(self, request_id: str) -> None:
        self._state.holds = [h for h in self._state.holds if h.request_id != request_id]

    def live_holds(self, now: datetime, exclude_request: str | None = None) -> tuple[Hold, ...]:
        """Expiry is evaluated lazily against the injected clock rather than by a
        background timer -- a timer would make hold state depend on wall-clock
        arrival, the one thing SD-3 exists to prevent."""
        return tuple(
            h
            for h in self._state.holds
            if h.is_live(now) and (exclude_request is None or h.request_id != exclude_request)
        )

    def hold_ttl(self, now: datetime, minutes: int) -> datetime:
        return now + timedelta(minutes=minutes)

    def snapshot(self) -> list[Appointment]:
        return copy.copy(self._state.appointments)
