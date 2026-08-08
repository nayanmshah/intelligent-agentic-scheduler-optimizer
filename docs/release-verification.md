# Release Verification

> What "it works" means here, and how it is checked rather than claimed.
>
> ```
> make release            # 3 cold starts, default
> RUNS=1 make release     # one
> COLD=0 scripts/release-check.sh 1   # skip the destructive rebuild
> ```

---

## The two phases, and why they are separate

Conflating them is how an offline claim quietly becomes false — the demo passes because
the wifi happened to be up, and nobody finds out until the room has no network.

| Phase | What runs | Network |
| :---- | :-------- | :------ |
| **A — build** | `make clean`, `uv sync`, `npm install`, SPA build | **Allowed.** Fetching pinned dependencies is a build step, not a request path. NFR-09 says nothing about it. |
| **B — the product** | preflight, full test suite, structural guards, lint, types, eval scorecard, HTTP server boot, six real requests, the SPA itself | **Blocked at the socket layer.** |

Phase B runs with `ANTHROPIC_API_KEY` unset *and* with
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
| `preflight` | NFR-12 — readiness is reported, not assumed |
| Full test suite | every FR/NFR with a test |
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
═══ summary ═══
  runs completed : 3/3
  failures       : 0
  RELEASE CHECK PASSED -- 3 cold starts, zero unrecovered failures.
```

Each cold start — full teardown, dependency install, SPA build, and the entire Phase B
battery — completed in **58–59 seconds**.

Per-run logs land in `.release-check/run{1,2,3}/` (gitignored). They are kept on
failure and are the first thing to read: `run_step` prints the last 20 lines of the
failing step inline, and the full log is on disk.

---

## What this does *not* prove

- **Concurrency.** v1.0 is single-operator (NFR-08). The conditional-write path
  (ADR-18) is unit-tested, but no multi-seat load is exercised here.
- **Live-mode latency under load.** Fixtures are the default and the demo path;
  live-mode p95 is measured only when `make fixtures` records.
- **A real practice's data.** The dataset is synthetic, generated from a committed
  seed, and its shape is the author's model of a practice — see
  [`known-limitations.md`](known-limitations.md).
- **Any wall-clock date outside 2026-08-03…2026-08-28.** The clock is injected
  (`SCHED_CLOCK=frozen` by default) precisely so this does not silently rot; a
  `SystemClock` exists and is one config flag away, but the seeded window is what the
  data covers.
