"""What the extractor produces and the reasoner consumes.

Everything downstream of ``RequestConstraints`` is deterministic (FR-054). This type
is therefore the exact boundary between "language, which can be wrong" and
"arithmetic, which cannot" -- so every field carries its confidence and the verbatim
words it came from (FR-002, FR-003). That provenance is not decoration: it is what
lets an operator trust the search without re-reading the request.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import Urgency
from app.domain.phi import PHI

OPEN = None  # time-window sentinel: "from opening"
CLOSE = None  # time-window sentinel: "until closing"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceSpan(Frozen):
    """The exact substring that produced a field, with its offsets.

    FR-003 asserts ``request_text[start:end] == text`` for every emitted span over the
    whole golden set. A fabricated span is worse than no span, which is why fields
    with no textual basis are marked ``derived`` instead of being given one.
    """

    text: Annotated[str, PHI]
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> SourceSpan:
        if self.end <= self.start:
            raise ValueError("SourceSpan.end must be after .start")
        if len(self.text) != self.end - self.start:
            raise ValueError("SourceSpan.text length must match its offsets")
        return self


class FieldValue[T](Frozen):
    value: T
    confidence: float = Field(ge=0.0, le=1.0)
    span: SourceSpan | None = None
    derived: bool = False
    derived_rule: str | None = None

    @model_validator(mode="after")
    def _provenance(self) -> FieldValue[T]:
        # FR-003: a field either points at the words that produced it, or admits it
        # was derived and names the rule. There is no third option.
        if self.span is None and not self.derived:
            raise ValueError("field needs either a source span or derived=True")
        if self.derived and not self.derived_rule:
            raise ValueError("derived fields must name the rule that derived them")
        return self

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < 0.6  # theta, [A-06]


class DateWindow(Frozen):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateWindow:
        if self.end < self.start:
            raise ValueError("DateWindow.end must not precede .start")
        return self

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end


class TimeWindow(Frozen):
    """Minute offsets from local midnight. ``None`` means open / close."""

    start_min: int | None = None
    end_min: int | None = None

    def contains(self, minute: int) -> bool:
        if self.start_min is not None and minute < self.start_min:
            return False
        return not (self.end_min is not None and minute > self.end_min)

    def distance_outside(self, minute: int) -> int:
        """Minutes by which ``minute`` falls outside the window; 0 when inside.

        Time fit is piecewise rather than binary (FR-040), so the scorer needs the
        magnitude of the miss, not just the fact of it.
        """
        if self.start_min is not None and minute < self.start_min:
            return self.start_min - minute
        if self.end_min is not None and minute > self.end_min:
            return minute - self.end_min
        return 0


class Exclusions(Frozen):
    """Patient-stated hard constraints. Never relaxed -- not by the counterfactual
    engine (FR-057), not by escalation, not by any weight vector. Suggesting a
    Tuesday to a patient who said "not Tuesdays, I have PT" is worse than offering
    nothing at all."""

    weekdays: frozenset[int] = frozenset()
    dates: frozenset[date] = frozenset()
    provider_ids: frozenset[str] = frozenset()
    time_ranges: tuple[tuple[int, int], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.weekdays or self.dates or self.provider_ids or self.time_ranges)

    def excludes(self, d: date, start_min: int, end_min: int, provider_id: str) -> bool:
        if d.weekday() in self.weekdays or d in self.dates:
            return True
        if provider_id in self.provider_ids:
            return True
        return any(start_min < hi and lo < end_min for lo, hi in self.time_ranges)


class RequestConstraints(Frozen):
    """The typed reading of one request. The LLM's entire output surface."""

    request_text: Annotated[str, PHI]
    patient_ref: str | None
    date_range: FieldValue[DateWindow]
    time_window: FieldValue[TimeWindow]
    urgency: FieldValue[Urgency]
    provider_preference: FieldValue[str | None]
    appointment_type: FieldValue[str]
    exclusions: FieldValue[Exclusions]

    def spans_are_verbatim(self) -> bool:
        """FR-003's assertion, callable at runtime as well as in tests."""
        for fv in self._fields():
            if fv.span is None:
                continue
            if self.request_text[fv.span.start : fv.span.end] != fv.span.text:
                return False
        return True

    def _fields(self) -> tuple[FieldValue, ...]:  # type: ignore[type-arg]
        return (
            self.date_range,
            self.time_window,
            self.urgency,
            self.provider_preference,
            self.appointment_type,
            self.exclusions,
        )

    def low_confidence_fields(self) -> tuple[str, ...]:
        names = (
            "date_range",
            "time_window",
            "urgency",
            "provider_preference",
            "appointment_type",
            "exclusions",
        )
        return tuple(n for n, fv in zip(names, self._fields(), strict=True) if fv.is_low_confidence)


class Hypothesis(Frozen):
    """One reading of an ambiguous field.

    Fan-out is capped at 2 hypotheses per field and 1 field per request
    (FR-012, FR-014). ``field`` names which constraint differs, which is what lets
    the reasoner decide whether Layer 0 can be shared (§8.3, §9).
    """

    field: str
    label: str  # operator-facing, e.g. "Thursday the 13th"
    constraints: RequestConstraints
    confidence: float = Field(ge=0.0, le=1.0)


class Flag(Frozen):
    code: str
    message: str  # operator-facing; passes the read-aloud lint


class Question(Frozen):
    """At most one per request (FR-012), with concrete chips and never free text."""

    field: str
    text: str
    chips: tuple[str, ...] = Field(min_length=2, max_length=3)


class VerifierVerdict(Frozen):
    outcome: str  # "proceed" | "proceed_with_flags" | "ask"
    flags: tuple[Flag, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    question: Question | None = None
