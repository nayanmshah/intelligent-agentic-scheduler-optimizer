# Intelligent Agentic Scheduler & Optimizer

Turns what a patient actually says — *"Can I come in next Thursday after 3? Prefer
Sarah if she's around."* — into **three ranked appointment options, each with a reason
a receptionist can read aloud.**

A front-desk coordinator hears that sentence forty times a day. They alt-tab to a grid,
scan for white space, and pick something. The pick is usually fine and occasionally
expensive: it fragments the day, or it consumes a block the practice was holding for
restorative work. This system makes that decision explicit, consistent, and
explainable.

> **LLMs at the edges, arithmetic in the middle.** Language models read the request and
> write the sentence. The ranking itself is a pure deterministic function — so *"did it
> miss anything?"* is a question with an answer.

---

## Run it

```bash
make demo          # cold start to a usable UI at http://127.0.0.1:8000
```

One command. No API key, no network, no manual steps — the model calls are served from
fixtures recorded once and committed. Everything below is optional.

```bash
make test          # the full suite, offline
make check         # lint + types + structural guards
make eval          # golden-set scorecard, with an exit code
make release       # 3 cold starts with the network blocked (see below)
make fixtures      # re-record LLM fixtures. Online, deliberate, once.
```

**Requires** `uv` (pins Python 3.12) and Node 20+. Nothing else.

**The dataset's today is Monday 2026-08-10**, shown in the header on every screen.
`NOW` is injected rather than read from the system clock — the seed covers
2026-08-03…2026-08-28, and *"next Thursday"* has to mean something fixed for the same
request to produce the same answer twice.

---

## What it does

| | |
| :-- | :-- |
| **Reads the request** | Six typed fields — date range, time window, urgency, provider preference, appointment type, exclusions — each with a confidence and **the verbatim span of the patient's words it came from**. |
| **Asks only when it matters** | Ambiguity triggers a question *only* if the readings produce different answers. *"My tooth's been bothering me"* runs as both a 30-minute exam and a 90-minute crown prep; the answers diverge, so it asks. When they agree, it proceeds. |
| **Enumerates exhaustively** | Every (operatory × day × start minute) candidate, filtered through a two-phase rule ladder. Nothing is ever deleted — rejections are annotated and kept, and `enumerated = offered + rejected` is reconciled on every request. |
| **Ranks on four axes** | Time fit, continuity, efficiency, block protection — as a score matrix times a weight vector, so the policy screen re-ranks instantly with zero model calls. |
| **Explains itself** | One sentence per offer, ≤25 words, second person, built only from facts the scorer emitted. A faithfulness gate and a read-aloud lint stand between the model and the operator. |
| **Never shows an empty screen** | If nothing fits, the nearest options are offered — **labelled**, leading with the gap, never silently substituted. |

---

## What the numbers say

Measured on 54 hand-labelled requests, reproducibly, offline (`make eval`).

**Against a naive first-available baseline**, on measures taken from the schedule
itself rather than from either ranker's own output:

| | This system | Naive first-available |
| :-- | --: | --: |
| Orphan minutes created per booking | **1.3** | 14.6 |
| Protected block minutes consumed | **0.0** | 3.1 |

Eleven times fewer unusable gaps, and it never eats a restorative block.

**The top-3 hit rate is 45.3% against the baseline's 47.2% — and that comparison is
biased against this system.** The preference label is a heuristic whose objective is
much closer to *earliest-first* than to a weighted trade-off. The reasoning, and the
honest fix, are in [`docs/known-limitations.md`](docs/known-limitations.md) rather than
omitted.

**Extraction** is 96.3% (rules) vs 94.8% (LLM) overall — close, and they fail
differently: the model is 7.4 points better at reading clinical intent from symptom
language, and worse at citing provenance for what it inferred. Full table and the
convention bias in the same document.

**Live extraction takes 7.3s at p50 against a 2.2s budget for that stage** (measured,
on both Opus 5 and Sonnet 5; adaptive thinking accounts for 0.1s of it). Committed
fixtures are therefore load-bearing rather than a convenience, and rules-mode is the
shipped default on latency grounds. What would actually close the gap is written down
rather than hand-waved.

---

## How it is built

```
request text
   ↓  Intent Extractor      LLM  +  deterministic fallback  +  committed fixtures
   ↓  Constraint Verifier   validates against the world, never sees the schedule
   ↓  Schedule Reasoner     DETERMINISTIC, zero LLM — enumerate, filter, score, rank
   ↓  Explainer             LLM phrasing over scorer-emitted facts, gated + linted
three ranked offers
```

Each of the four roles satisfies a `Protocol` with **two implementations**, one of
which needs no network. That is what makes the offline guarantee structural rather than
aspirational. The orchestrator between them is a plain state machine in 135 lines —
deliberately not an agent framework.

**Stack.** FastAPI + uvicorn (one process serves the API and the built SPA) · Python
3.12 · React 19 + TypeScript + Vite + Tailwind · Pydantic v2 at the I/O boundary,
frozen slotted dataclasses on the hot path.

**Four structural guards** parse the source and fail the build on: a clock read outside
`clock.py`, a naive datetime outside `timezone.py`, the reasoner importing the
explainer, or a magic weight literal inside a function. They caught three real
violations during the build.

---

## Verification

```
make release
  runs completed : 3/3
  failures       : 0
  RELEASE CHECK PASSED -- 3 cold starts, zero unrecovered failures.
```

Everything after dependency installation runs with **outbound connections blocked at
the socket layer** — the server, the harness, the CLI. "Works offline" is enforced by
the harness, not asserted by the author, and the guard itself is verified to bite.
See [`docs/release-verification.md`](docs/release-verification.md).

121 tests · lint and types clean · determinism checked on every eval run.

---

## Documentation

| | |
| :-- | :-- |
| [`docs/demo-script.md`](docs/demo-script.md) | Twelve minutes, six requests, three screens — with real output |
| [`docs/design-faq.md`](docs/design-faq.md) | The decisions most worth arguing, and their trade-offs |
| [`docs/known-limitations.md`](docs/known-limitations.md) | Every limitation, with the reason it is one |
| [`docs/architecture.md`](docs/architecture.md) | ADRs, component boundaries, production posture |
| [`docs/refined-prd.md`](docs/refined-prd.md) | Requirements, acceptance criteria, edge cases |
| [`docs/product-direction.md`](docs/product-direction.md) | The decisions taken before the PRD, and why |
| [`docs/development-plan.md`](docs/development-plan.md) | The ten build stages and their exit criteria |
| [`docs/release-verification.md`](docs/release-verification.md) | What "it works" means here |

A non-goal without a reason is an oversight; a non-goal with a reason is a design
decision. `known-limitations.md` exists so the difference is checkable.
