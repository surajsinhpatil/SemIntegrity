"""Aggregation by class, domain and probe factor (§4.11).

Every aggregate is a mean over CONSTRAINTS, because the constraint is the
independent unit. Constraints with an undefined metric are excluded from the
mean and **counted**, so an aggregate always arrives with the number of cells
it could not use — `metrics.yaml` requires the NA count be reported alongside.

The pair-factor cells implement ADR-0009, which the researcher DECIDED on
2026-09-11. A pair has two probes, so a probe-level factor has no well-defined
value at the pair level until it is made an unordered pair of levels:

    polarity   aff-aff · aff-neg · neg-neg
    syntax     dec-dec · dec-int · dec-clz · int-int · int-clz · clz-clz
    direction  dir-dir · dir-rev · rev-rev

Unordered, because a pair is unordered: (affirmative, negated) and
(negated, affirmative) are the same cell, and treating them separately would
split one cell's evidence in two.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from .metrics import ConstraintMetrics


@dataclass(frozen=True, slots=True)
class Aggregate:
    """A mean over constraints, with the cells it could not use."""

    key: str
    n_constraints: int
    n_defined: int
    n_undefined: int
    mean: float | None

    @property
    def defined(self) -> bool:
        return self.mean is not None

    @property
    def undefined_rate(self) -> float | None:
        if self.n_constraints == 0:
            return None
        return self.n_undefined / self.n_constraints


def _aggregate(key: str, values: Sequence[float | None]) -> Aggregate:
    defined = [v for v in values if v is not None]
    return Aggregate(
        key=key, n_constraints=len(values), n_defined=len(defined),
        n_undefined=len(values) - len(defined),
        mean=(sum(defined) / len(defined)) if defined else None,
    )


def group_by(
    rows: Iterable[ConstraintMetrics],
    key: Callable[[ConstraintMetrics], str],
    metric: Callable[[ConstraintMetrics], float | None],
) -> dict[str, Aggregate]:
    """Aggregate a metric over constraints, grouped by `key`."""
    buckets: dict[str, list[float | None]] = {}
    for row in rows:
        buckets.setdefault(key(row), []).append(metric(row))
    return {k: _aggregate(k, v) for k, v in sorted(buckets.items())}


def by_class(
    rows: Iterable[ConstraintMetrics],
    metric: Callable[[ConstraintMetrics], float | None] = lambda r: r.pscr,
) -> dict[str, Aggregate]:
    """Per-class profile. Classes are CATEGORICAL — never an ordered trend."""
    return group_by(rows, lambda r: r.constraint_class, metric)


def by_domain(
    rows: Iterable[ConstraintMetrics],
    metric: Callable[[ConstraintMetrics], float | None] = lambda r: r.pscr,
) -> dict[str, Aggregate]:
    return group_by(rows, lambda r: r.domain, metric)


#: Guards against anyone modelling class as ordinal or continuous.
CLASS_IS_CATEGORICAL = (
    "Constraint classes C1-C4 are CATEGORICAL, not ordered by difficulty. "
    "Report a four-class PROFILE, never a trend line or a complexity curve."
)


# --- pair-factor cells (ADR-0009) -------------------------------------------

_SHORT = {
    "affirmative": "aff", "negated": "neg",
    "declarative": "dec", "interrogative": "int", "cloze": "clz",
    "direct": "dir", "reverse": "rev",
}


def pair_factor_cell(level_a: str, level_b: str) -> str:
    """The UNORDERED pair-level cell for two probe-level factor values.

    Unordered because a pair is unordered. Sorting the two short codes means
    (aff, neg) and (neg, aff) land in one cell instead of splitting the
    evidence across two.
    """
    try:
        a, b = _SHORT[level_a], _SHORT[level_b]
    except KeyError as exc:
        raise ValueError(f"unknown factor level {exc.args[0]!r}") from None
    return "-".join(sorted((a, b)))


@dataclass(frozen=True, slots=True)
class BinomialCell:
    """One row of the beta-binomial model: a constraint x factor-cell count.

    `denominator` is the evaluable pairs falling in the cell. Cells with zero
    evaluable pairs contribute NO ROW — the config says so, and a zero-
    denominator row would either crash the fit or be silently imputed.
    """

    constraint_id: str
    constraint_class: str
    domain: str
    factor: str
    cell: str
    contradictions: int
    denominator: int

    @property
    def rate(self) -> float:
        return self.contradictions / self.denominator


def binomial_cells(
    constraint_id: str,
    constraint_class: str,
    domain: str,
    pair_rows: Sequence[Mapping[str, object]],
    factor: str,
) -> list[BinomialCell]:
    """Disaggregate a constraint's evaluable pairs into factor cells.

    Each item of `pair_rows` needs `level_a`, `level_b` and `is_contradiction`.
    Only EVALUABLE pairs should be passed; a non-evaluable pair has no verdict
    to count and belongs in neither numerator nor denominator.
    """
    counts: dict[str, list[int]] = {}
    for row in pair_rows:
        cell = pair_factor_cell(str(row["level_a"]), str(row["level_b"]))
        bucket = counts.setdefault(cell, [0, 0])
        bucket[0] += bool(row["is_contradiction"])
        bucket[1] += 1
    return [
        BinomialCell(constraint_id, constraint_class, domain, factor, cell,
                     contradictions=c, denominator=d)
        for cell, (c, d) in sorted(counts.items())
        if d > 0                      # zero-denominator cells contribute no row
    ]
