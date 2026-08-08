"""[SD-3] The one place time enters the system.

``datetime.now()`` anywhere else is a build failure, asserted by an AST walk over the
whole package (FR-102, NFR-14). That is not fastidiousness: "next Thursday" must
resolve to the same date on every run, on every machine, regardless of when the run
happens. Retrofitting a clock through a codebase that reads the wall clock in six
places is a class of heisenbug, not a refactor.

The reference instant is pinned to the dataset's own timestamp, so relative language
resolves into the seeded window rather than drifting out of it as real time passes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Always timezone-aware. [NFR-32]"""
        ...


@dataclass(frozen=True, slots=True)
class FrozenClock:
    """Pinned to the reference dataset's own timestamp.

    This is a *configuration* choice, not an architectural one. It exists because the
    committed dataset only contains appointments for 3-28 Aug 2026: read the real
    clock and "next Thursday" resolves to a date with no seeded schedule behind it,
    so every request returns nothing and every golden-set label -- which references
    specific seeded slots -- becomes meaningless.

    Swap in ``SystemClock`` and nothing else in the codebase changes. That is the
    whole point of injecting it.
    """

    reference: datetime

    def __post_init__(self) -> None:
        if self.reference.tzinfo is None:
            raise ValueError("reference NOW must be timezone-aware [NFR-32]")

    def now(self) -> datetime:
        return self.reference


@dataclass(frozen=True, slots=True)
class SystemClock:
    """Real time, for a deployment reading a live schedule.

    Selected with ``SCHED_CLOCK=system``. Everything downstream is unchanged --
    which is the answer to "why not just use today's date?": it can, and this is the
    switch. The demo does not, because its dataset is a fixed window.
    """

    tz: ZoneInfo

    def now(self) -> datetime:
        return datetime.now(tz=self.tz)


@dataclass(slots=True)
class AdvanceableClock:
    """Test-only. Lets hold-expiry tests move time without touching the machine
    clock, which is the whole point of injecting it in the first place."""

    reference: datetime

    def now(self) -> datetime:
        return self.reference

    def advance(self, *, minutes: int = 0, days: int = 0) -> None:
        from datetime import timedelta

        self.reference = self.reference + timedelta(minutes=minutes, days=days)
