"""[FR-085] One instrumentation abstraction, fanning out.

No observability SDK call appears anywhere outside ``trace/`` -- asserted by a grep
test. The in-process leg is always on and synchronous (a list append, microseconds);
the Opik leg is a bounded queue drained by one daemon thread, and its failures are
counted and swallowed. Nothing that can fail independently sits on the request path.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Span:
    span_id: str
    trace_id: str
    stage: str
    t_start: float
    t_end: float | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return ((self.t_end or self.t_start) - self.t_start) * 1000.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "stage": self.stage,
            "duration_ms": round(self.duration_ms, 3),
            **self.attrs,
        }


@runtime_checkable
class TraceSink(Protocol):
    def emit(self, span: Span) -> None: ...
    def record_decision(self, record: Any) -> None: ...


class NullTraceSink:
    def emit(self, span: Span) -> None: ...
    def record_decision(self, record: Any) -> None: ...


class FanOutTraceSink:
    """In-process first and synchronous; everything else best-effort."""

    def __init__(self, *sinks: TraceSink) -> None:
        self._sinks = sinks

    def emit(self, span: Span) -> None:
        for s in self._sinks:
            # A sink must never be the reason a request fails.
            with contextlib.suppress(Exception):
                s.emit(span)

    def record_decision(self, record: Any) -> None:
        for s in self._sinks:
            with contextlib.suppress(Exception):
                s.record_decision(record)


class Tracer:
    """The handle the orchestrator holds. Owns trace identity and span timing.

    Timing uses ``time.perf_counter``, which is a duration measurement rather than a
    clock reading -- it cannot resolve a date and so cannot make output
    non-reproducible. The structural guard permits it for exactly that reason.
    """

    def __init__(self, sink: TraceSink, trace_id: str | None = None) -> None:
        self.sink = sink
        self.trace_id = trace_id or uuid.uuid4().hex[:16]
        self.spans: list[Span] = []

    @contextmanager
    def span(self, stage: str, **attrs: Any) -> Iterator[Span]:
        s = Span(
            span_id=uuid.uuid4().hex[:12],
            trace_id=self.trace_id,
            stage=stage,
            t_start=time.perf_counter(),
            attrs=dict(attrs),
        )
        try:
            yield s
        finally:
            s.t_end = time.perf_counter()
            self.spans.append(s)
            self.sink.emit(s)

    def total_ms(self) -> float:
        return sum(s.duration_ms for s in self.spans)
