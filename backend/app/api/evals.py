"""Eval routes. Same ``run_evaluation`` the CLI calls (ADR-12).

The harness runs on its own thread so a 42-case sweep never blocks the operator
console, and the scorecard renders in-product because FR-092..FR-101 require it.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.eval.harness import run_evaluation

router = APIRouter(tags=["eval"])
_RUNS: dict[str, dict[str, Any]] = {}


@router.post("/eval/run")
async def start(request: Request) -> dict[str, str]:
    run_id = uuid.uuid4().hex[:12]
    _RUNS[run_id] = {"status": "running", "scorecard": None}
    settings = request.app.state.container.settings

    def work() -> None:
        try:
            card = run_evaluation(settings)
            _RUNS[run_id] = {"status": "done", "scorecard": card.as_dict()}
        except Exception as exc:  # pragma: no cover - surfaced to the caller
            _RUNS[run_id] = {"status": "error", "error": str(exc), "scorecard": None}

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": run_id, "status": "running"}


@router.get("/eval/runs/{run_id}")
async def status(run_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")
    return run
