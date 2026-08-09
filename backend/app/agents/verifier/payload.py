"""Wire model for verification, flat for the same reason extraction's is.

Structured outputs accept a subset of JSON Schema; the domain types use frozensets and
constrained fields that render keywords the API rejects. Keeping a separate wire shape
is cheaper than fighting the schema generator, and it keeps the domain model's
strictness intact -- see ``app.agents.extractor.payload`` for the full argument.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Flat(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FlagPayload(Flat):
    code: str  # SCREAMING_SNAKE, e.g. SYMPTOM_TYPE_MISMATCH
    message: str  # operator-facing, read aloud to a patient, <= 25 words


class QuestionPayload(Flat):
    field: str
    text: str
    chips: list[str]  # 2-3 concrete choices, never free text (FR-012)


class VerificationPayload(Flat):
    """What the model may return.

    Note what is *absent*: it cannot return constraints. The verifier may describe a
    problem and propose a question; it may not rewrite the extraction. That bound is
    enforced by the shape rather than by a prompt instruction.
    """

    flags: list[FlagPayload]
    question: QuestionPayload | None


def verdict_schema() -> dict:  # type: ignore[type-arg]
    return _tighten(VerificationPayload.model_json_schema())  # type: ignore[return-value]


def _tighten(node: object) -> object:
    if isinstance(node, dict):
        out = {k: _tighten(v) for k, v in node.items() if k not in _STRIP}
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = sorted(out["properties"])
        return out
    if isinstance(node, list):
        return [_tighten(v) for v in node]
    return node


_STRIP = frozenset({
    "uniqueItems", "prefixItems", "minItems", "maxItems", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength",
    "pattern", "default", "examples", "format",
})
