"""The DecisionRecord does three jobs with one type: replay substrate, eval
substrate, and override capture.

It is also where the score matrix is cached, which is what makes a tuner change a
dot product rather than a second pipeline run (ADR-06, FR-079).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Annotated

from app.domain.candidate import FunnelCounts, RejectionGroup
from app.domain.enums import OfferState, Scope
from app.domain.phi import PHI
from app.domain.policy import Weights
from app.domain.rationale import Rationale
from app.domain.request import RequestConstraints


@dataclass(frozen=True, slots=True)
class SlotExplanation:
    """Why one particular time was not offered (FR-109).

    The rejection ledger answers "where did 13,000 candidates go?" in aggregate, which
    is the wrong grain for the question an operator is actually asked: *"but isn't 3
    o'clock free?"* That question is about one time, so this counts only the candidates
    at that time -- and separates "nothing there was bookable" from "it was bookable and
    simply outranked", because those are different answers to give a patient.
    """

    day: date
    start_min: int
    considered: int
    bookable: int
    causes: tuple[RejectionGroup, ...]


@dataclass(frozen=True, slots=True)
class Contribution:
    axis: str
    value: float
    weight: float
    weighted: float


@dataclass(frozen=True, slots=True)
class Offer:
    """One card. FR-053 fixes the seven elements it must carry."""

    candidate_id: str
    # Identity, so a booking intent can be rebuilt without parsing display strings.
    start: datetime
    day: date
    operatory_id: str
    type_id: str
    weekday: str
    date_display: str
    start_display: str
    provider_id: str
    provider_name: str
    operatory_name: str
    duration_min: int
    type_name: str
    score: float
    contributions: tuple[Contribution, ...]
    rationale: Rationale
    template_reason: str
    llm_reason: str | None = None
    gate_fired: bool = False
    gate_failed_check: str | None = None
    coequal_group: int | None = None  # epsilon-band peers share a group (FR-049)
    is_overflow: bool = False
    emergency_hold_released: bool = False

    @property
    def reason(self) -> str:
        """What the operator actually reads. The template is not a degraded
        surface -- same content, plainer prose (FR-060)."""
        return self.llm_reason or self.template_reason


@dataclass(frozen=True, slots=True)
class Counterfactual:
    relaxation: str
    gain: float
    sentence: str


@dataclass(frozen=True, slots=True)
class ScoreMatrix:
    """Axis values for the in-tier set, computed once (ADR-06).

    Rows align with ``candidate_ids``; columns are ``AXIS_ORDER``. Every later
    question -- re-rank, 200-sample stability, sensitivity sweep, weight fitting --
    is this matrix times a different vector.
    """

    candidate_ids: tuple[str, ...]
    rows: tuple[tuple[float, float, float, float], ...]
    #: ``(provider_id, day_ordinal, start_min, operatory_id)`` per row, aligned with
    #: ``candidate_ids``. Present so the *selection* -- not a naive score sort -- can be
    #: replayed under a different weight vector (FR-081). Without it the stability
    #: measure compared the diversity-aware offer set against the top three by score,
    #: which disagree by construction whenever the diversity rule fires or slots tie,
    #: and the indicator read 0% for reasons that had nothing to do with stability.
    keys: tuple[tuple[str, int, int, str], ...] = ()
    #: ``(provider_name, start_display)`` per row, aligned with ``candidate_ids``.
    #:
    #: Re-ranking under new weights can promote a candidate that was never in the
    #: original top three -- that is the entire point of the policy screen. Without a
    #: label here the endpoint could only name the three it started with, and moving a
    #: slider rendered rows as "83% --". A matrix that can rank a row must be able to
    #: say what the row *is*.
    labels: tuple[tuple[str, str], ...] = ()

    def label_for(self, candidate_id: str) -> tuple[str, str] | None:
        try:
            return self.labels[self.candidate_ids.index(candidate_id)]
        except (ValueError, IndexError):
            return None

    def scores_for(self, w: Weights) -> tuple[float, ...]:
        a, b, c, d = w.as_row()
        return tuple(r[0] * a + r[1] * b + r[2] * c + r[3] * d for r in self.rows)


@dataclass(slots=True)
class DecisionRecord:
    id: str
    trace_id: str
    now: datetime
    raw_text: Annotated[str, PHI]
    constraints: Annotated[RequestConstraints | None, PHI] = None

    #: How the words reached the box: ``"text"`` typed, ``"voice"`` dictated and then
    #: confirmed by the operator (FR-110). Recorded because it is the only thing an
    #: eval or an audit needs to answer "is speech worse?" -- and because a transcript
    #: is a *reading* of what the patient said, where typed text is what they said.
    source: str = "text"

    scope: Scope = Scope.LOCATION  # [NFR-30]
    scope_ref: str = ""

    origin_state: OfferState = OfferState.OFFERED  # [AR-09]
    funnel: FunnelCounts | None = None
    offers: tuple[Offer, ...] = ()
    overflow: tuple[Offer, ...] = ()
    ledger: tuple[RejectionGroup, ...] = ()
    counterfactual: Counterfactual | None = None
    question_asked: str | None = None
    flags: tuple[str, ...] = ()
    limited_availability: bool = False

    weight_profile_id: str = ""
    nominal_weights: Weights | None = None
    effective_weights: Weights | None = None
    score_matrix: ScoreMatrix | None = None

    operator_corrections: list[str] = field(default_factory=list)
    accepted_slot_id: str | None = None
    override_reason: str | None = None
    hypotheses_considered: tuple[str, ...] = ()

    fallback_fired: tuple[str, ...] = ()
    gate_fired_count: int = 0
    llm_calls: int = 0

    @property
    def is_override(self) -> bool:
        """Every override is the most valuable data this product generates -- a
        labelled counterexample, not a failure (FR-075)."""
        if self.accepted_slot_id is None:
            return False
        return self.accepted_slot_id not in {o.candidate_id for o in self.offers}


@dataclass(frozen=True, slots=True)
class ReasonerOutcome:
    """What the deterministic core returns. Contains no prose beyond the template
    rendering, and no knowledge that an LLM exists."""

    offers: tuple[Offer, ...]
    overflow: tuple[Offer, ...]
    funnel: FunnelCounts
    ledger: tuple[RejectionGroup, ...]
    counterfactual: Counterfactual | None
    score_matrix: ScoreMatrix | None
    nominal_weights: Weights
    effective_weights: Weights
    origin_state: OfferState
    limited_availability: bool = False
    emergency_holds_unlocked: bool = False

    def top3_key(self) -> tuple[str, ...]:
        """Identity of the offered set, for the decision-relevance test (FR-011).

        Two hypotheses are 'the same answer' when this matches -- which is the only
        definition that matters, because it is what the operator would see.
        """
        return tuple(sorted(o.candidate_id for o in self.offers))
