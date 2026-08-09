"""[NFR-27] The orchestrator: a plain, readable state machine.

Deliberately not LangGraph or CrewAI. A framework DAG hides control flow behind a
runtime you must learn before your first change; this can be read end to end in five
minutes, which is the point -- the product's claim is that its decisions are
explainable, and that claim does not survive a codebase whose control flow cannot be
followed.

It owns sequencing, the timeout/fallback ladder, and a trace emit per hop. Nothing
else. All domain logic lives in the packages it calls.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.agents.explainer.render import explain_outcome
from app.config import Settings
from app.domain.decision import DecisionRecord
from app.domain.entities import Patient, SeedBundle
from app.domain.enums import Scope
from app.domain.policy import WeightProfile
from app.domain.request import RequestConstraints
from app.orchestrator.stages import run_stage
from app.reasoner.hypotheses import run_fanout
from app.trace.sink import FanOutTraceSink, Tracer


async def _ready(value):  # type: ignore[no-untyped-def]
    """An already-computed fallback, in the shape run_stage expects."""
    return value


@dataclass(frozen=True, slots=True)
class IncomingRequest:
    text: str
    patient: Patient | None
    request_id: str = ""


class Orchestrator:
    def __init__(self, agents, reasoner, world: SeedBundle, settings: Settings, sink) -> None:  # type: ignore[no-untyped-def]
        self.agents = agents
        self.reasoner = reasoner
        self.world = world
        self.settings = settings
        self.sink = sink

    async def run(
        self,
        req: IncomingRequest,
        now: datetime,
        profile: WeightProfile,
        progress: Any = None,
    ) -> DecisionRecord:
        """``progress``: an extra ``TraceSink`` that sees each span as it closes, so a
        caller can show the pipeline working during the ~15s a live request takes.
        Reuses the existing spans; nothing changes when it is None."""
        s = self.settings
        rid = req.request_id or uuid.uuid4().hex[:12]
        tracer = Tracer(FanOutTraceSink(self.sink, progress) if progress else self.sink)
        fallbacks: list[str] = []
        calls_before = self.agents.llm_call_count()

        with tracer.span("request", request_id=rid, mode=s.llm_mode):
            # 1. INTERPRET ----------------------------------------------------
            stage = await run_stage(
                tracer, "extract",
                primary=lambda: self.agents.extractor.extract(req.text, req.patient, now),
                fallback=lambda: self.agents.rules_extractor.extract(req.text, req.patient, now),
                timeout=s.timeout_extract,
                implementation=self.agents.extractor.name,
                model=s.model_extract,
            )
            constraints: RequestConstraints = stage.value
            if stage.fallback_fired:
                fallbacks.append("extract")

            # 2. VERIFY, split in two (ADR-21). The deterministic floor answers
            # everything the *reasoner* needs (hypotheses, world-validity flags) in
            # under a millisecond; the model's semantic pass only ADDS flags, so it
            # runs concurrently with reason+explain instead of gating them.
            floor = await self.agents.rules_verifier.verify(constraints, self.world, now)
            verify_task = asyncio.create_task(run_stage(
                tracer, "verify",
                primary=lambda: self.agents.verifier.verify(constraints, self.world, now),
                fallback=lambda: _ready(floor),
                timeout=s.timeout_verify,
                implementation=self.agents.verifier.name,
                model=s.model_verify,
            ))

            # 3. REASON -- deterministic, once per hypothesis, sharing Layer 0 --
            with tracer.span("reason", hypotheses=len(floor.hypotheses)) as span:
                fan = run_fanout(
                    self.reasoner, constraints, floor.hypotheses, now, profile, rid
                )
                span.attrs["shared_layer0"] = fan.shared_layer0
                span.attrs["diverged"] = fan.diverged

            # 4+5. EXPLAIN, with the model verify landing in parallel ------------
            outcome, gates = await explain_outcome(tracer, fan.resolved, self.agents.explainer)
            stage = await verify_task
            verdict = stage.value
            if stage.fallback_fired:
                fallbacks.append("verify")

            question = fan.question(floor.hypotheses[0].field).text if fan.diverged else None
            return self._record(
                rid, tracer, req, constraints, outcome, profile, fallbacks, verdict,
                question, gates, self.agents.llm_call_count() - calls_before,
            )

    def _record(
        self, rid, tracer, req, constraints, outcome, profile, fallbacks, verdict,
        question, gate_fired=0, llm_calls=0,
    ) -> DecisionRecord:  # type: ignore[no-untyped-def]
        record = DecisionRecord(
            id=rid,
            trace_id=tracer.trace_id,
            now=self.settings.reference_now,
            raw_text=req.text,
            constraints=constraints,
            scope=Scope.LOCATION,
            scope_ref=self.world.locations[0].id,
            origin_state=outcome.origin_state,
            funnel=outcome.funnel,
            offers=outcome.offers,
            overflow=outcome.overflow,
            ledger=outcome.ledger,
            counterfactual=outcome.counterfactual,
            question_asked=question,
            flags=tuple(f.message for f in verdict.flags),
            limited_availability=outcome.limited_availability,
            weight_profile_id=profile.id,
            nominal_weights=outcome.nominal_weights,
            effective_weights=outcome.effective_weights,
            score_matrix=outcome.score_matrix,
            fallback_fired=tuple(fallbacks),
            gate_fired_count=gate_fired,
            # Per decision, not per process: a cumulative counter answers "how busy
            # is the server", which is not the question the trace is asking.
            llm_calls=llm_calls,
        )
        self.sink.record_decision(record)
        return record
