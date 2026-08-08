"""S2 exit criteria: the dataset is loadable, reproducible, and frozen."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.config import get_settings
from app.data.digest import compute_digest, read_expected
from app.data.loader import SeedSchemaError, load_seed
from app.data.repository import ScheduleRepository
from app.data.session import MemoryScheduleRepository, SessionState

SEED_DIR = get_settings().seed_dir


@pytest.fixture(scope="module")
def result():  # type: ignore[no-untyped-def]
    return load_seed(SEED_DIR)


# ------------------------------------------------------------ FR-103, ADR-11 --
def test_digest_is_stable_across_loads() -> None:
    """Booting twice produces identical data digests. Anything else means the
    dataset is not actually frozen, and every golden label is unmoored."""
    assert compute_digest(SEED_DIR) == compute_digest(SEED_DIR)
    assert compute_digest(SEED_DIR) == read_expected(SEED_DIR)


def test_generator_is_not_invoked_by_boot() -> None:
    """FR-103. The Makefile's `demo` target must never regenerate data."""
    makefile = (SEED_DIR.parents[3] / "Makefile").read_text()
    demo = makefile.split("demo:")[1].split("\n\n")[0]
    assert "generate_seed" not in demo, "boot must not regenerate the dataset [FR-103]"


# --------------------------------------------------- loader, two failure modes --
def test_semantic_anomaly_is_quarantined_not_fatal(result) -> None:  # type: ignore[no-untyped-def]
    """Edge case 9. Real exports are dirty; refusing to boot is the wrong response,
    and ingesting silently is worse."""
    assert result.quarantined, "the deliberately dirty record was not detected"
    ids = {a.record_id for a in result.quarantined}
    assert "appt-dirty-01" in ids
    kept = {a.id for a in result.bundle.appointments}
    assert "appt-dirty-01" not in kept, "quarantined records must not reach the index"


def test_quarantine_report_names_the_record(result) -> None:  # type: ignore[no-untyped-def]
    """Any red item is named, never merely counted (NFR-12)."""
    text = str(result.quarantined[0])
    assert "appt-" in text and "--" in text


def test_schema_violation_fails_the_boot_loudly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    for f in SEED_DIR.glob("*.json"):
        (tmp_path / f.name).write_text(f.read_text())
    bad = json.loads((tmp_path / "appointment_types.json").read_text())
    bad[0]["duration_min"] = -5
    (tmp_path / "appointment_types.json").write_text(json.dumps(bad))

    with pytest.raises(SeedSchemaError) as exc:
        load_seed(tmp_path)
    msg = str(exc.value)
    assert "appointment_types.json" in msg
    assert "duration_min" in msg, "the message must name the field, not just the file"


# ------------------------------------------------------------- seed content ---
def test_seeded_shape_matches_the_prd(result) -> None:  # type: ignore[no-untyped-def]
    b = result.bundle
    assert len(b.locations) == 1
    assert len(b.operatories) == 6
    assert len(b.providers) == 9
    assert len([p for p in b.providers if p.role.value == "DDS"]) == 3
    assert len([p for p in b.providers if p.role.value == "RDH"]) == 4
    assert len(b.appointment_types) == 12
    assert len(b.patients) == 120
    assert {"Sarah", "Dr. Patel"} <= {p.name for p in b.providers}


def test_edge_case_2_sarah_is_on_pto(result) -> None:  # type: ignore[no-untyped-def]
    sarah = next(p for p in result.bundle.providers if p.name == "Sarah")
    assert sarah.on_pto(date(2026, 8, 13))
    assert not sarah.on_pto(date(2026, 8, 20))


def test_edge_case_8_only_one_operatory_is_surgical(result) -> None:  # type: ignore[no-untyped-def]
    equipped = [o.id for o in result.bundle.operatories if "surgical" in o.equipment_tags]
    assert equipped == ["OP-5"], "extraction must be constrained to a single room"


def test_edge_case_7_no_oral_surgeon_can_do_hygiene(result) -> None:  # type: ignore[no-untyped-def]
    okafor = next(p for p in result.bundle.providers if p.name == "Dr. Okafor")
    assert "RDH" not in okafor.credentials, "credential mismatch case needs this to hold"


def test_emergency_holds_are_seeded_and_unlockable(result) -> None:  # type: ignore[no-untyped-def]
    holds = [b for b in result.bundle.blocks if b.kind.value == "emergency_hold"]
    assert len(holds) == 2
    assert all(b.is_unlockable for b in holds)


def test_bookable_fortnight_occupancy_is_in_the_design_band(result) -> None:  # type: ignore[no-untyped-def]
    """Occupancy is the design parameter that matters: too empty and every request
    has a trivially easy answer; too full and everything is a rejection."""
    booked = sum(
        a.duration_min
        for a in result.bundle.appointments
        if date(2026, 8, 10) <= a.start.date() <= date(2026, 8, 21)
    )
    # 10 business days: 8 x 540 (Mon-Thu) + 2 x 360 (Fri), across 6 operatories.
    capacity = (8 * 540 + 2 * 360) * 6
    ratio = booked / capacity
    assert 0.60 <= ratio <= 0.85, f"bookable-fortnight occupancy {ratio:.0%} outside the band"


# ------------------------------------------------------- NFR-29 / ADR-18 -----
def test_repository_satisfies_the_protocol(result) -> None:  # type: ignore[no-untyped-def]
    repo = MemoryScheduleRepository(SessionState.from_seed(result.bundle))
    assert isinstance(repo, ScheduleRepository)


def test_versions_are_per_resource_day(result) -> None:  # type: ignore[no-untyped-def]
    """ADR-16. Invalidating one cell must not disturb its neighbours -- a global
    counter is invisible at one location and quadratic at many."""
    repo = MemoryScheduleRepository(SessionState.from_seed(result.bundle))
    d1, d2 = date(2026, 8, 12), date(2026, 8, 13)
    before_other = repo.version_of("OP-4", d1)
    before_day = repo.version_of("OP-3", d2)

    repo.invalidate("OP-3", d1)

    assert repo.version_of("OP-3", d1) == 1
    assert repo.version_of("OP-4", d1) == before_other
    assert repo.version_of("OP-3", d2) == before_day
