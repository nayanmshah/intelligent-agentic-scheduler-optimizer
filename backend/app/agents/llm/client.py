"""Anthropic client wiring.

Three details that are easy to get wrong and expensive to debug:

* **``max_retries=0``.** The SDK retries timeouts by default, so wall-clock can reach
  ``timeout x (max_retries + 1)``. The orchestrator owns retry and fallback, so the
  per-stage budget has to mean what it says (§15.4).
* **No ``temperature``** [AR-01]. Current models reject sampling parameters with a
  400. Determinism was never carried by temperature anyway -- it comes from committed
  fixtures being the default and from ranking being a pure function of the extraction.
* **Thinking is set explicitly** [AR-02]. It is on by default and shares the
  ``max_tokens`` budget with the response, so an unset value risks truncation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.trace import usage as usage_trace


def _supports_effort(model: str) -> bool:
    """Claude 4.6+ Opus/Sonnet/Fable take `effort` + adaptive thinking; Haiku 4.5
    rejects both with a 400. Capability keyed on the family, not a version list,
    so a model id bump does not silently start failing every call."""
    return not model.startswith("claude-haiku")


class LlmUnavailable(RuntimeError):
    """Raised so the orchestrator's fallback ladder handles it like any other
    stage failure. The operator sees nothing; the trace records it."""


class LlmRefused(RuntimeError):
    """[AR-08] A successful HTTP 200 carrying ``stop_reason == "refusal"``.

    Content may be empty or partial, so reading ``content[0]`` unconditionally would
    raise. A patient describing a symptom is exactly the sort of text a classifier
    might look twice at, so this is a real path, not a theoretical one.
    """


@dataclass
class LlmClient:
    settings: Settings

    def __post_init__(self) -> None:
        self._client: Any = None
        #: Real calls made. Surfaced per decision so "did the model run?" is a number
        #: on the trace rather than an inference from the prose style.
        self.calls = 0

    async def aclose(self) -> None:
        """Release the HTTP connection pool.

        The SDK keeps sockets open between calls, which is what makes the second
        request fast -- and what leaks a file descriptor per client if nobody closes
        it. Harmless in a short script; in a server that rebuilds a registry it is an
        fd leak with a long fuse.
        """
        client, self._client = self._client, None
        if client is not None:
            await client.close()

    def _ensure(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.settings.has_api_key:
            raise LlmUnavailable("ANTHROPIC_API_KEY is not set")
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise LlmUnavailable("anthropic SDK not installed") from exc
        self._client = AsyncAnthropic(
            api_key=self.settings.anthropic_api_key,
            max_retries=0,  # the orchestrator owns retry; see module docstring
        )
        return self._client

    async def structured(
        self, *, model: str, system: str, user: str, schema: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        """One call, JSON-schema constrained, validated by the caller.

        ``output_config`` carries both the schema and the effort level, which is why
        the SDK's convenience parse helper is not used -- and owning the
        validation-failure branch is the point, because that branch *is* the error
        ladder (§15.5).
        """
        client = self._ensure()
        s = self.settings
        self.calls += 1
        # Haiku rejects both `thinking` and `effort` with a 400. Measured before
        # being dropped, not assumed away: adaptive thinking moved extraction p50 by
        # under 0.2s on Opus, so nothing of value is lost on models without it.
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": s.llm_max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
            "messages": [{"role": "user", "content": user}],
        }
        if _supports_effort(model):
            kwargs["output_config"]["effort"] = s.llm_effort
            kwargs["thinking"] = {"type": "adaptive"}
        try:
            response = await client.with_options(timeout=timeout).messages.create(**kwargs)
        except Exception as exc:
            raise LlmUnavailable(str(exc)) from exc

        # Before the refusal and parse branches below, both of which raise: a refused
        # or malformed response is still a billed response, and a cost view that
        # counted only the successes would understate exactly the runs worth costing.
        usage_trace.record(usage_trace.LlmUsage.from_response(getattr(response, "usage", None)))

        if getattr(response, "stop_reason", None) == "refusal":
            raise LlmRefused(getattr(getattr(response, "stop_details", None), "category", ""))

        text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), None)
        if not text:
            raise LlmUnavailable("no text content in response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LlmUnavailable(f"malformed JSON: {exc}") from exc

    async def sentences(
        self, *, model: str, system: str, user: str, timeout: float, count: int
    ) -> list[str]:
        """One batched call for all three cards (ADR-09). Three sequential calls
        would triple tail latency on the most visible surface; three parallel calls
        would triple the failure surface for no quality gain."""
        self.calls += 1
        schema = {
            "type": "object",
            "properties": {
                "sentences": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["sentences"],
            "additionalProperties": False,
        }
        payload = await self.structured(
            model=model, system=system, user=user, schema=schema, timeout=timeout
        )
        out = list(payload.get("sentences", []))[:count]
        if len(out) != count:
            raise LlmUnavailable(f"expected {count} sentences, got {len(out)}")
        return out
