"""Seed entities -- the validated I/O boundary.

These are pydantic models because they are loaded from committed JSON and a schema
violation must fail the boot loudly (PRD §10). The hot-path value types
(``Candidate``, ``AxisValues``) are dataclasses instead: they are constructed tens of
thousands of times per request and never cross a validation boundary.

Time representation follows NFR-32. Anything *stored* is either a timezone-aware
instant or an explicit minute-offset from a location's day-open. Nothing here is a
naive datetime, and no arithmetic in this module crosses a day boundary.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import BlockKind, BlockScope, CheckPlacement, Role, Urgency
from app.domain.phi import PHI

MINUTES_PER_DAY = 24 * 60


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BusinessHours(Frozen):
    """Open/close as minute offsets from local midnight. Weekday is 0=Monday."""

    weekday: int = Field(ge=0, le=6)
    open_min: int = Field(ge=0, lt=MINUTES_PER_DAY)
    close_min: int = Field(ge=0, le=MINUTES_PER_DAY)

    @field_validator("close_min")
    @classmethod
    def _ordered(cls, v: int, info) -> int:  # type: ignore[no-untyped-def]
        if "open_min" in info.data and v <= info.data["open_min"]:
            raise ValueError("close_min must be after open_min")
        return v


class DateRange(Frozen):
    """Inclusive on both ends -- PTO covering a single day has start == end."""

    start: date
    end: date

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end


class Location(Frozen):
    id: str
    name: str
    timezone: str  # IANA zone, e.g. "America/Los_Angeles"  [NFR-32]
    business_hours: tuple[BusinessHours, ...]

    def hours_for(self, weekday: int) -> BusinessHours | None:
        for h in self.business_hours:
            if h.weekday == weekday:
                return h
        return None


class Operatory(Frozen):
    id: str
    name: str
    location_id: str
    equipment_tags: frozenset[str] = frozenset()
    preferred_use: str | None = None


class Provider(Frozen):
    id: str
    name: str  # staff names are not PHI
    role: Role
    credentials: frozenset[str] = frozenset()
    pod: str | None = None
    working_hours: tuple[BusinessHours, ...] = ()
    pto: tuple[DateRange, ...] = ()
    location_by_weekday: dict[int, str] = Field(default_factory=dict)

    @property
    def is_dentist(self) -> bool:
        return self.role is Role.DENTIST

    def on_pto(self, d: date) -> bool:
        return any(r.contains(d) for r in self.pto)

    def at_location(self, location_id: str, weekday: int) -> bool:
        """Providers rotate across offices in a multi-practice group; an empty map
        means 'always at their home location'."""
        if not self.location_by_weekday:
            return True
        return self.location_by_weekday.get(weekday) == location_id


class AppointmentType(Frozen):
    id: str
    name: str
    duration_min: int = Field(gt=0)
    requires_doctor_check: bool = False
    check_duration: int = 10
    check_placement: CheckPlacement = CheckPlacement.LAST_THIRD
    required_credentials: frozenset[str] = frozenset()
    required_equipment: frozenset[str] = frozenset()
    production_value: float = 0.0
    prime_time_protected: bool = False
    default_urgency: Urgency = Urgency.ROUTINE
    continuity_multiplier: float = Field(default=1.0, gt=0)


class LastSeen(Frozen):
    provider_id: str
    on: date


class Patient(Frozen):
    id: str
    name: Annotated[str, PHI]
    age_band: str  # "child" | "adult" | "senior"
    assigned_dentist_id: str | None = None
    assigned_hygienist_id: str | None = None
    last_seen_by_type: dict[str, LastSeen] = Field(default_factory=dict)
    no_show_count: int = 0

    @property
    def is_school_age(self) -> bool:
        return self.age_band == "child"


class Appointment(Frozen):
    id: str
    start: datetime  # timezone-aware  [NFR-32]
    duration_min: int = Field(gt=0)
    patient_id: str | None
    provider_id: str
    operatory_id: str
    type_id: str
    status: str = "scheduled"

    @field_validator("start")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Appointment.start must be timezone-aware [NFR-32]")
        return v


class ScheduleBlock(Frozen):
    """Not an appointment: the reserved shape of the day.

    Modelling this rather than hard-coding lunch and prime-time is what makes block
    protection a rule and the emergency-hold unlock a rule, instead of two special
    cases buried in the scorer.
    """

    id: str
    scope: BlockScope
    scope_ref: str | None = None  # provider or operatory id; None when global
    kind: BlockKind
    weekdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})
    start_min: int = Field(ge=0, lt=MINUTES_PER_DAY)
    end_min: int = Field(gt=0, le=MINUTES_PER_DAY)
    unlock_min_urgency: Urgency | None = None
    min_production_value: float | None = None
    dates: frozenset[date] = frozenset()  # empty => recurs on `weekdays`

    def applies_on(self, d: date) -> bool:
        return d in self.dates if self.dates else d.weekday() in self.weekdays

    @property
    def is_unlockable(self) -> bool:
        return self.unlock_min_urgency is not None


class Hold(Frozen):
    """Soft hold with a TTL. Deliberately an overlay rather than part of the
    availability index [AR-03] -- there are only ever a handful, and rebuilding index
    cells to add three intervals would put latency on the offer path for nothing."""

    id: str
    candidate_id: str
    request_id: str
    operatory_id: str
    provider_id: str
    start: datetime
    duration_min: int
    expires_at: datetime

    def is_live(self, now: datetime) -> bool:
        return now < self.expires_at


class SeedBundle(Frozen):
    """Everything the loader produces. One object so the digest has one input."""

    locations: tuple[Location, ...]
    operatories: tuple[Operatory, ...]
    providers: tuple[Provider, ...]
    appointment_types: tuple[AppointmentType, ...]
    patients: tuple[Patient, ...]
    appointments: tuple[Appointment, ...]
    blocks: tuple[ScheduleBlock, ...]

    def location(self, lid: str) -> Location:
        return next(x for x in self.locations if x.id == lid)

    def provider(self, pid: str) -> Provider:
        return next(x for x in self.providers if x.id == pid)

    def operatory(self, oid: str) -> Operatory:
        return next(x for x in self.operatories if x.id == oid)

    def appointment_type(self, tid: str) -> AppointmentType:
        return next(x for x in self.appointment_types if x.id == tid)

    def patient(self, pid: str) -> Patient | None:
        return next((x for x in self.patients if x.id == pid), None)

    @property
    def dentists(self) -> tuple[Provider, ...]:
        return tuple(p for p in self.providers if p.is_dentist)
