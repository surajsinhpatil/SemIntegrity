"""The probe-factor design must be exactly balanced at class level.

This is the arithmetic that makes §4.4.2's "balanced exactly across classes"
realisable at K = 8, and it is regression-tested because an off-by-one in the
rotation would silently confound a class effect with a phrasing effect.
"""

from collections import Counter
from itertools import product

import yaml

from semintegrity.utils.paths import p

CFG = yaml.safe_load(p("configs/benchmark/probe_factors.yaml").read_text())
SYNTAX = CFG["factors"]["syntax"]["levels"]
POLARITY = CFG["factors"]["polarity"]["levels"]
REGISTER = CFG["factors"]["register"]["levels"]
DIRECTION = CFG["factors"]["directionality"]["levels"]
GUARANTEES = CFG["guarantees"]
K = CFG["assignment"]["k"]


def cells():
    """The 2x2x2 within-constraint cells, in the frozen order."""
    return list(product(POLARITY, REGISTER, DIRECTION))


def assign_class(n_constraints: int = 30):
    """Yield (constraint_index, syntax, polarity, register, direction) slots."""
    for j in range(n_constraints):
        for i, (pol, reg, direction) in enumerate(cells()):
            yield j, SYNTAX[(i + j) % len(SYNTAX)], pol, reg, direction


def test_within_constraint_cells_equal_k():
    assert len(cells()) == K == 8


def test_class_level_balance_is_exact():
    slots = list(assign_class(30))
    per_cell = Counter((s, p_, r, d) for _, s, p_, r, d in slots)
    assert len(per_cell) == GUARANTEES["cells_per_class"] == 24
    assert set(per_cell.values()) == {GUARANTEES["observations_per_cell_per_class"]} == {10}
    assert sum(per_cell.values()) == GUARANTEES["probe_slots_per_class"] == 240


def test_benchmark_level_balance_is_exact():
    per_cell = Counter()
    for _ in range(4):  # four classes
        for _, s, p_, r, d in assign_class(30):
            per_cell[(s, p_, r, d)] += 1
    assert set(per_cell.values()) == {GUARANTEES["observations_per_cell_total"]} == {40}
    assert sum(per_cell.values()) == GUARANTEES["probe_slots_total"] == 960


def test_polarity_register_direction_balanced_within_every_constraint():
    for j in range(30):
        slots = [s for s in assign_class(30) if s[0] == j]
        assert Counter(x[2] for x in slots) == {"affirmative": 4, "negated": 4}
        assert Counter(x[3] for x in slots) == {"formal": 4, "colloquial": 4}
        assert Counter(x[4] for x in slots) == {"direct": 4, "reverse": 4}


def test_syntax_cannot_balance_within_a_constraint():
    """8 is not divisible by 3: the best possible split is 3/3/2.

    Documented rather than worked around, because the proposal argues balance at
    the CLASS level, which is achievable exactly.
    """
    for j in range(30):
        counts = Counter(x[1] for x in assign_class(30) if x[0] == j)
        assert sorted(counts.values(), reverse=True) == [3, 3, 2]
