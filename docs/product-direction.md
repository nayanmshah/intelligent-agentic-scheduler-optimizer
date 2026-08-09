# Product Direction — Intelligent Agentic Scheduling Optimizer

> Agreed product direction, approved 2026-08-08. This document records **what we decided and why**.
> Items marked ✅ DECIDED are settled — treat them as input to design, not as open proposals.
> Downstream: `refined-prd.md` → architecture → development plan.

---

## 1. Product thesis

**The job-to-be-done is not "book an appointment" — it's "collapse the investigation."**

Booking is trivial; every practice-management system does it. What's expensive is the 45–90 seconds
of dead air while a front-desk person scans six operatory columns across five days with a patient
waiting on the phone.

Two clocks conflict today:

| Clock | Optimizes for | Consequence |
| ----- | ------------- | ----------- |
| **Patient-on-phone latency** (seconds) | Fastest possible answer | Favors "first thing that's open" |
| **Schedule quality** (dollars) | Practice production | "First open slot" is exactly the choice that fragments the day and burns a prime restorative block on a 30-minute prophy |

> **The product's job is to make the fast answer and the good answer the same answer.**

This is a **multi-resource constraint problem**, not a calendar lookup. A bookable slot requires a
credentialed *provider*, an equipped *operatory*, and the correct *duration* for the appointment
type — simultaneously. For hygiene appointments it additionally requires a dentist free for a short
exam *inside* the appointment window.

### Success metrics

| Rank | Metric | Target |
| ---- | ------ | ------ |
| 1 | **Confirm-without-investigating rate** — booked slot was in the offered top 3, no calendar manually opened | ≥ 85% |
| 2 | **Time-to-offer** — request → three options | < 2s offline, < 5s with live LLM |
| 3 | **Schedule-quality delta** — production per chair-hour and unusable-gap minutes created, vs. a naive first-available baseline | positive, measured |
| 4 | **Consistency** — same request, same answer, every time | byte-identical |

Metric 2 carries a hard product meaning: beyond roughly 5 seconds the user opens the calendar
anyway, and the entire value proposition is lost.

### Failure modes, ranked by damage

1. **Confidently wrong extraction** — "next Thursday" resolved to the wrong week; "after 3" read as
   03:00. Silent, plausible, and it books a patient into a time they cannot make. Worse than
   returning nothing.
2. **Plausible-but-unfaithful explanation** — the reason text says "your usual hygienist" when the
   slot actually won on gap-fill. An explanation that does not reflect the ranking is worse than no
   explanation.
3. **Schedule vandalism** — technically valid, economically poor. Opens a 25-minute orphan gap or
   consumes a protected production block.
4. **Over-refusal** — "urgent, nothing open" returning an empty list. Useless. The system must
   always return something, including clearly-labeled overflow options.
5. **Latency.**

### Users

| Role | Relationship | Surface |
| ---- | ------------ | ------- |
| **Front-desk coordinator** | The operator | One keyboard-first screen: three cards, an editable interpretation strip, one primary action per card (Hold) |
| **Office manager / multi-practice ops lead** | The buyer | A **separate** panel: scoring-weight configuration and the evaluation scorecard |
| **Patient** | Beneficiary, not a user in v1 *(assumption)* | None. Patient self-scheduling is a different product with different liability |

Two consequences that are real, testable requirements:

- **The reason line must be readable aloud, verbatim, to a patient on the phone.** That single
  constraint decides the copy style — *"Thursday the 13th at 3:40 with Sarah, right after your PT
  day"*, not *"Score 0.87 (time fit 0.90, continuity 1.00)."*
- **Weights live with the office manager, never the front desk.** Per-call fiddling would destroy
  the consistency the product exists to provide.

Every operator override is the most valuable data the product generates — a labeled counterexample,
not a failure.

---

## 2. Agent topology — ✅ DECIDED

**Four roles. Three run on a model by default; the one that decides never does.** The critic sits
over the extraction, not over the ranking.

| # | Role | Implementation | Responsibility |
| - | ---- | -------------- | -------------- |
| 1 | **Intent Extractor** | LLM + deterministic fallback + cached fixtures | Request text + patient context → typed `RequestConstraints` (date range, time window, urgency, provider preference, appointment type, exclusions). **Every field carries a confidence and a verbatim source span from the request.** |
| 2 | **Constraint Verifier / Clarifier** | LLM by default, deterministic rules as the floor and the fallback | Does *not* see the schedule. Validates the extraction against the world: is the date in the past? does the provider exist and work at this location? is the type compatible with the stated symptom? is any low-confidence field one that would *change the answer*? Emits `proceed` / `proceed-with-flags` / `ask-one-question`. |
| 3 | **Schedule Reasoner** | **Deterministic, zero LLM** | Enumerate candidates → apply hard constraints, retaining rejections with reasons → score across four axes plus doctor-check and prime-time → apply urgency gate → rank → generate counterfactuals. |
| 4 | **Explainer** | LLM phrasing over scorer-emitted facts, template fallback, faithfulness gate | Sees only the score components the reasoner produced. Structurally cannot invent a reason it was not given. |

**Orchestrator:** a plain, readable state machine — explicit stages, per-stage timeout and fallback,
a `TraceSink` emit at every hop, under ~150 lines. **Deliberately not an agent framework.** A
legible hand-rolled orchestrator is easier to reason about, debug, and modify than a framework DAG,
and it keeps the control flow visible in the code rather than in library internals.

> **Design principle:** *LLMs at the edges, determinism in the core. Language in, language out —
> arithmetic in between.*

### Why the reasoner is not an LLM

For a well-defined constraint search, letting a language model drive enumeration is strictly worse
than exhausting it: it will miss candidates, and the question *"did it miss anything?"* becomes
unanswerable. That is disqualifying for a product whose entire promise is that the user does not
have to investigate.

The test applied to every LLM call — *would replacing this with deterministic code change decision
quality?*

| Component | Verdict |
| --------- | ------- |
| **Extractor** | **Yes** — and it is measured. The rules fallback scores materially lower than the LLM on the golden set; the eval reports exactly which phrasings it misses. |
| **Verifier** | **Yes, and it is now measured.** The rules catch what can be enumerated — a past date, a provider who does not exist, a credential mismatch. They cannot catch a *semantic* mismatch, because there is no list to check it against. Live, the model reads *"my crown fell off, can I get a cleaning?"* and returns "you mentioned a fallen-off crown, so you likely need a crown fitting or exam, not a cleaning." No lookup finds that. The rules still run underneath as the floor, so the model can add to the picture and never subtract from it. |
| **Explainer** | **Arguable.** Templates deliver roughly 90% of the value; the LLM buys naturalness and avoids combinatorial template explosion. The template always runs as fallback. |
| **Reasoner** | **No** — it would be strictly worse. That is why it is not one. |

**Implementation seam:** every agent is a `Protocol` with two implementations — LLM and
deterministic — satisfying NFR-28 in full. The product **ships live**: extraction, verification and
explanation all call a model by default, because a capability nobody sees working is a capability
nobody believes.

The deterministic implementations are the **fallback**, not the default. Degradation is automatic
and layered: no key, no network, a timeout or a refusal drops a stage to committed fixtures, and a
fixture miss drops it to rules. Silent to the operator, loud in the trace (NFR-16), and the header
always names which path answered. So the offline guarantee survives without costing the demo its
point.

---

## 3. Scoring model — three layers, not one weighted sum

The layering is what makes the model defensible. Hard feasibility and urgency sit **outside** the
weighted sum, so no weight can ever trade away a constraint that should be absolute.

### Layer 0 — Feasibility (hard, boolean)

A candidate is a `(start, duration, provider, operatory)` tuple. It survives only if:

- operatory free for the full duration **plus turnover/cleanup buffer** (~10 min)
- provider free for the full duration
- **provider credentialed** for the appointment type (a hygienist cannot do a crown prep; a crown
  seat should go to the dentist who did the prep)
- **operatory equipped** for the type (surgical suite for extractions; the room with the pano/CEREC)
- inside business hours, outside lunch and huddle blocks, and it fits before close
- **doctor-check overlay** — for hygiene, some dentist has ≥10 contiguous free minutes *inside* the
  appointment, in its **last third**, matching how the exam actually happens in practice. This is an
  interval-**within**-interval containment check, not an interval-overlap check.
- patient-stated **exclusions are hard** ("not Tuesdays, I have PT"); patient-stated **preferences
  are soft** ("prefer Sarah")

**Everything that fails is retained together with the reason it failed → the rejection ledger.**
The pipeline annotates; it never deletes.

### Layer 1 — Urgency gate (lexicographic, NOT a weight)

Tiers: `emergency ≤24h`, `urgent ≤72h`, `routine ≤ requested window`, `flexible`. Ranking happens
strictly within the highest non-empty tier.

> **Urgency is a gate, not a weight** — otherwise the model is pricing pain against convenience on
> the same axis, which no weighting can make correct.

If the tier is empty, the system does **not** fail. It escalates to clearly-labeled overflow:
unlock the daily **emergency-hold blocks** (real practices reserve these; seeded at 11:00 and 16:00,
unlockable only at urgency ≥ urgent), then surface bump candidates.

### Layer 2 — Weighted preference within the tier

Each axis normalized to [0,1]; weights sum to 1.0 so the score reads as a percentage. Defaults below
are the **general-practice profile** — a profile, not a universal truth.

| Axis | Weight | Design |
| ---- | ------ | ------ |
| **Time fit** | 0.35 | Piecewise, not binary: 1.0 inside the stated window; ~0.85 within 30 min of the boundary; ~0.6 within 60 min; 0 beyond 2h. Plus a mild sooner-is-better term inside the window — a patient who says "next Thursday" usually means the soonest acceptable Thursday slot. |
| **Provider continuity** | 0.25 | 1.0 assigned/last-seen provider for this care type; 0.7 same pod or team; 0.4 any previously-seen provider; 0.15 new. **Type-dependent, not global** — a crown *seat* with the wrong dentist is close to a hard constraint, while continuity on a routine prophy is a genuine nice-to-have. |
| **Schedule efficiency** | 0.25 | Composite: **fragmentation delta** (minutes of newly-created gap shorter than the shortest bookable appointment, ~30 min), provider idle-time delta for the day, doctor-check load (feasible-but-tight is not the same as good), and operatory balance. |
| **Prime-time / block protection** | 0.15 | Negative-going: penalizes consuming a designated high-production block with a low-production appointment type. Also expresses after-school demand (3–5pm favored for school-age patients). |

> **The schedule has a shape the practice wants. The optimizer defends that shape.**

### How the weights are justified

1. **They are a profile, not a truth.** Three named presets ship: *Patient-first*,
   *Production-first*, *Continuity-first*. Different practices genuinely want different things, and
   a multi-practice group needs to set policy centrally.
2. ✅ **DECIDED — they are fit, not guessed.** Grid-search / coordinate-ascent over ~40
   human-labeled preferred slots, maximizing top-1 and top-3 agreement. A few hundred weight vectors
   over 40 examples runs in seconds. The published **sensitivity curve** shows how flat the response
   is around the fitted value — a flat region means the model is not weight-fragile.
   **Disclosed limitation:** a single labeler, so the labels encode one person's judgment of "good"
   rather than a practice's. The remedy is 2–3 schedulers labeling independently and measuring
   inter-rater agreement; the data model reserves a `labeler` field for exactly this.
3. **Their influence is bounded and measured.** Each weight is swept 0→1 and the resulting change in
   top-3 membership is reported.

### The weight tuner — ✅ DECIDED: a product feature

Shipped as **practice-policy configuration for the office manager**, on a panel separate from the
front-desk screen, with the three named presets. Two requirements make the model *legible* rather
than arbitrary-looking:

- **Per-axis stacked contribution bar on every card** — the score is always decomposed, never shown
  as a naked number.
- **Rank-stability indicator** — *"these three remain in the top 3 across 78% of sampled weight
  vectors."* This is the key result: it establishes that **the recommendation is robust to the
  weights**, which is a much stronger claim than any particular weight being correct.

### Ties and near-ties

- **Deterministic tiebreak chain** — earlier date → better continuity → lower fragmentation delta →
  lower operatory ID. Identical input yields byte-identical output, every run.
- **ε-band (≈0.03) → present as co-equal**, with differentiating reasons, rather than manufacturing
  a false 1/2/3 ordering.
- **Top-3 diversity constraint** — never return 3:00, 3:10 and 3:20 in the same operatory with the
  same provider. **Three near-identical options are one option.** Enforce spread across ≥2 days or
  ≥2 providers wherever feasible.

---

## 4. Explainability — hybrid with a faithfulness gate

| Approach | Verdict |
| -------- | ------- |
| Pure template from score components | Always faithful, zero latency, works offline — but brittle, and robotic by the third card |
| Pure LLM narrative | Natural prose, **unverifiable faithfulness**. It will eventually produce a well-written reason that is not the actual reason. Also places network latency on the most visible surface |
| **Hybrid: deterministic facts → LLM phrasing → verification gate** | ✅ **Selected** |

1. The **scorer emits a structured `Rationale`** — the top 2–3 contributing components with values
   and human-readable atoms, plus at most one caveat atom. For example:
   `{continuity: "same hygienist as your last 3 visits (Sarah R.)", time_fit: "40 min after your
   requested 3pm", efficiency: "fills a gap between two existing appointments", caveat: "different
   room than usual"}`.
2. The **Explainer's only job** is rendering those atoms into one warm sentence, ≤25 words,
   readable aloud. Prompt constraint: use only the supplied facts, add nothing.
3. **Faithfulness gate** — a deterministic post-check verifies that every entity mentioned
   (provider, day, time, operatory, duration) exists in the fact set, and that no non-contributing
   fact was introduced. On failure it falls back to the template and **logs the gate firing to the
   trace**, so gate activations are observable rather than silent.
4. **The template is always computed regardless**, so offline operation is not a degraded surface —
   same content, plainer prose.

**Supporting layers:** why-not text on rejected slots (templated; each rejection has a single
cause); the per-card contribution bar; and **extraction provenance** — the verbatim span that
produced each constraint (`"after 3" → window 15:00–close`), which lets the operator trust the
interpretation without re-reading the request.

> **The explanation is generated *from* the decision, never in parallel with it — so it cannot
> disagree with it.**

---

## 5. Data model

**Entities:** Location · Provider · Operatory · AppointmentType · Patient · Appointment ·
ScheduleBlock · Hold · RequestLog/Decision · WeightProfile · GoldenLabel.

✅ **DECIDED — model multi-location, seed one.** `Location` is a first-class entity, and providers
carry **location assignment by day**, since providers rotate across offices in a multi-practice
group. Only one location is seeded. The cost is near zero and it keeps the multi-practice path open
without complicating the working demo.

**`ScheduleBlock`** is scoped to a provider, an operatory, or globally, with recurrence and a kind
of `{lunch, huddle, restorative_block, emergency_hold, pedo_after_school, admin}` plus an unlock
rule. This makes prime-time and block scheduling a **modeled concept** rather than a constant buried
in the scorer.

**`RequestLog/Decision`** does three jobs at once — replay substrate, evaluation substrate, and
override capture. It stores the raw text, the extracted constraints with confidences and spans, the
full candidate set with scores and rejection reasons, the offered top 3, what was accepted, and the
trace ID.

**`AppointmentType`** carries `requires_doctor_check`, `check_duration` (10 min), `check_placement`
(last third), production value, `prime_time_protected`, and default urgency. Roughly 12 types:
prophy adult 60 / child 40, perio maintenance 60, new-patient exam + FMX 90, limited exam
(emergency) 30, filling 1-surface 40 / 2-surface 60, crown prep 90, crown seat 45, extraction 45,
root canal 90, denture adjust 20.

### Sizing

1 location · 6 operatories · 3 dentists + 4 hygienists + 2 assistants · ~120 patients · a seed
window spanning **Mon 2026-08-03 → Fri 2026-08-28** at **70–80% occupancy** → roughly 250–400
existing appointments.

Occupancy is a deliberate design parameter. **Too empty and every request has a trivially easy
answer** — no candidate is ever rejected, every slot scores identically, and the ranking has nothing
to express. **Too full and everything is a rejection.** The target range makes slots genuinely
compete. Include a couple of near-full days and one sparse day.

**Generate with a seeded script, then hand-author the scenario appointments on top. Commit the
generated JSON — never regenerate at startup.** Regenerated data changes between runs, which means
the behavior observed in testing is not the behavior that will be observed later.

### ⚠️ The clock is injected and frozen

`NOW` is an injected dependency, fixed to **Monday 2026-08-10 09:00 (−07:00)** and surfaced in the
UI. Relative language — *"next Thursday," "first thing tomorrow"* — must resolve to dates that
actually exist in the seeded window. Reading the system clock instead would mean the same request
resolves to a different date each day and drifts out of the seeded scenarios entirely.

A useful consequence of this anchor: from a Monday, **"next Thursday" is genuinely ambiguous**
between **2026-08-13** and **2026-08-20**. That is a real-world extraction ambiguity, so both
Thursdays are seeded with meaningful contention and the case is represented in the golden set.

### Deliberately seeded edge cases

Each exists so a specific capability can be demonstrated on demand rather than waited for.

1. **Doctor-check starvation** — an afternoon where three hygiene operatories are open but every
   dentist is in back-to-back crowns. Operatory-available yet exam-infeasible; the clearest
   demonstration of the multi-resource constraint.
2. **Provider PTO** covering the patient's assigned hygienist for the requested week → forces the
   continuity-versus-timing tradeoff and sets up a counterfactual.
3. **The orphan gap** — a 50-minute hole between two appointments that exactly fits a 40-minute
   filling plus turnover. The efficiency axis's hero case.
4. **The fragmenting trap** — a 90-minute open stretch where booking 30 minutes in the middle
   creates two dead 30-minute orphans. The scorer pushes the booking to the edge, and the
   explanation says so.
5. **Urgent with nothing open** — exercises the empty-tier path, emergency-hold unlock, and bump
   candidates.
6. **Ambiguous appointment type** — "my tooth's been bothering me": a 30-minute limited exam versus
   a 90-minute crown. One seeded case where the hypotheses *diverge* (so it asks) and one where they
   *agree* (so it does not).
7. **Credential mismatch** — a patient requests an oral surgeon for a cleaning → graceful redirect,
   not an empty result.
8. **Equipment constraint** — an extraction that only fits the surgical-capable operatory, which is
   also the busiest.
9. **One deliberately malformed record** — an appointment overlapping a lunch block, caught by
   loader validation. Real practice-management exports contain dirty data.
10. **Chronic no-show patient** requesting prime time → policy hook, **flag OFF by default** (§7).

---

## 6. Booking behavior — ✅ DECIDED

**Session copy with reset.** Confirming a slot mutates an **in-memory session copy** of the
schedule, with a one-click **"reset state"** control. Bookings can be exercised repeatedly without
corrupting the seeded scenarios. The offered top 3 carry a **soft hold with a TTL**, which also
handles two operators racing for the same slot.

---

## 7. Scope

### MUST — the core, rock-solid

- Data model + seeded, **committed** dataset with the ten edge cases; frozen injected clock
- Extractor (LLM + rule fallback + fixtures) with per-field confidence and source spans
- Deterministic reasoner: enumeration, hard constraints including the doctor-check overlay,
  **rejection ledger**, four scoring axes + prime-time, urgency gate, tiebreak chain, top-3 diversity
- Templated explanations (faithful by construction) + why-not text
- FastAPI endpoints + React three-card UI + editable interpretation strip + funnel counter
- In-process trace store + replay panel
- Golden dataset (~40) + evaluation harness producing the scorecard
- One-command boot; fully functional with no network

### SHOULD

- LLM explainer **with the faithfulness gate** (template remains the fallback)
- Weight tuner with contribution bars + **rank-stability indicator**
- Counterfactual / constraint-relaxation panel
- **Weight fitting to golden labels + sensitivity curve**
- Constraint-verifier agent + single clarifying question gated on decision-relevance
- Soft-hold + confirm booking with session reset
- Opik wired behind `TraceSink`, optional at runtime
- Manual-mode side-by-side operatory grid for effort comparison

### STRETCH — cut without regret

Multi-hypothesis fan-out beyond type ambiguity · bump-candidate suggestions · production-dollar
figures · waitlist/ASAP gap-fill · cross-location routing (the model stays either way) ·
no-show-risk policy hook.

### Explicit non-goals

| Not building | Why |
| ------------ | --- |
| A real database | SQLite at most; JSON fixtures are simpler to inspect, diff, and version |
| Auth / RBAC | Single-operator scope; adds no decision quality |
| An agent framework | The orchestrator is ~150 legible lines; a framework would hide the control flow |
| Vector store / RAG | There is nothing to retrieve — the schedule is structured data |
| ILP / OR-tools | One request against a fixed schedule, not a global re-optimization. Exhaustive enumeration over hundreds of candidates is exact, sub-millisecond, and fully explainable |
| Global schedule re-optimization | Moving already-booked patients is a consent problem before it is a math problem |
| Patient self-scheduling | Different product, different liability surface |
| Voice input | ✅ **Cut permanently.** Transcription adds a failure mode and zero decision quality; typed text exercises the same extraction path |
| Streaming token UI, containerized app deploy, k8s, multi-tenancy | Infrastructure without product value at this stage |

---

## 8. Risk register

| ID | Risk | Mitigation | Evidence |
| -- | ---- | ---------- | -------- |
| **R-01** | *"Why agents rather than a rules engine?"* | For the scheduling half it **is** a rules engine, deliberately. The agentic part is confined to language: turning *"whatever works next week, I have PT on Tuesdays"* into typed constraints, and turning score components into a readable sentence. In the core, an LLM would add latency and nondeterminism without adding decision quality | Rules-vs-LLM accuracy pair in the eval |
| **R-02** | Unvalidated quality claims | ~40 labeled requests; per-field extraction accuracy; top-3 hit rate; reproducibility checked in CI; the failure list published alongside the successes | Evaluation scorecard |
| **R-03** | LLM extraction error | Three layers: the verifier catches structurally-wrong extractions; low confidence changes behavior (editable chips + source spans); **the LLM never touches the ranking**, so a language error can produce the wrong *search* but never an infeasible *booking*. Explanations are faithfulness-gated | Trace panel; gate firing |
| **R-04** | **Residual risk that cannot be engineered away** — a confidently-wrong date the operator does not notice | Mitigated at the UI level: the read-aloud sentence and the confirmation both echo the resolved date ("Thursday the 13th at 3:40"), so the patient catches it. Human confirmation is load-bearing by design — this is *confirm, not investigate*, not autonomous booking | Confirmation echo |
| **R-05** | Scale | Enumeration is O(days × operatories × granularity) — a few hundred candidates per request, sub-millisecond. **The LLM call is the latency floor, not the search.** Production shape is a precomputed availability index per provider/operatory-day with incremental invalidation. Per-request against a fixed schedule → parallel across offices. **What does not scale for free is *policy***, which is why `WeightProfile` is an entity rather than a set of constants | Latency budget; `WeightProfile` |
| **R-06** | Single-labeler bias in the golden dataset | Disclosed, not hidden. The remedy is 2–3 schedulers labeling independently and measuring inter-rater agreement; `GoldenLabel.labeler` exists for it. **If real schedulers disagree substantially, that disagreement is itself the business case for the product** | `GoldenLabel.labeler` |
| **R-07** | **Bias / fairness** | A scorer that optimizes production can systematically deprioritize low-production, high-need patients, and a no-show-risk feature can proxy for socioeconomic status. Those levers are **explicit, configurable, and off by default** rather than buried inside a weight | No-show flag OFF; contribution bars |
| **R-08** | PHI / HIPAA | All data synthetic. Production posture: **minimize** (send opaque patient IDs, rehydrate names client-side) → **contract** (BAA, or a VPC/self-hosted model with zero retention) → **audit** (every decision already logs with a trace ID). Non-obvious trap: **observability is a PHI leak vector** — traces capture prompts, which is why `TraceSink` has a redaction hook and a retention policy rather than SDK calls scattered through the code. The request text itself becomes PHI the moment a patient describes a symptom | `TraceSink` redaction hook |
| **R-09** | *"Is this just a fancy first-available?"* | Head-to-head against a naive first-available baseline over the golden set, reporting human agreement and fragmentation minutes created. Where the delta is small for a request class, report that too | Baseline comparison |
| **R-10** | Operators ignore the ranking | Then the ranking is wrong and we need to know. Every override is captured as a labeled counterexample flowing back into the golden set — designed in, not patched on | Override capture |
| **R-11** | Nondeterminism | Temperature 0, fixtures by default, and the ranking is deterministic given the extraction — so the only variance sits upstream of the decision, and it is measured | Reproducibility test |
| **R-12** | External dependency failure | The system runs fully offline by default; the network is opt-in. Opik is optional and never on the critical path — the replay panel reads the in-process store | Offline test suite |

---

## 9. Load-bearing structural decisions

Three choices that are inexpensive now and expensive to retrofit. They must survive into the
architecture.

| ID | Decision | Why it must be structural |
| -- | -------- | ------------------------- |
| **SD-1** | **The pipeline annotates rather than deletes** | The rejection ledger then exists for free. Retrofitting it means re-plumbing every filter. Enforced by the conservation invariant `feasible + Σrejected == enumerated` |
| **SD-2** | **The `Rationale` object is emitted by the scorer** | Explanations are then generated from the decision and cannot disagree with it. Any other arrangement makes faithfulness a hope rather than a property |
| **SD-3** | **`NOW` is injected; seed data is committed, not generated** | Behavior is reproducible across runs and across days. Retrofitting determinism into a system that reads the wall clock touches everything |
