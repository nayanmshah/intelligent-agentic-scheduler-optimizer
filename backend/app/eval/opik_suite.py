"""The golden set as an Opik Dataset, scored as an Opik Experiment.

``make eval`` already prints a scorecard and returns an exit code — that is the gate.
This is the *other* half of the same numbers: pushed into Opik so runs are comparable
to each other over time, filterable per case, and inspectable down to the trace that
produced each score.

**Why both exist.** The CLI scorecard answers "does this build pass?" in CI, offline,
in two seconds. Opik answers "did changing the model help, and which cases moved?" —
a question a terminal cannot answer because it needs history. Neither replaces the
other, and both read the same golden labels so they cannot disagree about the facts.

Five metrics, each measuring something the product actually claims:

    extraction_accuracy   per-field agreement with the labels (FR-093)
    top3_hit              the preferred slot appears in the offered three (FR-094)
    schedule_quality      orphan minutes created — the honest, unbiased number (§11)
    read_aloud            the reason lines pass the lint a receptionist needs (FR-065)
    faithful              no offer claims something the scorer did not emit (FR-062)

Usage::

    make opik-eval                 # live models, the shipped configuration
    SCHED_LLM_MODE=fixtures make opik-eval
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from opik import Opik
from opik.evaluation import evaluate
from opik.evaluation.metrics import base_metric, score_result

from app.agents.explainer import lint
from app.agents.explainer.render import render_outcome
from app.config import Settings, get_settings
from app.container import AppContainer
from app.data.digest import seed_digest
from app.eval.golden.labels import GOLDEN
from app.eval.harness import _expected_matches, _preferred_slot, _slot_cost
from app.orchestrator.machine import IncomingRequest

DATASET = "dental-scheduler-golden"


# ------------------------------------------------------------------ metrics ----
class ExtractionAccuracy(base_metric.BaseMetric):
    """Fraction of the six constraint fields the run got right.

    Partial credit on purpose: a run that reads the date correctly and the urgency
    wrongly is not the same failure as one that reads nothing, and a pass/fail metric
    would hide which field moved when a model changes.
    """

    def __init__(self) -> None:
        super().__init__(name="extraction_accuracy")

    def score(self, expected: dict, fields: dict, **_: Any) -> score_result.ScoreResult:  # type: ignore[override,type-arg]
        if not fields:
            return score_result.ScoreResult(
                name=self.name, value=0.0, reason="extraction produced nothing"
            )
        wrong = []
        for name, want in expected.items():
            ok, detail = _expected_matches(name, want, fields[name])
            if not ok:
                wrong.append(f"{name} ({detail})")
        value = 1.0 - len(wrong) / len(expected)
        return score_result.ScoreResult(
            name=self.name, value=value,
            reason="all six fields correct" if not wrong else "wrong: " + ", ".join(wrong),
        )


class Top3Hit(base_metric.BaseMetric):
    """Did the human-preferred slot appear in the offered three? (FR-094)

    The label is a heuristic whose bias toward earliest-first is documented in
    known-limitations §2 — kept here anyway, because a metric with a known bias and a
    written-down reason is more useful than no metric.
    """

    def __init__(self) -> None:
        super().__init__(name="top3_hit")

    def score(self, preferred: str | None, offered: list, **_: Any) -> score_result.ScoreResult:  # type: ignore[override,type-arg]
        if preferred is None:
            return score_result.ScoreResult(
                name=self.name, value=0.0, reason="no feasible slot to prefer",
                scoring_failed=True,
            )
        hit = preferred in offered
        return score_result.ScoreResult(
            name=self.name, value=1.0 if hit else 0.0,
            reason="preferred slot offered" if hit else "preferred slot not in the top three",
        )


class ScheduleQuality(base_metric.BaseMetric):
    """Orphan minutes the top offer would create, normalised against the ceiling.

    The unbiased half of the evaluation: measured from the schedule itself rather
    than from either ranker's own output, so the labeller's preferences cannot
    flatter it (§11). 1.0 means the booking wastes nothing.
    """

    def __init__(self) -> None:
        super().__init__(name="schedule_quality")

    def score(self, orphan_minutes: int | None, **_: Any) -> score_result.ScoreResult:  # type: ignore[override]
        if orphan_minutes is None:
            return score_result.ScoreResult(
                name=self.name, value=0.0, reason="no offer to evaluate", scoring_failed=True
            )
        value = max(0.0, 1.0 - orphan_minutes / 60.0)
        return score_result.ScoreResult(
            name=self.name, value=value,
            reason=f"{orphan_minutes} orphan minutes created by the top offer",
        )


class ReadAloud(base_metric.BaseMetric):
    """Every reason line is sayable to a patient on the phone (FR-065)."""

    def __init__(self) -> None:
        super().__init__(name="read_aloud")

    def score(self, reasons: list, **_: Any) -> score_result.ScoreResult:  # type: ignore[override,type-arg]
        if not reasons:
            return score_result.ScoreResult(
                name=self.name, value=0.0, reason="no reason lines", scoring_failed=True
            )
        bad = []
        for r in reasons:
            words = len(lint.words(r))
            if words > lint.MAX_WORDS:
                bad.append(f"{words} words")
            for token in ("candidate", "overflow", "escalate", "tier", "weight", "score"):
                if token in r.lower():
                    bad.append(f"jargon {token!r}")
        return score_result.ScoreResult(
            name=self.name, value=1.0 - min(1.0, len(bad) / len(reasons)),
            reason="all lines readable" if not bad else "; ".join(bad[:3]),
        )


class Faithful(base_metric.BaseMetric):
    """No offer asserts a booking, and every one echoes its resolved date and time.

    The two failures that reach a patient as a false statement rather than an awkward
    one — both found live, both now gate checks (F5, F6).
    """

    def __init__(self) -> None:
        super().__init__(name="faithful")

    def score(self, offers: list, **_: Any) -> score_result.ScoreResult:  # type: ignore[override,type-arg]
        if not offers:
            return score_result.ScoreResult(
                name=self.name, value=0.0, reason="nothing offered", scoring_failed=True
            )
        problems = []
        for o in offers:
            low = o["reason"].lower()
            for claim in ("you're booked", "you are booked", "you're scheduled", "all set"):
                if claim in low:
                    problems.append(f"asserts a booking: {claim!r}")
            for field in ("weekday", "date_display", "start_display"):
                if o[field].lower() not in low:
                    problems.append(f"missing {o[field]!r}")
        return score_result.ScoreResult(
            name=self.name, value=1.0 - min(1.0, len(problems) / len(offers)),
            reason="faithful" if not problems else "; ".join(problems[:3]),
        )


# --------------------------------------------------------------------- task ----
def build_task(settings: Settings):  # type: ignore[no-untyped-def]
    """One dataset item -> everything the metrics need.

    Runs the **real orchestrator**, not a reimplementation of it, so a regression in
    the shipped pipeline shows up here rather than in a parallel copy that drifted.
    """
    container = AppContainer(settings=settings)
    bundle = container.load.bundle
    patient = bundle.patient("pat-000")

    def task(item: dict[str, Any]) -> dict[str, Any]:
        # Fresh state per case: ordering must not be able to affect a score.
        c = AppContainer(settings=settings)
        record = asyncio.run(
            c.orchestrator.run(
                IncomingRequest(text=item["request"], patient=patient),
                c.clock.now(),
                c.state.active_profile,
            )
        )
        constraints = record.constraints
        fields = (
            {
                n: getattr(constraints, n)
                for n in (
                    "date_range", "time_window", "urgency",
                    "provider_preference", "appointment_type", "exclusions",
                )
            }
            if constraints
            else {}
        )

        preferred, orphan = None, None
        if constraints is not None:
            cs, _gate, _type = c.reasoner.prepare(constraints, c.clock.now(), record.id)
            preferred = _preferred_slot(cs, bundle, constraints)
            if record.offers:
                rendered = render_outcome(c.reasoner.run(
                    constraints, c.clock.now(), c.state.active_profile, record.id
                ))
                if rendered.offers:
                    orphan = _slot_cost(rendered.offers[0], c.reasoner, settings)[0]

        return {
            "fields": fields,
            "preferred": preferred,
            "offered": [o.candidate_id for o in record.offers],
            "orphan_minutes": orphan,
            "reasons": [o.reason for o in record.offers],
            "offers": [
                {
                    "reason": o.reason, "weekday": o.weekday,
                    "date_display": o.date_display, "start_display": o.start_display,
                }
                for o in record.offers
            ],
            # Shown in the Opik UI beside each score, so a bad number is one click
            # from the words that produced it.
            "output": {
                "offers": [
                    f"{o.weekday} {o.date_display} {o.start_display}" for o in record.offers
                ],
                "flags": list(record.flags),
                "question": record.question_asked,
                "llm_calls": record.llm_calls,
            },
        }

    return task


def sync_dataset(client: Opik) -> Any:
    """Push the golden cases. Idempotent: Opik deduplicates on item content."""
    dataset = client.get_or_create_dataset(
        name=DATASET,
        # Opik caps this at 255 characters, so it carries the one caveat a reader of
        # the scores must have and points at where the rest is written down.
        description=(
            "54 hand-labelled scheduling requests. Single annotator, unreviewed [R-08]: "
            "the preference label leans earliest-first, so top3_hit is the weakest "
            "metric here and schedule_quality the strongest. "
            "See docs/known-limitations.md sections 2 and 11."
        ),
    )
    dataset.insert([
        {
            "request": case["raw_text"],
            "expected": case["expected"],
            "tags": case.get("tags", []),
        }
        for case in GOLDEN
    ])
    return dataset


def main() -> int:
    settings = get_settings()
    client = Opik(
        host=settings.opik_url.rstrip("/") + ("" if settings.opik_url.endswith("/api") else "/api"),
        project_name=settings.opik_project,
    )
    dataset = sync_dataset(client)
    sys.stdout.write(f"  dataset {DATASET!r} synced with {len(GOLDEN)} cases\n")

    result = evaluate(
        dataset=dataset,
        task=build_task(settings),
        scoring_metrics=[
            ExtractionAccuracy(), Top3Hit(), ScheduleQuality(), ReadAloud(), Faithful()
        ],
        experiment_name_prefix=f"{settings.llm_mode}-{settings.model_extract}",
        project_name=settings.opik_project,
        experiment_config={
            "llm_mode": settings.llm_mode,
            "model_extract": settings.model_extract,
            "model_verify": settings.model_verify,
            "model_explain": settings.model_explain,
            "prompt_version": settings.prompt_version,
            "weight_profile": "general_practice",
            # So a run can be tied back to the exact data it scored (ADR-11).
            "seed_digest": seed_digest(settings.seed_dir)[0][:16],
        },
        experiment_tags=[settings.llm_mode, settings.model_extract],
        # One at a time: the task runs the real pipeline, and concurrent live calls
        # would measure the rate limiter rather than the product.
        task_threads=1,
    )
    sys.stdout.write(f"\n  experiment: {result.experiment_name}\n")
    sys.stdout.write(f"  open {settings.opik_url}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
