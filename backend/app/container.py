"""Composition root. The only place implementations are chosen.

Everything downstream receives its collaborators; nothing reaches for a global. That
is what lets the eval harness run 40 cases against 40 isolated states, and what makes
swapping an agent implementation a config edit rather than a code change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from app.agents.registry import AgentRegistry, build_registry
from app.clock import Clock, FrozenClock, SystemClock
from app.config import Settings, get_settings
from app.data.loader import LoadResult, load_seed
from app.data.session import MemoryScheduleRepository, SessionState
from app.data.timezone import zone
from app.orchestrator.machine import Orchestrator
from app.reasoner.pipeline import DeterministicReasoner
from app.trace.inprocess import InProcessTraceSink
from app.trace.opik import OpikTraceSink
from app.trace.redaction import PhiRedactor, RedactingSink
from app.trace.sink import FanOutTraceSink


@dataclass
class AppContainer:
    settings: Settings = field(default_factory=get_settings)

    @cached_property
    def clock(self) -> Clock:
        if self.settings.clock == "system":
            return SystemClock(zone(self.settings.timezone))
        return FrozenClock(self.settings.reference_now)

    @cached_property
    def load(self) -> LoadResult:
        return load_seed(self.settings.seed_dir)

    @cached_property
    def state(self) -> SessionState:
        return SessionState.from_seed(self.load.bundle)

    @cached_property
    def repo(self) -> MemoryScheduleRepository:
        return MemoryScheduleRepository(self.state)

    @cached_property
    def trace_store(self) -> InProcessTraceSink:
        return InProcessTraceSink(max_decisions=self.settings.trace_store_size)

    @cached_property
    def opik(self) -> OpikTraceSink:
        return OpikTraceSink(
            self.settings.opik_url,
            enabled=self.settings.opik_enabled,
            project=self.settings.opik_project,
        )

    @cached_property
    def sink(self) -> FanOutTraceSink:
        """In-process first and synchronous; Opik second, bounded and best-effort.

        Redaction is applied to the *external* leg only [AR-06]: the local store is
        the byte-identical replay substrate and needs the raw text. That reasoning is
        v1.0-specific -- in production the local store is a database and it inverts.
        """
        legs: list = [self.trace_store]
        if self.settings.opik_enabled:
            legs.append(
                RedactingSink(self.opik, PhiRedactor())
                if self.settings.opik_redact_phi
                else self.opik
            )
        return FanOutTraceSink(*legs)

    @cached_property
    def reasoner(self) -> DeterministicReasoner:
        tz = zone(self.load.bundle.locations[0].timezone)
        return DeterministicReasoner(self.repo, self.settings, tz)

    @cached_property
    def agents(self) -> AgentRegistry:
        return build_registry(self.settings, self.load.bundle)

    @cached_property
    def orchestrator(self) -> Orchestrator:
        return Orchestrator(
            agents=self.agents,
            reasoner=self.reasoner,
            world=self.load.bundle,
            settings=self.settings,
            sink=self.sink,
        )

    #: Cached properties that close over session state. Every one of them must be
    #: dropped on reset, or the object graph splits: the orchestrator keeps the
    #: pre-reset reasoner while a fresh one is built for replay, and the two disagree
    #: about the world. That is exactly how byte-identical replay (FR-088) started
    #: failing -- caught by making the API tests independent, not by a replay test.
    _STATE_DEPENDENT = ("reasoner", "orchestrator")

    def reset(self) -> None:
        """Restore the reference dataset. Traces deliberately survive (FR-072)."""
        self.state.reset()
        for name in self._STATE_DEPENDENT:
            self.__dict__.pop(name, None)

    def describe(self) -> dict[str, object]:
        """What pre-flight reports. Any red item is named, never merely counted."""
        s = self.settings
        return {
            "reference_now": self.clock.now().isoformat(),
            "clock": s.clock,
            "llm_mode": s.llm_mode,
            "network": "offline" if s.offline else "live",
            "api_key_present": s.has_api_key,
            "agents": self.agents.describe(),
            "models": {
                "extract": s.model_extract,
                "verify": s.model_verify,
                "explain": s.model_explain,
            },
            "timeout_ladder_total_s": round(s.timeout_ladder_total, 2),
            "voice_input": s.voice_input,
            "opik_enabled": s.opik_enabled,
            "opik": self.opik.counters.as_dict() if s.opik_enabled else None,
            "seed_anomalies": self.load.summary,
            "flags": {
                "fanout_beyond_two_classes": s.fanout_beyond_two_classes,
                "no_show_risk_hook": s.no_show_risk_hook,
                "bump_candidates": s.bump_candidates,
            },
        }


def build_container() -> AppContainer:
    return AppContainer()
