"""Operator-console routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import (
    AnswerRequest,
    BookingRequest,
    HoldRequest,
    SubmitRequest,
    decision_json,
)
from app.data.repository import BookingIntent
from app.data.timezone import to_local, zone
from app.domain.entities import Hold
from app.orchestrator.machine import IncomingRequest

router = APIRouter(tags=["console"])


def _c(request: Request) -> Any:
    return request.app.state.container


def _offer_for(record: Any, candidate_id: str) -> Any:
    return next(
        (o for o in (*record.offers, *record.overflow) if o.candidate_id == candidate_id),
        None,
    )


@router.post("/requests")
async def submit(body: SubmitRequest, request: Request) -> dict[str, Any]:
    c = _c(request)
    patient = c.load.bundle.patient(body.patient_id) if body.patient_id else None
    record = await c.orchestrator.run(
        IncomingRequest(text=body.text, patient=patient),
        c.clock.now(),
        c.state.active_profile,
    )
    _place_holds(c, record)
    return decision_json(record)


@router.post("/requests/{decision_id}/answer")
async def answer(decision_id: str, body: AnswerRequest, request: Request) -> dict[str, Any]:
    """Answering re-runs the deterministic pipeline only -- zero LLM calls (FR-011)."""
    c = _c(request)
    prior = c.trace_store.decision(decision_id)
    if prior is None:
        raise HTTPException(404, "decision not found")
    record = await c.orchestrator.run(
        IncomingRequest(text=f"{prior.raw_text} ({body.choice})", patient=None),
        c.clock.now(),
        c.state.active_profile,
    )
    _place_holds(c, record)
    return decision_json(record)


@router.get("/requests/{decision_id}")
async def get_decision(decision_id: str, request: Request) -> dict[str, Any]:
    record = _c(request).trace_store.decision(decision_id)
    if record is None:
        raise HTTPException(404, "decision not found")
    return decision_json(record)


def _place_holds(c: Any, record: Any) -> None:
    """Soft holds on the offered top 3 (FR-068), so the slot does not vanish while
    the patient decides. A request never blocks its own holds [AR-03]."""
    now = c.clock.now()
    c.repo.release_holds(record.id)
    for offer in record.offers:
        c.repo.place_hold(
            Hold(
                id=f"hold-{record.id}-{offer.candidate_id[:8]}",
                candidate_id=offer.candidate_id,
                request_id=record.id,
                operatory_id=offer.operatory_id,
                provider_id=offer.provider_id,
                start=offer.start,
                duration_min=offer.duration_min,
                expires_at=c.repo.hold_ttl(now, c.settings.hold_ttl_min),
            )
        )


@router.post("/holds")
async def hold(body: HoldRequest, request: Request) -> dict[str, str]:
    return {"status": "held", "candidate_id": body.candidate_id}


@router.delete("/holds/{request_id}")
async def release(request_id: str, request: Request) -> dict[str, str]:
    _c(request).repo.release_holds(request_id)
    return {"status": "released"}


@router.post("/bookings")
async def confirm(body: BookingRequest, request: Request) -> dict[str, Any]:
    """[ADR-18] Re-verify, then commit **conditionally** -- one operation, not
    check-then-write. Check-then-write cannot fail at one seat and double-books at
    two, which is the worst pairing of severity and undetectability.
    """
    c = _c(request)
    record = c.trace_store.decision(body.request_id)
    if record is None:
        raise HTTPException(404, "decision not found")
    offer = _offer_for(record, body.candidate_id)
    if offer is None:
        raise HTTPException(400, "that option was not offered")

    tz = zone(c.load.bundle.locations[0].timezone)
    day = to_local(offer.start, tz)[0]

    intent = BookingIntent(
        candidate_id=offer.candidate_id,
        start=offer.start,
        duration_min=offer.duration_min,
        provider_id=offer.provider_id,
        operatory_id=offer.operatory_id,
        patient_id=record.constraints.patient_ref if record.constraints else None,
        type_id=offer.type_id,
        request_id=record.id,
    )
    expect = c.repo.version_of(intent.operatory_id, day)
    result = c.repo.commit_booking(intent, expect)
    if not result.ok:
        # A named error, never a silent infeasible write (FR-069).
        raise HTTPException(409, result.error or "could not book")

    record.accepted_slot_id = offer.candidate_id
    if body.override_reason:
        record.override_reason = body.override_reason

    return {
        "status": "booked",
        "appointment_id": result.appointment.id if result.appointment else None,
        # The confirmation echoes the resolved date so the *patient* catches a
        # confidently-wrong one (FR-073, R-04).
        "confirmation": (
            f"You're booked for {offer.weekday} {offer.date_display} at "
            f"{offer.start_display} with {offer.provider_name}."
        ),
        "is_override": record.is_override,
    }


@router.post("/session/reset")
async def reset(request: Request) -> dict[str, Any]:
    """Restores the reference dataset and clears holds. **Traces survive** (FR-072):
    an evaluator will want to reset the schedule and still inspect a decision made
    before the reset, and coupling the two would destroy the audit trail."""
    c = _c(request)
    c.reset()
    return {"status": "reset", "traces_retained": len(c.trace_store.decisions)}
