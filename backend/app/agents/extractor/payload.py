"""The wire model for extraction, kept deliberately separate from the domain model.

Structured outputs accept a subset of JSON Schema. ``RequestConstraints`` uses
`frozenset`, nested tuples and constrained fields, and pydantic renders those as
`uniqueItems`, `prefixItems`, `minimum` and friends -- all rejected. Deriving the
schema and stripping keywords turned into whack-a-mole, one 400 per round trip.

So the wire shape is **flat and boring on purpose**: lists instead of sets, ints
instead of tuples, one level of nesting. It is a separate model rather than a relaxed
domain model because the domain model's strictness is load-bearing -- ``Exclusions``
being a frozenset is what makes candidate rejection cheap.

Drift between the two is caught by ``to_constraints`` plus a round-trip test, not by
hope.
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


class SpanPayload(Flat):
    text: str
    start: int
    end: int


class Meta(Flat):
    """Provenance for one field. Every field carries this (FR-002, FR-003)."""

    confidence: float
    derived: bool
    derived_rule: str | None = None
    span: SpanPayload | None = None


class ExtractionPayload(Flat):
    date_start: str  # ISO date
    date_end: str
    date_meta: Meta

    time_start_min: int | None  # minutes from local midnight; null = from opening
    time_end_min: int | None  # null = until close
    time_meta: Meta

    urgency: str  # emergency | urgent | routine | flexible
    urgency_meta: Meta

    provider_id: str | None
    provider_meta: Meta

    appointment_type: str
    type_meta: Meta

    exclude_weekdays: list[int]  # 0 = Monday
    exclusions_meta: Meta

    # -- mapping ---------------------------------------------------------------
    def to_constraints(self, text: str, patient_ref: str | None) -> RequestConstraints:
        return RequestConstraints(
            request_text=text,
            patient_ref=patient_ref,
            date_range=self._field(
                DateWindow(start=date.fromisoformat(self.date_start),
                           end=date.fromisoformat(self.date_end)),
                self.date_meta,
            ),
            time_window=self._field(
                TimeWindow(start_min=self.time_start_min, end_min=self.time_end_min),
                self.time_meta,
            ),
            urgency=self._field(Urgency(self.urgency), self.urgency_meta),
            provider_preference=self._field(self.provider_id, self.provider_meta),
            appointment_type=self._field(self.appointment_type, self.type_meta),
            exclusions=self._field(
                Exclusions(weekdays=frozenset(self.exclude_weekdays)), self.exclusions_meta
            ),
        )

    @staticmethod
    def _field(value: object, meta: Meta) -> FieldValue:  # type: ignore[type-arg]
        span = (
            SourceSpan(text=meta.span.text, start=meta.span.start, end=meta.span.end)
            if meta.span
            else None
        )
        # A model that returns neither a span nor a derivation rule has told us
        # nothing about provenance; treat that as derived rather than accept a field
        # with no accountability.
        derived = meta.derived or span is None
        return FieldValue(
            value=value,
            confidence=meta.confidence,
            span=None if derived else span,
            derived=derived,
            derived_rule=(meta.derived_rule or "model-did-not-cite-a-span") if derived else None,
        )


def wire_schema() -> dict:  # type: ignore[type-arg]
    """Flat enough that no unsupported keyword can appear."""
    schema = ExtractionPayload.model_json_schema()
    return _tighten(schema)  # type: ignore[return-value]


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
