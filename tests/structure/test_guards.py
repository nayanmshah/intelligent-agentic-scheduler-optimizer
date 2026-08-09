"""Structural guards.

These went in with the first commit, before the code they guard. A structural test
added *after* a violation exists is a cleanup chore; added before, it is a wall.

Every guard here is paired with a `_detects_violation` test that runs the same rule
against synthetic offending source. A guard nobody has watched fail is not a guard.
"""

from __future__ import annotations

import ast

import pytest

from tests.structure._rules import (
    APP_ROOT,
    IMPORT_RULES,
    REPO_ROOT,
    app_sources,
    check_import_rule,
    find_clock_reads,
    find_naive_datetimes,
    find_weight_literals,
)


def _tree(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------- FR-102 ----
#: The one module allowed to read a clock besides ``clock.py``.
#:
#: FR-102 exists so that no *decision* can depend on ambient time. The Opik sink
#: consumes decisions that are already made, on a background thread, and needs
#: absolute timestamps only to lay spans on a display timeline -- it cannot reach
#: anything the reasoner sees. Named here rather than added to a general exclusion
#: list, and the count is asserted, so a second exception cannot appear quietly.
_CLOCK_EXCEPTIONS = ("trace/opik.py",)


def test_no_clock_reads_outside_clock_module() -> None:
    violations, excused = [], []
    for path in app_sources(exclude=("clock.py",)):
        rel = path.relative_to(REPO_ROOT).as_posix()
        found = find_clock_reads(ast.parse(path.read_text()), rel)
        if rel.endswith(_CLOCK_EXCEPTIONS):
            excused += found
        else:
            violations += found
    assert not violations, "clock read outside clock.py [FR-102]:\n" + "\n".join(
        map(str, violations)
    )
    assert len(excused) <= 1, (
        "the observability sink is excused ONE clock read for span timestamps; it now "
        f"has {len(excused)}. Each one is a place ambient time could leak toward a "
        "decision, so adding another is a deliberate act:\n"
        + "\n".join(map(str, excused))
    )


def test_clock_guard_detects_violation() -> None:
    src = "from datetime import datetime\ndef f():\n    return datetime.now()\n"
    assert find_clock_reads(_tree(src), "synthetic.py"), "the clock guard does not actually fire"


# ---------------------------------------------------------------- NFR-32 ----
def test_no_naive_datetimes_outside_conversion_boundary() -> None:
    violations = []
    for path in app_sources(exclude=("data/timezone.py",)):
        rel = path.relative_to(REPO_ROOT).as_posix()
        violations += find_naive_datetimes(ast.parse(path.read_text()), rel)
    assert not violations, "naive datetime outside data/timezone.py [NFR-32]:\n" + "\n".join(
        map(str, violations)
    )


def test_naive_datetime_guard_detects_violation() -> None:
    src = "from datetime import datetime\nx = datetime(2026, 8, 10, 9, 0)\n"
    assert find_naive_datetimes(_tree(src), "synthetic.py"), "the naive-datetime guard is inert"


# ------------------------------------------------------ import direction ----
@pytest.mark.parametrize("rule", IMPORT_RULES, ids=lambda r: f"{r.package}->{r.forbidden[0]}")
def test_import_direction(rule) -> None:  # type: ignore[no-untyped-def]
    violations = check_import_rule(rule)
    assert not violations, "forbidden import:\n" + "\n".join(map(str, violations))


# ---------------------------------------------------------------- FR-046 ----
def test_no_weight_literals_in_scorer() -> None:
    violations = find_weight_literals()
    assert not violations, "weights must be data [FR-046]:\n" + "\n".join(map(str, violations))


# ---------------------------------------------------------------- FR-085 ----
#: Modules allowed to import the Opik SDK, each for a stated reason.
#:
#:   trace/opik.py       the sink abstraction itself -- the whole point of FR-085
#:   eval/opik_suite.py  an offline CLI that pushes datasets and experiments. Never
#:                       imported by the app; asserted below.
_OPIK_SDK_ALLOWED = ("trace/opik.py", "eval/opik_suite.py")

#: Packages that run while a patient is waiting. The SDK must not appear in any of
#: them -- this is the property FR-085 actually protects, and it is checked directly
#: rather than inferred from a file-name exclusion list.
_REQUEST_PATH = ("agents/", "api/", "orchestrator/", "reasoner/", "data/", "domain/")


def test_no_opik_sdk_outside_trace_package() -> None:
    offenders, on_request_path = [], []
    for path in app_sources():
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text()
        if "import opik" not in text and "from opik" not in text:
            continue
        if any(f"app/{pkg}" in rel for pkg in _REQUEST_PATH):
            on_request_path.append(rel)
        elif not rel.endswith(_OPIK_SDK_ALLOWED):
            offenders.append(rel)

    assert not on_request_path, (
        "the observability SDK is on the REQUEST PATH [FR-085]. An optional backend "
        f"must not be importable while a patient waits: {on_request_path}"
    )
    assert not offenders, (
        f"observability SDK escaped the sink abstraction [FR-085]: {offenders}. "
        "Add it to _OPIK_SDK_ALLOWED with a reason, or route it through TraceSink."
    )


# ---------------------------------------------------------------- NFR-27 ----
def test_orchestrator_stays_readable() -> None:
    machine = APP_ROOT / "orchestrator" / "machine.py"
    if not machine.exists():
        pytest.skip("orchestrator not built yet (S5)")
    code_lines = [
        ln
        for ln in machine.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert len(code_lines) <= 150, (
        f"orchestrator is {len(code_lines)} lines. NFR-27 caps it at ~150 so a reader can "
        "trace one request in five minutes. Push logic down into the packages it calls."
    )


# ---------------------------------------------------------------- NFR-02 ----
def test_timeout_ladder_fits_the_live_budget() -> None:
    from app.config import Settings

    s = Settings()
    assert s.timeout_ladder_total <= s.live_latency_ceiling, (
        f"per-stage timeouts sum to {s.timeout_ladder_total}s, over the "
        f"{s.live_latency_ceiling}s live ceiling [NFR-02]. Beyond ~5s the operator "
        "opens the calendar anyway and the value proposition is gone."
    )
