"""Deterministic extractor. No network, ever (FR-005).

Two jobs, and the second is the one people miss:

1. It is the **fallback** when the LLM times out, returns bad JSON, or is switched off.
2. It is the **measurement baseline**. The harness reports rules-mode and LLM-mode
   per-field accuracy as two columns (FR-093), and that pair of numbers is the entire
   evidence for "would replacing this with plain code change decision quality?".
   Without it, using an LLM here is a preference rather than a finding.

In production there are no committed fixtures, so this *is* the degraded mode -- its
accuracy number is a service level, not a curiosity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.entities import Patient, SeedBundle
from app.domain.enums import Urgency
from app.domain.request import (
    DateWindow,
    Exclusions,
    FieldValue,
    RequestConstraints,
    SourceSpan,
    TimeWindow,
)

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4,
}

TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bnew patient\b|\bfirst visit\b", "np_exam_fmx"),
    (r"\bcrown\b.*\b(fit|seat|back|ready|put on)\b|\b(fit|seat)\b.*\bcrown\b", "crown_seat"),
    (r"\bcrown\b", "crown_prep"),
    (r"\broot canal\b|\brct\b", "rct"),
    (r"\bextract|\bpull(ed|ing)?\b.*\btooth\b|\btooth\b.*\bpull", "extraction"),
    (r"\bdenture", "denture_adjust"),
    (r"\bgum\b|\bperio", "perio_maint"),
    (r"\bfilling\b|\bcavit", "filling_1s"),
    (r"\b(kid|child|son|daughter)\b.*\b(clean|check)", "prophy_child"),
    (r"\bclean(ing)?\b|\bcheck-?up\b|\bhygien", "prophy_adult"),
    (r"\bhurt|\bache|\baching|\bpain|\bsore\b|\bbothering\b|\bchipped\b|\bbroke"
     r"|\bkilling me\b|\bswollen\b|\bthrobbing\b|\bsensitive\b", "limited_exam"),
)

URGENT_PATTERNS = (
    (r"\bemergenc", Urgency.EMERGENCY),
    (r"\bas soon as possible\b|\basap\b|\burgent|\bright away\b|\btoday\b", Urgency.URGENT),
    (r"\bkilling me\b|\breally hurts?\b|\bsevere\b|\bswollen\b", Urgency.URGENT),
    (r"\bwhenever\b|\bno rush\b|\bflexible\b|\bany ?time\b", Urgency.FLEXIBLE),
)

_MORNING = (8 * 60, 12 * 60)
_AFTERNOON = (13 * 60, 17 * 60)
_FIRST_THING = (8 * 60, 10 * 60)


@dataclass
class _Hit:
    value: object
    span: SourceSpan | None
    confidence: float


def _span(text: str, match: re.Match[str]) -> SourceSpan:
    return SourceSpan(text=text[match.start() : match.end()], start=match.start(), end=match.end())


def _derived(value: object, rule: str, confidence: float = 0.75) -> FieldValue:  # type: ignore[type-arg]
    return FieldValue(value=value, confidence=confidence, derived=True, derived_rule=rule)


class RuleIntentExtractor:
    """Implementation B of ``IntentExtractor``."""

    name = "rules"

    def __init__(self, world: SeedBundle) -> None:
        self._world = world
        self._provider_names = {p.name.lower(): p.id for p in world.providers}
        self._surnames = {
            p.name.lower().split()[-1]: p.id for p in world.providers if " " in p.name
        }

    async def extract(
        self, text: str, patient: Patient | None, now: datetime
    ) -> RequestConstraints:
        """Async to satisfy the protocol; the work is synchronous and does no I/O."""
        return self.extract_sync(text, patient, now)

    def extract_sync(
        self, text: str, patient: Patient | None, now: datetime
    ) -> RequestConstraints:
        low = text.lower()
        today = now.date()

        type_hit = self._appointment_type(low, text)
        appointment_type = self._world.appointment_type(str(type_hit.value))
        # Exclusions are resolved first: a weekday the patient ruled out must never
        # be read as the weekday they asked for.
        exclusions = self._exclusions(low, text)

        return RequestConstraints(
            request_text=text,
            patient_ref=patient.id if patient else None,
            date_range=self._date_range(low, text, today, exclusions.value.weekdays),
            time_window=self._time_window(low, text),
            urgency=self._urgency(low, text, appointment_type.default_urgency),
            provider_preference=self._provider(low, text),
            appointment_type=FieldValue(
                value=type_hit.value, confidence=type_hit.confidence, span=type_hit.span
            )
            if type_hit.span
            else _derived(type_hit.value, "default-appointment-type", type_hit.confidence),
            exclusions=exclusions,
        )

    # -- date ------------------------------------------------------------------
    def _date_range(  # type: ignore[type-arg]
        self, low: str, text: str, today: date, excluded: frozenset[int] = frozenset()
    ) -> FieldValue:
        m = re.search(r"\btomorrow\b", low)
        if m:
            d = today + timedelta(days=1)
            return FieldValue(
                value=DateWindow(start=d, end=d), confidence=0.95, span=_span(text, m)
            )

        m = re.search(r"\btoday\b", low)
        if m:
            return FieldValue(
                value=DateWindow(start=today, end=today), confidence=0.95, span=_span(text, m)
            )

        m = re.search(r"\b(next|this|coming)\s+(" + "|".join(WEEKDAYS) + r")\b", low)
        if m and WEEKDAYS[m.group(2)] not in excluded:
            target = WEEKDAYS[m.group(2)]
            ahead = (target - today.weekday()) % 7 or 7
            d = today + timedelta(days=ahead)
            # From a Monday, "next Thursday" is genuinely either this week's or next
            # week's [D-03]. The nearer reading is taken with reduced confidence; the
            # verifier raises the second hypothesis, and the decision-relevance test
            # decides whether it is worth a question (FR-011).
            confidence = 0.55 if m.group(1) == "next" else 0.9
            return FieldValue(value=DateWindow(start=d, end=d), confidence=confidence,
                              span=_span(text, m))

        m = re.search(r"\b(" + "|".join(WEEKDAYS) + r")\b", low)
        if m and WEEKDAYS[m.group(1)] not in excluded:
            target = WEEKDAYS[m.group(1)]
            ahead = (target - today.weekday()) % 7 or 7
            d = today + timedelta(days=ahead)
            return FieldValue(value=DateWindow(start=d, end=d), confidence=0.8, span=_span(text, m))

        m = re.search(r"\bnext week\b", low)
        if m:
            start = today + timedelta(days=7 - today.weekday())
            return FieldValue(
                value=DateWindow(start=start, end=start + timedelta(days=4)),
                confidence=0.85,
                span=_span(text, m),
            )

        m = re.search(r"\bthis week\b", low)
        if m:
            return FieldValue(
                value=DateWindow(start=today, end=today + timedelta(days=4 - today.weekday())),
                confidence=0.85,
                span=_span(text, m),
            )

        return _derived(
            DateWindow(start=today, end=today + timedelta(days=14)), "default-search-horizon", 0.6
        )

    # -- time ------------------------------------------------------------------
    def _time_window(self, low: str, text: str) -> FieldValue:  # type: ignore[type-arg]
        m = re.search(r"\bafter\s+(\d{1,2})\s*(am|pm|:\d{2})?", low)
        if m:
            hour = self._hour(int(m.group(1)), m.group(2), prefer_pm=True)
            return FieldValue(
                value=TimeWindow(start_min=hour * 60, end_min=None),
                confidence=0.9,
                span=_span(text, m),
            )

        m = re.search(r"\bbefore\s+(\d{1,2})\s*(am|pm)?|\bbefore\s+(noon)\b", low)
        if m:
            hour = 12 if m.group(3) else self._hour(int(m.group(1)), m.group(2), prefer_pm=False)
            return FieldValue(
                value=TimeWindow(start_min=None, end_min=hour * 60),
                confidence=0.9,
                span=_span(text, m),
            )

        for pattern, window in (
            (r"\bfirst thing\b|\bearly\b", _FIRST_THING),
            (r"\bmorning\b", _MORNING),
            (r"\bafternoon\b|\bafter (?:school|work)\b", _AFTERNOON),
        ):
            m = re.search(pattern, low)
            if m:
                return FieldValue(
                    value=TimeWindow(start_min=window[0], end_min=window[1]),
                    confidence=0.85,
                    span=_span(text, m),
                )

        return _derived(TimeWindow(), "default-business-hours", 0.7)

    @staticmethod
    def _hour(value: int, suffix: str | None, *, prefer_pm: bool) -> int:
        if suffix and "pm" in suffix and value < 12:
            return value + 12
        if suffix and "am" in suffix:
            return value
        # "after 3" in a dental practice means 15:00, not 03:00. This is the ranked
        # #1 failure mode -- silent, plausible, and wrong -- which is exactly why the
        # interpretation strip shows the resolved value and its source words.
        if prefer_pm and value < 8:
            return value + 12
        return value

    # -- urgency ---------------------------------------------------------------
    def _urgency(self, low: str, text: str, default: Urgency) -> FieldValue:  # type: ignore[type-arg]
        for pattern, urgency in URGENT_PATTERNS:
            m = re.search(pattern, low)
            if m:
                return FieldValue(value=urgency, confidence=0.9, span=_span(text, m))
        return _derived(default, "appointment-type-default-urgency", 0.7)

    # -- provider --------------------------------------------------------------
    def _provider(self, low: str, text: str) -> FieldValue:  # type: ignore[type-arg]
        for name, pid in sorted(self._provider_names.items(), key=lambda kv: -len(kv[0])):
            m = re.search(rf"\b{re.escape(name)}\b", low)
            if not m:
                continue
            before = low[max(0, m.start() - 12) : m.start()]
            if re.search(r"\bnot\b|\bno\b|\banyone but\b", before):
                return _derived(None, "provider-named-but-excluded", 0.8)
            return FieldValue(value=pid, confidence=0.9, span=_span(text, m))

        for surname, pid in sorted(self._surnames.items(), key=lambda kv: -len(kv[0])):
            m = re.search(rf"\b{re.escape(surname)}\b", low)
            if m:
                return FieldValue(value=pid, confidence=0.85, span=_span(text, m))

        return _derived(None, "no-provider-named", 0.8)

    # -- exclusions ------------------------------------------------------------
    def _exclusions(self, low: str, text: str) -> FieldValue:  # type: ignore[type-arg]
        weekdays: set[int] = set()
        span: SourceSpan | None = None

        days = "|".join(WEEKDAYS)
        # A trailing "(?:s?\s*(?:,|or|and)\s*<weekday>)*" catches "Wednesdays or
        # Fridays" -- people list the days they cannot do, and capturing only the
        # first silently drops a hard constraint, which is the worst behaviour here.
        listed = rf"({days})s?(?:\s*(?:,|or|and)\s*(?:{days})s?)*"
        for pattern in (
            rf"\b(?:not|no|never|can'?t do|cannot do|can not do|avoid|except|excluding)"
            rf"\s+(?:on\s+)?{listed}",
            rf"\bi have\b[a-z ]{{0,14}}?\bon\s+{listed}",
            rf"\b{listed}\s+(?:are|is)\s+(?:no good|out|bad)\b",
        ):
            for m in re.finditer(pattern, low):
                # `s?` matters: "Wednesdays" must yield "wednesday".
                for name in re.findall(rf"\b({days})s?\b", m.group(0)):
                    weekdays.add(WEEKDAYS[name])
                if span is None:
                    span = _span(text, m)

        if weekdays:
            return FieldValue(
                value=Exclusions(weekdays=frozenset(weekdays)), confidence=0.9, span=span
            )
        return _derived(Exclusions(), "no-exclusions-stated", 0.8)

    # -- type ------------------------------------------------------------------
    def _appointment_type(self, low: str, text: str) -> _Hit:
        for pattern, type_id in TYPE_PATTERNS:
            m = re.search(pattern, low)
            if m:
                # A symptom is genuinely ambiguous between a short look and real work
                # (edge case 6a); the verifier decides whether that matters.
                confidence = 0.55 if type_id == "limited_exam" else 0.9
                return _Hit(type_id, _span(text, m), confidence)
        return _Hit("prophy_adult", None, 0.5)
