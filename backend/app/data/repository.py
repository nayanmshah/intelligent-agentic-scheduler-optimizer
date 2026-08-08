"""[NFR-29 / ADR-19] The seam between scheduling logic and storage.

Every other boundary in this system is a ``Protocol``; this one was the omission.
Without it, adopting a database later edits the reasoner -- which is exactly the
code that must not churn.

Three things the interface deliberately offers, each because omitting it would push
a defect into every caller:

* ``version_of`` is per ``(resource, day)`` (ADR-16). One global counter makes every
  write rebuild everything -- invisible at one location, quadratic at many.
* ``commit_booking`` takes an expected version and is **conditional** (ADR-18). A
  repository that only offers ``write()`` forces callers into check-then-write, and
  check-then-write double-books the moment there are two operators.
* ``invalidate`` is public, because in production the practice-management system is
  the system of record and changes arrive from outside -- cancellations, no-shows, a
  hygienist calling in sick. The index must not care who caused a change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from app.domain.entities import Appointment, Hold, ScheduleBlock, SeedBundle


@dataclass(frozen=True, slots=True)
class BookingIntent:
    candidate_id: str
    start: datetime
    duration_min: int
    provider_id: str
    operatory_id: str
    patient_id: str | None
    type_id: str
    request_id: str


@dataclass(frozen=True, slots=True)
class CommitResult:
    ok: bool
    appointment: Appointment | None = None
    error: str | None = None  # "SLOT_TAKEN" | "INFEASIBLE"

    @property
    def slot_taken(self) -> bool:
        return self.error == "SLOT_TAKEN"


@runtime_checkable
class ScheduleRepository(Protocol):
    """What the reasoner is allowed to know about storage."""

    @property
    def seed(self) -> SeedBundle: ...

    def appointments_on(self, day: date) -> tuple[Appointment, ...]: ...

    def blocks_on(self, day: date) -> tuple[ScheduleBlock, ...]: ...

    def holds(self) -> tuple[Hold, ...]: ...

    def live_holds(self, now: datetime, exclude_request: str | None = None) -> tuple[Hold, ...]:
        """Holds that have not yet expired at ``now``.

        On the interface rather than duck-typed onto the implementation: enumeration
        must subtract another operator's live holds, so this is part of what the
        reasoner is allowed to know about storage (ADR-19), not an extra.
        """
        ...

    def version_of(self, resource_id: str, day: date) -> int:
        """Per-cell version. Bumps only for the cell that actually changed."""
        ...

    def commit_booking(self, intent: BookingIntent, expect: int) -> CommitResult:
        """Conditional write. Succeeds only if the cell version still matches."""
        ...

    def invalidate(self, resource_id: str, day: date) -> None: ...
