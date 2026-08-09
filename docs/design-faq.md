# Design Rationale — FAQ

> The decisions that a reader is most likely to want argued rather than asserted.
> Each answer names the trade-off it accepted, not only the option it chose.
> Full detail lives in [`architecture.md`](architecture.md) (ADRs) and
> [`refined-prd.md`](refined-prd.md) (FR/NFR ids).

---

## On the shape of the system

### Why isn't the scheduler itself an LLM?

Because ranking appointment slots is a constraint search over a small, fully
enumerable space, and a model is strictly worse at that than exhausting it. Two
properties matter more here than fluency:

1. **"Did it miss anything?" must be answerable.** The reasoner enumerates every
   (operatory × day × start minute) cell and keeps every rejection with a reason
   (SD-1). The funnel counter on screen reconciles: `enumerated = offered + rejected`,
   with no leakage. A model that "considers options" cannot make that claim.
2. **The same request must produce the same answer.** Ranking is a pure function of
   `(constraints, schedule, profile, NOW)`. Nothing in it can drift between two
   identical requests — verified every run by FR-097.

The model is used where it is genuinely better: turning *"my kid gets out of school at
3, so after that"* into a time window, and turning a score vector into a sentence a
receptionist can read aloud.

> **LLMs at the edges, arithmetic in the middle.**

### Then why use a model at all?

Because the alternative is a keyword list, and the golden set shows exactly where a
keyword list breaks. The recorded model output is **7.4 points better at
`appointment_type`** than the rules extractor: it reads *"my gums have been bleeding,
due for maintenance"* as periodontal maintenance and *"is that a crown or just a
look?"* as an exam, where keyword matching reaches for a routine cleaning. Inferring
clinical intent from symptom language is the part that resists enumeration.

The full two-column comparison, including where the model is *worse*, is in
[`known-limitations.md` §11](known-limitations.md).

### Which roles actually call a model?

Three of four, on every request: the extractor, the verifier, and the explainer. The
reasoner never does, permanently — that is the thesis, not a gap.

Each is worth a model for a different reason. The extractor turns *"my kid gets out of
school at 3, so after that"* into a time window. The verifier catches what no lookup
can: given *"my crown fell off, can I get a cleaning?"* it returns "you mentioned a
fallen-off crown, so you likely need a crown fitting or exam, not a cleaning" — the
date is valid, the provider exists, the type is real, and the request still makes no
sense. The explainer turns a score vector into a sentence a receptionist can read
aloud.

### Why four agents rather than one big prompt?

Because they have different failure modes and different blast radii, and merging them
would merge those too. Splitting lets each one be independently swappable, testable,
and — critically — **independently replaceable by a deterministic implementation**.
Every agent satisfies a `Protocol` with two implementations (NFR-28): one that calls a
model, one that does not. That is what makes the offline guarantee structural rather
than aspirational.

The verifier is the clearest case: it validates the *extraction* against the world
(does this provider exist? is this date in the past?) and never sees the schedule. A
critic that could see the schedule would be tempted to critique the ranking, which is
the one thing that must stay deterministic.

### Why a hand-rolled orchestrator instead of an agent framework?

The whole state machine is 135 lines (`orchestrator/machine.py`, capped at 150 by
NFR-27). It has explicit stages, a per-stage timeout, a per-stage deterministic
fallback, and a trace emit at every hop. A framework DAG would put that control flow
inside library internals; here it is on one screen. When a stage misbehaves during a
demo, the difference between "read the function" and "read the framework" is the
difference between a 30-second answer and a shrug.

---

## On correctness

### Why is the clock injected instead of read from `datetime.now()`?

Three reasons, in increasing order of how much they would hurt:

1. **The seed data is fixed in time.** The dataset covers 2026-08-03 to 2026-08-28.
   Read the wall clock and the demo silently breaks the moment the machine's date
   leaves that window — every request lands outside the horizon and returns nothing.
2. **Determinism.** "Next Thursday" depends on today. If `NOW` were ambient, FR-097's
   check that two identical runs produce identical output would be comparing two
   different questions.
3. **The 14-day horizon and the urgency tiers are both relative to `NOW`.** A test that
   asserts "an emergency is offered inside 24 hours" is only meaningful if it controls
   what "now" means.

A structural guard (AST-level, `tests/structure`) fails the build if any module outside
`clock.py` calls `datetime.now()`, `date.today()`, or `time.time()`. `SystemClock`
exists and is one config flag away — the injection is the seam, not a limitation.

### Why is every datetime timezone-aware, and why only one conversion module?

A dental practice runs on local wall-clock time; a server runs on UTC. Every bug in
this class comes from a value crossing that boundary without anyone noticing. So the
conversion happens in exactly one module (`data/timezone.py`, NFR-32) and a structural
guard fails the build on any naive `datetime` construction elsewhere.

DST is the reason this is not over-engineering. A spring-forward day contains an hour
that does not exist; a fall-back day contains one that happens twice. Both enter a
14-day horizon twice a year, in every zone. The fixtures for both already exist and
pass, even though neither day falls inside the seeded window — that is the kind of bug
that is invisible until the Sunday morning it is not.

### Why is booking a conditional write rather than a read-then-write?

Because check-then-write cannot fail at one seat and double-books at two — the worst
possible pairing of severity and undetectability. `commit_booking` is a compare-and-set
against a per-`(operatory, day)` version (ADR-18/FR-069); a stale version loses and is
told so.

v1.0 is explicitly single-operator (NFR-08), so this is work done ahead of need. It is
the one piece of multi-seat groundwork worth doing early, because retrofitting
atomicity means auditing every write path rather than one function.

### What stops the explainer from inventing a reason?

Structure first, then a gate:

- The scorer emits a `Rationale` — the facts, already resolved (SD-2). The explainer
  receives *only* those facts. It has no access to the schedule, so there is nothing to
  invent from.
- A **faithfulness gate** (FR-062) then runs five checks over the generated sentence:
  every claim traces to an emitted fact, no fact is contradicted, no number appears
  that was not given, the named provider matches, the resolved date and time appear.
  Failure falls back to the template sentence and is recorded in the trace.
- A **read-aloud lint** (FR-065) enforces that the sentence is one a human can say to a
  patient: bounded length, no internal jargon, no banned tokens (`overflow`,
  `escalate`, `candidate`).

The gate firing is silent to the operator and loud in the trace (NFR-16). A fallback
that is invisible in both places is indistinguishable from a system that never fails.

---

## On the numbers

### Your top-3 hit rate (45.3%) is *below* the naive baseline (47.2%). Why ship it?

Because that comparison is biased against the system, and the write-up says so rather
than hiding it.

The "preferred slot" label is a heuristic — *earliest non-fragmenting feasible slot
with the patient's usual provider*. That objective is much closer to the **naive
baseline's** (earliest) than to this system's (a weighted trade-off across time-fit,
continuity, efficiency and risk). Scoring a trade-off ranker against an earliest-first
label measures how often it agreed to be earliest-first.

The unbiased comparisons are measured from the schedule itself, not from either
ranker's own numbers:

| Measure | This system | Naive first-available |
| :------ | ----------: | --------------------: |
| Orphan minutes created per booking | **1.3** | 14.6 |
| Protected block minutes consumed | **0.0** | 3.1 |

Eleven times fewer unusable gaps, and it never eats a restorative block. That is the
claim the product actually makes.

The honest fix is not to tune the heuristic until the system wins — that is fitting to
the referee. It is to have 2–3 practising schedulers label independently and report
inter-rater agreement. `GoldenLabel.labeler` exists for that. And if real schedulers
disagree substantially with *each other*, that disagreement is itself the business case
for a configurable policy layer.

### You fitted the weights and got a 70.7% hit rate. Why isn't that the default?

Because it is a diagnostic of the labels, not a product win. The fitted vector
(`0.70 / 0.25 / 0.05 / 0.00`) collapses onto time-fit and continuity — precisely what
the label heuristic optimises for. Fitting to a proxy label teaches the model the
proxy. All four axes also show a flat region ≤ 0.10 wide, which says the same thing
from the other side: a robust fit is flat across a *broad* band, not a narrow one.

So the shipped default is the hand-set General Practice profile, and the fitted vector
is committed unapplied. "Our weights are fitted" would be a misleading claim in its
current state.

### Why measure minutes instead of revenue?

The system has no fee schedule. A dollar figure derived from synthetic data and an
invented price list is unfalsifiable — it looks stronger on a slide and is worth less
in a conversation. Orphan minutes and protected-block minutes are measurable today; a
practice's own fee schedule is what converts them into money, and that conversion
belongs to the practice.

---

## On the engineering

### Why occupancy bitmaps and prefix sums?

Feasibility is asked thousands of times per request — every candidate start minute
against every operatory and provider. A minute-resolution bitmap with a precomputed
prefix sum answers "is this interval free?" in O(1) by subtracting two integers
(ADR-05). The doctor-check question is different in kind — *is there a dentist free for
the whole check window, contained inside this appointment?* — so it uses interval
containment over an OR-prefix index rather than overlap.

Caches invalidate per `(resource, day)` rather than by a global version counter
(ADR-16): one booking should not invalidate a fortnight.

### Why is the score matrix separate from the weight vector?

Because axis values do not depend on the weights (ADR-06). Computing them once and
multiplying by a weight vector means the policy panel's sliders re-rank instantly, with
no re-enumeration, and the contribution bar can show exactly what each axis
contributed. It also makes the rank-stability check cheap: perturb the vector, re-dot,
see whether the top three move.

### What are the structural guards, and why AST-level?

Four rules, enforced by parsing the source rather than by convention (FR-102, FR-054):

| Guard | Catches |
| :---- | :------ |
| No clock reads outside `clock.py` | ambient time sneaking back in |
| No naive `datetime` construction outside `timezone.py` | the tz boundary leaking |
| Import direction: the reasoner may not import the explainer | prose contaminating the decision |
| No magic weight literals inside functions | policy hard-coded where it cannot be seen |

They earned their place: during the build they caught three real violations, including
the reasoner importing the explainer to build a sentence. The fix was to move the prose
into `agents/explainer/render.py` — the code changed, not the guard.

### Does the model actually fit the latency budget?

**No, and it ships live anyway — that is a decision, not an oversight.** A full live
request takes ~16 seconds: ~7s extract, ~4s verify, ~5s explain, sequential because each
stage needs the last one's output. Disabling adaptive thinking changes it by 0.1s; the
cost is producing six fields each carrying a confidence, a derivation rule and a
verbatim span, and that provenance is the reason the interpretation strip is
trustworthy.

The alternative was defaulting to replayed fixtures, which makes the product's headline
capability the one thing nobody ever sees working. A demo of an agentic system that
runs no agents is not a demo of an agentic system.

The cost of the choice is bounded by the fallback ladder: a slow or failed call
degrades to fixtures and then to rules rather than failing. The four routes that would
actually close the gap — streaming, splitting provenance off the critical path,
rules-first-then-model, dropping verify on high-confidence requests — are named in
[`known-limitations.md` §12](known-limitations.md), and none are implemented.

### Why commit LLM fixtures instead of mocking?

A mock encodes what the author *thinks* the model returns. A fixture is what it
*actually* returned, recorded once against the live API with every source span verified
verbatim before it is written (`make fixtures` refuses to record a fabricated span).
The cache key includes the request text, the model id and the prompt version, so
bumping any of the three invalidates only its own entries.

Fixtures are the **fallback**, not the default — that inverted with ADR-20, and live mode
deliberately does not read the cache at all. Serving a recording while the header says
"Live models" would make the capability invisible exactly when someone is watching.

What the cache still guarantees is the degraded path: when the model is unreachable, a
miss raises rather than silently reaching for the network — which it used to do, making
"Offline · fixtures" on screen quietly untrue.

### How do you know it still works when the model is unreachable?

It is enforced, not asserted. `scripts/release-check.sh` runs the entire product —
preflight, test suite, eval scorecard, HTTP server, real requests — with outbound
connections blocked at the socket layer (`scripts/offline/sitecustomize.py`, injected
via `PYTHONPATH` so the application does not know it is being tested). Loopback stays
open so the real server can be driven over HTTP.

Only dependency installation is allowed network access, and the script separates the
two phases explicitly. See [`release-verification.md`](release-verification.md).

---

## On what was deliberately not built

Voice input, authentication, multi-tenancy, a database, and full WCAG AA conformance
are all cut, each with a stated reason, in
[`known-limitations.md`](known-limitations.md). The short version: a non-goal without a
reason is an oversight; a non-goal with a reason is a design decision. That page exists
so the difference is checkable.
