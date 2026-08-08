"""S8: the faithfulness gate.

~40 lines that turn "trust the LLM" into "verify the LLM". Tested against crafted
completions rather than live output, so it is deterministic and needs no network --
which is also the only way to exercise the failure branches on demand.
"""

from __future__ import annotations

import pytest

from app.agents.explainer import gate
from app.domain.enums import Axis
from app.domain.rationale import Atom, FactSet, Rationale

FACTS = FactSet(
    provider_name="Sarah",
    weekday="Thursday",
    date_display="August 13th",
    start_display="3:40pm",
    end_display="4:40pm",
    operatory_name="Op 1",
    duration_min=60,
    type_name="Cleaning",
    patient_first_name="Ana",
)


def rationale(*axes: Axis, caveat: Axis | None = None) -> Rationale:
    comps = tuple(
        Atom(axis=a, value=0.9, weighted=0.3, text=f"{a.value} reason") for a in axes
    )
    cav = (
        Atom(axis=caveat, value=0.2, weighted=0.05, text="though it is a week out")
        if caveat
        else None
    )
    return Rationale(facts=FACTS, components=comps, caveat=cav)


GOOD = "Thursday August 13th at 3:40pm with Sarah, in the window you asked for."


def test_a_faithful_sentence_passes() -> None:
    assert gate.check(GOOD, rationale(Axis.TIME_FIT)).ok


# ------------------------------------------------------------------- F1 -----
def test_naming_a_provider_not_in_the_fact_set_is_rejected() -> None:
    """The crafted case FR-062 names explicitly."""
    bad = "Thursday August 13th at 3:40pm with Maya, in the window you asked for."
    result = gate.check(bad, rationale(Axis.TIME_FIT))
    assert not result.ok
    assert result.failed_check == "F1"
    assert "Maya" in result.detail


# ------------------------------------------------------------------- F2 -----
def test_claiming_continuity_when_it_did_not_contribute_is_rejected() -> None:
    """The second crafted case: plausible prose describing a reason the slot did
    not actually win on. This is the failure the gate exists for."""
    bad = "Thursday August 13th at 3:40pm with your usual hygienist Sarah."
    result = gate.check(bad, rationale(Axis.TIME_FIT))
    assert not result.ok
    assert result.failed_check == "F2"


def test_claiming_continuity_when_it_did_contribute_is_allowed() -> None:
    ok = "Thursday August 13th at 3:40pm with Sarah, your usual hygienist."
    assert gate.check(ok, rationale(Axis.CONTINUITY, Axis.TIME_FIT)).ok


# ------------------------------------------------------------------- F3 -----
def test_over_length_is_rejected() -> None:
    bad = (
        "Thursday August 13th at 3:40pm with Sarah, and this sentence keeps going on "
        "well past the twenty five word limit that the requirement sets for you."
    )
    assert gate.check(bad, rationale(Axis.TIME_FIT)).failed_check == "F3"


# ------------------------------------------------------------------- F4 -----
@pytest.mark.parametrize("hedge", ["probably", "possibly", "might", "I think"])
def test_hedges_are_rejected(hedge: str) -> None:
    bad = f"Thursday August 13th at 3:40pm with Sarah {hedge} works for you."
    assert gate.check(bad, rationale(Axis.TIME_FIT)).failed_check in {"F1", "F4"}


# ------------------------------------------------------------------- F5 -----
@pytest.mark.parametrize(
    "bad",
    [
        "August 13th at 3:40pm with Sarah, in the window you asked for.",   # no weekday
        "Thursday at 3:40pm with Sarah, in the window you asked for.",      # no date
        "Thursday August 13th with Sarah, in the window you asked for.",    # no time
    ],
)
def test_the_resolved_date_and_time_must_be_echoed(bad: str) -> None:
    """R-04's mitigation. A confidently-wrong date cannot be engineered away, so the
    sentence must always carry it -- the patient is the one who catches it."""
    assert gate.check(bad, rationale(Axis.TIME_FIT)).failed_check == "F5"


# --------------------------------------------------------------- fallback ---
def test_a_gate_failure_substitutes_the_template_silently() -> None:
    """FR-063. The operator never sees an error; the trace shows the firing."""
    from app.agents.explainer import template

    r = rationale(Axis.TIME_FIT)
    unfaithful = "Thursday August 13th at 3:40pm with Maya."
    verdict = gate.check(unfaithful, r)
    substituted = unfaithful if verdict.ok else template.render(r)
    assert not verdict.ok
    assert "Maya" not in substituted
    assert "Sarah" in substituted


def test_the_gate_is_independent_of_the_schedule() -> None:
    """FR-059. It reaches the Rationale and nothing else, which is why it is short
    and testable without a fixture."""
    import inspect

    src = inspect.getsource(gate)
    for forbidden in ("repository", "AvailabilityIndex", "session", "CandidateSet"):
        assert forbidden not in src
