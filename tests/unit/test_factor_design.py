"""Probe factor design generator (ADR-0003)."""

from collections import Counter

import pytest

from semintegrity.probes.factor_design import (
    CELL_ORDER,
    K_PRIMARY,
    DesignError,
    cells_for_class,
    cells_for_constraint,
    full_primary_design,
    saturation_cells,
    verify_balance,
    verify_constraint_cells,
)
from semintegrity.schemas.enums import ConstraintClass, Directionality, Polarity, Register, Syntax


def test_within_constraint_lattice_is_the_full_2x2x2():
    assert len(CELL_ORDER) == K_PRIMARY == 8
    assert len(set(CELL_ORDER)) == 8


@pytest.mark.parametrize("j", range(30))
def test_every_constraint_satisfies_its_within_constraint_guarantees(j):
    verify_constraint_cells(cells_for_constraint(j))


def test_class_level_balance_is_exactly_ten_per_cell():
    counts = Counter(c.key for cells in cells_for_class(30) for c in cells)
    assert len(counts) == 24
    assert set(counts.values()) == {10}
    assert sum(counts.values()) == 240


def test_benchmark_level_balance_is_exactly_forty_per_cell():
    design = full_primary_design()
    counts = Counter(c.key for cls in design.values() for cells in cls for c in cells)
    assert len(counts) == 24
    assert set(counts.values()) == {40}
    assert sum(counts.values()) == 960


def test_syntax_rotates_across_constraints():
    """Constraint j and j+1 must not share a syntax assignment for cell 0."""
    a = cells_for_constraint(0)[0].syntax
    b = cells_for_constraint(1)[0].syntax
    c = cells_for_constraint(2)[0].syntax
    assert {a, b, c} == set(Syntax)


def test_full_design_is_verified_before_it_is_returned():
    design = full_primary_design()
    assert set(design) == set(ConstraintClass)
    verify_balance(design)


def test_verify_balance_localises_the_offending_cell():
    design = {cls: [list(x) for x in v] for cls, v in full_primary_design().items()}
    design[ConstraintClass.C3][5][2] = design[ConstraintClass.C3][5][3]
    with pytest.raises(DesignError, match="C3: unbalanced"):
        verify_balance(design)


def test_saturation_reuses_the_primary_probes():
    """§4.4.4: the 50 saturation probes include the 8 primary ones."""
    for j in (0, 7, 29):
        sat = saturation_cells(j, 50)
        assert len(sat) == 50
        assert sat[:8] == cells_for_constraint(j, 8)


def test_saturation_below_primary_k_is_rejected():
    with pytest.raises(DesignError, match="must be >="):
        saturation_cells(0, 4)


def test_negative_constraint_index_is_rejected():
    with pytest.raises(DesignError):
        cells_for_constraint(-1)


def test_within_constraint_factor_counts():
    cells = cells_for_constraint(0)
    assert Counter(c.polarity for c in cells) == {Polarity.AFFIRMATIVE: 4, Polarity.NEGATED: 4}
    assert Counter(c.register for c in cells) == {Register.FORMAL: 4, Register.COLLOQUIAL: 4}
    assert Counter(c.directionality for c in cells) == {
        Directionality.DIRECT: 4,
        Directionality.REVERSE: 4,
    }
    # 8 is not divisible by 3, so syntax cannot balance within a constraint
    assert sorted(Counter(c.syntax for c in cells).values(), reverse=True) == [3, 3, 2]


def test_verify_constraint_cells_rejects_a_duplicated_cell():
    cells = cells_for_constraint(0)
    cells[1] = cells[0]
    with pytest.raises(DesignError, match="exactly once"):
        verify_constraint_cells(cells)
