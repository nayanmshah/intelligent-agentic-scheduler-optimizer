# Refined PRD — Intelligent Agentic Scheduling Optimizer

> **Reading note.** This is the *refined, MVP-scoped* PRD for **v1.0**. It converts the approved
> product direction in `docs/product-direction.md` into individually testable requirements.
> Decisions marked ✅ DECIDED there are settled input, not proposals. Specification detail
> introduced here to make a settled decision *testable* is labelled **[spec-refinement]**. Anything
> not covered by the original product brief or the product direction is labelled
> **[ASSUMPTION A-nn]** and registered in §15.
>
> **The ordering principle behind this document, stated once so the requirement priorities make
> sense:** *every recommendation this system makes must be explainable and justifiable from its own
> recorded evidence.* A requirement that makes the system more explainable, more measurable, or more
> resistant to runtime failure outranks a requirement that makes it more capable. That ordering is
> deliberate, not conservative — an unexplainable scheduling recommendation is one a front-desk
> operator will not act on, and one an office manager cannot govern.

---

## 1. Basic Information

| Field          | Value                                                                                                                   |
| :------------- | :---------------------------------------------------------------------------------------------------------------------- |
| Project Name   | Intelligent Agentic Scheduling Optimizer                                                                                |
| Priority       | **P0** — fixed delivery date; the v1.0 scope in §6 is sized to it                                                       |
| Target Release | **v1.0 — stakeholder demo build, 2026-08-10 (Mon)**                                                                     |

### Create

| Nayan | User Name             | Create Date |
| :---- | :-------------------- | :---------- |
| Nayan | gr8.nayan@gmail.com   | 2026-08-08  |

### Sign-Off

| Role             | Approver Name | Sign-Off Date | Status (Pending / Approved / Needs Revision) |
| :--------------- | :------------ | :------------ | :------------------------------------------- |
| PM               | Nayan         | 2026-08-08    | **Approved**                                 |
| Engineering Lead | Nayan         | 2026-08-08    | **Approved**                                 |
| Design           | Nayan         | 2026-08-08    | **Approved**                                 |

> **Recorded deviation.** The standard gate expects a *distinct* approver per role. On this project
> one person holds all three, and has signed all three knowingly. Noted here rather than left
> implicit, because it means no role provided an independent challenge to the others — the eval
> scorecard (§7 UC-13) and the risk register (§14) carry that burden instead.

---

## 2. Problem Statement

### What problem are we solving?

**The job-to-be-done is not "book an appointment" — it is "collapse the investigation."**

Booking is trivial; every practice-management system does it. What is expensive is the **45–90
seconds of dead air** while a front-desk person mentally parses a sentence like *"whatever works
next week, I have PT on Tuesdays"* and then hand-scans six operatory columns across five days with
a patient waiting on the phone.

Dental scheduling is a **multi-resource constraint problem**, not a calendar lookup. A bookable
slot requires *provider* availability **and** *operatory* availability **and** the correct
appointment-type duration **and** — for hygiene — a **credentialed dentist free for a ~10-minute
exam inside the appointment**. A slot can look wide open on the grid and be structurally
un-bookable. That invisibility is why the manual scan is slow and why it is inconsistent.

**Two clocks conflict, and today they produce two different answers:**

| Clock                       | Unit    | Pushes toward                    | Cost of winning outright                                                  |
| :-------------------------- | :------ | :------------------------------- | :------------------------------------------------------------------------ |
| Patient-on-phone latency    | seconds | "first thing that's open"        | fragments the day; burns a prime restorative block on a 30-minute prophy  |
| Schedule quality            | dollars | "the slot that fits the day"     | dead air, hold time, patient abandons                                     |

> **Product thesis:**
> *Today the fast answer and the good answer are different answers. This product makes them the
> same answer.*

### Who has this problem?

- **Front-desk staff / treatment coordinators** — feel it every call, on the clock, in front of the
  patient.
- **Office managers** — feel it as inconsistency: the schedule's shape depends on who answered the
  phone that day.
- **DSO operations leads** — feel it as non-scalability: quality of scheduling decisions cannot be
  standardised across dozens or hundreds of offices by training alone.
- **Patients** — feel it as hold time and as being offered a slot that does not actually work for
  them.

### How do they experience this problem today?

1. Request arrives as free text or speech: *"Can I come in next Thursday after 3?"*, *"I need
   something first thing tomorrow, it's urgent"*, *"Whatever works next week, I have PT on
   Tuesdays."*
2. The staffer silently resolves date, time window, urgency, appointment type and provider
   preference — reading between the lines, from memory, with no record of how they resolved it.
3. They scan provider columns and operatory columns across several days, holding duration and
   turnover in their head.
4. They hold the doctor-check requirement in their head too, or they forget it and book something
   that has to be undone.
5. They offer whatever they found first. Nobody — including them — can say what they *didn't*
   consider.

**The two failure signatures of the manual process:** it is *slow*, and it is *unrepeatable*. The
same request on Tuesday with a different staffer produces a different answer, and neither answer
comes with a reason.

---

## 3. KPIs & Business Justification

**The business case has two layers and this PRD keeps them separate on purpose.**
**Layer A** is *delivery quality* — the properties that make v1.0 trustworthy enough to put in
front of a stakeholder and to hand to another engineer. **Layer B** is the *product value* the
system delivers to a dental practice. Conflating the two is how products end up with unfalsifiable
claims, so they are measured separately.

### Layer A — Delivery-quality KPIs

| KPI | Current Baseline | Expected Impact | How Measured | Timeline to Impact |
| :-- | :--------------- | :-------------- | :----------- | :----------------- |
| **Runtime reliability** | Unknown | **0 unrecovered failures** across ≥ 3 full cold-start runs of the end-to-end flow | Scripted cold-start runs from a clean machine state with networking disabled; failure log retained | By 2026-08-10 |
| **Requirement verification coverage** | 0 of 108 | **Every MUST requirement** has an automated check where the criterion is automatable | Test suite mapped to FR IDs; unmapped MUSTs reported | By 2026-08-10 |
| **Risk-mitigation coverage** | 0 of 16 | **Every risk in the §14 register** has (a) a documented mitigation and (b) a verifiable artifact — a test, a metric, or an in-product surface | §14 register cross-referenced to a requirement ID or eval metric per row | By 2026-08-10 |
| **Code maintainability** | n/a | An engineer new to the codebase can trace one request end to end in **≤ 5 minutes** | Orchestrator ≤ 150 lines; every agent a `Protocol` with two implementations (NFR-27, NFR-28); measured by an onboarding walkthrough | By 2026-08-10 |
| **Reproducibility** | n/a | **Byte-identical** results across runs and across machines in fixture mode | CI determinism check (FR-097) | By 2026-08-10 |

### Layer B — Product-value KPIs

| KPI | Current Baseline | Expected Impact | How Measured | Timeline to Impact |
| :-- | :--------------- | :-------------- | :----------- | :----------------- |
| **Front-desk investigation time per request** | 45–90 s (`product-direction.md` §1), midpoint 60 s | → ~10 s confirm for ≥ 85% of requests | Top-3 hit rate on the golden set as the offline proxy; in-session counter of manual-grid opens | Demonstrated in-product |
| **Recovered front-desk hours per office per year** | ~104 h/yr of investigation ([ASSUMPTION A-05]) | ~85 h/yr recovered | Arithmetic from the two rows above; the assumptions are stated explicitly wherever the figure is used | Modelled, not measured |
| **Unusable-gap minutes created per booking** | Naive first-available baseline, measured | Strictly lower | Eval harness: orphan-gap minutes created (gaps < 30 min) vs. the first-available baseline over the golden set | Measured in harness |
| **Prime-time block consumption by low-production types** | Naive baseline, measured | Strictly lower | Eval harness: count of protected-block minutes consumed by types below the block's production floor | Measured in harness |
| **Decision consistency** | Staff-dependent, unmeasurable today | Byte-identical repeat decisions | Determinism check in CI (§7 UC-13) | Measured in harness |

**Deliberate omission — production dollars.** The harness measures **minutes and counts, never
dollars.** Production-dollar figures are STRETCH and are *not* claimed. The system does not have a
practice's fee schedule, and a revenue figure derived from synthetic data and an invented fee
schedule would be unfalsifiable. Minutes and protected-block consumption are measurable today; a
practice's own fee schedule is what converts them into dollars, and that conversion belongs to the
practice, not to this PRD.

### Revenue / Business Impact

- **Estimated impact:** ~85 recovered front-desk hours per office per year ([A-05]) plus a measured
  reduction in schedule fragmentation and in protected-block erosion. At multi-office scale the
  *policy* value dominates the labour value: centrally managed weight profiles turn scheduling
  judgment into a configurable, auditable asset instead of tribal knowledge held by whoever answers
  the phone.
- **Customer segments affected:** single-location general dental practices (the profile shipped in
  v1.0); multi-location DSOs (**modelled but not exercised** in v1.0 — see §6 and `Location` in §8).
- **Strategic alignment:** practice-management platforms in the DSO segment are multi-location by
  nature. `Location` is first-class and providers carry per-day location assignment so that the
  multi-office extension is a data question rather than a rewrite.

### Why is this essential now?

- **The manual process is the bottleneck and it is not improving.** Every week without this,
  each office spends roughly two hours of front-desk time investigating rather than confirming
  ([A-05]), and schedule quality stays dependent on who answered the phone.
- **What happens if we delay:** the cost is recurring and the inconsistency compounds — there is no
  accumulating asset in the manual process, because no manual decision is recorded with its reason.
- **Contractual / regulatory drivers:** none binding on v1.0 (100% synthetic data, no PHI). The
  production HIPAA posture is nonetheless specified in §8 *Privacy & Sensitivity* **now**, because
  it constrains the architecture: observability is a PHI leak vector, and a redaction seam is cheap
  to design in and expensive to retrofit.
- **Delivery date:** v1.0 is scheduled for a stakeholder demonstration on **2026-08-10**; the scope
  triage in §6 is sized to that date.

---

## 4. Success Criteria

### How will we measure success?

The four metrics carried forward from `docs/product-direction.md` §1, each made measurable by the
eval harness (§7 UC-13). **Every one of them is readable directly from the product's own scorecard
— none requires external instrumentation.**

| # | Metric | Current State | Target | How Measured |
| - | :----- | :------------ | :----- | :----------- |
| 1 | **Confirm-without-investigating rate** — the booked slot was in the offered top 3 and no calendar grid was opened | Manual: 0% (the grid is always opened) | **≥ 85%** | **Offline proxy:** top-3 hit rate against the human-preferred slot on the ~40-request golden set. **In-session:** a counter increments on every manual-grid open; the target state is a session in which the operator never opens the grid. Both surfaced on the eval scorecard. |
| 2 | **Time-to-offer** — request submitted → three ranked options rendered | Manual: 45–90 s | **3.9 s p50 live (measured, the shipped path, ADR-21); < 2 s degraded call** (p95 over the golden set) | Trace spans: `t(render) − t(submit)`, p50 and p95 reported per mode by the harness and shown in the trace panel per request. |
| 3 | **Schedule-quality delta vs. naive first-available** | Naive baseline computed by the harness over the same golden set | **Strictly better** on orphan-gap minutes created and on protected-block minutes consumed; **non-inferior** on human agreement | Harness runs both rankers over the golden set and emits a head-to-head table. **Where the delta is small for a request class, the harness reports it and names the class** — knowing where the product does not add value is part of the measurement, not an omission from it. |
| 4 | **Consistency** — same request, same answer, every time | Staff-dependent; unmeasurable | **Byte-identical** | Harness runs the golden set twice in fixture mode and diffs the serialised `DecisionRecord`s; any diff fails the run. Also enforced in CI. |

**Metric 2 has a hard product meaning, not a vanity meaning:** beyond ~5 seconds the human opens
the calendar anyway and the entire value proposition is lost. It is therefore a *functional*
threshold, and the per-stage timeout/fallback ladder in NFR-03 exists to defend it.

### What does "done" look like?

Done is the conjunction of all of the following. Each is independently checkable.

1. **The end-to-end flow runs cold, from a clean machine state, with networking disabled, three
   times, with zero unrecovered failures.**
2. **Every MUST requirement in §7 passes its acceptance criterion**, verified by automated test
   where the criterion is automatable.
3. **The eval scorecard renders in-product** with: per-field extraction accuracy, top-1/top-3
   agreement, the naive-baseline head-to-head, latency percentiles, the weight-sensitivity curve,
   the determinism check, and **a named list of the failing cases**.
4. **A reason line from any offered card can be read aloud verbatim to a patient** and passes the
   read-aloud lint (FR-065) for 100% of golden-set outputs.
5. **Changing a weight in the policy panel re-ranks the cards in under 300 ms**, with the
   rank-stability number visible before and after.
6. **Replaying any captured decision reproduces it byte-for-bit** from the in-process store, with
   the observability backend stopped.
7. **The documentation package exists:** one architecture diagram, a demo script covering the
   reference scenarios, a design-rationale FAQ, and a known-limitations page.
8. **Everything that can fail independently has a fallback on the request path.** The model is
   called three times per request and any stage that fails drops to committed fixtures and then
   to deterministic rules; no container, no machine-clock dependency, no runtime data generation
   — and one command to boot. *(Restated with ADR-20. The original read "nothing that can fail
   is on the request path", which was true when the model was opt-in and is not now.)*

---

## 5. Users & Personas

| User Type | Description | Primary Goal |
| :-------- | :---------- | :----------- |
| **Front-Desk Operator** (treatment coordinator) — *the user* | Answers the phone with a patient live on the line. Keyboard-first, high call volume, low tolerance for a second screen. Not a scheduling theorist. | **Confirm, don't investigate.** Turn a sentence into a bookable, defensible offer inside the patient's attention span — and be able to say the reason out loud without translating it. |
| **Office Manager / DSO Ops Lead** — *the buyer* | Owns the shape of the schedule and its economics. Answers to production targets. At DSO scale, owns policy across many offices. | **Make good scheduling judgment repeatable and configurable** rather than dependent on who answered the phone — and be able to prove the system is doing what it claims. |
| **Patient** — *beneficiary, never a user in v1* ([ASSUMPTION A-02]) | The person on the phone. Consumes the output through the operator's voice. Never touches the UI. | Get an appointment that actually works, quickly, and hear *why* it was offered in language they understand. |

### User Context

**Surface separation is a requirement, not a layout preference.**

| Surface | Persona | Contains | Explicitly does **not** contain |
| :------ | :------ | :------- | :------------------------------ |
| **Operator Console** (`/`) | Front-Desk Operator | Request box, editable interpretation strip with source spans, funnel counter, three offer cards with one primary action each (Hold), why-not ledger (collapsed), counterfactual line | **No weight sliders.** Putting weights in front of the front desk invites per-call fiddling and destroys the consistency the product sells. |
| **Practice Policy Panel** (`/policy`) | Office Manager / DSO Ops Lead | Named weight presets, per-axis sliders, live re-rank, contribution bars, rank-stability indicator, eval scorecard, no-show policy hook (off) | Not reachable from the operator flow; no per-request state |
| **Trace / Replay Panel** (`/traces`) | Office Manager / DSO Ops Lead — audit and diagnostics | Per-hop spans, latency, token cost, fallback and gate firings, byte-identical replay | Not part of the operator's task flow |

**The single copy-defining constraint.** *The reason line must be readable aloud, verbatim, to a
patient on the phone.* This is not a tone guideline — it is a testable requirement (FR-065) with a
lint that runs over every golden-set output. It decides the copy style for the entire product: no
scores, no axis names, no internal identifiers, no jargon, resolved weekday + date + clock time
always echoed.

**Every staff override is the most valuable data the product generates** — a labelled
counterexample, not a failure (FR-075).

**Operational actor (not a persona):** the **office's own IT or operations contact**, who installs
and starts the system and runs it in an evaluation environment. Requirements that exist for that
actor are collected in UC-14 and in §11. They are first-class, not boilerplate: a scheduling
assistant that only works when the network is up is not a scheduling assistant.

---

## 6. Scope

### Critical Path Journey (the one journey that proves the value)

> **Unstructured request → extracted constraints (with confidence + verbatim source spans) →
> enumerated candidates → hard-constraint feasibility with a retained rejection ledger → urgency
> gate → weighted ranking → deterministic, diverse top 3 → one plain-language reason per option
> that can be read aloud to the patient → soft hold → confirm.**

Everything in MUST exists to make that path work and to make it *inspectable*. Everything in SHOULD
exists to make it *justifiable and governable*. Everything in STRETCH can be deferred without
losing the core value.

### What's IN scope (MVP)?

Carried from `docs/product-direction.md` §8. Triage is preserved verbatim in intent; requirement
IDs are added for traceability.

#### MUST — the verifiable core

| Item | Requirements |
| :--- | :----------- |
| Data model + seeded, **committed** dataset with the eleven edge cases; injectable reference clock | §8; FR-102, FR-103 |
| Extractor (LLM + rule fallback + fixtures) with per-field confidence and verbatim source spans | UC-01 (FR-001…FR-008) |
| Deterministic reasoner: enumeration, hard constraints incl. doctor-check overlay, **rejection ledger**, four axes + prime-time, urgency gate, tiebreak chain, top-3 diversity | UC-03, UC-04, UC-05, UC-06, UC-07 |
| Templated explanations (faithful by construction) + why-not text | FR-059, FR-060, FR-065, FR-030 |
| FastAPI endpoints + React three-card UI + editable interpretation strip + funnel counter | UC-01, UC-04, UC-07; §12 |
| In-process trace store + replay panel | UC-12 |
| Golden dataset (~40) + eval harness producing the scorecard | UC-13 |
| One-command boot; live by default, still answers with no network | UC-14; NFR-08, NFR-09 |
| Architecture diagram, demo script, design-rationale FAQ, known-limitations page | §13 deliverables; §14 |

#### SHOULD — what makes it governable and provable

| Item | Requirements |
| :--- | :----------- |
| LLM explainer **with the faithfulness gate** (template stays the fallback) | FR-061…FR-064, FR-066 |
| Live weight tuner with contribution bars + **rank-stability indicator** | UC-11 (FR-076…FR-084) |
| Counterfactual / relaxation panel | UC-08 (FR-055…FR-058) |
| **Weight fitting to golden labels + sensitivity curve** | FR-098, FR-099 |
| Constraint-verifier agent + single clarifying question with the decision-relevance test | UC-02 (FR-009…FR-015) |
| Soft-hold + confirm booking (session copy + reset) | UC-10 (FR-068…FR-074) |
| Opik wired behind `TraceSink` (optional at runtime) | FR-089, FR-090 |
| Manual-comparison grid + time-on-task measurement | FR-107; override capture FR-075 |

#### STRETCH — deferrable without losing core value

Multi-hypothesis fan-out beyond type and relative-date ambiguity · **bump-candidate suggestions**
(FR-037) · production-dollar figures · waitlist / ASAP gap-fill · multi-location *routing* (the
model stays — see §8) · no-show-risk policy hook (FR-084, built behind a flag, **OFF by default**).

> **Reconciliation note [spec-refinement].** `product-direction.md` §3 places bump candidates inside
> the urgency-gate narrative while §8 lists them under STRETCH. Resolved without changing either
> decision: the **empty-tier escalation path and the emergency-hold unlock are MUST** (FR-035,
> FR-036) — the product must never return an empty list; **bump-candidate *suggestions* are
> STRETCH** (FR-037). If FR-037 is deferred, FR-036 alone satisfies "never return nothing."

#### Voice input — shipped as a front door ✅ DECIDED *(reversed 2026-08-09)*

The original product brief allows "text or speech." This was cut on the grounds that transcription
adds a runtime failure mode for **zero decision quality** — constraint extraction operates on text
either way, so speech only changes how the text arrives.

**That reasoning was right about the pipeline and wrong about the conclusion.** Precisely because
speech only changes how the text arrives, it can be added as a *front door* that touches nothing
downstream: the browser's Web Speech API writes a transcript into the same box, the operator
confirms it, and `POST /api/requests` receives text exactly as it always did. The pipeline cannot
tell the difference — FR-110 has a test asserting a dictated request and a typed one produce an
identical decision.

The failure mode named in the original cut is real and is handled rather than avoided: dictation
**never submits**, so a mis-transcription is something an operator sees and corrects rather than
something the audit trail records as the patient's words. See FR-110 and `known-limitations.md`
for what speech still costs (accuracy on proper nouns, and where the audio goes).

### What's OUT of scope?

**Explicit non-goals, each with its rationale. A non-goal without a reason is an oversight; a
non-goal with a reason is a design decision.**

| Non-goal | Rationale |
| :------- | :-------- |
| **A real database** (SQLite at most) | Committed JSON fixtures are more legible to a reviewer than a schema, and the whole dataset fits on one screen. A database adds migration and setup surface for zero decision quality at this scale. **The decision is about the store, not the boundary:** NFR-29 puts a `ScheduleRepository` `Protocol` between the reasoner and whatever backs it, so adopting a database later is an implementation of an existing interface rather than a change to the scheduling logic. |
| **Auth / RBAC** | Zero decision quality, real build cost. The surface separation that matters in v1.0 is a route, not a role — and §11 says so explicitly rather than implying a security boundary that does not exist. |
| **An agent framework** (LangGraph, CrewAI) | A hand-rolled ~150-line state machine can be read end to end; a framework DAG hides control flow behind a runtime the reader must learn first. Legibility of the orchestration *is* the point here. |
| **Vector store / RAG** | There is nothing to retrieve — the constraints are structured data, not documents. |
| **Streaming token UI** | The answer is a ranked list, not prose; streaming would make a 2-second response *feel* slower. |
| **Containerised app deploy / k8s** | v1.0 runs on a single machine; a container in the request path is an additional failure mode, not a feature. |
| **ILP / OR-tools** | One request against a fixed schedule, hundreds of candidates — exhaustive enumeration is exact, sub-millisecond, and fully explainable. An ILP returns the same answer with less legibility. |
| **CI beyond one test + eval workflow** | The one workflow that matters proves reproducibility; additional pipelines add maintenance for no verification gain. |
| **Multi-tenancy — isolation only** *(rationale amended)* | The **isolation** half of tenancy is infrastructure and stays out of v1.0. The **policy-scoping** half is not, and the original rationale was wrong to fold the two together: at multi-practice scale a `WeightProfile` needs an owner and an inheritance chain — platform default → group policy → location override — and *who may override what* is a scheduling product decision, not a deployment one. v1.0 therefore ships the **scope field** (§8) and defers only the **resolution logic** (NFR-30). Adding a nullable field now costs nothing; adding an owner to a table that already has rows costs a migration plus a backfill of guesses. |
| ~~**Voice / speech input**~~ *(now in scope — FR-110)* | Shipped as a front door: the browser transcribes into the request box and the operator confirms. Kept honest by the rule that dictation never submits, so the pipeline, the provenance spans and the audit trail are all unchanged. |
| **Global schedule re-optimisation** | Moving already-booked patients is a consent problem before it is a math problem. |
| **Patient self-scheduling** | Different product, different liability; the human confirmation step is load-bearing by design. |
| **Autonomous booking (no human confirm)** | The promise is "confirm, not investigate" — not "book without looking." A confidently-wrong date must have a human between it and the patient. |

---

## 7. Use Cases

### Traceability index

| UC | Name | Persona | Requirements | Triage |
| :- | :--- | :------ | :----------- | :----- |
| UC-01 | Interpret an unstructured request | Front-Desk Operator | FR-001 … FR-008 | MUST |
| UC-02 | Verify the interpretation; ask at most one question | Front-Desk Operator | FR-009 … FR-015 | SHOULD |
| UC-03 | Enumerate candidates and apply hard feasibility | System (Schedule Reasoner) | FR-016 … FR-026 | MUST |
| UC-04 | Show what was rejected and why | Front-Desk Operator | FR-027 … FR-031, FR-109 | MUST |
| UC-05 | Apply the urgency gate; never return nothing | Front-Desk Operator | FR-032 … FR-038 | MUST (FR-037 STRETCH) |
| UC-06 | Score surviving candidates on four axes | System (Schedule Reasoner) | FR-039 … FR-047 | MUST |
| UC-07 | Produce a stable, diverse, explained top 3 | Front-Desk Operator | FR-048 … FR-054 | MUST |
| UC-08 | Offer a counterfactual relaxation | Front-Desk Operator | FR-055 … FR-058 | SHOULD |
| UC-09 | Generate a phone-readable reason, faithfulness-gated | Front-Desk Operator | FR-059 … FR-067 | MUST (FR-061…064, 066 SHOULD) |
| UC-10 | Hold, confirm, and reset a booking | Front-Desk Operator | FR-068 … FR-075 | SHOULD |
| UC-11 | Configure practice scheduling policy | Office Manager / DSO Ops Lead | FR-076 … FR-084 | SHOULD (FR-084 STRETCH) |
| UC-12 | Inspect and replay a decision trace | Office Manager / DSO Ops Lead | FR-085 … FR-091 | MUST (FR-089, FR-090 SHOULD) |
| UC-13 | Run the eval harness and read the scorecard | Office Manager / DSO Ops Lead | FR-092 … FR-101 | MUST (FR-098, FR-099 SHOULD) |
| UC-14 | Run the system reliably and reproducibly | Office Manager / DSO Ops Lead | FR-102 … FR-108 | MUST (FR-107 SHOULD) |

### Load-bearing structural requirements

Three things that are **cheap to build in now and expensive to retrofit**. They are called out here
because they are architectural obligations disguised as product requirements, and the architect
must not treat them as implementation detail.

| # | Structural decision | Why it must be built in from the start | Requirement |
| - | :------------------ | :------------------------------------- | :---------- |
| **SD-1** | **The pipeline annotates rather than deletes.** No stage removes a candidate from the working set; every stage attaches an annotation (`feasible: false`, `rejection_reason`, `tier`, `score`, `rank`). | The rejection ledger — the single most domain-credible moment in the demo — becomes **free**. Retrofitting it means re-plumbing every filter to also emit its casualties. | **FR-027** |
| **SD-2** | **The `Rationale` object is emitted *by the scorer*, not assembled afterwards.** The explainer is a renderer over facts the scorer already produced. | Explanations then **cannot disagree with the ranking** — the failure mode is structurally eliminated rather than tested for. Retrofitting means the explainer grows its own view of "why," which will drift. | **FR-059** |
| **SD-3** | **`NOW` is injected everywhere; seed data is committed, never generated at runtime.** No `datetime.now()` outside the clock provider; no seeding at startup. | *"Next Thursday"* must resolve to the same date in every run, on every machine, regardless of when the run happens — otherwise no regression test on relative dates is stable and no evaluation is repeatable. Retrofitting a clock through a codebase that calls `now()` in six places is a class of heisenbugs. | **FR-102**, **FR-103** |

**Requirement notation.** `SHALL` = mandatory. **AC** = acceptance criterion (the check that can
fail). Triage tag = MUST / SHOULD / STRETCH per §6.

---

### Use Case 1: Interpret an unstructured request into typed constraints

**As a** Front-Desk Operator **I want to** paste or type the patient's own words and immediately see
what the system understood, with the exact words it understood it from **So that** I can trust the
search that follows, and correct it in one click when it is wrong.

**Steps:**

1. Operator selects a patient (or proceeds anonymously) and types/pastes the request text, then
   presses Enter.
    - System routes the raw text plus patient context to the Intent Extractor and shows a
      per-stage progress indicator.
2. Operator reads the interpretation strip.
    - System renders one chip per extracted field, each showing the resolved value, a confidence
      band, and the **verbatim source span** from the request that produced it.
3. Operator clicks a chip that is wrong and edits it.
    - System re-runs the deterministic pipeline from the edited constraints — **without a new LLM
      call** — and re-renders the offers.

**Acceptance Criteria:** all of FR-001 … FR-008 pass.

**Functional Requirements**

- **FR-001 — Typed extraction output.** The Intent Extractor SHALL convert raw request text plus
  patient context into a typed `RequestConstraints` object containing: `date_range`,
  `time_window`, `urgency`, `provider_preference`, `appointment_type`, `exclusions`,
  `patient_ref`.
  **AC:** The endpoint returns a schema-valid `RequestConstraints` for all ~40 golden requests;
  schema validation failure is a hard error, never a partial object. *(MUST)*
- **FR-002 — Per-field confidence.** Every field in `RequestConstraints` SHALL carry a
  `confidence` in [0,1].
  **AC:** No field is emitted without a confidence; a missing confidence fails schema validation.
  *(MUST)*
- **FR-003 — Verbatim source spans.** Every non-defaulted field SHALL carry a `source_span`
  containing the exact substring of the request text and its character offsets.
  **AC:** For every golden request, `request_text[span.start:span.end] == span.text` for every
  emitted span. Fields with no textual basis SHALL be marked `derived: true` with the rule that
  derived them (e.g. type-default urgency) rather than given a fabricated span. *(MUST)*
- **FR-004 — Relative-date resolution against injected `NOW`.** Relative expressions ("next
  Thursday", "tomorrow", "first thing", "next week", "after the holidays") SHALL resolve against
  the injected `NOW` (FR-102), never the machine clock.
  **AC:** With `NOW` pinned, the golden set produces identical resolved dates on two runs 24 real
  hours apart, and on a machine whose clock is set well past the reference date. *(MUST)*
- **FR-005 — Deterministic fallback extractor.** A rule-based extractor SHALL exist that produces
  the same `RequestConstraints` shape with no network access, and SHALL be selected automatically
  when the LLM call fails, times out, or is disabled.
  **AC:** With networking disabled and fixtures cleared, all ~40 golden requests still return a
  schema-valid object. The harness reports rules-mode vs. LLM-mode per-field accuracy **as two
  numbers** (this comparison is the evidence for "why an LLM here at all"). *(MUST)*
- **FR-006 — Cached fixtures.** Golden-set and demo-script requests SHALL have committed,
  keyed LLM-response fixtures, used automatically when the model is unreachable.
  **AC:** Live is the default; a fixture is served only when a live call fails, and the UI
  names which path answered. *(Inverted from the original draft — see ADR-20.)*
  Cache key includes request text, model version string, and prompt version. *(MUST)*
- **FR-007 — Editable interpretation strip.** The operator SHALL be able to edit any extracted
  field; editing SHALL re-run the deterministic pipeline only.
  **AC:** Editing a field produces new offers in < 300 ms with zero LLM calls recorded in the
  trace. The edit is recorded on the `DecisionRecord` as `operator_corrections[]`. *(MUST)*
- **FR-008 — Exclusions are hard, preferences are soft.** Patient-stated exclusions ("not
  Tuesdays, I have PT") SHALL be captured as hard constraints; provider preference ("prefer
  Sarah") SHALL be captured as a soft preference.
  **AC:** For the golden case containing a day exclusion, zero offered or feasible candidates fall
  on the excluded day, and the rejection ledger shows them rejected with reason
  `PATIENT_EXCLUSION`. For the preference case, non-preferred providers still appear as feasible
  and can still be offered. *(MUST)*

**Validation Rules**

| Field | Valid Values | Error if Invalid |
| :---- | :----------- | :--------------- |
| `date_range` | `start ≤ end`; `start ≥ NOW.date()`; `end ≤ NOW + search_horizon` (14 days, [A-09]) | `PAST_DATE` — flagged by the verifier (FR-010), surfaced as *"That date has already passed — did you mean …?"* |
| `time_window` | `start < end`; both within business hours ∪ `{open, close}` sentinels | `INVERTED_WINDOW` — clamp to business hours and flag |
| `urgency` | `emergency` \| `urgent` \| `routine` \| `flexible` | Default to the appointment type's `default_urgency`, marked `derived: true` |
| `provider_preference` | An existing `Provider.id` at the location, or null | `UNKNOWN_PROVIDER` — flagged; treated as null preference with an operator-visible note |
| `appointment_type` | An existing `AppointmentType.id`, or an ambiguity set of ≥ 2 | `UNRESOLVED_TYPE` — routes to UC-02 |
| `exclusions` | Weekday set, date set, provider set, time-range set | Malformed exclusion is dropped **and flagged loudly** — silently dropping a hard constraint is the worst available behaviour |

---

### Use Case 2: Verify the interpretation and ask at most one clarifying question

**As a** Front-Desk Operator **I want to** be asked a clarifying question **only when the answer
would actually change what I'm offered** **So that** I am not interrogated on every call, and the
one question I am asked is obviously worth asking.

**Steps:**

1. System passes `RequestConstraints` to the Constraint Verifier.
    - Verifier checks the extraction **against the world** — never against the schedule — and
      emits `proceed`, `proceed_with_flags`, or `ask`.
2. On `ask`, system shows one question with 2–3 concrete answer chips.
    - Operator taps an answer (or reads it to the patient and taps).
3. System resolves the hypothesis and continues.
    - Offers render; the trace records which hypothesis won and why the question was asked.

**Acceptance Criteria:** all of FR-009 … FR-015 pass.

**Functional Requirements**

- **FR-009 — Verifier is schedule-blind.** The Constraint Verifier SHALL NOT read the schedule.
  **AC:** A code-level test asserts the verifier module has no import path to the schedule store.
  *(SHOULD)* — *Design rationale: the verifier checks the request against the world's facts, not
  against availability. Mixing the two makes "why did it ask?" unanswerable, because the answer
  would depend on scheduling state that changes minute to minute.*
- **FR-010 — World checks.** The verifier SHALL check at minimum: date is not in the past;
  requested provider exists and works at this location on the requested days; requested provider
  is credentialed for the requested type; appointment type is compatible with any stated symptom;
  exclusions are well-formed.
  **AC:** Each check has a unit test with a positive and negative case; each emits a distinct,
  named flag code. *(SHOULD)*
- **FR-011 — The decision-relevance test.** A clarifying question SHALL be asked **only if** (a) a
  field is low-confidence (< θ = 0.6, [A-06]) or genuinely ambiguous with ≥ 2 hypotheses, **and**
  (b) running the deterministic pipeline under each hypothesis produces **different top-3 sets**.
  **AC:** Seeded edge case 6a (diverging *type* hypotheses: 30-min limited exam vs. 90-min crown) →
  system asks. Seeded edge case 6b (converging hypotheses) → system **does not ask**, proceeds,
  and shows a flag chip instead. Seeded edge case 11 (diverging *relative-date* hypotheses:
  "next Thursday" → Thu 2026-08-13 vs. Thu 2026-08-20) → system asks. A golden-set entry using an
  unambiguous phrasing of the same request → system does not ask. **All four cases are in the
  golden set and are asserted, not sampled.** *(SHOULD)*
- **FR-012 — At most one question.** At most **one** clarifying question SHALL be asked per
  request.
  **AC:** No golden-set request produces two questions. If multiple fields are decision-relevant,
  the one with the largest top-3 divergence is chosen. *(SHOULD)*
- **FR-013 — Questions are answerable by the patient.** The question SHALL be phrased for the
  operator to read aloud and SHALL offer 2–3 concrete chips, never free text.
  **AC:** Passes the read-aloud lint (FR-065) with the same banned-token list. *(SHOULD)*
- **FR-014 — Multi-hypothesis fan-out is confined here.** Hypothesis fan-out SHALL live in the
  verifier stage, scoped for MVP to **appointment-type ambiguity and relative-date ambiguity** —
  the two ambiguity classes that routinely change which slots are offered.
  **AC:** Fan-out beyond those two classes is feature-flagged off; the flag is visible in config.
  Fan-out is capped at 2 hypotheses per field and 1 field per request (see FR-012).
  *(SHOULD; broader fan-out is STRETCH)*
- **FR-015 — Flags are surfaced, never swallowed.** `proceed_with_flags` SHALL render every flag
  as a visible chip on the interpretation strip.
  **AC:** A request producing 3 flags renders 3 chips; zero flags are logged-only. *(SHOULD)*

---

### Use Case 3: Enumerate candidates and apply hard-constraint feasibility

**As a** Front-Desk Operator **I want** the system to consider *every* slot that could possibly work
and to reject the impossible ones for a stated, single reason **So that** I never have to wonder
whether it missed something.

**Steps:**

1. System enumerates every `(start, duration, provider, operatory)` tuple in the search horizon.
    - Funnel counter shows the enumerated count.
2. System applies the hard-constraint ladder in a fixed order, annotating rather than deleting.
    - Funnel counter shows the feasible count.
3. Operator can expand any rejection group.
    - System shows the specific candidates and the single, first-failing cause per candidate.

**Acceptance Criteria:** all of FR-016 … FR-026 pass.

**Functional Requirements**

- **FR-016 — Exhaustive enumeration.** The reasoner SHALL enumerate candidates over
  `days × operatories × start-grid` for the search horizon, where the start grid is 10-minute
  granularity ([A-20]) and the horizon is 14 days from `NOW` ([A-09]).
  **AC:** Enumerated count equals `business_minutes_in_horizon / 10 × operatory_count` minus
  out-of-hours starts, verified arithmetically by a test. **"Did it miss anything?" must be
  answerable with "no, by construction."** *(MUST)*
- **FR-017 — Candidate identity.** A candidate SHALL be the tuple
  `(start, duration, provider, operatory)` with a stable, deterministic `candidate_id`.
  **AC:** Two runs over the same inputs produce identical `candidate_id`s. *(MUST)*
- **FR-018 — Operatory availability with turnover buffer.** A candidate SHALL require the
  operatory free for the full duration **plus a 10-minute turnover/cleanup buffer** ([A-08]).
  **AC:** A candidate abutting an existing appointment with a 5-minute gap is rejected with
  `OPERATORY_TURNOVER`; with an 11-minute gap it is feasible. *(MUST)*
- **FR-019 — Provider availability.** The assigned provider SHALL be free for the full duration.
  **AC:** Overlap with any existing appointment, block, or PTO for that provider →
  `PROVIDER_BUSY`. *(MUST)*
- **FR-020 — Provider credentialing.** The provider SHALL be credentialed for the appointment
  type.
  **AC:** An RDH is never offered a crown prep (`PROVIDER_NOT_CREDENTIALED`). Seeded edge case 7
  (patient requests an oral surgeon for a cleaning) produces a graceful redirect, not an empty
  list. *(MUST)*
- **FR-021 — Operatory equipment.** The operatory SHALL carry every equipment tag the appointment
  type requires.
  **AC:** Seeded edge case 8 — an extraction is feasible only in the surgical-capable operatory;
  all other operatories are rejected `OPERATORY_NOT_EQUIPPED`. *(MUST)*
- **FR-022 — Business hours and blocks.** The candidate SHALL start and end inside business hours
  ([A-19]) and SHALL NOT overlap a `lunch`, `huddle`, or `admin` `ScheduleBlock`. The appointment
  must end by close; the turnover buffer MAY extend past close ([A-08]).
  **AC:** A 60-minute candidate starting 30 minutes before close is rejected `PAST_CLOSE`; one
  ending exactly at close is feasible. *(MUST)*
- **FR-023 — Doctor-check overlay (interval-*within*-interval).** For any appointment type with
  `requires_doctor_check = true`, the candidate `[s, s+d)` SHALL be feasible **only if** there
  exists a credentialed dentist `p` and a time `t` such that
  `[t, t + check_duration) ⊆ [s + ⌈2d/3⌉, s + d)` **and** `[t, t + check_duration) ⊆ free(p)`.
  `check_duration` defaults to 10 minutes; the placement window is the **last third** of the
  appointment.
  **AC — this is the requirement most likely to be implemented wrong, so the tests are specified
  explicitly:**
    1. Dentist free only during the *first* third → **rejected** `DOCTOR_CHECK_UNAVAILABLE`.
    2. Dentist free for a contiguous **9** minutes inside the last third → **rejected** (9 < 10).
    3. Dentist free for exactly 10 minutes ending at `s+d` → **feasible**.
    4. Dentist free for 10 minutes *straddling* the last-third boundary (5 min before, 5 min
       inside) → **rejected** — the check window must be fully contained.
    5. **An overlap-based implementation SHALL fail tests 1 and 4.** A test named
       `test_doctor_check_is_containment_not_overlap` asserts this.
    6. Seeded edge case 1 (Thursday PM: three hygiene operatories open, every dentist in
       back-to-back crowns) → all three rejected for this reason, and the ledger says so in one
       sentence. *(MUST)*
- **FR-024 — Patient exclusions are hard.** Candidates violating a stated exclusion SHALL be
  rejected `PATIENT_EXCLUSION`.
  **AC:** See FR-008. Exclusions are **never** relaxed, including by the counterfactual engine
  (FR-057). *(MUST)*
- **FR-025 — Fixed rule order.** The hard-constraint ladder SHALL execute in a fixed, documented
  order so that the *first* failing rule is the single stated cause.
  **AC:** The order is declared in one place as data, not scattered through code; reordering it
  changes ledger causes deterministically and is covered by a snapshot test. *(MUST)*
- **FR-026 — Emergency-hold blocks are invisible by default.** Candidates overlapping an
  `emergency_hold` block SHALL be rejected `EMERGENCY_HOLD_LOCKED` unless unlocked by FR-036.
  **AC:** A routine request never sees hold slots at any stage, including in the ledger's
  "available" grouping. *(MUST)*

**Calculation Logic — feasibility ladder (fixed order)**

```
1. within_business_hours          → PAST_CLOSE / BEFORE_OPEN
2. not_overlapping_global_block   → BLOCKED_LUNCH | BLOCKED_HUDDLE | BLOCKED_ADMIN
3. emergency_hold_locked          → EMERGENCY_HOLD_LOCKED
4. patient_exclusion              → PATIENT_EXCLUSION
5. operatory_free(d + turnover)   → OPERATORY_BUSY | OPERATORY_TURNOVER
6. operatory_equipped(type)       → OPERATORY_NOT_EQUIPPED
7. provider_free(d)               → PROVIDER_BUSY | PROVIDER_PTO
8. provider_credentialed(type)    → PROVIDER_NOT_CREDENTIALED
9. provider_at_location(day)      → PROVIDER_OFFSITE
10. doctor_check_containment      → DOCTOR_CHECK_UNAVAILABLE
→ feasible
```

---

### Use Case 4: Show what was rejected and why (the rejection ledger)

**As a** Front-Desk Operator **I want to** see what the system considered and threw away, grouped by
reason **So that** I can answer the patient's "but isn't 3 o'clock open?" without opening the
calendar — and so I can tell when the system is wrong.

**Steps:**

1. Operator expands "Considered and rejected (N)".
    - System shows rejection groups ordered by count, each with a one-line plain cause.
2. Operator expands a group.
    - System lists the specific candidates (day, time, provider, operatory) with the single cause.

**Acceptance Criteria:** all of FR-027 … FR-031 and FR-109 pass.

**Functional Requirements**

- **FR-027 — [SD-1] Annotate, never delete.** No pipeline stage SHALL remove a candidate from the
  working set. Each stage SHALL attach annotations (`feasible`, `rejection_reason`, `tier`,
  `score`, `rank`).
  **AC — conservation invariant:** for every request,
  `count(feasible) + Σ count(rejected_by_reason) == count(enumerated)`, asserted as a runtime
  invariant **and** as a test over the whole golden set. This single assertion is what makes the
  funnel counter trustworthy. *(MUST)*
- **FR-028 — Single stated cause.** Each rejected candidate SHALL carry exactly one
  `rejection_reason`, the first rule it failed in the FR-025 order.
  **AC:** No candidate carries a reason list. *(MUST)*
- **FR-029 — Funnel counter.** The UI SHALL display `enumerated → feasible → in-tier → offered` as
  four live numbers.
  **AC:** The four numbers reconcile with the invariant in FR-027 for every scripted demo request.
  *(MUST)*
- **FR-030 — Templated why-not text.** Each rejection group SHALL render a plain-language,
  single-cause sentence with no jargon and no internal identifiers.
  **AC:** *"Three hygiene rooms were open Thursday afternoon, but no dentist was free for the
  10-minute exam inside those appointments."* Passes the read-aloud lint (FR-065). *(MUST)*
- **FR-031 — Ledger is collapsed by default.** The ledger SHALL be collapsed on first render and
  expandable in one click.
  **AC:** Default operator view shows three cards and a single summary line; expansion is one
  click and one scroll on a 1920×1080 display at 125–150% browser zoom. *(MUST)*
- **FR-109 — Per-time lookup ("but isn't 3 o'clock free?").** For any decision, the system SHALL
  report, for one (day, start time), how many candidates started at that time, how many were
  bookable, and the plain-language cause of each rejection grouped by cause. Selectable times
  SHALL be restricted to the search grid inside that day's business hours. "Bookable but not
  offered" SHALL be reported distinctly from "nothing was bookable".
  **Rationale:** FR-027 … FR-031 answer *"where did 13,000 candidates go?"*, which is the wrong
  grain for the question an operator is actually asked. Aggregate causes cannot end a phone call
  about one time.
  **AC:** counts conserve at the slot grain (`bookable + Σ causes == considered`); every selectable
  time is a multiple of `grid_granularity_min` within business hours; no cause string contains an
  enum identifier. *(MUST)*

---

### Use Case 5: Apply the urgency gate and never return nothing

**As a** Front-Desk Operator **I want** an urgent request to be triaged before it is optimised, and
**I want** to never see an empty result **So that** a patient in pain is never told "nothing's
available" by a computer.

**Steps:**

1. System buckets feasible candidates by urgency tier relative to `NOW`.
    - Ranking runs **only inside the top non-empty tier**.
2. If the top tier is empty and urgency ≥ urgent, system unlocks emergency-hold blocks and
   re-enumerates.
    - New candidates appear, explicitly labelled as released emergency holds.
3. If still empty, system returns labelled overflow (nearest options outside the window) and, when
   built, bump candidates.
    - Operator always sees at least one actionable option with an honest label.

**Acceptance Criteria:** all of FR-032 … FR-038 pass.

**Functional Requirements**

- **FR-032 — Urgency is a gate, not a weight.** Tier assignment SHALL be lexicographic and SHALL
  NOT participate in the weighted sum.
  **AC:** No weight vector, including extreme ones set in the tuner, can promote a
  lower-tier candidate above a higher-tier one. A property test asserts this over 200 random
  weight vectors. *(MUST)* — *Design rationale: urgency is a gate, not a weight. Scored as a weight,
  it would price pain against convenience on the same axis, and a sufficiently strong preference
  for convenience could outrank a genuine emergency.*
- **FR-033 — Tier definitions.** `emergency` ≤ 24 h from `NOW`; `urgent` ≤ 72 h; `routine` ≤ the
  requested window's end; `flexible` ≤ search horizon.
  **AC:** Boundary tests at exactly 24 h and 24 h + 10 min. *(MUST)*
- **FR-034 — Rank within the top non-empty tier.** Ranking SHALL operate on the highest-priority
  non-empty bucket only.
  **AC:** With one emergency-tier candidate and forty routine-tier candidates, exactly one option
  is offered, plus overflow labelled as such. *(MUST)*
- **FR-035 — Never return an empty list.** If the top tier is empty, the system SHALL escalate
  rather than return zero results; the response SHALL always contain ≥ 1 offer or an explicitly
  labelled overflow set.
  **AC:** Seeded edge case 5 ("urgent, nothing open") returns a non-empty, correctly labelled
  response. A test asserts `len(offers) + len(overflow) ≥ 1` for every golden request. *(MUST)*
- **FR-036 — Emergency-hold unlock.** `ScheduleBlock`s of kind `emergency_hold` (seeded daily at
  11:00 and 16:00) SHALL be unlockable **only** when request urgency ≥ `urgent`, and unlocked
  candidates SHALL be visibly labelled *"emergency hold released."*
  **AC:** Routine request → hold slots never appear. Urgent request with an empty top tier → hold
  slots appear, labelled, and the trace records `emergency_hold_unlocked: true`. *(MUST)*
- **FR-037 — Bump candidates.** The system MAY surface an existing appointment that could be moved
  to free a slot, only when: request urgency = `emergency`; the bumped appointment's urgency is
  `routine` or `flexible`; and a feasible alternative exists for the bumped patient inside that
  patient's original window.
  **AC:** Bump suggestions are **never auto-executed** — they require an explicit, separate
  operator action and render with the bumped patient's alternative already computed. *(STRETCH —
  see the §6 reconciliation note)*
- **FR-038 — Overflow is labelled honestly.** Options outside the requested window or tier SHALL
  be visually and textually distinguished, never silently mixed into the top 3.
  **AC:** An overflow option's reason line begins by naming the gap (*"Nothing opened before
  Thursday, but …"*). *(MUST)*

**State Transitions — request lifecycle**

| Current State | Trigger | New State |
| :------------ | :------ | :-------- |
| `received` | extraction completes | `interpreted` |
| `interpreted` | verifier → `ask` | `awaiting_clarification` |
| `awaiting_clarification` | operator answers | `interpreted` |
| `interpreted` | verifier → `proceed` / `proceed_with_flags` | `searching` |
| `searching` | feasible set computed | `ranked` |
| `ranked` | slots fit the request as stated | `offered` |
| `ranked` | nothing fits, urgency ≥ urgent | `escalated_holds_unlocked` → `offered` |
| `ranked` | still nothing after unlocking holds | `offered_overflow` |
| `ranked` | nothing fits, no unlock permitted | `offered_overflow` |
| `offered` / `offered_overflow` | operator holds a slot | `held` |
| `held` | operator confirms, re-verification passes | `booked` |
| `held` | TTL expires, operator releases, or re-verification fails | **returns to the state it came from** — `offered` or `offered_overflow` |

> **[spec-refinement] The return transition preserves the originating state.** An expired hold on an
> overflow option must return to `offered_overflow`, not to `offered`. Collapsing both into
> `offered` would silently drop the "this is not what you asked for" labelling (FR-038) from a card
> that is still on screen — the operator would see a Friday slot presented as though it satisfied a
> request for Thursday. The `DecisionRecord` therefore carries the originating state, and the hold
> release restores it.

---

### Use Case 6: Score surviving candidates on four weighted axes

**As an** Office Manager **I want** the ranking to reflect the practice's actual priorities on four
named, separately-visible axes **So that** I can see *why* a slot won and change the policy if the
practice's priorities change.

**Steps:**

1. System scores each in-tier candidate on four normalised axes.
    - Each axis returns a value in [0,1] plus human-readable atoms.
2. System applies the active `WeightProfile` (weights sum to 1.0).
    - Total score reads as a percentage.
3. UI renders a stacked contribution bar per card.
    - Every number on screen decomposes into its four parts.

**Acceptance Criteria:** all of FR-039 … FR-047 pass.

**Functional Requirements**

- **FR-039 — Four axes, normalised, weights sum to 1.0.** Axes: **Time fit**, **Provider
  continuity**, **Schedule efficiency**, **Prime-time / block protection**. Defaults for the
  general-practice profile: **0.35 / 0.25 / 0.25 / 0.15** — explicitly *a profile, not a universal
  truth*.
  **AC:** `Σ weights == 1.0 ± 1e-9` is enforced on load and on every tuner change; every axis
  value ∈ [0,1]; total score ∈ [0,1] and renders as a percentage. *(MUST)*
- **FR-040 — Time fit is piecewise, not binary.** 1.0 inside the requested window; ~0.85 within 30
  min of a boundary; ~0.6 within 60 min; **linear taper 0.6 → 0.0 across 60 → 120 min
  [spec-refinement, A-10]**; 0 beyond 2 h. Plus a mild sooner-is-better term inside the window
  (base 1.0 minus `min(0.10, 0.01 × days_out)` [A-10]).
  **AC:** Unit tests at 0, 30, 60, 90, 120, 121 minutes outside the boundary. Two candidates
  inside the window differing only in date rank earlier-first. *(MUST)*
- **FR-041 — Provider continuity is tiered and type-dependent.** Base: 1.0 assigned / last-seen
  for this care type; 0.7 same pod; 0.4 any previously seen; 0.15 new.
  Type dependence [spec-refinement, A-11]: `AppointmentType.continuity_multiplier` scales the
  continuity weight before renormalisation — crown seat 2.0, crown prep / RCT 1.5, prophy / perio
  1.0, limited exam 0.5.
  **AC:** For a crown *seat*, a candidate with a different dentist than the one who did the prep
  ranks below every same-dentist candidate in the same tier. For a routine prophy, a
  different-hygienist candidate can outrank a same-hygienist candidate on time fit alone.
  Renormalisation keeps `Σ weights == 1.0`. *(MUST)* — *Design rationale: a crown seat with the
  wrong dentist is nearly a hard constraint; continuity on a routine prophy is a nice-to-have. A
  single global continuity weight cannot express both.*
- **FR-042 — Schedule efficiency is a composite of four sub-terms.** Sub-weights [A-12]:
  fragmentation delta **0.40**, provider idle-time delta **0.25**, doctor-check load **0.20**,
  operatory balance **0.15**.
  **AC:** Sub-weights sum to 1.0; each sub-term is separately inspectable in the trace. *(MUST)*
- **FR-043 — Fragmentation delta.** Defined as the minutes of **newly created gap shorter than the
  shortest bookable appointment** (30 min). Normalised: 1.0 at 0 orphan minutes, 0.0 at ≥ 60
  orphan minutes, linear between.
  **AC:** Seeded edge case 3 — a **50-minute** hole that exactly fits a 40-minute filling plus its
  10-minute turnover — the gap-filling candidate creates 0 orphan minutes, scores 1.0 on this
  sub-term, and is offered. Seeded edge case 4 — in a 90-minute open stretch, a 30-minute booking
  placed in the middle creates two 30-minute orphans and scores 0.0; the scorer pushes the booking
  to the **edge** of the stretch, **and the explanation says so.** *(MUST)*
  > **[spec-refinement]** `product-direction.md` §5 describes edge case 3 as a "45-min hole" that fits a
  > 40-minute filling *plus turnover*; with the 10-minute turnover in FR-018 that arithmetic
  > requires **50 minutes**. Corrected to 50 here so the hero case actually fires. The intent —
  > a hole that fits the appointment *exactly*, with zero remainder — is unchanged.
- **FR-044 — Doctor-check load.** Feasible-but-tight ≠ good: a candidate whose doctor-check window
  has little slack, or which consumes the last available dentist-check capacity in that hour, SHALL
  score lower on this sub-term.
  **AC:** Two otherwise-identical candidates differing only in doctor-check slack rank
  slack-first. *(MUST)*
- **FR-045 — Prime-time / block protection is negative-going.** Consuming a `restorative_block` (or
  a `pedo_after_school` block with a non-school-age patient) with a type whose `production_value`
  is below the block's floor SHALL reduce this axis toward 0 in proportion to the overlap fraction.
  Non-consuming candidates score 1.0.
  **AC:** A 30-minute prophy placed inside a protected restorative block scores materially lower
  than the same prophy 40 minutes later outside the block, holding the other three axes equal. A
  school-age patient at 15:00–17:00 is **not** penalised. *(MUST)* — *Design rationale: the schedule
  has a shape the practice wants. The optimizer defends that shape rather than discovering it anew
  on every request.*
- **FR-046 — Weights are data, not constants.** The active weight vector SHALL be a first-class
  `WeightProfile` entity loaded at request time, never hard-coded in the scorer.
  **AC:** Changing the profile changes ranking with no code change; grep finds no numeric weight
  literal inside the scoring functions. *(MUST)* — *Design rationale: policy is the thing that does
  not scale for free. Hundreds of offices need centrally managed profiles with local override,
  which is impossible if the weights are constants in a function body.*
- **FR-047 — Score decomposition is always emitted.** Every scored candidate SHALL carry its four
  raw axis values, four weighted contributions, and the composite sub-terms.
  **AC:** `Σ weighted_contributions == total_score ± 1e-9` for every candidate; the UI never
  displays a naked number. *(MUST)*

**Calculation Logic**

```
score(c) = Σ_axis  w_axis_effective × v_axis(c)          where Σ w_axis_effective = 1.0

w_continuity_raw   = w_continuity × type.continuity_multiplier      (FR-041)
w_*_effective      = w_*_raw / Σ w_*_raw                            (renormalise)

v_efficiency(c) = 0.40·frag(c) + 0.25·idle(c) + 0.20·check_load(c) + 0.15·op_balance(c)
frag(c)         = clamp(1 − orphan_minutes_created(c) / 60, 0, 1)   (orphan < 30 min)
```

---

### Use Case 7: Produce a stable, diverse, explained top 3

**As a** Front-Desk Operator **I want** three options that are genuinely *different* options, in an
order that never changes for the same request **So that** the patient gets a real choice and I can
trust what I saw yesterday.

**Steps:**

1. System sorts in-tier candidates by total score descending.
2. System applies the deterministic tiebreak chain, the ε-band grouping, and the diversity
   constraint.
3. UI renders exactly three cards with contribution bars, one reason line, and one primary action.

**Acceptance Criteria:** all of FR-048 … FR-054 pass.

**Functional Requirements**

- **FR-048 — Deterministic tiebreak chain.** When scores differ by < 1e-9, order SHALL be decided
  by: **earlier date/time → higher continuity → lower fragmentation delta → lower operatory ID.**
  **AC:** Running the same request twice produces a **byte-identical** response. A test
  constructs an exact four-way tie and asserts the chain resolves it in the stated order. *(MUST)*
- **FR-049 — ε-band co-equality.** Candidates within ε = 0.03 [A-13] of each other SHALL be
  presented as **co-equal options with differentiating reasons**, not as a false 1 / 2 / 3.
  **AC:** Two candidates 0.01 apart render without ordinal badges and with reasons that name
  *different* winning axes. Display order is still deterministic (FR-048). *(MUST)*
- **FR-050 — Top-3 diversity.** The three offers SHALL NOT be near-duplicates. A candidate is
  skipped if it shares provider **and** day **and** starts within 60 minutes [A-13] of an
  already-selected offer — unless skipping would leave fewer than three offers.
  **AC:** Given candidates at 15:00, 15:10, 15:20 with the same provider and operatory, the
  offered set contains at most one of them. The final three span **≥ 2 distinct days or ≥ 2
  distinct providers** whenever the feasible set permits; when it does not, a
  `limited_availability` flag renders. *(MUST)* — *Design rationale: three near-identical options
  are one option. Offering them as three wastes the patient's only real choice.*
- **FR-051 — Exactly three, or fewer with a reason.** The system SHALL offer three options when
  three exist post-diversity, otherwise fewer, with an explicit statement of why.
  **AC:** A request with two feasible candidates renders two cards plus a stated reason, never a
  padded third. *(MUST)*
- **FR-052 — One primary action per card.** Each card SHALL expose exactly one primary action
  (**Hold**), with secondary details behind disclosure.
  **AC:** Keyboard-only operation: `1` / `2` / `3` holds the corresponding card. *(MUST)*
- **FR-053 — Card content contract.** Each card SHALL show: resolved weekday + date + start time,
  provider name, duration, appointment type, total score as a percentage, a stacked contribution
  bar, and the one-sentence reason line.
  **AC:** All seven elements present on every card at 125–150% browser zoom without truncation or
  scrolling. *(MUST)*
- **FR-054 — Ranking is independent of the LLM.** Ranking SHALL be a pure function of
  `(RequestConstraints, schedule state, WeightProfile, NOW)`.
  **AC:** With the LLM disabled entirely, ranking output for a fixed `RequestConstraints` is
  identical to LLM-enabled mode. *(MUST)* — *Design rationale: a language error can produce the
  wrong search. It can never produce an infeasible booking.*

---

### Use Case 8: Offer a counterfactual relaxation

**As a** Front-Desk Operator **I want to** be told what the patient would gain by bending one
constraint **So that** I can offer a genuinely better trade instead of just the best of a bad set.

**Steps:**

1. System re-ranks with one soft constraint relaxed at a time.
2. System selects the single relaxation with the largest score gain above threshold.
3. UI renders one sentence beneath the cards.

**Acceptance Criteria:** all of FR-055 … FR-058 pass.

**Functional Requirements**

- **FR-055 — One-at-a-time relaxation.** The engine SHALL re-run ranking with exactly one soft
  constraint relaxed per trial: time window ±60 min, time window ±120 min, provider preference
  dropped, urgency window extended by one tier.
  **AC:** Four trials max per request; each trial recorded in the trace with its resulting top-1
  score. *(SHOULD)*
- **FR-056 — Threshold and single suggestion.** At most one counterfactual SHALL be surfaced, and
  only when the score gain ≥ 0.08 [A-14].
  **AC:** A request whose best relaxation gains 0.05 shows no counterfactual. *(SHOULD)*
- **FR-057 — Hard constraints are never relaxed.** Patient-stated exclusions and all Layer-0
  feasibility rules (FR-018 … FR-026) SHALL NOT be relaxed by the counterfactual engine.
  **AC:** A test asserts no counterfactual output violates an exclusion or any hard rule. **This
  is a safety requirement:** suggesting a Tuesday to a patient who said "not Tuesdays, I have PT"
  is worse than offering nothing. *(SHOULD)*
- **FR-058 — Counterfactual copy is phone-readable.** Rendered as one sentence naming the
  trade explicitly.
  **AC:** *"If 11:20 works instead of first thing, you get Dr. Patel and we skip the double-book."*
  Passes the read-aloud lint (FR-065). *(SHOULD)*

---

### Use Case 9: Generate a plain-language reason that cannot be unfaithful

**As a** Front-Desk Operator **I want** one warm sentence per option that I can read straight to the
patient **So that** I never have to translate a score into English while someone is waiting.

**Steps:**

1. Scorer emits a `Rationale` per offered candidate.
2. Explainer renders the rationale's atoms into one sentence.
3. Faithfulness gate verifies the sentence against the fact set.
4. On failure, system silently substitutes the template rendering and logs the gate firing.

**Acceptance Criteria:** all of FR-059 … FR-067 pass.

**Functional Requirements**

- **FR-059 — [SD-2] The scorer emits the `Rationale`.** The scorer — not the explainer — SHALL emit
  a structured `Rationale` containing the **top 2–3 contributing components** with values and
  human-readable atoms, **at most one caveat atom**, and the fact set (provider, weekday, date,
  time, operatory, duration, type).
  **AC:** The explainer module has no access to the schedule or to the scorer's internals beyond
  the `Rationale` — asserted by a code-level import test. The `Rationale`'s top components match
  the highest weighted contributions computed in FR-047. *(MUST)* — *Design rationale: the
  explanation is generated from the decision, never in parallel with it, so it cannot disagree with
  it. Faithfulness becomes a structural property rather than something to test for.*
- **FR-060 — Template rendering is always computed.** A deterministic template rendering SHALL be
  produced for every offer regardless of LLM availability.
  **AC:** Offline mode produces a complete reason line for 100% of golden-set offers. Both
  renderings are returned by the API so the two can be compared directly. *(MUST)*
- **FR-061 — LLM explainer is constrained to supplied facts.** The prompt SHALL supply only the
  `Rationale` atoms and fact set and SHALL instruct: one sentence, ≤ 25 words, second person, use
  only the supplied facts, add nothing.
  **AC:** Prompt is version-pinned and committed; prompt version is part of the fixture cache key.
  *(SHOULD)*
- **FR-062 — Faithfulness gate.** A deterministic post-check SHALL verify: (1) every named entity
  (provider, weekday, date, clock time, operatory, duration, type) exists in the fact set; (2) no
  claim maps to a component absent from the `Rationale`'s top atoms or caveat; (3) sentence ≤ 25
  words; (4) no banned hedge/negation tokens; (5) the resolved date and time are echoed exactly.
  **AC:** A crafted response naming a provider not in the fact set is rejected. A crafted response
  claiming continuity when continuity was not a top contributor is rejected. The gate is ~40 lines
  and is unit-tested independently of the LLM. *(SHOULD)*
- **FR-063 — Silent, logged fallback.** On gate failure the system SHALL silently substitute the
  template rendering and SHALL log `gate_fired: true` with the failing check ID to the trace.
  **AC:** The operator never sees an error; the trace panel shows the firing. A test forces a
  deliberately unfaithful completion and asserts that the template is substituted and the firing is
  logged. *(SHOULD)* — *~40 lines that turn "trust the LLM" into "verify the LLM."*
- **FR-064 — Gate firing rate is a reported metric.** The eval scorecard SHALL report gate-firing
  rate over the golden set.
  **AC:** Rate appears on the scorecard; a rate of 0 across 40 requests is itself reported, and
  recorded as a limitation — a gate that never fires has not been stress-tested. *(SHOULD)*
- **FR-065 — Read-aloud lint (the copy-defining requirement).** Every operator-facing sentence
  (reason lines, why-not text, counterfactuals, clarifying questions) SHALL be:
  a single grammatical sentence; ≤ 25 words; addressed to the patient in second person; containing
  the resolved **weekday + date + clock time** where it refers to a slot; and containing **none**
  of: numeric scores or percentages, axis names ("time fit", "efficiency", "continuity"), internal
  identifiers (candidate IDs, operatory IDs, `provider_id`), or system jargon ("fragmentation",
  "candidate", "constraint", "tier", "weight", "score", "operatory", **"overflow"**,
  **"escalate"**).
  **[spec-refinement]** `overflow` and `escalate` are added to the banned list because they are
  internal state names that read as ordinary English and will therefore slip into copy unnoticed —
  unlike "fragmentation", which announces itself. An overflow option must be described by naming
  the gap (*"Nothing opened before Thursday, but …"*, FR-038), never by naming the mechanism.
  **AC:** An automated lint runs over **all** golden-set outputs in both LLM and template modes and
  fails the build on any violation. Banned-token list is committed as data. **This is the
  requirement that makes reading a reason aloud to a patient reliable rather than lucky, on every
  request rather than the ones that happen to phrase well.** *(MUST)*
- **FR-066 — Caveat atoms are surfaced, capped at one.** Where a top offer has a real downside,
  the `Rationale` MAY carry at most one caveat atom, which the reason line SHALL include.
  **AC:** *"…though it's a week out"* renders; two caveats never render. *(SHOULD)*
- **FR-067 — Extraction provenance is visible alongside the reason.** The UI SHALL show the
  verbatim source span that produced each constraint (`"after 3" → window 15:00–close`).
  **AC:** Every chip on the interpretation strip exposes its span on hover/expand; derived fields
  say "derived" and name the rule. *(MUST)*

---

### Use Case 10: Hold, confirm, and reset a booking

**As a** Front-Desk Operator **I want to** hold the options I just read out and then confirm one
**So that** the slot doesn't vanish while the patient decides — and, in an evaluation environment,
so that a single control restores the reference dataset for a repeat run.

**Steps:**

1. Operator presses Hold on a card (or the system auto-holds all three on offer).
    - System creates `Hold` records with a TTL and shows a countdown.
2. Operator presses Confirm.
    - System re-verifies feasibility, writes an `Appointment` to the session copy, releases the
      other holds, and shows a confirmation echoing weekday, date, time and provider.
3. Operator presses **Reset to reference data**.
    - System restores the committed seed snapshot, clears holds, and preserves the trace history.

**Acceptance Criteria:** all of FR-068 … FR-075 pass.

**Functional Requirements**

- **FR-068 — Soft holds on the offered top 3.** Offering SHALL create soft `Hold` records on all
  offered candidates with a TTL of 15 minutes [A-07], configurable.
  **AC:** Held slots are excluded from enumeration for other requests in the same session and are
  visibly marked; expiry releases automatically. *(SHOULD)*
- **FR-069 — Confirm re-verifies before writing, and the write is conditional
  [spec-refinement].** Confirmation SHALL re-run the full hard-constraint ladder against current
  schedule state, and SHALL then commit the appointment through a **conditional write** — a single
  operation that succeeds only if the target `(operatory, time-range)` is still unoccupied at the
  moment of commit. Re-verification and commit SHALL NOT be two independently-observable steps.
  **AC:** If state changed since offer, confirmation fails with a specific, named error and offers
  a re-run — it never writes an infeasible appointment. A test drives a concurrent write **between**
  re-verification and commit and asserts that exactly one of the two bookings succeeds and the other
  receives `SLOT_TAKEN`. *(MUST)*
  > **Why this was raised from SHOULD to MUST, and why the wording changed.** The original
  > requirement described *check, then write*, which is a time-of-check-to-time-of-use race: two
  > operators can both pass re-verification and both write, and the result is two patients in one
  > chair. At one operator the race cannot fire, which is exactly why it would have shipped
  > unnoticed and surfaced on the first day of multi-seat use. Making the write conditional costs
  > nothing at one seat — an in-memory compare-and-set — and is the difference between a design that
  > is single-seat *by configuration* and one that is single-seat *by accident*. NFR-08 defers
  > multi-seat; it does not license a data-corrupting write path.
- **FR-070 — Session-copy mutation only ✅ DECIDED.** Confirmation SHALL mutate an **in-memory
  session copy** of the schedule. Committed seed JSON SHALL never be written at runtime.
  **AC:** After any number of bookings, `git status` on the seed data is clean. *(SHOULD)*
- **FR-071 — One-click reset.** A **Reset to reference data** control SHALL restore the session to
  the committed seed snapshot.
  **AC:** Reset completes in < 1 s and is reachable from every screen. Reference scenarios are
  bit-identical after reset — verified by booking, resetting, and re-running a reference request to
  a byte-identical response. *(SHOULD)* — *without this, any evaluation session is single-use: the
  first booking permanently changes the dataset every later result depends on.*
- **FR-072 — Reset preserves traces by default [spec-refinement].** Reset SHALL restore schedule
  state and clear holds but SHALL retain captured traces; clearing traces is a separate,
  explicitly-labelled action.
  **AC:** After reset, a trace captured before the reset is still replayable. *(SHOULD)* —
  *rationale: an evaluator will want to reset the schedule and still inspect a decision made before
  the reset. Coupling the two would destroy the audit trail on every reset.*
- **FR-073 — Confirmation echoes the resolved date aloud.** The confirmation message SHALL restate
  weekday, date, clock time, provider and duration.
  **AC:** Passes the read-aloud lint. **This is the mitigation for the one residual risk that
  cannot be engineered away — a confidently-wrong date the staffer doesn't notice. The *patient*
  catches it.** *(SHOULD)*
- **FR-074 — Every decision is recorded.** Offering and confirming SHALL write a `DecisionRecord`
  (§8) containing raw text, extracted constraints with confidences and spans, the full annotated
  candidate set with scores and rejection reasons, the offered top 3, what was accepted, the
  active weight profile, and the trace ID.
  **AC:** One `DecisionRecord` per request; it is sufficient to replay the decision with no other
  input (FR-088). *(MUST)*
- **FR-075 — Override capture.** If the operator books a slot that was **not** in the offered top
  3, the system SHALL record it as an override with a reason code.
  **AC:** The override appears in the `DecisionRecord` and is exportable into the golden set as a
    labelled counterexample. *(SHOULD)* — *Design rationale: every override is the most valuable data
  this product generates. If staff systematically ignore the ranking, the ranking is wrong, and the
  product should be the first to know.*

**State Transitions — slot lifecycle**

| Current State | Trigger | New State |
| :------------ | :------ | :-------- |
| `available` | included in an offered top 3 | `soft_held` |
| `soft_held` | TTL expires | `available` |
| `soft_held` | operator releases | `available` |
| `soft_held` | operator confirms, re-verification passes | `booked` |
| `soft_held` | operator confirms, re-verification fails | `available` + `RE_VERIFY_FAILED` |
| `booked` | reset demo state | `available` |

---

### Use Case 11: Configure practice scheduling policy (the weight tuner)

**As an** Office Manager / DSO Ops Lead **I want to** set and see the practice's scheduling policy,
and see how much the recommendation actually depends on it **So that** the policy is an explicit,
owned decision rather than a constant buried in someone's code.

**Steps:**

1. Manager opens the Practice Policy panel and picks a named preset.
    - System applies the preset and re-ranks the current request immediately.
2. Manager drags an axis slider.
    - System renormalises the remaining weights, re-ranks in < 300 ms, animates card reordering,
      and updates the rank-stability number.
3. Manager reads the rank-stability indicator.
    - System states what fraction of sampled weight vectors preserve this top 3.

**Acceptance Criteria:** all of FR-076 … FR-084 pass.

**Functional Requirements**

- **FR-076 — Separate surface ✅ DECIDED.** The tuner SHALL live on a panel separate from the
  operator console and SHALL NOT be reachable from the operator flow.
  **AC:** No weight control appears anywhere on `/`. *(SHOULD)* — *Design rationale: putting weights
  in front of the front desk invites per-call adjustment, which destroys the decision consistency
  the product exists to provide.*
- **FR-077 — Named presets.** The system SHALL ship the fitted default **General Practice** plus
  three named presets: **Patient-first**, **Production-first**, **Continuity-first**.
  **AC:** Selecting each preset produces a materially different ranking on at least one golden
  request, demonstrated by the harness. *(SHOULD)* — *this reframes "why 0.35?" from an arithmetic
  question into a product question.*
- **FR-078 — Sliders renormalise.** Adjusting one axis SHALL renormalise the others so weights
  always sum to 1.0, displayed to two decimals.
  **AC:** No slider position can produce a sum ≠ 1.0; all-zero input is rejected. *(SHOULD)*
- **FR-079 — Live re-rank with no LLM call.** A weight change SHALL re-rank the current request
  through the deterministic layer only.
  **AC:** Re-rank renders in **< 300 ms** and the trace records zero LLM calls. *(SHOULD)*
- **FR-080 — Per-axis stacked contribution bar on every card.** Every card SHALL decompose its
  score into four labelled weighted contributions.
  **AC:** Bar segments sum to the displayed total (FR-047); segments are distinguishable at
  presentation distance on a large display. **The score is always decomposed, never a naked
  number.** *(SHOULD)*
- **FR-081 — Rank-stability indicator.** The panel SHALL sample **N = 200** [A-15] weight vectors
  and report the percentage in which the current three remain the top 3, plus a per-slot
  percentage.
  **AC:** Computes in **< 500 ms**; sampling is seeded so the number is reproducible run to run;
  displayed prominently in words: *"These three stay in the top 3 across 78% of sampled weight
  vectors."* *(SHOULD)* — *Design rationale: this converts "the weights are arbitrary" from an
  objection into a measurement — the recommendation is robust to the weights being arbitrary, or
  it is not, and the number says which.*
- **FR-082 — Session-scoped changes.** Tuner changes SHALL be session-scoped and SHALL NOT persist
  to committed seed data; reset restores defaults.
  **AC:** After reset, the active profile is the fitted default. *(SHOULD)*
- **FR-083 — Any reachable weight vector is safe.** Any weight vector reachable through the UI SHALL
  produce a valid, non-crashing, fully-explained ranking.
  **AC:** A property test over 200 random valid vectors asserts: no exception, `Σ weights = 1.0`,
  three offers or a stated reason for fewer, and a passing read-aloud lint on every reason line.
  **The policy panel is directly manipulable by a non-engineer; this requirement is what makes that
  safe.** *(SHOULD)*
- **FR-084 — No-show-risk hook, off by default ✅ DECIDED.** A no-show-risk policy hook SHALL exist
  behind a feature flag, **OFF by default**, and SHALL be named on the known-limitations page.
  **AC:** Flag defaults to off; when on, its effect is visible as a separate labelled contribution,
  never folded silently into another axis. *(STRETCH)* — *Design rationale: a no-show-risk feature
  can proxy for socioeconomic status. That is why it is explicit, configurable, off by default, and
  recorded on the known-limitations page rather than buried inside a weight.*

---

### Use Case 12: Inspect and replay a decision trace

**As an** Office Manager / DSO Ops Lead **I want** every hop of every request recorded and
replayable without any external service **So that** any decision the system made can be audited and
reproduced later, and any failure can be diagnosed in place rather than guessed at.

**Steps:**

1. User opens the trace panel and selects a decision.
    - System shows every stage with timing, model, cost, fallbacks and gate firings.
2. User presses Replay.
    - System re-runs the deterministic pipeline from the stored extraction and asserts byte
      equality, showing a diff if it fails.

**Acceptance Criteria:** all of FR-085 … FR-091 pass.

**Functional Requirements**

- **FR-085 — `TraceSink` abstraction with fan-out.** All instrumentation SHALL go through a single
  `TraceSink` protocol that fans out to an **in-process store (always)** and to Opik (optional).
  **AC:** No observability SDK call appears outside the sink implementations — asserted by a grep
  test. *(MUST)*
- **FR-086 — Per-stage spans.** Every orchestrator stage SHALL emit a span with: stage name,
  start/end, `duration_ms`, input and output digests, model and provider when applicable, token
  counts and cost when applicable, `fallback_fired`, `gate_fired`, and error.
  **AC:** A single request produces a complete, ordered span tree with no gaps; stage durations sum
  to within 5% of end-to-end latency. *(MUST)*
- **FR-087 — Replay panel reads only the in-process store.** The replay UI SHALL NOT depend on
  Opik or on any container.
  **AC:** **With the container runtime stopped, traces render and replay normally.** *(MUST)* —
  *Design rationale: never put a container on the request path of a system that has to work on an
  arbitrary machine.*
- **FR-088 — Byte-identical replay.** Replaying a `DecisionRecord` SHALL re-run the deterministic
  pipeline from the stored extraction and assert byte equality with the stored result.
  **AC:** Replaying any recorded decision reproduces it bit-for-bit; a forced mismatch renders a
  visible field-level diff rather than failing silently. *(MUST)*
- **FR-089 — Opik is best-effort and never blocking.** Opik emission SHALL be fire-and-forget with
  a bounded queue; failures SHALL be counted and swallowed, never retried on the request path.
  **AC:** With Opik unreachable, p95 time-to-offer is unchanged within noise, and a single
  non-blocking "Opik offline" banner appears. *(SHOULD)*
- **FR-090 — Opik receives traces and eval runs when available.** When reachable, Opik SHALL
  receive the same spans plus eval-harness runs.
  **AC:** With Opik up, a golden-set run appears as an experiment in the local Opik UI. *(SHOULD)*
- **FR-091 — Redaction hook and retention policy.** `TraceSink` SHALL expose a redaction hook and a
  retention setting, no-op in the demo, documented as the PHI seam.
  **AC:** The hook exists and is unit-tested with a redacting implementation that provably removes
  patient identifiers and raw request text from an emitted span. *(MUST)* — *Design rationale:
  observability is a PHI leak vector. Traces capture prompts, and the request text becomes PHI the
  moment a patient describes a symptom.*

---

### Use Case 13: Run the eval harness and read the scorecard

**As an** Office Manager / DSO Ops Lead **I want** numbers, including the unflattering ones
**So that** the claim that this system schedules well is evidenced rather than asserted, and so that
a regression in scheduling quality is visible before a patient feels it.

**Steps:**

1. User runs the harness (one command, or a button on the policy panel).
    - System evaluates the golden set and renders the scorecard.
2. User opens the failures list.
    - System names the failing cases with the specific field or slot that missed.

**Acceptance Criteria:** all of FR-092 … FR-101 pass.

**Functional Requirements**

- **FR-092 — Golden dataset of ~40 labelled requests.** Committed, versioned; each entry carries
  raw text, expected `RequestConstraints`, the human-preferred slot ID(s), and request-class tags
  (relative date, exclusion, urgency, ambiguity, credential, equipment, gap-fill, prime-time).
  **AC:** ≥ 40 entries; every class has ≥ 3 entries; schema-validated in CI. *(MUST)*
- **FR-093 — Per-field extraction accuracy.** The harness SHALL report exact-match accuracy per
  field (`date_range`, `time_window`, `urgency`, `provider_preference`, `appointment_type`,
  `exclusions`) plus an overall figure, **for both LLM and rules modes**.
  **AC:** Two columns of numbers appear side by side. *(MUST)* — *Design rationale: this pair of
  numbers is the entire evidence for "would replacing the LLM with plain code change decision
  quality?" Without it, using an LLM is a preference rather than a finding.*
- **FR-094 — Ranking quality.** The harness SHALL report **top-1 agreement** and **top-3 hit rate**
  against the human-preferred slot.
  **AC:** Both reported with denominators; top-3 hit rate is Success Metric 1's offline proxy.
  *(MUST)*
- **FR-095 — Naive first-available baseline head-to-head.** The harness SHALL run a naive
  first-available ranker over the same golden set and report deltas in human agreement, orphan-gap
  minutes created, and protected-block minutes consumed.
  **AC:** A head-to-head table renders. **Per-request-class deltas are reported, and any class
  where the delta is small is named** — knowing where the product does not add value is part of
  knowing whether it works. *(MUST)*
- **FR-096 — Latency percentiles.** p50 and p95 time-to-offer, end to end and per stage, for both
  offline and live-LLM modes.
  **AC:** Reported against the < 2 s / < 5 s thresholds with pass/fail colouring. *(MUST)*
- **FR-097 — Determinism check.** The harness SHALL run the golden set twice in fixture mode and
  diff serialised `DecisionRecord`s.
  **AC:** Any diff fails the run and prints the differing path. Runs in CI. *(MUST)*
- **FR-098 — Weight fitting ✅ DECIDED.** A fitting routine SHALL grid-search / coordinate-ascend
  over the weight simplex to maximise top-3 hit rate (tiebreak: top-1 agreement) on the golden set.
  **AC:** Runs in **< 60 s**; emits the fitted vector and the objective value; the fitted vector is
  what ships as the **General Practice** default. *(SHOULD)* — *Design rationale: the default
  weights are fitted to 40 human decisions, not chosen. "Why 0.35?" then has an answer that is not
  an opinion.*
- **FR-099 — Sensitivity curve.** The harness SHALL sweep each axis weight 0 → 1 in 0.05 steps and
  report how much top-3 membership changes.
  **AC:** A per-axis curve renders and the **flat region is stated numerically** — e.g. *flat
  between 0.28 and 0.44*, which is direct evidence that the ranking is not weight-fragile.
  *(SHOULD)*
- **FR-100 — Named failures, shown unprompted.** The scorecard SHALL list failing cases **by name**
  with the specific field or slot that missed — not only aggregates.
  **AC:** The failures list is visible on the default scorecard view, not behind a toggle. *(MUST)*
  — *Design rationale: a scorecard that shows only aggregates is not a scorecard. Aggregates hide
  exactly the systematic failures worth fixing.*
- **FR-101 — Faithfulness and fallback telemetry.** The scorecard SHALL report gate-firing rate
  (FR-064), rules-fallback rate, and Opik-unavailable count.
  **AC:** All three appear on the scorecard. *(MUST)*

---

### Use Case 14: Run the system reliably and reproducibly

**As an** Office Manager / DSO Ops Lead evaluating this system **I want** it to start with one
command, run with no network access, and resolve relative dates against a fixed reference date
**So that** an evaluation produces the same result every time and does not depend on connectivity,
on a container runtime, or on what day it happens to be run.

**Steps:**

1. User runs one command from a cold start.
    - Backend, frontend and (optionally) the observability backend come up; a pre-flight check
      reports readiness.
2. User enables presentation mode.
    - Font sizes and contrast increase; the reference `NOW` is displayed persistently.
3. User opts in to live LLM access when a network is available.
    - The mode indicator changes; fixtures remain the default on the next start.

**Acceptance Criteria:** all of FR-102 … FR-108 pass.

**Functional Requirements**

- **FR-102 — [SD-3] Injectable reference clock.** `NOW` SHALL be injected through a single clock
  provider; `datetime.now()` SHALL NOT be called anywhere else. The reference dataset's `NOW` is
  **2026-08-10T09:00:00−07:00 (Monday)** ([D-01], settled), configurable.
  **AC:** A grep/AST test fails the build on any direct clock call outside the provider. **The
  full golden set produces identical output with the machine clock set months forward of the
  reference date** — this test is run explicitly, not assumed. *(MUST)*
- **FR-103 — [SD-3] Committed seed data, zero runtime generation.** Seed JSON SHALL be generated by
  a seeded script **offline** and committed; the application SHALL NOT generate or randomise data
  at startup.
  **AC:** Booting twice produces identical data digests; the generator script is not invoked by the
  boot command. *(MUST)*
- **FR-104 — A simulated clock is visible in the UI; a real one is not.** When `NOW` comes from
  the system clock — the default — the UI SHALL NOT display it: an application scheduling real days
  runs on today's date, and announcing that is noise. When `NOW` is pinned (`SCHED_CLOCK=frozen`,
  used by tests, evals and any demo outside the seeded window) the UI SHALL display it
  persistently and label it as simulated.
  **AC:** With the system clock, no date indicator appears on any screen. With the frozen clock, an
  amber "Simulated clock · <date>" indicator is visible on every screen in both normal and
  presentation mode. *(MUST)* — *Design rationale: the exception is what needs announcing. Under a
  pinned clock a user reading "Thursday the 13th" would otherwise resolve it against the real
  today and every date on screen would look wrong; under a real clock, saying "today is today"
  is clutter. See also FR-102 (no inline clock reads) and ladder rule 0.*
- **FR-105 — Full operation without the network.** The application SHALL boot and serve every MUST
  requirement with no network access. **Live is the default**; this requirement is about what
  survives when the model is unreachable, not about which path runs first.
  **AC:** **Verified end to end with networking disabled** (`release-check.sh` Phase C). A degraded
  run is never mistaken for a live one: the UI raises an amber indicator when — and only when —
  the deterministic fallbacks answered. The live path is the expected state and is deliberately
  *not* announced; the guess this requirement forbids was only ever possible in the degraded
  direction, which is the direction that speaks up. `make preflight` names the mode in words for
  anyone who wants it stated. *(MUST)*
- **FR-106 — One-command boot.** A single command (`make demo`) SHALL start everything needed.
  **AC:** Cold start from a clean machine state to a usable UI in **< 60 s**, executed as part of
  release verification. A pre-flight check reports backend, frontend, seed digest, reference clock,
  network mode and observability-backend status. *(MUST)*
- **FR-107 — Manual-comparison view.** A side-by-side view SHALL show the six-operatory grid a
  staffer scans today, with time-on-task measurement.
  **AC:** Opening the grid increments the manual-grid-open counter used by Success Metric 1; elapsed
  time on the manual grid is recorded per session. *(SHOULD)*
- **FR-108 — Presentation mode.** A toggle SHALL increase font sizes and contrast for large-display
  and screen-share use.
  **AC:** All card content, funnel numbers and the stability indicator remain legible at 1920×1080
  with browser zoom at 125–150%. *(MUST)*
- **FR-110 — Dictation as a front door.** The console SHALL accept the request by speech using the
  browser's Web Speech API. The transcript SHALL be written into the request field and SHALL NOT be
  submitted automatically; the operator submits it like any other text. The control SHALL be absent
  entirely where the browser provides no speech API, and SHALL be suppressible by configuration
  (`SCHED_VOICE_INPUT=false`) without a rebuild. Each decision SHALL record how its words arrived
  (`source`: `text` | `voice`), and that value SHALL survive a clarifying-question re-run.
  **Rationale:** FR-003 requires every extracted field to quote a verbatim span of `request_text`.
  If speech submitted itself, those spans would quote the *transcriber* rather than the patient, and
  a misheard "Tuesday" would enter the audit trail as something the patient said. Landing the
  transcript in a field a human confirms keeps `request_text` exactly what a human agreed was said,
  and leaves FR-003 true unchanged.
  **AC:** A dictated request and a typed request with the same text produce an **identical**
  decision — same offers, same interpretation (asserted, not assumed); an unknown `source` is
  rejected with 422 rather than stored; a body omitting `source` is treated as `text`; the mic
  control does not render when the API is missing. *(MUST)*

---

## 8. Data, Entities & Information

### Entities Involved

| Entity | Action | Key Fields Affected | Related Entities |
| :----- | :----- | :------------------ | :--------------- |
| **Location** | Read | `id`, `name`, `timezone`, `business_hours[]` | Provider, Operatory |
| **Provider** | Read | `id`, `name`, `role` (DDS/RDH/DA), `credentials[]`, `pod`, `location_assignment_by_day[]`, `working_hours[]`, `pto[]` | Location, Appointment, ScheduleBlock |
| **Operatory** | Read | `id`, `name`, `location_id`, `equipment_tags[]`, `preferred_use` | Location, Appointment |
| **AppointmentType** | Read | `id`, `name`, `duration_min`, `requires_doctor_check`, `check_duration` (10), `check_placement` (`last_third`), `required_credentials[]`, `required_equipment[]`, `production_value`, `prime_time_protected`, `default_urgency`, `continuity_multiplier` | Appointment |
| **Patient** | Read | `id`, `name`, `dob`/`age_band`, `assigned_dentist`, `assigned_hygienist`, `last_seen_by_type{}`, `no_show_history` (flag-gated) | Appointment, DecisionRecord |
| **Appointment** | Create (session copy), Read | `id`, `start`, `duration_min`, `patient_id`, `provider_id`, `operatory_id`, `type_id`, `status` | Patient, Provider, Operatory, AppointmentType |
| **ScheduleBlock** | Read, Update (unlock) | `id`, `scope` (provider/operatory/global), `kind` ∈ {`lunch`, `huddle`, `restorative_block`, `emergency_hold`, `pedo_after_school`, `admin`}, `recurrence`, `start`, `end`, `unlock_rule`, `min_production_value` | Provider, Operatory |
| **Hold** | Create, Read, Delete | `id`, `candidate_id`, `expires_at`, `session_id` | Appointment, DecisionRecord |
| **WeightProfile** | Read, Update (session) | `id`, `name`, **`scope`** (`platform` \| `group` \| `location`), **`scope_ref`**, `weights{time_fit, continuity, efficiency, prime_time}`, `efficiency_subweights{}`, `is_fitted`, `fit_objective_value` | DecisionRecord, Location |
| **DecisionRecord** (`RequestLog/Decision`) | Create, Read | `id`, **`scope`** + **`scope_ref`** (NFR-30), `raw_text` **[PHI]**, `constraints` (+confidences, +spans) **[PHI]**, `operator_corrections[]`, `annotated_candidates[]` (scores, tiers, rejection reasons), `offered[]`, `counterfactual`, `accepted_slot_id`, `override`, `weight_profile_id`, `trace_id`, `now`, **`origin_state`** (`offered` \| `offered_overflow`, see §7 UC-05) | everything |
| **TraceSpan** | Create, Read | `id`, `trace_id`, `stage`, `t_start`, `t_end`, `duration_ms`, `model`, `tokens`, `cost`, `fallback_fired`, `gate_fired`, `error` | DecisionRecord |
| **GoldenLabel** | Read | `id`, `raw_text`, `expected_constraints`, `preferred_slot_ids[]`, `class_tags[]`, `labeler` | DecisionRecord |

**Three entities carry most of the design weight:**

1. **`ScheduleBlock` is the entity most candidates will not have.** It is what makes prime-time and
   block scheduling a *modelled concept* rather than a constant buried in the scorer, and it is
   what makes the emergency-hold unlock a rule rather than a special case.
2. **`DecisionRecord` does three jobs at once** — replay substrate, eval substrate, and override
   capture. One entity, three capabilities that would otherwise each need their own store.
3. **`WeightProfile` is an entity, not constants** — because policy is what does not scale for
   free. Hundreds of offices need centrally managed profiles with local override, and that is
   impossible if the weights live in a function body.

### Multi-location ✅ DECIDED — model multi-location, demo one

`Location` is first-class and `Provider` carries **location assignment by day** (providers rotate
across offices in a DSO). The seeded dataset contains **one** location. Modelling it now makes the
multi-office extension a data question rather than a rewrite, at near-zero cost in v1.0.
Multi-location **routing** stays STRETCH; the **model** stays.

### Data Elements (selected)

| Data Element | Entity | Source | Required? | Default | Example Value |
| :----------- | :----- | :----- | :-------- | :------ | :------------ |
| `raw_text` | DecisionRecord | User input | Yes | — | "Can I come in next Thursday after 3? Prefer Sarah if she's around." |
| `date_range` | RequestConstraints | System (extractor) | Yes | search horizon | `2026-08-13 … 2026-08-13` (nearer resolution of "next Thursday"; see edge case 11) |
| `time_window` | RequestConstraints | System (extractor) | No | business hours | `15:00 … close` |
| `urgency` | RequestConstraints | System (extractor) | Yes | type default | `routine` |
| `source_span` | RequestConstraints | System (extractor) | Yes per field | — | `{text: "after 3", start: 27, end: 34}` |
| `requires_doctor_check` | AppointmentType | Seed data | Yes | `false` | `true` (prophy adult) |
| `check_placement` | AppointmentType | Seed data | Yes when check required | `last_third` | `last_third` |
| `unlock_rule` | ScheduleBlock | Seed data | No | `null` | `urgency >= urgent` |
| `weights` | WeightProfile | Fitted (FR-098) / user | Yes | `0.35/0.25/0.25/0.15` | fitted vector |
| `NOW` | Clock provider | Config | Yes | system clock (default) or `2026-08-10T09:00−07:00` when pinned | always injected, never read inline (FR-102) |

### What information is created/stored?

| Data Element | Entity | Description | Retention |
| :----------- | :----- | :---------- | :-------- |
| Decision records | DecisionRecord | Full request → decision provenance | In-memory + JSONL for the session; cleared on explicit "clear traces" |
| Trace spans | TraceSpan | Per-hop instrumentation | In-process store (always) + Opik (optional, local) |
| Session schedule copy | Appointment | Bookings made during the demo | Discarded on reset; never written to committed seed |
| Holds | Hold | Soft holds with TTL | 15 min TTL [A-07]; cleared on reset |
| Overrides | DecisionRecord | Operator chose outside the top 3 | Exportable into the golden set |

### Seed dataset sizing (per `docs/product-direction.md` §5)

| Dimension | Value |
| :-------- | :---- |
| Locations | **1** (multi-location modelled) |
| Operatories | **6** — OP-1/OP-2 hygiene-primary; OP-3/OP-4 restorative; OP-5 surgical-capable; OP-6 CEREC + pano ([A-16b] names/equipment illustrative) |
| Providers | **9** — 3 dentists, 4 hygienists, 2 assistants. **Fixed by the reference scenarios: hygienist "Sarah" and "Dr. Patel."** Others illustrative. Pod A / Pod B assignment for the 0.7 continuity tier |
| Patients | **~120** |
| Appointment types | **~12** — prophy adult 60 / child 40, perio maintenance 60, NP exam + FMX 90, limited exam (emergency) 30, filling 1-surface 40 / 2-surface 60, crown prep 90, crown seat 45, extraction 45, RCT 90, denture adjust 20 |
| Reference `NOW` | **2026-08-10T09:00:00−07:00 (Monday)** ([D-01], settled) |
| Schedule window | **History** Mon **2026-08-03** → Fri **2026-08-07** (completed, ~60% occupancy, supplies continuity history); **bookable** Mon **2026-08-10** → Fri **2026-08-21** (**70–80% occupancy**); **tail** Mon **2026-08-24** → Fri **2026-08-28** (~30%, mostly beyond the search horizon — supports out-of-horizon overflow answers) |
| Search horizon | 14 days from `NOW` → through Mon **2026-08-24** ([A-09]) |
| Total appointments | **~250–400.** *Reconciliation rule:* if the occupancy targets over the full window overshoot, **occupancy on the bookable fortnight wins** and the history week's density is the release valve. |
| Shape | Near-full days at **Tue 2026-08-11** and **Thu 2026-08-13 PM**; **one visibly sparse day at Fri 2026-08-14** so that "later is easier" is a real, visible gradient rather than an assertion |

**Why the size is what it is:** large enough that the grid is realistic and hand-scanning is visibly
slow; small enough to eyeball and debug by hand. Occupancy is the variable that matters —
too empty and every request has an easy answer; too full and everything is a rejection.

**Generation policy:** generate with a **seeded script**, hand-author **~15 scenario appointments**
on top, then **commit the resulting JSON**. Do not regenerate at startup (FR-103). A loader
validation pass runs on boot and reports anomalies without crashing.

### Deliberately seeded edge cases → requirement traceability

The seed dataset is not random data with a few appointments in it. **Each of the eleven cases below
is placed deliberately to exercise a specific requirement**, so that the requirement is validated
against realistic contention rather than a synthetic unit fixture. Day/operatory anchors are the
design intent; the seed author may shift them provided every case remains reachable from the
reference scenarios and the golden set.

| # | Edge case | Seeded anchor ([D-01] window) | Exercises | Why it matters |
| - | :-------- | :---------------------------- | :-------- | :------------- |
| 1 | **Doctor-check starvation** — three hygiene operatories open, every dentist in back-to-back crowns | **Thu 2026-08-13 PM**, OP-1 / OP-2 / OP-6 | FR-023, FR-027, FR-030 | The multi-resource point: operatory-available ≠ bookable. A slot that looks wide open on the grid is structurally un-bookable, and only the ledger can say so |
| 2 | **Provider PTO** over the patient's usual hygienist (Sarah) | **Wed–Fri 2026-08-12 → 08-14** | FR-019, FR-041, FR-055 | Forces the continuity-vs-timing tradeoff and produces a genuine counterfactual rather than a contrived one |
| 3 | **The orphan gap** — a **50-minute** hole that exactly fits a 40-min filling plus its 10-min turnover | **Wed 2026-08-12**, OP-3 | FR-018, FR-043 | The efficiency axis's positive case: a booking that creates zero orphan minutes |
| 4 | **The fragmenting trap** — a 90-min open stretch where booking 30 min in the middle creates two dead 30-min orphans | **Wed 2026-08-12**, OP-4 | FR-043, FR-059 | The scorer pushes the booking to the **edge** of the stretch, and the reason line says why in patient-readable words |
| 5 | **Urgent with nothing open** | **Tue 2026-08-11**, near-full all day | FR-035, FR-036, FR-037 | Empty-tier escalation, emergency-hold unlock, bump candidates. The product must never answer a patient in pain with an empty list |
| 6a | **Ambiguous type, hypotheses diverge** — "my tooth's been bothering me" (30-min limited exam vs. 90-min crown) | Type-level; any day in the bookable window | FR-011, FR-012, FR-014 | Decision-relevance test → **asks** one question |
| 6b | **Ambiguous type, hypotheses agree** | Contrast case | FR-011, FR-015 | Decision-relevance test → **does not ask**, proceeds with a flag. The contrast is what proves the test is a test and not a coin flip |
| 7 | **Credential mismatch** — patient asks for an oral surgeon for a cleaning | Provider-level | FR-010, FR-020 | Graceful redirect to credentialed providers, not an empty list and not a silent substitution |
| 8 | **Equipment constraint** — an extraction that only fits the surgical-capable (and busiest) operatory | OP-5 | FR-021 | The multi-resource constraint is not just provider + chair; equipment is a third axis of scarcity |
| 9 | **One deliberately dirty record** — an appointment overlapping a lunch block | History week, **Wed 2026-08-05** | FR-103; §10 loader validation | Real PMS data is dirty. The loader quarantines and reports rather than crashing or silently ingesting |
| 10 | **Chronic no-show patient requesting prime time** | Patient-level | FR-084 (flag **OFF**) | The fairness lever exists, is explicit, and is off by default — see R-09 |
| 11 | **Relative-date ambiguity** ([D-03]) — from Mon 2026-08-10, *"next Thursday"* is legitimately **Thu 2026-08-13** or **Thu 2026-08-20** | Both Thursdays seeded with **different shapes of contention**: 08-13 PM is doctor-check-starved with Sarah on PTO (cases 1 + 2); 08-20 PM has Sarah back but OP-1/OP-2 booked solid 13:00–17:00 | FR-003, FR-004, FR-011, FR-014 | The two resolutions produce **materially different top-3 sets**, so the decision-relevance test fires and the system asks exactly one question. Relative-date ambiguity is the most common and most damaging ambiguity in real scheduling language — a wrong week is a missed appointment — and this anchor date exercises it for free. A paired golden-set entry using an unambiguous phrasing confirms the system does **not** ask when it need not |

### Privacy & Sensitivity

- **All data is 100% synthetic.** No real PHI exists in this repository. Patient names are
  obviously fictional.
- **No PHI to a third-party model without a BAA** — stated as the production rule; not applicable
  here because the data is synthetic.
- **Production posture, specified now because it constrains the architecture rather than being a
  later concern:**
  **(a) Minimise** — send opaque patient IDs to the model and rehydrate names client-side.
  **(b) Contract** — BAA, or a VPC/self-hosted model, with zero retention.
  **(c) Audit** — every decision already logs with a trace ID, which is most of an audit trail.
  **(d) The trap:** *observability is a PHI leak vector.* Traces
  capture prompts. That is precisely why `TraceSink` is an abstraction with a **redaction hook and
  a retention policy** (FR-091) rather than SDK calls sprinkled through the code.
- **The request text itself becomes PHI the moment a patient describes a symptom.** This is the
  non-obvious consequence: the free-text input field, not just the patient record, is regulated
  data.
- **Secrets:** the Anthropic API key lives in a **gitignored `.env`**, is never committed, and is
  not required for offline operation.
- **Logging:** raw request text is stored in `DecisionRecord` for replay; in production this field
  is the first thing the redaction hook would target.
- **PHI is marked on the model, not tracked in someone's head [spec-refinement].** Fields that
  would carry PHI in production are annotated as such on the domain types (NFR-31), and the
  redactor is **derived** from those annotations. The alternative — a hand-maintained list of
  field names inside the redactor — is correct exactly once, and then silently wrong the first
  time a field is added by someone who did not know the list existed.
- **The redaction placement argument is demo-specific and must be revisited before any real
  deployment.** In v1.0, redaction is applied to the *external* sink and deliberately **not** to the
  in-process trace store, because that store is the byte-identical replay substrate (FR-088) and
  lives only in memory on one machine. In production the local store **is a database**, and the
  argument inverts: `raw_text` becomes PHI at rest requiring encryption, retention, and access
  control, and *replay itself becomes a permissioned, audited action* — replaying a decision means
  reading a patient's own words. Recorded here so the v1.0 reasoning is not mistaken for a
  production posture.

---

## 9. Integrations

### External Systems

| System | Purpose | Direction | Interface Type | Format | Error Handling |
| :----- | :------ | :-------- | :------------- | :----- | :------------- |
| **Anthropic Claude API** | Intent extraction (agent 1), constraint verification (agent 2), explanation phrasing (agent 4) | Outbound | HTTPS API (Messages) | JSON | Per-stage timeout → **deterministic fallback** (FR-005 rules extractor, rules verifier, template explainer). Failures are logged to the trace as `fallback_fired`, never surfaced as errors. **Model version string is pinned in config and forms part of the fixture cache key.** Temperature 0. |
| **Opik (self-hosted, localhost container)** | Trace and eval observability | Outbound | HTTP to `localhost` | JSON | **Optional at runtime.** Fire-and-forget, bounded queue, failures counted and swallowed (FR-089). **Never on the request path** (FR-087). |
| **Committed JSON fixtures** (filesystem) | Seed data, cached LLM responses, golden dataset | Inbound | Local file read | JSON / JSONL | Loader validation reports anomalies (edge case 9) without crashing; a schema failure on seed data fails boot loudly. |

**No other external system is integrated.** No PMS integration, no practice-management API, no
calendar provider, no payment, no messaging. v1.0 is self-contained and runs against a committed
reference dataset. Integration with a live practice-management system is the natural v2 boundary
and is deliberately deferred: the scheduling logic must be demonstrably correct against a known
dataset before it is pointed at a production schedule.

### Internal Systems

| System | Interaction |
| :----- | :---------- |
| FastAPI backend | Serves the orchestrator, reasoner, eval harness, and trace store |
| React + TypeScript (Vite) frontend | Operator console, policy panel, trace/replay panel, scorecard |
| In-process trace store | Always-on trace sink; sole data source for the replay panel |
| Session schedule store | In-memory copy of the committed seed; reset restores it |

---

## 10. Error Handling & Edge Cases

### Expected Errors

| Scenario | Expected Behavior | User Message |
| :------- | :---------------- | :----------- |
| LLM call times out or errors | Per-stage timeout fires; deterministic fallback runs; `fallback_fired` recorded | *(silent — no error shown)*; trace panel shows the fallback |
| LLM returns malformed / non-schema JSON | One bounded retry, then fallback to rules extractor | *(silent)*; trace records `schema_violation` |
| Faithfulness gate fails | Template rendering substituted silently; `gate_fired` + failing check ID logged | *(silent)*; trace shows the gate firing |
| Network unavailable | Fixture mode; if no fixture, rules path | Mode indicator reads "Offline (fixtures)" |
| Container runtime stopped / observability backend unreachable | App fully functional; trace + replay unaffected | Single non-blocking banner: "Observability backend offline — traces are local" |
| Requested provider does not exist | Verifier flag; treated as no preference | "I don't see that provider here — I'll look across everyone." |
| Requested date is in the past | Verifier flag; clamp forward and ask for confirmation | "That date has already passed — did you mean Thursday the 13th?" |
| Requested provider not credentialed for the type | Graceful redirect to credentialed providers (edge case 7) | "Dr. Okafor handles surgery; for a cleaning I'll look at our hygienists." |
| No feasible candidate in the top tier | Escalate: emergency-hold unlock (FR-036), then labelled overflow (FR-038) | "Nothing opened before Thursday, but here's the soonest we have." |
| Zero feasible candidates in the entire horizon | Return the nearest three outside the horizon, explicitly labelled; never an empty screen | "Nothing fits in the next two weeks — here's the soonest after that." |
| Confirm re-verification fails (state changed) | Named error; offers re-run automatically | "That slot just filled — here are three fresh options." |
| Hold TTL expires | Slot returns to available; card marks itself stale | "This hold expired — press Hold again to keep it." |
| Seed data fails schema validation on boot | **Boot fails loudly** — a silently-degraded dataset is worse than no boot | Console: named file, named record, named field |
| Seed data contains a semantic anomaly (edge case 9) | Loader logs the anomaly, quarantines the record, continues | Pre-flight report lists "1 anomaly quarantined" |
| Weight vector sums to 0 | Rejected at the API boundary; previous profile retained | "Weights can't all be zero." |

### Edge Cases

| Scenario | Expected Behavior |
| :------- | :---------------- |
| **"Next Thursday" is genuinely ambiguous** (this week vs. next) — from Mon 2026-08-10 it is either Thu 08-13 or Thu 08-20 | The extractor emits **both hypotheses** with confidences and source spans (FR-003, FR-014). The decision-relevance test (FR-011) compares the two resulting top-3 sets: **when they differ, the system asks one question; when they agree, it proceeds with the nearer date and shows a flag chip.** The interpretation chip stays editable in one click (FR-007). Seeded as edge case 11 |
| "After 3" could mean 03:00 | Resolve to 15:00 with a business-hours prior; confidence and span shown. **Ranked failure mode #1 — this is exactly the class of silent, plausible error the interpretation strip exists to catch** |
| Patient states an exclusion that removes all feasible slots | Exclusion stays hard; overflow path fires; the reason line names the exclusion as the cause |
| Two candidates score within ε | Presented co-equal with differentiating reasons (FR-049) |
| Three best candidates are 10 minutes apart in the same operatory | Diversity constraint suppresses two (FR-050); `limited_availability` flag if no spread exists |
| **User phrases a request unlike anything in the golden set** | Handled by the normal path, not a special case. ~20 adversarial phrasings are pre-tested ("sometime after the holidays", "not with Dr. Kim", "my kid gets out of school at 3") and carried as golden-set class tags. **When extraction does fail, the trace panel makes the failure diagnosable in place rather than a black box** |
| Machine clock has moved past the reference dataset window | No effect — `NOW` is injected (FR-102); verified by an explicit clock-forward test |
| Repeated bookings during a long evaluation session | Session copy accumulates; one-click reset restores the reference state (FR-071) |
| School-age patient requesting 3–5 pm | **Not** penalised by prime-time protection; the `pedo_after_school` block is *for* them (FR-045) |
| Crown seat requested with a different dentist than did the prep | Continuity multiplier 2.0 pushes same-dentist candidates above all others (FR-041) |

---

## 11. Non-Functional Expectations

**These are first-class requirements here, not boilerplate.** For this product, "survives runtime
failure without a network" and "explainable without a narrator" *are* the quality bar — a
scheduling assistant that is slow, non-reproducible, or unexplainable will simply not be used, and
the operator will reopen the calendar grid.

### Performance

| ID | Requirement | Acceptance |
| :- | :---------- | :--------- |
| **NFR-01** | **Time-to-offer < 2 s p95 in the degraded (fixture/rules) path** | Measured by the harness over the golden set; enforced as a threshold in the scorecard |
| **NFR-02** | **Time-to-offer.** Fixture path < 2 s p95. **Live path: 3.9 s p50 — inside the 5 s target.** | First measured at ~15.9 s, and recorded here as *not met* rather than quietly dropped, because "beyond ~5 s the human opens the calendar anyway" was the whole argument. Keeping the failure visible is what funded the work that closed it (ADR-21): latency tracked **output tokens** almost linearly, so the extraction schema became quotes with offsets computed locally; adaptive thinking was worth < 0.2 s and was not the lever; and verification does not gate the search, so it now runs in parallel with reason-and-explain. Provenance was never the cost — every field still carries a confidence, a rule and a verbatim span. Sub-2 s remains open and is priced in `known-limitations.md` §12 |
| **NFR-03** | **Per-stage timeout and fallback ladder.** Every orchestrator stage has an explicit timeout; exceeding it triggers the deterministic fallback rather than failing the request | A forced-timeout test per LLM stage returns a complete response within the budget |
| **NFR-04** | **Deterministic re-rank < 300 ms** (weight change, interpretation edit) with zero LLM calls | Measured; trace shows no LLM span |
| **NFR-05** | **Rank-stability computation (200 samples) < 500 ms** | Measured |
| **NFR-06** | **Candidate enumeration + feasibility < 150 ms** for the full horizon | Measured. *"The LLM call is the latency floor, not the search"* — this number is the evidence |
| **NFR-07** | **Data volume:** 1 location, 6 operatories, 9 providers, ~120 patients, ~250–400 appointments, 14-day horizon, 10-min grid | Enumeration count is a few hundred to a few thousand per request; fits in memory |
| **NFR-08** | **Concurrent operators: 1 in v1.0** — single-session by design. **This is a scope decision, not a licence for an unsafe write path** *(rationale amended)* | Multi-seat concurrency changes the hold model (FR-068) and is deferred until hold semantics are validated single-seat. But the original rationale concealed a **correctness** requirement behind a scope one: FR-069 now mandates a conditional write, because check-then-write double-books at two seats and cannot fire at one — the worst combination of severity and undetectability. The deferred work is the *hold* model and *cross-process* state; the atomic commit is not deferred |

### Availability & Runtime Resilience

| ID | Requirement | Acceptance |
| :- | :---------- | :--------- |
| **NFR-09** | **Full offline operation.** Every MUST requirement works with no network access | **Verified end to end with networking disabled** — `scripts/release-check.sh` Phase C blocks outbound connections at the socket layer and unsets the key. Note the inversion since the first draft: offline is now the **fallback**, not the default. The product ships live; losing the network degrades it to fixtures and then to rules, silently for the operator and loudly in the trace |
| **NFR-10** | **No container on the request path.** With the container runtime stopped, the app boots, serves, traces and replays normally | Verified with the container runtime stopped. The observability backend is an optional enrichment, never a dependency |
| **NFR-11** | **One-command boot in < 60 s from a cold, clean machine state** | `make demo`; executed from a clean state as part of release verification |
| **NFR-12** | **Pre-flight check** reports backend, frontend, seed digest, reference clock, network mode and observability-backend status | Runs automatically on boot and is re-runnable on demand; any red item is named, not just counted |
| **NFR-13** | **Determinism / reproducibility.** Identical inputs produce **byte-identical** outputs in fixture mode | Golden set run twice and diffed; enforced in CI (FR-097) |
| **NFR-14** | **Injectable reference clock.** No direct clock access outside the provider | AST/grep test fails the build; clock-forward test passes (FR-102) |
| **NFR-15** | **No runtime data generation.** Seed digests identical across boots | FR-103 |
| **NFR-16** | **Graceful degradation is silent to the operator and loud in the trace** | Every fallback and gate firing is invisible in the operator UI and visible in the trace panel |
| **NFR-17** | **Standard contractual SLAs: N/A for v1.0.** The system runs locally against a committed dataset and carries no uptime obligation | Stated deliberately rather than left blank. The availability requirements that *do* bind v1.0 are re-expressed as NFR-09 … NFR-12; a hosted deployment would reopen this row |

### Security

| ID | Requirement | Acceptance |
| :- | :---------- | :--------- |
| **NFR-18** | **Authentication: none.** Deliberate non-goal (§6) | Surface separation is by route, not by role |
| **NFR-19** | **Authorization/roles: none in v1.0.** The operator/manager surface split is a UX boundary, **not a security boundary** — stated explicitly so it is never mistaken for one | Documented on the known-limitations page. Any deployment beyond a single trusted workstation must add real authorization before the policy panel is exposed |
| **NFR-20** | **No secrets in the repository.** API key in a gitignored `.env`; app boots without it | Verified by booting from a clean clone with no `.env` |
| **NFR-21** | **Compliance: none applicable** (100% synthetic data). Production HIPAA posture specified in §8 | §8 *Privacy & Sensitivity* |
| **NFR-22** | **Redaction hook + retention policy on `TraceSink`** — no-op in v1.0 (synthetic data), unit-tested with a real redacting implementation | FR-091 |

### Accessibility

| ID | Requirement | Acceptance |
| :- | :---------- | :--------- |
| **NFR-23** | **Large-display legibility is the binding accessibility constraint.** Presentation mode increases font sizes and contrast; all critical content legible at 1920×1080 with browser zoom 125–150% | FR-108; verified on an external display and in a screen-share |
| **NFR-24** | **Contrast: WCAG 2.1 AA for text and for contribution-bar segments.** Bar segments must be distinguishable **without relying on colour alone** (labels + ordering) | Contrast checked; a greyscale screenshot remains interpretable |
| **NFR-25** | **Keyboard-first operator flow.** Submit, edit a chip, and hold cards 1/2/3 without a mouse | FR-052; the front desk is a keyboard job and a mouse round-trip is dead air on a live call |
| **NFR-26** | Full WCAG AA conformance beyond the above is **explicitly deferred** for v1.0 and named as a non-goal, not silently skipped | Known-limitations page. Deferred, not rejected — a front-desk tool used all day is exactly the kind of software that needs it |

### Code Legibility & Maintainability (a first-class NFR for this product)

The system's core claim is that its decisions are explainable. That claim does not survive a
codebase whose control flow cannot be followed. These two requirements exist so that the
scheduling logic can be reviewed, modified and trusted by someone who did not write it.

| ID | Requirement | Acceptance |
| :- | :---------- | :--------- |
| **NFR-27** | **The orchestrator is a plain, readable Python state machine under ~150 lines** with explicit stages, per-stage timeout and fallback, and a `TraceSink` emit at every hop. **Not LangGraph/CrewAI** | Line count checked; an engineer new to the codebase traces one request through it in ≤ 5 min. *This is a deliberate choice, not a shortcut: a legible hand-rolled orchestrator can be read and modified in an afternoon, whereas a framework DAG requires learning the framework before the first change* |
| **NFR-28** | **Every agent is a `Protocol` with two implementations** (LLM and deterministic), swappable by config | Satisfied for all three model-backed roles. The verifier's LLM implementation was the last one built, and until it existed this row was aspirational for that role — the config advertised `llm \| rules` and only rules existed. **This seam is what makes the LLM-vs-deterministic tradeoff measurable (FR-093) rather than asserted**, and it is what lets the model be removed from any stage that stops earning its latency |

### Extension seams [spec-refinement]

Three seams that cost nothing to build now and are structural to retrofit. They are stated as
requirements rather than left to the architecture because each one is a place where v1.0's
simplifying assumption would otherwise leak into code that outlives it. **None of them adds a v1.0
feature** — each only fixes where a boundary sits.

| ID | Requirement | Acceptance |
| :- | :---------- | :--------- |
| **NFR-29** | **The reasoner reads the schedule through a `ScheduleRepository` `Protocol`, never through a concrete store.** The v1.0 implementation is the in-memory session copy; the interface exposes reads, a conditional commit (FR-069), and per-`(resource, day)` invalidation | An import-guard test asserts `reasoner/**` imports no concrete storage module. A second in-memory implementation (used by the eval harness for per-case isolation) proves the seam is real rather than nominal. *Every other boundary in this system is a `Protocol`; the one between domain logic and persistence was the omission* |
| **NFR-30** | **`WeightProfile` and `DecisionRecord` carry an owning scope** (`platform` / `group` / `location`) from v1.0, populated with the single seeded location. **Resolution and inheritance logic is deferred**, the field is not | Schema-validated; every profile has a scope. A test asserts no query path ignores it. *The field is free today and a migration-plus-guesswork later — and the inheritance semantics it enables are the multi-practice product, not a deployment detail (§6)* |
| **NFR-31** | **PHI-bearing fields are marked on the domain model**, and the `TraceSink` redactor is **derived** from those marks rather than hand-maintained | A test adds a new PHI-marked field and asserts the redactor covers it with no redactor change. *A hand-written redactor drifts the first time someone adds a field; deriving it makes the drift impossible rather than reviewable* |
| **NFR-32** | **One timezone conversion boundary.** Every stored instant is timezone-aware and carries its `Location`'s IANA zone. Slot arithmetic operates on **minute offsets from that location's day-open**, and conversion between the two happens in exactly one module | An AST test asserts no naive `datetime` is constructed outside the conversion module, and no arithmetic crosses a day boundary in local time. A DST-transition test fixture (a spring-forward and a fall-back day) is enumerated and asserted even though neither falls inside the v1.0 seed window — **the test exists before the data does**, because this is the class of bug that is invisible until the day it is not |

### Platform Support

- **Browsers:** Chrome/Chromium latest (the reference browser). Firefox/Safari best-effort, untested in v1.0.
- **Devices:** a developer/operator workstation, optionally driving an external display at 1920×1080. **No mobile, no tablet, no touch.**
- **OS:** macOS (Darwin 24.x) is the reference platform; nothing in the stack is macOS-specific. Python **3.12 pinned via `uv`**; Node 25.x.
- **Hardware assumed:** ≥ 16 GB RAM, ≥ 8 CPUs, ~5 GB free disk. The full dataset fits in memory.

---

## 12. UI/UX Requirements

### Design Assets

- **Figma / design link:** **None.** No designer is involved; there is no design file and one is not
  being commissioned. The UI is specified by this section plus the prototype phase. *This is a
  deliberate scope decision, not a gap.*
- **Locofy link:** N/A.
- **Brand guidelines:** None yet. Neutral, professional, clinical-adjacent. **No imitation of any
  incumbent practice-management product's visual identity** — a partial imitation reads worse than
  a clean neutral one and creates a false expectation of feature parity. [A-16]

### Visual Depth / Surface Style

- **Flat**, with restrained elevation (1-level shadow) used only to separate the three offer cards
  from the page. No skeuomorphism, no neumorphism, no glassmorphism. [A-16]
  *Rationale: users read numbers off this screen under time pressure, sometimes on a shared or
  projected display; ornament costs contrast.*

### Theme and Responsive

- **Theme:** **Light, single theme.** Plus a **Presentation Mode** that increases type scale and
  contrast (FR-108). No dark mode in v1.0 — a second theme doubles the contrast-verification
  surface (NFR-24) for zero decision quality. [A-16]
- **High contrast:** yes, via Presentation Mode (NFR-23, NFR-24). **Reduced motion:** respected; the only
  animation is the card-reorder transition on weight change, which is suppressed under
  `prefers-reduced-motion`.
- **Responsive:** **Desktop-only, 1280–1920 px.** Not mobile-first, not adaptive. Explicit non-goal.

### Design System / Component Library

- **Design system:** **Tailwind CSS** utility layer, no heavyweight system. [A-16]
- **Component library:** **shadcn/ui on Radix primitives** — accessible primitives, source-in-repo
  (so components are readable and modifiable in-repo rather than a black-box dependency). [A-16]
- **Custom vs. off-the-shelf:** off-the-shelf for primitives (slider, dialog, tooltip, disclosure);
  **custom for the four artifacts that carry the product's argument** — the interpretation strip,
  the funnel counter, the stacked contribution bar, and the rank-stability indicator.

### Material Types

- **2D only.** One micro-animation (card reorder on weight change) because the *movement itself* is
  the evidence that weights matter. No 3D, no video, no immersive. [A-16]

### Key UI Elements

| # | Element | Surface | Contract |
| - | :------ | :------ | :------- |
| 1 | **Request box** | Operator | Single multiline input, patient selector, Enter to submit, example requests one click away |
| 2 | **Interpretation strip** | Operator | One chip per extracted field: resolved value, confidence band, **verbatim source span** on expand, one-click edit (FR-007, FR-067) |
| 3 | **Funnel counter** | Operator | `enumerated → feasible → in-tier → offered`, four live numbers, reconciling with the conservation invariant (FR-029) |
| 4 | **Three offer cards** | Operator | Weekday + date + time, provider, duration, type, score %, stacked contribution bar, one reason line, one primary action (FR-053) |
| 5 | **Reason line** | Operator | ≤ 25 words, phone-readable, read-aloud lint enforced (FR-065) |
| 6 | **Rejection ledger** | Operator | Collapsed by default; grouped by single cause with counts; expandable to individual candidates (FR-030, FR-031) |
| 7 | **Counterfactual line** | Operator | One sentence beneath the cards (FR-058) |
| 8 | **Clarifying question** | Operator | One question, 2–3 answer chips, never free text (FR-013) |
| 9 | **Weight sliders + presets** | Policy | Four axes, renormalising, two decimals, four named presets (FR-077, FR-078) |
| 10 | **Rank-stability indicator** | Policy | Stated in words with a number; updates on every change (FR-081) |
| 11 | **Eval scorecard** | Policy | Extraction accuracy (LLM vs. rules), top-1/top-3, baseline head-to-head, latency, sensitivity curve, determinism, **named failures visible by default** (FR-100) |
| 12 | **Trace panel + replay** | Trace | Ordered spans with latency, model, cost, `fallback_fired`, `gate_fired`; Replay button with byte-equality assertion (FR-086, FR-088) |
| 13 | **Manual-comparison grid** | Operator (comparison) | Six operatory columns as a staffer sees them today; time-on-task measurement; increments the manual-open counter (FR-107) |
| 15 | **Dictation control** | Console | A mic button in the command bar: fills the request field, never submits. Absent where the browser has no speech API (FR-110) |
| 14 | **Exception indicators** | Global | Nothing is shown for the expected state (live models, real clock). Amber pills appear only for a simulated clock (FR-104) or a degraded model path (FR-105); observability-backend status when tracing is local-only |
| 15 | **Reset to reference data** | Global | One click, < 1 s, reachable everywhere (FR-071) |

### Interaction Patterns

- **Keyboard-first.** Enter submits; `1`/`2`/`3` hold the corresponding card; `E` focuses the first
  editable chip; `R` resets. The front desk is a keyboard job.
- **One primary action per card.** Everything else is behind disclosure. Decision surface stays at
  three choices.
- **Progressive disclosure of evidence.** Default view: three cards + one summary line. One click
  reveals the rejection ledger. One more reveals individual candidates. **Depth is always exactly
  one click away and never on screen by default** — the operator's decision surface stays at three
  choices even though the evidence behind them is complete.
- **Never a naked number.** Any score shown is accompanied by its decomposition (FR-047, FR-080).
- **Silent degradation, loud tracing.** Fallbacks and gate firings never interrupt the operator and
  always appear in the trace panel.
- **Live re-rank animates.** Cards move rather than snap, so the user *sees* which options the
  policy change actually moved, immediately followed by the updated stability number.
- **No modal ever blocks the primary flow.** Nothing on the request path is gated behind a dialog;
  the clarifying question (FR-013) renders inline, because a patient is waiting.

---

## 13. Constraints & Dependencies

### Constraints

| Constraint | Detail |
| :--------- | :----- |
| **Fixed delivery date** | **v1.0 stakeholder demo build due 2026-08-10 (Mon)** ([D-02]). The §6 MUST / SHOULD / STRETCH triage is the mechanism for meeting it: MUST is not negotiable, STRETCH is the release valve |
| **Delivery sequencing** | Data model and committed reference dataset first (everything downstream depends on it), then the deterministic reasoner, then extraction with fallback, then UI, then the eval harness and golden set, then the tuner / counterfactual / explainer gate, then tracing and observability, then the documentation package |
| **Reference dataset must precede the golden set** | The golden set labels *specific slots* in the seeded schedule. Changing seed data after labelling invalidates labels. Freeze the dataset before labelling begins |
| **Locked stack ✅ DECIDED** | Python 3.12 (pinned via `uv`) + FastAPI; React + TypeScript (Vite); Claude API with deterministic fallback + committed fixtures; Opik self-hosted in a local container behind a `TraceSink` abstraction |
| **Target runtime environment** | Must run on a single developer/operator workstation. **A container runtime may or may not be running** — the system must not require one (hence NFR-10). Python 3.12 via `uv`; Node 25.x |
| **Documentation package ✅ DECIDED** | The working application is the primary artifact; documentation supports it rather than substituting for it. Deliverables: one architecture diagram, a demo script covering the reference scenarios, a design-rationale FAQ, and a known-limitations page |
| **Labelling capacity** | The golden set is labelled by **a single annotator**. This is a known, disclosed methodological limitation (§14 R-08), not a defect to hide |

### Dependencies

| Dependency | Type | Status |
| :--------- | :--- | :----- |
| Anthropic API key in a gitignored `.env` | **Needed for the shipped configuration**; without it the app still boots and answers, on the degraded path | Available; supplied at runtime, never committed |
| `uv` + Python 3.12 toolchain | Blocks this work | Available |
| Node 25.x + Vite | Blocks this work | Available |
| Container runtime (observability backend only) | **Optional — must never block** | NFR-10 makes its absence a non-issue by design |
| ~40 human-labelled golden requests | Blocks FR-092 … FR-099 (eval + weight fitting) | Not started; blocks the entire measurement story, including the fitted default weights |
| Committed reference dataset with the eleven edge cases | Blocks UC-03 … UC-09 and the golden set | Not started; first work item |
| External display at 1920×1080 | Needed by NFR-23 verification | Available |
| Architecture diagram, demo script, design-rationale FAQ, known-limitations page | Needed by release | Not started; the **postArchitecture and flow diagrams are produced by the architect phase**, not here |

---

## 14. Open Questions

### Product risk register

Sixteen risks, each restated as the question a stakeholder — an office manager, a security
reviewer, an engineer inheriting the code — would reasonably ask, and each answered by something
that exists in the product rather than by an argument. **A risk whose mitigation cannot be pointed
at is an unmitigated risk**, so the third column names the requirement, metric or surface that
verifies it.

| ID | Risk / stakeholder question | Mitigation built into the product | Verification / evidence |
| :- | :-------------------------- | :-------------------------------- | :---------------------- |
| **R-01** | **The agentic framing may not be justified.** Why agents rather than a rules engine? | For the *scheduling* half it **is** a rules engine, deliberately. The agentic part is confined to language: turning *"whatever works next week, I have PT on Tuesdays"* into typed constraints, and turning score components into a sentence readable to a patient. In the core, an LLM would add latency and nondeterminism and remove the ability to answer "did it miss anything?" | FR-093 rules-vs-LLM accuracy pair (the number that decides it); NFR-27, NFR-28 |
| **R-02** | **The system may not actually work, and nobody would know.** How is scheduling quality measured? | ~40 labelled requests; per-field extraction accuracy; top-1 and top-3 agreement; reproducibility enforced in CI; **and a named failure list surfaced by default, not on request** | Eval scorecard (FR-092 … FR-101), especially FR-100 |
| **R-03** | **The LLM will sometimes be wrong.** What happens then? | Three layers. (1) The verifier catches structurally-wrong extractions (UC-02). (2) Low confidence changes behaviour — the interpretation renders as editable chips with verbatim source spans. (3) **The LLM never touches the ranking**, so a language error can produce the wrong *search* but never an infeasible *booking*. Explanations are faithfulness-gated | UC-02; FR-054; FR-062, FR-063 |
| **R-04** | **Residual risk that cannot be engineered away:** a confidently-wrong date that the operator does not notice | Mitigated at the **UI level**: the read-aloud reason line and the booking confirmation both echo the resolved date ("Thursday the 13th at 3:40"), **so the patient catches it.** Human confirmation is load-bearing by design — this is why the product is *"confirm, not investigate,"* not *"autonomous booking"* | FR-065, FR-073; §6 non-goal "autonomous booking" |
| **R-05** | **Scalability.** Does this work beyond one office? | Computationally: enumeration is O(days × operatories × granularity) — a few hundred candidates per request, sub-millisecond; **the LLM call is the latency floor, not the search.** The production shape is a precomputed availability index per provider/operatory-day with incremental invalidation on write. Organisationally: per-request against a fixed schedule is embarrassingly parallel across offices. **What does not scale for free is *policy*** — which is why `WeightProfile` is an entity, not constants. Honest limit: no global re-optimisation, by choice | NFR-06; FR-046; `Location` in §8 |
| **R-06** | **The optimisation approach may be under-powered.** Why not OR-tools or an ILP? | This is a recommendation for **one request against a fixed schedule**, not a global re-optimisation. With hundreds of candidates, exhaustive enumeration is exact, sub-millisecond and fully explainable; an ILP returns the same answer with less legibility. **Honest concession: bump candidates are a first step into that space, and that is where a solver would earn its keep** | §6 non-goals; FR-037 |
| **R-07** | **The product may add no value over first-available.** | Head-to-head against a naive first-available baseline over the same golden set, reporting human agreement, orphan-gap minutes and protected-block consumption. **Where the delta is small for a request class, the harness names the class** rather than reporting only the favourable aggregate | FR-095; Success Metric 3 |
| **R-08** | **Single-annotator bias in the golden dataset — a known, disclosed methodological limitation** | The labels currently encode one person's judgment of "good," not a practice's. This is recorded rather than hidden, because it bounds every ranking number in §4. The fix is 2–3 practising schedulers labelling independently and reporting inter-rater agreement. **If they disagree substantially, that disagreement is itself the business case for a configurable policy layer** | Known-limitations page; `GoldenLabel.labeler` field in §8; open question below |
| **R-09** | **Bias and fairness.** A scorer that optimises production can systematically deprioritise low-production, high-need patients, and a no-show-risk signal can proxy for socioeconomic status | Those levers are **explicit, individually visible in the contribution bar, configurable, and off by default**, and are named on the known-limitations page rather than buried inside a composite weight. A practice that turns them on does so knowingly | FR-084 (flag OFF by default); FR-080 contribution bars; FR-047 |
| **R-10** | **HIPAA / PHI exposure.** | v1.0 is 100% synthetic. Production posture: **minimise** (opaque patient IDs to the model, rehydrate client-side) → **contract** (BAA, or self-hosted/VPC model, zero retention) → **audit** (every decision already carries a trace ID). Plus the non-obvious one: **observability is a PHI leak vector**, because traces capture prompts and the request text becomes PHI the moment a patient describes a symptom | §8 *Privacy & Sensitivity*; FR-091 redaction hook; NFR-22 |
| **R-11** | **Staff may ignore the ranking entirely.** | Then the ranking is wrong, and the product should be the first to know. Every override is captured as a labelled counterexample that flows back into the golden set. **Designed in, not patched on** | FR-075; `DecisionRecord.override` in §8 |
| **R-12** | **Nondeterminism makes behaviour unpredictable and untestable.** | Temperature 0, committed fixtures by default, and ranking that is a pure function of the extraction — **so the only variance sits upstream of the decision, and it is measured rather than assumed** | FR-054; FR-097; NFR-13 |
| **R-13** | **The explainer may not need to be an LLM at all — a conceded weakness.** | Templates get roughly 90% of the value, and this stayed a theoretical concern for longer than it should have: the LLM explainer was built, unit-tested, and **never reached from a request** until the live-first change wired it in. | The LLM buys naturalness and avoids combinatorial template explosion as the number of rationale combinations grows. The template is always computed and always available as the fallback, so the LLM can be removed from this stage at any time without loss of function | FR-060 (both renderings returned); NFR-28 |
| **R-14** | **Network or LLM API unavailable at runtime.** | Handled by a layered fallback rather than by avoiding the network. A stage that cannot reach the model drops to committed fixtures; a fixture miss drops to rules. Every MUST requirement is satisfied with networking disabled, and the eval harness reports **both** columns so the degraded path's quality is a known number rather than a hope. The header raises an amber pill when the fallbacks answered, so a degraded run is never mistaken for a live one | NFR-09; FR-005, FR-006, FR-105 |
| **R-15** | **Observability backend unavailable** (container runtime not running). | Opik is optional by construction. The replay panel reads the in-process store, emission is fire-and-forget behind a bounded queue, and failures are counted and swallowed. A non-blocking banner reports the state | NFR-10, NFR-12; FR-087, FR-089 |
| **R-16** | **Relative-date resolution drifts as real time passes**, silently invalidating tests, evaluations and the reference dataset | Injectable reference clock, committed seed data, zero runtime generation. Verified explicitly with the machine clock set months forward of the reference date — a test that is run, not assumed | FR-102, FR-103; NFR-14, NFR-15 |

### Genuinely open questions

| Question | Impact if Unresolved |
| :------- | :------------------- |
| **Can a second annotator label even 10 of the 40 golden requests?** | Would convert R-08 from "disclosed limitation" into "measured inter-rater agreement," which materially strengthens every ranking number in §4. **Medium — the highest-value unresolved item.** If not, R-08 stands as written and the ranking metrics carry a stated single-annotator caveat |
| **Exact weight vectors for the three non-default presets** (Patient-first, Production-first, Continuity-first) | Needed for FR-077. **Low** — derivable once the fitted default exists (FR-098); the presets are deliberate perturbations of the fitted vector, not independent fits |
| **Will v1.0 be handed to another engineer to extend?** | Changes how much goes into README and inline commentary versus walkthrough. **Low-to-medium.** Assume yes and write for a reader — NFR-27 and NFR-28 already price this in |
| **Primary presentation surface — external display or screen-share?** | Affects default font scale and contrast (FR-108, NFR-23). **Low** — Presentation Mode covers both, but verification should be done on whichever is primary |
| **Should the reason line ever name the operatory / room number?** | Currently **no** — room numbers are jargon to a patient and are on the read-aloud lint's banned list (FR-065); the room appears in card metadata instead. **Low.** Revisit if practices ask for room numbers in patient-facing copy |
| **What is the correct hold TTL for real front-desk use?** | [A-07] sets 15 minutes. **Low for v1.0, medium for a multi-seat deployment** — TTL only becomes load-bearing when two operators can contend for the same slot (NFR-08) |
| **How should the system behave if the observability backend is unavailable at start-up?** | **Resolved by design, recorded for completeness:** boot normally, show a non-blocking banner, keep all traces local. NFR-10 guarantees nothing else is affected |

### Closed gaps recorded for completeness

| Item | Status |
| :--- | :----- |
| **A section of the original product brief — "Building Blocks — Open Design Space" — was not captured in the source material available** | **Closed, non-blocking.** That section's own framing — *"no single right architecture… some directions worth considering, none required"* — makes its contents optional by construction, and every architectural decision it might have suggested has been made explicitly and with a recorded rationale in `docs/product-direction.md` and this PRD. If the missing content is recovered later, reconcile it against those decisions rather than re-opening them |
| **Voice / speech input** (the original brief allows "text or speech") | **Closed — permanently cut ✅ DECIDED.** Adds a runtime failure mode for zero decision quality, since constraint extraction operates on text either way. Recorded with its rationale on the known-limitations page |
| **Bump candidates: MUST or STRETCH?** | **Closed** — see the §6 reconciliation note. Empty-tier escalation + emergency-hold unlock are MUST; bump *suggestions* are STRETCH |

---

## 15. Appendix

### Glossary (Domain Glossary)

| Term | Definition |
| :--- | :--------- |
| **Operatory** | The dental treatment room / chair. Scheduling requires *provider* availability **and** *operatory* availability **and** appointment-type duration — a multi-resource constraint problem, not a calendar lookup |
| **Doctor check** | The brief exam a dentist performs during a hygiene appointment. Modelled as a **~10-minute contiguous window that must fall entirely within the last third of the appointment** — an interval-**within**-interval containment check, **not** an overlap check |
| **Prophy** | Routine preventive cleaning (prophylaxis). Adult 60 min, child 40 min |
| **Perio maintenance** | Periodontal maintenance cleaning for patients with prior gum disease, 60 min |
| **NP exam + FMX** | New-patient exam with a full-mouth series of radiographs, 90 min |
| **Limited exam** | Focused emergency exam addressing a specific complaint, 30 min |
| **Crown prep / crown seat** | Two-visit restoration: preparation (90 min) then seating of the finished crown (45 min). **The seat should go to the dentist who did the prep** — continuity here is nearly a hard constraint |
| **RCT** | Root canal therapy, 90 min |
| **Pod** | A standing grouping of providers who work together (a dentist plus assigned hygienists and assistants). Drives the 0.7 continuity tier |
| **DSO** | Dental Service Organisation — a group operating many practice locations under shared management |
| **PMS** | Practice Management System — the system of record for patients, schedules and billing that a dental practice runs on |
| **Turnover buffer** | Cleanup/room-reset time after an appointment before the operatory is bookable again (~10 min) |
| **ScheduleBlock** | A modelled reservation on the calendar that is not an appointment — `lunch`, `huddle`, `restorative_block`, `emergency_hold`, `pedo_after_school`, `admin` — with recurrence, scope, and an optional unlock rule |
| **Prime-time / restorative block** | A high-production time band the practice protects for high-value work. Consuming it with a low-production type is penalised |
| **Emergency hold** | A daily reserved slot (seeded 11:00 and 16:00) that is invisible to routine requests and unlockable only at urgency ≥ urgent |
| **Urgency gate** | The lexicographic tier filter applied **before** weighted scoring. Urgency is a gate rather than a weight so that no preference setting can price pain against convenience on the same axis |
| **Candidate** | A `(start, duration, provider, operatory)` tuple evaluated for feasibility and score |
| **Rejection ledger** | The retained set of candidates that failed a hard constraint, each with its single first-failing cause. Exists because the pipeline **annotates rather than deletes** |
| **Funnel counter** | The four live numbers `enumerated → feasible → in-tier → offered` |
| **Fragmentation delta** | Minutes of newly-created gap shorter than the shortest bookable appointment (~30 min) that a booking would produce |
| **Orphan gap** | A gap too short to book anything into — dead chair time |
| **`Rationale`** | The structured object emitted **by the scorer** containing the top contributing components, human-readable atoms, at most one caveat, and the fact set. The explainer renders it and can add nothing to it |
| **Faithfulness gate** | The deterministic post-check that verifies a generated explanation mentions only entities and components present in the `Rationale`; failure falls back to the template and is logged to the trace |
| **Read-aloud lint** | The automated check that every operator-facing sentence can be spoken verbatim to a patient — one sentence, ≤ 25 words, second person, resolved weekday + date + time, no scores, no jargon, no internal identifiers |
| **Counterfactual / relaxation** | A one-sentence statement of what the patient would gain by bending exactly one *soft* constraint. Hard constraints and patient exclusions are never relaxed |
| **ε-band** | The ~0.03 score band within which candidates are presented as co-equal options rather than a false 1/2/3 |
| **Tiebreak chain** | The deterministic ordering applied to equal scores: earlier date/time → higher continuity → lower fragmentation delta → lower operatory ID |
| **Top-3 diversity constraint** | The rule preventing three near-identical offers, on the principle that three near-identical options are functionally one option |
| **Rank stability** | The percentage of sampled weight vectors under which the same three options remain the top 3. Turns "the weights are arbitrary" from an objection into a measurement |
| **`WeightProfile`** | The named, first-class, configurable weight vector (plus efficiency sub-weights) that defines practice scheduling policy |
| **Golden set** | The ~40 human-labelled requests used to measure extraction accuracy and ranking quality and to fit the weights |
| **Top-3 hit rate** | The fraction of golden requests where the human-preferred slot appears in the offered top 3 — the offline proxy for the confirm-without-investigating rate |
| **`TraceSink`** | The single instrumentation abstraction that fans out to an always-on in-process store and to an optional Opik backend, with a redaction hook and retention policy |
| **Opik** | Comet's LLM observability platform, self-hosted on localhost in a container. **Optional at runtime; never on the request path** |
| **`NOW` injection** | The single clock provider through which all time resolution flows, pinned to the reference dataset's timestamp so relative dates resolve identically on every run and every machine |
| **Session copy** | The in-memory copy of the schedule that bookings mutate, restorable in one click, so the committed seed data is never touched |
| **Agent-justification test** | The design heuristic applied to every agent in the topology: *would replacing this agent with plain code change decision quality?* Extractor: yes, and FR-093 produces the number. Verifier: yes — it catches errors the extractor is structurally blind to. Explainer: arguable, and recorded as such (R-13). Reasoner: **no — it would be strictly worse, which is why it is not an agent** |

### Settled Decisions

Values that were open when this PRD was first drafted and have since been **confirmed**. They are
recorded here separately from assumptions because downstream work may rely on them without
re-checking.

| ID | Decision | Consequence |
| :- | :------- | :---------- |
| **D-01** | **Reference `NOW` = `2026-08-10T09:00:00−07:00` (Monday).** Seed window: history Mon **2026-08-03** → Fri **2026-08-07**; bookable Mon **2026-08-10** → Fri **2026-08-21**; tail Mon **2026-08-24** → Fri **2026-08-28**. Edge-case day/operatory anchors as tabulated in §8 | **Must be fixed before seed authoring begins** — every edge-case anchor, every golden-set label and every date in this PRD is expressed relative to it. Changing it invalidates the golden set |
| **D-02** | **v1.0 delivery date = 2026-08-10 (Mon)**, stakeholder demo build | Sets the §6 triage boundary. MUST is not negotiable; STRETCH is the release valve |
| **D-03** | *"Next Thursday"* from the reference date is **legitimately ambiguous** between Thu **2026-08-13** and Thu **2026-08-20**, and this is treated as a **feature case, not a defect** | Both Thursdays are seeded with different shapes of contention so the two resolutions produce different top-3 sets, which makes the decision-relevance test (FR-011) fire on a real linguistic ambiguity rather than a contrived one. Seeded as edge case 11; widens FR-014 to cover relative-date fan-out |

### Assumptions Register

Every assumption introduced by this PRD that is not settled by the original product brief or by
`docs/product-direction.md`. Each is cheap to change; none is load-bearing for the architecture.

| ID | Assumption | Source | Risk if wrong |
| :- | :--------- | :----- | :------------ |
| **A-01** | *(Closed — superseded by [D-02].)* The delivery date is confirmed as 2026-08-10 | — | None |
| **A-02** | Patient is a beneficiary, never a user in v1.0 | `product-direction.md` §1 (already flagged there) | Low — but it is a **product scope boundary, not an oversight**: patient self-scheduling is a different product with different liability (§6) |
| **A-03** | *(Withdrawn.)* Originally a demonstration-timing allowance; not a product assumption | — | None |
| **A-04** | *(Withdrawn.)* The original day-based effort budget was calibrated to a single developer and does not apply. Scope is fixed by §6; sequencing is in §13 | — | None |
| **A-05** | Manual-effort baseline: **~25 scheduling requests per office per business day at ~60 s investigation each → ~104 h/office/year** | **New (this PRD)** — required to make §3 Layer B arithmetic explicit rather than implicit | **Medium.** Every figure derived from it in §3 is labelled as modelled, never as measured. Replacing it with a practice's real call volume is a one-line change to the arithmetic |
| **A-06** | Clarifying-question confidence threshold **θ = 0.6** | **New** | Low — tunable; the decision-relevance test (FR-011), not the threshold, is the real gate |
| **A-07** | Soft-hold TTL **15 minutes**, configurable | **New** — the product direction specifies a TTL without a value | Low for single-seat v1.0; see the open question in §14 for multi-seat |
| **A-08** | Turnover buffer **10 min**; the appointment must end by close, the buffer may extend past close | **New** — product direction says "~10 min" | Low |
| **A-09** | Search horizon **14 days** from `NOW` → through Mon 2026-08-24 | **New** | Low — widening it only adds lower-ranked candidates |
| **A-10** | Time-fit taper 60 → 120 min is **linear 0.6 → 0.0**; sooner-is-better term inside the window is `−min(0.10, 0.01 × days_out)` | **New** — product direction specifies 1.0 / 0.85 / 0.6 / 0-beyond-2h and leaves 60–120 unstated | Low — refitted by FR-098 in any case |
| **A-11** | Continuity type-dependence is implemented as a per-type **multiplier on the continuity weight with renormalisation** (crown seat 2.0, prep/RCT 1.5, prophy/perio 1.0, limited exam 0.5) | **New** — the product direction states the *intent* ("nearly a hard constraint" vs. "nice-to-have") without a mechanism | **Medium** — this mechanism is visible in the ranking behaviour and must be explicable; the alternative (promoting high-criticality continuity to a Layer-0 hard constraint) is flagged for the architect in §15 |
| **A-12** | Efficiency sub-weights **0.40 / 0.25 / 0.20 / 0.15** (fragmentation / idle / check-load / operatory balance) | **New** — the product direction names the four sub-terms without weights | Low — tunable |
| **A-13** | ε-band **0.03**; diversity suppression window **60 min** same provider + same day | **New** (ε is "≈0.03" in the product direction) | Low |
| **A-14** | Counterfactual surfaces only when the score gain **≥ 0.08** | **New** | Low — a threshold that is too low produces noise, too high produces silence; tunable against the golden set |
| **A-15** | Rank stability samples **N = 200** seeded weight vectors | **New** | Low — the seed matters more than N, because the number must be reproducible run to run |
| **A-16** | UI: Tailwind + shadcn/Radix, flat surface, single light theme + Presentation Mode, desktop-only 1280–1920, 2D only, no incumbent-product imitation | **New** — no design input exists | Low — **flagged for the prototype phase to confirm** |
| **A-16b** | Operatory equipment layout (OP-5 surgical, OP-6 CEREC/pano) and provider names other than **Sarah** and **Dr. Patel** are illustrative | **New** | Low |
| **A-17** | *(Closed — superseded by [D-01].)* The reference `NOW` and seed window are confirmed | — | None |
| **A-18** | Single timezone **America/Los_Angeles**; no DST transition inside the seed window. **The assumption is confined behind a named conversion boundary** (NFR-32) rather than diffused through the code *(amended)* | **New** | Low **for v1.0** — verified: no DST boundary falls between 2026-08-03 and 2026-08-28. **Medium-to-high beyond it**, and it fails in two distinct ways rather than one: (a) a multi-practice group spans timezones, so any cross-location comparison needs an absolute instant; (b) DST lands inside a 14-day horizon **twice a year in every timezone**, and a spring-forward day contains a wall-clock hour that does not exist while a fall-back day contains one that happens twice. A scheduler that stores naive local times is wrong on those two days every year. Confining the assumption is what keeps the fix local |
| **A-19** | Business hours **Mon–Thu 08:00–17:00, Fri 08:00–14:00**; lunch 12:00–13:00; huddle 07:50–08:00 | **New** | Low — but it must be fixed before seeding, since occupancy targets are expressed as a fraction of it |
| **A-20** | Candidate start-time granularity **10 minutes** | **New** | Low — drives enumeration count and therefore NFR-06 |
| **A-21** | Users will phrase requests in ways not represented in the golden set; ~20 adversarial phrasings are pre-tested and carried as class tags | `product-direction.md` §7 | Low — the trace panel makes an extraction failure diagnosable rather than opaque (§10) |
| **A-22** | The no-show hook ships behind a flag that is **OFF by default** | `product-direction.md` §10 ✅ DECIDED | Low — see R-09 |
| **A-23** | The golden set is labelled by a **single annotator** | `product-direction.md` §10 — **disclosed, not hidden** (R-08) | **Medium** — disclosure plus the open question in §14 is the mitigation; a second annotator would remove it |

### References

| Document | Path / Note |
| :------- | :---------- |
| Original product brief | Source material; retained outside the repository. Cited throughout as "the original product brief" |
| Approved product direction | `docs/product-direction.md` — **settled; do not re-litigate anything marked ✅ DECIDED** |
| Reference scenarios and demo script | Derived from `docs/product-direction.md` §7; produced as part of the documentation package (§13) |
| Design rationale and risk responses | `docs/product-direction.md` §10 → §14 of this document |
| Locked technology decisions | Recorded in project notes; summarised in §13 *Constraints* |

### Downstream Handoff Notes (Architect)

Passed forward from the pipeline definition; **this PRD does not produce diagrams.**

| Field | Value |
| :---- | :---- |
| `pipelineId` | `greenfield` |
| `preArchitecture` diagrams | `null` — none required before architecture |
| `postArchitecture` diagrams | **`required`** |
| `flowDiagrams` | **`required`** |
| Upstream | Product direction (`docs/product-direction.md`, approved) → **PRD (this document)** |
| Downstream | **architect** |

**What the architect must resolve** (called out so it is not silently absorbed):

1. **The doctor-check containment algorithm and its data structure.** FR-023 specifies the
   semantics and the failing tests; the free-interval representation that makes containment cheap
   across 9 providers × 14 days is an architecture decision.
2. **The annotate-never-delete pipeline shape (SD-1).** This constrains the reasoner's internal data
   flow more than any other requirement. It must be designed in, not filtered in.
3. **`Rationale` emission from the scorer (SD-2)** — the scorer/explainer interface is the seam that
   makes explanations structurally faithful. Get the object shape right once.
4. **Clock provider and seed-loading design (SD-3)** — one provider, injected; loader validation that
   quarantines rather than crashes (edge case 9) while failing loudly on schema violations.
5. **`Protocol` seam for all four agents with two implementations each** (NFR-28) — an architecture
   obligation, not a coding-style preference: it is what makes FR-093's LLM-vs-rules comparison
   possible at all.
6. **The `TraceSink` fan-out, its bounded queue, and the redaction hook** (FR-085, FR-089, FR-091).
7. **The continuity-multiplier mechanism [A-11]** — confirm the multiplier-with-renormalisation
   approach, or promote high-criticality continuity to a Layer-0 hard constraint. Either is
   defensible; the choice must be made once and recorded with its rationale.
8. **Whether the eval harness runs in-process or as a separate entry point**, given it must also
   emit to Opik (FR-090) without being blocked by it.
9. **Sequencing constraint, not a design choice:** the reference `NOW` and seed window are settled
   ([D-01]) and **the reference dataset must be authored and frozen before the golden set is
   labelled** — the labels reference specific seeded slots (§13 *Constraints*).
10. **Hypothesis fan-out cost** — FR-014 now covers relative-date ambiguity as well as type
    ambiguity, so the decision-relevance test may run the deterministic pipeline twice per request.
    Confirm this fits inside NFR-01 (< 2 s p95 on the degraded path) or design the shared-work optimisation.

---

**PRD Complete and Approved (2026-08-08) — handed off to architecture; prototype follows.**

*All three sign-off roles are Approved (§1), with the single-approver deviation recorded there.
Downstream artifact: `docs/architecture.md`.*
