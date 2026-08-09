"""Operator-console routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

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
        IncomingRequest(text=body.text, patient=patient, source=body.source),
        c.clock.now(),
        c.state.active_profile,
    )
    _place_holds(c, record)
    return decision_json(record)


#: What each stage is called on screen. The trace keeps the internal names; an
#: operator watching a 15-second wait needs to know what is happening to *them*.
STAGE_LABELS = {
    "extract": "Reading the request",
    "verify": "Checking it against the practice",
    "reason": "Searching every room and provider",
    "explain": "Writing the reasons",
}


class _QueueSink:
    """A ``TraceSink`` that forwards closed spans to one request's stream.

    Not registered on the container: it exists for the life of a single request, so a
    slow client cannot make the server hold spans for anybody else.
    """

    def __init__(self, queue: asyncio.Queue) -> None:  # type: ignore[type-arg]
        self._queue = queue

    def emit(self, span: Any) -> None:
        if span.stage in STAGE_LABELS:
            self._queue.put_nowait(span)

    def record_decision(self, record: Any) -> None:  # pragma: no cover - not used here
        pass


@router.post("/requests/stream")
async def submit_stream(body: SubmitRequest, request: Request) -> StreamingResponse:
    """The same decision as ``POST /requests``, with the stages narrated as they close.

    A live request is three sequential model calls and takes ~15 seconds. A button that
    only says "…" for that long reads as frozen -- that is how the first person to use
    it described it. The stages already emit spans; this streams them, so the wait
    *shows the pipeline working* rather than hiding it.

    Which is the better answer twice over: the honest fix for the latency complaint is
    also the clearest demonstration that there are agents here at all.
    """
    c = _c(request)
    patient = c.load.bundle.patient(body.patient_id) if body.patient_id else None
    queue: asyncio.Queue = asyncio.Queue()

    async def events() -> AsyncIterator[str]:
        def sse(event: str, data: dict) -> str:  # type: ignore[type-arg]
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        task = asyncio.create_task(
            c.orchestrator.run(
                IncomingRequest(text=body.text, patient=patient, source=body.source),
                c.clock.now(),
                c.state.active_profile,
                progress=_QueueSink(queue),
            )
        )
        for stage, label in STAGE_LABELS.items():
            yield sse("pending", {"stage": stage, "label": label})

        # Drain as stages close. The timeout is a poll, not a deadline: without it a
        # request whose last span has already been emitted would block here forever.
        while not task.done() or not queue.empty():
            try:
                span = await asyncio.wait_for(queue.get(), timeout=0.2)
            except TimeoutError:
                continue
            yield sse("stage", {
                "stage": span.stage,
                "label": STAGE_LABELS[span.stage],
                "ms": round(span.duration_ms),
                "implementation": span.attrs.get("implementation"),
                "fallback_fired": bool(span.attrs.get("fallback_fired")),
            })

        try:
            record = await task
        except Exception as exc:  # the client gets a named failure, never a hung stream
            yield sse("error", {"detail": str(exc)})
            return
        _place_holds(c, record)
        yield sse("decision", decision_json(record))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Proxies and browsers will otherwise buffer an event stream into uselessness.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/requests/{decision_id}/answer")
async def answer(decision_id: str, body: AnswerRequest, request: Request) -> dict[str, Any]:
    """Answering re-runs the deterministic pipeline only -- zero LLM calls (FR-011)."""
    c = _c(request)
    prior = c.trace_store.decision(decision_id)
    if prior is None:
        raise HTTPException(404, "decision not found")
    record = await c.orchestrator.run(
        IncomingRequest(
            text=f"{prior.raw_text} ({body.choice})", patient=None, source=prior.source
        ),
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


@router.get("/requests/{decision_id}/why-options")
async def why_options(decision_id: str, request: Request) -> dict[str, Any]:
    """The days and start times an operator can actually ask about (FR-109).

    Generated from the same business hours and grid granularity the search used, so
    every option offered is a time an appointment could conceivably start -- asking
    "why not 3:07?" of a ten-minute grid is a question with no honest answer.
    """
    c = _c(request)
    record = c.trace_store.decision(decision_id)
    if record is None or record.constraints is None:
        raise HTTPException(404, "decision not found")

    from app.reasoner.enumerate import horizon_days

    loc = c.repo.seed.locations[0]
    step = c.settings.grid_granularity_min
    days, times = [], {}
    for d in horizon_days(record.now.date(), c.settings, loc):
        hours = loc.hours_for(d.weekday())
        if hours is None:
            continue
        days.append({"value": d.isoformat(), "label": _day_label(d)})
        times[d.isoformat()] = [
            {"value": _hhmm(m), "label": _clock_label(m)}
            for m in range(hours.open_min, hours.close_min, step)
        ]
    # Land on the day the offers are on: the operator is being asked about *that*
    # afternoon, not the first day of the horizon.
    offered = record.offers[0].day.isoformat() if record.offers else None
    known = {d["value"] for d in days}
    return {
        "days": days,
        "times": times,
        "default_day": offered if offered in known else (days[0]["value"] if days else None),
    }


@router.get("/requests/{decision_id}/why")
async def why_not(
    decision_id: str, request: Request, at: str, day: str | None = None
) -> dict[str, Any]:
    """FR-109 -- "but isn't 3 o'clock free?", answered for that one time.

    The ledger groups every rejection by cause, which is the right grain for "where did
    13,000 candidates go?" and the wrong grain for the question a patient actually asks.
    This counts only the candidates starting at one time, and keeps "nothing there was
    bookable" separate from "it was bookable and simply outranked" -- different answers,
    and only one of them is a refusal.
    """
    c = _c(request)
    record = c.trace_store.decision(decision_id)
    if record is None or record.constraints is None:
        raise HTTPException(404, "decision not found")
    try:
        hh, mm = at.split(":")
        start_min = int(hh) * 60 + int(mm)
    except ValueError:
        raise HTTPException(422, "at must be HH:MM") from None
    try:
        target = (
            date.fromisoformat(day)
            if day
            else (record.offers[0].day if record.offers else record.now.date())
        )
    except ValueError:
        raise HTTPException(422, "day must be YYYY-MM-DD") from None

    # ``request_id=record.id`` matters: this decision placed soft holds on its own
    # top three (FR-068), and a request never blocks its own holds [AR-03]. Without
    # it the lookup reports the offered slots as "held for another patient" -- held
    # for *this* patient -- and reports them as not bookable at all.
    e = c.reasoner.explain_slot(record.constraints, record.now, target, start_min, record.id)

    # How many of the bookable ones are already on screen. "Outranked" is false about
    # a time the operator is looking at in the top three.
    tz = zone(c.repo.seed.locations[0].timezone)
    offered_here = sum(
        1
        for o in (*record.offers, *record.overflow)
        if to_local(o.start, tz) == (target, start_min)
    )
    return {
        "day": e.day.isoformat(),
        "day_label": _day_label(e.day),
        "at": _clock_label(e.start_min),
        "considered": e.considered,
        "bookable": e.bookable,
        "offered": offered_here,
        "causes": [
            {"reason": g.reason.value, "count": g.count, "sentence": g.sentence}
            for g in e.causes
        ],
    }


_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _day_label(d: date) -> str:
    return f"{_WEEKDAYS[d.weekday()]}, {_MONTHS[d.month - 1]} {d.day}"


def _hhmm(minute_of_day: int) -> str:
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def _clock_label(minute_of_day: int) -> str:
    h, m = divmod(minute_of_day, 60)
    suffix = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12}:{m:02d} {suffix}"


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
