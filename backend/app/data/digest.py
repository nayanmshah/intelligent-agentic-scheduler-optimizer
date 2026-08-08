"""Canonical digest over the seed directory.

[ADR-11] This is what turns the PRD's sequencing constraint -- *freeze the dataset
before labelling the golden set* -- from a procedure someone has to remember into a
check that fails loudly. Each golden entry records the digest it was labelled
against; a mismatch stops the harness rather than quietly reporting wrong numbers.

Canonicalisation matters more than the hash: sorted keys, fixed separators, no
whitespace drift. Otherwise reformatting a JSON file would "change" the dataset.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

DIGEST_FILE = "SEED_DIGEST"


def canonical_json(obj: object) -> str:
    """One serialiser, used for digests, fixtures, and the determinism diff.

    Two runs that disagree on key order are not two different answers, and the
    determinism check (FR-097) must not report them as such.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_digest(seed_dir: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(seed_dir.glob("*.json")):
        h.update(path.name.encode())
        payload = json.loads(path.read_text(encoding="utf-8"))
        h.update(canonical_json(payload).encode())
    return h.hexdigest()


def read_expected(seed_dir: Path) -> str | None:
    f = seed_dir / DIGEST_FILE
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def write_digest(seed_dir: Path) -> str:
    digest = compute_digest(seed_dir)
    (seed_dir / DIGEST_FILE).write_text(digest + "\n", encoding="utf-8")
    return digest


def seed_digest(seed_dir: Path) -> tuple[str, str | None]:
    """(computed, committed). Pre-flight reports both so a mismatch names itself."""
    return compute_digest(seed_dir), read_expected(seed_dir)
