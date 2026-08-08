"""Closed vocabularies. Every one of these is data the loader validates against."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    DENTIST = "DDS"
    HYGIENIST = "RDH"
    ASSISTANT = "DA"


class Urgency(StrEnum):
    """Ordered most- to least-urgent. Order is load-bearing: the gate is
    lexicographic (FR-032), so ``rank`` below defines tier precedence."""

    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"
    FLEXIBLE = "flexible"

    @property
    def rank(self) -> int:
        return _URGENCY_RANK[self]

    def at_least(self, other: Urgency) -> bool:
        return self.rank <= other.rank


_URGENCY_RANK: dict[Urgency, int] = {
    Urgency.EMERGENCY: 0,
    Urgency.URGENT: 1,
    Urgency.ROUTINE: 2,
    Urgency.FLEXIBLE: 3,
}


class BlockKind(StrEnum):
    LUNCH = "lunch"
    HUDDLE = "huddle"
    RESTORATIVE = "restorative_block"
    EMERGENCY_HOLD = "emergency_hold"
    PEDO_AFTER_SCHOOL = "pedo_after_school"
    ADMIN = "admin"


class BlockScope(StrEnum):
    PROVIDER = "provider"
    OPERATORY = "operatory"
    GLOBAL = "global"


class CheckPlacement(StrEnum):
    LAST_THIRD = "last_third"


class Scope(StrEnum):
    """Owning scope for policy and decisions. [NFR-30]

    v1.0 populates every row at LOCATION scope against the single seeded location.
    The resolution chain (platform -> group -> location) is deferred; the field is not.
    """

    PLATFORM = "platform"
    GROUP = "group"
    LOCATION = "location"


class OfferState(StrEnum):
    """Which kind of offer set the operator is looking at. [AR-09]

    Carried on the DecisionRecord so a released or expired hold returns to the state
    it came from -- otherwise an alternative option silently starts looking like a
    slot that satisfied the request.
    """

    OFFERED = "offered"
    OFFERED_OVERFLOW = "offered_overflow"


class RejectionReason(StrEnum):
    """The single stated cause per rejected candidate (FR-028).

    Declaration order here is *not* the ladder order -- that lives in
    ``reasoner.ladder.RULES`` as data, in one place, so reordering it is a visible
    diff (FR-025).
    """

    BEFORE_OPEN = "BEFORE_OPEN"
    PAST_CLOSE = "PAST_CLOSE"
    BLOCKED_LUNCH = "BLOCKED_LUNCH"
    BLOCKED_HUDDLE = "BLOCKED_HUDDLE"
    BLOCKED_ADMIN = "BLOCKED_ADMIN"
    EMERGENCY_HOLD_LOCKED = "EMERGENCY_HOLD_LOCKED"
    PATIENT_EXCLUSION = "PATIENT_EXCLUSION"
    OPERATORY_BUSY = "OPERATORY_BUSY"
    OPERATORY_TURNOVER = "OPERATORY_TURNOVER"
    SLOT_HELD = "SLOT_HELD"
    OPERATORY_NOT_EQUIPPED = "OPERATORY_NOT_EQUIPPED"
    PROVIDER_BUSY = "PROVIDER_BUSY"
    PROVIDER_PTO = "PROVIDER_PTO"
    PROVIDER_NOT_CREDENTIALED = "PROVIDER_NOT_CREDENTIALED"
    PROVIDER_OFFSITE = "PROVIDER_OFFSITE"
    DOCTOR_CHECK_UNAVAILABLE = "DOCTOR_CHECK_UNAVAILABLE"


class Axis(StrEnum):
    """The four scored axes. Column order here is the column order of the score
    matrix (ADR-06) -- changing it changes every cached matrix, so it is fixed."""

    TIME_FIT = "time_fit"
    CONTINUITY = "continuity"
    EFFICIENCY = "efficiency"
    PRIME_TIME = "prime_time"


AXIS_ORDER: tuple[Axis, ...] = (
    Axis.TIME_FIT,
    Axis.CONTINUITY,
    Axis.EFFICIENCY,
    Axis.PRIME_TIME,
)
