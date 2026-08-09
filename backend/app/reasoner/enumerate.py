"""Enumeration and the two-phase ladder.

**Two numbers are reported, not one** [AR-04]. FR-016's arithmetic acceptance
criterion is expressed over grid slots -- ``business_minutes / 10 x operatories``,
with no provider dimension -- while FR-017 defines candidate identity as
``(start, duration, provider, operatory)``. Both are true; they count different
things, so both are surfaced and the conservation invariant is stated over the
larger one.

**Phase A is provider-independent**, so it runs once per grid slot and its verdict is
written to every candidate in that slot. That preserves the fixed rule order of
FR-025 and the single-cause guarantee of FR-028 while doing the work once -- and it
is the same split that makes hypothesis fan-out affordable (§9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.data.repository import ScheduleRepository
from app.data.timezone import local_minute, to_instant
from app.domain.candidate import Candidate, CandidateSet
from app.domain.entities import AppointmentType, Location, Provider
from app.domain.request import RequestConstraints
from app.reasoner.availability import AvailabilityIndex
from app.reasoner.ladder import (
    PROVIDER_RULES,
    SLOT_RULES,
    ProviderCtx,
    SlotCtx,
    holds_unlocked,
)


@dataclass(frozen=True, slots=True)
class EnumerationResult:
    candidates: CandidateSet
    grid_slots: int
    days: tuple[date, ...]


def eligible_providers(
    repo: ScheduleRepository, appointment_type: AppointmentType
) -> tuple[Provider, ...]:
    """Pruned before the cross product. Enumerating a hygienist for a crown prep only
    to reject it would inflate the ledger with candidates nobody ever considered
    plausible -- the ledger is evidence, not noise."""
    need = appointment_type.required_credentials
    return tuple(p for p in repo.seed.providers if not need or need.issubset(p.credentials))


def horizon_days(now_date: date, settings: Settings, location: Location) -> tuple[date, ...]:
    out: list[date] = []
    for offset in range(settings.search_horizon_days + 1):
        d = now_date + timedelta(days=offset)
        if location.hours_for(d.weekday()) is not None:
            out.append(d)
    return tuple(out)


def run_layer0(
    repo: ScheduleRepository,
    index: AvailabilityIndex,
    constraints: RequestConstraints,
    appointment_type: AppointmentType,
    location: Location,
    tz: ZoneInfo,
    now: date,
    settings: Settings,
    request_id: str,
    now_dt: datetime | None = None,
) -> EnumerationResult:
    days = horizon_days(now, settings, location)
    operatories = repo.seed.operatories
    providers = eligible_providers(repo, appointment_type)
    duration = appointment_type.duration_min
    turnover = settings.turnover_min
    unlocked = holds_unlocked(constraints)
    live_holds = (
        repo.live_holds(now_dt, exclude_request=request_id) if now_dt is not None else ()
    )

    cs = CandidateSet()
    grid_slots = 0

    for day in days:
        hours = index.hours(day)
        if hours is None:
            continue
        open_min, close_min = hours
        blocks = repo.blocks_on(day)
        starts = range(open_min, close_min, settings.grid_granularity_min)

        for operatory in operatories:
            for start_min in starts:
                grid_slots += 1
                end_min = start_min + duration

                slot = SlotCtx(
                    now_min=(
                        local_minute(now_dt, tz)
                        if now_dt is not None and day == now
                        else None
                    ),
                    day=day,
                    start_min=start_min,
                    duration=duration,
                    operatory=operatory,
                    appointment_type=appointment_type,
                    constraints=constraints,
                    blocks=blocks,
                    holds=live_holds,
                    open_min=open_min,
                    close_min=close_min,
                    turnover=turnover,
                    operatory_free=index.is_free(
                        operatory.id, day, start_min, min(end_min, close_min)
                    ),
                    operatory_free_with_turnover=index.is_free(
                        operatory.id, day, start_min, min(end_min + turnover, close_min)
                    ),
                    unlocked_holds=unlocked,
                )

                # Phase A -- evaluated once, then written to every candidate here.
                slot_reason = None
                slot_rule = ""
                for rule in SLOT_RULES:
                    slot_reason = rule.check(slot)
                    if slot_reason is not None:
                        slot_rule = rule.code
                        break

                start_dt = to_instant(day, start_min, tz)
                for provider in providers:
                    cid = Candidate.make_id(day, start_min, duration, provider.id, operatory.id)
                    cs.add(
                        Candidate(
                            candidate_id=cid,
                            day=day,
                            start=start_dt,
                            start_min=start_min,
                            duration_min=duration,
                            provider_id=provider.id,
                            operatory_id=operatory.id,
                        )
                    )
                    if slot_reason is not None:
                        cs.reject(cid, slot_reason, slot_rule)
                        continue

                    # Phase B -- provider-level, only for slots that survived Phase A.
                    pctx = ProviderCtx(
                        slot=slot,
                        provider=provider,
                        provider_free=index.is_free(provider.id, day, start_min, end_min),
                        doctor_check_ok=(
                            index.doctor_check_available(
                                day, start_min, duration, settings.doctor_check_min
                            )
                            if appointment_type.requires_doctor_check
                            else True
                        ),
                        location_id=location.id,
                    )
                    reason = None
                    for rule in PROVIDER_RULES:
                        reason = rule.check(pctx)
                        if reason is not None:
                            cs.reject(cid, reason, rule.code)
                            break
                    if reason is None:
                        cs.mark_feasible(cid)

    cs.set_grid_slots(grid_slots)
    cs.conserve()  # FR-027, in every mode -- not only under test
    return EnumerationResult(candidates=cs, grid_slots=grid_slots, days=days)


def expected_grid_slots(
    location: Location, days: tuple[date, ...], operatories: int, granularity: int
) -> int:
    """FR-016's arithmetic, computed independently so the test compares two
    derivations rather than the implementation against itself."""
    total = 0
    for d in days:
        h = location.hours_for(d.weekday())
        if h is None:
            continue
        total += len(range(h.open_min, h.close_min, granularity))
    return total * operatories
