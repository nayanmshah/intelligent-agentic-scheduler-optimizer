"""Pre-flight readiness report [NFR-12].

Design rule: **any red item is named, never merely counted.** "3 checks failed" sends
someone hunting; "seed digest mismatch: expected abc123, found def456" does not.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from app.container import AppContainer, build_container

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


@dataclass
class PreflightReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def ready(self) -> bool:
        return not self.failed

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail} for c in self.checks
            ],
        }

    def render(self) -> str:
        glyph = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}
        lines = ["", "  Pre-flight", "  " + "-" * 62]
        for c in self.checks:
            lines.append(f"  [{glyph[c.status]}] {c.name:<28} {c.detail}")
        lines.append("  " + "-" * 62)
        lines.append("  READY" if self.ready else f"  NOT READY -- {len(self.failed)} blocking")
        return "\n".join(lines) + "\n"


def run_preflight(container: AppContainer | None = None) -> PreflightReport:
    c = container or build_container()
    s = c.settings
    r = PreflightReport()

    r.add("reference clock", OK, s.reference_now.isoformat())
    # Live is the shipped default; fixtures are the fallback. The wording used to say
    # "LIVE -- opt-in", which was true when offline was the default and is now exactly
    # backwards -- and this line is the one an operator reads to know which is running.
    r.add(
        "network mode",
        OK,
        "LIVE -- models in use" if not s.offline else "offline (fixtures) -- degraded",
    )

    if s.offline:
        r.add("api key", OK, "not required offline")
    elif s.has_api_key:
        r.add("api key", OK, "present")
    else:
        r.add("api key", FAIL, "live mode selected but ANTHROPIC_API_KEY is unset")

    if s.seed_dir.exists() and any(s.seed_dir.glob("*.json")):
        from app.data.digest import seed_digest

        try:
            digest, expected = seed_digest(s.seed_dir)
            if expected is None:
                r.add("seed digest", WARN, f"{digest[:12]} (no SEED_DIGEST committed yet)")
            elif digest == expected:
                r.add("seed digest", OK, digest[:12])
            else:
                r.add(
                    "seed digest",
                    FAIL,
                    f"mismatch: computed {digest[:12]}, committed {expected[:12]}",
                )
        except Exception as exc:  # pragma: no cover - defensive
            r.add("seed digest", FAIL, str(exc))
    else:
        r.add("seed data", WARN, "not generated yet -- run `make seed` (S2)")

    r.add(
        "frontend assets",
        OK if s.static_dir.exists() else WARN,
        str(s.static_dir) if s.static_dir.exists() else "not built -- run `make frontend`",
    )

    if s.opik_enabled:
        r.add("observability", WARN, "enabled; optional and never on the request path")
    else:
        r.add("observability", OK, "local trace store only")

    r.add(
        "timeout ladder",
        OK if s.timeout_ladder_total <= s.live_latency_ceiling else FAIL,
        f"{s.timeout_ladder_total:.1f}s <= {s.live_latency_ceiling:.1f}s ceiling",
    )
    return r


def main() -> int:
    report = run_preflight()
    sys.stdout.write(report.render())
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
