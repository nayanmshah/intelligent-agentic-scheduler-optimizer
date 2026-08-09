"""Wire shapes. Deliberately separate from the domain types.

Every decision-bearing response carries the funnel, the ledger, the trace id, **both**
the nominal and effective weight vectors (§8.7), and both renderings of each reason
line (FR-060) -- so the UI never has to ask a second question to show its work.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.decision import DecisionRecord

#: Long enough for any real request, short enough that a paste accident or a
#: deliberate flood cannot make the extractor the slow part of someone else's day.
MAX_REQUEST_CHARS = 2000


class SubmitRequest(BaseModel):
    text: str = Field(max_length=MAX_REQUEST_CHARS)
    patient_id: str | None = None
    #: FR-110. The transcript is submitted as text like any other request -- this only
    #: records *how it arrived*, so a scorecard can slice by input mode. A closed set,
    #: because an open string here becomes an unqueryable field within a month.
    source: Literal["text", "voice"] = "text"

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        """A blank request is not a request.

        Without this the pipeline answers it: every field falls back to a default --
        14-day horizon, routine, adult cleaning, any time -- and three confident
        offers come back for a question nobody asked. An operator who fat-fingers
        Enter on an empty box should get an error, not a plausible answer.
        """
        if not v.strip():
            raise ValueError("a request needs some text")
        return v


class AnswerRequest(BaseModel):
    choice: str


class HoldRequest(BaseModel):
    request_id: str
    candidate_id: str


class BookingRequest(BaseModel):
    request_id: str
    candidate_id: str
    override_reason: str | None = None


class WeightsPayload(BaseModel):
    time_fit: float
    continuity: float
    efficiency: float
    prime_time: float


class RerankRequest(BaseModel):
    request_id: str
    weights: WeightsPayload


def offer_json(o: Any) -> dict[str, Any]:
    return {
        "candidate_id": o.candidate_id,
        "weekday": o.weekday,
        "date_display": o.date_display,
        "start_display": o.start_display,
        "provider_name": o.provider_name,
        "operatory_name": o.operatory_name,
        "duration_min": o.duration_min,
        "type_name": o.type_name,
        "score": o.score,
        "contributions": [
            {"axis": c.axis, "value": c.value, "weight": c.weight, "weighted": c.weighted}
            for c in o.contributions
        ],
        # Both renderings, so the two can be compared directly (FR-060).
        "reason": o.reason,
        "template_reason": o.template_reason,
        "llm_reason": o.llm_reason,
        "gate_fired": o.gate_fired,
        "coequal_group": o.coequal_group,
        "is_overflow": o.is_overflow,
        "emergency_hold_released": o.emergency_hold_released,
    }


def field_json(fv: Any, name: str) -> dict[str, Any]:
    value = fv.value
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif hasattr(value, "value"):
        value = value.value
    return {
        "name": name,
        "value": value,
        "confidence": fv.confidence,
        "derived": fv.derived,
        "derived_rule": fv.derived_rule,
        "span": (
            {"text": fv.span.text, "start": fv.span.start, "end": fv.span.end}
            if fv.span
            else None
        ),
    }


def decision_json(r: DecisionRecord) -> dict[str, Any]:
    c = r.constraints
    return {
        "id": r.id,
        "trace_id": r.trace_id,
        "raw_text": r.raw_text,
        "source": r.source,
        "origin_state": r.origin_state.value,
        "question": r.question_asked,
        "flags": list(r.flags),
        "limited_availability": r.limited_availability,
        "interpretation": (
            [
                field_json(c.date_range, "date_range"),
                field_json(c.time_window, "time_window"),
                field_json(c.urgency, "urgency"),
                field_json(c.provider_preference, "provider_preference"),
                field_json(c.appointment_type, "appointment_type"),
                field_json(c.exclusions, "exclusions"),
            ]
            if c
            else []
        ),
        "funnel": (
            {
                "grid_slots": r.funnel.grid_slots,
                "enumerated": r.funnel.enumerated,
                "feasible": r.funnel.feasible,
                "in_tier": r.funnel.in_tier,
                "offered": r.funnel.offered,
            }
            if r.funnel
            else None
        ),
        "offers": [offer_json(o) for o in r.offers],
        "overflow": [offer_json(o) for o in r.overflow],
        "ledger": [
            {"reason": g.reason.value, "count": g.count, "sentence": g.sentence}
            for g in r.ledger
        ],
        "counterfactual": (
            {"sentence": r.counterfactual.sentence, "gain": r.counterfactual.gain}
            if r.counterfactual
            else None
        ),
        "weights": {
            "profile_id": r.weight_profile_id,
            # Both, because a continuity multiplier makes them differ and the card
            # would otherwise appear to contradict the policy panel (§8.7).
            "nominal": r.nominal_weights.model_dump() if r.nominal_weights else None,
            "effective": r.effective_weights.model_dump() if r.effective_weights else None,
        },
        "fallback_fired": list(r.fallback_fired),
    }
