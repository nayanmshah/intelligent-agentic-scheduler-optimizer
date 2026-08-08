"""The Constraint Verifier. **Schedule-blind, by construction** (FR-009).

It checks the extraction against the world's facts -- is the date in the past, does
this provider exist and work here, are they credentialed for this treatment -- never
against availability. Mixing the two makes "why did it ask?" unanswerable, because
the answer would depend on scheduling state that changes minute to minute. An import
guard asserts this package cannot reach the schedule at all.

It **proposes** hypotheses; it does not decide whether to ask. The decision-relevance
test (FR-011) needs to run the deterministic pipeline under each reading and compare
the resulting top-3 sets, which is the runner's job (§9).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.domain.entities import SeedBundle
from app.domain.request import (
    DateWindow,
    FieldValue,
    Flag,
    Hypothesis,
    RequestConstraints,
    VerifierVerdict,
)

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")

#: Ambiguity classes in scope for v1.0 (FR-014). Anything beyond these is behind a
#: config flag that defaults off, and the flag is visible in config.
IN_SCOPE = ("date_range", "appointment_type")


def _ordinal(day: int) -> str:
    if 11 <= day <= 13:
        return f"{day}th"
    return f"{day}{('th', 'st', 'nd', 'rd')[day % 10] if day % 10 < 4 else 'th'}"


def label_for_date(d) -> str:  # type: ignore[no-untyped-def]
    return f"{WEEKDAY_NAMES[d.weekday()]} the {_ordinal(d.day)}"


class RuleConstraintVerifier:
    """Implementation B of ``ConstraintVerifier``."""

    name = "rules"

    def __init__(self, theta: float, allow_wider_fanout: bool = False) -> None:
        self._theta = theta
        self._wider = allow_wider_fanout

    async def verify(
        self, constraints: RequestConstraints, world: SeedBundle, now: datetime
    ) -> VerifierVerdict:
        flags = [*self._world_checks(constraints, world, now)]
        hypotheses = self._hypotheses(constraints, world, now)

        if hypotheses:
            return VerifierVerdict(
                outcome="ask", flags=tuple(flags), hypotheses=tuple(hypotheses)
            )
        return VerifierVerdict(
            outcome="proceed_with_flags" if flags else "proceed", flags=tuple(flags)
        )

    # -- world checks (FR-010) -------------------------------------------------
    def _world_checks(
        self, c: RequestConstraints, world: SeedBundle, now: datetime
    ) -> list[Flag]:
        out: list[Flag] = []
        window = c.date_range.value

        if window.end < now.date():
            out.append(
                Flag(
                    code="PAST_DATE",
                    message=(
                        "That date has already passed — did you mean "
                        f"{label_for_date(window.start + timedelta(days=7))}?"
                    ),
                )
            )

        pref = c.provider_preference.value
        if pref is not None:
            provider = next((p for p in world.providers if p.id == pref), None)
            if provider is None:
                out.append(
                    Flag(code="UNKNOWN_PROVIDER",
                         message="I don't see that provider here, so I'll look across everyone.")
                )
            else:
                appointment_type = world.appointment_type(c.appointment_type.value)
                need = appointment_type.required_credentials
                if need and not need.issubset(provider.credentials):
                    alt = next(
                        (p.name for p in world.providers if need.issubset(p.credentials)),
                        "another provider",
                    )
                    out.append(
                        Flag(
                            code="PROVIDER_NOT_CREDENTIALED",
                            message=(
                                f"{provider.name} doesn't do that treatment, "
                                f"so I'll look at {alt}."
                            ),
                        )
                    )

        ex = c.exclusions.value
        if any(lo >= hi for lo, hi in ex.time_ranges):
            # Silently dropping a hard constraint is the worst available behaviour.
            out.append(
                Flag(code="MALFORMED_EXCLUSION",
                     message="I couldn't read one of the times you wanted to avoid "
                             "— please check it.")
            )

        if (
            c.time_window.value.start_min is not None
            and c.time_window.value.end_min is not None
            and c.time_window.value.start_min >= c.time_window.value.end_min
        ):
            out.append(
                Flag(code="INVERTED_WINDOW",
                     message="That time range looked backwards, so I've used the whole day.")
            )
        return out

    # -- hypotheses (FR-014) ---------------------------------------------------
    def _hypotheses(
        self, c: RequestConstraints, world: SeedBundle, now: datetime
    ) -> list[Hypothesis]:
        """At most one field, at most two readings (FR-012, FR-014)."""
        date_alts = self._date_hypotheses(c, now)
        if date_alts:
            return date_alts
        return self._type_hypotheses(c, world)

    def _date_hypotheses(self, c: RequestConstraints, now: datetime) -> list[Hypothesis]:
        field = c.date_range
        if field.confidence >= self._theta or field.span is None:
            return []
        if not re.search(r"\bnext\b", field.span.text.lower()):
            return []

        near = field.value.start
        far = near + timedelta(days=7)
        return [
            Hypothesis(
                field="date_range",
                label=label_for_date(near),
                confidence=field.confidence,
                constraints=replace_field(c, "date_range",
                                          FieldValue(value=DateWindow(start=near, end=near),
                                                     confidence=0.95, span=field.span)),
            ),
            Hypothesis(
                field="date_range",
                label=label_for_date(far),
                confidence=1.0 - field.confidence,
                constraints=replace_field(c, "date_range",
                                          FieldValue(value=DateWindow(start=far, end=far),
                                                     confidence=0.95, span=field.span)),
            ),
        ]

    def _type_hypotheses(self, c: RequestConstraints, world: SeedBundle) -> list[Hypothesis]:
        field = c.appointment_type
        if field.confidence >= self._theta or field.span is None:
            return []
        if field.value != "limited_exam":
            return []
        # "my tooth's been bothering me" is either a short look or real work, and the
        # two have very different durations -- which is precisely why it changes the
        # answer (edge case 6a).
        alternatives = ("limited_exam", "crown_prep")
        return [
            Hypothesis(
                field="appointment_type",
                label=world.appointment_type(tid).name,
                confidence=field.confidence if i == 0 else 1.0 - field.confidence,
                constraints=replace_field(
                    c, "appointment_type",
                    FieldValue(value=tid, confidence=0.95, span=field.span),
                ),
            )
            for i, tid in enumerate(alternatives)
        ]


def replace_field(c: RequestConstraints, name: str, value: FieldValue) -> RequestConstraints:  # type: ignore[type-arg]
    return c.model_copy(update={name: value})
