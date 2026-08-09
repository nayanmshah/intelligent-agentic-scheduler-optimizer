"""Mutation testing for the decision core.

Coverage says a line ran. Mutation testing asks a harder question: if that line were
*wrong*, would anything fail? A suite can execute a scorer thoroughly and still assert
nothing about what it computes.

Scoped deliberately to the modules where a silent wrong answer is the failure mode --
the ladder, the axes, the composition, the tier gate, the selection. The API layer and
the CLIs are excluded: their failure modes are loud, and mutating them mostly measures
the test runner.

Operators are the classic set, chosen because each one corresponds to a real mistake:
an off-by-one boundary, an inverted comparison, a swapped `and`/`or`, a dropped
negation, a constant typed wrong.

Usage
-----
    uv run python scripts/mutate.py --count          # how many mutants
    uv run python scripts/mutate.py                  # run them all
    uv run python scripts/mutate.py --module select  # one module
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The decision core. A wrong answer here is silent -- it looks like a recommendation.
TARGETS = [
    "backend/app/reasoner/ladder.py",
    "backend/app/reasoner/tiers.py",
    "backend/app/reasoner/select.py",
    "backend/app/reasoner/enumerate.py",
    "backend/app/reasoner/availability.py",
    "backend/app/reasoner/scoring/axes.py",
    "backend/app/reasoner/scoring/compose.py",
    "backend/app/reasoner/pipeline.py",
    "backend/app/data/timezone.py",
    "backend/app/data/session.py",
]

#: The fast subset that constrains those modules. Running the whole suite per mutant
#: would multiply 27s by several hundred for no extra signal.
TESTS = [
    "tests/requirements/test_s2_dataset.py",
    "tests/requirements/test_s2_write_path.py",
    "tests/requirements/test_s3_reasoner.py",
    "tests/requirements/test_s4_decision.py",
    "tests/requirements/test_s4_axis_curves.py",
    "tests/requirements/test_s4_selection.py",
    "tests/property",
]

_CMP_SWAP = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
    ast.In: ast.NotIn, ast.NotIn: ast.In,
}
_BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}


@dataclass
class Mutant:
    path: str
    lineno: int
    kind: str
    description: str
    index: int


class _Collector(ast.NodeVisitor):
    """Finds every mutation site. Each site becomes exactly one mutant."""

    def __init__(self) -> None:
        self.sites: list[tuple[str, int, str]] = []

    def visit_Compare(self, node: ast.Compare) -> None:
        for op in node.ops:
            if type(op) in _CMP_SWAP:
                self.sites.append(
                    ("cmp", node.lineno, f"{type(op).__name__} -> {_CMP_SWAP[type(op)].__name__}")
                )
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        flip = "or" if isinstance(node.op, ast.And) else "and"
        self.sites.append(("bool", node.lineno, f"{'and' if flip == 'or' else 'or'} -> {flip}"))
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if isinstance(node.op, ast.Not):
            self.sites.append(("not", node.lineno, "drop `not`"))
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if type(node.op) in _BIN_SWAP:
            before, after = type(node.op).__name__, _BIN_SWAP[type(node.op)].__name__
            self.sites.append(("arith", node.lineno, f"{before} -> {after}"))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, bool):
            self.sites.append(("const", node.lineno, f"{node.value} -> {not node.value}"))
        elif isinstance(node.value, int | float) and not isinstance(node.value, bool):
            self.sites.append(("const", node.lineno, f"{node.value} -> {node.value + 1}"))
        self.generic_visit(node)


class _Applier(ast.NodeTransformer):
    """Applies the Nth site only. One mutation per run, so a survivor names one cause.

    **Traversal order must match ``_Collector`` exactly**, or index N here is not the
    site index N there and every reported line number is wrong. Both process the node
    *before* recursing into children. The first version of this class recursed first,
    which silently mislabelled survivors -- a mutation harness that lies about where
    the hole is, is worse than none.
    """

    def __init__(self, target: int) -> None:
        self.target = target
        self.n = -1

    def _hit(self) -> bool:
        self.n += 1
        return self.n == self.target

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        node.ops = [
            _CMP_SWAP[type(op)]() if (type(op) in _CMP_SWAP and self._hit()) else op
            for op in node.ops
        ]
        self.generic_visit(node)
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        if self._hit():
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        self.generic_visit(node)
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        drop = isinstance(node.op, ast.Not) and self._hit()
        self.generic_visit(node)
        return node.operand if drop else node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        if type(node.op) in _BIN_SWAP and self._hit():
            node.op = _BIN_SWAP[type(node.op)]()
        self.generic_visit(node)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, bool):
            return ast.Constant(value=not node.value) if self._hit() else node
        if isinstance(node.value, int | float):
            return ast.Constant(value=node.value + 1) if self._hit() else node
        return node


def collect(path: Path) -> list[tuple[str, int, str]]:
    c = _Collector()
    c.visit(ast.parse(path.read_text(encoding="utf-8")))
    return c.sites


def mutate_source(source: str, index: int) -> str | None:
    tree = ast.parse(source)
    mutated = _Applier(index).visit(tree)
    ast.fix_missing_locations(mutated)
    try:
        return ast.unparse(mutated)
    except Exception:
        return None


def run_one(mutant: Mutant, pool: queue.Queue) -> str:  # type: ignore[type-arg]
    """KILLED, SURVIVED, SKIPPED, or ERROR.

    The work tree is *checked out* of a queue rather than picked by index. Assigning
    ``workdirs[i % jobs]`` assumed tasks run in lockstep; they do not, so two mutants
    shared a directory and one read the other's half-written file.
    """
    workdir: Path = pool.get()
    try:
        target = workdir / mutant.path
        original = target.read_text(encoding="utf-8")
        mutated = mutate_source(original, mutant.index)
        if mutated is None or mutated == original:
            return "SKIPPED"

        # A mutant that will not parse is a harness bug, not a caught defect. Counting
        # it as KILLED would let a broken harness report a perfect score.
        try:
            ast.parse(mutated)
        except SyntaxError:
            return "ERROR"

        return _run_tests(target, original, mutated, workdir)
    finally:
        pool.put(workdir)


def _run_tests(target: Path, original: str, mutated: str, workdir: Path) -> str:
    target.write_text(mutated, encoding="utf-8")
    try:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", SCHED_LLM_MODE="fixtures")
        cmd = [sys.executable, "-m", "pytest", *TESTS,
               "-q", "-x", "--no-header", "-p", "no:cacheprovider"]
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, timeout=180, env=env)
        # A mutant that breaks the import or hangs is still caught, not "survived".
        return "KILLED" if proc.returncode != 0 else "SURVIVED"
    except subprocess.TimeoutExpired:
        return "KILLED"
    finally:
        target.write_text(original, encoding="utf-8")


def make_workdir(base: Path) -> Path:
    """A private copy of the tree per worker. Cheaper than it sounds and it keeps the
    real repository untouched even if this is interrupted."""
    d = Path(tempfile.mkdtemp(prefix="mutate-"))
    # Everything the fast subset touches. FR-103's test reads the Makefile itself, so
    # a work tree missing it fails for a reason that has nothing to do with the mutant.
    for item in ("backend", "tests", "pyproject.toml", "Makefile", "scripts"):
        src = base / item
        dst = d / item
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, dst)
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--module", default=None)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()

    targets = [t for t in TARGETS if not args.module or args.module in t]
    mutants: list[Mutant] = []
    for rel in targets:
        for i, (kind, lineno, desc) in enumerate(collect(ROOT / rel)):
            mutants.append(Mutant(rel, lineno, kind, desc, i))

    print(f"  {len(mutants)} mutants across {len(targets)} modules")
    if args.count:
        by_mod: dict[str, int] = {}
        for m in mutants:
            by_mod[m.path] = by_mod.get(m.path, 0) + 1
        for path, n in sorted(by_mod.items(), key=lambda kv: -kv[1]):
            print(f"    {n:>4}  {path}")
        return 0

    # --- integrity gate --------------------------------------------------------
    # Without this the score is worthless. If the *unmutated* tree fails -- a missing
    # file, a broken import, an env var -- then every mutant "fails" for that same
    # reason and the harness reports a triumphant 100%. It did exactly that on the
    # first run, and the number looked great.
    print("  verifying the baseline passes before trusting any mutant...")
    probe = make_workdir(ROOT)
    try:
        target = probe / TARGETS[0]
        verdict = _run_tests(target, target.read_text(), target.read_text(), probe)
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    if verdict != "SURVIVED":
        print("  BASELINE FAILS in a clean work tree -- every mutant would read as "
              "killed and the score would be a lie. Fix the work tree first.")
        return 2
    print("  baseline is green.\n")

    started = time.time()
    workdirs = [make_workdir(ROOT) for _ in range(args.jobs)]
    available: queue.Queue = queue.Queue()
    for d in workdirs:
        available.put(d)
    results: dict[str, list[Mutant]] = {
        "KILLED": [], "SURVIVED": [], "SKIPPED": [], "ERROR": []
    }
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(run_one, m, available): m for m in mutants}
            for done, fut in enumerate(concurrent.futures.as_completed(futures), start=1):
                m = futures[fut]
                results[fut.result()].append(m)
                if done % 25 == 0 or done == len(mutants):
                    rate = done / max(1e-9, time.time() - started)
                    left = (len(mutants) - done) / max(1e-9, rate)
                    sys.stdout.write(
                        f"\r  {done}/{len(mutants)}  killed={len(results['KILLED'])} "
                        f"survived={len(results['SURVIVED'])}  ~{left/60:.1f} min left   "
                    )
                    sys.stdout.flush()
    finally:
        for d in workdirs:
            shutil.rmtree(d, ignore_errors=True)

    killed, survived = len(results["KILLED"]), len(results["SURVIVED"])
    scored = killed + survived
    print(f"\n\n  ran in {(time.time()-started)/60:.1f} min")
    print(f"  killed    {killed}")
    print(f"  survived  {survived}")
    print(f"  skipped   {len(results['SKIPPED'])} (mutation was a no-op)")
    if results["ERROR"]:
        print(f"  ERRORS    {len(results['ERROR'])} -- harness produced unparseable source")
    if scored:
        print(f"\n  MUTATION SCORE  {100*killed/scored:.1f}%")

    if results["SURVIVED"]:
        print(f"\n  Survivors -- a wrong value here changes nothing any test checks ({survived}):")
        by_mod: dict[str, list[Mutant]] = {}
        for m in results["SURVIVED"]:
            by_mod.setdefault(m.path, []).append(m)
        for path, ms in sorted(by_mod.items(), key=lambda kv: -len(kv[1])):
            print(f"\n    {path}  ({len(ms)})")
            for m in sorted(ms, key=lambda x: x.lineno)[:40]:
                print(f"      line {m.lineno:<5} {m.kind:<6} {m.description}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
