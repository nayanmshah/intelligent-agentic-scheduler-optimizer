# Release Verification

> What "it works" means here, and how it is checked rather than claimed.
>
> ```
> make release            # 3 cold starts, default
> RUNS=1 make release     # one
> COLD=0 scripts/release-check.sh 1   # skip the destructive rebuild
> ```

---

## The three phases, and why they are separate

Conflating them is how a claim quietly becomes false in either direction — the demo
passes because the wifi happened to be up, or the offline suite passes while the live
path nobody exercised has been broken for a week.

| Phase | What runs | Network |
| :---- | :-------- | :------ |
| **A — build** | `make clean`, `uv sync`, `npm install`, SPA build | **Allowed.** Fetching pinned dependencies is a build step, not a request path. NFR-09 says nothing about it. |
| **B — the shipped configuration** | the live suite: extraction, verification and explanation against the real API; live preflight | **Required.** This is what a demo runs, so it is what the check has to prove works. |
| **C — the degraded path** | preflight, full test suite, structural guards, lint, types, eval scorecard, HTTP server boot, six real requests, the SPA itself | **Blocked at the socket layer**, key unset. |

**Both halves matter and neither substitutes for the other.** Testing only Phase C
proves the safety net and never the trapeze — that was the earlier shape of this
script, and it is how the LLM explainer stayed unreachable from a request for as long
as it did. Testing only Phase B means a network blip on stage is unrehearsed.

If no API key is present, Phase B is skipped and the summary says so explicitly, so a
green run never quietly means "we verified half the product".

Phase C runs with `ANTHROPIC_API_KEY` unset *and* with
`scripts/offline/sitecustomize.py` on `PYTHONPATH`. Python imports `sitecustomize`
automatically at interpreter start, so every process in the phase — server, harness,
CLI — refuses outbound connections without the application knowing it is being tested.

Loopback stays open, deliberately: the check drives the **real HTTP server** over
127.0.0.1 rather than calling functions in-process, and asyncio needs its self-pipe.
Connections are blocked rather than socket *creation*, for the same reason.

### This is stronger than the offline test suite

`tests/offline/test_no_network.py` proves the code paths it exercises are offline.
The guard proves the **shipped process** is, including any path a test forgot. Both
exist; they check different things.

### The guard is verified to bite

A blocking guard that silently does nothing would make the whole check vacuous, so it
is exercised directly:

```
$ PYTHONPATH=scripts/offline uv run python -c \
    "import socket; socket.create_connection(('api.anthropic.com', 443))"
  [offline-guard] outbound connections blocked (loopback allowed)
  OSError: outbound network is disabled for this run [NFR-09]: api.anthropic.com

$ PYTHONPATH=scripts/offline SCHED_LLM_MODE=live uv run python -c "<real LlmClient call>"
  blocked: LlmUnavailable: Connection error.
```

The second control matters more than the first: it drives the actual Anthropic SDK
through the actual client, in live mode, and the call fails. The run also greps every
log for the guard's refusal message afterwards — a MUST path that reached out fails the
run rather than passing quietly.

---

## What each run checks

| Step | Requirement |
| :--- | :---------- |
| Cold rebuild from `make clean` | NFR-11 — one command, no manual steps |
| Live pipeline against the real API | the shipped configuration; three model-backed roles actually run |
| Live preflight names the model path | FR-105 — which path answered is never a guess |
| `preflight` | NFR-12 — readiness is reported, not assumed |
| Deterministic suite (`-m "not live"`) | every FR/NFR with a test, offline |
| Structural guards | FR-102, FR-054, NFR-32 — clock reads, naive datetimes, import direction, weight literals |
| `ruff` + `mypy` | the repo's own quality bar |
| Eval scorecard | FR-092…FR-101, including the FR-097 determinism check |
| Server boots and serves the SPA | the demo path itself |
| Six requests over real HTTP | every one returns offers *or* overflow *or* a question, each offer with a reason line, funnel counts and a trace id |
| Eval driven through the API | ADR-12 — the CLI and the HTTP route call the same function, so there is no second implementation to drift |
| Log grep for refused connections | NFR-09 |

The six requests are drawn from the reference scenarios, so a pass means the demo path
works — not merely that the process starts.

---

## Result

```
  live pipeline [shipped config]                ok
  live preflight reports the model path         ok
  preflight [NFR-12]                            ok
  test suite [degraded]                         ok
  structural guards                             ok
  lint + types                                  ok
  eval scorecard [FR-092]                       ok
  boot server on :8099                          ok
  end-to-end smoke over HTTP                    ok
  no outbound connection was attempted          ok

  RELEASE CHECK PASSED -- zero unrecovered failures.
```

A cold start with the live phase included takes **~170 seconds**; skipping it (no key
present) takes **~55**. The difference is 8 real API round trips.

Per-run logs land in `.release-check/run{1,2,3}/` (gitignored). They are kept on
failure and are the first thing to read: `run_step` prints the last 20 lines of the
failing step inline, and the full log is on disk.

---

## What this does *not* prove

- **Concurrency.** v1.0 is single-operator (NFR-08). The conditional-write path
  (ADR-18) is unit-tested, but no multi-seat load is exercised here.
- **Live-mode latency under load.** A single live request is timed against the
  configured ceiling; no concurrent load is applied. The per-stage numbers are in
  [`known-limitations.md`](known-limitations.md) §12.
- **A real practice's data.** The dataset is synthetic, generated from a committed
  seed, and its shape is the author's model of a practice — see
  [`known-limitations.md`](known-limitations.md).
- **Any wall-clock date outside 2026-08-03…2026-08-28.** The clock is injected
  (`SCHED_CLOCK=frozen` by default) precisely so this does not silently rot; a
  `SystemClock` exists and is one config flag away, but the seeded window is what the
  data covers.
