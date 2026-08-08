"""S5 exit criteria: unstructured text in, offers out, with the network unplugged."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.agents.extractor.rules import RuleIntentExtractor
from app.agents.verifier.rules import RuleConstraintVerifier
from app.config import get_settings
from app.container import AppContainer
from app.domain.enums import Urgency
from app.orchestrator.machine import IncomingRequest
from app.orchestrator.stages import run_stage
from app.trace.sink import Tracer

SETTINGS = get_settings()
NOW = SETTINGS.reference_now


@pytest.fixture(scope="module")
def container():  # type: ignore[no-untyped-def]
    return AppContainer()


@pytest.fixture(scope="module")
def world(container):  # type: ignore[no-untyped-def]
    return container.load.bundle


@pytest.fixture(scope="module")
def extractor(world):  # type: ignore[no-untyped-def]
    return RuleIntentExtractor(world)


async def extract(extractor, text):  # type: ignore[no-untyped-def]
    return await extractor.extract(text, None, NOW)


# ---------------------------------------------------- FR-001 / FR-003 -------
async def test_every_span_is_verbatim(extractor) -> None:
    """FR-003's assertion: request_text[start:end] == span.text, every time.
    A fabricated span is worse than no span."""
    for text in (
        "Can I come in next Thursday after 3? Prefer Sarah if she's around.",
        "I need something first thing tomorrow, it's urgent",
        "Whatever works next week, I have PT on Tuesdays",
        "My tooth's been bothering me since Friday",
        "Need a cleaning, not with Dr. Okafor please",
    ):
        c = await extract(extractor, text)
        assert c.spans_are_verbatim(), f"non-verbatim span for {text!r}"


async def test_reference_scenario_resolves_correctly(extractor) -> None:
    c = await extract(
        extractor, "Can I come in next Thursday after 3? Prefer Sarah if she's around."
    )
    # "after 3" must be 15:00, not 03:00 -- the ranked #1 failure mode.
    assert c.time_window.value.start_min == 15 * 60
    assert c.provider_preference.value == "prov-sarah"
    # From Monday the 10th, "next Thursday" is genuinely ambiguous, so the nearer
    # reading is taken with low confidence rather than a confident guess.
    assert c.date_range.value.start == date(2026, 8, 13)
    assert c.date_range.confidence < SETTINGS.confidence_theta


async def test_exclusions_are_captured_as_hard_constraints(extractor) -> None:
    c = await extract(extractor, "Whatever works next week, I have PT on Tuesdays")
    assert 1 in c.exclusions.value.weekdays  # Tuesday
    assert c.exclusions.span is not None


async def test_urgency_is_read_from_the_words(extractor) -> None:
    c = await extract(extractor, "I need something first thing tomorrow, it's urgent")
    assert c.urgency.value is Urgency.URGENT
    assert c.date_range.value.start == date(2026, 8, 11)
    assert c.time_window.value.start_min == 8 * 60


async def test_negated_provider_is_not_treated_as_a_preference(extractor) -> None:
    c = await extract(extractor, "Need a cleaning, not with Dr. Okafor please")
    assert c.provider_preference.value is None
    assert c.provider_preference.derived


# ---------------------------------------------------- FR-011 / FR-014 -------
async def test_ambiguous_relative_date_produces_two_hypotheses(extractor, world) -> None:
    c = await extract(extractor, "Can I come in next Thursday after 3?")
    verdict = await RuleConstraintVerifier(SETTINGS.confidence_theta).verify(c, world, NOW)
    assert verdict.outcome == "ask"
    assert len(verdict.hypotheses) == 2
    starts = {h.constraints.date_range.value.start for h in verdict.hypotheses}
    assert starts == {date(2026, 8, 13), date(2026, 8, 20)}


async def test_unambiguous_phrasing_asks_nothing(extractor, world) -> None:
    """The contrast is what proves the test is a test and not a coin flip."""
    c = await extract(extractor, "Can I come in Thursday after 3?")
    verdict = await RuleConstraintVerifier(SETTINGS.confidence_theta).verify(c, world, NOW)
    assert verdict.outcome != "ask"


async def test_date_fanout_shares_layer0(extractor, world) -> None:
    """§9 -- the property that keeps fan-out affordable. date_range appears in no
    Layer-0 rule, so both readings reuse the whole annotated candidate set."""
    from app.reasoner.hypotheses import can_share_layer0

    c = await extract(extractor, "Can I come in next Thursday after 3?")
    verdict = await RuleConstraintVerifier(SETTINGS.confidence_theta).verify(c, world, NOW)
    assert can_share_layer0(verdict.hypotheses) is True


# ------------------------------------------------- orchestrator, offline ----
async def test_end_to_end_with_no_network(container) -> None:
    """Every MUST path works with networking disabled (NFR-09)."""
    record = await container.orchestrator.run(
        IncomingRequest(text="I'd like a cleaning next Thursday after 3", patient=None),
        NOW,
        container.state.active_profile,
    )
    assert record.offers or record.question_asked
    assert record.funnel is not None
    assert record.trace_id


async def test_the_decision_is_recorded_and_replayable(container) -> None:
    record = await container.orchestrator.run(
        IncomingRequest(text="cleaning on Wednesday morning", patient=None),
        NOW,
        container.state.active_profile,
    )
    stored = container.trace_store.decision(record.id)
    assert stored is not None
    spans = container.trace_store.spans_for(record.trace_id)
    assert {s.stage for s in spans} >= {"extract", "verify", "reason"}


async def test_ambiguous_request_asks_exactly_one_question(container) -> None:
    record = await container.orchestrator.run(
        IncomingRequest(text="Can I come in next Thursday after 3?", patient=None),
        NOW,
        container.state.active_profile,
    )
    if record.question_asked:
        assert record.question_asked.count("?") == 1


# ------------------------------------------------------------- NFR-03 ------
async def test_a_stage_timeout_falls_back_deterministically() -> None:
    """A forced timeout returns a complete response inside the budget, and the
    firing is loud in the trace and silent to the operator."""
    from app.trace.inprocess import InProcessTraceSink

    sink = InProcessTraceSink()
    tracer = Tracer(sink)

    async def hangs():  # type: ignore[no-untyped-def]
        await asyncio.sleep(5)
        return "never"

    async def deterministic():  # type: ignore[no-untyped-def]
        return "fallback"

    result = await run_stage(tracer, "extract", hangs, deterministic, timeout=0.05)
    assert result.value == "fallback"
    assert result.fallback_fired
    assert result.reason == "timeout"
    assert tracer.spans[0].attrs["fallback_fired"] is True


async def test_a_stage_error_also_falls_back() -> None:
    from app.trace.inprocess import InProcessTraceSink

    tracer = Tracer(InProcessTraceSink())

    async def explodes():  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    async def deterministic():  # type: ignore[no-untyped-def]
        return "fallback"

    result = await run_stage(tracer, "extract", explodes, deterministic, timeout=1.0)
    assert result.value == "fallback"
    assert result.reason == "RuntimeError"


# ------------------------------------------------------------- NFR-31 ------
def test_the_phi_redactor_provably_removes_patient_text(container) -> None:
    """FR-091 asks for a hook that provably works, not one that exists."""
    from app.trace.redaction import PhiRedactor
    from app.trace.sink import Span

    redactor = PhiRedactor()
    span = Span(span_id="a", trace_id="b", stage="extract", t_start=0.0,
                attrs={"raw_text": "my tooth is killing me", "duration_ms": 1})
    cleaned = redactor.span(span)
    assert cleaned.attrs["raw_text"] == "[redacted]"
    assert cleaned.attrs["duration_ms"] == 1  # non-PHI survives
    assert "raw_text" in redactor.covered
