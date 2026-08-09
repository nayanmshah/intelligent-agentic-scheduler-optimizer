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

One command. **Set `ANTHROPIC_API_KEY` and three of the four agent roles run against a
live model** — extraction, verification and explanation. Without a key it still boots
and answers every request, degrading to committed fixtures and then to deterministic
rules, with the header naming which path answered.

```bash
make test          # the deterministic suite: fast, free, no network
make test-live     # the shipped configuration, against the real API
make check         # lint + types + structural guards
make eval          # golden-set scorecard (fixtures: reproducible, free)
make eval-live     # the same scorecard against the real API
make release       # 3 cold starts with the network blocked (see below)
make opik          # start the local Opik stack (traces + experiments UI)
make opik-eval     # golden set as an Opik Dataset, scored as an Experiment
make audit         # known-CVE scan over both dependency trees
make coverage      # line coverage by module
make mutants       # mutation testing over the decision core
make fixtures      # re-record LLM fixtures. Online, deliberate, once.
```

**Requires** `uv` (pins Python 3.12) and Node 20+. An `ANTHROPIC_API_KEY` in `.env`
enables the live path; nothing else is needed.

**The clock is real.** The app runs on today's date like any application should; the
seeded schedule covers 2026-08-03 → 2026-08-28 and pre-flight fails loudly outside it.
The clock is *injected*, so tests, evals and release checks pin `SCHED_CLOCK=frozen` —
"next Thursday" means the same date on every CI run forever, while a demo runs on now.

---

## What it does

| | |
| :-- | :-- |
| **Takes it typed or spoken** | The request can be dictated: the browser transcribes into the box and the operator confirms before it runs. Speech never submits itself, so every quote below is still a quote of something a human agreed was said. |
| **Reads the request** | Six typed fields — date range, time window, urgency, provider preference, appointment type, exclusions — each with a confidence and **the verbatim span of the patient's words it came from**. |
| **Asks only when it matters** | Ambiguity triggers a question *only* if the readings produce different answers. *"My tooth's been bothering me"* runs as both a 30-minute exam and a 90-minute crown prep; the answers diverge, so it asks. When they agree, it proceeds. |
| **Enumerates exhaustively** | Every (operatory × day × start minute) candidate, filtered through a two-phase rule ladder. Nothing is ever deleted — rejections are annotated and kept, and `enumerated = offered + rejected` is reconciled on every request. |
| **Ranks on four axes** | Time fit, continuity, efficiency, block protection — as a score matrix times a weight vector, so the policy screen re-ranks instantly with zero model calls. |
| **Explains itself** | One sentence per offer, ≤25 words, second person, built only from facts the scorer emitted. A faithfulness gate and a read-aloud lint stand between the model and the operator. |
| **Never shows an empty screen** | If nothing fits, the nearest options are offered — **labelled**, leading with the gap, never silently substituted. |

---

## What the numbers say

Measured on 54 hand-labelled requests. `make eval-live` scores the shipped configuration;
`make eval` replays committed fixtures for a reproducible, free run.

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

**Extraction** is 96.3% (rules) vs 93.8% (LLM, measured live) overall — close, and they fail
differently: the model is 7.4 points better at reading clinical intent from symptom
language, and worse at citing provenance for what it inferred. Full table and the
convention bias in the same document.

**A live request takes ~3.9 s** (was ~15.9 s). Measured, then redesigned: latency
tracks output tokens, so the extraction wire format shrank to verbatim quotes with
offsets computed locally; every stage moved to Haiku 4.5 after per-stage benchmarks
showed the faithfulness gate and the deterministic verify floor make the cheap model
safe; and the semantic verify runs in parallel with reasoning and explanation, since
hypotheses come from the deterministic floor. The research and the trade-offs are in
`docs/latency-research.md` and ADR-21.

---

## How it is built

```
request text
   ↓  Intent Extractor      LLM   → fixtures → rules
   ↓  Constraint Verifier   LLM   → rules            (never sees the schedule)
   ↓  Schedule Reasoner     DETERMINISTIC, zero LLM — enumerate, filter, score, rank
   ↓  Explainer             LLM   → template          (behind a 6-check faithfulness gate)
three ranked offers
```

Three of the four roles call a model on every request. The fourth never does, and that
is the point: a model driving enumeration would miss candidates and make *"did it miss
anything?"* unanswerable.

Each of the four roles satisfies a `Protocol` with **two implementations**, one of
which needs no network. That is what makes the offline guarantee structural rather than
aspirational. The orchestrator between them is a plain state machine in ~150 lines —
agentic by architecture, deliberately not by framework: the coordination is code you
can read, not a library DAG.

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

241 deterministic tests + 8 live · 78% line coverage · 53.1% mutation score over the
decision core · lint and types clean · zero known CVEs in either dependency tree
(`make audit`) · determinism checked on every fixture-mode eval run.

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
| [`docs/latency-research.md`](docs/latency-research.md) | How 15.9 s became 3.9 s — measurements and trade-offs |
| [`docs/observability.md`](docs/observability.md) | Traces, datasets and experiments in Opik |
| [`docs/qa-report.md`](docs/qa-report.md) | Coverage, defects found after development, traceability |
| [`docs/security-review.md`](docs/security-review.md) | Findings, what was fixed, and what is accepted |

A non-goal without a reason is an oversight; a non-goal with a reason is a design
decision. `known-limitations.md` exists so the difference is checkable.
