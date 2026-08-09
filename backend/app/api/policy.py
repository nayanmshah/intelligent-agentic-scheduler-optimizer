"""Practice-policy routes. Deliberately not reachable from the operator flow (FR-076).

Putting weight controls in front of the front desk invites per-call adjustment, which
destroys the decision consistency the product exists to provide.
"""

from __future__ import annotations

import random
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import RerankRequest
from app.domain.policy import PRESETS, Weights

router = APIRouter(tags=["policy"])


def _c(request: Request) -> Any:
    return request.app.state.container


@router.get("/policy/profiles")
async def profiles(request: Request) -> dict[str, Any]:
    active = _c(request).state.active_profile
    return {
        "active": active.id,
        "profiles": [
            {"id": p.id, "name": p.name, "weights": p.weights.model_dump(),
             "is_fitted": p.is_fitted}
            for p in PRESETS
        ],
    }


@router.put("/policy/active")
async def set_active(body: dict, request: Request) -> dict[str, Any]:
    c = _c(request)
    profile = next((p for p in PRESETS if p.id == body.get("id")), None)
    if profile is None:
        raise HTTPException(404, "unknown profile")
    c.state.active_profile = profile
    return {"active": profile.id, "weights": profile.weights.model_dump()}


@router.post("/policy/rerank")
async def rerank(body: RerankRequest, request: Request) -> dict[str, Any]:
    """[ADR-06] A product against a matrix already computed -- not a second pipeline
    run. That is what keeps this under 300ms with zero LLM calls (FR-079, NFR-04)."""
    c = _c(request)
    record = c.trace_store.decision(body.request_id)
    if record is None or record.score_matrix is None:
        raise HTTPException(404, "no scored decision to re-rank")

    try:
        weights = Weights.normalised(
            (body.weights.time_fit, body.weights.continuity,
             body.weights.efficiency, body.weights.prime_time)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc   # all-zero is rejected (FR-078)

    scores = record.score_matrix.scores_for(weights)
    ranked = sorted(
        zip(record.score_matrix.candidate_ids, scores, strict=True),
        key=lambda kv: -kv[1],
    )[:3]
    # Labels come from the matrix, not from the original top three: re-ranking is
    # *supposed* to promote candidates that were not offered, and naming only the
    # first three rendered those rows as "83% --" on the one screen whose whole
    # purpose is watching the order change.
    def row(cid: str, score: float) -> dict[str, Any]:
        label = record.score_matrix.label_for(cid) if record.score_matrix else None
        return {
            "candidate_id": cid,
            "score": round(score, 6),
            "provider_name": label[0] if label else None,
            "start_display": label[1] if label else None,
            "was_offered": any(o.candidate_id == cid for o in record.offers),
        }

    return {
        "weights": weights.model_dump(),
        "llm_calls": 0,
        "ranked": [row(cid, score) for cid, score in ranked],
    }


def _reselect(matrix: Any, w: Any, diversity_window_min: int, want: int = 3) -> set[str]:
    """The three the operator would actually see under weight vector ``w``.

    Replays `select.select_top3`'s greedy diversity pass rather than taking the top
    three by score. Those two disagree by construction: the same provider at the same
    minute in two rooms scores identically, and the diversity rule deliberately skips
    a higher-scoring near-duplicate to avoid offering one option wearing three hats.
    Comparing the offer set against a naive sort therefore reported 0% for reasons
    that had nothing to do with the weights being unstable.
    """
    scores = matrix.scores_for(w)
    keys = matrix.keys or ((("", 0, 0, ""),) * len(matrix.candidate_ids))
    ranked = sorted(
        zip(matrix.candidate_ids, scores, keys, strict=True),
        # Score first, then FR-048's tiebreak prefix (earlier, then room) so the order
        # is total and reproducible rather than dependent on list order.
        key=lambda t: (-t[1], t[2][1], t[2][2], t[2][3]),
    )
    chosen: list[tuple[str, float, tuple[str, int, int, str]]] = []
    for item in ranked:
        if len(chosen) >= want:
            break
        _, _, (prov, day, start, _) = item
        if any(
            c[2][0] == prov and c[2][1] == day and abs(c[2][2] - start) < diversity_window_min
            for c in chosen
        ):
            continue
        chosen.append(item)
    # Selection relaxes suppression rather than return fewer than three (select.py).
    if len(chosen) < want:
        picked = {c[0] for c in chosen}
        for item in ranked:
            if len(chosen) >= want:
                break
            if item[0] not in picked:
                chosen.append(item)
    return {c[0] for c in chosen}


@router.get("/policy/stability")
async def stability(request_id: str, request: Request) -> dict[str, Any]:
    """[FR-081] Converts "the weights are arbitrary" from an objection into a
    measurement: the recommendation is robust to the weights, or it is not, and the
    number says which. Sampling is seeded so it is reproducible run to run."""
    c = _c(request)
    record = c.trace_store.decision(request_id)
    if record is None or record.score_matrix is None:
        raise HTTPException(404, "no scored decision")

    s = c.settings
    matrix = record.score_matrix
    baseline = {o.candidate_id for o in record.offers}
    if not baseline:
        raise HTTPException(400, "no offers to test")

    rng = random.Random(s.stability_seed)
    exact = 0
    per_slot = dict.fromkeys(baseline, 0)
    for _ in range(s.stability_samples):
        w = Weights.normalised(tuple(rng.random() for _ in range(4)))  # type: ignore[arg-type]
        top = _reselect(matrix, w, s.diversity_window_min)
        if top == baseline:
            exact += 1
        for cid in baseline & top:
            per_slot[cid] += 1

    pct = round(100 * exact / s.stability_samples)
    weakest = round(100 * min(per_slot.values()) / s.stability_samples) if per_slot else 0
    return {
        "samples": s.stability_samples,
        "seed": s.stability_seed,
        "held_pct": pct,
        # Stated in words, not just a number -- that is the point of the indicator.
        "sentence": (
            f"These three are what you would be offered under {pct}% of "
            f"{s.stability_samples} random weight settings."
        ),
        "weakest_pct": weakest,
        "per_slot_pct": {
            cid: round(100 * n / s.stability_samples) for cid, n in per_slot.items()
        },
    }
