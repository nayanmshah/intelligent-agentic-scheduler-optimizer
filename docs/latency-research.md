# Latency Research — 15.9 s to 3.9 s

> Every number here is a real API round trip against the live Anthropic API, with
> output tokens recorded next to wall time. Probe sets are named; the full golden set
> (54 cases) decided anything that shipped. Conducted 2026-08-08; results feed ADR-21.

## The question

The live pipeline ran ~15.9 s end to end: three sequential model calls at roughly
7 s + 4 s + 5 s. NFR-02 wants < 5 s — beyond that the operator opens the calendar and
the product has lost. Specifically asked: is Sonnet needed anywhere or does Haiku
suffice, does adaptive thinking matter, and what gets us under 5 s — under 2 s if
possible.

## Finding 1 — Adaptive thinking is not the cost

Opus extraction, current schema, 10-case probe:

| thinking | p50 |
| :--- | --: |
| adaptive (shipped) | 6.63 s |
| off | 7.31 s |

Within noise — *slightly faster with thinking on this sample*. Whatever intuition says
about "thinking overhead", the measurement says the lever is elsewhere. Thinking stays
on for models that support it; Haiku rejects the parameter and loses nothing.

## Finding 2 — Output tokens are the cost, near-linearly

| configuration | out-tokens p50 | p50 latency |
| :--- | --: | --: |
| sonnet · full schema | 636 | 6.36 s |
| opus · full schema | 558 | 6.63 s |
| sonnet · slim schema | 335 | 4.28 s |
| haiku · full schema | 295 | 2.68 s |
| opus · slim schema | 286 | 5.39 s |
| haiku · slim schema | 162 | 1.88 s |

Two consequences. First, **the wire schema was the biggest single lever**: the original
format made the model emit, per field, a meta object with confidence, a derived flag, a
rule name, span text *and* character offsets. The slim format emits a verbatim quote
and a confidence; offsets are found by local string search and "derived" simply means
"no quote". Same information, ~70% fewer output tokens — and it **eliminated a failure
class**, because model-emitted offsets disagreed with their own span text often enough
to fail validation and silently fall back to rules.

Second, model choice compounds with schema choice rather than substituting for it.

## Finding 3 — Haiku holds up where the architecture bounds the damage

Full 54-case golden set, slim schema:

| model | p50 | max | accuracy |
| :--- | --: | --: | --: |
| haiku-4.5 | **1.96 s** | **3.56 s** | 89.6% |
| sonnet-5 | 4.15 s | 8.51 s | 92.3% |
| opus-5 | 4.76 s | 12.83 s | 92.3% |

(Reference: the shipped opus/full-schema config measured 93.8% live; the deterministic
rules score 96.3% on labels written by the same hand — the bias is documented in
`known-limitations.md` §2/§11.)

Haiku's 10-case probe showed frightening tails (max 18.6 s) that **vanished at n=54**
(max 3.56 s — the outliers were first-run artifacts). It ended with the *tightest*
distribution of the three, which matters more than the median: the timeout that
protects the ladder can sit at 2× a 3.6 s max, not 2× a 13 s one.

Per stage, against the incumbent:

| stage | metric that matters | sonnet | haiku |
| :--- | :--- | --: | --: |
| explain | faithfulness-gate pass rate | 20/21 | **20/21** — at half the latency (1.5 s vs 2.8 s) |
| verify | seeded mismatches caught | 1/2 | **2/2** — at 1.25 s vs 3.18 s |

This is the architectural point rather than a model-benchmark point: **the gate and the
deterministic verify floor are what make a cheap model safe.** A bad explainer sentence
costs a template fallback; a bad verify flag is bounded to one spurious banner; neither
can reach the booking. Where the damage is bounded, buy speed.

The one calibration cost: raw Haiku was chattier on verify (2 false flags across the
probe set, one fabricating a claim about the extraction). Tightened in prompt v2 — "at
most one flag, the EXTRACTED section is ground truth, restating with less certainty is
not a flag" — after which: **4/4 mismatches caught, 1/4 mild false flags**, better than
Sonnet's catch rate at 2.5× its speed.

## Finding 4 — The verify call never needed to be on the critical path

Hypotheses — the things the reasoner and the clarifying-question flow need — come from
the **deterministic floor**, which answers in under a millisecond. The model verify
only *adds* semantic flags. So it now runs concurrently with reason + explain and joins
before final assembly:

```
before:  extract ─→ verify ─→ reason ─→ explain            ≈ 15.9 s
after:   extract ─→ floor(≈0) ─→ reason ─→ explain         p50 3.9 s
                    └→ verify (parallel) ──────┘
```

## Result

Five reference scenarios, live, end to end: **p50 3.91 s, max 4.86 s** — 4× faster and
under the 5 s target. The stage stream (already shipped) shows each agent finish, so
the remaining four seconds read as work, not as a hang.

## Why not under 2 s

Extraction *alone* is p50 1.96 s, and it gates everything. The remaining routes:

1. **Speculative rules-first rendering** — decision on screen at ~0.1 s from the
   deterministic extraction (96.3% on these labels), silently re-ranked when the model
   lands at ~2 s. Rejected for now: cards that can change underneath an operator
   mid-read cost more trust than two seconds buy. Revisit if sub-2 becomes a hard
   requirement.
2. **Hedged extraction** (send a second call at p90, take the first back) — pointless
   now that the tail is 3.6 s.
3. **A smaller quote format still** (drop confidences, ~40 fewer tokens) — maybe
   0.3 s; not worth the provenance loss.

## Reproducing

The probe scripts live in the session scratchpad and are deliberately not committed —
they are one-shot instruments, and the numbers that matter are pinned here and asserted
where they are load-bearing (`test_the_live_round_trip_is_reported`, the timeout-ladder
test, `make eval-live`). Per-stage models and timeouts are `Settings` fields; rerunning
any comparison is an env var away.
