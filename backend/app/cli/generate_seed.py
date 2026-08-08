"""Offline seed generator. NEVER invoked by boot (FR-103).

Generate with a seeded script, hand-author the scenario appointments on top, commit
the result. Regenerated data changes between runs, which means the behaviour observed
in testing is not the behaviour observed later -- and every relative-date test and
every golden label silently rots.

The eleven edge cases (PRD §8) are placed **deliberately**, after the seeded fill,
because each one exists to exercise a specific requirement against realistic
contention rather than a synthetic unit fixture.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.data.digest import write_digest

RNG_SEED = 20260810

LOCATION_ID = "loc-1"
TZ = "America/Los_Angeles"

HISTORY = (date(2026, 8, 3), date(2026, 8, 7))
BOOKABLE = (date(2026, 8, 10), date(2026, 8, 21))
TAIL = (date(2026, 8, 24), date(2026, 8, 28))

OPEN_MIN, CLOSE_MIN = 8 * 60, 17 * 60  # Mon-Thu
FRI_CLOSE_MIN = 14 * 60
LUNCH = (12 * 60, 13 * 60)

# Deliberately seeded anchors -- see PRD §8 "edge cases -> requirement traceability"
THU_NEAR = date(2026, 8, 13)  # doctor-check starvation + Sarah on PTO
THU_FAR = date(2026, 8, 20)   # Sarah back, hygiene rooms booked solid
TUE_FULL = date(2026, 8, 11)  # urgent with nothing open
WED_GAPS = date(2026, 8, 12)  # orphan gap (OP-3) and fragmenting trap (OP-4)
FRI_SPARSE = date(2026, 8, 14)
DIRTY_DAY = date(2026, 8, 5)  # one malformed record, in the history week


# ---------------------------------------------------------------- entities --
def business_hours() -> list[dict[str, int]]:
    hours = [{"weekday": wd, "open_min": OPEN_MIN, "close_min": CLOSE_MIN} for wd in range(4)]
    hours.append({"weekday": 4, "open_min": OPEN_MIN, "close_min": FRI_CLOSE_MIN})
    return hours


OPERATORIES: list[dict[str, Any]] = [
    {"id": "OP-1", "name": "Op 1", "location_id": LOCATION_ID,
     "equipment_tags": [], "preferred_use": "hygiene"},
    {"id": "OP-2", "name": "Op 2", "location_id": LOCATION_ID,
     "equipment_tags": [], "preferred_use": "hygiene"},
    {"id": "OP-3", "name": "Op 3", "location_id": LOCATION_ID,
     "equipment_tags": [], "preferred_use": "restorative"},
    {"id": "OP-4", "name": "Op 4", "location_id": LOCATION_ID,
     "equipment_tags": [], "preferred_use": "restorative"},
    {"id": "OP-5", "name": "Op 5", "location_id": LOCATION_ID,
     "equipment_tags": ["surgical"], "preferred_use": "surgical"},
    {"id": "OP-6", "name": "Op 6", "location_id": LOCATION_ID,
     "equipment_tags": ["cerec", "pano"], "preferred_use": "restorative"},
]

# "Sarah" and "Dr. Patel" are fixed by the reference scenarios; the rest are
# illustrative [A-16b].
PROVIDERS: list[dict[str, Any]] = [
    {"id": "prov-patel", "name": "Dr. Patel", "role": "DDS",
     "credentials": ["DDS", "restorative", "endo"], "pod": "A"},
    {"id": "prov-reyes", "name": "Dr. Reyes", "role": "DDS",
     "credentials": ["DDS", "restorative"], "pod": "B"},
    {"id": "prov-okafor", "name": "Dr. Okafor", "role": "DDS",
     "credentials": ["DDS", "oral_surgery"], "pod": "S"},
    {"id": "prov-sarah", "name": "Sarah", "role": "RDH", "credentials": ["RDH"], "pod": "A"},
    {"id": "prov-nia", "name": "Nia", "role": "RDH", "credentials": ["RDH"], "pod": "A"},
    {"id": "prov-maya", "name": "Maya", "role": "RDH", "credentials": ["RDH"], "pod": "B"},
    {"id": "prov-jo", "name": "Jo", "role": "RDH", "credentials": ["RDH"], "pod": "B"},
    {"id": "prov-dana", "name": "Dana", "role": "DA", "credentials": ["DA"], "pod": "A"},
    {"id": "prov-chris", "name": "Chris", "role": "DA", "credentials": ["DA"], "pod": "B"},
]

TYPES: list[dict[str, Any]] = [
    {"id": "prophy_adult", "name": "Cleaning", "duration_min": 60, "requires_doctor_check": True,
     "required_credentials": ["RDH"], "production_value": 120, "continuity_multiplier": 1.0},
    {"id": "prophy_child", "name": "Child cleaning", "duration_min": 40,
     "requires_doctor_check": True, "required_credentials": ["RDH"],
     "production_value": 95, "continuity_multiplier": 1.0},
    {"id": "perio_maint", "name": "Gum maintenance", "duration_min": 60,
     "requires_doctor_check": True, "required_credentials": ["RDH"],
     "production_value": 180, "continuity_multiplier": 1.0},
    {"id": "np_exam_fmx", "name": "New patient exam", "duration_min": 90,
     "required_credentials": ["DDS"], "required_equipment": ["pano"],
     "production_value": 320, "continuity_multiplier": 1.0},
    {"id": "limited_exam", "name": "Emergency exam", "duration_min": 30,
     "required_credentials": ["DDS"], "production_value": 110,
     "default_urgency": "urgent", "continuity_multiplier": 0.5},
    {"id": "filling_1s", "name": "Filling", "duration_min": 40,
     "required_credentials": ["restorative"], "production_value": 240,
     "continuity_multiplier": 1.0},
    {"id": "filling_2s", "name": "Two-surface filling", "duration_min": 60,
     "required_credentials": ["restorative"], "production_value": 330,
     "continuity_multiplier": 1.0},
    {"id": "crown_prep", "name": "Crown preparation", "duration_min": 90,
     "required_credentials": ["restorative"], "production_value": 1250,
     "prime_time_protected": True, "continuity_multiplier": 1.5},
    {"id": "crown_seat", "name": "Crown fitting", "duration_min": 45,
     "required_credentials": ["restorative"], "production_value": 400,
     "continuity_multiplier": 2.0},
    {"id": "extraction", "name": "Extraction", "duration_min": 45,
     "required_credentials": ["oral_surgery"], "required_equipment": ["surgical"],
     "production_value": 420, "continuity_multiplier": 1.0},
    {"id": "rct", "name": "Root canal", "duration_min": 90,
     "required_credentials": ["endo"], "production_value": 1100,
     "prime_time_protected": True, "continuity_multiplier": 1.5},
    {"id": "denture_adjust", "name": "Denture adjustment", "duration_min": 20,
     "required_credentials": ["DDS"], "production_value": 80, "continuity_multiplier": 1.0},
]

FIRST = ["Ana", "Ben", "Cara", "Dev", "Elle", "Femi", "Gus", "Hana", "Ivan", "Jess",
         "Kai", "Lena", "Mo", "Nora", "Omar", "Pia", "Quinn", "Rosa", "Sam", "Tess",
         "Uma", "Vik", "Wren", "Xan", "Yara", "Zed"]
LAST = ["Alvarez", "Brooks", "Chen", "Duarte", "Ellis", "Farooq", "Grant", "Haddad",
        "Ibarra", "Jensen", "Kowal", "Lind", "Moreau", "Nkemi", "Ortiz", "Park"]

BLOCKS: list[dict[str, Any]] = [
    {"id": "blk-lunch", "scope": "global", "kind": "lunch",
     "start_min": LUNCH[0], "end_min": LUNCH[1], "weekdays": [0, 1, 2, 3, 4]},
    # Faithful to [A-19]: the huddle sits *before* open, so it constrains nothing.
    # Kept because the practice's day really does start that way.
    {"id": "blk-huddle", "scope": "global", "kind": "huddle",
     "start_min": 7 * 60 + 50, "end_min": OPEN_MIN, "weekdays": [0, 1, 2, 3, 4]},
    {"id": "blk-prime-op3", "scope": "operatory", "scope_ref": "OP-3",
     "kind": "restorative_block", "start_min": OPEN_MIN, "end_min": 11 * 60,
     "weekdays": [0, 1, 2, 3], "min_production_value": 300},
    {"id": "blk-prime-op4", "scope": "operatory", "scope_ref": "OP-4",
     "kind": "restorative_block", "start_min": OPEN_MIN, "end_min": 11 * 60,
     "weekdays": [0, 1, 2, 3], "min_production_value": 300},
    {"id": "blk-pedo-op2", "scope": "operatory", "scope_ref": "OP-2",
     "kind": "pedo_after_school", "start_min": 15 * 60, "end_min": CLOSE_MIN,
     "weekdays": [0, 1, 2, 3]},
    # Real practices reserve these. Invisible to routine requests; unlockable only
    # at urgency >= urgent (FR-026, FR-036).
    {"id": "blk-hold-am", "scope": "operatory", "scope_ref": "OP-1",
     "kind": "emergency_hold", "start_min": 11 * 60, "end_min": 11 * 60 + 30,
     "weekdays": [0, 1, 2, 3, 4], "unlock_min_urgency": "urgent"},
    {"id": "blk-hold-pm", "scope": "operatory", "scope_ref": "OP-3",
     "kind": "emergency_hold", "start_min": 16 * 60, "end_min": 16 * 60 + 30,
     "weekdays": [0, 1, 2, 3, 4], "unlock_min_urgency": "urgent"},
]


# ------------------------------------------------------------------ helpers --
def business_days(a: date, b: date) -> list[date]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def close_for(d: date) -> int:
    return FRI_CLOSE_MIN if d.weekday() == 4 else CLOSE_MIN


def iso(d: date, minute: int) -> str:
    """Local wall clock -> offset-aware ISO. No DST boundary in the seed window
    [A-18], and NFR-32's conversion module owns the general case."""
    return f"{d.isoformat()}T{minute // 60:02d}:{minute % 60:02d}:00-07:00"


@dataclass
class Busy:
    """Occupancy while generating. Prevents the generator from emitting the very
    overlaps the loader would have to quarantine."""

    by_operatory: dict[tuple[str, date], list[tuple[int, int]]]
    by_provider: dict[tuple[str, date], list[tuple[int, int]]]

    @classmethod
    def empty(cls) -> Busy:
        return cls({}, {})

    def free(self, key: tuple[str, date], lo: int, hi: int, table: str) -> bool:
        spans = (self.by_operatory if table == "op" else self.by_provider).get(key, [])
        return all(hi <= s or e <= lo for s, e in spans)

    def take(self, op: str, prov: str, d: date, lo: int, hi: int) -> None:
        self.by_operatory.setdefault((op, d), []).append((lo, hi))
        self.by_provider.setdefault((prov, d), []).append((lo, hi))


def type_providers(type_id: str) -> list[str]:
    t = next(x for x in TYPES if x["id"] == type_id)
    need = set(t.get("required_credentials", []))
    return [p["id"] for p in PROVIDERS if need.issubset(set(p["credentials"]))]


def type_operatories(type_id: str) -> list[str]:
    t = next(x for x in TYPES if x["id"] == type_id)
    need = set(t.get("required_equipment", []))
    return [o["id"] for o in OPERATORIES if need.issubset(set(o["equipment_tags"]))]


def duration(type_id: str) -> int:
    return int(next(x for x in TYPES if x["id"] == type_id)["duration_min"])


HYGIENE = ["prophy_adult", "prophy_child", "perio_maint"]
RESTORATIVE = ["filling_1s", "filling_2s", "crown_prep", "crown_seat", "rct", "denture_adjust"]


def preferred_types(op_id: str) -> list[str]:
    """Room preference, not room restriction.

    Only two providers hold the `restorative` credential, so confining three rooms to
    restorative work makes the practice provider-bound and the schedule unrealistically
    empty -- and an empty schedule is the one thing that makes this product look easy.
    Real practices flex rooms, so restorative rooms take hygiene overflow.
    """
    if op_id in ("OP-1", "OP-2"):
        return HYGIENE
    if op_id == "OP-5":
        return ["extraction", "limited_exam"]
    if op_id == "OP-6":
        return ["np_exam_fmx", *RESTORATIVE, *HYGIENE]
    return [*RESTORATIVE, *HYGIENE]


def make_patients(rng: random.Random) -> list[dict[str, Any]]:
    """~120 obviously-fictional patients. One is a chronic no-show (edge case 10):
    the fairness lever exists, is explicit, and is off by default [R-09]."""
    out: list[dict[str, Any]] = []
    dentists = [p["id"] for p in PROVIDERS if p["role"] == "DDS" and p["id"] != "prov-okafor"]
    hygienists = [p["id"] for p in PROVIDERS if p["role"] == "RDH"]
    for i in range(120):
        band = "child" if i % 7 == 0 else ("senior" if i % 11 == 0 else "adult")
        out.append({
            "id": f"pat-{i:03d}",
            "name": f"{FIRST[i % len(FIRST)]} {LAST[(i // 3) % len(LAST)]}",
            "age_band": band,
            "assigned_dentist_id": dentists[i % len(dentists)],
            "assigned_hygienist_id": hygienists[i % len(hygienists)],
            "last_seen_by_type": {},
            "no_show_count": 0,
        })
    # Edge case 10 -- chronic no-show, used to demonstrate the flagged-off policy hook.
    out[42]["no_show_count"] = 5
    # The reference scenarios need one patient whose hygienist is Sarah and whose
    # dentist is Dr. Patel, so continuity and the PTO tradeoff both bite.
    out[0].update({"name": "Ana Alvarez", "assigned_hygienist_id": "prov-sarah",
                   "assigned_dentist_id": "prov-patel", "age_band": "adult"})
    return out


def _free_windows(d: date, op_id: str) -> list[tuple[int, int]]:
    """Bookable stretches, with lunch and this operatory's emergency hold removed.

    Holds are carved out of the *generated* schedule so they stay genuinely empty --
    a hold that already has an appointment in it cannot be released (FR-036).
    """
    windows = [(OPEN_MIN, LUNCH[0]), (LUNCH[1], close_for(d))]
    for b in BLOCKS:
        if b["kind"] != "emergency_hold" or b.get("scope_ref") != op_id:
            continue
        if d.weekday() not in b["weekdays"]:
            continue
        cut: list[tuple[int, int]] = []
        for lo, hi in windows:
            if b["end_min"] <= lo or hi <= b["start_min"]:
                cut.append((lo, hi))
                continue
            if lo < b["start_min"]:
                cut.append((lo, b["start_min"]))
            if b["end_min"] < hi:
                cut.append((b["end_min"], hi))
        windows = cut
    return [(lo, hi) for lo, hi in windows if hi - lo >= 20]


def generate_fill(rng: random.Random, busy: Busy) -> list[dict[str, Any]]:
    """Seeded greedy packer.

    Occupancy is the design parameter that matters. Too empty and every request has a
    trivially easy answer -- nothing is ever rejected and the ranking has nothing to
    express. Too full and everything is a rejection.
    """
    appts: list[dict[str, Any]] = []
    n = 0

    # These are *placement* probabilities, not the resulting occupancy. Turnover
    # (10 min after every appointment) means even a perfectly packed operatory tops
    # out near 86% booked minutes, so the numbers here run higher than the occupancy
    # band they produce. The test in tests/requirements asserts the *outcome*.
    def target(d: date) -> float:
        if d <= HISTORY[1]:
            return 0.72
        if d <= BOOKABLE[1]:
            if d == TUE_FULL:
                return 0.995         # edge case 5 -- urgent with nothing open
            if d == FRI_SPARSE:
                return 0.34          # one visibly sparse day: "later is easier" must be real
            return 0.93
        return 0.34                   # tail, mostly beyond the horizon

    for d in business_days(HISTORY[0], TAIL[1]):
        occ = target(d)
        for op in OPERATORIES:
            for lo, hi in _free_windows(d, op["id"]):
                cursor = lo
                while cursor < hi - 20:
                    if rng.random() > occ:
                        cursor += rng.choice((10, 20))
                        continue
                    placed = False
                    wanted = preferred_types(op["id"])
                    for type_id in rng.sample(wanted, k=len(wanted)):
                        if op["id"] not in type_operatories(type_id):
                            continue
                        dur = duration(type_id)
                        if cursor + dur > hi:
                            continue
                        provs = type_providers(type_id)
                        rng.shuffle(provs)
                        for prov in provs:
                            if not busy.free((op["id"], d), cursor, cursor + dur, "op"):
                                continue
                            if not busy.free((prov, d), cursor, cursor + dur, "prov"):
                                continue
                            busy.take(op["id"], prov, d, cursor, cursor + dur)
                            appts.append({
                                "id": f"appt-{n:05d}",
                                "start": iso(d, cursor),
                                "duration_min": dur,
                                "patient_id": f"pat-{rng.randrange(120):03d}",
                                "provider_id": prov,
                                "operatory_id": op["id"],
                                "type_id": type_id,
                                "status": "completed" if d <= HISTORY[1] else "scheduled",
                            })
                            n += 1
                            cursor += dur + 10  # turnover [A-08]
                            placed = True
                            break
                        if placed:
                            break
                    if not placed:
                        cursor += 10
    return appts


def _clear(appts: list[dict[str, Any]], d: date, op: str, lo: int, hi: int) -> None:
    keep = []
    for a in appts:
        if a["operatory_id"] != op or not a["start"].startswith(d.isoformat()):
            keep.append(a)
            continue
        s = int(a["start"][11:13]) * 60 + int(a["start"][14:16])
        if s + a["duration_min"] <= lo or hi <= s:
            keep.append(a)
    appts[:] = keep


def _clear_provider(appts: list[dict[str, Any]], busy: Busy, d: date, prov: str,
                    lo: int, hi: int) -> None:
    """Evict generated work that would clash with a hand-authored placement.

    Scenario appointments win: they exist to make a specific requirement reachable,
    and a generated filling is fungible. Clearing by room alone leaves the provider
    double-booked across rooms -- which the loader then quarantines, so the seeded
    case silently loses appointments.
    """
    keep = []
    for a in appts:
        if a["provider_id"] != prov or not a["start"].startswith(d.isoformat()):
            keep.append(a)
            continue
        s0 = int(a["start"][11:13]) * 60 + int(a["start"][14:16])
        if s0 + a["duration_min"] <= lo or hi <= s0:
            keep.append(a)
    appts[:] = keep
    busy.by_provider[(prov, d)] = [
        (s0, e0) for s0, e0 in busy.by_provider.get((prov, d), []) if e0 <= lo or hi <= s0
    ]


def _place(appts: list[dict[str, Any]], busy: Busy, d: date, op: str, prov: str,
           type_id: str, start: int, tag: str) -> None:
    dur = duration(type_id)
    _clear_provider(appts, busy, d, prov, start, start + dur)
    busy.take(op, prov, d, start, start + dur)
    appts.append({
        "id": f"appt-{tag}",
        "start": iso(d, start),
        "duration_min": dur,
        "patient_id": f"pat-{(start + len(tag)) % 120:03d}",
        "provider_id": prov,
        "operatory_id": op,
        "type_id": type_id,
        "status": "scheduled",
    })


def apply_scenarios(appts: list[dict[str, Any]], busy: Busy) -> list[str]:
    """The eleven deliberately seeded cases. Each is placed to exercise a named
    requirement against realistic contention."""
    notes: list[str] = []

    # 1 + 11a. Thu 13 Aug PM: three hygiene rooms wide open, every dentist wall-to-wall.
    #          A slot that looks free on the grid is structurally un-bookable, and only
    #          the ledger can say so (FR-023, FR-027, FR-030).
    for op in ("OP-1", "OP-2", "OP-6"):
        _clear(appts, THU_NEAR, op, 13 * 60, CLOSE_MIN)
    # Each dentist gets a run of work they are actually credentialed for, packed
    # contiguously so no gap is wide enough to host a 10-minute exam. Dr. Okafor is
    # an oral surgeon, so "back-to-back crowns" is not a thing he can be doing --
    # he gets extractions and limited exams instead.
    dentist_runs = {
        "prov-patel": ("OP-3", ("crown_prep", "crown_seat", "filling_2s", "filling_1s")),
        "prov-reyes": ("OP-4", ("crown_prep", "crown_seat", "filling_2s", "filling_1s")),
        "prov-okafor": ("OP-5", ("extraction",) * 4 + ("limited_exam",) * 2),
    }
    for i, (prov, (op, run)) in enumerate(dentist_runs.items()):
        _clear(appts, THU_NEAR, op, 13 * 60, CLOSE_MIN)
        busy.by_provider[(prov, THU_NEAR)] = [
            (lo, hi) for lo, hi in busy.by_provider.get((prov, THU_NEAR), []) if hi <= 13 * 60
        ]
        cursor = 13 * 60
        for j, type_id in enumerate(run):
            dur = duration(type_id)
            if cursor + dur > CLOSE_MIN:
                break
            _place(appts, busy, THU_NEAR, op, prov, type_id, cursor, f"ec1-{i}-{j}")
            cursor += dur  # contiguous: the whole point is that no exam window exists
    notes.append(
        "1  doctor-check starvation seeded Thu 2026-08-13 PM (OP-1/2/6 open, dentists full)"
    )

    # 2. Sarah on PTO Wed-Fri, forcing the continuity-vs-timing tradeoff and producing
    #    a genuine counterfactual rather than a contrived one.
    pto_days = {date(2026, 8, 12), date(2026, 8, 13), date(2026, 8, 14)}
    appts[:] = [
        a for a in appts
        if not (
            a["provider_id"] == "prov-sarah"
            and date.fromisoformat(a["start"][:10]) in pto_days
        )
    ]
    notes.append("2  Sarah PTO Wed-Fri 2026-08-12..14")

    # 3. The orphan gap: a 50-minute hole that fits a 40-minute filling plus its
    #    10-minute turnover *exactly*. The efficiency axis's positive case -- a
    #    booking that creates zero orphan minutes.
    #    (PRD [spec-refinement]: the product direction called this a 45-minute hole;
    #     with the 10-minute turnover of FR-018 the arithmetic needs 50, or the hero
    #     case never fires.)
    _clear(appts, WED_GAPS, "OP-3", 9 * 60, LUNCH[0])
    _place(appts, busy, WED_GAPS, "OP-3", "prov-patel", "crown_prep", 9 * 60, "ec3-a")
    _place(appts, busy, WED_GAPS, "OP-3", "prov-reyes", "filling_1s", 11 * 60 + 20, "ec3-b")
    notes.append("3  orphan gap Wed 2026-08-12 OP-3 10:30-11:20 (exactly 40+10)")

    # 4. The fragmenting trap: a 90-minute open stretch where booking 30 minutes in
    #    the middle creates two dead 30-minute orphans. The scorer must push the
    #    booking to the *edge* of the stretch, and the reason line must say so.
    _clear(appts, WED_GAPS, "OP-4", 13 * 60, 15 * 60 + 10)
    _place(appts, busy, WED_GAPS, "OP-4", "prov-reyes", "filling_1s", 14 * 60 + 30, "ec4-a")
    notes.append("4  fragmenting trap Wed 2026-08-12 OP-4 13:00-14:30 open (exactly 90)")

    # 5. Urgent with nothing open. Hand-saturated rather than left to the packer:
    #    the packer is provider-bound (two dentists hold the `restorative` credential
    #    across three restorative rooms), so it plateaus well below full. The product
    #    must never answer a patient in pain with an empty list, and that path only
    #    gets exercised if the day is genuinely full.
    # Clear the day in both the appointment list *and* the occupancy map. Clearing
    # only the former leaves every provider looking busy, so nothing can be re-placed.
    appts[:] = [a for a in appts if not a["start"].startswith(TUE_FULL.isoformat())]
    for table in (busy.by_operatory, busy.by_provider):
        for key in list(table):
            if key[1] == TUE_FULL:
                table[key] = []
    for op in OPERATORIES:
        for lo, hi in _free_windows(TUE_FULL, op["id"]):
            cursor = lo
            while cursor < hi:
                placed = False
                for type_id in preferred_types(op["id"]):
                    dur = duration(type_id)
                    if cursor + dur > hi or op["id"] not in type_operatories(type_id):
                        continue
                    for prov in type_providers(type_id):
                        if busy.free((prov, TUE_FULL), cursor, cursor + dur, "prov"):
                            _place(appts, busy, TUE_FULL, op["id"], prov, type_id, cursor,
                                   f"ec5-{op['id']}-{cursor}")
                            cursor += dur
                            placed = True
                            break
                    if placed:
                        break
                if not placed:
                    cursor += 10
    notes.append("5  Tue 2026-08-11 hand-saturated -- empty-tier escalation path")

    # 8. Extraction fits only the surgical-capable room, which is also the busiest --
    #    the multi-resource constraint is not just provider + chair; equipment is a
    #    third axis of scarcity.
    dur_ext = duration("extraction")
    for d in business_days(BOOKABLE[0], BOOKABLE[1]):
        if d == FRI_SPARSE:
            continue
        for lo in (8 * 60, 9 * 60, 10 * 60, 13 * 60, 14 * 60, 15 * 60):
            if lo + dur_ext > close_for(d):
                continue  # Friday closes at 14:00; do not generate what we would quarantine
            if lo < LUNCH[1] and LUNCH[0] < lo + dur_ext:
                continue
            if busy.free(("OP-5", d), lo, lo + dur_ext, "op") and busy.free(
                ("prov-okafor", d), lo, lo + dur_ext, "prov"
            ):
                _place(appts, busy, d, "OP-5", "prov-okafor", "extraction", lo, f"ec8-{d}-{lo}")
    notes.append("8  OP-5 (surgical) saturated across the bookable fortnight")

    # 11b. The far Thursday: Sarah is back, but both hygiene rooms are booked solid,
    #      so the two readings of "next Thursday" produce materially different offers.
    for op in ("OP-1", "OP-2"):
        _clear(appts, THU_FAR, op, 13 * 60, CLOSE_MIN)
        cursor = 13 * 60
        for prov in ("prov-nia", "prov-maya", "prov-jo", "prov-sarah"):
            if cursor + 60 > CLOSE_MIN:
                break
            if busy.free((prov, THU_FAR), cursor, cursor + 60, "prov"):
                _place(
                    appts, busy, THU_FAR, op, prov, "prophy_adult", cursor,
                    f"ec11-{op}-{cursor}",
                )
                cursor += 60
    notes.append("11 far Thursday 2026-08-20 PM: hygiene rooms booked solid, Sarah back")

    # 9. One deliberately dirty record -- an appointment overlapping the lunch block.
    #    Real practice-management exports contain dirty data; the loader must
    #    quarantine and report rather than crash or silently ingest.
    appts.append({
        "id": "appt-dirty-01",
        "start": iso(DIRTY_DAY, LUNCH[0] - 20),
        "duration_min": 60,
        "patient_id": "pat-007",
        "provider_id": "prov-reyes",
        "operatory_id": "OP-4",
        "type_id": "filling_2s",
        "status": "completed",
    })
    notes.append("9  one malformed record (overlaps lunch) Wed 2026-08-05 -- expect quarantine")
    return notes


def _spans(appts: list[dict[str, Any]], d: date, *, op: str | None = None,
           prov: str | None = None) -> list[tuple[int, int]]:
    out = []
    for a in appts:
        if not a["start"].startswith(d.isoformat()):
            continue
        if op is not None and a["operatory_id"] != op:
            continue
        if prov is not None and a["provider_id"] != prov:
            continue
        s = int(a["start"][11:13]) * 60 + int(a["start"][14:16])
        out.append((s, s + a["duration_min"]))
    return sorted(out)


def _gaps(spans: list[tuple[int, int]], lo: int, hi: int) -> list[int]:
    gaps, cursor = [], lo
    for s, e in spans:
        if s > cursor:
            gaps.append(s - cursor)
        cursor = max(cursor, e)
    if cursor < hi:
        gaps.append(hi - cursor)
    return gaps


def verify(appts: list[dict[str, Any]]) -> list[tuple[str, bool, str]]:
    """Assert the seeded cases actually hold.

    Without this, a change to the packer silently guts an edge case and the failure
    surfaces as "the demo didn't do the thing" rather than as a red build.
    """
    checks: list[tuple[str, bool, str]] = []

    # 1. Hygiene rooms open *in the afternoon* -- they are normally busy in the
    #    morning, and demanding an empty day would be checking the wrong thing.
    pm_open = all(
        not [x for x in _spans(appts, THU_NEAR, op=o) if x[1] > 13 * 60]
        for o in ("OP-1", "OP-2", "OP-6")
    )
    # default=0, not 999: an empty gap list means the dentist is packed solid, which
    # is precisely the condition this case needs.
    worst = max(
        max(_gaps(_spans(appts, THU_NEAR, prov=p), 13 * 60, CLOSE_MIN), default=0)
        for p in ("prov-patel", "prov-reyes", "prov-okafor")
    )
    checks.append((
        "1  doctor-check starvation (Thu 13 Aug PM)",
        pm_open and worst < 10,
        f"hygiene rooms clear={pm_open}, largest dentist gap={worst}min (needs <10)",
    ))

    # 3. A hole of exactly 50 minutes: 40-minute filling plus its turnover.
    g3 = _gaps(_spans(appts, WED_GAPS, op="OP-3"), OPEN_MIN, LUNCH[0])
    checks.append(("3  orphan gap == 50min (Wed 12 Aug OP-3)", 50 in g3, f"gaps={g3}"))

    # 4. A 90-minute stretch, so a 30-minute booking in the middle makes two orphans.
    g4 = _gaps(_spans(appts, WED_GAPS, op="OP-4"), 13 * 60, 15 * 60 + 10)
    checks.append(("4  fragmenting stretch == 90min (Wed 12 Aug OP-4)", 90 in g4, f"gaps={g4}"))

    # 5. Urgent with nothing open.
    busy_tue = sum(e - s for s, e in _spans(appts, TUE_FULL))
    # Emergency holds carve 60 minutes out of the day that cannot be filled by design
    # (that is what makes them releasable), so full is not 100%.
    cap_tue = (CLOSE_MIN - OPEN_MIN - 60) * 6 - 60
    checks.append((
        "5  Tue 11 Aug near-full", busy_tue / cap_tue >= 0.85,
        f"{busy_tue / cap_tue:.0%} of fillable minutes",
    ))

    # 9. Exactly one deliberately dirty record.
    dirty = [a for a in appts if a["id"] == "appt-dirty-01"]
    checks.append(("9  one dirty record present", len(dirty) == 1, f"found {len(dirty)}"))

    # 11. The two Thursdays must differ, or the fan-out demo has nothing to show.
    near = sum(e - s for s, e in _spans(appts, THU_NEAR, op="OP-1"))
    far = sum(e - s for s, e in _spans(appts, THU_FAR, op="OP-1"))
    checks.append((
        "11 the two Thursdays differ in shape", abs(near - far) > 60,
        f"OP-1 booked: near={near}min far={far}min",
    ))
    return checks


def derive_last_seen(patients: list[dict[str, Any]], appts: list[dict[str, Any]]) -> None:
    """Continuity needs history. Derived from the completed week rather than invented,
    so 'your usual hygienist' means something checkable."""
    for a in sorted(appts, key=lambda x: x["start"]):
        if a["status"] != "completed" or not a["patient_id"]:
            continue
        p = next((x for x in patients if x["id"] == a["patient_id"]), None)
        if p is not None:
            p["last_seen_by_type"][a["type_id"]] = {
                "provider_id": a["provider_id"],
                "on": a["start"][:10],
            }


def main() -> int:
    settings = get_settings()
    seed_dir: Path = settings.seed_dir
    seed_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(RNG_SEED)

    providers = [dict(p) for p in PROVIDERS]
    for p in providers:
        p["working_hours"] = business_hours()
        p["pto"] = []
    next(p for p in providers if p["id"] == "prov-sarah")["pto"] = [
        {"start": "2026-08-12", "end": "2026-08-14"}
    ]

    patients = make_patients(rng)
    busy = Busy.empty()
    appts = generate_fill(rng, busy)
    notes = apply_scenarios(appts, busy)
    appts.sort(key=lambda a: (a["start"], a["operatory_id"]))
    derive_last_seen(patients, appts)

    payload = {
        "locations.json": [{
            "id": LOCATION_ID, "name": "Riverbend Dental", "timezone": TZ,
            "business_hours": business_hours(),
        }],
        "operatories.json": OPERATORIES,
        "providers.json": providers,
        "appointment_types.json": TYPES,
        "patients.json": patients,
        "appointments.json": appts,
        "blocks.json": BLOCKS,
    }
    for name, obj in payload.items():
        (seed_dir / name).write_text(
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    digest = write_digest(seed_dir)
    lo, hi = BOOKABLE[0].isoformat(), BOOKABLE[1].isoformat()
    bookable = [a for a in appts if lo <= a["start"][:10] <= hi]
    print(f"  seed written to {seed_dir}")
    print(f"  {len(appts)} appointments  ({len(bookable)} in the bookable fortnight)")
    print(f"  digest {digest[:16]}")
    print("  seeded edge cases:")
    for n in notes:
        print(f"    - {n}")

    print("  verification:")
    checks = verify(appts)
    for name, ok, detail in checks:
        print(f"    [{'ok' if ok else 'FAIL'}] {name:<44} {detail}")
    failed = [c for c in checks if not c[1]]
    if failed:
        print(f"\n  {len(failed)} seeded case(s) did not survive generation.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
