"""The read-aloud lint -- the copy-defining requirement (FR-065).

*Every operator-facing sentence must be speakable, verbatim, to a patient on the
phone.* That is not a tone guideline. It decides the copy style for the whole
product, and it is what makes reading a reason aloud **reliable rather than lucky**
-- on every request, not just the ones that happen to phrase well.

One module, three callers: the faithfulness gate, the eval harness, and CI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.domain.rationale import FactSet

BANNED_PATH = Path(__file__).parent / "banned_tokens.json"

MAX_WORDS = 25
SECOND_PERSON = {"you", "your", "you're", "yours"}
# Both apostrophe characters are matched on purpose. Operators paste text out of Word
# and out of the practice-management system, which substitute the typographic form; a
# tokeniser that split on it would score the same sentence differently by provenance.
_WORD = re.compile(r"[A-Za-z0-9'’:\-]+")  # noqa: RUF001 - typographic apostrophe, deliberate
_SENTENCE_END = re.compile(r"[.!?]")
#: Titles carry a period that is not a sentence boundary. Provider names are the
#: single most common thing a reason line contains, so "Dr. Patel" must not read as
#: two sentences.
_ABBREVIATION = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Prof|St|Jr|Sr)\.")


def sentence_count(text: str) -> int:
    return len(_SENTENCE_END.findall(_ABBREVIATION.sub("", text)))
_PERCENT = re.compile(r"\d+\s?%")
_BARE_DECIMAL = re.compile(r"\b0\.\d+\b")


@dataclass(frozen=True, slots=True)
class LintResult:
    ok: bool
    violations: tuple[str, ...]

    def __bool__(self) -> bool:
        return self.ok


@lru_cache(maxsize=1)
def _banned() -> dict[str, list[str]]:
    data = json.loads(BANNED_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def check(text: str, facts: FactSet | None = None, *, refers_to_slot: bool = True) -> LintResult:
    """Returns every violation, not just the first -- a writer fixing copy wants the
    whole list, and a build log with one item at a time is a slow loop."""
    v: list[str] = []
    stripped = text.strip()

    if not stripped:
        return LintResult(False, ("empty sentence",))

    # 1. exactly one grammatical sentence
    n_sentences = sentence_count(stripped)
    if n_sentences != 1 or not _SENTENCE_END.search(stripped[-1]):
        v.append(
            f"must be exactly one sentence ending in terminal punctuation "
            f"(found {n_sentences})"
        )

    # 2. length
    n = len(words(stripped))
    if n > MAX_WORDS:
        v.append(f"{n} words, limit {MAX_WORDS}")

    # 3. second person
    lowered = {w.lower().strip("',.:") for w in words(stripped)}
    if not (lowered & SECOND_PERSON):
        v.append("not addressed to the patient in second person")

    # 4. no numbers that read as measurements
    if _PERCENT.search(stripped):
        v.append("contains a percentage")
    if _BARE_DECIMAL.search(stripped):
        v.append("contains a bare decimal score")

    # 5. jargon, axis names, hedges
    low = stripped.lower()
    banned = _banned()
    for token in banned["jargon"] + banned["axis_names"] + banned["hedges"]:
        if re.search(rf"\b{re.escape(token)}\b", low):
            v.append(f"jargon: {token!r}")

    # 6. internal identifiers
    for pattern in banned["identifier_patterns"]:
        for w in words(stripped):
            if re.search(pattern, w):
                v.append(f"internal identifier: {w!r}")
                break

    # 7. the resolved date and time must actually be present
    if refers_to_slot and facts is not None:
        if facts.weekday.lower() not in low:
            v.append(f"missing the resolved weekday ({facts.weekday})")
        if facts.date_display.lower() not in low:
            v.append(f"missing the resolved date ({facts.date_display})")
        if (
            facts.start_display.lower().rstrip("m") not in low.replace(" ", "")
            and facts.start_display.lower() not in low
        ):
            v.append(f"missing the resolved clock time ({facts.start_display})")

    return LintResult(not v, tuple(v))


def assert_clean(text: str, facts: FactSet | None = None, **kw: bool) -> None:
    result = check(text, facts, **kw)
    if not result.ok:
        raise AssertionError(f"read-aloud lint failed for {text!r}: {'; '.join(result.violations)}")
