# Demo Script

> Twelve minutes, six requests, three screens. Every line of output below is copied
> from an actual run against the committed dataset — nothing here is illustrative.
>
> **Before you start:** `make demo`, then open `http://127.0.0.1:8000`.
> The header must read **Reference date: Monday, August 10, 2026, 9:00 AM** and
> **Offline · fixtures**. If it says *Live model*, unset `ANTHROPIC_API_KEY` — the
> whole demo runs with no network.

**Keyboard.** `E` focuses the request box · `Enter` submits · `1` `2` `3` book that
card · `R` resets the dataset. The front desk is a keyboard job; a mouse round-trip is
dead air on a live call.

---

## 0 · Frame it (30 seconds, before touching anything)

> "A front-desk coordinator hears *'can I come in next Thursday after 3?'* forty times
> a day. They alt-tab to a grid, scan for white space, and pick something. The pick is
> usually fine and occasionally expensive — it fragments the day, or it burns a block
> the practice was holding for restorative work. This turns that sentence into three
> ranked options, each with a reason you can read aloud."

Point at the header once: **the dataset's today is Monday the 10th.** Every date on
screen is relative to that. Say it now and no one is confused later.

---

## 1 · The main line — "it understood, and it can show its work"

Type (or click the first example chip):

```
Can I come in next Thursday after 3? Prefer Sarah if she's around.
```

**What appears:**

```
[1] Nothing opened when you asked, but Thursday August 20th at 3:00pm
    with Sarah, outside the days you asked about.
[2] Nothing opened when you asked, but Thursday August 20th at 4:00pm
    with Sarah, outside the days you asked about.
[3] Nothing opened when you asked, but Wednesday August 12th at 4:00pm
    with Nia, outside the days you asked about.
```

**Say this:**

> "Three things happened. It resolved *next Thursday* to the 13th — look at the
> interpretation strip, every field is highlighted back to the words that produced it.
> It found nothing on the 13th after 3. And rather than showing an empty screen, it
> offered the nearest alternatives — but it **leads with the gap**. It doesn't say
> 'Thursday the 20th with Sarah' and let you discover the mismatch on the phone."

**The moment worth pausing on.** This sentence used to read *"Thursday August 20th at
3:00pm with Sarah, the provider you asked for"* — technically true, and it would have
been read to a patient as a match. The caveat was being dropped because the sentence
was assembled by contribution size, and an axis that scores badly contributes little.
Warnings now outrank compliments. That is the kind of bug this product exists to not
have.

**The interpretation strip sits above the cards** — Visit, Provider, Urgency, Avoid,
and the resolved date and time. **Click any chip** and it opens to show that field's
confidence and the exact span of the patient's words it came from. Nothing on this
screen is asserted without provenance.

---

## 2 · The funnel — "did it miss anything?"

Stay on the same result. Point at the funnel counter:

```
grid 3348  →  enumerated 13392  →  feasible 133  →  offered 3
```

**Say this:**

> "Thirteen thousand candidates were considered and every one that was rejected is
> still here with the reason it was rejected. `enumerated = offered + rejected`,
> reconciled on every request. Nothing is deleted from the pipeline — it's annotated.
> So 'did it miss anything?' is a question with an answer, not a shrug."

**Open the rejection ledger** (one click, never on screen by default) → every cause,
grouped, in plain language:

```
We looked at 7972 other times for you, but the room is already in use.
We looked at 2904 other times for you, but the practice is on a break then.
We looked at 1320 other times for you, but the practice is closed then.
We looked at  480 other times for you, but that time is reserved for emergencies.
We looked at  199 other times for you, but the provider is already booked.
We looked at  184 other times for you, but no dentist was free for the short exam
                                        inside the appointment.
```

That last line is the one to point at — three rooms sat empty and the slot was still
unbookable, because a hygiene appointment needs a dentist free for a short exam
*inside* it. A grid shows white space there. This says why the white space is a lie.

---

## 3 · The one that asks a question

```
my tooth's been bothering me
```

**What appears:** a single question, above the results —

```
Is this for emergency exam or crown preparation?
```

**Say this:**

> "It ran the request both ways — as a 30-minute limited exam and as a 90-minute crown
> prep — and the two readings produced *different* answers. So it asks. If they had
> produced the same three slots, it would not have asked, because the ambiguity
> wouldn't have mattered."

**This is the point to land:** the system asks when the ambiguity is
**decision-relevant**, not whenever it is uncertain. Uncertainty that doesn't change
the answer is not worth a patient's time.

Answer either option and the results resolve in place.

---

## 4 · The hard constraint it will never relax

```
Not Thursday, and not Wednesdays or Fridays either
```

**What appears:**

```
[1] Monday August 24th at 1:50pm with Nia, someone on the same team as
    your usual provider.
[2] Monday August 24th at 3:40pm with Sarah, it uses time the practice
    keeps for after-school visits, your usual hygienist.
[3] Monday August 24th at 8:00am with Maya, a provider who is new to you,
    in the window you asked for.
```

**Say this:**

> "Three exclusions from one sentence, including the plural. And a patient exclusion is
> never relaxed — not by the urgency escalation, not by the counterfactual engine, not
> by any weight setting. Suggesting a Tuesday to someone who said *'not Tuesdays, I
> have physio'* is worse than offering nothing."

Note offer [2] volunteers that it uses after-school time. It didn't have to say that.

---

## 5 · The policy screen — "consistency is the product"

Navigate to **Policy**.

**Say this:**

> "Here is what a practice manager controls: four weights — Time fit, Continuity,
> Efficiency, Block protection — as one profile applied to every request. Move a slider
> and the three cards re-rank instantly, because the axis scores were computed once and
> the weights are just a dot product over them. No re-search, and no model call."

Move **Continuity** up. Watch the ranking change and the contribution bars redraw. The
footer under the sliders states it outright: *re-ranked in Nms with zero model calls.*

The preset row above the sliders carries a **General Practice** default and a profile
marked **· fitted**. Worth 15 seconds:

> "The fitted one is committed but **not** the default. Fitting to our own labels
> lifted the hit rate to 70% and that's not a win — the labels and the objective came
> from the same head. It ships as a diagnostic of the labels, not as policy."

Then the important half:

> "There is deliberately **no weight control on the console**. Per-call fiddling is
> exactly the inconsistency this replaces. The manager sets policy; the coordinator
> executes it."

If asked about no-show risk: the hook exists in the policy model and **ships off**. A
no-show signal can proxy for socioeconomic status, so it is a named, individually
visible lever rather than something folded into a composite weight — a practice that
turns it on does so knowingly. It is not on this screen in v1.0.

---

## 6 · The traces screen — "every answer is replayable"

Navigate to **Traces** and open the most recent decision. Each row shows its stage,
duration, and any fallback that fired.

**Say this:**

> "Every stage, its duration, whether a fallback fired and why. This whole demo ran
> with the network physically blocked — the model calls are served from fixtures
> recorded once and committed. When a stage falls back, the operator sees a normal
> answer and the trace sees the truth. A fallback that's invisible in both places is
> indistinguishable from a system that never fails."

---

## 7 · Close on the numbers (`make eval`, in a second terminal)

```
Extraction accuracy (FR-093)
  field                     rules        LLM
  OVERALL                   96.3%      94.8%

Head-to-head vs naive first-available (FR-095)
  ours  top-3           45.3%
  naive top-3           47.2%
  orphan min/case      ours    1.3   naive   14.6
  protected min/case   ours    0.0   naive    3.1
```

**Say the uncomfortable number first:**

> "Our top-3 hit rate is *below* the naive baseline, and I'll tell you why rather than
> hide it. The 'preferred slot' label is a heuristic — earliest non-fragmenting slot
> with the usual provider — and that objective is much closer to the naive baseline's
> than to ours. We're being scored on how often we agreed to be earliest-first.
>
> The unbiased numbers are the two below it, measured from the schedule rather than
> from either ranker: **eleven times fewer orphan minutes, and it never eats a
> restorative block.** That's the claim the product actually makes.
>
> The fix isn't to tune the heuristic until we win — that's fitting to the referee.
> It's three practising schedulers labelling independently. And if they disagree with
> each other, that disagreement is the business case for the policy layer."

---

## If something goes wrong

| Symptom | Cause | Do this |
| :------ | :---- | :------ |
| Header says **Live model** | `ANTHROPIC_API_KEY` is set | `unset ANTHROPIC_API_KEY`, restart. Nothing else changes. |
| Dates look wrong | Reading them against the real today | The dataset's today is **Monday 2026-08-10**, shown in the header |
| A booking says the slot moved | Someone booked it earlier in the demo | Press `R` to restore the dataset. Traces are kept. |
| Blank results panel | Request not submitted | The textarea needs `Enter`, not the send key of a different app |

**Recovery is one keystroke.** `R` restores the committed dataset without restarting
the server, so a mis-click in front of an audience costs a second.

---

## What to skip if you have six minutes, not twelve

Keep **§1** (understanding + leading with the gap), **§3** (asks only when it matters),
and **§7** (the honest numbers). Those three carry the argument. §2, §4, §5 and §6 are
depth on request.
