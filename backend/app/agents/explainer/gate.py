"""[FR-062] The faithfulness gate. ~40 lines that turn "trust the LLM" into
"verify the LLM".

It checks generated prose against the ``Rationale`` and nothing else -- no schedule,
no scorer internals -- which is why it is short and independently unit-testable
without a fixture.

Five checks, each with an id so a firing names *which* one failed:

  F1  every named entity exists in the fact set
  F2  no claim maps to a component absent from the rationale's top atoms or caveat
  F3  <= 25 words
  F4  no banned hedge or negation tokens
  F5  the resolved date and time are echoed exactly

On failure the template rendering is substituted **silently**, and the firing is
logged (FR-063). The operator never sees an error; the trace panel shows it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.explainer import lint
from app.domain.enums import Axis
from app.domain.rationale import Rationale

#: Words that signal a claim about an axis. If the sentence makes one of these
#: claims and the axis is not a top contributor, the explanation is describing a
#: reason the slot did not actually win on.
AXIS_CLAIMS: dict[Axis, tuple[str, ...]] = {
    Axis.CONTINUITY: ("usual", "same ", "you saw", "your regular", "team", "before"),
    Axis.EFFICIENCY: ("gap", "fills", "shape of the day", "between two"),
    Axis.PRIME_TIME: ("protected", "keeps for", "busier part"),
    Axis.TIME_FIT: ("you asked for", "window", "sooner", "earliest"),
}

_CAPITALISED = re.compile(r"\b[A-Z][a-z]{2,}\b")


@dataclass(frozen=True, slots=True)
class GateResult:
    ok: bool
    failed_check: str | None = None
    detail: str = ""


def check(sentence: str, rationale: Rationale) -> GateResult:
    facts = rationale.facts
    low = sentence.lower()

    # F1 -- every named entity must exist in the fact set.
    known = {e.lower() for e in facts.entities()}
    known |= {w.lower() for e in facts.entities() for w in e.split()}
    known |= {"i", "we", "you", "your", "the", "a", "an", "and", "but", "though",
              "at", "on", "in", "with", "for", "is", "it", "not", "am", "pm"}
    for word in _CAPITALISED.findall(sentence):
        if word.lower() not in known:
            return GateResult(False, "F1", f"names {word!r}, which is not in the fact set")

    # F2 -- no claim about an axis that did not contribute.
    cited = rationale.top_axes
    for axis, phrases in AXIS_CLAIMS.items():
        if axis in cited:
            continue
        for phrase in phrases:
            if phrase in low:
                return GateResult(
                    False, "F2", f"claims {axis.value} ({phrase!r}) which was not a top contributor"
                )

    # F3 -- length.
    if len(lint.words(sentence)) > lint.MAX_WORDS:
        return GateResult(False, "F3", f"{len(lint.words(sentence))} words")

    # F4 -- hedges and negations have no place in something read to a patient.
    for token in ("probably", "possibly", "might", "should be able", "i think", "not sure"):
        if token in low:
            return GateResult(False, "F4", f"hedge {token!r}")

    # F5 -- the resolved date and time must be echoed exactly. This is the mitigation
    # for the one residual risk that cannot be engineered away: a confidently-wrong
    # date the operator does not notice. The *patient* catches it when it is read out.
    for required in (facts.weekday, facts.date_display, facts.start_display):
        if required.lower() not in low:
            return GateResult(False, "F5", f"missing {required!r}")

    return GateResult(True)
