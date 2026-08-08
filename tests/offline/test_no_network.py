"""[NFR-09] Every MUST path works with networking disabled.

Not "should not need the network" -- *cannot use it*. The socket module is patched to
raise, so any code path that reaches out fails this test loudly rather than passing
whenever the wifi happens to work.

This exists because the failure it guards against is invisible in the normal case:
`llm_mode=fixtures` previously fell through to a live API call on a cache miss, so
"Offline · fixtures" on screen was not true and NFR-09 passed only by luck.
"""

from __future__ import annotations

import socket

import pytest

from app.config import Settings
from app.container import AppContainer
from app.orchestrator.machine import IncomingRequest

LOOPBACK = {"127.0.0.1", "::1", "localhost", ""}


@pytest.fixture
def no_network(monkeypatch):  # type: ignore[no-untyped-def]
    """Block outbound *connections*, not socket creation.

    Patching ``socket.socket`` itself breaks asyncio's own self-pipe, which would
    make this fixture fail the test harness rather than the product. Loopback stays
    open for the same reason.
    """
    real_connect = socket.socket.connect

    def guarded(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else str(address)
        if host in LOOPBACK:
            return real_connect(self, address, *args, **kwargs)
        raise OSError(f"outbound network is disabled for this test [NFR-09]: {host}")

    def refuse_create(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("outbound network is disabled for this test [NFR-09]")

    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(socket, "create_connection", refuse_create)
    return guarded


REQUESTS = [
    "Can I come in next Thursday after 3? Prefer Sarah if she's around.",
    "I need something first thing tomorrow, it's urgent",
    "Whatever works next week, I have PT on Tuesdays",
    "My tooth's been bothering me since Friday",
    "I need a tooth pulled",
]


async def test_every_request_is_answered_with_no_network(no_network) -> None:  # type: ignore[no-untyped-def]
    container = AppContainer(settings=Settings(llm_mode="fixtures"))
    for text in REQUESTS:
        record = await container.orchestrator.run(
            IncomingRequest(text=text, patient=container.load.bundle.patient("pat-000")),
            container.clock.now(),
            container.state.active_profile,
        )
        assert record.offers or record.overflow or record.question_asked, text
        assert record.funnel is not None
        # A complete reason line for every offer, offline (FR-060).
        for offer in record.offers:
            assert offer.reason


async def test_the_fallback_is_recorded_not_hidden(no_network) -> None:  # type: ignore[no-untyped-def]
    """Silent to the operator, loud in the trace (NFR-16)."""
    container = AppContainer(settings=Settings(llm_mode="fixtures", extractor="llm"))
    record = await container.orchestrator.run(
        IncomingRequest(text="cleaning next Wednesday", patient=None),
        container.clock.now(),
        container.state.active_profile,
    )
    spans = container.trace_store.spans_for(record.trace_id)
    extract = next(s for s in spans if s.stage == "extract")
    assert extract.attrs["fallback_fired"] is True
    assert "fallback_reason" in extract.attrs
    assert "extract" in record.fallback_fired


def test_the_seed_loads_with_no_network(no_network) -> None:  # type: ignore[no-untyped-def]
    container = AppContainer()
    assert len(container.load.bundle.appointments) > 100


async def test_eval_harness_runs_with_no_network(no_network) -> None:  # type: ignore[no-untyped-def]
    """The scorecard is a MUST, so it cannot depend on connectivity either."""
    from app.eval.harness import run_evaluation

    card = run_evaluation(Settings(llm_mode="fixtures"))
    assert card.cases >= 40
    assert card.determinism["identical"]
