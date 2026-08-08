"""[NFR-32 / ADR-17] The one timezone conversion boundary.

Two representations, deliberately:

* **Stored, transported, compared across locations** -- a timezone-aware instant plus
  the location's IANA zone. An absolute instant is the only thing two practices in
  different zones can be compared on.
* **Inside the index and the ladder** -- minute offsets from local midnight. Business
  hours, turnover and the doctor-check window are all local wall-clock concepts, so
  expressing them as offsets removes timezone handling from the hot path entirely.

This module is the *only* place a naive ``datetime`` may be constructed; an AST test
enforces that. Confining the assumption is what keeps the eventual multi-timezone fix
local to one file rather than diffused through the scheduler.

**Why this is a module and not a convention.** DST enters a 14-day horizon twice a
year in every zone. A spring-forward day contains a wall-clock hour that does not
exist; a fall-back day contains one that happens twice. A scheduler that stores naive
local times books into the first and double-books into the second -- silently, on two
days a year, in a way no ordinary test catches. So the DST fixtures exist now, before
the data that would trigger them.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MINUTES_PER_DAY = 24 * 60


class NonexistentLocalTime(ValueError):
    """The wall-clock time does not exist on that date (spring forward)."""


class AmbiguousLocalTime(ValueError):
    """The wall-clock time happens twice on that date (fall back)."""


def zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def to_instant(d: date, minute_of_day: int, tz: ZoneInfo, *, strict: bool = True) -> datetime:
    """Local wall clock -> absolute instant.

    ``strict`` raises on a nonexistent local time rather than silently shifting it.
    Silence here is how a spring-forward appointment ends up an hour off with nobody
    noticing until the patient arrives.
    """
    if not 0 <= minute_of_day < MINUTES_PER_DAY:
        raise ValueError(f"minute_of_day out of range: {minute_of_day}")
    naive = datetime.combine(d, time(minute_of_day // 60, minute_of_day % 60))
    aware = naive.replace(tzinfo=tz)
    if strict and _is_nonexistent(naive, tz):
        raise NonexistentLocalTime(f"{naive.isoformat()} does not exist in {tz.key}")
    return aware


def to_local(dt: datetime, tz: ZoneInfo) -> tuple[date, int]:
    """Absolute instant -> (local date, minutes from local midnight)."""
    if dt.tzinfo is None:
        raise ValueError("to_local requires a timezone-aware datetime [NFR-32]")
    local = dt.astimezone(tz)
    return local.date(), local.hour * 60 + local.minute


def local_minute(dt: datetime, tz: ZoneInfo) -> int:
    return to_local(dt, tz)[1]


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    return to_local(dt, tz)[0]


def _is_nonexistent(naive: datetime, tz: ZoneInfo) -> bool:
    """A local time is nonexistent when it does not survive a round trip through UTC."""
    aware = naive.replace(tzinfo=tz)
    return aware.astimezone(ZoneInfo("UTC")).astimezone(tz).replace(tzinfo=None) != naive


def is_nonexistent(d: date, minute_of_day: int, tz: ZoneInfo) -> bool:
    naive = datetime.combine(d, time(minute_of_day // 60, minute_of_day % 60))
    return _is_nonexistent(naive, tz)


def is_ambiguous(d: date, minute_of_day: int, tz: ZoneInfo) -> bool:
    """True when the wall-clock time occurs twice (fall back)."""
    naive = datetime.combine(d, time(minute_of_day // 60, minute_of_day % 60))
    first = naive.replace(tzinfo=tz, fold=0)
    second = naive.replace(tzinfo=tz, fold=1)
    return first.utcoffset() != second.utcoffset()


def day_length_minutes(d: date, tz: ZoneInfo) -> int:
    """Wall-clock minutes in a local day: 1440 normally, 1380 or 1500 on DST days.

    The availability index sizes its arrays from business hours rather than from this,
    so a short day does not corrupt the index -- but any code that assumes 1440 is
    wrong twice a year, and this function exists so that assumption has to be written
    down rather than made silently.
    """
    start = datetime.combine(d, time(0, 0)).replace(tzinfo=tz)
    nxt = datetime.combine(d + timedelta(days=1), time(0, 0)).replace(tzinfo=tz)
    return int((nxt - start).total_seconds() // 60)


def business_days(start: date, end_inclusive: date) -> list[date]:
    """Mon-Fri between two local dates, inclusive. Pure calendar arithmetic --
    no clock reading, so it is safe outside this module's timezone concerns."""
    out: list[date] = []
    d = start
    while d <= end_inclusive:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out
