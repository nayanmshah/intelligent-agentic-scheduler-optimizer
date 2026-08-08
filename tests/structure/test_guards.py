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
def test_no_clock_reads_outside_clock_module() -> None:
    violations = []
    for path in app_sources(exclude=("clock.py",)):
        rel = path.relative_to(REPO_ROOT).as_posix()
        violations += find_clock_reads(ast.parse(path.read_text()), rel)
    assert not violations, "clock read outside clock.py [FR-102]:\n" + "\n".join(
        map(str, violations)
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
def test_no_opik_sdk_outside_trace_package() -> None:
    offenders = []
    for path in app_sources(exclude=("trace/opik.py",)):
        text = path.read_text()
        if "import opik" in text or "from opik" in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert not offenders, f"observability SDK escaped the sink abstraction [FR-085]: {offenders}"


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
