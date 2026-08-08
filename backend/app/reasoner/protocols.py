"""The reasoner seam.

``run_fanout`` runs *a* reasoner over several readings of the same request. It does
not care which one, and it must not import the concrete pipeline -- the naive
baseline is run through the same call so that the head-to-head in FR-095 compares
ranking rather than one ranker being handed a different candidate set.

This is the reasoner-side twin of ``app.agents.protocols``: the same reason (two
implementations, one contract), stated in the same shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.decision import ReasonerOutcome
from app.domain.policy import WeightProfile
from app.domain.request import RequestConstraints


@runtime_checkable
class Reasoner(Protocol):
    """Constraints in, ranked-and-explained outcome out. Pure with respect to
    ``(constraints, schedule, profile, now)`` -- see FR-097."""

    def run(
        self,
        constraints: RequestConstraints,
        now: datetime,
        profile: WeightProfile,
        request_id: str = ...,
    ) -> ReasonerOutcome: ...
