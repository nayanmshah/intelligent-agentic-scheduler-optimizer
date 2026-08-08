"""[ADR-06] Axis values once; every weight question afterwards is a dot product.

This is the single most consequential performance decision in the system. Because
axis values do not depend on the weights, re-ranking on a tuner change (FR-079),
200-sample rank stability (FR-081), the sensitivity sweep (FR-099) and weight fitting
(FR-098) are all the *same* matrix against a different vector.

[SD-2] The ``Rationale`` is emitted here, by the scorer -- not assembled later by the
explainer. The explainer is a renderer over facts that already exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.config import Settings
from app.data.repository import ScheduleRepository
from app.domain.candidate import AxisValues, Candidate, CandidateSet
from app.domain.decision import ScoreMatrix
from app.domain.entities import AppointmentType, Patient
from app.domain.enums import AXIS_ORDER
from app.domain.policy import WeightProfile, Weights
from app.domain.rationale import Atom, FactSet, Rationale
from app.domain.request import RequestConstraints
from app.reasoner.availability import AvailabilityIndex
from app.reasoner.scoring import axes

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")

#: Below this an axis is not worth mentioning; above it a *low* value is worth a caveat.
CAVEAT_FLOOR = 0.45
COMPONENT_FLOOR = 0.05
MAX_COMPONENTS = 3


@dataclass(frozen=True, slots=True)
class ScoringResult:
    matrix: ScoreMatrix
    nominal: Weights
    effective: Weights
    rationales: dict[str, Rationale]


def _ordinal(day: int) -> str:
    if 11 <= day <= 13:
        return f"{day}th"
    return f"{day}{('th', 'st', 'nd', 'rd')[day % 10] if day % 10 < 4 else 'th'}"


def clock(minute: int) -> str:
    """12-hour, no leading zero. Operators read this aloud."""
    hour, mins = divmod(minute, 60)
    suffix = "am" if hour < 12 else "pm"
    h12 = hour % 12 or 12
    return f"{h12}:{mins:02d}{suffix}"


def fact_set(
    cand: Candidate,
    repo: ScheduleRepository,
    appointment_type: AppointmentType,
    patient: Patient | None,
) -> FactSet:
    provider = repo.seed.provider(cand.provider_id)
    operatory = repo.seed.operatory(cand.operatory_id)
    d = cand.day
    return FactSet(
        provider_name=provider.name,
        weekday=WEEKDAYS[d.weekday()],
        date_display=f"{MONTHS[d.month - 1]} {_ordinal(d.day)}",
        start_display=clock(cand.start_min),
        end_display=clock(cand.start_min + cand.duration_min),
        operatory_name=operatory.name,
        duration_min=cand.duration_min,
        type_name=appointment_type.name,
        patient_first_name=(patient.name.split()[0] if patient else "there"),
    )


def score_all(
    cs: CandidateSet,
    repo: ScheduleRepository,
    index: AvailabilityIndex,
    constraints: RequestConstraints,
    appointment_type: AppointmentType,
    profile: WeightProfile,
    settings: Settings,
    today: date,
) -> ScoringResult:
    patient = repo.seed.patient(constraints.patient_ref) if constraints.patient_ref else None
    providers = {p.id: p for p in repo.seed.providers}
    operatory_ids = tuple(o.id for o in repo.seed.operatories)

    nominal = profile.weights
    effective = profile.effective_for(appointment_type.continuity_multiplier)

    ids: list[str] = []
    rows: list[tuple[float, float, float, float]] = []
    rationales: dict[str, Rationale] = {}

    for cand, ann in cs.in_tier():
        blocks = repo.blocks_on(cand.day)
        provider = providers[cand.provider_id]

        tf = axes.score_time_fit(cand, constraints, today)
        co = axes.score_continuity(
            cand, provider, patient, appointment_type, constraints, providers
        )
        eff_value, eff_atom, subterms = axes.score_efficiency(
            cand, index, settings.turnover_min, settings.min_bookable_min, operatory_ids
        )
        pt = axes.score_prime_time(cand, appointment_type, patient, blocks)

        values = AxisValues(
            time_fit=tf.value,
            continuity=co.value,
            efficiency=eff_value,
            prime_time=pt.value,
            subterms=subterms,
            atoms=(tf.atom, co.atom, eff_atom, pt.atom),
            # Only one efficiency phrasing is a shortfall ("an awkward gap"); a
            # merely-imperfect packing score is not something to lead a sentence with.
            concessions=(
                tf.concessive, co.concessive,
                subterms.fragmentation < axes.MID_VALUE, pt.concessive,
            ),
        )
        caveats = (tf.caveat, co.caveat, "though it leaves a short gap afterwards", pt.caveat)
        ann.axes = values
        ids.append(cand.candidate_id)
        rows.append(values.as_row())

        rationales[cand.candidate_id] = _rationale(
            values, effective, fact_set(cand, repo, appointment_type, patient), caveats
        )

    matrix = ScoreMatrix(candidate_ids=tuple(ids), rows=tuple(rows))
    for cid, score in zip(ids, matrix.scores_for(effective), strict=True):
        cs.ann(cid).score = round(score, 6)  # fixed precision: byte-identical output

    return ScoringResult(matrix=matrix, nominal=nominal, effective=effective, rationales=rationales)


def _rationale(
    values: AxisValues, weights: Weights, facts: FactSet, caveats: tuple[str, ...]
) -> Rationale:
    """Top contributors, plus at most one caveat (FR-059, FR-066)."""
    concessive = values.concessions or (False,) * len(AXIS_ORDER)
    atoms = [
        Atom(axis=axis, value=values.value_of(axis),
             weighted=values.value_of(axis) * weights.of(axis), text=values.atoms[i],
             concessive=concessive[i])
        for i, axis in enumerate(AXIS_ORDER)
    ]
    # Concessions first, then by contribution. Ranking purely by weighted value put
    # shortfalls last by construction -- an axis that scored badly contributes little --
    # so the sentence spent its word budget on compliments and dropped the warning.
    # "Thursday 20th with Sarah, the provider you asked for" read as a match when the
    # patient had asked for Thursday the *13th*.
    # Among warnings, lead with the *worst* one; among reasons, lead with the
    # strongest. Sorting warnings by contribution would put the mildest first, which
    # is the same mistake one level down.
    ranked = sorted(
        atoms,
        key=lambda a: (
            not a.concessive,
            a.value if a.concessive else -a.weighted,
            a.axis.value,
        ),
    )
    keep = [a for a in ranked if a.concessive or a.weighted >= COMPONENT_FLOOR]
    components = tuple(keep[:MAX_COMPONENTS]) or (ranked[0],)

    # A caveat is a *real* downside, not merely the weakest axis: the axis has to be
    # genuinely low, and it must not already be cited as a reason the slot won.
    chosen = {a.axis for a in components}
    caveat = next(
        (a for a in sorted(atoms, key=lambda a: a.value)
         if a.value < CAVEAT_FLOOR and a.axis not in chosen),
        None,
    )
    if caveat is not None:
        # The axis supplies its own phrasing: only it knows what it was comparing
        # against. A generic writer here named the *offered* provider and produced
        # "though it is not Maya" on an offer with Maya.
        text = caveats[AXIS_ORDER.index(caveat.axis)]
        if not text:
            return Rationale(facts=facts, components=components, caveat=None)
        caveat = Atom(axis=caveat.axis, value=caveat.value, weighted=caveat.weighted, text=text)
    return Rationale(facts=facts, components=components, caveat=caveat)
