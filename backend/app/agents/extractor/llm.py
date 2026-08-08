"""Implementation A of ``IntentExtractor``.

The prompt is version-pinned and committed, and its version is part of the fixture
cache key (FR-006, FR-061). The wire shape lives in ``payload.py`` -- deliberately
flatter than the domain model, because structured outputs accept only a subset of
JSON Schema and the domain model's strictness renders keywords the API rejects.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.agents.extractor.payload import ExtractionPayload, wire_schema
from app.agents.llm.client import LlmClient, LlmUnavailable
from app.config import Settings
from app.domain.entities import Patient, SeedBundle
from app.domain.request import RequestConstraints

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"


class LlmIntentExtractor:
    name = "llm"

    def __init__(self, client: LlmClient, world: SeedBundle, settings: Settings) -> None:
        self._client = client
        self._world = world
        self._settings = settings
        self._prompt = (PROMPT_DIR / f"extract_{settings.prompt_version}.md").read_text(
            encoding="utf-8"
        )

    async def extract(
        self, text: str, patient: Patient | None, now: datetime
    ) -> RequestConstraints:
        providers = "\n".join(f"- {p.id}: {p.name} ({p.role.value})" for p in self._world.providers)
        types = "\n".join(
            f"- {t.id}: {t.name} ({t.duration_min} min)" for t in self._world.appointment_types
        )
        system = self._prompt.format(
            now=now.isoformat(), weekday=now.strftime("%A"), providers=providers, types=types
        )
        raw = await self._client.structured(
            model=self._settings.model_extract,
            system=system,
            user=text,
            schema=wire_schema(),
            timeout=self._settings.timeout_extract,
        )
        try:
            payload = ExtractionPayload(**raw)
            return payload.to_constraints(text, patient.id if patient else None)
        except Exception as exc:  # schema violation -> the fallback ladder handles it
            raise LlmUnavailable(f"schema violation: {exc}") from exc
