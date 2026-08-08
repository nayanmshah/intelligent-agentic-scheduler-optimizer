"""Two phases, two failure modes -- and the asymmetry is the point.

**Schema violation fails the boot, loudly, naming file, record and field.** A
silently-degraded dataset is worse than no boot: every number downstream would be
computed against data nobody knows is wrong.

**Semantic anomaly quarantines and reports.** Real practice-management exports
contain dirty records -- an appointment overlapping lunch, a double-booked chair.
Refusing to start is the wrong response to reality; ingesting it silently is worse.
So the record is excluded from the index and *named* in pre-flight (edge case 9).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.data.timezone import to_local, zone
from app.domain.entities import (
    Appointment,
    AppointmentType,
    Location,
    Operatory,
    Patient,
    Provider,
    ScheduleBlock,
    SeedBundle,
)


class SeedSchemaError(RuntimeError):
    """Boot-stopping. Names the file, the record and the field."""


@dataclass
class Anomaly:
    record_id: str
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.record_id}: {self.kind} -- {self.detail}"


@dataclass
class LoadResult:
    bundle: SeedBundle
    quarantined: list[Anomaly] = field(default_factory=list)

    @property
    def summary(self) -> str:
        n = len(self.quarantined)
        return "no anomalies" if n == 0 else f"{n} anomaly quarantined" if n == 1 else \
            f"{n} anomalies quarantined"


_FILES = {
    "locations": ("locations.json", Location),
    "operatories": ("operatories.json", Operatory),
    "providers": ("providers.json", Provider),
    "appointment_types": ("appointment_types.json", AppointmentType),
    "patients": ("patients.json", Patient),
    "appointments": ("appointments.json", Appointment),
    "blocks": ("blocks.json", ScheduleBlock),
}


def _phase1(seed_dir: Path) -> dict[str, list[Any]]:
    """Schema validation. Any failure stops the boot with a specific message."""
    out: dict[str, list[Any]] = {}
    for key, (filename, model) in _FILES.items():
        path = seed_dir / filename
        if not path.exists():
            raise SeedSchemaError(f"{filename}: missing from {seed_dir}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SeedSchemaError(f"{filename}: not valid JSON -- {exc}") from exc
        records = []
        for i, item in enumerate(raw):
            try:
                records.append(model(**item))
            except ValidationError as exc:
                first = exc.errors()[0]
                loc = ".".join(str(p) for p in first["loc"]) or "<root>"
                ident = item.get("id", f"index {i}")
                raise SeedSchemaError(
                    f"{filename}: record {ident}: field `{loc}`: {first['msg']}"
                ) from exc
        out[key] = records
    return out


def _phase2(data: dict[str, list[Any]]) -> list[Anomaly]:
    """Semantic validation. Findings are quarantined, never fatal."""
    anomalies: list[Anomaly] = []

    locations: list[Location] = data["locations"]
    operatories = {o.id for o in data["operatories"]}
    providers = {p.id for p in data["providers"]}
    types = {t.id for t in data["appointment_types"]}
    patients = {p.id for p in data["patients"]}
    loc = locations[0]
    tz = zone(loc.timezone)

    global_blocks = [b for b in data["blocks"] if b.scope.value == "global"
                     and b.kind.value in {"lunch", "huddle", "admin"}]

    seen_op: dict[tuple[str, date], list[tuple[int, int, str]]] = defaultdict(list)
    seen_prov: dict[tuple[str, date], list[tuple[int, int, str]]] = defaultdict(list)

    for a in data["appointments"]:
        for name, pool, value in (
            ("operatory", operatories, a.operatory_id),
            ("provider", providers, a.provider_id),
            ("appointment type", types, a.type_id),
        ):
            if value not in pool:
                anomalies.append(Anomaly(a.id, "dangling reference", f"unknown {name} {value!r}"))
        if a.patient_id is not None and a.patient_id not in patients:
            anomalies.append(
                Anomaly(a.id, "dangling reference", f"unknown patient {a.patient_id!r}")
            )

        day, start_min = to_local(a.start, tz)
        end_min = start_min + a.duration_min

        hours = loc.hours_for(day.weekday())
        if hours is None:
            anomalies.append(Anomaly(a.id, "outside business days", day.isoformat()))
        elif start_min < hours.open_min or end_min > hours.close_min:
            anomalies.append(
                Anomaly(a.id, "outside business hours", f"{start_min}-{end_min} on {day}")
            )

        for b in global_blocks:
            if b.applies_on(day) and start_min < b.end_min and b.start_min < end_min:
                anomalies.append(
                    Anomaly(a.id, "overlaps a blocked period", f"{b.kind.value} on {day}")
                )

        for table, key in ((seen_op, (a.operatory_id, day)), (seen_prov, (a.provider_id, day))):
            for lo, hi, other in table[key]:
                if start_min < hi and lo < end_min:
                    what = "operatory" if table is seen_op else "provider"
                    anomalies.append(
                        Anomaly(a.id, f"{what} double-booked", f"overlaps {other} on {day}")
                    )
                    break
        seen_op[(a.operatory_id, day)].append((start_min, end_min, a.id))
        seen_prov[(a.provider_id, day)].append((start_min, end_min, a.id))

    return anomalies


def load_seed(seed_dir: Path) -> LoadResult:
    data = _phase1(seed_dir)
    anomalies = _phase2(data)
    bad = {a.record_id for a in anomalies}

    bundle = SeedBundle(
        locations=tuple(data["locations"]),
        operatories=tuple(data["operatories"]),
        providers=tuple(data["providers"]),
        appointment_types=tuple(data["appointment_types"]),
        patients=tuple(data["patients"]),
        appointments=tuple(a for a in data["appointments"] if a.id not in bad),
        blocks=tuple(data["blocks"]),
    )
    return LoadResult(bundle=bundle, quarantined=anomalies)
