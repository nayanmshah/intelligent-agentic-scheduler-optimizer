"""PHI marking, and the reflection that derives a redactor from it.

[NFR-31] A hand-maintained list of PHI field names inside the redactor is correct
exactly once, and then silently wrong the first time somebody adds a field without
knowing the list exists. So the mark lives on the field, and the redactor is
*derived*. `tests/structure/test_phi_derivation.py` adds a new marked field and
asserts coverage with no change to the redactor -- that test is the requirement.

In v1.0 the data is 100% synthetic and the active redactor is a no-op. This module
buys nothing today; it costs an annotation now and an audit later.
"""

from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from typing import Annotated, Any, Final, get_args, get_origin, get_type_hints


class _PhiMarker:
    """Sentinel placed in ``Annotated[...]`` metadata to mark a PHI-bearing field."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "PHI"


PHI: Final = _PhiMarker()


def phi_fields(cls: type) -> frozenset[str]:
    """Field names on ``cls`` annotated ``Annotated[T, PHI]``.

    Works for dataclasses and pydantic models alike -- both keep their annotations
    reachable through ``get_type_hints(..., include_extras=True)``.
    """
    try:
        hints = get_type_hints(cls, include_extras=True)
    except Exception:  # pragma: no cover - unresolvable forward refs
        return frozenset()

    marked = set()
    for name, hint in hints.items():
        if get_origin(hint) is Annotated and any(m is PHI for m in get_args(hint)[1:]):
            marked.add(name)
    return frozenset(marked)


def phi_paths(cls: type, _seen: frozenset[type] = frozenset()) -> frozenset[str]:
    """Dotted paths to every PHI field reachable from ``cls``, recursively.

    Nested structures matter: ``DecisionRecord.constraints`` is marked, but so are
    fields inside ``RequestConstraints``. A redactor that only handles the top level
    leaks the nested ones.
    """
    if cls in _seen:
        return frozenset()
    seen = _seen | {cls}

    paths = set(phi_fields(cls))
    try:
        hints = get_type_hints(cls, include_extras=True)
    except Exception:  # pragma: no cover
        return frozenset(paths)

    for name, hint in hints.items():
        inner = _unwrap(hint)
        if _is_structured(inner):
            for sub in phi_paths(inner, seen):
                paths.add(f"{name}.{sub}")
    return frozenset(paths)


def _unwrap(hint: Any) -> Any:
    """Peel Annotated / Optional / sequence wrappers down to a candidate class."""
    if get_origin(hint) is Annotated:
        hint = get_args(hint)[0]
    args = get_args(hint)
    if args:
        for arg in args:
            if _is_structured(arg):
                return arg
    return hint


def _is_structured(obj: Any) -> bool:
    if not isinstance(obj, type):
        return False
    if is_dataclass(obj):
        return True
    return hasattr(obj, "model_fields")  # pydantic BaseModel, without importing it


def dataclass_defaults(cls: type) -> dict[str, Any]:  # pragma: no cover - utility
    """Default values for a dataclass, used by redactors that blank rather than drop."""
    if not is_dataclass(cls):
        return {}
    return {
        f.name: (f.default if f.default is not MISSING else None) for f in fields(cls)
    }
