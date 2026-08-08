"""[NFR-28] Every agent is a Protocol with two implementations.

This is an architecture obligation, not a coding-style preference: it is what makes
FR-093's LLM-vs-rules comparison possible at all. Without it, "we used an LLM here"
is a preference you defend with an opinion; with it, it is a measurement.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.entities import Patient, SeedBundle
from app.domain.request import RequestConstraints, VerifierVerdict


@runtime_checkable
class IntentExtractor(Protocol):
    name: str

    async def extract(
        self, text: str, patient: Patient | None, now: datetime
    ) -> RequestConstraints: ...


@runtime_checkable
class ConstraintVerifier(Protocol):
    """Checks the extraction against **the world**, never against the schedule.

    Mixing the two makes "why did it ask?" unanswerable, because the answer would
    depend on scheduling state that changes minute to minute.
    """

    name: str

    async def verify(
        self, constraints: RequestConstraints, world: SeedBundle, now: datetime
    ) -> VerifierVerdict: ...


@runtime_checkable
class Explainer(Protocol):
    name: str

    async def render(self, rationales: list) -> list[str]: ...  # type: ignore[type-arg]
