"""Implementation A of ``ConstraintVerifier``.

The verifier reads the *extraction* against the world -- never against the schedule.
Mixing the two makes "why did it ask?" unanswerable, because the answer would depend on
scheduling state that changes minute to minute.

**What the model adds over the rules implementation.** The rules catch what can be
enumerated: a date in the past, a provider who does not exist, a credential mismatch.
They cannot catch a *semantic* mismatch, because there is no list to check it against --
"my crown fell off, can I get a cleaning?" is a request whose stated symptom and
requested treatment disagree, and no lookup finds that. That judgement is the reason
this implementation exists.

**Its authority is deliberately bounded.** It may raise a flag and it may propose a
clarifying question. It may not alter the constraints, and it never sees a candidate
slot -- so a wrong call here costs a spurious question, never a wrong booking. Anything
it returns that does not name a real provider or appointment type is dropped rather
than shown, because a flag about a provider who does not exist is worse than silence.

Deterministic checks still run underneath: the rules verdict is computed first and its
flags are merged in. The model can add to the picture, never subtract from it.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.agents.llm.client import LlmClient, LlmUnavailable
from app.agents.verifier.payload import VerificationPayload, verdict_schema
from app.agents.verifier.rules import RuleConstraintVerifier
from app.config import Settings
from app.domain.entities import SeedBundle
from app.domain.request import Flag, Question, RequestConstraints, VerifierVerdict

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"


class LlmConstraintVerifier:
    name = "llm"

    def __init__(
        self, client: LlmClient, settings: Settings, rules: RuleConstraintVerifier
    ) -> None:
        self._client = client
        self._settings = settings
        self._rules = rules
        self._prompt = (PROMPT_DIR / f"verify_{settings.prompt_version}.md").read_text(
            encoding="utf-8"
        )

    async def verify(
        self, constraints: RequestConstraints, world: SeedBundle, now: datetime
    ) -> VerifierVerdict:
        # The deterministic checks are the floor, not the fallback. They run whatever
        # the model says, so a model that returns nothing cannot suppress a real
        # problem the rules already found.
        floor = await self._rules.verify(constraints, world, now)

        providers = "\n".join(f"- {p.id}: {p.name} ({p.role.value})" for p in world.providers)
        types = "\n".join(
            f"- {t.id}: {t.name} ({t.duration_min} min)" for t in world.appointment_types
        )
        system = self._prompt.format(
            now=now.isoformat(), weekday=now.strftime("%A"), providers=providers, types=types
        )
        user = _describe(constraints)

        try:
            raw = await self._client.structured(
                model=self._settings.model_verify,
                system=system,
                user=user,
                schema=verdict_schema(),
                timeout=self._settings.timeout_verify,
            )
            payload = VerificationPayload(**raw)
        except Exception as exc:  # the fallback ladder owns the retry policy
            raise LlmUnavailable(f"verify failed: {exc}") from exc

        return _merge(floor, payload, world)


def _describe(c: RequestConstraints) -> str:
    """What the extractor concluded, in the words the model needs to judge it.

    The raw request goes in too: the model is checking the *reading* against what was
    actually said, and it cannot do that from the reading alone.
    """
    w = c.time_window.value
    window = "any time" if w.start_min is None and w.end_min is None else (
        f"{_hhmm(w.start_min)}-{_hhmm(w.end_min)}"
    )
    return (
        f"PATIENT SAID: {c.request_text!r}\n\n"
        f"EXTRACTED:\n"
        f"- dates: {c.date_range.value.start} to {c.date_range.value.end}"
        f" (confidence {c.date_range.confidence:.2f})\n"
        f"- time: {window} (confidence {c.time_window.confidence:.2f})\n"
        f"- urgency: {c.urgency.value.value} (confidence {c.urgency.confidence:.2f})\n"
        f"- provider: {c.provider_preference.value or 'none stated'}"
        f" (confidence {c.provider_preference.confidence:.2f})\n"
        f"- appointment type: {c.appointment_type.value}"
        f" (confidence {c.appointment_type.confidence:.2f})\n"
        f"- avoid weekdays: {sorted(c.exclusions.value.weekdays) or 'none'}\n"
    )


def _hhmm(minute: int | None) -> str:
    if minute is None:
        return "open"
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _merge(
    floor: VerifierVerdict, payload: VerificationPayload, world: SeedBundle
) -> VerifierVerdict:
    """Rules flags first, then whatever the model added that survives validation."""
    seen = {f.code for f in floor.flags}
    flags = list(floor.flags)
    for item in payload.flags:
        if item.code in seen or not item.message.strip():
            continue
        seen.add(item.code)
        flags.append(Flag(code=item.code[:40], message=item.message.strip()))

    # A question the rules already decided to ask wins: it was derived from a
    # divergence the reasoner actually measured, not from a judgement about wording.
    if floor.outcome == "ask":
        return VerifierVerdict(outcome="ask", flags=tuple(flags),
                               hypotheses=floor.hypotheses, question=floor.question)

    question = None
    if payload.question is not None and len(payload.question.chips) >= 2:
        known = {t.id for t in world.appointment_types} | {p.id for p in world.providers}
        chips = tuple(
            c for c in payload.question.chips if not c.startswith("prov-") or c in known
        )
        if len(chips) >= 2:
            question = Question(
                field=payload.question.field[:40],
                text=payload.question.text.strip(),
                chips=chips[:3],
            )

    outcome = "ask" if question is not None else ("proceed_with_flags" if flags else "proceed")
    return VerifierVerdict(
        outcome=outcome, flags=tuple(flags), hypotheses=floor.hypotheses, question=question
    )
