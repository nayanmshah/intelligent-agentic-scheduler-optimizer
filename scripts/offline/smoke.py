"""End-to-end smoke test against a running server, with the network blocked.

Driven by ``scripts/release-check.sh``. Uses ``urllib`` over loopback so the only
dependency is the standard library -- this has to run in whatever interpreter the
cold start produced, before anything else is trusted.

Every request here is one from the reference scenarios, so a pass means the demo
path itself works, not merely that the process starts.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

REQUESTS = [
    "Can I come in next Thursday after 3? Prefer Sarah if she's around.",
    "I need something first thing tomorrow, it's urgent",
    "Whatever works next week, I have PT on Tuesdays",
    "My tooth's been bothering me since Friday",
    "I need a tooth pulled",
    "Not Thursday, and not Wednesdays or Fridays either",
]


def post(base: str, path: str, payload: dict) -> dict:  # type: ignore[type-arg]
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - loopback only
        return json.loads(r.read())


def get(base: str, path: str) -> bytes:
    with urllib.request.urlopen(base + path, timeout=30) as r:  # noqa: S310
        return r.read()


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
    problems: list[str] = []

    for text in REQUESTS:
        try:
            d = post(base, "/api/requests", {"text": text, "patient_id": "pat-000"})
        except (urllib.error.URLError, OSError) as exc:
            problems.append(f"{text[:40]!r}: request failed -- {exc}")
            continue

        offers = d.get("offers") or []
        overflow = d.get("overflow") or []
        # FR-035: the operator is never shown an empty screen. Either there are
        # options, or there is a question, or there is a stated reason there are none.
        if not offers and not overflow and not d.get("question"):
            problems.append(f"{text[:40]!r}: no offers, no overflow, no question")
            continue
        for o in offers:
            if not o.get("reason"):
                problems.append(f"{text[:40]!r}: offer {o.get('candidate_id')} has no reason line")
        if not d.get("funnel"):
            problems.append(f"{text[:40]!r}: no funnel counts (FR-070)")
        if not d.get("trace_id"):
            problems.append(f"{text[:40]!r}: no trace id")

    # The scorecard must be reachable in-product, not only from the CLI (ADR-12) --
    # the same function behind both, so there is no second implementation to drift.
    try:
        run_id = post(base, "/api/eval/run", {})["run_id"]
        card = None
        for _ in range(120):  # the harness replays 54 cases twice for FR-097
            state = json.loads(get(base, f"/api/eval/runs/{run_id}"))
            if state["status"] == "done":
                card = state["scorecard"]
                break
            if state["status"] == "error":
                problems.append(f"eval run errored: {state.get('error')}")
                break
            time.sleep(1)
        if card is None and not problems:
            problems.append("eval run did not finish within 120s")
        elif card is not None:
            if not card.get("extraction_rules"):
                problems.append("eval returned no extraction results")
            if card.get("extraction_llm") is None:
                problems.append("eval returned no LLM extraction column (FR-093)")
            if not card.get("determinism", {}).get("identical"):
                problems.append("determinism check failed in-product (FR-097)")
    except (urllib.error.URLError, OSError, KeyError) as exc:
        problems.append(f"eval endpoint failed -- {exc}")

    # The SPA itself.
    try:
        if b'id="root"' not in get(base, "/"):
            problems.append("index.html did not contain the SPA mount point")
    except (urllib.error.URLError, OSError) as exc:
        problems.append(f"SPA not served -- {exc}")

    if problems:
        for p in problems:
            sys.stderr.write(f"  SMOKE FAIL: {p}\n")
        return 1
    sys.stdout.write(f"  {len(REQUESTS)} requests answered, scorecard and SPA served\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
