"""[ADR-03] Config -> implementations, in exactly one place.

This is the switch FR-093 needs: the harness runs the golden set through both
implementations and prints two columns of accuracy. Scattered branches would make
that comparison impossible to obtain and impossible to trust.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.explainer.llm import LlmExplainer
from app.agents.explainer.template import TemplateExplainer
from app.agents.extractor.llm import LlmIntentExtractor
from app.agents.extractor.rules import RuleIntentExtractor
from app.agents.llm.client import LlmClient
from app.agents.llm.fixtures import FixtureCachedExtractor, FixtureStore
from app.agents.verifier.rules import RuleConstraintVerifier
from app.config import Settings
from app.domain.entities import SeedBundle


@dataclass
class AgentRegistry:
    extractor: Any
    rules_extractor: Any
    verifier: Any
    rules_verifier: Any
    explainer: Any
    template_explainer: Any

    def describe(self) -> dict[str, str]:
        return {
            "extractor": self.extractor.name,
            "verifier": self.verifier.name,
            "explainer": self.explainer.name,
        }


def build_registry(settings: Settings, world: SeedBundle) -> AgentRegistry:
    rules_extractor = RuleIntentExtractor(world)
    rules_verifier = RuleConstraintVerifier(
        theta=settings.confidence_theta,
        allow_wider_fanout=settings.fanout_beyond_two_classes,
    )
    template_explainer = TemplateExplainer()

    extractor: Any = rules_extractor
    if settings.extractor == "llm" and settings.llm_mode != "rules":
        client = LlmClient(settings)
        llm = LlmIntentExtractor(client, world, settings)
        # Fixtures wrap the LLM rather than replacing it, so offline and live differ
        # only in where the JSON came from.
        extractor = (
            FixtureCachedExtractor(
                llm,
                FixtureStore(settings.fixtures_dir),
                model=settings.model_extract,
                prompt_version=settings.prompt_version,
                record=settings.llm_mode == "live",
                allow_network=settings.llm_mode == "live",
            )
            if settings.llm_mode in {"fixtures", "live"}
            else llm
        )

    explainer: Any = template_explainer
    if settings.explainer == "llm" and settings.llm_mode == "live":
        explainer = LlmExplainer(LlmClient(settings), settings)

    return AgentRegistry(
        extractor=extractor,
        rules_extractor=rules_extractor,
        verifier=rules_verifier,
        rules_verifier=rules_verifier,
        explainer=explainer,
        template_explainer=template_explainer,
    )
