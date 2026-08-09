"""Selection: which three the operator actually sees.

Scored **17.4%** against mutation -- the lowest of any module in the decision core,
while being the one whose output is literally the product. The existing tests asserted
that three offers come back; almost nothing asserted *which* three, so the diversity
window, the epsilon band, the tiebreak chain and the relaxation ladder could all be
wrong without a failure.

Built on a hand-made candidate set rather than the seed, so each property is stated in
isolation and a failure names one cause.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.candidate import AxisValues, Candidate, CandidateSet, EfficiencySubterms
from app.reasoner.select import nearest_overflow, select_top3, tiebreak_key

LA = ZoneInfo("America/Los_Angeles")
DAY = date(2026, 8, 12)
WINDOW = 45  # diversity window, minutes
EPSILON = 0.02


def cand(cid: str, *, minute: int, provider: str = "prov-a", room: str = "OP-1",
         day: date = DAY) -> Candidate:
    return Candidate(
        candidate_id=cid,
        day=day,
        start=datetime.combine(day, datetime.min.time(), tzinfo=LA) + timedelta(minutes=minute),
        start_min=minute,
        duration_min=40,
        provider_id=provider,
        operatory_id=room,
    )


def make_set(rows: list[tuple[Candidate, float]], *, continuity: float = 0.5,
             fragmentation: float = 1.0) -> CandidateSet:
    """Every candidate feasible and in-tier, with the given score."""
    cs = CandidateSet()
    for c, score in rows:
        cs.add(c)
        ann = cs.ann(c.candidate_id)
        ann.feasible = True
        ann.in_tier = True
        ann.score = score
        ann.axes = AxisValues(
            time_fit=score, continuity=continuity, efficiency=score, prime_time=1.0,
            subterms=EfficiencySubterms(fragmentation, 1.0, 1.0, 1.0),
        )
    return cs


# ---------------------------------------------------------------- FR-051 ----


def test_the_three_highest_scores_are_offered_in_order() -> None:
    cs = make_set([
        (cand("low", minute=600, provider="prov-a"), 0.30),
        (cand("high", minute=700, provider="prov-b"), 0.90),
        (cand("mid", minute=800, provider="prov-c"), 0.60),
        (cand("lowest", minute=900, provider="prov-d"), 0.10),
    ])
    sel = select_top3(cs, EPSILON, WINDOW)
    assert sel.offered == ("high", "mid", "low")


def test_fewer_candidates_than_wanted_returns_what_exists() -> None:
    cs = make_set([(cand("only", minute=600), 0.5)])
    sel = select_top3(cs, EPSILON, WINDOW)
    assert sel.offered == ("only",)
    assert sel.limited_availability, "a single option must be flagged as limited"


def test_an_empty_tier_selects_nothing_rather_than_raising() -> None:
    sel = select_top3(CandidateSet(), EPSILON, WINDOW)
    assert sel.offered == ()
    assert not sel.limited_availability


# ---------------------------------------------------------------- FR-049 ----
# Diversity. Three slots with the same provider ten minutes apart is one option
# wearing three hats.


def test_near_duplicates_from_one_provider_are_suppressed() -> None:
    cs = make_set([
        (cand("a1", minute=600, provider="prov-a"), 0.90),
        (cand("a2", minute=610, provider="prov-a"), 0.89),  # 10 min later, same provider
        (cand("b1", minute=800, provider="prov-b"), 0.50),
        (cand("c1", minute=900, provider="prov-c"), 0.40),
    ])
    sel = select_top3(cs, EPSILON, WINDOW)
    assert "a2" not in sel.offered, "a near-duplicate of the winner was offered"
    assert sel.offered == ("a1", "b1", "c1")
    assert sel.suppressed >= 1


def test_the_same_provider_far_enough_apart_is_not_a_duplicate() -> None:
    """The window is a window, not a ban: two genuinely different times with the same
    hygienist are two real options."""
    cs = make_set([
        (cand("morning", minute=540, provider="prov-a"), 0.90),
        (cand("afternoon", minute=540 + WINDOW, provider="prov-a"), 0.80),
        (cand("other", minute=900, provider="prov-b"), 0.10),
    ])
    sel = select_top3(cs, EPSILON, WINDOW)
    assert set(sel.offered) == {"morning", "afternoon", "other"}


def test_the_same_time_with_a_different_provider_is_not_a_duplicate() -> None:
    cs = make_set([
        (cand("a", minute=600, provider="prov-a"), 0.90),
        (cand("b", minute=600, provider="prov-b", room="OP-2"), 0.80),
        (cand("c", minute=600, provider="prov-c", room="OP-3"), 0.70),
    ])
    assert len(select_top3(cs, EPSILON, WINDOW).offered) == 3


def test_the_same_provider_on_a_different_day_is_not_a_duplicate() -> None:
    cs = make_set([
        (cand("mon", minute=600, provider="prov-a"), 0.90),
        (cand("tue", minute=600, provider="prov-a", day=DAY + timedelta(days=1)), 0.80),
        (cand("wed", minute=600, provider="prov-a", day=DAY + timedelta(days=2)), 0.70),
    ])
    assert len(select_top3(cs, EPSILON, WINDOW).offered) == 3


def test_suppression_relaxes_in_stages_rather_than_returning_two() -> None:
    """Naively re-adding everything suppressed hands back the exact near-duplicates
    the constraint exists to remove. Relaxing in stages prefers the least-similar
    option that is still available."""
    cs = make_set([
        (cand("a1", minute=600, provider="prov-a"), 0.90),
        (cand("a2", minute=612, provider="prov-a"), 0.80),   # 12 min -- very similar
        (cand("a3", minute=600 + WINDOW // 2, provider="prov-a"), 0.70),  # half-window
    ])
    sel = select_top3(cs, EPSILON, WINDOW)
    assert len(sel.offered) == 3, "relaxation failed to fill the card"
    assert sel.offered[0] == "a1"
    # The half-window option is less similar than the 12-minute one, so it comes back
    # first even though it scores lower.
    assert sel.offered[1] == "a3", sel.offered


# ---------------------------------------------------------------- FR-048 ----
# The tiebreak chain must be total: two candidates cannot tie all the way down, or
# ordering depends on list order and the same request answers differently.


def test_equal_scores_break_on_time_then_continuity_then_room() -> None:
    early = cand("early", minute=600, provider="prov-b", room="OP-9")
    late = cand("late", minute=700, provider="prov-a", room="OP-1")
    cs = make_set([(late, 0.5), (early, 0.5)])
    assert select_top3(cs, EPSILON, WINDOW).offered[0] == "early"


def test_the_tiebreak_chain_is_total() -> None:
    """Two candidates identical on every earlier key still order deterministically,
    because the chain terminates in ids."""
    a = cand("a", minute=600, provider="prov-a", room="OP-1")
    b = cand("b", minute=600, provider="prov-a", room="OP-2")
    cs = make_set([(a, 0.5), (b, 0.5)])
    keys = [tiebreak_key((c, cs.ann(c.candidate_id))) for c in (a, b)]
    assert keys[0] != keys[1], "two candidates tie all the way down"
    assert select_top3(cs, EPSILON, WINDOW).offered == ("a", "b")


# ---------------------------------------------------------------- FR-050 ----
# Co-equal grouping. Scores within epsilon are "as good as each other", and the UI
# says so rather than implying a precision the model does not have.


def test_scores_within_epsilon_share_a_group() -> None:
    cs = make_set([
        (cand("a", minute=600, provider="prov-a"), 0.900),
        (cand("b", minute=700, provider="prov-b"), 0.895),  # within 0.02
        (cand("c", minute=800, provider="prov-c"), 0.500),  # clearly worse
    ])
    g = select_top3(cs, EPSILON, WINDOW).coequal_groups
    assert g["a"] == g["b"], "near-identical scores were presented as ranked"
    assert g["c"] != g["a"], "a clearly worse option was grouped with the winners"


def test_a_gap_wider_than_epsilon_starts_a_new_group() -> None:
    cs = make_set([
        (cand("a", minute=600, provider="prov-a"), 0.90),
        (cand("b", minute=700, provider="prov-b"), 0.80),
        (cand("c", minute=800, provider="prov-c"), 0.70),
    ])
    g = select_top3(cs, EPSILON, WINDOW).coequal_groups
    assert len({g["a"], g["b"], g["c"]}) == 3


# ---------------------------------------------------------------- FR-035 ----


def test_overflow_prefers_the_soonest_and_spreads_across_days() -> None:
    """The operator gets options, not three views of the same afternoon."""
    cs = CandidateSet()
    for i, (cid, day, minute) in enumerate([
        ("d1a", DAY, 600), ("d1b", DAY, 700),
        ("d2", DAY + timedelta(days=1), 600),
        ("d3", DAY + timedelta(days=2), 600),
    ]):
        c = cand(cid, minute=minute, day=day, room=f"OP-{i}")
        cs.add(c)
        cs.ann(cid).feasible = True

    picked = nearest_overflow(cs)
    assert picked[0] == "d1a", "overflow did not lead with the soonest option"
    assert len(picked) == 3
    assert "d1b" not in picked, "two slots on one day crowded out a later day"


def test_overflow_is_empty_when_nothing_is_feasible() -> None:
    assert nearest_overflow(CandidateSet()) == ()
