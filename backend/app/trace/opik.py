"""The Opik leg. Best effort, bounded, and **never on the request path**.

[FR-089] Emission is fire-and-forget behind a bounded queue drained by one daemon
thread. A full queue drops and counts; any exception counts and is swallowed. There
is no retry, because a retry on the request path is exactly the thing that would let
an observability backend slow down a patient-facing answer.

**Shape.** One Opik *trace* per decision, with one child *span* per pipeline stage --
not a flat trace per span, which is what this did first and which threw away the only
structure worth looking at. Stages that called a model are typed ``llm`` and carry the
model id, so Opik's own cost and latency views work without being told anything extra.

Spans close before the decision does, so they are buffered by ``trace_id`` and flushed
when the decision arrives. The buffer is capped: an abandoned request must not retain
spans forever.

This is the only module in the codebase permitted to import the Opik SDK -- a grep
test asserts it (FR-085).
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.trace.sink import Span

#: Stages that call a model. Typed ``llm`` in Opik so its cost/latency views light up.
_LLM_STAGES = {"extract", "verify", "explain"}

#: Opik keys its price table on (provider, model). Every model call here goes to the
#: Anthropic API directly -- not Bedrock or Vertex, which are separate providers at
#: different prices -- so this is a fact about the client, not a default.
_PROVIDER = "anthropic"

#: Fallback only: used when a stage has not been taught to summarise its own
#: payloads. Real input/output comes from ``app.trace.payloads``.
_STAGE_DESCRIPTIONS = {
    "extract": "patient's words -> typed constraints with source spans",
    "verify": "checks the reading against the world; never sees the schedule",
    "reason": "deterministic: enumerate, filter, score, rank",
    "explain": "scorer facts -> one sentence per offer, behind the faithfulness gate",
}


@dataclass
class OpikCounters:
    emitted: int = 0
    dropped: int = 0
    failed: int = 0
    unavailable: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "emitted": self.emitted,
            "dropped": self.dropped,
            "failed": self.failed,
            "unavailable": self.unavailable,
        }


class OpikTraceSink:
    """Wrap with ``RedactingSink`` -- observability is a PHI leak vector [AR-06]."""

    def __init__(
        self,
        url: str,
        enabled: bool,
        maxsize: int = 1000,
        project: str = "dental-scheduler",
        max_pending_traces: int = 64,
    ) -> None:
        self.url = url
        self.enabled = enabled
        self.project = project
        self.counters = OpikCounters()
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=maxsize)
        self._client: Any = None
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._pending: dict[str, list[Span]] = {}
        self._max_pending = max_pending_traces
        if enabled:
            self._start()

    # -- the request path touches only this ------------------------------------
    def emit(self, span: Span) -> None:
        self._offer(("span", span))

    def record_decision(self, record: Any) -> None:
        self._offer(("decision", record))

    def _offer(self, item: tuple[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            # Dropping is correct. Blocking here would put an optional backend on a
            # patient-facing path; the count is reported on the scorecard (FR-101).
            self.counters.dropped += 1

    # -- everything below runs on the worker thread ----------------------------
    def _start(self) -> None:
        self._worker = threading.Thread(target=self._drain, name="opik-sink", daemon=True)
        self._worker.start()

    def _connect(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import opik

            # The SDK wants the API root, not the UI root. Accepting either and
            # normalising here means a reader can put the address they see in the
            # browser into .env and have it work.
            host = self.url.rstrip("/")
            if not host.endswith("/api"):
                host = f"{host}/api"
            self._client = opik.Opik(host=host, project_name=self.project)
        except Exception:
            self.counters.unavailable += 1
            self._client = False  # remember the failure; do not retry per item
        return self._client

    def _drain(self) -> None:
        while not self._stop.is_set():
            try:
                kind, payload = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                if kind == "span":
                    self._buffer(payload)
                    continue
                client = self._connect()
                if not client:
                    self.counters.unavailable += 1
                    self._pending.pop(getattr(payload, "trace_id", ""), None)
                    continue
                self._flush_decision(client, payload)
                self.counters.emitted += 1
            except Exception:
                # Counted and swallowed. A failing sink must never surface to a user.
                self.counters.failed += 1

    def _buffer(self, span: Span) -> None:
        self._pending.setdefault(span.trace_id, []).append(span)
        # A request that errors before recording a decision would otherwise pin its
        # spans forever. Oldest-first eviction keeps this bounded without a timer.
        while len(self._pending) > self._max_pending:
            self._pending.pop(next(iter(self._pending)))
            self.counters.dropped += 1

    def _flush_decision(self, client: Any, record: Any) -> None:
        """One trace, one child span per stage, wall-clock times reconstructed.

        ``Span`` measures with ``perf_counter`` -- a duration, not a clock reading,
        deliberately (a clock read would be a determinism hazard, FR-102). Opik wants
        absolute times, so they are reconstructed backwards from *now* using the
        measured durations. The offsets are exact; only the origin is approximate,
        which is the right trade for a display timeline.
        """
        spans = sorted(self._pending.pop(record.trace_id, []), key=lambda s: s.t_start)
        total_s = sum(s.duration_ms for s in spans) / 1000.0
        finished = datetime.now(UTC)
        origin = finished - timedelta(seconds=total_s)

        offers = list(getattr(record, "offers", ()) or ())
        trace = client.trace(
            name="scheduling-decision",
            start_time=origin,
            end_time=finished,
            input={"request": getattr(record, "raw_text", "")},
            output={
                "offers": [
                    {
                        "when": f"{o.weekday} {o.date_display} {o.start_display}",
                        "provider": o.provider_name,
                        "reason": o.reason,
                        "score": o.score,
                    }
                    for o in offers
                ],
                "question": getattr(record, "question_asked", None),
                "flags": list(getattr(record, "flags", ()) or ()),
            },
            metadata=_decision_metadata(record),
            tags=_decision_tags(record),
        )

        cursor = origin
        for s in spans:
            end = cursor + timedelta(milliseconds=s.duration_ms)
            attrs = dict(s.attrs)
            # The stage's real payloads (see app.trace.payloads). An "input" that
            # describes the stage and an "output" naming the implementation are a
            # label and a config value -- not input and output. The descriptions
            # below are a fallback for any stage not yet taught to summarise itself.
            span_in = attrs.pop("input", None) or {
                "stage": _STAGE_DESCRIPTIONS.get(s.stage, s.stage)
            }
            span_out = attrs.pop("output", None) or {
                "implementation": attrs.get("implementation")
            }
            # Cost is f(provider, model, usage). Sending the model alone -- which is
            # what this did first -- yields a confident $0 on every span. The provider
            # is named only when tokens were actually spent, so a stage that fell back
            # to the deterministic path is not labelled as a model call that cost
            # nothing.
            span_usage = attrs.pop("usage", None)
            # start_time and end_time are supplied at creation, so no .end() call is
            # needed -- and calling it here would risk the batcher shipping an update
            # for a span it has not yet created (the SDK warns about exactly this).
            trace.span(
                name=s.stage,
                type="llm" if s.stage in _LLM_STAGES else "general",
                start_time=cursor,
                end_time=end,
                model=attrs.get("model"),
                provider=_PROVIDER if span_usage else None,
                usage=span_usage,
                input=span_in,
                output=span_out,
                metadata={"duration_ms": round(s.duration_ms, 1), **attrs},
            )
            cursor = end

    def close(self, timeout: float = 1.0) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=timeout)
        if self._client:
            try:
                self._client.flush()
            except Exception:
                self.counters.failed += 1

    def flush(self) -> None:
        """Drain to Opik now. For CLI and eval runs, which exit before the daemon
        thread would otherwise get there."""
        deadline = 40
        while deadline and not self._queue.empty():
            threading.Event().wait(0.05)
            deadline -= 1
        if self._client:
            try:
                self._client.flush()
            except Exception:
                self.counters.failed += 1

    @property
    def backlog(self) -> int:
        return self._queue.qsize()


def _decision_metadata(record: Any) -> dict[str, Any]:
    funnel = getattr(record, "funnel", None)
    return {
        "decision_id": getattr(record, "id", ""),
        "origin_state": getattr(getattr(record, "origin_state", None), "value", None),
        "llm_calls": getattr(record, "llm_calls", 0),
        "gate_fired": getattr(record, "gate_fired_count", 0),
        "weight_profile": getattr(record, "weight_profile_id", None),
        "limited_availability": getattr(record, "limited_availability", False),
        # The funnel is the product's "did it miss anything?" answer, so it belongs
        # on the trace rather than only on screen.
        "funnel": {
            "grid_slots": getattr(funnel, "grid_slots", None),
            "enumerated": getattr(funnel, "enumerated", None),
            "feasible": getattr(funnel, "feasible", None),
            "in_tier": getattr(funnel, "in_tier", None),
            "offered": getattr(funnel, "offered", None),
        }
        if funnel
        else None,
    }


def _decision_tags(record: Any) -> list[str]:
    """Tags are what make the Opik trace list filterable, so they name the things
    worth filtering on: degradation, gate firings, and asking a question."""
    tags = []
    for stage in getattr(record, "fallback_fired", ()) or ():
        tags.append(f"fallback:{stage}")
    if getattr(record, "gate_fired_count", 0):
        tags.append("gate-fired")
    if getattr(record, "question_asked", None):
        tags.append("asked-a-question")
    if getattr(record, "limited_availability", False):
        tags.append("limited-availability")
    if getattr(record, "source", "text") == "voice":
        # Filterable, so "did the dictated ones go worse?" is a click (FR-110).
        tags.append("source:voice")
    state = getattr(getattr(record, "origin_state", None), "value", None)
    if state:
        tags.append(state)
    return tags
