# Known Limitations

> Every limitation here is deliberate and recorded. A non-goal without a reason is an
> oversight; a non-goal with a reason is a design decision. This page exists so the
> difference is checkable.

---

## 1. Live-mode extraction is not reproducible

**What.** With `SCHED_LLM_MODE=live`, two identical requests may produce different
extractions. Only fixture mode is byte-identical.

**Why it cannot simply be fixed.** The original design called for `temperature=0`.
Current Claude models **reject sampling parameters with a 400** — the parameter no
longer exists. Temperature was never what carried determinism anyway:

| Mechanism | Status |
| :-------- | :----- |
| Committed fixtures are the **default** source, not a fallback | The actual guarantee |
| Ranking is a pure function of `(constraints, schedule, profile, NOW)` | Unchanged — the model cannot reach it |
| Injected clock, committed seed | Unchanged |
| `temperature=0` | **Unavailable.** Removed from the design |

**Consequence, and it is a real trade.** Live is now the shipped default, so **the demo
path is not byte-reproducible**. The determinism check (FR-097) runs in fixture mode and
is reported as *not applicable* on a live scorecard rather than as a pass — marking it
green there would be the most misleading number on the card.

What survives regardless: **ranking** is a pure function of
`(constraints, schedule, profile, NOW)`, so two identical extractions always produce
identical offers. The nondeterminism is confined to language in and language out. We do
**not** claim temperature-based determinism the API cannot provide.

---

## 2. The golden set has one annotator, and the labels are unreviewed

**What.** All 54 golden requests were labelled by a single person, and the
"preferred slot" is a *heuristic*, not a scheduler's judgement.

**Why it bounds every ranking number.** The labels encode one reading of "good",
not a practice's. Worse, the preference heuristic — *earliest non-fragmenting
feasible slot with the patient's usual provider* — is closer to the **naive
baseline's** objective than to this system's. That biases the top-3 head-to-head
**against** this system.

The unbiased comparisons are the schedule-quality deltas, which are measured from the
schedule itself rather than from either ranker's own numbers:

| Measure | This system | Naive first-available |
| :------ | ----------: | --------------------: |
| Orphan minutes created per case | **1.3** | 14.6 |
| Protected block minutes consumed per case | **0.0** | 3.1 |

**The fix** is 2–3 practising schedulers labelling independently and reporting
inter-rater agreement. `GoldenLabel.labeler` exists for exactly this. And if real
schedulers disagree substantially with each other, *that disagreement is itself the
business case for a configurable policy layer.*

---

## 3. Weight fitting currently learns the labeller, not the scheduler

`make fit` finds `0.70 / 0.25 / 0.05 / 0.00` and lifts the top-3 hit rate from 39% to
70.7%. That is **not** a product win. The fitted vector collapses onto time-fit and
continuity, which is precisely what the label heuristic optimises for — fitting to a
proxy label teaches the model the proxy.

All four axes show a flat region ≤ 0.10 wide, which says the same thing from the other
side: a robust fit would be flat across a broad band.

**So the shipped default remains the hand-set General Practice profile.** The fitted
vector is committed as a *diagnostic of the labels*, not applied. This is disclosed
rather than quietly shipped, because "our weights are fitted" would be a misleading
claim in its current state.

---

## 4. The operator/manager split is not a security boundary

`/` and `/policy` are separate **routes**, not separate roles. There is no
authentication and no authorization in v1.0 — a deliberate non-goal, since it adds no
decision quality at this scale.

The header carries a **Seat: Front desk / Practice manager** label so the two jobs are
legible during a walkthrough. It is deliberately styled as a label and not as an
account: no avatar, no "signed in as", no user menu, and a tooltip that states there is
no authentication. A component test asserts those absences, because an affordance that
*looks* like a login is worse than none — it implies a boundary that is not there.

**Any deployment beyond a single trusted workstation must add real authorization
before the policy panel is exposed.** A front-desk user who can reach `/policy` and
move the weights is precisely the consistency destruction this product exists to
eliminate.

---

## 5. Voice input is permanently cut

The original brief allowed "text or speech". Transcription adds a runtime failure mode
for **zero decision quality** — constraint extraction operates on text either way, so
speech would only change how the text arrives.

---

## 6. Single timezone, and no DST day inside the seed window

The dataset is one location in `America/Los_Angeles`, and no DST transition falls
between 2026-08-03 and 2026-08-28.

Both assumptions are confined behind one conversion module (NFR-32) rather than
diffused through the code, and **both transitions are asserted** even though neither
falls in the dataset — see `tests/requirements/test_s2_write_path.py`. Those
assertions were written during the QA pass and immediately found a real bug:
`day_length_minutes` returned 1440 for every day, including the two it exists to
describe ([`qa-report.md`](qa-report.md) QA-1). DST enters a
14-day horizon twice a year in every zone; a spring-forward day contains an hour that
does not exist and a fall-back day contains one that happens twice. That is the class
of bug that is invisible until the Sunday morning it is not.

---

## 7. One operator at a time

`NFR-08` scopes v1.0 to a single session. The **hold model** is in-memory and
single-process, so multi-seat needs real work.

The *atomic commit* is not deferred, though: booking is a conditional write
(compare-and-set on a per-`(operatory, day)` version), because check-then-write cannot
fail at one seat and double-books at two — the worst possible pairing of severity and
undetectability.

---

## 8. The no-show risk hook ships OFF

A no-show-risk signal can proxy for socioeconomic status. The lever exists, is
individually visible in the contribution bar, is configurable, and **defaults to
off**. A practice that turns it on does so knowingly. It is named here rather than
buried inside a composite weight.

---

## 9. Accessibility beyond the stated bar is deferred, not rejected

Presentation Mode and WCAG AA contrast on text and contribution bars are in.
Full WCAG AA conformance is deferred — and named, because a front-desk tool used all
day is exactly the kind of software that needs it.

---

## 10. The numbers are in minutes, never in dollars

The harness measures minutes and counts. The system has no fee schedule, and a revenue
figure derived from synthetic data and an invented price list would be unfalsifiable —
impressive on a slide and useless in a negotiation.

Orphan minutes and protected-block minutes are measurable today. A practice's own fee
schedule is what converts them into money, and that conversion belongs to the practice.

---

## 11. The extraction head-to-head is biased toward the rules extractor

Both columns of FR-093 are now populated, from real model output recorded once against
the live API and committed as fixtures:

| Field | Rules | LLM |
| :---- | ----: | --: |
| `date_range` | 98.1% | 98.1% |
| `time_window` | 94.4% | 90.7% |
| `urgency` | **98.1%** | 85.2% |
| `provider_preference` | 98.1% | 98.1% |
| `appointment_type` | 88.9% | **96.3%** |
| `exclusions` | 100.0% | 100.0% |
| **Overall** | **96.3%** | 94.8% |

**The headline number does not mean the rules extractor is better.** One person wrote
both the labels and the rules, so wherever the two disagree about a *convention* rather
than a *meaning*, the rules win by construction. This is the same circularity already
disclosed for the ranking labels in §2, appearing in a second place.

Two conventions account for almost the whole gap:

- **`urgency` (6 of 8 misses).** The labels expect an inferred urgency to be marked
  `derived`, with a named rule and **no source span**. The model instead cites a span
  for urgency it actually inferred — for *"Book me in next week sometime"* there are no
  words that say "routine". Under FR-003 the label convention is the stricter and more
  defensible one, so this gap is real, and it is a **provenance** failure rather than a
  comprehension one. It is also exactly what the faithfulness gate exists to catch.
- **`afternoon` starts at 12:00 or 13:00?** The labels say 13:00 (post-lunch); the model
  says 12:00. Neither is wrong. A practice would settle this in a sentence.

The remaining two urgency misses are genuine judgement disagreements — the model reads
*"my tooth is killing me"* and *"swollen and sore since last night"* as `emergency`
where the label says `urgent`. A dentist, not an engineer, should arbitrate those.

Going the other way, **the model is 7.4 points better at `appointment_type`**, and that
difference is not a convention artefact: it reads *"my gums have been bleeding, due for
maintenance"* as periodontal maintenance and *"is that a crown or just a look?"* as an
exam, where the keyword rules reach for a routine cleaning. Inferring clinical intent
from symptom language is precisely the part that resists enumeration.

**So the shipped default is rules-mode**, on latency and determinism grounds rather than
accuracy grounds — and the honest reading of this table is *"the two are close, and they
fail differently."* Resolving it properly needs the same fix as §2: labels from
practising schedulers, written before either extractor is looked at.

> One measurement bug was found and fixed while producing this table. An open-ended
> window is representable two ways — `None` ("from opening") and the opening minute
> itself — and the comparator scored them as different. That cost the LLM column five
> cases it had read correctly, and `time_window` was reported as 81.5% instead of 90.7%.
> The comparator now normalises before comparing.

---

## 12. Live latency: ~3.9 s typical, and how it got there

NFR-02's target is a sub-5-second answer; beyond that the operator opens the calendar
anyway. The first live pipeline missed it badly — ~15.9 s — and the fix was measurement
rather than optimism (`docs/latency-research.md`, ADR-21):

| | Before | After |
| :-- | --: | --: |
| extract | 7.3 s · Opus, 558-token payload | 2.0 s · Haiku, 162-token quote format |
| verify | 4.0 s · Sonnet, on the critical path | 1.3 s · Haiku, **in parallel** |
| explain | 5.0 s · Sonnet | 1.5 s · Haiku, in parallel with verify |
| **end to end** | **~15.9 s** | **p50 3.9 s · max 4.9 s** |

Three findings carried it: adaptive thinking was **not** the cost (< 0.2 s); output
tokens were (near-linear); and the LLM verify never needed to gate the reasoner, since
hypotheses come from the deterministic floor.

**What was traded, stated plainly.** Extraction accuracy on the golden labels moved
93.8% → ~91% (fixture measurement; the labels' bias toward the rules extractor is §2
and §11 of this document — `time_window` carries most of the drop, largely the
"afternoon starts at 12:00 or 13:00" convention). The faithfulness gate's pass rate and
the verifier's catch rate did not regress. Any stage moves back up a model tier with
one env var (`SCHED_MODEL_EXTRACT=claude-opus-5`), at ~3 s per request for extraction.

**Under 2 s** would need speculative rendering from the rules extraction while the
model runs — rejected for now because cards that can change underneath the operator
cost more trust than 2 s of visible, narrated progress buys.

---

## 13. Three of the four roles run on a model; the fourth never will

| Role | Shipped implementation | Model? |
| :--- | :--------------------- | :----- |
| Intent Extractor | `llm` | **Yes** — live, every request |
| Constraint Verifier | `llm` over a deterministic floor | **Yes** — live, every request |
| Schedule Reasoner | deterministic | **No, permanently** |
| Explainer | `llm` behind the faithfulness gate | **Yes** — live, every request |

**The reasoner is not a gap and never will be.** "LLMs at the edges, arithmetic in the
middle" is the product's central claim. A model driving enumeration would miss
candidates and make *"did it miss anything?"* unanswerable, which is the one question
this product exists to answer.

**The verifier's model output is bounded by design.** It may raise a flag and propose a
question; it may not alter the constraints, and it never sees a candidate slot. The
deterministic checks run first and its flags are merged in, so the model adds to the
picture and cannot subtract from it. A wrong call costs a spurious question, never a
wrong booking.

**The explainer's output is gated, not trusted.** Six checks (FR-062) run over every
generated sentence; a failure substitutes the template silently and records the firing.
The rate is typically one rejection per three-card batch, which is the honest number —
a gate that never fires is a gate that is not running.

> One of those six checks exists because of something found during live testing: the
> model wrote *"You're booked for a Cleaning on Wednesday"* and every other check passed
> it. Nothing was booked. An operator reading that aloud tells a patient they have an
> appointment they do not have, so F6 now rejects any sentence asserting the booking
> exists — in the gate, not only in the prompt, because a prompt is a request and a
> gate is a guarantee.
