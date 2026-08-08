"""Implementation B of ``ScheduleReasoner``: naive first-available.

This is the control (FR-095). "Is this just a fancy first-available?" is answered by
running both rankers over the same feasible set and reporting the delta -- and, where
the delta is small for a request class, **naming that class**. Knowing where the
product does not add value is part of knowing whether it works.

It shares Layer 0 with the product ranker deliberately. The comparison must be about
*ranking*: letting the baseline book something infeasible would flatter the product
for the wrong reason.
"""

from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.data.repository import ScheduleRepository
from app.domain.decision import Offer, ReasonerOutcome
from app.domain.enums import OfferState
from app.domain.policy import WeightProfile
from app.domain.request import RequestConstraints
from app.reasoner.pipeline import DeterministicReasoner
from app.reasoner.scoring.compose import fact_set


class NaiveFirstAvailableReasoner:
    """Takes the earliest feasible slots, the way a rushed human scanning operatory
    columns would: no scoring, no diversity constraint, no tiebreak beyond time."""

    name = "naive-first-available"

    def __init__(self, repo: ScheduleRepository, settings: Settings, tz) -> None:  # type: ignore[no-untyped-def]
        self._repo = repo
        self._settings = settings
        self._inner = DeterministicReasoner(repo, settings, tz)

    def run(
        self,
        constraints: RequestConstraints,
        now: datetime,
        profile: WeightProfile,
        request_id: str = "req",
    ) -> ReasonerOutcome:
        cs, _gate, appointment_type = self._inner.prepare(constraints, now, request_id)
        patient = (
            self._repo.seed.patient(constraints.patient_ref)
            if constraints.patient_ref
            else None
        )

        pool = list(cs.in_tier()) or list(cs.feasible())
        earliest = sorted(pool, key=lambda p: (p[0].start, p[0].operatory_id))[:3]

        offers = tuple(
            Offer(
                candidate_id=cand.candidate_id,
                start=cand.start,
                day=cand.day,
                operatory_id=cand.operatory_id,
                type_id=appointment_type.id,
                weekday=(f := fact_set(cand, self._repo, appointment_type, patient)).weekday,
                date_display=f.date_display,
                start_display=f.start_display,
                provider_id=cand.provider_id,
                provider_name=f.provider_name,
                operatory_name=f.operatory_name,
                duration_min=cand.duration_min,
                type_name=f.type_name,
                score=0.0,           # the baseline does not score; that is the point
                contributions=(),
                rationale=None,      # type: ignore[arg-type]
                template_reason="",
            )
            for cand, _ in earliest
        )
        return ReasonerOutcome(
            offers=offers,
            overflow=(),
            funnel=cs.funnel(),
            ledger=(),
            counterfactual=None,
            score_matrix=None,
            nominal_weights=profile.weights,
            effective_weights=profile.weights,
            origin_state=OfferState.OFFERED,
        )

    @property
    def index(self):  # type: ignore[no-untyped-def]
        return self._inner.index
