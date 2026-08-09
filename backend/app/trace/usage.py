"""[FR-085] Token counts, carried from the model client to the span that owns them.

Opik prices a span as a function of ``(provider, model, usage)``. The model id was
already on the span and the provider is implied, but the token counts were not sent
at all -- so every LLM span priced at exactly $0. That is a missing field wearing the
costume of an answer, which is worse than a blank, and it is the whole bug.

**Why a ContextVar rather than a return value.** Usage is billing data; it belongs to
the span, not to the stage's result. Threading it back would mean widening
``extract -> ExtractionPayload -> RequestConstraints`` and the verifier and explainer
equivalents -- three return types that have nothing to do with cost -- so that the
orchestrator could copy a number onto a span it already holds. The span instead
publishes a collector and the client appends to it.

**Why it survives ``asyncio``.** Every LLM stage runs under ``asyncio.wait_for``, and
one runs under ``create_task``. A task gets a *copy* of the context, so rebinding the
var inside a task would not propagate out -- but the bound value here is a list, and
the copy holds the same list. Appends are seen by the span that opened it.

Nesting is the behaviour we want, not a hazard: the ``request`` span wraps the stage
spans, and a stage's collector shadows it, so tokens are attributed to ``extract`` and
never counted twice on its parent.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

#: The span currently accepting usage, or None outside any span.
_active: contextvars.ContextVar[list[LlmUsage] | None] = contextvars.ContextVar(
    "opik_llm_usage", default=None
)


@dataclass(frozen=True)
class LlmUsage:
    """One model call's billed tokens, in Anthropic's own field names.

    Kept in the provider's vocabulary rather than normalised to OpenAI's because
    Opik recognises the original format when ``provider`` is set, and the cache
    fields have no OpenAI equivalent -- normalising early would silently drop the
    part of the bill this codebase works hardest to reduce.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @classmethod
    def from_response(cls, usage: Any) -> LlmUsage | None:
        """Read the SDK's usage object defensively.

        Fields appear and are renamed across SDK versions, and a trace is never worth
        an exception on the request path, so anything unreadable becomes a zero.
        """
        if usage is None:
            return None

        def n(name: str) -> int:
            value = getattr(usage, name, 0)
            return value if isinstance(value, int) else 0

        return cls(
            input_tokens=n("input_tokens"),
            output_tokens=n("output_tokens"),
            cache_creation_input_tokens=n("cache_creation_input_tokens"),
            cache_read_input_tokens=n("cache_read_input_tokens"),
        )


def record(usage: LlmUsage | None) -> None:
    """Attribute a call's tokens to the enclosing span. A no-op outside one."""
    if usage is None:
        return
    bucket = _active.get()
    if bucket is not None:
        bucket.append(usage)


@contextmanager
def collecting(bucket: list[LlmUsage]) -> Iterator[None]:
    token = _active.set(bucket)
    try:
        yield
    finally:
        _active.reset(token)


def merge(calls: list[LlmUsage]) -> dict[str, int]:
    """Sum a stage's calls into one usage dict.

    A stage is usually one call, but the explainer's retry path can make two, and a
    span reporting only the last one would under-report the bill.

    ``prompt_tokens``/``completion_tokens``/``total_tokens`` are included alongside
    the Anthropic names because Opik shows token columns only for the OpenAI-shaped
    keys, and cost is computed from the provider-native ones. Sending both means the
    UI's numbers and the price calculation agree. Cache reads and writes are billed,
    so they count toward the prompt side.
    """
    totals = {
        "input_tokens": sum(c.input_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "cache_creation_input_tokens": sum(c.cache_creation_input_tokens for c in calls),
        "cache_read_input_tokens": sum(c.cache_read_input_tokens for c in calls),
    }
    prompt = (
        totals["input_tokens"]
        + totals["cache_creation_input_tokens"]
        + totals["cache_read_input_tokens"]
    )
    return {
        **totals,
        "prompt_tokens": prompt,
        "completion_tokens": totals["output_tokens"],
        "total_tokens": prompt + totals["output_tokens"],
    }
