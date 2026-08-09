"""The live path, against the real API.

Excluded from the default suite because these cost money and need a network; run with
``make test-live``. They exist because the product ships live-first, and a suite that
only ever exercised the deterministic fallbacks would be testing the safety net rather
than the trapeze.

What they assert is deliberately about *behaviour that only a model produces* -- a
semantic mismatch no lookup could find, prose that reads aloud, a gate that actually
rejects things. Anything a rule could also do is tested in the fast suite instead.

Each test states its own tolerance. Model output varies run to run, so an assertion
that pins an exact sentence would be a flake generator; these pin properties.
"""

from __future__ import annotations

import time

import pytest

from app.config import Settings, get_settings
from app.container import AppContainer
from app.orchestrator.machine import IncomingRequest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not get_settings().has_api_key, reason="ANTHROPIC_API_KEY is not set"),
]


@pytest.fixture
async def container():  # type: ignore[no-untyped-def]
    """One container per test, constructed explicitly rather than from the environment.

    Two things this shape is buying, both learned the hard way:

    * **Explicit settings.** An earlier version set ``SCHED_LLM_MODE=live`` in a
      ``conftest`` at import, which runs during *collection* -- so it leaked into every
      module imported afterwards and the whole "deterministic" suite quietly started
      calling the API. Four minutes a run, and billed.
    * **Per test, and async.** A module-scoped container shares one schedule, so a test
      that books or holds a slot changes what the next one sees. And the teardown has
      to close the SDK's pool inside the *same* event loop that opened it --
      ``asyncio.run()`` in a sync fixture makes a new loop and the close fails there.
    """
    c = AppContainer(settings=Settings(llm_mode="live", verifier="llm", explainer="llm"))
    assert c.settings.llm_mode == "live", "these tests are meaningless outside live mode"
    try:
        yield c
    finally:
        await c.agents.aclose()


async def ask(container, text: str):  # type: ignore[no-untyped-def]
    return await container.orchestrator.run(
        IncomingRequest(text=text, patient=container.load.bundle.patient("pat-000")),
        container.clock.now(),
        container.state.active_profile,
    )


# ------------------------------------------------------------ the wiring ----


async def test_all_three_model_backed_roles_actually_run(container) -> None:
    """The regression this encodes: the explainer was built, tested, and never
    reached from a request -- the orchestrator called the template renderer directly.
    ``llm_calls`` is the number that would have caught it."""
    assert container.describe()["agents"] == {
        "extractor": "llm", "verifier": "llm", "explainer": "llm"
    }

    record = await ask(container, "Whatever works next week, I have PT on Tuesdays")

    assert record.llm_calls >= 3, (
        f"only {record.llm_calls} model call(s) -- a role is silently not running"
    )
    assert not record.fallback_fired, f"fell back to deterministic: {record.fallback_fired}"


async def test_the_model_writes_the_reason_lines(container) -> None:
    """At least one card must carry model prose. If the gate rejects every sentence
    the operator still gets a good answer -- but the model is buying nothing, and
    that is worth failing over."""
    record = await ask(container, "Any chance of a cleaning next Tuesday morning?")

    assert record.offers
    assert any(o.llm_reason for o in record.offers), (
        "every sentence fell back to the template; the gate or the prompt is wrong"
    )
    for offer in record.offers:
        assert offer.reason, "an offer has no reason line at all"


# ------------------------------------------------- what only a model can do ----


async def test_the_verifier_catches_a_symptom_treatment_mismatch(container) -> None:
    """The case that justifies a model in this role. No lookup finds it: the date is
    valid, the provider exists, the type is real -- and the request still does not
    make sense, because a fallen-off crown is not a cleaning."""
    record = await ask(container, "My crown fell off, can I get a cleaning?")

    joined = " ".join(record.flags).lower()
    assert record.flags, "no flag raised on a request whose symptom contradicts its type"
    assert "crown" in joined, f"the flag does not name the problem: {record.flags}"


async def test_an_ordinary_request_is_not_flagged(container) -> None:
    """The control. Without it, a verifier that flags everything would pass the test
    above and be useless in practice -- an operator learns to ignore a field that is
    always full."""
    record = await ask(container, "A cleaning on Thursday afternoon please")
    assert not record.flags, f"an unremarkable request was flagged: {record.flags}"


# ----------------------------------------------------------- the guardrails ----


async def test_no_offer_claims_the_appointment_is_already_booked(container) -> None:
    """Found live: the model wrote "You're booked for a Cleaning on Wednesday" and
    every other gate check passed it. An operator reading that aloud has told a
    patient they have an appointment they do not have."""
    record = await ask(container, "Something on Wednesday afternoon")

    for offer in record.offers:
        low = offer.reason.lower()
        for claim in ("you're booked", "you are booked", "you're scheduled",
                      "you're all set", "we've booked", "see you on"):
            assert claim not in low, f"offer asserts a booking: {offer.reason!r}"


async def test_every_reason_line_survives_the_read_aloud_lint(container) -> None:
    """Whatever the model writes, it has to be sayable to a patient (FR-065)."""
    from app.agents.explainer import lint

    record = await ask(container, "I need something first thing tomorrow, it's urgent")
    for offer in record.offers:
        assert len(lint.words(offer.reason)) <= lint.MAX_WORDS, offer.reason
        for banned in ("candidate", "overflow", "escalate", "score", "tier", "weight"):
            assert banned not in offer.reason.lower(), offer.reason


async def test_the_resolved_date_and_time_are_always_echoed(container) -> None:
    """FR-062's F5, end to end. This is the mitigation for the one residual risk that
    cannot be engineered away -- a confidently-wrong date -- because the *patient*
    catches it when it is read back."""
    record = await ask(container, "Can I come in next Thursday after 3?")
    for offer in (*record.offers, *record.overflow):
        assert offer.weekday.lower() in offer.reason.lower(), offer.reason
        assert offer.date_display.lower() in offer.reason.lower(), offer.reason
        assert offer.start_display.lower() in offer.reason.lower(), offer.reason


# --------------------------------------------------------------- latency ----


async def test_the_live_round_trip_is_reported(container) -> None:
    """Not a pass/fail on speed -- the honest number is in known-limitations.md §12.
    This asserts only that a live request completes inside the configured ladder, so
    a regression that doubles it fails here rather than on stage."""
    started = time.perf_counter()
    record = await ask(container, "A filling on Wednesday late morning")
    elapsed = time.perf_counter() - started

    ceiling = get_settings().live_latency_ceiling
    assert elapsed < ceiling, f"{elapsed:.1f}s exceeds the {ceiling}s live ceiling"
    assert record.offers or record.overflow or record.question_asked
