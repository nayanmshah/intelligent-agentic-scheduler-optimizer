"""The only module that reads the environment.

Every tunable the PRD registers as an assumption ([A-06] through [A-20]) appears here
as a named field rather than as a literal at its point of use. That is what makes the
assumptions register checkable: if a number in the PRD has no field here, one of the
two is out of date.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parent.parent

# [D-01] Settled. Every edge-case anchor, every golden label and every relative date
# in the PRD is expressed against this instant. Changing it invalidates the golden set.
REFERENCE_NOW = datetime.fromisoformat("2026-08-10T09:00:00-07:00")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCHED_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- clock and data ---------------------------------------------------------
    # "frozen" pins NOW to the reference dataset (the demo default, and what makes
    # relative dates reproducible). "system" reads real time -- correct the moment
    # the schedule behind it is live rather than committed.
    clock: str = "frozen"
    reference_now: datetime = REFERENCE_NOW
    timezone: str = "America/Los_Angeles"
    seed_dir: Path = BACKEND_ROOT / "data" / "seed"
    fixtures_dir: Path = BACKEND_ROOT / "agents" / "llm" / "fixtures"
    golden_path: Path = BACKEND_ROOT / "eval" / "golden" / "golden_set.json"
    static_dir: Path = BACKEND_ROOT / "static"

    # -- agent implementations (ADR-03; one registry reads these) ---------------
    # **Live by default.** Every role that a model makes better uses one, and the
    # deterministic implementation is the *fallback* rather than the default. Running
    # the model only when asked meant the product's headline capability was the one
    # thing a reader never saw working.
    #
    # Degradation is automatic and layered, so this costs no reliability: no key, no
    # network, a timeout or a refusal drops to committed fixtures, and a fixture miss
    # drops to rules. Silent to the operator, loud in the trace (NFR-16), and the
    # header always says which path answered.
    llm_mode: str = "live"  # live | fixtures | rules
    extractor: str = "llm"  # llm | rules
    verifier: str = "llm"  # llm | rules
    explainer: str = "llm"  # llm | template
    reasoner: str = "deterministic"  # deterministic | naive

    # -- models, per stage (ADR-15) ---------------------------------------------
    model_extract: str = "claude-opus-5"
    model_verify: str = "claude-sonnet-5"
    model_explain: str = "claude-sonnet-5"
    llm_effort: str = "low"
    llm_max_tokens: int = 8192  # sized for thinking + output together [AR-02]
    prompt_version: str = "v1"

    # -- the timeout ladder ------------------------------------------------------
    # Measured, not guessed: live extraction runs ~7.3s at p50 against this schema
    # (six fields, each with a confidence and a verbatim span -- FR-003 is what makes
    # the payload large, and the interpretation strip is why it is worth it).
    #
    # The original 2.2s budget was set before that measurement and could not be met,
    # so every live request timed out into the fallback -- the ladder "worked" by
    # never running the model. These are the numbers that let it actually run; the
    # honest cost is in known-limitations.md §12.
    timeout_extract: float = 20.0
    timeout_verify: float = 12.0
    timeout_explain: float = 15.0
    deterministic_budget: float = 0.3
    overhead_budget: float = 0.2
    live_latency_ceiling: float = 50.0

    # -- scheduling policy ------------------------------------------------------
    search_horizon_days: int = 14  # [A-09]
    grid_granularity_min: int = 10  # [A-20]
    turnover_min: int = 10  # [A-08]
    doctor_check_min: int = 10  # FR-023
    min_bookable_min: int = 30  # orphan-gap threshold, FR-043
    hold_ttl_min: int = 15  # [A-07]

    # -- decision thresholds ----------------------------------------------------
    confidence_theta: float = 0.6  # [A-06]
    epsilon_band: float = 0.03  # [A-13]
    diversity_window_min: int = 60  # [A-13]
    counterfactual_min_gain: float = 0.08  # [A-14]
    stability_samples: int = 200  # [A-15]
    stability_seed: int = 20260810  # seeded so the number is reproducible run to run

    # -- feature flags. Both default OFF and both are visible in config. --------
    fanout_beyond_two_classes: bool = False  # FR-014 STRETCH
    no_show_risk_hook: bool = False  # FR-084 STRETCH, off by default [R-09]
    bump_candidates: bool = False  # FR-037 STRETCH

    # -- observability ----------------------------------------------------------
    opik_enabled: bool = False
    opik_url: str = "http://localhost:5173"
    trace_store_size: int = 500

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    @property
    def timeout_ladder_total(self) -> float:
        """Asserted against ``live_latency_ceiling`` by a test, not by inspection."""
        return (
            self.timeout_extract
            + self.timeout_verify
            + self.timeout_explain
            + self.deterministic_budget
            + self.overhead_budget
        )

    @property
    def offline(self) -> bool:
        return self.llm_mode != "live"

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
