"""Trace and replay routes. Reads the in-process store only (FR-087).

Never put a container on the request path of a system that has to work on an
arbitrary machine: with the container runtime stopped, traces render and replay
normally.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.data.digest import canonical_json

router = APIRouter(tags=["traces"])


def _c(request: Request) -> Any:
    return request.app.state.container


@router.get("/traces")
async def list_traces(request: Request) -> dict[str, Any]:
    c = _c(request)
    return {
        "decisions": [
            {
                "id": d.id,
                "trace_id": d.trace_id,
                "raw_text": d.raw_text,
                "offers": len(d.offers),
                "fallback_fired": list(d.fallback_fired),
                "question": d.question_asked,
            }
            for d in c.trace_store.latest(50)
        ]
    }


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, request: Request) -> dict[str, Any]:
    spans = _c(request).trace_store.spans_for(trace_id)
    if not spans:
        raise HTTPException(404, "trace not found")
    return {"trace_id": trace_id, "spans": [s.as_dict() for s in spans]}


@router.post("/traces/{decision_id}/replay")
async def replay(decision_id: str, request: Request) -> dict[str, Any]:
    """[FR-088] Re-runs the deterministic pipeline from the *stored extraction* and
    asserts byte equality. Because the extraction is stored rather than re-requested,
    replay needs no network -- and because NOW is stored on the record, it needs no
    assumption about when the replay happens."""
    c = _c(request)
    record = c.trace_store.decision(decision_id)
    if record is None or record.constraints is None:
        raise HTTPException(404, "decision not found")

    from app.agents.explainer.render import render_outcome

    fresh = render_outcome(
        c.reasoner.run(record.constraints, record.now, c.state.active_profile, record.id)
    )
    before = canonical_json([_offer_key(o) for o in record.offers])
    after = canonical_json([_offer_key(o) for o in fresh.offers])

    if before == after:
        return {"identical": True, "diff": None}
    return {
        "identical": False,
        # A visible field-level diff rather than a silent failure.
        "diff": {"stored": before, "replayed": after},
    }


def _offer_key(o: Any) -> dict[str, Any]:
    return {
        "candidate_id": o.candidate_id,
        "score": o.score,
        "provider": o.provider_name,
        "start": o.start_display,
        "reason": o.reason,
    }


@router.delete("/traces")
async def clear(request: Request) -> dict[str, str]:
    """A separate, explicitly-labelled action -- session reset does not do this."""
    _c(request).trace_store.clear_traces()
    return {"status": "cleared"}


@router.get("/observability")
async def observability(request: Request) -> dict[str, Any]:
    """The non-blocking banner's data source (FR-089, NFR-12).

    Reports the state rather than hiding it: an unreachable backend is a warning on
    screen, never an error on the request path.
    """
    c = _c(request)
    if not c.settings.opik_enabled:
        return {"enabled": False, "status": "local trace store only"}
    counters = c.opik.counters.as_dict()
    reachable = counters["unavailable"] == 0
    return {
        "enabled": True,
        "reachable": reachable,
        "status": "connected" if reachable else "Observability backend offline — traces are local",
        "backlog": c.opik.backlog,
        **counters,
    }
