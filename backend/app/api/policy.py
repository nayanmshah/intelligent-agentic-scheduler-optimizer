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
    by_id = {o.candidate_id: o for o in record.offers}
    return {
        "weights": weights.model_dump(),
        "llm_calls": 0,
        "ranked": [
            {
                "candidate_id": cid,
                "score": round(score, 6),
                "start_display": by_id[cid].start_display if cid in by_id else None,
                "provider_name": by_id[cid].provider_name if cid in by_id else None,
            }
            for cid, score in ranked
        ],
    }


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
    held = 0
    per_slot = dict.fromkeys(baseline, 0)
    for _ in range(s.stability_samples):
        w = Weights.normalised(tuple(rng.random() for _ in range(4)))  # type: ignore[arg-type]
        scores = matrix.scores_for(w)
        top = {
            cid for cid, _ in sorted(
                zip(matrix.candidate_ids, scores, strict=True), key=lambda kv: -kv[1]
            )[:3]
        }
        if top == baseline:
            held += 1
        for cid in baseline & top:
            per_slot[cid] += 1

    pct = round(100 * held / s.stability_samples)
    return {
        "samples": s.stability_samples,
        "seed": s.stability_seed,
        "held_pct": pct,
        # Stated in words, not just a number -- that is the point of the indicator.
        "sentence": f"These three stay in the top 3 across {pct}% of sampled weight vectors.",
        "per_slot_pct": {
            cid: round(100 * n / s.stability_samples) for cid, n in per_slot.items()
        },
    }
