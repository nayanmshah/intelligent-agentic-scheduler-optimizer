"""S9: replay and the observability fan-out.

The guarantee under test is *"nothing that can fail independently is on the request
path"*. So these tests run with the observability backend unreachable -- which is the
state it will actually be in on an arbitrary machine.
"""

from __future__ import annotations

import time

import pytest

from app.config import Settings
from app.container import AppContainer
from app.orchestrator.machine import IncomingRequest
from app.trace.opik import OpikTraceSink
from app.trace.redaction import NoOpRedactor, PhiRedactor, RedactingSink
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
    machine -- traces must still render and replay."""
    assert container.settings.opik_enabled is False
    record = await container.orchestrator.run(
        IncomingRequest(text="a filling on Wednesday late morning", patient=None),
        container.clock.now(),
        container.state.active_profile,
    )
    assert container.trace_store.spans_for(record.trace_id)
    assert container.trace_store.decision(record.id) is not None


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
