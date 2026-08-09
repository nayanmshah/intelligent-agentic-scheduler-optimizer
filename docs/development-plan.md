# Development Plan — Intelligent Agentic Scheduling Optimizer

> **Upstream:** `docs/product-direction.md` → `docs/refined-prd.md` (approved) →
> `docs/architecture.md`. This document sequences the build. It adds no requirements and makes no
> new decisions — where it appears to, that is a bug and the PRD or architecture wins.
>
> **How to read it.** Ten stages, ordered by dependency rather than by calendar. Each carries a
> goal, its deliverables, and an **exit criterion that is a test, not an opinion**. A stage is done
> when its exit criterion passes, and not before — because every downstream stage assumes it.

---

## 1. The spine

PRD §13 fixes the delivery sequencing, and it is not arbitrary. Each item exists because the next
one cannot be built or verified without it:

```
reference dataset → deterministic reasoner → extraction with fallback → UI
    → golden set + harness → tuner / counterfactual / gate → tracing → docs
```

Two ordering constraints are hard, and violating either costs rework rather than time:

| Constraint | Why |
| :--------- | :-- |
| **The dataset freezes before the golden set is labelled** | Labels reference specific seeded slots. Changing seed data after labelling silently invalidates every ranking number. Enforced mechanically by `SEED_DIGEST` (NFR-29 / ADR-11), not by memory |
| **The deterministic reasoner precedes the extractor** | The reasoner is testable with hand-written `RequestConstraints`. Building extraction first means debugging two unknowns at once — was the search wrong, or was the interpretation? |

---

## 2. Stages

### S1 — Foundation

**Goal:** an empty application that boots, with the three structural guards already in place so
they can never be retrofitted.

- Repo scaffold: `uv` + Python 3.12 pin, FastAPI skeleton, Vite skeleton, `Makefile`
  (`demo` / `dev` / `test` / `eval` / `fit` / `seed`)
- `domain/` — every type from architecture §7: entities, request, candidate, rationale, decision,
  policy. PHI annotations included from the first commit (NFR-31)
- `clock.py` + `FrozenClock`, wired through `AppContainer`
- `data/timezone.py` — the single conversion boundary (NFR-32)
- `tests/structure/` — AST clock guard, naive-datetime guard, import guards

**Exit:** `make demo` serves an empty page; the structural test suite passes and **fails when
deliberately violated** (add a `datetime.now()`, watch it break, remove it).

> The guards go in before the code they guard. A structural test added after the violation exists
> is a cleanup task; added before, it is a wall.

---

### S2 — Reference dataset  ← *first real work item, blocks everything*

**Goal:** a committed, validated, frozen dataset containing all eleven seeded edge cases.

- `scripts/generate_seed.py` — seeded generator, offline, never invoked by boot (FR-103)
- Hand-author ~15 scenario appointments on top for the eleven edge cases (PRD §8)
- `data/loader.py` — two-phase validation: schema violation fails boot loudly, semantic anomaly
  quarantines and reports (edge case 9)
- `data/digest.py` → `SEED_DIGEST`
- `data/repository.py` `ScheduleRepository` Protocol + `memory_repo.py` (NFR-29)

**Exit:** boot twice → identical digests. Edge case 9 quarantines and is named in pre-flight. A
deliberately malformed field fails the boot with file, record, and field named.

**→ FREEZE THE DATASET HERE.** Golden-set labelling (S7) may begin the moment this exits, in
parallel with everything below.

---

### S3 — Deterministic reasoner: enumeration and feasibility

**Goal:** the multi-resource constraint engine — the part that carries the domain credibility.

- `availability.py` — occupancy bitmaps + prefix sums, per-`(resource, day)` versioning (ADR-16);
  doctor-check OR-index
- `enumerate.py` — grid slots → candidates, both counts reported (AR-04)
- `ladder.py` — the fixed-order rule table **as data**, each rule carrying its code, phase, and
  `depends_on`
- `feasibility.py` — two-phase execution
- `CandidateSet` with no delete operation; `conserve()` on the `@stage` decorator

**Exit:** FR-016 … FR-038 pass, including the two the PRD names explicitly —
`test_doctor_check_is_containment_not_overlap` and the ladder-order snapshot. The conservation
invariant holds across every synthetic request. Enumeration + feasibility measured **< 150 ms**
(NFR-06).

---

### S4 — Scoring, selection, rationale, template explanation

**Goal:** a complete deterministic decision — three ranked, explained offers — with no LLM anywhere.

- Four axis scorers, each returning `(value, atom_text, subterms)`
- `ScoreMatrix` — axis values computed once, weights applied as a product (ADR-06)
- `WeightProfile` with `scope`/`scope_ref`, continuity multiplier + renormalisation (ADR-07)
- `rationale.py` — emitted **by the scorer**
- `select.py` — tiebreak chain → ε-band → diversity
- `counterfactual.py`
- `TemplateExplainer` + **read-aloud lint** (FR-065 is MUST — the lint ships here, not later)

**Exit:** FR-039 … FR-058 and FR-059/FR-060/FR-065 pass. The same request run twice produces a
**byte-identical** `DecisionRecord`. Every reason line passes the lint.

> At the end of S4 the product's whole argument is demonstrable from a Python REPL. That is the
> right place to be before any UI exists.

---

### S5 — Agents, orchestrator, fan-out

**Goal:** unstructured text in, with the fallback ladder proven by removing the network.

- `protocols.py` + `registry.py`
- **Rules extractor and rules verifier first** — no network, fully testable
- `orchestrator/machine.py` (≤ 150 lines) + `stages.py` (timeout, fallback, span, invariant)
- `TraceSink` protocol + in-process store (spans must exist from the orchestrator's first line)
- LLM extractor + verifier + `FixtureCache`; per-stage models per ADR-15
- `hypotheses.py` — fan-out with Layer-0 reuse (§9)

**Exit:** FR-001 … FR-015 pass. The full flow runs **with networking disabled**. Forced-timeout
tests per LLM stage return a complete response inside budget. Σ per-stage timeouts ≤ 4.5 s asserted.

---

### S6 — API and UI

**Goal:** the demo surface.

- Routers per architecture §16; OpenAPI → generated TS types
- Operator console, policy panel, trace panel
- The four custom components; keyboard map; presentation mode

**Exit:** FR-029, FR-031, FR-052, FR-053, FR-104, FR-108. All card content legible at 1920×1080 at
125–150% zoom. `1`/`2`/`3` hold without a mouse.

---

### S7 — Golden set and eval harness  ← *parallel from S2*

**Goal:** the numbers. This is what converts every claim into a measurement.

- Label ~40 requests against the **frozen** dataset; every class ≥ 3 entries; `seed_digest`
  recorded per entry
- `run_evaluation()` + CLI and HTTP entry points (ADR-12)
- Per-field accuracy **LLM vs rules** (FR-093) · top-1/top-3 (FR-094) · naive baseline head-to-head
  (FR-095) · latency percentiles · determinism check · **named failures visible by default**
- `make fit` → fitted weights ship as the `General Practice` default (FR-098)

**Exit:** FR-092 … FR-101. Scorecard renders in-product. CI runs the determinism check.

---

### S8 — LLM explainer, gate, tuner  *(all SHOULD — first release valve)*

- `LlmExplainer` (one batched call) + faithfulness gate + silent logged fallback
- Weight tuner: sliders, presets, contribution bars, rank stability (< 500 ms)
- Sensitivity curve

**Exit:** FR-061 … FR-064, FR-066, FR-076 … FR-083, FR-099. Re-rank < 300 ms with zero LLM calls.

---

### S9 — Replay and observability

- Replay panel with byte-equality assertion and field-level diff
- Opik leg: bounded queue, worker thread, redaction, counters

**Exit:** FR-085 … FR-091. **Traces render and replay with the container runtime stopped** (NFR-10).

---

### S10 — Release verification and documentation package

- Three cold-start runs from a clean state, networking disabled, zero unrecovered failures
- Demo script, design-rationale FAQ, known-limitations page
- Architecture diagram (already in `docs/diagrams/`)

**Exit:** PRD §4 *"What does done look like"* — all eight clauses.

> **The known-limitations page has three entries that must not be softened:** live-mode extraction
> is not reproducible (AR-01), the golden set has one annotator (R-08), and the operator/manager
> split is not a security boundary (NFR-19).

---

## 3. Critical path and parallelism

```
S1 ─→ S2 ─→ S3 ─→ S4 ─→ S5 ─→ S6 ─────────────→ S10
             │                    ╰─→ S8 ─→ S9 ─╯
             ╰──────────→ S7 (labelling starts at the S2 freeze)
```

Three things can run alongside the critical path once their input exists:

| Work | Unblocked by | Why it parallelises |
| :--- | :----------- | :------------------ |
| Golden-set labelling | S2 freeze | Needs the dataset, not the code |
| Frontend scaffolding and component shells | S1 | Needs types, not behaviour |
| Documentation package | S4 | The argument is stable once the decision is |

---

## 4. Operator console layout *(the folded prototype)*

The information hierarchy, which is the one thing PRD §12 leaves open. Everything below the fold
is evidence; everything above it is the decision.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Chairside · agentic scheduling   Seat: Front desk   Console ⋯  ⟳   │  persistent (FR-104/105)
├──────────────────────────────────────────────────────────────────────┤
│  Patient ▾   ┌──────────────────────────────────────────────┐        │
│              │ "Can I come in next Thursday after 3?"    ⏎  │        │  FR-001
│              │                              [🎙 Speak] ← fills, never submits │  FR-110
│              └──────────────────────────────────────────────┘        │
├──────────────────────────────────────────────────────────────────────┤
│  [next Thursday → Thu 13 Aug ✎] [after 3 → 15:00–close ✎] [prophy ✎] │  interpretation strip
│   ·high            ·high              ·medium ⚑                       │  FR-002/003/007/067
├──────────────────────────────────────────────────────────────────────┤
│  13,392 considered → 214 bookable → 47 in window → 3 offered         │  funnel (FR-029)
├──────────────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐          │
│  │ Thu 13 Aug     │  │ Thu 13 Aug     │  │ Fri 14 Aug     │          │  THE DECISION
│  │ 3:40 PM · Sarah│  │ 4:20 PM · Nia  │  │ 9:20 AM · Sarah│          │  FR-053
│  │ Prophy · 60 min│  │ Prophy · 60 min│  │ Prophy · 60 min│          │
│  │ ▇▇▇▇▇▆▆▃▃ 87%  │  │ ▇▇▇▆▆▆▃  81%   │  │ ▇▇▇▇▇▇▆▆▃ 84%  │          │  contribution bar
│  │ "Thursday the  │  │ "A bit later   │  │ "Friday morning│          │
│  │  13th at 3:40  │  │  the same day, │  │  with Sarah,   │          │  ONE reason line
│  │  with Sarah,   │  │  with Nia."    │  │  and the day   │          │  ≤25 words, FR-065
│  │  right after…" │  │                │  │  is quieter."  │          │
│  │    [ Hold  1 ] │  │    [ Hold  2 ] │  │    [ Hold  3 ] │          │  one action, FR-052
│  └────────────────┘  └────────────────┘  └────────────────┘          │
│                                                                       │
│  If 11:20 works instead of first thing, you get Dr. Patel.           │  counterfactual (FR-058)
├──────────────────────────────────────────────────────────────────────┤
│  ▸ Considered and rejected (211)                                     │  COLLAPSED (FR-031)
│  ▸ Compare with the calendar grid                                    │  FR-107
└──────────────────────────────────────────────────────────────────────┘
```

Four rules the layout enforces, each traceable to a requirement:

1. **The three cards are the visual centre.** Everything else is smaller, quieter, or collapsed.
2. **The evidence is exactly one click away and never on screen by default.** The ledger is the
   most domain-credible surface in the product and it stays shut until asked for.
3. **No naked number anywhere.** Every percentage sits directly above its decomposition.
4. **No weight control on this screen, at any size** (FR-076). Per-call fiddling destroys the
   consistency the product sells.

---

## 5. If time runs short — the release valve, in cut order

PRD §6 makes triage the mechanism for hitting the date. Cut strictly in this order; **never
reorder to protect a favourite feature**:

| # | Cut | Consequence |
| - | :-- | :---------- |
| 1 | Bump-candidate suggestions (FR-037, STRETCH) | None — FR-036 alone satisfies "never return nothing" |
| 2 | No-show hook (FR-084, STRETCH) | None — it ships flag-off regardless |
| 3 | Fan-out beyond the two ambiguity classes | None — the two seeded classes still demonstrate it |
| 4 | Manual-comparison grid (FR-107, SHOULD) | Loses the time-on-task comparison; the argument survives |
| 5 | Counterfactual panel (UC-08, SHOULD) | Loses a genuinely good moment. Cut with regret |
| 6 | LLM explainer + gate (SHOULD) | Template still renders every line. **Costs the "verify the LLM" story** |
| 7 | Weight fitting (FR-098, SHOULD) | Ship hand-set defaults **and say so** — do not present chosen weights as fitted |

**Never cut, at any cost:** the MUST core, the eval harness, the fallback ladder, the read-aloud
lint. A build that demos beautifully with no numbers behind it has lost the argument it exists to
make.

---

## 6. Definition of done

PRD §4's eight clauses, unmodified. The two that are easiest to declare prematurely:

- **"Three cold-start runs from a clean machine state with networking disabled."** Three actual
  runs, from a genuinely clean state, with the wifi genuinely off.
- **"Every MUST requirement passes its acceptance criterion."** Measured by the FR-coverage script,
  which reports unmapped MUSTs — not by reading the list and nodding.

---

**Plan complete — ready to build.** Start point is **S1**, whose first commit is the structural
guards, because they are the only thing in this plan that cannot be added later.
