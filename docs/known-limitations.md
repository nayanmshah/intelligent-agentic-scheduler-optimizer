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

**Consequence.** The determinism check (FR-097) runs in fixture mode, which is the
demo path. Live mode is an explicit opt-in and carries this caveat. We do **not**
claim temperature-based determinism the API cannot provide.

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

## 12. Live extraction does not fit the request-path latency budget

NFR-02 gives the extract stage **2.2 seconds** — what an operator can afford while a
patient is on the phone. Measured against the live API on eight golden requests:

| Model | p50 | p95 | Fits 2.2s? |
| :---- | --: | --: | :--------- |
| `claude-opus-5` (the configured extractor) | 7.3s | 9.1s | **No** |
| `claude-sonnet-5` | 7.0s | 9.2s | **No** |
| `claude-haiku-4-5` | — | — | rejects the `effort` parameter (400) |

**Adaptive thinking is not the cause.** Disabling it moved p50 from 7.3s to 7.2s. The
cost is generating the response itself: six fields, each carrying a confidence, a
derivation rule and a verbatim source span. FR-003's provenance requirement is what
makes the output large, and the provenance is not negotiable — it is the reason an
operator can trust the interpretation strip.

**What this means.** Committed fixtures are not a demo convenience; they are what makes
the stated latency target achievable at all. The shipped default is rules-mode
extraction (sub-millisecond, 96.3% accurate) with fixtures behind it, and that is a
design decision rather than a fallback.

**What would actually close it**, in the order worth trying:

1. **Stream the response** and parse incrementally — the operator needs the *first*
   fields (date, time) to render the strip, not the last.
2. **Split the call.** Extract the six values in one small request; resolve spans in a
   second, off the critical path. The strip can fill in provenance a beat later.
3. **Run rules first and the model only on disagreement.** Rules answer instantly and
   are right 96.3% of the time; spend the latency only where the two differ.
4. Re-measure on Haiku once it accepts `effort`, or without structured outputs.

None of these are implemented. The number is stated because "we'd use the model live in
production" is a claim that should come with a measurement, and this one does not
currently support it.

---

## 13. Only one of the four roles carries a model in the demo

The architecture is four agent roles, each behind a `Protocol` so the implementation is
swappable by config (NFR-28). What actually runs on the demo path is narrower than
"four agents" suggests, and it is worth saying before someone asks:

| Role | Demo implementation | Model involved? |
| :--- | :------------------ | :-------------- |
| Intent Extractor | `fixtures(llm)` | **Yes** — real Claude output, recorded once and replayed |
| Constraint Verifier | `rules` | No — and no LLM implementation exists at all |
| Schedule Reasoner | deterministic | No — **by design**, this is the thesis |
| Explainer | `template` | No — `LlmExplainer` is built and tested, but activates only in live mode |

**The reasoner is not a gap.** "LLMs at the edges, arithmetic in the middle" is the
product's central claim; a deterministic ranker is the feature.

**The explainer is a mode difference, not a missing piece.** `LlmExplainer` and its
five-check faithfulness gate exist and are tested. In fixture mode the template renders
instead — and the template cannot hallucinate by construction, since it only
interpolates facts the scorer emitted. A consequence worth knowing: **the faithfulness
gate never fires during the demo**, because there is no generated prose to check.

**The verifier is a real gap against NFR-28**, which asks every agent for two
implementations. It has one. The reason is that its checks — is the date in the past?
does this provider exist and hold this credential? — are lookups against a known world,
where a model would add latency and a failure mode to answer *less* reliably. That is a
defensible decision, but NFR-28 says "every agent" and this is an exception to it, so it
is recorded here rather than left to be discovered. The `ConstraintVerifier` Protocol is
in place, so the seam costs nothing to fill later.

**What this means for the demo narration.** "Four agents, three of which can run without
a model, and the one that decides never uses one" is accurate. "Four AI agents" is not,
and will not survive the first follow-up question.
