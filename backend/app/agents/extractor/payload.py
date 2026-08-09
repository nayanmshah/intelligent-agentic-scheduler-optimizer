"""The wire model for extraction — flat, small, and quote-based on purpose.

Two constraints shape it:

1. **Structured outputs accept a subset of JSON Schema.** ``RequestConstraints`` uses
   frozensets, nested tuples and constrained fields, which render as keywords the API
   rejects. So the wire shape is a separate flat model, and the domain model keeps its
   strictness (``Exclusions`` being a frozenset is what makes rejection cheap).

2. **Latency tracks output tokens almost linearly** (measured: 558 tokens → 6.6s,
   162 → 2.0s). The first wire model made the model emit, per field, a nested meta
   object with confidence, a derived flag, a rule name, span text *and* character
   offsets. This one emits a verbatim quote and a confidence — everything else is
   computed locally:

   - **Offsets** by exact string search. Models copy text far more reliably than they
     count characters; the old shape produced offsets that disagreed with their own
     text, which failed validation and silently fell back to rules.
   - **Derived** is simply "no quote given" (or the quote is not verbatim). A field
     either points at the patient's words or admits it does not — FR-003, enforced by
     construction rather than by asking the model to self-report.

   That cut extraction output ~70% and p50 from ~7.3s to ~2.0s with no measured
   accuracy cost from the shape itself (the schema change alone, same model: 86.7%
   both ways on the probe set).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import Urgency
from app.domain.request import (
    DateWindow,
    Exclusions,
    FieldValue,
    RequestConstraints,
    SourceSpan,
    TimeWindow,
)


class Flat(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractionPayload(Flat):
    """One quote (``*_q``) and one confidence (``*_conf``) per field.

    A null quote means the value was inferred rather than stated. There is no
    ``derived`` flag to get wrong: provenance is derived from the quote itself.
    """

    date_start: str  # ISO date
    date_end: str
    date_q: str | None
    date_conf: float

    time_start_min: int | None  # minutes from local midnight; null = from opening
    time_end_min: int | None  # null = until close
    time_q: str | None
    time_conf: float

    urgency: str  # emergency | urgent | routine | flexible
    urgency_q: str | None
    urgency_conf: float

    provider_id: str | None
    provider_q: str | None
    provider_conf: float

    appointment_type: str
    type_q: str | None
    type_conf: float

    exclude_weekdays: list[int]  # 0 = Monday
    excl_q: str | None
    excl_conf: float

    # -- mapping ---------------------------------------------------------------
    def to_constraints(self, text: str, patient_ref: str | None) -> RequestConstraints:
        return RequestConstraints(
            request_text=text,
            patient_ref=patient_ref,
            date_range=_field(
                DateWindow(
                    start=date.fromisoformat(self.date_start),
                    end=date.fromisoformat(self.date_end),
                ),
                self.date_q, self.date_conf, text,
            ),
            time_window=_field(
                TimeWindow(start_min=self.time_start_min, end_min=self.time_end_min),
                self.time_q, self.time_conf, text,
            ),
            urgency=_field(Urgency(self.urgency), self.urgency_q, self.urgency_conf, text),
            provider_preference=_field(
                self.provider_id, self.provider_q, self.provider_conf, text
            ),
            appointment_type=_field(
                self.appointment_type, self.type_q, self.type_conf, text
            ),
            exclusions=_field(
                Exclusions(weekdays=frozenset(self.exclude_weekdays)),
                self.excl_q, self.excl_conf, text,
            ),
        )


def _field(value: object, quote: str | None, confidence: float, text: str) -> FieldValue:  # type: ignore[type-arg]
    """Quote -> provenance, locally.

    The span is accepted only if the quote occurs verbatim in the request, so
    ``request_text[start:end] == span.text`` holds by construction (FR-003). A
    paraphrase — the model quoting words the patient did not say — is treated as
    *derived*, never as a fabricated span.
    """
    confidence = max(0.0, min(1.0, confidence))
    if quote:
        start = text.find(quote)
        if start >= 0:
            return FieldValue(
                value=value,
                confidence=confidence,
                span=SourceSpan(text=quote, start=start, end=start + len(quote)),
                derived=False,
            )
        return FieldValue(
            value=value, confidence=confidence, span=None,
            derived=True, derived_rule="quote-not-verbatim",
        )
    return FieldValue(
        value=value, confidence=confidence, span=None,
        derived=True, derived_rule="model-inferred",
    )


def wire_schema() -> dict:  # type: ignore[type-arg]
    """Flat enough that no unsupported keyword can appear."""
    return _tighten(ExtractionPayload.model_json_schema())  # type: ignore[return-value]


def _tighten(node: object) -> object:
    if isinstance(node, dict):
        out = {k: _tighten(v) for k, v in node.items() if k not in _STRIP}
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = sorted(out["properties"])
        return out
    if isinstance(node, list):
        return [_tighten(v) for v in node]
    return node


_STRIP = frozenset({
    "uniqueItems", "prefixItems", "minItems", "maxItems", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength",
    "pattern", "default", "examples", "format",
})


def now_hint(now: datetime) -> str:
    return f"{now:%A %d %B %Y, %H:%M %Z}"
