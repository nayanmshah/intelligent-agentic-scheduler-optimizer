"""The deterministic reasoner, end to end.

Ranking is a pure function of ``(RequestConstraints, schedule, WeightProfile, NOW)``
(FR-054). Nothing in this package imports ``app.agents`` -- enforced by an import
guard -- so a language error upstream can produce the wrong *search*, but never an
infeasible *booking*.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.data.repository import ScheduleRepository
from app.domain.candidate import Candidate, CandidateSet, RejectionGroup
from app.domain.decision import Contribution, Offer, ReasonerOutcome
from app.domain.entities import AppointmentType
from app.domain.enums import AXIS_ORDER, OfferState, RejectionReason
from app.domain.policy import WeightProfile
from app.domain.request import RequestConstraints
from app.reasoner import select, tiers
from app.reasoner.availability import AvailabilityIndex
from app.reasoner.enumerate import run_layer0
from app.reasoner.ladder import RULES
from app.reasoner.scoring.compose import ScoringResult, score_all
from app.reasoner.tiers import TierOutcome

_WHY = {r.code: r.why for r in RULES}
_REASON_TO_RULE = {
    RejectionReason.BEFORE_OPEN: "within_business_hours",
    RejectionReason.PAST_CLOSE: "within_business_hours",
    RejectionReason.BLOCKED_LUNCH: "not_overlapping_global_block",
    RejectionReason.BLOCKED_HUDDLE: "not_overlapping_global_block",
    RejectionReason.BLOCKED_ADMIN: "not_overlapping_global_block",
    RejectionReason.EMERGENCY_HOLD_LOCKED: "emergency_hold_locked",
    RejectionReason.PATIENT_EXCLUSION: "patient_exclusion",
    RejectionReason.OPERATORY_BUSY: "operatory_free",
    RejectionReason.OPERATORY_TURNOVER: "operatory_free",
    RejectionReason.SLOT_HELD: "slot_not_held",
    RejectionReason.OPERATORY_NOT_EQUIPPED: "operatory_equipped",
    RejectionReason.PROVIDER_BUSY: "provider_free",
    RejectionReason.PROVIDER_PTO: "provider_free",
    RejectionReason.PROVIDER_NOT_CREDENTIALED: "provider_credentialed",
    RejectionReason.PROVIDER_OFFSITE: "provider_at_location",
    RejectionReason.DOCTOR_CHECK_UNAVAILABLE: "doctor_check_containment",
}


class DeterministicReasoner:
    """Implementation A of the ``ScheduleReasoner`` protocol. Implementation B is the
    naive first-available baseline the eval harness needs (FR-095)."""

    def __init__(self, repo: ScheduleRepository, settings: Settings, tz: ZoneInfo) -> None:
        self._repo = repo
        self._settings = settings
        self._tz = tz
        self._location = repo.seed.locations[0]
        self._index = AvailabilityIndex(repo, self._location, tz)

    @property
    def index(self) -> AvailabilityIndex:
        return self._index

    def prepare(
        self, constraints: RequestConstraints, now: datetime, request_id: str = "req"
    ) -> tuple[CandidateSet, TierOutcome, AppointmentType]:
        """Layer 0 + the urgency gate, with no scoring and no selection.

        Shared by the product ranker and the naive baseline so the head-to-head
        compares *ranking*, not one of them being allowed to book something the
        other could not (FR-095).
        """
        s = self._settings
        appointment_type = self._repo.seed.appointment_type(constraints.appointment_type.value)
        result = run_layer0(
            repo=self._repo, index=self._index, constraints=constraints,
            appointment_type=appointment_type, location=self._location, tz=self._tz,
            now=now.date(), settings=s, request_id=request_id, now_dt=now,
        )
        gate = tiers.apply_gate(result.candidates, now, constraints)
        return result.candidates, gate, appointment_type

    def run(
        self,
        constraints: RequestConstraints,
        now: datetime,
        profile: WeightProfile,
        request_id: str = "req",
    ) -> ReasonerOutcome:
        s = self._settings
        appointment_type = self._repo.seed.appointment_type(constraints.appointment_type.value)

        # Layer 0 -- enumerate and annotate. Nothing is ever removed.
        result = run_layer0(
            repo=self._repo,
            index=self._index,
            constraints=constraints,
            appointment_type=appointment_type,
            location=self._location,
            tz=self._tz,
            now=now.date(),
            settings=s,
            request_id=request_id,
            now_dt=now,
        )
        cs = result.candidates

        # Layer 1 -- the urgency gate, then escalation if the top tier is empty.
        outcome = tiers.apply_gate(cs, now, constraints)
        origin = OfferState.OFFERED
        overflow_ids: tuple[str, ...] = ()

        if outcome.exhausted:
            origin = OfferState.OFFERED_OVERFLOW
            overflow_ids = select.nearest_overflow(cs)

        # Layer 2 -- score the in-tier set once (ADR-06).
        scoring = score_all(
            cs, self._repo, self._index, constraints, appointment_type, profile, s, now.date()
        )
        picked = select.select_top3(cs, s.epsilon_band, s.diversity_window_min)

        # FR-038: an offer that does not do what was asked must say so, or an operator
        # reads out a Wednesday slot as though it answered a request for Thursday.
        # Decided slot by slot -- see ``_misses_the_request``.
        alternative = {cid: _misses_the_request(cs.get(cid), constraints) for cid in picked.offered}
        offers = tuple(
            self._offer(cid, cs, scoring, appointment_type,
                        picked.coequal_groups.get(cid), alternative[cid])
            for cid in picked.offered
        )
        # The record-level badge follows the offers rather than leading them: "nothing
        # opened when you asked" is only true if none of what we are showing did.
        if origin is OfferState.OFFERED and alternative and all(alternative.values()):
            origin = OfferState.OFFERED_OVERFLOW
        overflow = tuple(
            self._offer(cid, cs, scoring, appointment_type, None, True) for cid in overflow_ids
        )

        cs.conserve()
        return ReasonerOutcome(
            offers=offers,
            overflow=overflow,
            funnel=cs.funnel(),
            ledger=self._ledger(cs),
            counterfactual=None,
            score_matrix=scoring.matrix,
            nominal_weights=scoring.nominal,
            effective_weights=scoring.effective,
            origin_state=origin,
            limited_availability=picked.limited_availability,
            emergency_holds_unlocked=outcome.escalated,
        )

    # -- rendering -------------------------------------------------------------
    def _offer(
        self,
        cid: str,
        cs: CandidateSet,
        scoring: ScoringResult,
        appointment_type: AppointmentType,
        group: int | None,
        is_overflow: bool,
    ) -> Offer:
        cand = cs.get(cid)
        ann = cs.ann(cid)
        rationale = scoring.rationales.get(cid)
        if rationale is None:  # pragma: no cover - overflow sits outside the scored set
            raise KeyError(f"no rationale for {cid}")

        facts = rationale.facts
        contributions = tuple(
            Contribution(
                axis=axis.value,
                value=(ann.axes.value_of(axis) if ann.axes else 0.0),
                weight=scoring.effective.of(axis),
                weighted=(ann.axes.value_of(axis) if ann.axes else 0.0)
                * scoring.effective.of(axis),
            )
            for axis in AXIS_ORDER
        )
        return Offer(
            candidate_id=cid,
            start=cand.start,
            day=cand.day,
            operatory_id=cand.operatory_id,
            type_id=appointment_type.id,
            weekday=facts.weekday,
            date_display=facts.date_display,
            start_display=facts.start_display,
            provider_id=cand.provider_id,
            provider_name=facts.provider_name,
            operatory_name=facts.operatory_name,
            duration_min=cand.duration_min,
            type_name=facts.type_name,
            score=ann.score or 0.0,
            contributions=contributions,
            rationale=rationale,
            # No prose here. [SD-2] The reasoner emits a Rationale; the explainer
            # renders it. Reaching into agents/ from here would also trip FR-054's
            # import guard, which exists to keep ranking LLM-independent.
            template_reason="",
            coequal_group=group,
            is_overflow=is_overflow,
            emergency_hold_released=ann.emergency_hold_released,
        )

    def _ledger(self, cs: CandidateSet) -> tuple[RejectionGroup, ...]:
        """Grouped by single cause, ordered by count -- the most common obstacle first,
        because that is the one the operator will be asked about."""
        groups = []
        for reason, count in sorted(
            cs.rejected_by_reason().items(), key=lambda kv: (-kv[1], kv[0].value)
        ):
            stem = _WHY.get(_REASON_TO_RULE.get(reason, ""), "it did not fit")
            groups.append(RejectionGroup(reason=reason, count=count, sentence=stem))
        return tuple(groups)


def _asked_for_specific_days(constraints: RequestConstraints) -> bool:
    """True when the patient named days rather than leaving it open. A defaulted
    search horizon is not a request, so falling outside it is not a miss."""
    field = constraints.date_range
    return not field.derived


def _misses_the_request(cand: Candidate, constraints: RequestConstraints) -> bool:
    """Does *this* slot fall outside what the patient actually asked for?

    Asked per candidate, never per record. The record-level tier says which band the
    winning slots came from, which is not the same question: a request for "next
    Thursday after 3" can be answered by a Thursday 3pm slot that still sits in the
    FLEXIBLE tier, and captioning that slot "nothing opened when you asked" is a
    plain falsehood in front of a patient.

    Same lesson as the axis caveats: only the thing being compared knows what it was
    compared against.
    """
    days = constraints.date_range
    if _asked_for_specific_days(constraints) and not days.value.contains(cand.day):
        return True
    window = constraints.time_window
    return bool(not window.derived and not window.value.contains(cand.start_min))
