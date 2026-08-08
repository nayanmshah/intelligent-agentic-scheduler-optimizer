"""Record LLM fixtures for the golden set and the demo script.

Run **once, online, deliberately** (``make fixtures``). Never part of boot or of the
demo path: fixture mode is the default precisely so the demo cannot depend on
connectivity, and a recorder that ran implicitly would defeat that.

The recorded JSON is committed. Each key includes the request text, the model id and
the prompt version, so bumping any of the three invalidates only its own entries.
"""

from __future__ import annotations

import asyncio
import sys

from app.agents.extractor.llm import LlmIntentExtractor
from app.agents.llm.client import LlmClient, LlmRefused, LlmUnavailable
from app.agents.llm.fixtures import FixtureStore, cache_key
from app.config import get_settings
from app.data.loader import load_seed
from app.eval.golden.labels import GOLDEN


async def record() -> int:
    s = get_settings()
    if not s.has_api_key:
        sys.stderr.write("  ANTHROPIC_API_KEY is not set; nothing to record.\n")
        return 1

    bundle = load_seed(s.seed_dir).bundle
    store = FixtureStore(s.fixtures_dir)
    extractor = LlmIntentExtractor(LlmClient(s), bundle, s)
    patient = bundle.patient("pat-000")

    # Recording is an offline batch job, so it must NOT inherit the request-path
    # budget: 2.2s is what the operator can afford while a patient waits, not what a
    # one-off recording run needs. The per-call latency is measured and reported so
    # live-mode viability against NFR-02 is a number rather than an assumption.
    import time as _time

    s.timeout_extract = 90.0
    latencies: list[float] = []
    recorded = failed = skipped = 0
    for i, case in enumerate(GOLDEN):
        text = case["raw_text"]
        key = cache_key(
            stage="extract", text=text, model=s.model_extract,
            prompt_version=s.prompt_version, patient=patient.id if patient else None,
        )
        if store.get("extract", key) is not None:
            skipped += 1
            continue
        t0 = _time.perf_counter()
        try:
            result = await extractor.extract(text, patient, s.reference_now)
            latencies.append(_time.perf_counter() - t0)
        except LlmRefused as exc:
            sys.stdout.write(f"  [refused] g{i:02d}  {text[:50]!r}  ({exc})\n")
            failed += 1
            continue
        except LlmUnavailable as exc:
            sys.stdout.write(f"  [failed ] g{i:02d}  {text[:50]!r}  {exc}\n")
            failed += 1
            continue

        # FR-003 is verified here rather than trusted: a fixture with a fabricated
        # span would poison every later run silently.
        if not result.spans_are_verbatim():
            sys.stdout.write(f"  [bad-span] g{i:02d}  {text[:50]!r}  -- not recorded\n")
            failed += 1
            continue

        import json

        store.put("extract", key, json.loads(result.model_dump_json()))
        recorded += 1
        sys.stdout.write(f"  [ok     ] g{i:02d}  {text[:50]!r}\n")

    sys.stdout.write(
        f"\n  recorded {recorded}, skipped {skipped} (already present), failed {failed}\n"
        f"  fixtures now in {s.fixtures_dir} ({store.count()} files)\n"
    )
    if latencies:
        ordered = sorted(latencies)
        p50 = ordered[len(ordered) // 2]
        p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
        budget = get_settings().timeout_extract
        sys.stdout.write(
            f"\n  live extraction latency: p50 {p50:.2f}s   p95 {p95:.2f}s\n"
            f"  request-path budget is {budget:.1f}s -- "
            f"{'FITS' if p95 < budget else 'DOES NOT FIT'} (NFR-02)\n"
        )
    return 0 if failed == 0 else 1


def main() -> int:
    return asyncio.run(record())


if __name__ == "__main__":
    raise SystemExit(main())
