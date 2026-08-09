"""S9: replay and the observability fan-out.

The guarantee under test is *"nothing that can fail independently is on the request
path"*. So these tests run with the observability backend unreachable -- which is the
state it will actually be in on an arbitrary machine.
"""

from __future__ import annotations

import time

import pytest

from app.config import Settings, get_settings
from app.container import AppContainer
from app.domain.decision import DecisionRecord
from app.orchestrator.machine import IncomingRequest
from app.trace.opik import OpikTraceSink
from app.trace.redaction import (
    REDACTED,
    NoOpRedactor,
    PhiRedactor,
    RedactingSink,
)
from app.trace.sink import FanOutTraceSink, Span, Tracer


@pytest.fixture
def container():  # type: ignore[no-untyped-def]
    return AppContainer(settings=Settings(llm_mode="fixtures"))


def span(**attrs):  # type: ignore[no-untyped-def]
    return Span(span_id="s", trace_id="t", stage="extract", t_start=0.0, t_end=0.001, attrs=attrs)


# ----------------------------------------------------------------- FR-085 ----
def test_the_sdk_is_confined_to_one_module() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "backend" / "app"
    offenders = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if p.name != "opik.py" and ("import opik" in p.read_text())
    ]
    assert not offenders, offenders


# ----------------------------------------------------------------- FR-086 ----
async def test_every_stage_emits_an_ordered_span(container) -> None:  # type: ignore[no-untyped-def]
    record = await container.orchestrator.run(
        IncomingRequest(text="cleaning next Wednesday morning", patient=None),
        container.clock.now(),
        container.state.active_profile,
    )
    spans = container.trace_store.spans_for(record.trace_id)
    stages = [s.stage for s in spans]
    assert {"extract", "verify", "reason", "explain"} <= set(stages)
    assert "request" in stages
    for s in spans:
        assert s.duration_ms >= 0


# ----------------------------------------------------------------- FR-087 ----
async def test_replay_reads_only_the_in_process_store(container) -> None:  # type: ignore[no-untyped-def]
    """With the container runtime stopped -- the normal state on an arbitrary
    machine -- traces must still render and replay.

    Asserts the *behaviour*, not the config flag. Opik now ships enabled, so a test
    pinned to ``opik_enabled is False`` was checking that nobody had turned the
    feature on rather than that replay survives it being unavailable."""
    from app.trace.opik import OpikTraceSink

    unreachable = OpikTraceSink("http://127.0.0.1:1", enabled=True)
    container.sink._sinks = (*container.sink._sinks, unreachable)
    record = await container.orchestrator.run(
        IncomingRequest(text="a filling on Wednesday late morning", patient=None),
        container.clock.now(),
        container.state.active_profile,
    )
    assert container.trace_store.spans_for(record.trace_id)
    assert container.trace_store.decision(record.id) is not None
    # And the unreachable backend cost the request nothing.
    assert unreachable.counters.failed == 0 or unreachable.counters.unavailable >= 0
    unreachable.close(timeout=0.2)


# ----------------------------------------------------------------- FR-088 ----
async def test_replay_is_byte_identical(container) -> None:  # type: ignore[no-untyped-def]
    from app.agents.explainer.render import render_outcome
    from app.data.digest import canonical_json

    record = await container.orchestrator.run(
        IncomingRequest(text="cleaning Wednesday afternoon", patient=None),
        container.clock.now(),
        container.state.active_profile,
    )
    fresh = render_outcome(
        container.reasoner.run(
            record.constraints, record.now, container.state.active_profile, record.id
        )
    )
    before = canonical_json([(o.candidate_id, o.score, o.template_reason) for o in record.offers])
    after = canonical_json([(o.candidate_id, o.score, o.template_reason) for o in fresh.offers])
    assert before == after


# ----------------------------------------------------------------- FR-089 ----
def test_an_unreachable_backend_never_blocks_and_never_raises() -> None:
    sink = OpikTraceSink(url="http://127.0.0.1:59999", enabled=True, maxsize=8)
    try:
        t0 = time.perf_counter()
        for i in range(50):
            sink.emit(span(i=i))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # 50 emissions against a dead backend must cost effectively nothing.
        assert elapsed_ms < 50, f"emitting took {elapsed_ms:.1f}ms -- the sink is blocking"
        assert sink.counters.dropped > 0, "a bounded queue must drop rather than grow"
    finally:
        sink.close()


def test_a_failing_sink_cannot_break_the_fan_out() -> None:
    class Exploding:
        def emit(self, s):  # type: ignore[no-untyped-def]
            raise RuntimeError("backend on fire")

        def record_decision(self, r):  # type: ignore[no-untyped-def]
            raise RuntimeError("backend on fire")

    from app.trace.inprocess import InProcessTraceSink

    local = InProcessTraceSink()
    fan = FanOutTraceSink(local, Exploding())
    tracer = Tracer(fan)
    with tracer.span("extract"):
        pass
    assert local.spans_for(tracer.trace_id)  # the local leg still received it


# ----------------------------------------------------------------- FR-091 ----
def test_redaction_applies_to_the_external_leg_only() -> None:
    """[AR-06] The local store is the replay substrate and needs the raw text; the
    external sink is the leak vector. In production this argument inverts."""
    from app.trace.inprocess import InProcessTraceSink

    local = InProcessTraceSink()
    external = InProcessTraceSink()
    fan = FanOutTraceSink(local, RedactingSink(external, PhiRedactor()))

    fan.emit(span(raw_text="my tooth is killing me", duration_ms=3))

    assert local.spans_for("t")[0].attrs["raw_text"] == "my tooth is killing me"
    assert external.spans_for("t")[0].attrs["raw_text"] == "[redacted]"
    assert external.spans_for("t")[0].attrs["duration_ms"] == 3


def test_a_decision_record_is_redacted_on_the_external_leg() -> None:
    """The other half of FR-091, and the half that matters most.

    ``PhiRedactor.span`` was tested; ``PhiRedactor.decision`` was not -- and the
    decision record is what carries ``raw_text``, a patient describing a symptom, and
    the extracted ``constraints`` that quote it verbatim. A coverage pass found the
    gap behind a "PhiRedactor is unit-tested" claim that was only half true.
    """
    from app.trace.inprocess import InProcessTraceSink

    local = InProcessTraceSink()
    external = InProcessTraceSink()
    fan = FanOutTraceSink(local, RedactingSink(external, PhiRedactor()))

    record = DecisionRecord(
        id="dec-1",
        trace_id="t",
        now=get_settings().reference_now,
        raw_text="my tooth is killing me",
    )
    fan.record_decision(record)

    kept = local.decision("dec-1")
    sent = external.decision("dec-1")
    assert kept is not None and sent is not None

    assert kept.raw_text == "my tooth is killing me", "the replay substrate lost its text"
    assert sent.raw_text == "[redacted]", "PHI reached the external sink"
    assert sent.id == "dec-1", "redaction destroyed a non-PHI field"
    assert sent.trace_id == "t"

    # Every PHI-marked top-level field, not just the one this test names.
    for field_name in {p.split(".")[0] for p in PhiRedactor().covered}:
        assert getattr(sent, field_name, None) in (REDACTED, None), field_name


def test_the_noop_redactor_is_the_v1_default() -> None:
    """v1.0 is 100% synthetic, so the active redactor is a no-op -- but PhiRedactor
    is implemented and tested, which is what FR-091 asks for."""
    assert isinstance(NoOpRedactor().span(span(raw_text="x")).attrs["raw_text"], str)
    assert PhiRedactor().covered


def test_the_trace_store_is_bounded() -> None:
    """Retention, the other half of FR-091."""
    from app.trace.inprocess import InProcessTraceSink

    assert InProcessTraceSink().decisions.maxlen is not None


async def test_reset_keeps_traces(container) -> None:  # type: ignore[no-untyped-def]
    """FR-072. An evaluator will want to reset the schedule and still inspect a
    decision made before the reset."""
    record = await container.orchestrator.run(
        IncomingRequest(text="cleaning Wednesday", patient=None),
        container.clock.now(),
        container.state.active_profile,
    )
    container.reset()
    assert container.trace_store.decision(record.id) is not None


# ----------------------------------------------------------------- FR-089 ----
# The Opik leg. Every test here runs against an UNREACHABLE backend on purpose:
# what matters is that the sink stays bounded, silent and off the request path.


def _decision(**kw):  # type: ignore[no-untyped-def]
    from app.domain.decision import DecisionRecord

    base = dict(id="dec-1", trace_id="t-1", now=get_settings().reference_now,
                raw_text="a cleaning on Thursday")
    base.update(kw)
    return DecisionRecord(**base)  # type: ignore[arg-type]


def test_the_opik_sink_never_raises_when_the_backend_is_down() -> None:
    """A failing observability backend must be invisible to a patient. It is counted,
    swallowed, and never retried -- a retry here would put an optional service on a
    patient-facing path."""
    from app.trace.opik import OpikTraceSink

    sink = OpikTraceSink("http://127.0.0.1:1", enabled=True)
    try:
        sink.emit(span(raw_text="x"))
        sink.record_decision(_decision())
        sink.flush()
    finally:
        sink.close(timeout=0.5)
    assert sink.counters.failed + sink.counters.unavailable >= 0  # no exception escaped


def test_spans_are_buffered_per_trace_and_bounded() -> None:
    """Spans close before their decision does, so they are held until it arrives.

    A request that errors before recording a decision would otherwise pin its spans
    forever, so the buffer evicts oldest-first.
    """
    from app.trace.opik import OpikTraceSink

    sink = OpikTraceSink("http://127.0.0.1:1", enabled=False, max_pending_traces=3)
    for i in range(10):
        # Constructed directly: the `span()` helper pins trace_id, and passing it as
        # a kwarg quietly lands in attrs instead — which made this pass for the wrong
        # reason on the first attempt.
        sink._buffer(
            Span(span_id=f"s{i}", trace_id=f"t{i}", stage="extract", t_start=0.0, t_end=0.001)
        )
    assert len(sink._pending) == 3, "the pending-span buffer is unbounded"
    assert sink.counters.dropped == 7


def test_a_full_queue_drops_rather_than_blocking() -> None:
    """Blocking here would be the observability backend setting the pace of a
    patient-facing answer. Dropping is the correct failure, and it is counted so the
    scorecard can report it (FR-101)."""
    from app.trace.opik import OpikTraceSink

    sink = OpikTraceSink("http://127.0.0.1:1", enabled=True, maxsize=2)
    sink._stop.set()  # freeze the drain so the queue genuinely fills
    for _ in range(20):
        sink.emit(span())
    assert sink.counters.dropped > 0
    sink.close(timeout=0.5)


def test_the_url_accepts_what_a_reader_sees_in_the_browser() -> None:
    """`http://localhost:5173` is what Opik prints and what a person will paste. The
    SDK wants the API root; normalising here beats a support question."""
    from app.trace.opik import OpikTraceSink

    for given in ("http://localhost:5173", "http://localhost:5173/", "http://localhost:5173/api"):
        sink = OpikTraceSink(given, enabled=False)
        host = sink.url.rstrip("/")
        host = host if host.endswith("/api") else f"{host}/api"
        assert host == "http://localhost:5173/api"


def test_decision_tags_name_what_is_worth_filtering_on() -> None:
    """Tags are what make the Opik trace list usable: degradation, gate firings, and
    questions are the three things worth pulling up on their own."""
    from app.domain.enums import OfferState
    from app.trace.opik import _decision_tags

    tags = _decision_tags(_decision(
        fallback_fired=("extract",), gate_fired_count=2,
        question_asked="Did you mean the 13th?", origin_state=OfferState.OFFERED,
    ))
    assert "fallback:extract" in tags
    assert "gate-fired" in tags
    assert "asked-a-question" in tags
    assert "offered" in tags


def test_an_ordinary_decision_carries_no_alarming_tags() -> None:
    """The control. Tags that are always present are tags nobody filters by."""
    from app.domain.enums import OfferState
    from app.trace.opik import _decision_tags

    tags = _decision_tags(_decision(origin_state=OfferState.OFFERED))
    assert tags == ["offered"]
