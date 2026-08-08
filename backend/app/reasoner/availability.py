"""[ADR-05] Minute-resolution occupancy with prefix sums.

Every feasibility question in the ladder is *"is this exact window entirely free?"*.
A prefix sum answers that in one subtraction; an interval tree answers it with a
search plus a loop. It is faster, and -- which matters more for NFR-27 -- it is four
lines a reviewer can verify by inspection.

Two indexes, built from the same bitmaps:

* **Occupancy**, per ``(resource, day)``, memoised on that cell's own version
  (ADR-16). One global counter would make every write rebuild everything: invisible
  at one location, quadratic at many.
* **Doctor check**, per day. ``C[t]`` is 1 when *some* credentialed dentist has ten
  contiguous free minutes starting at ``t``. Prefix-summing ``C`` turns FR-023's
  containment question into one subtraction, independent of how many dentists there
  are. Naming *which* dentist is deferred to the handful of candidates actually
  offered, where the rationale needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import accumulate
from zoneinfo import ZoneInfo

from app.data.repository import ScheduleRepository
from app.data.timezone import to_local
from app.domain.entities import Location, Provider


@dataclass(frozen=True, slots=True)
class DayGrid:
    """Occupancy for one (resource, day), as a prefix sum over busy minutes."""

    open_min: int
    close_min: int
    prefix: tuple[int, ...]  # prefix[i] = busy minutes in [open_min, open_min + i)
    version: int

    def free(self, start_min: int, end_min: int) -> bool:
        if start_min < self.open_min or end_min > self.close_min:
            return False
        lo = start_min - self.open_min
        hi = end_min - self.open_min
        return self.prefix[hi] - self.prefix[lo] == 0

    @property
    def busy_minutes(self) -> int:
        return self.prefix[-1]


class AvailabilityIndex:
    """Built once per schedule version and shared by every hypothesis (§9)."""

    def __init__(self, repo: ScheduleRepository, location: Location, tz: ZoneInfo) -> None:
        self._repo = repo
        self._loc = location
        self._tz = tz
        self._cells: dict[tuple[str, date], DayGrid] = {}
        self._check: dict[date, tuple[tuple[int, ...], int, int]] = {}
        self._dentists = tuple(p for p in repo.seed.providers if p.is_dentist)

    # -- occupancy -------------------------------------------------------------
    def hours(self, day: date) -> tuple[int, int] | None:
        h = self._loc.hours_for(day.weekday())
        return (h.open_min, h.close_min) if h else None

    def cell(self, resource_id: str, day: date) -> DayGrid | None:
        hours = self.hours(day)
        if hours is None:
            return None
        cached = self._cells.get((resource_id, day))
        version = self._repo.version_of(resource_id, day)
        if cached is not None and cached.version == version:
            return cached
        grid = self._build_cell(resource_id, day, hours, version)
        self._cells[(resource_id, day)] = grid
        return grid

    def _build_cell(
        self, resource_id: str, day: date, hours: tuple[int, int], version: int
    ) -> DayGrid:
        open_min, close_min = hours
        span = close_min - open_min
        busy = bytearray(span)

        def mark(lo: int, hi: int) -> None:
            a = max(lo, open_min) - open_min
            b = min(hi, close_min) - open_min
            if b > a:
                busy[a:b] = b"\x01" * (b - a)

        for appt in self._repo.appointments_on(day):
            if resource_id not in (appt.operatory_id, appt.provider_id):
                continue
            start = to_local(appt.start, self._tz)[1]
            mark(start, start + appt.duration_min)

        for block in self._repo.blocks_on(day):
            if block.kind.value == "emergency_hold":
                continue  # handled as its own ladder rule so it can be released
            if block.kind.value in {"restorative_block", "pedo_after_school"}:
                continue  # soft: these are scored, not enforced
            if block.scope.value == "global" or block.scope_ref == resource_id:
                mark(block.start_min, block.end_min)

        provider = next((p for p in self._repo.seed.providers if p.id == resource_id), None)
        if provider is not None and (
            provider.on_pto(day) or not provider.at_location(self._loc.id, day.weekday())
        ):
            mark(open_min, close_min)

        prefix = (0, *accumulate(busy))
        return DayGrid(open_min, close_min, prefix, version)

    def is_free(self, resource_id: str, day: date, start_min: int, end_min: int) -> bool:
        grid = self.cell(resource_id, day)
        return grid is not None and grid.free(start_min, end_min)

    def busy_minutes(self, resource_id: str, day: date) -> int:
        grid = self.cell(resource_id, day)
        return grid.busy_minutes if grid else 0

    # -- doctor check (FR-023) -------------------------------------------------
    def _check_index(self, day: date, check_min: int) -> tuple[tuple[int, ...], int, int] | None:
        hours = self.hours(day)
        if hours is None:
            return None
        cached = self._check.get(day)
        if cached is not None:
            return cached

        open_min, close_min = hours
        span = close_min - open_min
        # C[t] = 1 when SOME dentist is free across [t, t+check_min)
        c = bytearray(span)
        for t in range(span - check_min + 1):
            absolute = open_min + t
            for dentist in self._dentists:
                if self.is_free(dentist.id, day, absolute, absolute + check_min):
                    c[t] = 1
                    break
        prefix = (0, *accumulate(c))
        self._check[day] = (prefix, open_min, close_min)
        return self._check[day]

    def doctor_check_available(
        self, day: date, start_min: int, duration: int, check_min: int
    ) -> bool:
        """Interval-*within*-interval containment, not overlap.

        Read it as: is there any minute in the last third at which a dentist has ten
        uninterrupted minutes, with all ten still inside the appointment? The
        ``b - check_min`` upper bound is what makes it containment -- a check starting
        later than that would run past the appointment's end and is not counted.
        """
        index = self._check_index(day, check_min)
        if index is None:
            return False
        prefix, open_min, close_min = index

        a = start_min + -(-2 * duration // 3)  # ceil(2d/3): start of the last third
        b = start_min + duration
        if b - a < check_min or b > close_min:
            return False

        lo = a - open_min
        hi = b - check_min - open_min
        if hi < lo:
            return False
        return prefix[hi + 1] - prefix[lo] > 0

    def doctor_for_check(
        self, day: date, start_min: int, duration: int, check_min: int
    ) -> str | None:
        """Which dentist. Resolved only for candidates that are actually offered."""
        a = start_min + -(-2 * duration // 3)
        b = start_min + duration
        for t in range(a, b - check_min + 1):
            for dentist in self._dentists:
                if self.is_free(dentist.id, day, t, t + check_min):
                    return dentist.id
        return None

    def invalidate_day(self, day: date) -> None:
        self._check.pop(day, None)

    @property
    def dentists(self) -> tuple[Provider, ...]:
        return self._dentists
