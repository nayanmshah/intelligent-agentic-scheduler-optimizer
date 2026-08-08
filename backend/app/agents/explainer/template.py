"""Deterministic rendering. Always computed, for every offer, regardless of LLM
availability (FR-060).

Offline is not a degraded surface -- same content, plainer prose. Both renderings are
returned by the API so the two can be compared directly.

This module may import ``app.domain.rationale`` and nothing else from the reasoner
(FR-059, enforced by an import guard). It cannot see the schedule, so it cannot
invent a reason it was not given.
"""

from __future__ import annotations

from app.agents.explainer import lint
from app.domain.rationale import Rationale


def render(rationale: Rationale, *, is_alternative: bool = False) -> str:
    """One sentence, <=25 words, second person, resolved weekday + date + time.

    When the option does not satisfy what was asked, the sentence **opens by naming
    the gap** (FR-038). If it merely mentioned it at the end, an operator half-
    listening would hand the patient a Wednesday when they asked for Thursday, and
    nobody would catch it.
    """
    f = rationale.facts
    opener = "Nothing opened when you asked, but " if is_alternative else ""
    stem = (
        f"{opener}{f.weekday} {f.date_display} at {f.start_display} "
        f"with {f.provider_name}"
    ).strip()

    parts = [stem]
    budget = lint.MAX_WORDS - len(lint.words(stem))

    for atom in rationale.components:
        clause = atom.text
        cost = len(lint.words(clause)) + 1
        if cost <= budget - 3:  # leave room for a caveat
            parts.append(clause)
            budget -= cost
        if len(parts) >= 3:
            break

    if rationale.caveat is not None:
        clause = rationale.caveat.text
        if len(lint.words(clause)) + 1 <= budget:
            parts.append(clause)

    sentence = _join(parts)
    if not lint.check(sentence, f).ok:
        # The operator never sees a lint failure; they see a plainer sentence.
        sentence = f"{stem} is the closest we have to what you asked for."
    return sentence


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return f"{parts[0]} works for you."
    body = ", ".join(parts[:-1]) + ", " + parts[-1]
    return body.rstrip(".") + "."


def render_why_not(reason_stem: str, count: int) -> str:
    """The ledger's plain-language line (FR-030). One cause, no jargon.

    e.g. "Three rooms were free on Thursday afternoon, but no dentist was free for
    the short exam inside those appointments."
    """
    noun = "time" if count == 1 else "times"
    return f"We looked at {count} other {noun} for you, but {reason_stem}."


class TemplateExplainer:
    """Implementation B of ``Explainer``. Always available, no network (FR-060)."""

    name = "template"

    async def render(self, rationales: list) -> list[str]:  # type: ignore[type-arg]
        return [render(r) for r in rationales]
