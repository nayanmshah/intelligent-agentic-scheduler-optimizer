"""Implementation A of ``Explainer``: LLM phrasing over scorer-emitted facts.

It sees only the ``Rationale`` -- an import guard asserts it cannot reach the
schedule or the scorer's internals (FR-059). So it *structurally cannot* invent a
reason it was not given; the gate then verifies that it did not paraphrase one into
existence either.

**Conceded weakness [R-13]:** templates get roughly 90% of the value here. The model
buys naturalness and avoids combinatorial template explosion as rationale
combinations grow. The template is always computed, so this stage can be removed at
any time without loss of function -- and FR-060 returns both renderings so the two
can be compared directly.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.explainer import gate, template
from app.agents.llm.client import LlmClient, LlmUnavailable
from app.config import Settings
from app.domain.rationale import Rationale

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"


def _describe(r: Rationale) -> dict:  # type: ignore[type-arg]
    f = r.facts
    return {
        "weekday": f.weekday,
        "date": f.date_display,
        "time": f.start_display,
        "provider": f.provider_name,
        "treatment": f.type_name,
        "minutes": f.duration_min,
        "reasons": [a.text for a in r.components],
        "caveat": r.caveat.text if r.caveat else None,
    }


class LlmExplainer:
    name = "llm"

    def __init__(self, client: LlmClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._prompt = (PROMPT_DIR / f"explain_{settings.prompt_version}.md").read_text(
            encoding="utf-8"
        )

    async def render(self, rationales: list[Rationale]) -> list[str]:
        """One batched call for all cards (ADR-09), then a **per-sentence** gate.

        Per-sentence matters: one bad sentence falls back to its own template without
        disturbing the other two.
        """
        if not rationales:
            return []
        fallback = [template.render(r) for r in rationales]
        try:
            import json

            sentences = await self._client.sentences(
                model=self._settings.model_explain,
                system=self._prompt,
                user=json.dumps({"options": [_describe(r) for r in rationales]}),
                timeout=self._settings.timeout_explain,
                count=len(rationales),
            )
        except LlmUnavailable:
            return fallback

        out: list[str] = []
        for sentence, rationale, safe in zip(sentences, rationales, fallback, strict=True):
            verdict = gate.check(sentence, rationale)
            out.append(sentence if verdict.ok else safe)
        return out

    async def render_with_gate(
        self, rationales: list[Rationale]
    ) -> list[tuple[str, gate.GateResult]]:
        """Same, but reporting which check fired -- the harness needs the rate."""
        if not rationales:
            return []
        fallback = [template.render(r) for r in rationales]
        try:
            import json

            sentences = await self._client.sentences(
                model=self._settings.model_explain,
                system=self._prompt,
                user=json.dumps({"options": [_describe(r) for r in rationales]}),
                timeout=self._settings.timeout_explain,
                count=len(rationales),
            )
        except LlmUnavailable as exc:
            return [(s, gate.GateResult(False, "unavailable", str(exc))) for s in fallback]

        out = []
        for sentence, rationale, safe in zip(sentences, rationales, fallback, strict=True):
            verdict = gate.check(sentence, rationale)
            out.append((sentence if verdict.ok else safe, verdict))
        return out
