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
