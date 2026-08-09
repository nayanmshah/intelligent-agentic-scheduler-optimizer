"""[ADR-04] Fixtures are a decorator over the LLM implementation, not a third one.

That keeps "which implementation ran?" a two-value question, and it means the fixture
path and the live path are byte-identical in everything except where the JSON came
from.

**Live mode does not read this cache.** Serving a recorded answer while the header
says "Live model" would make the product's headline capability invisible precisely when
someone is watching it -- a demo request that happened to match a fixture would never
reach the model. In live mode the cache is write-through: every call is real, and the
recording is a by-product that keeps offline mode possible.

Reading resumes in fixture mode, which is the degraded path (no key, no network) rather
than the default. The cache key includes the request text, the model id and the prompt
version, so changing any of the three invalidates only its own fixtures.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.domain.entities import Patient
from app.domain.request import RequestConstraints


def cache_key(
    *, stage: str, text: str, model: str, prompt_version: str, patient: str | None
) -> str:
    raw = json.dumps(
        {"stage": stage, "text": text.strip(), "model": model,
         "prompt": prompt_version, "patient": patient},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class FixtureStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, stage: str, key: str) -> Path:
        return self.root / stage / f"{key}.json"

    def get(self, stage: str, key: str) -> dict[str, Any] | None:
        p = self._path(stage, key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put(self, stage: str, key: str, payload: dict[str, Any]) -> None:
        p = self._path(stage, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def count(self) -> int:
        return len(list(self.root.rglob("*.json")))


class FixtureCachedExtractor:
    """Same protocol as the thing it wraps.

    **A cache miss in offline mode must NOT reach the network.** Falling through to a
    live call would make "offline (fixtures)" a lie: the demo would silently depend
    on connectivity, and NFR-09 would pass only when the wifi happened to work. On a
    miss we raise, and the orchestrator's existing fallback ladder routes to the
    deterministic extractor -- which is the behaviour the mode indicator promises.
    """

    def __init__(self, inner: Any, store: FixtureStore, model: str, prompt_version: str,
                 record: bool = False, allow_network: bool = False,
                 read_cache: bool = True) -> None:
        self._inner = inner
        self._store = store
        self._model = model
        self._prompt_version = prompt_version
        self._record = record
        self._allow_network = allow_network
        self._read_cache = read_cache
        #: What the header reports. In live mode the cache is write-only, so calling
        #: this "fixtures(llm)" would misdescribe which path answered.
        self.name = inner.name if not read_cache else f"fixtures({inner.name})"
        self.misses = 0

    async def extract(
        self, text: str, patient: Patient | None, now: datetime
    ) -> RequestConstraints:
        key = cache_key(
            stage="extract", text=text, model=self._model,
            prompt_version=self._prompt_version, patient=patient.id if patient else None,
        )
        if self._read_cache:
            cached = self._store.get("extract", key)
            if cached is not None:
                return RequestConstraints(**cached)

        self.misses += 1
        if not self._allow_network:
            from app.agents.llm.client import LlmUnavailable

            raise LlmUnavailable(
                f"fixture miss for key {key} and network is disabled (llm_mode=fixtures)"
            )

        result = await self._inner.extract(text, patient, now)
        if self._record:
            self._store.put("extract", key, json.loads(result.model_dump_json()))
        return result
