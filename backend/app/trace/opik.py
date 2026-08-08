"""The optional Opik leg. Best effort, bounded, and **never on the request path**.

[FR-089] Emission is fire-and-forget behind a bounded queue drained by one daemon
thread. A full queue drops and counts; any exception counts and is swallowed. There
is no retry, because a retry on the request path is exactly the thing that would let
an observability backend slow down a patient-facing answer.

This is the only module in the codebase permitted to import the Opik SDK -- a grep
test asserts it (FR-085).
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any

from app.trace.sink import Span


@dataclass
class OpikCounters:
    emitted: int = 0
    dropped: int = 0
    failed: int = 0
    unavailable: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "emitted": self.emitted,
            "dropped": self.dropped,
            "failed": self.failed,
            "unavailable": self.unavailable,
        }


class OpikTraceSink:
    """Wrap with ``RedactingSink`` -- observability is a PHI leak vector [AR-06]."""

    def __init__(self, url: str, enabled: bool, maxsize: int = 1000) -> None:
        self.url = url
        self.enabled = enabled
        self.counters = OpikCounters()
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=maxsize)
        self._client: Any = None
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        if enabled:
            self._start()

    # -- the request path touches only this ------------------------------------
    def emit(self, span: Span) -> None:
        self._offer(("span", span))

    def record_decision(self, record: Any) -> None:
        self._offer(("decision", record))

    def _offer(self, item: tuple[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            # Dropping is correct. Blocking here would put an optional backend on a
            # patient-facing path; the count is reported on the scorecard (FR-101).
            self.counters.dropped += 1

    # -- everything below runs on the worker thread ----------------------------
    def _start(self) -> None:
        self._worker = threading.Thread(target=self._drain, name="opik-sink", daemon=True)
        self._worker.start()

    def _connect(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import opik

            self._client = opik.Opik(host=self.url)
        except Exception:
            self.counters.unavailable += 1
            self._client = False  # remember the failure; do not retry per item
        return self._client

    def _drain(self) -> None:
        while not self._stop.is_set():
            try:
                kind, payload = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                client = self._connect()
                if not client:
                    self.counters.unavailable += 1
                    continue
                if kind == "span":
                    client.trace(name=payload.stage, metadata=payload.as_dict())
                else:
                    client.trace(name="decision", metadata={"id": getattr(payload, "id", "")})
                self.counters.emitted += 1
            except Exception:
                # Counted and swallowed. A failing sink must never surface to a user.
                self.counters.failed += 1

    def close(self, timeout: float = 1.0) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=timeout)

    @property
    def backlog(self) -> int:
        return self._queue.qsize()
