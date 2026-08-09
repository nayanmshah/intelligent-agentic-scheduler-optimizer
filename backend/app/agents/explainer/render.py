"""Turn a reasoner outcome into readable prose.

Lives in ``agents/explainer`` rather than in the reasoner because that is the
boundary FR-054 and FR-059 draw: the reasoner decides and emits facts, the explainer
renders them and can reach nothing else. The orchestrator calls this after the
deterministic pipeline returns.

The template rendering is **always** produced (FR-060), so offline is not a degraded
surface -- same content, plainer prose.
"""

from __future__ import annotations

from dataclasses import replace

from app.agents.explainer import template
from app.domain.candidate import RejectionGroup
from app.domain.decision import Offer, ReasonerOutcome


def render_offer(offer: Offer) -> Offer:
    return replace(
        offer,
        template_reason=template.render(offer.rationale, is_alternative=offer.is_overflow),
    )


def render_ledger(groups: tuple[RejectionGroup, ...]) -> tuple[RejectionGroup, ...]:
    return tuple(
        replace(g, sentence=template.render_why_not(g.sentence, g.count)) for g in groups
    )


def render_outcome(outcome: ReasonerOutcome) -> ReasonerOutcome:
    """Fill in every operator-facing sentence. Deterministic; no network."""
    return replace(
        outcome,
        offers=tuple(render_offer(o) for o in outcome.offers),
        overflow=tuple(render_offer(o) for o in outcome.overflow),
        ledger=render_ledger(outcome.ledger),
    )


async def explain_outcome(tracer, outcome: ReasonerOutcome, explainer):  # type: ignore[no-untyped-def]
    """The explain stage: template always, model on top of it (FR-060).

    The template is computed unconditionally so an operator-facing sentence exists
    whatever happens next -- offline is a plainer surface, never an empty one. The
    model then rewrites each line, and the faithfulness gate (FR-062) decides per
    sentence whether the rewrite survives or the template stands.

    Lives here rather than in the orchestrator so that NFR-27's 150-line cap stays a
    real constraint rather than one relaxed the moment it binds.
    """
    with tracer.span("explain", offers=len(outcome.offers)) as span:
        span.attrs["model"] = getattr(explainer, "model_id", None)
        outcome = render_outcome(outcome)
        span.attrs["implementation"] = explainer.name
        if explainer.name == "template":
            span.attrs["gate_fired"] = 0
            return outcome, 0

        outcome, fired = await apply_llm_prose(outcome, explainer)
        # Loud in the trace, silent to the operator (NFR-16). A firing rate of exactly
        # zero forever means the gate is not running, not that the model is perfect.
        span.attrs["gate_fired"] = fired
        return outcome, fired


async def apply_llm_prose(outcome: ReasonerOutcome, explainer) -> tuple[ReasonerOutcome, int]:  # type: ignore[no-untyped-def]
    """Overlay model-written reason lines on an already-rendered outcome.

    ``template_reason`` is left untouched, so the API returns both renderings and the
    two can be compared side by side (FR-060). ``llm_reason`` is set only where the
    faithfulness gate passed; where it did not, the field stays ``None`` and
    ``Offer.reason`` falls back to the template on its own.

    Returns the number of gate rejections, which is a real signal: a rate of exactly
    zero forever means the gate is not running, not that the model is perfect.
    """
    cards = [*outcome.offers, *outcome.overflow]
    if not cards:
        return outcome, 0

    results = await explainer.render_with_gate(
        [c.rationale for c in cards], [c.is_overflow for c in cards]
    )
    fired = sum(1 for _, verdict in results if not verdict.ok)

    rewritten = [
        replace(card, llm_reason=sentence if verdict.ok else None)
        for card, (sentence, verdict) in zip(cards, results, strict=True)
    ]
    n = len(outcome.offers)
    return replace(outcome, offers=tuple(rewritten[:n]), overflow=tuple(rewritten[n:])), fired
