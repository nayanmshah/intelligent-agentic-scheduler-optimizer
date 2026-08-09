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

    #: Words a patient uses for damage or acute trouble. Paired with a reading of
    #: routine hygiene, they are the one mismatch that must never depend on a model
    #: being in the mood: the patient is understating an injury, and the practice
    #: needs to know before the visit. The model still runs on top and catches the
    #: phrasings this list does not have -- this is a floor, not a replacement.
    _DAMAGE_WORDS = (
        "fell off", "fell out", "came off", "came out", "broke", "broken", "chipped",
        "cracked", "knocked out", "lost a filling", "lost my filling", "swollen",
        "abscess", "pus", "bleeding",
    )
    #: Readings that mean "a routine clean", i.e. no repair happens at this visit.
    _HYGIENE_TYPES = ("prophy_adult", "prophy_child", "perio_maint")
    #: What a patient calls a routine visit in their own words.
    _HYGIENE_WORDS = ("cleaning", "clean", "polish", "hygiene", "check-up", "checkup")

    def _symptom_type_mismatch(self, c: RequestConstraints) -> Flag | None:
        """FR-009. "My crown fell off, can I get a cleaning?", checked deterministically.

        **Two directions, because the extractor resolves this request both ways.**
        Sometimes it takes the patient at their word and reads *cleaning*, leaving
        damage words contradicting the reading. Sometimes it infers the repair itself
        and reads *crown seat* — no contradiction left, but now the operator is about
        to book something the patient did not ask for, which they equally need told.
        Only the first direction existed when this relied on the model, which is why
        the warning went missing on runs where extraction was cleverer, not worse.

        The model still runs on top and covers phrasings this word list does not have.
        This is a floor, not a replacement.
        """
        text = c.request_text.lower()
        reading_is_hygiene = c.appointment_type.value in self._HYGIENE_TYPES
        hit = next((w for w in self._DAMAGE_WORDS if w in text), None)
        asked_hygiene = any(w in text for w in self._HYGIENE_WORDS)
        if hit is None:
            return None

        said = self._clause_around(c.request_text, hit)
        if reading_is_hygiene:
            return Flag(
                code="SYMPTOM_TYPE_MISMATCH",
                message=f"You said {said} — that needs a repair visit, not a cleaning.",
            )
        if asked_hygiene:
            return Flag(
                code="SYMPTOM_TYPE_MISMATCH",
                message=(
                    f"You asked for a cleaning, but you said {said} — "
                    "these times fix that first."
                ),
            )
        return None

    @staticmethod
    def _clause_around(text: str, needle: str) -> str:
        """The patient's own clause, quoted back. A warning that names the thing
        ("your crown fell off") is one an operator can read out; a warning about
        "something broken" is a category, and categories do not end phone calls."""
        lower = text.lower()
        at = lower.find(needle)
        start = max((lower.rfind(ch, 0, at) for ch in ",.;?!"), default=-1) + 1
        end = min(
            (i for i in (lower.find(ch, at) for ch in ",.;?!") if i != -1),
            default=len(text),
        )
        clause = text[start:end].strip().rstrip(",")
        words = clause.split()
        if len(words) > 6:
            # Centre on the damage phrase rather than taking a fixed end of the clause:
            # "my front tooth chipped yesterday and I want a cleaning" should quote back
            # "front tooth chipped", not the half about the cleaning.
            lowered = [w.strip(",.;?!").lower() for w in words]
            head = needle.split()[0]
            at_word = next((i for i, w in enumerate(lowered) if head in w), 0)
            span = len(needle.split())
            clause = " ".join(words[max(0, at_word - 2) : at_word + span])
        return f"your {clause[3:]}" if clause.lower().startswith("my ") else clause

    # -- world checks (FR-010) -------------------------------------------------
    def _world_checks(
        self, c: RequestConstraints, world: SeedBundle, now: datetime
    ) -> list[Flag]:
        out: list[Flag] = []
        window = c.date_range.value

        mismatch = self._symptom_type_mismatch(c)
        if mismatch is not None:
            out.append(mismatch)

        # Defence in depth for the HTTP boundary's blank-text check (schemas.py):
        # the orchestrator is also callable directly, and a request with no words in
        # it produces a full set of defaults that look exactly like a real answer.
        if not c.request_text.strip():
            out.append(
                Flag(
                    code="NO_REQUEST_TEXT",
                    message="There is nothing here to look up — what did the patient ask for?",
                )
            )

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
