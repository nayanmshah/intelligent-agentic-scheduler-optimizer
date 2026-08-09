# Observability

> ```
> make opik        # start the local Opik stack -> http://localhost:5173
> make opik-eval   # push the golden set as a Dataset, score a run as an Experiment
> ```
>
> Opik is **optional by construction**. It ships enabled because a demo that never
> shows its telemetry is not showing much, but a stopped container is a pre-flight
> `warn`, never a failure, and never a slower answer.

---

## Two legs, different jobs

```
stage span ─→ FanOutTraceSink ─┬─→ InProcessTraceSink   synchronous, always on,
                               │                        the sole source for replay
                               └─→ OpikTraceSink        bounded queue, daemon thread,
                                                        drops rather than blocks
```

The in-process store is the **replay substrate** (FR-087/FR-088) — byte-identical
replay reads it and nothing else, verified with the container stopped. Opik is where
the same data goes to be *kept*, compared, and filtered.

**The Opik leg can never slow a patient-facing answer.** Emission is a `put_nowait`
onto a bounded queue; a full queue drops and counts; every exception on the worker
thread is counted and swallowed; there is no retry. A retry is precisely the thing
that would let an observability backend set the pace of a booking.

---

## Trace shape

**One trace per decision, one child span per stage** — not a flat trace per span,
which is what the first version did and which threw away the only structure worth
looking at.

| | |
| :-- | :-- |
| **input** | the patient's own words |
| **output** | the offers (when, provider, reason, score), any flags, any question |
| **metadata** | funnel counts, `llm_calls`, `gate_fired`, weight profile, origin state |
| **tags** | `fallback:<stage>`, `gate-fired`, `asked-a-question`, `limited-availability`, the origin state |
| **spans** | `extract` · `verify` · `reason` · `explain`, each with duration and implementation |

Model stages are typed `llm` and carry the model id, so Opik's own cost and latency
views work without being told anything extra. `reason` is typed `general` — it is
deterministic and calls nothing.

The tags are chosen to be *worth filtering by*: degradation, gate firings, and
questions are the three things you would actually pull up on their own. A tag that is
always present is a tag nobody uses.

### Why spans are buffered

A stage span ends when the stage ends; the decision exists only once all of them have.
So spans are held by `trace_id` and the Opik trace is assembled when the decision
arrives — bounded to 64 pending traces, oldest-first, because a request that errors
before recording a decision would otherwise pin its spans forever.

Absolute timestamps are reconstructed backwards from *now* using measured durations.
`Span` times with `perf_counter` deliberately — a clock read is a determinism hazard
(FR-102) — so span *offsets* are exact and only the origin is approximate. That is the
right trade for a display timeline, and it is the single clock read the structural
guard excuses by name.

---

## Datasets and experiments

`make eval` is the **gate**: a scorecard and an exit code, offline, in two seconds.
`make opik-eval` is the **history**: the same 54 golden cases as an Opik Dataset,
scored as an Experiment.

| Metric | Measures | Typical |
| :----- | :------- | ------: |
| `extraction_accuracy` | per-field agreement with the labels, partial credit | 0.91 |
| `top3_hit` | preferred slot appears in the offered three | 0.47 |
| `schedule_quality` | orphan minutes created by the top offer | 0.97 |
| `read_aloud` | reason lines pass the lint a receptionist needs | 1.00 |
| `faithful` | no offer asserts a booking; date and time echoed | 1.00 |

**Read `top3_hit` last and `schedule_quality` first.** The preference label leans
earliest-first, so `top3_hit` is the metric most biased against this system — the
argument is in [`known-limitations.md`](known-limitations.md) §2 and §11.
`schedule_quality` is measured from the schedule rather than from either ranker's own
output, so it is the one the labeller cannot flatter.

The experiment config records `llm_mode`, all three model ids, `prompt_version` and the
**seed digest** (ADR-11) — so a run is tied to the exact data it scored, and two
experiments are comparable only when they should be. Running it in both modes gives the
side-by-side:

```
fixtures-claude-haiku-4-5   extraction 0.9074  top3 0.4906  quality 0.9686
live-claude-haiku-4-5       extraction 0.9105  top3 0.4717  quality 0.9686
```

The task runs the **real orchestrator**, not a reimplementation, so a regression in the
shipped pipeline shows up here rather than in a parallel copy that drifted.

---

## PHI

`opik_redact_phi` defaults **False** because the dataset is 100% synthetic — the same
reasoning that makes `NoOpRedactor` the in-process default. A trace whose input reads
`[redacted]` is a trace nobody can debug from, and paying that cost for invented
patients buys nothing.

**Any deployment carrying real patient text must set it True.** The redactor is derived
from `Annotated[..., PHI]` on the domain model rather than a hand-maintained field
list, so it stays correct as fields are added, and flipping the flag is the whole
change required. Both halves — `span()` and `decision()` — are unit-tested.

---

## Confinement

A structural guard asserts the Opik SDK appears in exactly two places: the sink itself
and the offline eval CLI. It fails **loudly and separately** if the SDK ever appears
under `agents/`, `api/`, `orchestrator/`, `reasoner/`, `data/` or `domain/` — the
packages that run while a patient is waiting. That is the property FR-085 actually
protects, and it is checked directly rather than inferred from a filename list.
