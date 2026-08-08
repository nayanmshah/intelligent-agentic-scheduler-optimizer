"""[Q10 / §9] Fan-out, and the shared work that makes it affordable.

The PRD asked whether running the deterministic pipeline twice per request fits
inside NFR-01. It does, and the optimisation is nearly free because ``ladder.py``
already declares which rules read which constraint fields.

* **Relative-date fan-out** -- ``date_range`` appears in no Layer-0 rule, so the two
  readings share the *entire* annotated candidate set. Only tier and score re-run.
* **Type fan-out** -- duration, equipment, credentials and the doctor check all
  change, so Layer 0 genuinely re-runs. It still reuses the availability index, which
  is the expensive artefact.

The decision-relevance test lives here rather than in the verifier because it needs
the *schedule*, and the verifier is schedule-blind by construction (FR-009).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.decision import ReasonerOutcome
from app.domain.policy import WeightProfile
from app.domain.request import Hypothesis, Question, RequestConstraints
from app.reasoner.ladder import LAYER0_DEPENDENCIES
from app.reasoner.protocols import Reasoner


@dataclass(frozen=True, slots=True)
class FanOutResult:
    outcomes: tuple[tuple[Hypothesis, ReasonerOutcome], ...]
    shared_layer0: bool
    diverged: bool

    @property
    def resolved(self) -> ReasonerOutcome:
        """The reading taken when no question is warranted: highest confidence."""
        return max(self.outcomes, key=lambda pair: pair[0].confidence)[1]

    def question(self, field_label: str) -> Question:
        chips = tuple(h.label for h, _ in self.outcomes)[:3]
        return Question(
            field=self.outcomes[0][0].field,
            text=_question_text(self.outcomes[0][0].field, chips),
            chips=chips,
        )

    def for_label(self, label: str) -> ReasonerOutcome | None:
        return next((o for h, o in self.outcomes if h.label == label), None)


def _question_text(field: str, chips: tuple[str, ...]) -> str:
    """Phrased for the operator to read aloud, and answerable by the patient
    (FR-013). Never free text -- the chips are the whole answer space."""
    joined = " or ".join(chips)
    if field == "date_range":
        return f"Did you mean {joined}?"
    return f"Is this for {joined.lower()}?"


def can_share_layer0(hypotheses: tuple[Hypothesis, ...]) -> bool:
    """True when the differing field appears in no Layer-0 rule's ``depends_on``."""
    return all(h.field not in LAYER0_DEPENDENCIES for h in hypotheses)


def run_fanout(
    reasoner: Reasoner,
    base: RequestConstraints,
    hypotheses: tuple[Hypothesis, ...],
    now: datetime,
    profile: WeightProfile,
    request_id: str,
) -> FanOutResult:
    """Run each reading and compare the *offered sets* -- which is the only
    definition of "the same answer" that matters, because it is what the operator
    would see."""
    if not hypotheses:
        outcome = reasoner.run(base, now, profile, request_id)
        placeholder = Hypothesis(field="", label="", constraints=base, confidence=1.0)
        return FanOutResult(((placeholder, outcome),), shared_layer0=True, diverged=False)

    shared = can_share_layer0(hypotheses)
    outcomes = tuple(
        (h, reasoner.run(h.constraints, now, profile, request_id)) for h in hypotheses
    )
    keys = {o.top3_key() for _, o in outcomes}
    return FanOutResult(outcomes=outcomes, shared_layer0=shared, diverged=len(keys) > 1)
