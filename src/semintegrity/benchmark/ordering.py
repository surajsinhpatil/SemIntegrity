"""The canonical constraint ordering that fixes every probe's syntax.

Why this module exists
----------------------
ADR-0003 rotates the syntax factor across constraints::

    syntax(constraint j, cell i) = SYNTAX[(i + j) mod 3]

and :mod:`semintegrity.probes.factor_design` documents ``j`` as "the
constraint's 0-based position **within its class**", adding that it "must be
stable once the benchmark is frozen". Until now that position came from whichever
order the authoring source happened to list families in, which made the
*file layout* of ``candidates.yaml`` determine the surface form of all 960
probes. Re-ordering two families in a YAML file would silently re-word a third of
the benchmark.

So the ordering is pinned here instead, derived from the record rather than from
the file:

1. **domain**, in the order §4.3 lists them — geography, history, biology,
   public office, science & technology;
2. **schema index** within the class, i.e. the axis number from ``schema_id``;
3. **constraint cell index**, as a final tie-break so the function is total even
   if a future allocation puts two constraints in one (domain, schema) cell.

Under ADR-0002's lattice the first two keys are already unique within a class —
schema × domain is fully crossed, one constraint per cell — so the third never
fires in the approved design. It is there so that the function cannot silently
return an arbitrary order if that assumption is ever relaxed (Q12).

This reproduces the existing 12-constraint pilot exactly: its families are listed
geography, public office, science & technology, which is their §4.3 order, so no
pilot probe changes. ``tests/unit/test_constraint_ordering.py`` pins that.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..schemas.constraint import Constraint
from ..schemas.enums import ConstraintClass, Domain
from ..utils.ids import CONSTRAINT_RE, SCHEMA_RE

#: §4.3's own order: "geography, history, biology, public office, science &
#: technology". This must equal the declaration order of :class:`Domain`; a
#: module-level ``assert`` would vanish under ``python -O``, so the equality is
#: pinned by ``tests/unit/test_constraint_ordering.py`` instead.
DOMAIN_ORDER: tuple[Domain, ...] = (
    Domain.GEOGRAPHY,
    Domain.HISTORY,
    Domain.BIOLOGY,
    Domain.PUBLIC_OFFICE,
    Domain.SCIENCE_TECHNOLOGY,
)


class OrderingError(ValueError):
    """Raised when a constraint cannot be placed in the canonical order."""


def schema_index(schema_id: str) -> int:
    """The axis number encoded in a ``schema_id`` (``S-C3-04`` -> 4)."""
    m = SCHEMA_RE.match(schema_id)
    if not m:  # pragma: no cover - the schema pins the pattern
        raise OrderingError(f"malformed schema_id: {schema_id!r}")
    return int(m.group(2))


def constraint_cell_index(constraint_id: str) -> int:
    """The cell number encoded in a ``constraint_id`` (``K-C3-BIO-14`` -> 14)."""
    m = CONSTRAINT_RE.match(constraint_id)
    if not m:  # pragma: no cover - the schema pins the pattern
        raise OrderingError(f"malformed constraint_id: {constraint_id!r}")
    return int(m.group(3))


def canonical_key(constraint: Constraint) -> tuple[int, int, int]:
    """Sort key for the canonical within-class ordering."""
    return (
        DOMAIN_ORDER.index(constraint.domain),
        schema_index(constraint.schema_id),
        constraint_cell_index(constraint.constraint_id),
    )


def order_within_class(
    constraints: Iterable[Constraint], cls: ConstraintClass
) -> list[Constraint]:
    """The constraints of one class, in canonical order."""
    return sorted((c for c in constraints if c.constraint_class is cls), key=canonical_key)


def constraint_indices(constraints: Sequence[Constraint]) -> dict[str, int]:
    """``constraint_id`` -> 0-based canonical position within its class.

    This is the ``constraint_index`` ADR-0003's syntax rotation consumes. It is a
    pure function of the constraint records, so re-running the authoring pipeline
    on unchanged records reproduces every probe's syntax.
    """
    out: dict[str, int] = {}
    for cls in ConstraintClass:
        for position, constraint in enumerate(order_within_class(constraints, cls)):
            out[constraint.constraint_id] = position
    return out
