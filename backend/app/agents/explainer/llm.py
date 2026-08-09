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


def _describe(r: Rationale, is_alternative: bool = False) -> dict:  # type: ignore[type-arg]
    f = r.facts
    return {
        # FR-038. Without this the model has no way to know the slot misses the
        # request, and it writes "Thursday the 20th with Sarah, the provider you asked
        # for" for a patient who asked for the 13th -- true, and read aloud as a match.
        "does_not_match_request": is_alternative,
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
        self, rationales: list[Rationale], alternatives: list[bool] | None = None
    ) -> list[tuple[str, gate.GateResult]]:
        """Same, but reporting which check fired -- the harness needs the rate."""
        if not rationales:
            return []
        alt = alternatives or [False] * len(rationales)
        fallback = [
            template.render(r, is_alternative=a)
            for r, a in zip(rationales, alt, strict=True)
        ]
        try:
            import json

            sentences = await self._client.sentences(
                model=self._settings.model_explain,
                system=self._prompt,
                user=json.dumps({
                    "options": [_describe(r, a) for r, a in zip(rationales, alt, strict=True)]
                }),
                timeout=self._settings.timeout_explain,
                count=len(rationales),
            )
        except LlmUnavailable as exc:
            return [(s, gate.GateResult(False, "unavailable", str(exc))) for s in fallback]

        out = []
        for sentence, rationale, safe, is_alt in zip(
            sentences, rationales, fallback, alt, strict=True
        ):
            verdict = gate.check(sentence, rationale, is_alternative=is_alt)
            out.append((sentence if verdict.ok else safe, verdict))
        return out
