"""Rank concordance between a continuous score and a detector partition.

**This module is NOT in :mod:`semintegrity.analysis.detector_scores`, and that
is deliberate.** That module guards precision/recall/F1/AUPRC behind
``require_human_gold``, which stays in force. Nothing here may be printed under
an accuracy heading, so nothing here lives next to the functions that compute
accuracy.

WHAT THIS MEASURES, AND WHAT IT CANNOT
--------------------------------------
D2's per-class threshold was calibrated on human-labelled development data,
which does not exist and will not (ADR-0023 D6). D2 therefore reports a
**continuous contradiction score** and no verdict. The question that remains
answerable is whether that score **orders** pairs the way another detector
**partitions** them:

    rank_concordance = P( score(pair the reference called VIOLATION)
                        > score(pair the reference called SATISFIED) )

with ties credited 0.5. This is numerically the Mann-Whitney U statistic (the
same quantity an ROC area computes), but **the reference is a detector, not
ground truth**, so it is a measure of agreement in ordering and **not** an
accuracy, an AUPRC, or evidence that either instrument is correct. A value near
1 says D2 ranks pairs as D1 partitions them. It says nothing about whether
either is right, and both may share the bias induced by rendering claims from
canonical answers.

Why it is worth computing at all: D0, D1 and D3 all reduce to comparing answer
slots (measured D0-vs-D1 pair agreement is 1.0000). An NLI model scoring the
full rendered claims is the only instrument in the stack whose mechanism is not
answer-identity, so it is the only one that can disagree for an interesting
reason. Where it disagrees is the finding; the headline number is the summary.

THE UNIT IS THE CONSTRAINT
--------------------------
``statistics.yaml`` sets ``pair_level_independence_assumption: FORBIDDEN``. The
pooled statistic is therefore a **point estimate only**, and
:func:`per_constraint_concordance` supplies one value per constraint for
``analysis.bootstrap.cluster_bootstrap``, which is the only interval this
project reports for it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..schemas.enums import Verdict

#: A reference partition must contain at least this many pairs on EACH side for
#: the statistic to be defined. One pair on a side makes the estimate a single
#: comparison, which is not informative and invites over-reading.
MIN_PER_SIDE = 2


@dataclass(frozen=True, slots=True)
class ScoredPair:
    """One pair: a continuous score, plus the reference detector's verdict."""

    pair_id: str
    constraint_id: str
    score: float
    reference_verdict: Verdict | None


@dataclass(frozen=True, slots=True)
class Concordance:
    """Rank concordance of a score against one detector's partition."""

    reference: str
    n_pairs: int
    n_violation: int
    n_satisfied: int
    n_excluded_undecided: int
    n_ties: int
    estimate: float | None
    refusal: str

    @property
    def defined(self) -> bool:
        return self.estimate is not None

    @property
    def is_accuracy(self) -> bool:
        """Always False. Present so a caller cannot mistake this for accuracy."""
        return False


def rank_concordance(pairs: Sequence[ScoredPair], *, reference: str = "D1") -> Concordance:
    """P(score of a VIOLATION pair > score of a SATISFIED pair), ties at 0.5.

    Pairs the reference detector did not decide (``NOT_APPLICABLE`` or ``None``)
    are **excluded and counted**, never folded into either side: "the reference
    said compatible" and "the reference was not asked" are different facts.

    Returns ``estimate=None`` with a stated reason when either side is too
    small. It never returns 0.5 as a stand-in for "undefined", because 0.5 is
    also the value meaning "no ordering relationship", and the two must not look
    alike.
    """
    decided = [
        p for p in pairs
        if p.reference_verdict in (Verdict.VIOLATION, Verdict.SATISFIED)
    ]
    excluded = len(pairs) - len(decided)
    for p in decided:
        if not math.isfinite(p.score):
            raise ValueError(f"{p.pair_id}: non-finite score {p.score!r}")

    pos = [p.score for p in decided if p.reference_verdict is Verdict.VIOLATION]
    neg = [p.score for p in decided if p.reference_verdict is Verdict.SATISFIED]

    if len(pos) < MIN_PER_SIDE or len(neg) < MIN_PER_SIDE:
        return Concordance(
            reference=reference, n_pairs=len(pairs), n_violation=len(pos),
            n_satisfied=len(neg), n_excluded_undecided=excluded, n_ties=0,
            estimate=None,
            refusal=(
                f"undefined: the reference partition has {len(pos)} VIOLATION and "
                f"{len(neg)} SATISFIED pair(s); at least {MIN_PER_SIDE} on each "
                "side are required. This is NOT 0.5."
            ),
        )

    wins = ties = 0.0
    n_ties = 0
    for a in pos:
        for b in neg:
            if a > b:
                wins += 1
            elif a == b:
                ties += 1
                n_ties += 1
    estimate = (wins + 0.5 * ties) / (len(pos) * len(neg))
    return Concordance(
        reference=reference, n_pairs=len(pairs), n_violation=len(pos),
        n_satisfied=len(neg), n_excluded_undecided=excluded, n_ties=n_ties,
        estimate=estimate, refusal="",
    )


def per_constraint_concordance(
    pairs: Sequence[ScoredPair], *, reference: str = "D1"
) -> tuple[list[str], list[float | None]]:
    """One concordance value per constraint, ready for ``cluster_bootstrap``.

    A constraint whose reference partition is one-sided contributes ``None`` —
    never 0.5, which would read as "no relationship" rather than "not
    estimable". Q6's rule: an undefined cluster widens the interval instead of
    biasing it.
    """
    by_constraint: dict[str, list[ScoredPair]] = {}
    for p in pairs:
        by_constraint.setdefault(p.constraint_id, []).append(p)
    cids = sorted(by_constraint)
    return cids, [
        rank_concordance(by_constraint[c], reference=reference).estimate for c in cids
    ]


def disagreement_examples(
    pairs: Sequence[ScoredPair], *, limit: int = 20
) -> dict[str, list[dict[str, Any]]]:
    """The pairs where the score and the partition diverge most.

    The headline statistic summarises; these are where the only
    non-answer-identity instrument in the stack departs from the symbolic rule,
    which is the scientifically interesting part and the reason D2 was retained.
    Returned as data for inspection, with **no verdict attached**: neither
    instrument is gold, so nothing here identifies which one is wrong. These are
    divergences, not errors, and a caller that labels them errors is wrong.
    """
    decided = [
        p for p in pairs
        if p.reference_verdict in (Verdict.VIOLATION, Verdict.SATISFIED)
    ]
    viol = sorted(
        (p for p in decided if p.reference_verdict is Verdict.VIOLATION),
        key=lambda p: p.score,
    )
    sat = sorted(
        (p for p in decided if p.reference_verdict is Verdict.SATISFIED),
        key=lambda p: -p.score,
    )

    def _fmt(ps: Sequence[ScoredPair]) -> list[dict[str, Any]]:
        return [
            {"pair_id": p.pair_id, "constraint_id": p.constraint_id,
             "score": p.score, "reference_verdict": str(p.reference_verdict)}
            for p in ps[:limit]
        ]

    return {
        # Both keys hold the same row shape so a caller can iterate either.
        # The caveat travels with the data rather than in a sibling key of a
        # different type, which is what mypy objected to.
        "reference_violation_lowest_score": _fmt(viol),
        "reference_satisfied_highest_score": _fmt(sat),
    }


def report(
    pairs_by_reference: Mapping[str, Sequence[ScoredPair]],
    *,
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
) -> dict[str, Any]:
    """Pooled concordance plus the constraint-clustered interval, per reference."""
    from .bootstrap import cluster_bootstrap

    out: dict[str, Any] = {
        "estimand": (
            "P(score of a pair the reference detector called VIOLATION > score "
            "of a pair it called SATISFIED), ties at 0.5"
        ),
        "is_accuracy": False,
        "reference_is_ground_truth": False,
        "interpretation_limit": (
            "The reference is a DETECTOR. A value near 1 means the score orders "
            "pairs as that detector partitions them; it does not mean either is "
            "correct, and both may share the bias induced by rendering claims "
            "from canonical answers."
        ),
        "references": {},
    }
    for ref, pairs in sorted(pairs_by_reference.items()):
        c = rank_concordance(pairs, reference=ref)
        _, values = per_constraint_concordance(pairs, reference=ref)
        boot = cluster_bootstrap(values, n_boot=n_boot, ci=ci, seed=seed)
        out["references"][ref] = {
            "pooled_estimate": c.estimate,
            "pooled_refusal": c.refusal,
            "n_pairs": c.n_pairs, "n_violation": c.n_violation,
            "n_satisfied": c.n_satisfied,
            "n_excluded_undecided": c.n_excluded_undecided, "n_ties": c.n_ties,
            "clustered": {
                "estimate": boot.estimate, "ci_low": boot.ci_low,
                "ci_high": boot.ci_high, "n_constraints": boot.n_clusters,
                "n_defined": boot.n_defined, "method": boot.method,
                "unit": "constraint",
                "note": "pair-level independence is FORBIDDEN; this resamples constraints",
            },
        }
    return out
