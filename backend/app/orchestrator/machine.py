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

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.agents.explainer.render import render_outcome
from app.config import Settings
from app.domain.decision import DecisionRecord
from app.domain.entities import Patient, SeedBundle
from app.domain.enums import Scope
from app.domain.policy import WeightProfile
from app.domain.request import RequestConstraints
from app.orchestrator.stages import run_stage
from app.reasoner.hypotheses import run_fanout
from app.trace.sink import Tracer


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
        self, req: IncomingRequest, now: datetime, profile: WeightProfile
    ) -> DecisionRecord:
        s = self.settings
        rid = req.request_id or uuid.uuid4().hex[:12]
        tracer = Tracer(self.sink)
        fallbacks: list[str] = []

        with tracer.span("request", request_id=rid, mode=s.llm_mode):
            # 1. INTERPRET ----------------------------------------------------
            stage = await run_stage(
                tracer, "extract",
                primary=lambda: self.agents.extractor.extract(req.text, req.patient, now),
                fallback=lambda: self.agents.rules_extractor.extract(req.text, req.patient, now),
                timeout=s.timeout_extract,
                implementation=self.agents.extractor.name,
            )
            constraints: RequestConstraints = stage.value
            if stage.fallback_fired:
                fallbacks.append("extract")

            # 2. VERIFY (against the world, never the schedule) ----------------
            stage = await run_stage(
                tracer, "verify",
                primary=lambda: self.agents.verifier.verify(constraints, self.world, now),
                fallback=lambda: self.agents.rules_verifier.verify(constraints, self.world, now),
                timeout=s.timeout_verify,
                implementation=self.agents.verifier.name,
            )
            verdict = stage.value
            if stage.fallback_fired:
                fallbacks.append("verify")

            # 3. REASON -- deterministic, once per hypothesis, sharing Layer 0 --
            with tracer.span("reason", hypotheses=len(verdict.hypotheses)) as span:
                fan = run_fanout(
                    self.reasoner, constraints, verdict.hypotheses, now, profile, rid
                )
                span.attrs["shared_layer0"] = fan.shared_layer0
                span.attrs["diverged"] = fan.diverged

            # 4. DECIDE -- ask only when the answer would change what is offered --
            if fan.diverged:
                question = fan.question(verdict.hypotheses[0].field)
                # The provisional offers are still on screen behind the question, so
                # they still need readable reason lines.
                with tracer.span("explain", offers=len(fan.resolved.offers)):
                    provisional = render_outcome(fan.resolved)
                return self._record(
                    rid, tracer, req, constraints, provisional, profile,
                    fallbacks, verdict, question.text
                )

            # 5. EXPLAIN -- renders a Rationale and can reach nothing else -------
            outcome = fan.resolved
            with tracer.span("explain", offers=len(outcome.offers)):
                outcome = render_outcome(outcome)

            return self._record(
                rid, tracer, req, constraints, outcome, profile, fallbacks, verdict, None
            )

    def _record(
        self, rid, tracer, req, constraints, outcome, profile, fallbacks, verdict, question,
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
        )
        self.sink.record_decision(record)
        return record
