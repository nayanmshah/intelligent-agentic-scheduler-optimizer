"""The hard-constraint ladder, declared **as data** in one place (FR-025).

Order is what makes the ledger meaningful: the *first* rule a candidate fails is its
single stated cause (FR-028). Reordering this table therefore changes ledger causes
deterministically, which is why it is a table and not control flow scattered through
a function -- and why a snapshot test covers it.

``depends_on`` is what makes hypothesis fan-out cheap (§8.3, §9): a rule declares the
constraint fields it reads, so the runner can tell whether two hypotheses can share
Layer 0 entirely. Note what is *absent* from every entry -- ``date_range``,
``time_window`` and ``provider_preference`` never affect feasibility, only scoring.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from app.domain.entities import AppointmentType, Hold, Operatory, Provider, ScheduleBlock
from app.domain.enums import RejectionReason, Urgency
from app.domain.request import RequestConstraints

Phase = Literal["slot", "provider"]


@dataclass(frozen=True, slots=True)
class SlotCtx:
    """Everything a slot-level rule may read. Provider-independent by construction."""

    day: date
    start_min: int
    duration: int
    operatory: Operatory
    appointment_type: AppointmentType
    constraints: RequestConstraints
    blocks: tuple[ScheduleBlock, ...]
    holds: tuple[Hold, ...]
    open_min: int
    close_min: int
    turnover: int
    operatory_free: bool
    operatory_free_with_turnover: bool
    unlocked_holds: bool

    @property
    def end_min(self) -> int:
        return self.start_min + self.duration


@dataclass(frozen=True, slots=True)
class ProviderCtx:
    slot: SlotCtx
    provider: Provider
    provider_free: bool
    doctor_check_ok: bool
    location_id: str


@dataclass(frozen=True, slots=True)
class Rule:
    order: int
    code: str
    phase: Phase
    depends_on: frozenset[str]
    check: Callable[..., RejectionReason | None]
    why: str  # the plain-language stem used by the ledger


# ---------------------------------------------------------------- slot rules --
def _within_business_hours(c: SlotCtx) -> RejectionReason | None:
    if c.start_min < c.open_min:
        return RejectionReason.BEFORE_OPEN
    # The appointment must end by close; the turnover buffer may extend past it [A-08].
    if c.end_min > c.close_min:
        return RejectionReason.PAST_CLOSE
    return None


_BLOCK_REASON = {
    "lunch": RejectionReason.BLOCKED_LUNCH,
    "huddle": RejectionReason.BLOCKED_HUDDLE,
    "admin": RejectionReason.BLOCKED_ADMIN,
}


def _not_overlapping_global_block(c: SlotCtx) -> RejectionReason | None:
    for b in c.blocks:
        if b.kind.value not in _BLOCK_REASON:
            continue
        if b.scope.value != "global" and b.scope_ref != c.operatory.id:
            continue
        if c.start_min < b.end_min and b.start_min < c.end_min:
            return _BLOCK_REASON[b.kind.value]
    return None


def _emergency_hold_locked(c: SlotCtx) -> RejectionReason | None:
    """Invisible by default (FR-026). A routine request never sees these slots at any
    stage -- not in the offers, not in the ledger's counts."""
    if c.unlocked_holds:
        return None
    for b in c.blocks:
        if b.kind.value != "emergency_hold" or b.scope_ref != c.operatory.id:
            continue
        if c.start_min < b.end_min and b.start_min < c.end_min:
            return RejectionReason.EMERGENCY_HOLD_LOCKED
    return None


def _patient_exclusion(c: SlotCtx) -> RejectionReason | None:
    """Hard, always. Never relaxed -- not by escalation, not by the counterfactual
    engine (FR-057), not by any weight vector. Suggesting a Tuesday to a patient who
    said "not Tuesdays, I have PT" is worse than offering nothing."""
    ex = c.constraints.exclusions.value
    if ex.weekdays and c.day.weekday() in ex.weekdays:
        return RejectionReason.PATIENT_EXCLUSION
    if ex.dates and c.day in ex.dates:
        return RejectionReason.PATIENT_EXCLUSION
    if any(c.start_min < hi and lo < c.end_min for lo, hi in ex.time_ranges):
        return RejectionReason.PATIENT_EXCLUSION
    return None


def _operatory_free(c: SlotCtx) -> RejectionReason | None:
    if not c.operatory_free:
        return RejectionReason.OPERATORY_BUSY
    if not c.operatory_free_with_turnover:
        return RejectionReason.OPERATORY_TURNOVER
    return None


def _slot_not_held(c: SlotCtx) -> RejectionReason | None:
    """[AR-03] Holds are an overlay, not part of the index -- there are only ever a
    handful and rebuilding cells to add three intervals would cost the offer path
    for nothing. A request never blocks its own holds."""
    for h in c.holds:
        if h.operatory_id != c.operatory.id:
            continue
        h_start = h.start.hour * 60 + h.start.minute
        if c.start_min < h_start + h.duration_min and h_start < c.end_min:
            return RejectionReason.SLOT_HELD
    return None


def _operatory_equipped(c: SlotCtx) -> RejectionReason | None:
    need = c.appointment_type.required_equipment
    if need and not need.issubset(c.operatory.equipment_tags):
        return RejectionReason.OPERATORY_NOT_EQUIPPED
    return None


# ------------------------------------------------------------ provider rules --
def _provider_free(c: ProviderCtx) -> RejectionReason | None:
    if not c.provider_free:
        return (
            RejectionReason.PROVIDER_PTO
            if c.provider.on_pto(c.slot.day)
            else RejectionReason.PROVIDER_BUSY
        )
    return None


def _provider_credentialed(c: ProviderCtx) -> RejectionReason | None:
    need = c.slot.appointment_type.required_credentials
    if need and not need.issubset(c.provider.credentials):
        return RejectionReason.PROVIDER_NOT_CREDENTIALED
    return None


def _provider_at_location(c: ProviderCtx) -> RejectionReason | None:
    if not c.provider.at_location(c.location_id, c.slot.day.weekday()):
        return RejectionReason.PROVIDER_OFFSITE
    return None


def _doctor_check(c: ProviderCtx) -> RejectionReason | None:
    if not c.slot.appointment_type.requires_doctor_check:
        return None
    return None if c.doctor_check_ok else RejectionReason.DOCTOR_CHECK_UNAVAILABLE


# ------------------------------------------------------------------ the table --
RULES: tuple[Rule, ...] = (
    Rule(1, "within_business_hours", "slot", frozenset(), _within_business_hours,
         "the practice is closed then"),
    Rule(2, "not_overlapping_global_block", "slot", frozenset(), _not_overlapping_global_block,
         "the practice is on a break then"),
    Rule(3, "emergency_hold_locked", "slot", frozenset({"urgency"}), _emergency_hold_locked,
         "that time is reserved for emergencies"),
    Rule(4, "patient_exclusion", "slot", frozenset({"exclusions"}), _patient_exclusion,
         "you asked us to avoid that time"),
    Rule(5, "operatory_free", "slot", frozenset({"appointment_type"}), _operatory_free,
         "the room is already in use"),
    Rule(6, "slot_not_held", "slot", frozenset(), _slot_not_held,
         "the room is being held for another patient"),
    Rule(7, "operatory_equipped", "slot", frozenset({"appointment_type"}), _operatory_equipped,
         "the room does not have the equipment that visit needs"),
    Rule(8, "provider_free", "provider", frozenset({"appointment_type"}), _provider_free,
         "the provider is already booked"),
    Rule(9, "provider_credentialed", "provider", frozenset({"appointment_type"}),
         _provider_credentialed, "that provider does not do that treatment"),
    Rule(10, "provider_at_location", "provider", frozenset(), _provider_at_location,
         "the provider is at another office that day"),
    Rule(11, "doctor_check_containment", "provider", frozenset({"appointment_type"}), _doctor_check,
         "no dentist was free for the short exam inside the appointment"),
)

SLOT_RULES = tuple(r for r in RULES if r.phase == "slot")
PROVIDER_RULES = tuple(r for r in RULES if r.phase == "provider")

#: Constraint fields that any Layer-0 rule reads. A hypothesis differing only in a
#: field absent from this set can reuse the entire annotated candidate set (§9).
LAYER0_DEPENDENCIES: frozenset[str] = frozenset().union(*(r.depends_on for r in RULES))


def holds_unlocked(constraints: RequestConstraints) -> bool:
    """FR-036: emergency holds are releasable only at urgency >= urgent."""
    return constraints.urgency.value.at_least(Urgency.URGENT)


def ladder_snapshot() -> tuple[tuple[int, str, str], ...]:
    """What the snapshot test pins. Reordering the ladder is a visible diff."""
    return tuple((r.order, r.code, r.phase) for r in RULES)


def hold_minutes(h: Hold, ref: datetime) -> tuple[int, int]:  # pragma: no cover - helper
    start = h.start.hour * 60 + h.start.minute
    return start, start + h.duration_min
