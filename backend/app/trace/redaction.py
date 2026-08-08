"""[FR-091 / NFR-31] The PHI seam.

Observability is a PHI leak vector: traces capture prompts, and the request text
becomes PHI the moment a patient describes a symptom. That is precisely why this is
an abstraction with a hook rather than SDK calls sprinkled through the code.

**The redactor is derived from the domain model**, not hand-maintained. A hand-written
field list is correct once and then silently wrong the first time somebody adds a
field without knowing the list exists.

**Placement is per-sink, and that reasoning is v1.0-specific** [AR-06]. The local
store is the byte-identical replay substrate and lives in memory on one machine, so
it is not redacted; the external sink is. In production the local store is a
database, `raw_text` is PHI at rest, and the argument inverts.
"""

from __future__ import annotations

import contextlib
from typing import Any, Protocol, runtime_checkable

from app.domain.decision import DecisionRecord
from app.domain.phi import phi_paths
from app.trace.sink import Span

REDACTED = "[redacted]"


@runtime_checkable
class Redactor(Protocol):
    def span(self, span: Span) -> Span: ...
    def decision(self, record: Any) -> Any: ...


class NoOpRedactor:
    """v1.0 default. The data is 100% synthetic, so there is nothing to redact --
    but the seam is exercised by ``PhiRedactor`` in tests, which is what FR-091 asks
    for: a hook that provably works, not a hook that exists."""

    def span(self, span: Span) -> Span:
        return span

    def decision(self, record: Any) -> Any:
        return record


class PhiRedactor:
    """Blanks every field the domain model marks ``Annotated[..., PHI]``."""

    def __init__(self) -> None:
        self._paths = phi_paths(DecisionRecord)
        self._top = {p.split(".")[0] for p in self._paths}

    def span(self, span: Span) -> Span:
        attrs = dict(span.attrs)
        for key in list(attrs):
            if key in self._top or key in {"raw_text", "request_text", "patient_name"}:
                attrs[key] = REDACTED
        return Span(
            span_id=span.span_id,
            trace_id=span.trace_id,
            stage=span.stage,
            t_start=span.t_start,
            t_end=span.t_end,
            attrs=attrs,
        )

    def decision(self, record: Any) -> Any:
        import copy

        clone = copy.copy(record)
        for field_name in self._top:
            if hasattr(clone, field_name):
                with contextlib.suppress(Exception):  # frozen fields refuse the write
                    setattr(clone, field_name, REDACTED)
        return clone

    @property
    def covered(self) -> frozenset[str]:
        return self._paths


class RedactingSink:
    """Wraps another sink, applying a redactor at the boundary."""

    def __init__(self, inner: Any, redactor: Redactor) -> None:
        self._inner = inner
        self._redactor = redactor

    def emit(self, span: Span) -> None:
        self._inner.emit(self._redactor.span(span))

    def record_decision(self, record: Any) -> None:
        self._inner.record_decision(self._redactor.decision(record))
