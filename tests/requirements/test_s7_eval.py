"""S7 exit criteria: the golden set and the scorecard.

These tests check the *methodology*, not the numbers. A harness that reports a
flattering figure because the label was drawn from the system's own output is worse
than no harness, so the circularity guards below matter more than any threshold.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.data.digest import compute_digest
from app.eval.golden.labels import GOLDEN
from app.eval.harness import run_evaluation

SETTINGS = get_settings()


@pytest.fixture(scope="module")
def card():  # type: ignore[no-untyped-def]
    return run_evaluation(SETTINGS)


# ----------------------------------------------------------------- FR-092 ----
def test_golden_set_is_large_enough_and_covers_every_class() -> None:
    assert len(GOLDEN) >= 40
    counts: dict[str, int] = {}
    for case in GOLDEN:
        for tag in case["class_tags"]:
            counts[tag] = counts.get(tag, 0) + 1
    thin = {t: n for t, n in counts.items() if n < 3}
    # Every class needs >= 3 entries, or its accuracy figure is noise.
    assert not thin, f"classes with fewer than 3 entries: {thin}"


def test_labels_are_hand_written_not_captured_from_the_extractor() -> None:
    """If the labels were the extractor's own output, FR-093's accuracy number would
    be 100% by construction and would mean nothing."""
    assert SETTINGS  # labels live in labels.py as literals, not generated at runtime
    src = (SETTINGS.seed_dir.parents[1] / "eval" / "golden" / "labels.py").read_text()
    assert "RuleIntentExtractor" not in src
    assert "LlmIntentExtractor" not in src


def test_scorecard_is_pinned_to_the_frozen_dataset(card) -> None:  # type: ignore[no-untyped-def]
    """ADR-11. Labels reference specific seeded slots, so a dataset change must be
    visible rather than silently producing wrong numbers."""
    assert card.seed_digest == compute_digest(SETTINGS.seed_dir)


# ----------------------------------------------------------------- FR-093 ----
def test_extraction_is_reported_per_field_with_denominators(card) -> None:
    per_field = card.extraction_rules["per_field"]
    assert set(per_field) == {
        "date_range", "time_window", "urgency",
        "provider_preference", "appointment_type", "exclusions",
    }
    for name, acc in per_field.items():
        assert acc["total"] == len(GOLDEN), name
        assert "failures" in acc


# ----------------------------------------------------------------- FR-094 ----
def test_ranking_reports_both_metrics_with_denominators(card) -> None:
    assert "/" in card.ranking["top1"]
    assert "/" in card.ranking["top3"]


def test_the_preference_label_is_not_drawn_from_our_own_offers() -> None:
    """The circularity that makes a top-3 hit rate meaningless. The label comes from
    the full feasible set; if it came from the offered three the rate would be 100%
    by definition -- which is exactly the bug this test exists to prevent."""
    import inspect

    from app.eval import harness

    src = inspect.getsource(harness.run_evaluation)
    assert "_preferred_slot(label_cs" in src, "label must come from the candidate set"
    assert "_preferred_slot(list(outcome.offers)" not in src


# ----------------------------------------------------------------- FR-095 ----
def test_baseline_is_a_real_alternative_ranker(card) -> None:
    """The naive ranker must select its own top 3 from the feasible set, not
    reshuffle ours -- otherwise the head-to-head is vacuous."""
    ours = card.baseline["ours"]["top3_pct"]
    naive = card.baseline["naive"]["top3_pct"]
    quality_ours = card.baseline["quality_ours"]["orphan_minutes_per_case"]
    quality_naive = card.baseline["quality_naive"]["orphan_minutes_per_case"]
    assert quality_ours != quality_naive, (
        "identical schedule-quality numbers mean the baseline is not ranking "
        "independently"
    )
    assert isinstance(ours, float) and isinstance(naive, float)


def test_classes_with_no_measurable_gain_are_named(card) -> None:
    """Knowing where the product does not add value is part of knowing whether it
    works. Reporting only the favourable aggregate is the failure mode."""
    per_class = card.baseline["per_class"]
    assert per_class
    verdicts = {v["verdict"] for v in per_class.values()}
    assert "no measurable gain" in verdicts or all(v == "better" for v in verdicts)
    for tag, v in per_class.items():
        assert "delta" in v, tag


# ------------------------------------------------------- FR-097 / FR-100 -----
def test_determinism_check_runs_and_passes(card) -> None:
    assert card.determinism["identical"], f"differing cases: {card.determinism['differing']}"


def test_failing_cases_are_named_not_just_counted(card) -> None:
    named = [f for acc in card.extraction_rules["per_field"].values() for f in acc["failures"]]
    total_wrong = sum(
        acc["total"] - acc["correct"] for acc in card.extraction_rules["per_field"].values()
    )
    assert len(named) == total_wrong, "every failure must be nameable, not just counted"


def test_read_aloud_lint_holds_over_the_whole_golden_set(card) -> None:
    assert card.lint["violations"] == 0, card.lint["detail"]


# ----------------------------------------------------------------- FR-101 ----
def test_limitations_are_disclosed_including_the_label_bias(card) -> None:
    blob = " ".join(card.limitations).lower()
    assert "single-annotator" in blob or "single annotator" in blob
    assert "biased" in blob, "the label heuristic's bias must be stated, not buried"


def test_telemetry_is_reported(card) -> None:
    assert set(card.telemetry) >= {
        "rules_fallback_rate_pct", "gate_firing_rate_pct", "opik_unavailable_count"
    }


# ----------------------------------------------------------------- NFR-01 ----
def test_latency_is_measured_against_the_threshold(card) -> None:
    assert card.latency["p95_ms"] < card.latency["ceiling_ms"]
    assert card.latency["pass"]
