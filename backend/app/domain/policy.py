"""Policy as data, never as constants.

FR-046 is enforced by a grep test: no numeric weight literal may appear inside
``reasoner/scoring/``. That is not style policing -- policy is the thing that does
not scale for free. Hundreds of offices need centrally managed profiles with local
override, which is impossible if the weights live in a function body.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import AXIS_ORDER, Axis, Scope

WEIGHT_SUM_TOLERANCE = 1e-9


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Weights(Frozen):
    time_fit: float = Field(ge=0.0, le=1.0)
    continuity: float = Field(ge=0.0, le=1.0)
    efficiency: float = Field(ge=0.0, le=1.0)
    prime_time: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sums_to_one(self) -> Weights:
        total = self.time_fit + self.continuity + self.efficiency + self.prime_time
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"weights must sum to 1.0, got {total!r}")
        return self

    def as_row(self) -> tuple[float, float, float, float]:
        return (self.time_fit, self.continuity, self.efficiency, self.prime_time)

    def of(self, axis: Axis) -> float:
        return self.as_row()[AXIS_ORDER.index(axis)]

    @classmethod
    def normalised(cls, raw: tuple[float, float, float, float]) -> Weights:
        total = sum(raw)
        if total <= 0:
            raise ValueError("weight vector cannot be all-zero")  # FR-078
        t, c, e, p = (x / total for x in raw)
        return cls(time_fit=t, continuity=c, efficiency=e, prime_time=p)


class EfficiencySubWeights(Frozen):
    """[A-12]. Fixed in v1.0 -- the tuner exposes four axes, not eight."""

    fragmentation: float = 0.40
    idle: float = 0.25
    check_load: float = 0.20
    operatory_balance: float = 0.15


class WeightProfile(Frozen):
    id: str
    name: str
    scope: Scope = Scope.LOCATION  # [NFR-30]
    scope_ref: str = ""
    weights: Weights
    efficiency_subweights: EfficiencySubWeights = EfficiencySubWeights()
    is_fitted: bool = False
    fit_objective_value: float | None = None

    def effective_for(self, continuity_multiplier: float) -> Weights:
        """[A-11] / ADR-07. Scale the continuity weight by the appointment type's
        multiplier, then renormalise so the vector still sums to 1.0.

        A crown *seat* with the wrong dentist is nearly a hard constraint; continuity
        on a routine prophy is a genuine nice-to-have. One global continuity weight
        cannot express both, and promoting the former to a Layer-0 hard constraint
        would return nothing at all in exactly the case a practice handles easily --
        the prep dentist is on PTO, so you book someone else and say so.

        Consequence the UI must honour: when the multiplier is not 1.0 the effective
        vector differs from the one on the policy panel, so the API returns both and
        the contribution bar renders the effective one with the multiplier named.
        Otherwise the card and the panel appear to contradict each other.
        """
        raw = self.weights.as_row()
        scaled = (raw[0], raw[1] * continuity_multiplier, raw[2], raw[3])
        return Weights.normalised(scaled)


GENERAL_PRACTICE_DEFAULT = WeightProfile(
    id="general-practice",
    name="General Practice",
    weights=Weights(time_fit=0.35, continuity=0.25, efficiency=0.25, prime_time=0.15),
    is_fitted=False,  # flipped to True by `make fit` (FR-098)
)

PRESETS: tuple[WeightProfile, ...] = (
    GENERAL_PRACTICE_DEFAULT,
    WeightProfile(
        id="patient-first",
        name="Patient-first",
        weights=Weights(time_fit=0.55, continuity=0.25, efficiency=0.12, prime_time=0.08),
    ),
    WeightProfile(
        id="production-first",
        name="Production-first",
        weights=Weights(time_fit=0.20, continuity=0.15, efficiency=0.30, prime_time=0.35),
    ),
    WeightProfile(
        id="continuity-first",
        name="Continuity-first",
        weights=Weights(time_fit=0.25, continuity=0.50, efficiency=0.15, prime_time=0.10),
    ),
)
