"""The golden set: ~40 requests with **hand-written** expected constraints.

These are written by hand rather than captured from the extractor's own output. If
the labels were the extractor's output, FR-093's accuracy number would be 100% by
construction and would mean nothing -- the whole point is an independent statement of
what the right answer is.

**Disclosed limitation [R-08]:** a single annotator wrote these, so they encode one
person's reading rather than a practice's. That bounds every ranking number in the
scorecard, and the fix is 2-3 practising schedulers labelling independently and
reporting inter-rater agreement. It is recorded rather than hidden.

Every field left as ``None`` means "the extractor should mark this derived" -- an
absence is as much a claim as a value.

Reference NOW: Monday 2026-08-10 09:00 -07:00.
  Mon 10 · Tue 11 (near-full) · Wed 12 (gaps seeded) · Thu 13 (doctor-check starved,
  Sarah on PTO) · Fri 14 (sparse) · Mon 17 … Fri 21 · Thu 20 (hygiene rooms full)
"""

from __future__ import annotations

from typing import Any

D = "2026-08-"


def label(
    text: str,
    *,
    tags: list[str],
    date: tuple[str, str] | None = None,
    window: tuple[int | None, int | None] | None = None,
    urgency: str | None = None,
    provider: str | None = None,
    type_id: str = "prophy_adult",
    exclude_weekdays: list[int] | None = None,
    note: str = "",
) -> dict[str, Any]:
    return {
        "raw_text": text,
        "class_tags": tags,
        "expected": {
            "date_range": list(date) if date else None,
            "time_window": list(window) if window else None,
            "urgency": urgency,
            "provider_preference": provider,
            "appointment_type": type_id,
            "exclusions": exclude_weekdays or [],
        },
        "note": note,
    }


GOLDEN: list[dict[str, Any]] = [
    # -- relative date (>= 3, per FR-092) ------------------------------------
    label("Can I come in next Thursday after 3? Prefer Sarah if she's around.",
          tags=["relative-date", "ambiguity", "provider-preference"],
          date=(f"{D}13", f"{D}13"), window=(900, None), provider="prov-sarah",
          note="the reference scenario; 'next Thursday' is genuinely ambiguous [D-03]"),
    label("Any chance of something tomorrow morning?",
          tags=["relative-date"], date=(f"{D}11", f"{D}11"), window=(480, 720)),
    label("I'd like a cleaning this Friday",
          tags=["relative-date"], date=(f"{D}14", f"{D}14")),
    label("Book me in next week sometime",
          tags=["relative-date", "flexible"], date=(f"{D}17", f"{D}21")),
    label("Can we do Wednesday?",
          tags=["relative-date"], date=(f"{D}12", f"{D}12")),
    label("How about a week on Monday?",
          tags=["relative-date"], date=(f"{D}17", f"{D}17"),
          note="ADVERSARIAL: 'a week on Monday' is idiomatic; rules mode is expected to miss"),

    # -- time window ---------------------------------------------------------
    label("Something after 4 on Wednesday please",
          tags=["time-window"], date=(f"{D}12", f"{D}12"), window=(960, None)),
    label("First thing Tuesday if you have it",
          tags=["time-window"], date=(f"{D}11", f"{D}11"), window=(480, 600)),
    label("I can only do before noon",
          tags=["time-window"], window=(None, 720)),
    label("Afternoon works best for me",
          tags=["time-window"], window=(780, 1020)),
    label("My kid gets out of school at 3, so after that",
          tags=["time-window", "adversarial"], window=(900, None), type_id="prophy_child",
          note="ADVERSARIAL: the time is implied by a reason, not stated"),

    # -- urgency -------------------------------------------------------------
    label("I need something first thing tomorrow, it's urgent",
          tags=["urgency", "time-window"], date=(f"{D}11", f"{D}11"),
          window=(480, 600), urgency="urgent", type_id="prophy_adult"),
    label("My tooth is killing me, anything today?",
          tags=["urgency", "symptom"], date=(f"{D}10", f"{D}10"),
          urgency="urgent", type_id="limited_exam"),
    label("It's an emergency, I chipped a tooth",
          tags=["urgency", "symptom"], urgency="emergency", type_id="limited_exam"),
    label("No rush at all, whenever suits you",
          tags=["urgency", "flexible"], urgency="flexible"),
    label("Swollen and sore since last night, need to be seen",
          tags=["urgency", "symptom"], urgency="urgent", type_id="limited_exam"),

    # -- exclusions ----------------------------------------------------------
    label("Whatever works next week, I have PT on Tuesdays",
          tags=["exclusion", "relative-date"], date=(f"{D}17", f"{D}21"),
          exclude_weekdays=[1]),
    label("Any day except Monday please",
          tags=["exclusion"], exclude_weekdays=[0]),
    label("I can't do Wednesdays or Fridays",
          tags=["exclusion"], exclude_weekdays=[2, 4]),
    label("Not Thursday, I'm travelling",
          tags=["exclusion"], exclude_weekdays=[3]),

    # -- provider preference -------------------------------------------------
    label("Can I see Sarah for my cleaning?",
          tags=["provider-preference"], provider="prov-sarah"),
    label("I'd rather see Dr. Patel this time",
          tags=["provider-preference"], provider="prov-patel", type_id="prophy_adult"),
    label("Need a cleaning, not with Dr. Okafor please",
          tags=["provider-preference", "adversarial"], provider=None,
          note="negation must NOT become a preference"),
    label("Whoever is free is fine",
          tags=["provider-preference", "flexible"], provider=None),

    # -- appointment type ----------------------------------------------------
    label("Time for my six month check-up",
          tags=["type"], type_id="prophy_adult"),
    label("I need my crown fitted, the lab sent it back",
          tags=["type", "continuity"], type_id="crown_seat",
          note="the seat should go to the dentist who did the prep"),
    label("I think I need a filling, there's a hole",
          tags=["type"], type_id="filling_1s"),
    label("The dentist said I need a root canal",
          tags=["type"], type_id="rct"),
    label("My gums have been bleeding, due for maintenance",
          tags=["type"], type_id="perio_maint"),
    label("I need a tooth pulled",
          tags=["type", "equipment"], type_id="extraction",
          note="only fits the surgical-capable room (edge case 8)"),
    label("My denture is rubbing, can it be adjusted?",
          tags=["type"], type_id="denture_adjust"),
    label("First visit for my daughter, she's never been",
          tags=["type"], type_id="np_exam_fmx"),
    label("My tooth's been bothering me since Friday",
          tags=["type", "ambiguity", "symptom"], type_id="limited_exam",
          note="edge case 6a: limited exam vs. crown -- hypotheses should diverge"),

    # -- credential and equipment -------------------------------------------
    label("Can Dr. Okafor do my cleaning?",
          tags=["credential"], provider="prov-okafor", type_id="prophy_adult",
          note="edge case 7: graceful redirect, never an empty list"),
    label("I want the surgeon to look at this extraction",
          tags=["credential", "equipment"], provider="prov-okafor", type_id="extraction"),
    label("Cleaning with Dr. Patel",
          tags=["credential"], provider="prov-patel", type_id="prophy_adult",
          note="a dentist is not credentialed for hygiene"),

    # -- gap-fill and prime time --------------------------------------------
    label("A filling on Wednesday late morning",
          tags=["gap-fill"], date=(f"{D}12", f"{D}12"), window=(600, 720),
          type_id="filling_1s",
          note="edge case 3: the 50-minute hole fits 40 + turnover exactly"),
    label("Quick cleaning Wednesday early afternoon",
          tags=["prime-time"], date=(f"{D}12", f"{D}12"), window=(780, 900),
          note="edge case 4: booking mid-stretch creates two orphans"),
    label("A cleaning on Thursday afternoon",
          tags=["doctor-check"], date=(f"{D}13", f"{D}13"), window=(780, 1020),
          note="edge case 1: rooms open, no dentist free for the exam"),
    label("Anything on Tuesday? It's urgent",
          tags=["urgency", "escalation"], date=(f"{D}11", f"{D}11"), urgency="urgent",
          type_id="limited_exam",
          note="edge case 5: near-full day -> emergency-hold unlock"),

    # -- adversarial phrasings ----------------------------------------------
    label("Sometime after the holidays would be great",
          tags=["adversarial", "relative-date"],
          note="ADVERSARIAL: no holiday in the horizon; should fall back to the window"),
    label("Same time as last time with the same person",
          tags=["adversarial", "continuity"],
          note="ADVERSARIAL: requires patient history the extractor cannot see"),

    # -- topping every class up to FR-092's minimum of three -------------------
    # A class with one or two entries produces a number that is noise, and a noisy
    # number on a scorecard is worse than an absent one.
    label("Is my usual hygienist free on Wednesday?",
          tags=["continuity", "provider-preference"], date=(f"{D}12", f"{D}12"),
          provider=None, note="'usual' is relational, not a name -- rules mode cannot resolve it"),
    label("I'd like to stay with Sarah for my cleanings",
          tags=["continuity"], provider="prov-sarah"),
    label("Something short on Wednesday between my meetings",
          tags=["gap-fill"], date=(f"{D}12", f"{D}12"), type_id="denture_adjust"),
    label("A quick filling Wednesday if there's a slot going spare",
          tags=["gap-fill"], date=(f"{D}12", f"{D}12"), type_id="filling_1s"),
    label("Crown prep on Wednesday morning",
          tags=["prime-time"], date=(f"{D}12", f"{D}12"), window=(480, 720),
          type_id="crown_prep", note="high production; belongs in the protected block"),
    label("Just a cleaning, Wednesday first thing",
          tags=["prime-time"], date=(f"{D}12", f"{D}12"), window=(480, 600),
          note="low production in a protected block -- should be penalised"),
    label("Cleaning Thursday, any time that afternoon",
          tags=["doctor-check"], date=(f"{D}13", f"{D}13"), window=(780, 1020)),
    label("Gum maintenance on Thursday afternoon",
          tags=["doctor-check"], date=(f"{D}13", f"{D}13"), window=(780, 1020),
          type_id="perio_maint"),
    label("Tuesday, and it's an emergency",
          tags=["escalation", "urgency"], date=(f"{D}11", f"{D}11"),
          urgency="emergency", type_id="limited_exam"),
    label("I'm in a lot of pain, Tuesday if at all possible",
          tags=["escalation", "urgency", "symptom"], date=(f"{D}11", f"{D}11"),
          type_id="limited_exam"),
    label("Extraction, and it needs the surgical room",
          tags=["equipment"], type_id="extraction"),
    label("My tooth is chipped, is that a crown or just a look?",
          tags=["ambiguity", "symptom"], type_id="limited_exam",
          note="edge case 6a contrast: the two readings have very different durations"),
]
