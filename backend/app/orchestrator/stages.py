"""The single place a timeout, a fallback, and a span exist.

Every per-stage timeout, every ``fallback_fired`` and every ``gate_fired`` in the
system passes through these ~30 lines (NFR-03, NFR-16). That is why "what happens
when the LLM is slow?" has one answer and one place to read it -- and why the
orchestrator itself stays under 150 lines.

Degradation is **silent to the operator and loud in the trace**. The operator never
sees an error; the trace panel shows the firing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.trace.sink import Tracer


@dataclass(frozen=True, slots=True)
class StageResult:
    value: Any
    fallback_fired: bool
    reason: str | None


async def run_stage[T](
    tracer: Tracer,
    name: str,
    primary: Callable[[], Awaitable[T]],
    fallback: Callable[[], Awaitable[T]] | None,
    timeout: float,
    describe: Callable[[T], Any] | None = None,
    **attrs: Any,
) -> StageResult:
    """Try the primary within its budget; fall back deterministically on any failure.

    The failure modes are collapsed on purpose: a timeout, a malformed response, a
    refusal and a connection error all mean the same thing to the operator -- the
    request still needs answering -- and all mean the same thing to the trace: the
    deterministic path ran instead.

    ``describe`` turns the stage's result into the span's ``output``. Without it a
    span records only *that* a stage ran; with it, the trace shows what the stage
    produced -- which is the only reason to open one.
    """
    with tracer.span(name, **attrs) as span:

        def record(value: T) -> T:
            if describe is not None:
                span.attrs["output"] = describe(value)
            return value

        if fallback is None:
            span.attrs["fallback_fired"] = False
            return StageResult(record(await primary()), False, None)
        try:
            value = await asyncio.wait_for(primary(), timeout=timeout)
            span.attrs["fallback_fired"] = False
            return StageResult(record(value), False, None)
        except TimeoutError:
            reason = "timeout"
        except Exception as exc:
            reason = type(exc).__name__

        span.attrs["fallback_fired"] = True
        span.attrs["fallback_reason"] = reason
        return StageResult(record(await fallback()), True, reason)
