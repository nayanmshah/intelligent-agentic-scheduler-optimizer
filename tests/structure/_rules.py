"""Reusable static checks.

Factored out of the tests so each rule can be run against a synthetic violating
source string as well as against the real tree. A guard nobody has ever seen fail is
not a guard -- it is a decoration.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}  {self.detail}"


def app_sources(exclude: tuple[str, ...] = ()) -> list[Path]:
    out = []
    for p in sorted(APP_ROOT.rglob("*.py")):
        rel = p.relative_to(APP_ROOT).as_posix()
        if any(rel == e or rel.startswith(e.rstrip("/") + "/") for e in exclude):
            continue
        out.append(p)
    return out


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# --------------------------------------------------------------------------
# FR-102 / NFR-14 -- no clock reading outside clock.py
# --------------------------------------------------------------------------
_CLOCK_CALLS = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("datetime", "today"),
    ("date", "today"),
    ("time", "time"),
    ("time", "monotonic"),
}


def find_clock_reads(tree: ast.AST, path: str) -> list[Violation]:
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and (f.value.id, f.attr) in _CLOCK_CALLS
        ):
            out.append(
                Violation(path, node.lineno, f"clock read `{f.value.id}.{f.attr}()` [FR-102]")
            )
    return out


# --------------------------------------------------------------------------
# NFR-32 / ADR-17 -- naive datetimes only inside the conversion boundary
# --------------------------------------------------------------------------
def find_naive_datetimes(tree: ast.AST, path: str) -> list[Violation]:
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and f.value.id == "datetime"
            and f.attr == "combine"
        ):
            out.append(
                Violation(path, node.lineno, "datetime.combine() builds a naive value [NFR-32]")
            )
        if isinstance(f, ast.Name) and f.id == "datetime":
            has_tz = any(k.arg == "tzinfo" for k in node.keywords)
            if not has_tz:
                out.append(
                    Violation(path, node.lineno, "datetime(...) without tzinfo [NFR-32]")
                )
    return out


# --------------------------------------------------------------------------
# Import direction. Each of these is a requirement, not a preference.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ImportRule:
    package: str  # path prefix under backend/app
    forbidden: tuple[str, ...]  # module prefixes it may not import
    allow: tuple[str, ...] = ()  # explicit exemptions
    requirement: str = ""


IMPORT_RULES: tuple[ImportRule, ...] = (
    ImportRule(
        package="reasoner",
        forbidden=("app.agents",),
        requirement="FR-054 -- ranking is a pure function, independent of the LLM",
    ),
    ImportRule(
        package="reasoner",
        forbidden=("app.data.session", "app.data.memory_repo", "app.data.loader"),
        allow=("app.data.repository", "app.data.timezone"),
        requirement="NFR-29 -- the reasoner reads through ScheduleRepository, not a concrete store",
    ),
    ImportRule(
        package="agents/explainer",
        forbidden=("app.reasoner",),
        allow=("app.reasoner.rationale",),
        requirement="FR-059 -- the explainer renders a Rationale and can reach nothing else",
    ),
    ImportRule(
        package="agents/verifier",
        forbidden=("app.data", "app.reasoner"),
        allow=("app.data.timezone",),
        requirement="FR-009 -- the verifier is schedule-blind",
    ),
)


def _imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    mods: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend((a.name, node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append((node.module, node.lineno))
    return mods


def check_import_rule(rule: ImportRule) -> list[Violation]:
    out: list[Violation] = []
    root = APP_ROOT / rule.package
    if not root.exists():
        return out
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for mod, line in _imported_modules(_parse(path)):
            if any(mod == a or mod.startswith(a + ".") for a in rule.allow):
                continue
            if any(mod == f or mod.startswith(f + ".") for f in rule.forbidden):
                out.append(Violation(rel, line, f"imports `{mod}` -- {rule.requirement}"))
    return out


# --------------------------------------------------------------------------
# FR-046 -- weights are data, never literals in the scorer
# --------------------------------------------------------------------------
_ALLOWED_SCORING_NUMBERS = {0, 1, 2, 3, 60, 120, 30, 100}


def find_weight_literals() -> list[Violation]:
    """FR-046 forbids *magic numbers inside the scoring functions*, not every float.

    A module-level ``NEAR_VALUE = 0.85`` is the "as data" pattern the requirement
    asks for -- it names the axis's shape where a reader can find and change it. An
    inline ``0.85`` buried in an expression is what the rule is actually about, and
    is what this reports.
    """
    out: list[Violation] = []
    root = APP_ROOT / "reasoner" / "scoring"
    if not root.exists():
        return out
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        tree = _parse(path)

        allowed: set[int] = set()
        for node in tree.body:  # module level only
            if isinstance(node, ast.Assign) and all(
                isinstance(t, ast.Name) and t.id.isupper() for t in node.targets
            ):
                for sub in ast.walk(node.value):
                    allowed.add(id(sub))

        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, float):
                    continue
                if id(node) in allowed or node.value in (0.0, 1.0):
                    continue
                if 0.0 < node.value < 1.0:
                    out.append(
                        Violation(
                            rel,
                            node.lineno,
                            f"magic number {node.value!r} inside a scoring function -- "
                            "name it as a module constant or move it to Settings [FR-046]",
                        )
                    )
    return out
