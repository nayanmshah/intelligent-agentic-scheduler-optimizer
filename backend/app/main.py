"""FastAPI application factory.

One process serves the API and the built SPA from the same origin (ADR-01): no
reverse proxy, no second port, no CORS. Every extra process is another way the
system fails on an unfamiliar machine.

Two ordering details that are easy to get wrong and expensive to debug:

1. **Routers mount before static.** The SPA fallback is a catch-all; registered
   first it would swallow every ``/api`` request.
2. **Unmatched non-API paths return ``index.html``.** ``/policy`` and ``/traces`` are
   client-side routes with no file behind them. Without the fallback, a refresh or a
   pasted link 404s -- and opening the policy panel in a second tab is exactly the
   natural thing to do.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import evals, policy, system, traces
from app.api import requests as request_routes
from app.container import build_container


@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Hold the connection pool open for the process, then release it.

    Without the close, every reload in development leaks the SDK's sockets.
    """
    yield
    await app.state.container.agents.aclose()


def create_app() -> FastAPI:
    container = build_container()

    app = FastAPI(
        lifespan=_lifespan,
        title="Intelligent Agentic Scheduling Optimizer",
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.container = container

    # 1. API first -- the static mount below is a catch-all.
    app.include_router(system.router, prefix="/api")
    app.include_router(request_routes.router, prefix="/api")
    app.include_router(policy.router, prefix="/api")
    app.include_router(traces.router, prefix="/api")
    app.include_router(evals.router, prefix="/api")

    # 2. Then the SPA.
    static_dir: Path = container.settings.static_dir
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        # response_model=None: the return is a union of Response subclasses, which
        # FastAPI would otherwise try to treat as a pydantic response model.
        @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
        async def spa(full_path: str) -> FileResponse | JSONResponse:
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            index = static_dir / "index.html"
            return FileResponse(index)

    else:

        @app.get("/", include_in_schema=False)
        async def unbuilt() -> JSONResponse:
            return JSONResponse(
                {
                    "detail": "Frontend not built. Run `make frontend` (or `make demo`).",
                    "api": "/api/docs",
                }
            )

    return app


app = create_app()
