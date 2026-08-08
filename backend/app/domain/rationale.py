"""[SD-2] The Rationale is emitted BY THE SCORER, not assembled afterwards.

The explainer is a renderer over facts the scorer already produced. It imports this
module and nothing else from ``reasoner`` (asserted by an import-guard test), so an
explanation *cannot* disagree with the ranking -- the failure mode is structurally
eliminated rather than tested for.

The mechanism is small and worth stating: each axis scorer returns
``(value, atom_text, subterms)``. The number and the sentence about the number have a
single origin. There is no code path by which prose could describe a component that
did not contribute.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import Axis


@dataclass(frozen=True, slots=True)
class Atom:
    """One contributing component, with the words for it."""

    axis: Axis
    value: float
    weighted: float
    text: str  # e.g. "same hygienist as your last three visits"
    #: Names a shortfall rather than a strength. Rendered *before* the positives,
    #: because a sentence truncated to fit must lose a compliment, never a warning.
    concessive: bool = False


@dataclass(frozen=True, slots=True)
class FactSet:
    """The ONLY entities an explanation may name.

    The faithfulness gate (FR-062) checks generated prose against exactly this set.
    Anything absent here and present in the sentence is a hallucination by
    definition, which is what makes the gate ~40 lines instead of a judgement call.
    """

    provider_name: str
    weekday: str
    date_display: str
    start_display: str
    end_display: str
    operatory_name: str
    duration_min: int
    type_name: str
    patient_first_name: str

    def entities(self) -> frozenset[str]:
        return frozenset(
            {
                self.provider_name,
                self.weekday,
                self.date_display,
                self.start_display,
                self.end_display,
                self.operatory_name,
                self.type_name,
                self.patient_first_name,
            }
        )


@dataclass(frozen=True, slots=True)
class Rationale:
    facts: FactSet
    components: tuple[Atom, ...]  # top 2-3 weighted contributions, descending
    caveat: Atom | None = None  # at most one (FR-066)

    @property
    def top_axes(self) -> frozenset[Axis]:
        axes = {a.axis for a in self.components}
        if self.caveat is not None:
            axes.add(self.caveat.axis)
        return frozenset(axes)
