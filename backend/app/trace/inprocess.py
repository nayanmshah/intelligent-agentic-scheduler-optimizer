"""The always-on leg, and the sole data source for replay (FR-087).

Never put a container on the request path of a system that has to work on an
arbitrary machine. With the container runtime stopped, traces render and replay
normally -- that is verified, not assumed.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.trace.sink import Span


@dataclass
class InProcessTraceSink:
    """Bounded, so a long evaluation session cannot grow without limit (FR-091's
    retention half). Traces deliberately survive a session reset (FR-072)."""

    max_decisions: int = 500
    spans: dict[str, list[Span]] = field(default_factory=dict)
    decisions: deque = field(default_factory=lambda: deque(maxlen=500))

    def emit(self, span: Span) -> None:
        self.spans.setdefault(span.trace_id, []).append(span)

    def record_decision(self, record: Any) -> None:
        self.decisions.append(record)

    # -- read -----------------------------------------------------------------
    def spans_for(self, trace_id: str) -> list[Span]:
        return list(self.spans.get(trace_id, []))

    def decision(self, decision_id: str) -> Any | None:
        return next((d for d in self.decisions if getattr(d, "id", None) == decision_id), None)

    def latest(self, n: int = 20) -> list[Any]:
        return list(self.decisions)[-n:][::-1]

    def clear_traces(self) -> None:
        """A separate, explicitly-labelled action -- reset does not do this (FR-072).
        An evaluator will want to reset the schedule and still inspect a decision made
        before the reset; coupling them would destroy the audit trail on every reset."""
        self.spans.clear()
        self.decisions.clear()
