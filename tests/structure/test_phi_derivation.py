"""[NFR-31] The redactor is derived from the model, and this test is the requirement.

It adds a *new* PHI-marked field to a synthetic type and asserts coverage without
touching any redactor code. If somebody replaces the derivation with a hand-written
list of field names, this test fails -- which is the only way to stop that list from
silently going stale the first time a field is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from app.domain.decision import DecisionRecord
from app.domain.phi import PHI, phi_fields, phi_paths
from app.domain.request import RequestConstraints, SourceSpan


def test_known_phi_fields_are_marked() -> None:
    assert "raw_text" in phi_fields(DecisionRecord)
    assert "constraints" in phi_fields(DecisionRecord)
    assert "request_text" in phi_fields(RequestConstraints)
    # The span text is a verbatim substring of the request, so it inherits its status.
    assert "text" in phi_fields(SourceSpan)


def test_nested_phi_is_reachable() -> None:
    """A redactor that only handles the top level leaks everything underneath."""
    paths = phi_paths(DecisionRecord)
    assert "raw_text" in paths
    assert any(p.startswith("constraints.") for p in paths), (
        "nested PHI under DecisionRecord.constraints was not discovered -- "
        "a top-level-only redactor would leak the request text and its spans"
    )


def test_a_newly_added_field_is_covered_with_no_redactor_change() -> None:
    @dataclass
    class LaterAddition:
        harmless: str
        chief_complaint: Annotated[str, PHI]

    assert phi_fields(LaterAddition) == {"chief_complaint"}


def test_unmarked_fields_are_not_swept_up() -> None:
    """Over-redaction is its own failure: it would blank the fields replay needs."""
    assert "trace_id" not in phi_fields(DecisionRecord)
    assert "weight_profile_id" not in phi_fields(DecisionRecord)
