"""System routes: readiness, pre-flight, and the reference indicators.

FR-104 and FR-105 exist because a user reading "Thursday the 13th" needs to know the
dataset's today is Monday the 10th -- otherwise every date on screen looks wrong.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/reference")
async def reference(request: Request) -> dict[str, Any]:
    """The persistent header: reference date, network mode, observability status."""
    container = request.app.state.container
    return container.describe()


@router.get("/preflight")
async def preflight(request: Request) -> dict[str, Any]:
    """NFR-12. Runs at boot and is re-runnable on demand. Any red item is *named*."""
    from app.cli.preflight import run_preflight

    return run_preflight(request.app.state.container).as_dict()
