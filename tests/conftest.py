"""Test-suite defaults.

**The product ships live-first; this suite does not run that way, and the distinction
is deliberate.**

Almost everything here tests logic the model never touches -- enumeration, the rule
ladder, scoring, selection, the write path, the timezone boundary. Running those
against a live API would make them slow, non-deterministic, and expensive, and would
buy exactly nothing: a scoring axis does not behave differently because a model was
called upstream.

So the default suite pins fixture mode. The live path is not left unverified -- it has
its own suite in ``tests/live/``, marked ``live``, excluded here and run deliberately
by ``make test-live``. That way "the tests pass" never quietly means "the tests
skipped the thing the product actually does".
"""

from __future__ import annotations

import os

# Set at import, not in a fixture. Several test modules call ``get_settings()`` at
# module scope, which happens during collection -- long before any fixture runs. A
# fixture-based version of this looked correct and silently did nothing, and the
# suite quietly started billing the API on every run.
os.environ.setdefault("SCHED_LLM_MODE", "fixtures")
os.environ["SCHED_LLM_MODE"] = "fixtures"
os.environ["SCHED_VERIFIER"] = "rules"
os.environ["SCHED_EXPLAINER"] = "template"
# Opik ships enabled, so without this the "offline, free" suite quietly opens sockets
# to a container that may or may not be running — an external dependency, and a
# ResourceWarning that `filterwarnings = ["error"]` correctly turns into a failure.
# Tests that care about the sink construct one explicitly and point it at nothing.
os.environ["SCHED_OPIK_ENABLED"] = "false"
