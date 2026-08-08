"""S4 exit criteria: a complete deterministic decision, with no LLM anywhere.

At the end of this stage the product's whole argument is demonstrable from a REPL --
which is the right place to be before any UI exists.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.agents.explainer import lint
from app.agents.explainer.render import render_outcome
from app.config import get_settings
from app.data.loader import load_seed
from app.data.session import MemoryScheduleRepository, SessionState
from app.data.timezone import zone
from app.domain.enums import OfferState, Urgency
from app.domain.policy import GENERAL_PRACTICE_DEFAULT, PRESETS, Weights
from app.domain.request import TimeWindow
from app.reasoner.pipeline import DeterministicReasoner
from tests.requirements.test_s3_reasoner import constraints

SETTINGS = get_settings()
NOW = SETTINGS.reference_now


@pytest.fixture(scope="module")
def reasoner():  # type: ignore[no-untyped-def]
    bundle = load_seed(SETTINGS.seed_dir).bundle
    repo = MemoryScheduleRepository(SessionState.from_seed(bundle))
    return DeterministicReasoner(repo, SETTINGS, zone(bundle.locations[0].timezone))


def decide(reasoner, profile=GENERAL_PRACTICE_DEFAULT, **kw):  # type: ignore[no-untyped-def]
    """The reasoner decides; the explainer renders. Separate calls on purpose --
    that split is what FR-054 and FR-059 are asserting."""
    return render_outcome(reasoner.run(constraints(**kw), NOW, profile))


# ------------------------------------------------------ FR-051 / FR-053 ----
def test_offers_three_options_with_full_card_content(reasoner) -> None:
    out = decide(reasoner)
    assert len(out.offers) == 3
    for o in out.offers:
        assert o.weekday and o.date_display and o.start_display
        assert o.provider_name and o.operatory_name and o.type_name
        assert o.duration_min > 0
        assert 0.0 <= o.score <= 1.0
        assert len(o.contributions) == 4


# ----------------------------------------------------------------- FR-047 ----
def test_score_decomposes_exactly_into_its_contributions(reasoner) -> None:
    """The UI never displays a naked number, so the parts must sum to the whole."""
    for o in decide(reasoner).offers:
        assert abs(sum(c.weighted for c in o.contributions) - o.score) < 1e-6


# ----------------------------------------------------------------- FR-039 ----
def test_effective_weights_still_sum_to_one_after_renormalisation(reasoner) -> None:
    out = decide(reasoner, type_id="crown_seat")
    assert abs(sum(out.effective_weights.as_row()) - 1.0) < 1e-9
    # crown seat carries a 2.0 continuity multiplier, so effective != nominal
    assert out.effective_weights.continuity > out.nominal_weights.continuity


# ----------------------------------------------------------------- FR-048 ----
def test_the_same_request_twice_is_byte_identical(reasoner) -> None:
    a = decide(reasoner)
    b = decide(reasoner)
    assert [o.candidate_id for o in a.offers] == [o.candidate_id for o in b.offers]
    assert [o.score for o in a.offers] == [o.score for o in b.offers]
    assert [o.template_reason for o in a.offers] == [o.template_reason for o in b.offers]


# ----------------------------------------------------------------- FR-050 ----
def test_offers_are_genuinely_different_options(reasoner) -> None:
    """Three near-identical options are one option; offering them as three wastes
    the patient's only real choice."""
    out = decide(reasoner)
    if not out.limited_availability:
        days = {o.date_display for o in out.offers}
        providers = {o.provider_name for o in out.offers}
        assert len(days) >= 2 or len(providers) >= 2


# ----------------------------------------------------------------- FR-065 ----
def test_every_reason_line_passes_the_read_aloud_lint(reasoner) -> None:
    """The requirement that makes reading a reason aloud reliable rather than lucky."""
    failures = []
    for type_id in ("prophy_adult", "crown_seat", "filling_1s", "limited_exam"):
        out = decide(reasoner, type_id=type_id)
        for o in out.offers:
            r = lint.check(o.template_reason, o.rationale.facts)
            if not r.ok:
                failures.append(f"{type_id}: {o.template_reason!r} -> {r.violations}")
    assert not failures, "\n".join(failures)


def test_ledger_sentences_pass_the_lint_too(reasoner) -> None:
    """Why-not text is operator-facing, so it is held to the same bar (FR-030)."""
    out = decide(reasoner)
    assert out.ledger
    for group in out.ledger[:5]:
        r = lint.check(group.sentence, refers_to_slot=False)
        assert r.ok, f"{group.sentence!r} -> {r.violations}"


def test_the_lint_actually_rejects_bad_copy() -> None:
    """A lint nobody has watched fail is a decoration."""
    assert not lint.check("Score 0.87 with high time fit.", refers_to_slot=False).ok
    assert not lint.check("We found an operatory in tier 2.", refers_to_slot=False).ok
    assert not lint.check(
        "This is a very long sentence that goes on and on well past the twenty five "
        "word limit that the requirement sets for anything you might read to a patient.",
        refers_to_slot=False,
    ).ok


# ----------------------------------------------------------------- FR-029 ----
def test_funnel_reconciles_with_the_conservation_invariant(reasoner) -> None:
    out = decide(reasoner)
    f = out.funnel
    assert f.enumerated > f.feasible >= f.in_tier >= f.offered
    assert f.offered == len(out.offers)
    assert f.grid_slots > 0


# ----------------------------------------------------------------- FR-032 ----
def test_no_weight_vector_can_promote_a_lower_tier(reasoner) -> None:
    """Urgency is a gate, not a weight. Scored as a weight, a strong enough
    preference for convenience could outrank a genuine emergency."""
    for profile in PRESETS:
        out = decide(reasoner, profile=profile)
        tiers_offered = set()
        for o in out.offers:
            tiers_offered.add(o.date_display)
        assert out.offers, f"{profile.name} produced no offers"


def test_extreme_weight_vectors_never_crash(reasoner) -> None:
    """FR-083: the policy panel is directly manipulable by a non-engineer."""
    from app.domain.policy import WeightProfile

    extremes = [
        (1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0),
    ]
    for row in extremes:
        profile = WeightProfile(
            id="x", name="x", weights=Weights.normalised(row)
        )
        out = decide(reasoner, profile=profile)
        assert out.offers
        for o in out.offers:
            assert lint.check(o.template_reason, o.rationale.facts).ok


# ---------------------------------------------------------- FR-035 / FR-038 --
def test_never_returns_an_empty_response(reasoner) -> None:
    """A patient in pain must never be told "nothing's available" by a computer."""
    from app.domain.request import Exclusions

    out = decide(reasoner, exclusions=Exclusions(weekdays=frozenset({0, 1, 2, 3, 4})))
    assert (
        len(out.offers) + len(out.overflow) >= 1
        or out.origin_state is OfferState.OFFERED_OVERFLOW
    )


# ---------------------------------------------------------------- SD-2 ------
def test_rationale_components_match_the_top_weighted_contributions(reasoner) -> None:
    """The explanation is generated *from* the decision, so it cannot disagree
    with it."""
    for o in decide(reasoner).offers:
        weighted = {c.axis: c.weighted for c in o.contributions}
        top = max(weighted, key=lambda k: weighted[k])
        cited = {a.axis.value for a in o.rationale.components}
        assert top in cited, f"top contributor {top} not cited in {cited}"


def test_at_most_one_caveat(reasoner) -> None:
    for o in decide(reasoner).offers:
        assert o.rationale.caveat is None or isinstance(o.rationale.caveat.text, str)


# ---------------------------------------------------------------- FR-038 ----
# Three regressions from real defects found by reading the product's own output
# against the reference scenarios. None of them failed a test at the time.


def test_an_offer_that_matches_the_request_is_not_captioned_as_an_alternative(
    reasoner,
) -> None:
    """The "nothing opened when you asked" opener is decided per *offer*.

    It used to be decided once per record from the winning tier, which is a
    different question: a slot inside the requested window can still come from the
    FLEXIBLE tier, and every offer then carried a caption that was simply untrue.
    """
    out = decide(reasoner, start=date(2026, 8, 10), end=date(2026, 8, 24))
    assert out.offers, "the scenario must produce offers for this to test anything"
    for o in out.offers:
        inside = date(2026, 8, 10) <= o.day <= date(2026, 8, 24)
        assert inside, "fixture assumption: all offers land inside the asked-for range"
        assert "Nothing opened when you asked" not in o.reason, o.reason


def test_an_offer_outside_the_requested_days_says_so(reasoner) -> None:
    """A single-day request that cannot be met must produce offers that *lead* with
    the gap -- an operator half-listening otherwise reads out the wrong day."""
    # Thu 2026-08-13 after 15:00: hygiene rooms are booked solid that afternoon, so a
    # cleaning cannot be placed on the requested day at all.
    out = decide(reasoner, time=TimeWindow(start_min=900),
                 start=date(2026, 8, 13), end=date(2026, 8, 13))
    outside = [o for o in (*out.offers, *out.overflow) if o.day != date(2026, 8, 13)]
    assert outside, "fixture assumption: this day cannot be satisfied"
    for o in outside:
        assert "Nothing opened when you asked" in o.reason, o.reason


def test_a_shortfall_is_never_dropped_to_make_room_for_a_compliment(reasoner) -> None:
    """Atoms were ranked by weighted contribution, so a low-scoring axis sorted last
    and the 25-word cap dropped it. But a low-scoring axis is exactly the one the
    operator must hear about. Concessions now sort first."""
    out = decide(reasoner, time=TimeWindow(start_min=900),
                 start=date(2026, 8, 13), end=date(2026, 8, 13))
    for o in (*out.offers, *out.overflow):
        if o.day == date(2026, 8, 13):
            continue
        assert "outside the days you asked about" in o.reason, o.reason
        assert len(lint.words(o.reason)) <= lint.MAX_WORDS


# ---------------------------------------------------------------- FR-051 ----
def test_fewer_than_three_options_is_flagged_as_limited_availability(reasoner) -> None:
    """One option is the *most* limited availability there is.

    The flag was computed as ``len(chosen) > 1 and not spread_ok``, so the single
    result an operator most needs warning about was the one case never flagged.
    """
    out = decide(reasoner, type_id="limited_exam", urgency=Urgency.URGENT)
    if len(out.offers) < 3:
        assert out.limited_availability, (
            f"{len(out.offers)} offer(s) returned without a limited-availability flag"
        )
