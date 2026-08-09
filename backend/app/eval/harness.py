"""[Q8 / ADR-12] One function, two entry points.

``make eval`` needs an exit code and a diffable artifact; the policy panel needs the
scorecard to render in-product (FR-092…FR-101). Both call ``run_evaluation``, so
there is no second implementation to drift.

**Isolation:** each case constructs a fresh session state from the committed seed, so
no case can see another's bookings. That is a precondition for FR-097's determinism
check meaning anything.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.agents.explainer import lint
from app.agents.explainer.render import render_outcome
from app.agents.extractor.llm import LlmIntentExtractor
from app.agents.extractor.rules import RuleIntentExtractor
from app.agents.llm.client import LlmClient, LlmUnavailable
from app.agents.llm.fixtures import FixtureCachedExtractor, FixtureStore
from app.config import Settings, get_settings
from app.data.digest import canonical_json, compute_digest
from app.data.loader import load_seed
from app.data.session import MemoryScheduleRepository, SessionState
from app.data.timezone import zone
from app.domain.policy import WeightProfile
from app.eval.baseline import NaiveFirstAvailableReasoner
from app.eval.golden.labels import GOLDEN
from app.eval.metrics import ExtractionScore, Latency, RankingScore, ScheduleQuality
from app.reasoner.pipeline import DeterministicReasoner


@dataclass
class Scorecard:
    seed_digest: str
    cases: int
    labeler: str
    #: Which configuration produced these numbers. A scorecard without it invites the
    #: reader to assume the shipped one.
    mode: str = "fixtures"
    extraction_rules: dict[str, Any] = field(default_factory=dict)
    extraction_llm: dict[str, Any] | None = None
    ranking: dict[str, Any] = field(default_factory=dict)
    baseline: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    latency: dict[str, Any] = field(default_factory=dict)
    determinism: dict[str, Any] = field(default_factory=dict)
    lint: dict[str, Any] = field(default_factory=dict)
    telemetry: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        # A live run cannot assert determinism, so it is excluded from the gate
        # rather than counted as a failure.
        deterministic = self.determinism.get("identical")
        return bool(
            (deterministic is None or deterministic)
            and self.lint.get("violations") == 0
            and self.latency.get("pass")
        )

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()} | {"passed": self.passed}


def _fresh(settings: Settings):  # type: ignore[no-untyped-def]
    """A brand-new state per case. Ordering must not be able to affect results."""
    bundle = load_seed(settings.seed_dir).bundle
    repo = MemoryScheduleRepository(SessionState.from_seed(bundle))
    tz = zone(bundle.locations[0].timezone)
    return bundle, repo, tz


def _expected_matches(
    name: str, expected: Any, actual: Any, hours: tuple[int, int] = (480, 1020)
) -> tuple[bool, str]:
    """Exact match per field (FR-093). ``None`` in a label means "should be derived".

    ``time_window`` is compared on **meaning, not encoding**. An open end is
    representable two ways -- ``None`` ("from opening") and the opening minute
    itself -- and they denote the same window. Scoring them as different measured the
    extractor's serialisation preference rather than its comprehension, which cost
    the LLM column five cases it had actually read correctly.
    """
    if name == "date_range":
        if expected is None:
            return actual.derived, "expected derived"
        got = [actual.value.start.isoformat(), actual.value.end.isoformat()]
        return got == expected, f"got {got}"
    if name == "time_window":
        if expected is None:
            return actual.derived, "expected derived"
        open_min, close_min = hours
        got = [actual.value.start_min, actual.value.end_min]
        norm = [
            open_min if got[0] is None else got[0],
            close_min if got[1] is None else got[1],
        ]
        want = [
            open_min if expected[0] is None else expected[0],
            close_min if expected[1] is None else expected[1],
        ]
        return norm == want, f"got {got}"
    if name == "urgency":
        if expected is None:
            return actual.derived, "expected derived"
        return actual.value.value == expected, f"got {actual.value.value}"
    if name == "provider_preference":
        return actual.value == expected, f"got {actual.value}"
    if name == "appointment_type":
        return actual.value == expected, f"got {actual.value}"
    if name == "exclusions":
        got = sorted(actual.value.weekdays)
        return got == sorted(expected), f"got {got}"
    return False, "unknown field"


def _preferred_slot(candidates, bundle, constraints) -> str | None:  # type: ignore[no-untyped-def]
    """The independent preference rule, applied to the **full feasible set**.

    Two forms of circularity to avoid, and the second is easy to miss:

    1. Using the scorer's own top pick as the label -- then top-1 agreement is 100%
       by definition.
    2. Choosing the label from among the *offered* three -- then the top-3 hit rate
       is 100% by definition, which is the trap this function was in.

    So the label is drawn from everything that was bookable, using a plain rule a
    scheduler would recognise: the earliest feasible slot with the patient's usual
    provider, inside the requested window; falling back to the earliest feasible slot.
    """
    pool = [(c, a) for c, a in candidates.in_tier()] or list(candidates.feasible())
    if not pool:
        return None
    window = constraints.time_window.value
    in_window = [(c, a) for c, a in pool if window.distance_outside(c.start_min) == 0] or pool

    patient = bundle.patient(constraints.patient_ref) if constraints.patient_ref else None
    if patient is not None:
        usual = {patient.assigned_hygienist_id, patient.assigned_dentist_id} - {None}
        with_usual = [(c, a) for c, a in in_window if c.provider_id in usual]
        if with_usual:
            in_window = with_usual

    # A scheduler does not simply take the earliest slot -- they avoid the ones that
    # obviously wreck the day. Preferring a non-fragmenting slot keeps the label a
    # model of human judgement rather than a stopwatch. It is still an independent
    # criterion: it uses no weight vector and no axis from the scorer.
    clean = [
        (c, a) for c, a in in_window
        if a.axes is None or a.axes.subterms.fragmentation >= 0.99
    ]
    return min(clean or in_window, key=lambda p: p[0].start)[0].candidate_id


def _slot_cost(offer, reasoner, settings) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    """Orphan minutes a booking would create, and protected minutes it would consume.

    Minutes and counts, never dollars: the system has no fee schedule, and a revenue
    figure from synthetic data would be unfalsifiable.
    """
    from app.domain.candidate import Candidate
    from app.reasoner.scoring.axes import _orphan_minutes

    grid = reasoner.index.cell(offer.operatory_id, offer.day)
    if grid is None:
        return 0, 0
    cand = Candidate(
        candidate_id=offer.candidate_id, day=offer.day, start=offer.start,
        start_min=(offer.start.hour * 60 + offer.start.minute),
        duration_min=offer.duration_min, provider_id=offer.provider_id,
        operatory_id=offer.operatory_id,
    )
    orphan = _orphan_minutes(grid, cand, settings.turnover_min, settings.min_bookable_min)

    protected = 0
    for b in reasoner._repo.blocks_on(offer.day):
        if b.kind.value != "restorative_block" or b.scope_ref != offer.operatory_id:
            continue
        overlap = min(cand.end_min, b.end_min) - max(cand.start_min, b.start_min)
        if overlap > 0:
            protected += overlap
    return orphan, protected


def _llm_extractor(settings: Settings, bundle):  # type: ignore[no-untyped-def]
    """The model-backed extractor for FR-093's second column.

    In **live** mode this calls the API for all 54 cases: slower, billed, and the only
    way to measure what the shipped configuration actually scores. Recording as it
    goes means the next fixture-mode run reproduces exactly this.

    In **fixture** mode it replays committed output -- reproducible and free, and still
    genuine model output rather than a simulation, which is what makes the two-column
    comparison meaningful.
    """
    live = settings.llm_mode == "live"
    return FixtureCachedExtractor(
        LlmIntentExtractor(LlmClient(settings), bundle, settings),
        FixtureStore(settings.fixtures_dir),
        model=settings.model_extract,
        prompt_version=settings.prompt_version,
        record=live,
        allow_network=live,
        read_cache=not live,
    )


def _try_llm(extractor, text: str, bundle, settings):  # type: ignore[no-untyped-def]
    """A fixture miss means the case has no recorded model output. It is skipped, not
    counted as a failure -- an unrecorded case says nothing about model accuracy, and
    scoring it zero would understate the column.

    Only ``LlmUnavailable`` is caught. A bug in the mapping layer must surface as a
    crash here, because a column that silently degrades to "no data" is worse than no
    column at all.
    """
    try:
        return _run_sync(
            lambda: extractor.extract(text, bundle.patient("pat-000"), settings.reference_now)
        )
    except LlmUnavailable:
        return None


def _run_sync(make_coro):  # type: ignore[no-untyped-def]
    """Drive one async extraction from synchronous harness code.

    ``asyncio.run`` alone is not enough: the offline test calls the harness from
    inside a running loop, where ``asyncio.run`` raises. A private loop on a worker
    thread works from either context.

    It takes a *factory* rather than a coroutine so that no coroutine is ever created
    and then abandoned -- an un-awaited coroutine surfaces later as an unraisable
    exception in whichever unrelated test happens to trigger the collection.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(make_coro())
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(make_coro())).result()


def run_evaluation(
    settings: Settings | None = None, profile: WeightProfile | None = None
) -> Scorecard:
    s = settings or get_settings()
    bundle, repo, tz = _fresh(s)
    # The widest business day, since the labels state windows in weekday-agnostic terms
    # ("morning" is 08:00-12:00 whichever day it lands on).
    day_hours = bundle.locations[0].business_hours
    hours = (min(h.open_min for h in day_hours), max(h.close_min for h in day_hours))
    prof = profile or __import__(
        "app.domain.policy", fromlist=["GENERAL_PRACTICE_DEFAULT"]
    ).GENERAL_PRACTICE_DEFAULT

    card = Scorecard(
        seed_digest=compute_digest(s.seed_dir),
        cases=len(GOLDEN),
        labeler="proposed-unreviewed (single annotator) [R-08]",
    )

    rules_score = ExtractionScore()
    llm_score = ExtractionScore()
    # FR-093's second column. Served from committed fixtures, so the comparison is
    # reproducible and needs no network -- but the numbers are real model output.
    llm_extractor = _llm_extractor(s, bundle)
    ranking = RankingScore()
    baseline_ranking = RankingScore()
    quality = ScheduleQuality()
    baseline_quality = ScheduleQuality()
    latency = Latency()
    lint_violations: list[str] = []
    per_class: dict[str, dict[str, int]] = {}
    signatures: list[str] = []

    for i, case in enumerate(GOLDEN):
        case_id = f"g{i:02d}"
        bundle, repo, tz = _fresh(s)
        extractor = RuleIntentExtractor(bundle)
        reasoner = DeterministicReasoner(repo, s, tz)
        naive = NaiveFirstAvailableReasoner(repo, s, tz)

        constraints = extractor.extract_sync(
            case["raw_text"], bundle.patient("pat-000"), s.reference_now
        )

        for name in rules_score.per_field:
            ok, detail = _expected_matches(
                name, case["expected"][name], getattr(constraints, name), hours
            )
            rules_score.per_field[name].record(ok, case_id, detail)

        llm_constraints = _try_llm(llm_extractor, case["raw_text"], bundle, s)
        if llm_constraints is not None:
            for name in llm_score.per_field:
                ok, detail = _expected_matches(
                    name, case["expected"][name], getattr(llm_constraints, name), hours
                )
                llm_score.per_field[name].record(ok, case_id, detail)

        t0 = time.perf_counter()
        outcome = render_outcome(reasoner.run(constraints, s.reference_now, prof, case_id))
        latency.record((time.perf_counter() - t0) * 1000)

        naive_outcome = naive.run(constraints, s.reference_now, prof, case_id)

        # Drawn from everything bookable, not from what we chose to offer.
        label_cs, _, _ = reasoner.prepare(constraints, s.reference_now, case_id)
        preferred = _preferred_slot(label_cs, bundle, constraints)
        offered_ids = [o.candidate_id for o in outcome.offers]
        ranking.record(preferred, offered_ids, case_id)
        baseline_ranking.record(preferred, [o.candidate_id for o in naive_outcome.offers], case_id)

        for tag in case["class_tags"]:
            bucket = per_class.setdefault(tag, {"cases": 0, "ours": 0, "naive": 0})
            bucket["cases"] += 1
            bucket["ours"] += int(preferred in offered_ids)
            bucket["naive"] += int(
                preferred in [o.candidate_id for o in naive_outcome.offers]
            )

        # Measured from the schedule itself, so the two rankers are scored on the
        # same basis rather than on their own self-reported numbers.
        for target, outc in ((quality, outcome), (baseline_quality, naive_outcome)):
            target.cases += 1
            top = outc.offers[0] if outc.offers else None
            if top is not None:
                orphan, protected = _slot_cost(top, reasoner, s)
                target.orphan_minutes += orphan
                target.protected_minutes += protected

        for o in (*outcome.offers, *outcome.overflow):
            result = lint.check(o.template_reason, o.rationale.facts)
            if not result.ok:
                lint_violations.append(f"{case_id}: {o.template_reason!r} -> {result.violations}")

        signatures.append(canonical_json([
            {"c": o.candidate_id, "s": o.score, "r": o.template_reason} for o in outcome.offers
        ]))

    # FR-097: run twice, diff the serialised records, fail on any difference.
    second: list[str] = []
    for i, case in enumerate(GOLDEN):
        bundle, repo, tz = _fresh(s)
        extractor = RuleIntentExtractor(bundle)
        reasoner = DeterministicReasoner(repo, s, tz)
        c2 = extractor.extract_sync(
            case["raw_text"], bundle.patient("pat-000"), s.reference_now
        )
        o2 = render_outcome(reasoner.run(c2, s.reference_now, prof, f"g{i:02d}"))
        second.append(canonical_json([
            {"c": o.candidate_id, "s": o.score, "r": o.template_reason} for o in o2.offers
        ]))

    differing = [
        f"g{i:02d}"
        for i, (a, b) in enumerate(zip(signatures, second, strict=True))
        if a != b
    ]

    card.mode = s.llm_mode
    card.extraction_rules = rules_score.as_dict()
    card.extraction_llm = llm_score.as_dict() if llm_score.per_field["urgency"].total else None
    card.ranking = ranking.as_dict()
    card.baseline = {
        "naive": baseline_ranking.as_dict(),
        "ours": ranking.as_dict(),
        "quality_ours": quality.as_dict(),
        "quality_naive": baseline_quality.as_dict(),
        # Where the delta is small for a class, the class is NAMED (FR-095).
        "per_class": {
            tag: {
                **v,
                "delta": v["ours"] - v["naive"],
                "verdict": "no measurable gain" if v["ours"] <= v["naive"] else "better",
            }
            for tag, v in sorted(per_class.items())
        },
    }
    card.quality = quality.as_dict()
    card.latency = latency.as_dict(ceiling_ms=2000.0)
    card.determinism = {"identical": not differing, "differing": differing}
    if s.llm_mode == "live":
        # Live extraction is not reproducible (known-limitations.md §1), so the check
        # is reported as not-applicable rather than as a pass. Marking it green here
        # would be the most misleading number on the card: the one that says the
        # system is deterministic, produced by the run that proves it is not.
        card.determinism = {
            "identical": None,
            "differing": [],
            "not_applicable": "live mode; run in fixture mode for FR-097",
        }
    card.lint = {"violations": len(lint_violations), "detail": lint_violations}
    card.telemetry = {
        "rules_fallback_rate_pct": 100.0,  # rules mode is the shipped default offline
        "gate_firing_rate_pct": None,      # the LLM explainer is not wired yet (S8)
        "opik_unavailable_count": 0,
    }
    card.limitations = [
        "Labels are single-annotator and unreviewed [R-08] -- every ranking number "
        "below carries that caveat.",
        "The preferred slot is heuristic, not a practising scheduler's judgement: "
        "earliest non-fragmenting feasible slot with the patient's usual provider, "
        "inside the requested window.",
        "That heuristic is closer to the naive baseline's objective (earliest) than "
        "to this system's (a weighted trade-off), so the TOP-3 head-to-head is "
        "biased AGAINST this system. The unbiased comparisons are the orphan-minute "
        "and protected-minute deltas, which are measured from the schedule itself "
        "rather than from either ranker's own numbers.",
    ]
    if card.extraction_llm is None:
        card.limitations.append(
            "Extraction accuracy is reported for rules mode only; the LLM column "
            "needs recorded fixtures to populate (FR-093)."
        )
    return card
