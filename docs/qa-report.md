# QA Report

> Conducted after development completed. The quality gate (lint, types, tests, release
> check) had been green throughout, which is exactly why this pass was worth running:
> a green gate measures what you thought to test.
>
> Reproduce with `make coverage`, `make mutants`, `make check`, `make audit`,
> `make release`.

---

## Summary

| | Before | After |
| :-- | --: | --: |
| Tests | 134 | **218** |
| Line coverage | 74% | **78%** |
| Mutation score (decision core) | 35.7% | **53.1%** |
| Defects found | — | **5** (2 in shipped behaviour, 3 in verification) |

Coverage moved four points, which understates it: the gaps were concentrated in the two
places where a bug is *silent* — the write path and the timezone boundary — and both
were documented as tested when they were not.

The mutation score is the more honest measure, and the more uncomfortable one. At 74%
line coverage the suite caught **35.7%** of deliberate corruptions to the ranking. That
is what a green gate can hide.

---

## Findings

### QA-1 · `day_length_minutes` returned 1440 for every day, including the two it exists to describe — **product defect**

```python
start = datetime.combine(d, time(0, 0)).replace(tzinfo=tz)
nxt   = datetime.combine(d + timedelta(days=1), time(0, 0)).replace(tzinfo=tz)
return int((nxt - start).total_seconds() // 60)      # 1440, always
```

Subtracting two aware datetimes that **share a `tzinfo`** makes Python ignore the
offset and do wall-clock arithmetic. Documented behaviour, and invisible without a DST
day to test against.

The function's own docstring says it exists "so that assumption has to be written down
rather than made silently." It was making the assumption.

No production caller yet, so no live impact — but it is the module the whole codebase
is supposed to trust for this question, and it would have been wrong the first time
anyone asked. **Fixed** by converting to UTC before subtracting; asserted against a
spring-forward day (1380), a fall-back day (1500) and an ordinary day (1440).

### QA-2 · The conditional booking commit had zero tests — **verification gap, highest severity**

`commit_booking` is the compare-and-set that prevents double-booking. It was described
as "unit-tested" in `release-verification.md` and in a status report. **No test
referenced it.**

This is the single function where a bug means two patients in one chair, and the
failure mode is one the system cannot detect on its own.

**Fixed:** 8 tests covering the version match, the stale-version loss, the version
bump after commit, two callers racing on the same version, room overlap, provider
double-booking across rooms, the non-overlapping negative control, and hold release
scoped to the booked request only.

> The first draft of these tests hardcoded 08:00 and failed because the seed had
> already booked it. They now derive a free slot from the repository, so a regenerated
> seed cannot make them fail for the wrong reason.

### QA-3 · DST had no tests — **verification gap**

`known-limitations.md` §6 and the design FAQ both claimed "the DST fixtures already
exist — a spring-forward and a fall-back day are asserted." The *functions* existed
(`is_nonexistent`, `is_ambiguous`, `day_length_minutes`); the assertions did not, and
`timezone.py` sat at 56%.

**Fixed:** 7 tests over both 2026 transitions — day length, the hour that does not
exist, the hour that happens twice, the strict-mode refusal to silently shift a
nonexistent time, and a local↔UTC round trip across both days. This is what surfaced
QA-1. Coverage 56% → 94%.

### QA-4 · Re-ranking returned rows the UI could not render — **product defect**

The policy screen's whole purpose is watching the order change as the weights move. But
`/api/policy/rerank` looked up display names in the *original* top three, so any
candidate a new weighting promoted came back as `provider_name: null`. The screen
rendered it `83% —`.

Reproduced on three of three weightings tried; a heavy-efficiency vector produced two
blank rows out of three.

**Fixed** at the source rather than in the view: `ScoreMatrix` now carries a label per
row, so a matrix that can *rank* a candidate can also say what it is. The response also
now marks `was_offered: false`, and the UI labels those rows **newly promoted** — the
thing the manager most wants to see is which slot the weighting surfaced.

### QA-5 · `PhiRedactor.decision()` was untested — **verification gap, security-relevant**

Three documents state `PhiRedactor` is "unit-tested". Half true: `span()` was covered,
`decision()` was not — and `decision()` is the half that redacts `raw_text`, a patient
describing a symptom, plus the extracted constraints that quote it verbatim.

**Fixed:** a test asserting a `DecisionRecord` through the fan-out keeps its text on
the local replay leg, has it redacted on the external leg, retains its non-PHI fields,
and blanks **every** field the domain model marks PHI rather than only the one the test
names.

---

## Coverage

Reproduce with `make coverage`.

| Area | Before | After | Note |
| :--- | --: | --: | :--- |
| `data/session.py` | 75% | **98%** | the write path (QA-2) |
| `data/timezone.py` | 56% | **94%** | DST (QA-3) |
| `api/policy.py` | 27% | **90%** | re-rank, profiles, stability (QA-4) |
| `api/requests.py` | 50% | **79%** | booking, reset |
| `api/schemas.py` | — | **100%** | input validation |
| **Total** | **74%** | **78%** | |

The decision core was already strong by this measure and stayed there: `pipeline.py`
100%, `tiers.py` 100%, `gate.py` 100%, `compose.py` 99%, `enumerate.py` 98%, `axes.py`
97%.

That row is exactly why line coverage is not enough. Every one of those modules was
near-100% covered and, before the mutation pass, largely unconstrained — `axes.py` at
97% coverage caught 9.8% of mutations.

**Remaining gaps, and why they are acceptable:**

| Module | Cov | Why |
| :----- | --: | :-- |
| `agents/llm/client.py`, `extractor/llm.py`, `explainer/llm.py` | 30–65% | The live-network branches. Untestable in a suite that blocks the network by design; exercised by `make fixtures` against the real API. |
| `eval/run.py`, `eval/fit.py` | 0% | CLI entry points. `run.py` is exercised end-to-end by `make eval` and by the release check; `fit.py` is a diagnostic tool. |
| `api/traces.py` | 39%→ | Replay's *behaviour* is asserted at container level; the HTTP wrapper now has three tests. |
| `trace/opik.py` | 81% | The external-service branches, which need an Opik instance. |
| `agents/protocols.py` | 0% | Protocol declarations. No runtime code exists to cover. |

---

## Requirement traceability

| | Defined | Cited in source | Cited in a test |
| :-- | --: | --: | --: |
| FR | 108 | 76 | 51 |
| NFR | 32 | 14 | 12 |
| ADR | 19 | 15 | 4 |

**This measures citation, not coverage, and the two are not the same.** Spot-checks
confirm it: FR-036 (emergency-hold unlock) and FR-020 (credential redirect) appear in
no test by name and are both covered behaviourally in `test_s2_dataset.py` and
`test_s3_reasoner.py`.

So the number is not a coverage figure and should not be quoted as one. What it *is*
good for is direction: **adopt id citation in test docstrings as a convention**, and
the matrix becomes a real instrument instead of a rough one. Retro-fitting 57 ids now
would manufacture a traceability figure without adding a single assertion, which is
worse than the honest 51.

---

## Mutation testing

> `make mutants` — ~2 minutes, 507 mutants across the decision core.

Coverage says a line ran. Mutation testing asks whether a test would notice it being
**wrong**. Each run corrupts one operator or constant — an inverted comparison, an
off-by-one boundary, a swapped `and`/`or`, a dropped negation — and checks whether
anything fails.

The first answer was **35.7%**: nearly two-thirds of deliberate corruptions to the
ranking survived, against 78% line coverage. The diagnosis is one sentence: **the suite
asserted the pipeline's shape and almost never its arithmetic.** Three offers came
back, each with four contributions and a reason line, whatever the numbers were.

| Module | Before | After | What was missing |
| :----- | -----: | ----: | :--------------- |
| `select.py` | 17.4% | **52.2%** | *which* three slots — the diversity window, epsilon grouping, the tiebreak chain |
| `scoring/axes.py` | 9.8% | **53.8%** | the piecewise time-fit curve, the continuity tiers, orphan-minute arithmetic |
| `tiers.py` | 27.8% | **61.1%** | the 24h/72h boundaries, and that a routine request is never promoted by the clock |
| **Overall** | **35.7%** | **53.1%** | |

54 tests added, in three characterization suites. Two things they pin that nothing
did before:

- **The 24h and 72h tier boundaries**, which appear in the PRD, the architecture doc
  and the demo script. They can now only change deliberately.
- **Orphan-minute arithmetic** — the calculation behind the headline "11× fewer orphan
  minutes" claim, which had survived mutation entirely. Booking flush at the front of a
  free stretch orphans nothing; booking 20 minutes in strands 20 on each side. Both
  sides of the bookable threshold are asserted.

### The harness had two bugs of its own, and the first score was a lie

Worth recording, because it is the same failure this whole report is about.

1. **It reported 100%.** The work trees were missing `Makefile`, so the *baseline*
   failed, so every mutant "failed" too and was scored as killed. The harness now
   refuses to run unless the unmutated tree passes first — without that gate the number
   is worthless, and it looked excellent.
2. **The collector and the applier traversed in different orders**, so mutant *N* did
   not correspond to site *N*. Every reported line number would have been wrong. A
   mutation harness that lies about where the hole is, is worse than none.

Both are fixed and the traversal alignment is self-checked.

### Where it stands

**53.1% is not a good score in absolute terms, and it is not claimed as one.** What
changed is that the three modules deciding *what the operator sees* — the tier gate,
the axis curves, the selection — went from mostly-unconstrained to roughly half.

Remaining survivors, in priority order:

| Module | Survivors | Why it matters |
| :----- | --------: | :------------- |
| `scoring/axes.py` | 61 | mostly `score_efficiency` composite and `score_prime_time` |
| `ladder.py` | 38 | the feasibility rules — high value, and each needs a hand-built world |
| `availability.py` | 35 | prefix-sum internals; partly equivalent mutants |
| `scoring/compose.py` | 29 | the caveat/component selection introduced during S10 |

**Not every survivor is a defect.** Some are equivalent mutants — a constant whose
change cannot alter an observable outcome. Separating those from real gaps takes
reading each one, which is the next increment rather than something to assert in
advance.

---

## Method

- **Coverage measurement** — `pytest-cov` over the whole suite, read by module rather
  than by total, because the total hides exactly the concentration that mattered here.
- **Adversarial input** — twelve hostile or malformed requests driven through the
  running orchestrator (see [`security-review.md`](security-review.md), which found the
  blank-request defect).
- **Claim verification** — every "is tested" / "fixtures exist" assertion in the docs
  checked against the suite. Three were false; all three are now true because the tests
  were written, not because the claims were softened.
- **Exploratory testing** — the reference scenarios run through the product and the
  output read as an operator would. This is what found the offer-copy defects during
  S10 and the re-rank rendering defect here. It remains the highest-yield technique in
  this codebase and the least automatable.

## Not done

- **Load and soak testing.** Single-operator scope (NFR-08); no concurrency is
  exercised beyond the compare-and-set unit tests.
- **Cross-browser testing.** Chrome only.
- **Accessibility audit.** Presentation Mode and AA contrast are in; full WCAG AA
  conformance is deferred and named in [`known-limitations.md`](known-limitations.md) §9.
- **Equivalent-mutant triage.** 238 survivors remain; an unknown fraction cannot
  change behaviour at all. Reading them is what turns 53.1% into an actionable number
  rather than a target to game.
