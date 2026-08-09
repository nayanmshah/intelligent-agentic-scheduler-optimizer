"""What each stage actually received and produced, summarised for a trace.

An observability span whose "input" is a description of the stage and whose "output"
is the name of the implementation is not showing input and output — it is showing a
label and a config value. This module builds the real thing: the patient's words going
into extraction, the constraints coming out, the flags verification raised, the funnel
the reasoner walked, the sentences the explainer wrote and which of them the gate kept.

Three rules, because this runs while a patient waits:

* **Summaries, not dumps.** A trace is read by a person. Field values and counts, not
  a serialised object graph.
* **Cheap.** String formatting over data already in hand; no schedule access, no
  recomputation.
* **Total.** Every helper tolerates a partly-built value, because a stage that failed
  is exactly when its span matters most.
"""

from __future__ import annotations

from typing import Any


def _window(w: Any) -> str:
    start, end = getattr(w, "start_min", None), getattr(w, "end_min", None)
    if start is None and end is None:
        return "any time"
    lo = _hhmm(start) if start is not None else "open"
    hi = _hhmm(end) if end is not None else "close"
    return f"{lo}-{hi}"


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def constraints_out(c: Any) -> dict[str, Any]:
    """What extraction concluded, with its provenance.

    ``quoted`` is the part worth reading: it says which fields came from the patient's
    own words rather than from a default, which is the whole claim of FR-003.
    """
    if c is None:
        return {"error": "extraction produced nothing"}
    fields = {
        "dates": f"{c.date_range.value.start} to {c.date_range.value.end}",
        "time": _window(c.time_window.value),
        "urgency": c.urgency.value.value,
        "provider": c.provider_preference.value or "any",
        "appointment_type": c.appointment_type.value,
        "avoid_weekdays": sorted(c.exclusions.value.weekdays) or "none",
    }
    quoted = {
        name: getattr(c, attr).span.text
        for name, attr in (
            ("dates", "date_range"), ("time", "time_window"), ("urgency", "urgency"),
            ("provider", "provider_preference"), ("appointment_type", "appointment_type"),
            ("avoid_weekdays", "exclusions"),
        )
        if getattr(c, attr).span is not None
    }
    return {**fields, "quoted_from_the_request": quoted or "nothing quoted; all inferred"}


def constraints_in(c: Any) -> dict[str, Any]:
    """The reading handed to verification. Includes the raw text, because the
    verifier's job is to compare the two and a trace should show both sides."""
    if c is None:
        return {}
    return {
        "patient_said": c.request_text,
        "reading": {
            "dates": f"{c.date_range.value.start} to {c.date_range.value.end}",
            "time": _window(c.time_window.value),
            "urgency": c.urgency.value.value,
            "appointment_type": c.appointment_type.value,
        },
    }


def verdict_out(v: Any) -> dict[str, Any]:
    if v is None:
        return {"error": "verification produced nothing"}
    return {
        "outcome": v.outcome,
        "flags": [f.message for f in v.flags] or "none",
        "hypotheses": [h.label for h in v.hypotheses] or "none",
        "question": v.question.text if v.question else None,
    }


def reason_out(fan: Any) -> dict[str, Any]:
    """The funnel is the product's answer to "did it miss anything?", so it is the
    thing this span exists to show."""
    outcome = getattr(fan, "resolved", None)
    funnel = getattr(outcome, "funnel", None)
    if funnel is None:
        return {"error": "no candidates produced"}
    return {
        "funnel": {
            "grid_slots": funnel.grid_slots,
            "enumerated": funnel.enumerated,
            "feasible": funnel.feasible,
            "in_tier": funnel.in_tier,
            "offered": funnel.offered,
        },
        "top_rejections": [
            f"{g.count}x {g.reason.value}" for g in (getattr(outcome, "ledger", ()) or ())[:4]
        ],
        "diverged": getattr(fan, "diverged", False),
    }


def rationales_in(outcome: Any) -> dict[str, Any]:
    """The facts the explainer is allowed to use — and nothing else (FR-059).

    Showing them next to the sentences is what makes the faithfulness claim
    checkable by eye rather than only by the gate.
    """
    cards = [*getattr(outcome, "offers", ()), *getattr(outcome, "overflow", ())]
    return {
        "facts_available": [
            {
                "when": f"{c.rationale.facts.weekday} {c.rationale.facts.date_display} "
                        f"{c.rationale.facts.start_display}",
                "provider": c.rationale.facts.provider_name,
                "reasons": [a.text for a in c.rationale.components],
                "caveat": c.rationale.caveat.text if c.rationale.caveat else None,
            }
            for c in cards
        ]
    }


def sentences_out(outcome: Any, gate_fired: int) -> dict[str, Any]:
    """The sentences an operator will read, and where each came from.

    ``source`` is the interesting column: ``model`` means the gate accepted the
    rewrite, ``template`` means it rejected it and the deterministic sentence stands.
    A firing rate of zero forever means the gate is not running.
    """
    cards = [*getattr(outcome, "offers", ()), *getattr(outcome, "overflow", ())]
    return {
        "sentences": [
            {"text": c.reason, "source": "model" if c.llm_reason else "template"}
            for c in cards
        ],
        "gate_rejections": gate_fired,
    }
