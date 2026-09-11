"""Probe factor design generator (ADR-0003, proposal §4.4.2).

Produces the exact factor cell each probe must occupy, so that the balance is a
*generated* property rather than something an author has to get right by hand
960 times.

The design
----------
Four factors span 24 cells but K = 8, so a full crossing inside one constraint
is impossible. Instead:

* ``(polarity x register x directionality)`` = 2x2x2 = **8 = K**, so every
  constraint carries each of these cells exactly once;
* syntax rotates across constraints: ``SYNTAX[(cell_index + constraint_index) % 3]``.

Result, verified in ``tests/unit/test_probe_balance.py`` and asserted again here
by :func:`verify_balance`:

=========================  =====  =========================
Level                      Cells  Observations per cell
=========================  =====  =========================
per class (30 constraints)    24  exactly 10
whole benchmark (960)         24  exactly 40
=========================  =====  =========================
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import product

from ..schemas.enums import ConstraintClass, Directionality, Polarity, Register, Syntax

#: The frozen order of the 2x2x2 within-constraint lattice. Changing this order
#: changes which syntax lands on which cell, so it is fixed here and nowhere else.
CELL_ORDER: tuple[tuple[Polarity, Register, Directionality], ...] = tuple(
    product(Polarity, Register, Directionality)
)

SYNTAX_ORDER: tuple[Syntax, ...] = (Syntax.DECLARATIVE, Syntax.INTERROGATIVE, Syntax.CLOZE)

K_PRIMARY = 8


@dataclass(frozen=True, slots=True)
class FactorCell:
    """The factor assignment for one probe slot."""

    cell_index: int
    syntax: Syntax
    polarity: Polarity
    register: Register
    directionality: Directionality

    @property
    def key(self) -> tuple[Syntax, Polarity, Register, Directionality]:
        return (self.syntax, self.polarity, self.register, self.directionality)


class DesignError(ValueError):
    """Raised when a generated or observed design violates its guarantees."""


def cells_for_constraint(constraint_index: int, k: int = K_PRIMARY) -> list[FactorCell]:
    """The k factor cells for one constraint.

    ``constraint_index`` is the constraint's 0-based position **within its
    class**, taken from the frozen benchmark ordering. It drives the syntax
    rotation, so it must be stable once the benchmark is frozen.
    """
    if constraint_index < 0:
        raise DesignError(f"constraint_index must be >= 0, got {constraint_index}")
    if k < 1:
        raise DesignError(f"k must be >= 1, got {k}")

    cells: list[FactorCell] = []
    for i in range(k):
        pol, reg, direction = CELL_ORDER[i % len(CELL_ORDER)]
        cells.append(
            FactorCell(
                cell_index=i % len(CELL_ORDER),
                syntax=SYNTAX_ORDER[(i + constraint_index) % len(SYNTAX_ORDER)],
                polarity=pol,
                register=reg,
                directionality=direction,
            )
        )
    return cells


def cells_for_class(n_constraints: int = 30, k: int = K_PRIMARY) -> list[list[FactorCell]]:
    """Factor cells for every constraint in one class, in frozen order."""
    return [cells_for_constraint(j, k) for j in range(n_constraints)]


def saturation_cells(constraint_index: int, k: int = 50) -> list[FactorCell]:
    """Factor cells for a saturation-tier constraint (§4.4.4).

    The first 8 are byte-identical to the primary tier — the saturation tier
    *reuses* the primary probes and adds 42 more — so a probe generated here at
    index < 8 must equal the primary probe at the same index.
    """
    if k < K_PRIMARY:
        raise DesignError(f"saturation k must be >= {K_PRIMARY}, got {k}")
    cells = cells_for_constraint(constraint_index, k)
    primary = cells_for_constraint(constraint_index, K_PRIMARY)
    if cells[:K_PRIMARY] != primary:
        raise DesignError("saturation cells diverge from the primary tier at the first 8 slots")
    return cells


# --- verification -----------------------------------------------------------
def verify_balance(
    design: dict[ConstraintClass, list[list[FactorCell]]],
    *,
    expected_per_cell_per_class: int = 10,
    expected_cells: int = 24,
) -> None:
    """Assert the design's balance guarantees, or raise with the offending counts.

    Run at benchmark freeze time. A design that fails this would confound a class
    effect with a phrasing effect, which is precisely the threat §4.4.2 names.
    """
    total: Counter = Counter()
    for cls, constraints in design.items():
        per_class: Counter = Counter()
        for cells in constraints:
            for c in cells:
                per_class[c.key] += 1
                total[c.key] += 1

        if len(per_class) != expected_cells:
            raise DesignError(
                f"{cls.value}: {len(per_class)} distinct factor cells, expected {expected_cells}"
            )
        counts = set(per_class.values())
        if counts != {expected_per_cell_per_class}:
            offenders = {k: v for k, v in per_class.items() if v != expected_per_cell_per_class}
            raise DesignError(
                f"{cls.value}: unbalanced factor cells (expected {expected_per_cell_per_class} "
                f"each, saw {sorted(counts)}); offenders: {offenders}"
            )

    expected_total = expected_per_cell_per_class * len(design)
    bad = {k: v for k, v in total.items() if v != expected_total}
    if bad:
        raise DesignError(f"benchmark-level imbalance (expected {expected_total} per cell): {bad}")


def verify_constraint_cells(cells: list[FactorCell], k: int = K_PRIMARY) -> None:
    """Assert one constraint's within-constraint guarantees (ADR-0003)."""
    if len(cells) != k:
        raise DesignError(f"expected {k} cells, got {len(cells)}")
    if k == K_PRIMARY:
        triples = {(c.polarity, c.register, c.directionality) for c in cells}
        if len(triples) != K_PRIMARY:
            raise DesignError(
                f"the 2x2x2 lattice must appear exactly once each; saw {len(triples)} distinct triples"
            )
        for factor, expected in (
            ("polarity", {Polarity.AFFIRMATIVE: 4, Polarity.NEGATED: 4}),
            ("register", {Register.FORMAL: 4, Register.COLLOQUIAL: 4}),
            ("directionality", {Directionality.DIRECT: 4, Directionality.REVERSE: 4}),
        ):
            got = Counter(getattr(c, factor) for c in cells)
            if dict(got) != expected:
                raise DesignError(f"{factor} not balanced within constraint: {dict(got)}")
        # Syntax cannot balance within a constraint: 8 is not divisible by 3.
        shape = sorted(Counter(c.syntax for c in cells).values(), reverse=True)
        if shape != [3, 3, 2]:
            raise DesignError(f"syntax split must be 3/3/2 within a constraint, got {shape}")


def full_primary_design(n_per_class: int = 30) -> dict[ConstraintClass, list[list[FactorCell]]]:
    """The complete factor design for the primary tier, verified before return."""
    design = {cls: cells_for_class(n_per_class) for cls in ConstraintClass}
    verify_balance(design)
    return design
