"""Per-pair detector concordance (proposal §4.8.2).

"D0 vs D1 disagreement stays a reportable result (§4.8.2)" — and once a judge
run exists, so does D1 vs D3 and D0 vs D3. This module computes that, and only
that.

THREE DISTINCTIONS THIS MODULE REFUSES TO BLUR
----------------------------------------------
1. **Not asked vs. reached no decision.** A detector that was never consulted
   about a pair is ``None`` here; one that was consulted and returned
   ``NOT_APPLICABLE`` is that verdict. Collapsing them would silently charge
   D0's restricted domain to its coverage. D0 is asked only about pairs where
   BOTH responses are ``ANSWER`` (see :func:`d0_pair_verdicts`), whereas D1 and
   D3 also take ``NEGATED`` — so for any pair holding a negation D0 has no
   opinion, which is not the same as having an undecided one.

2. **Matching rates vs. agreeing pairwise.** Two detectors can report the
   identical contradiction rate and differ on every single pair. Concordance is
   therefore computed pair-by-pair over the joint-decision set, never inferred
   from marginals. :attr:`Concordance.a_violation_rate` and its ``b`` twin are
   reported **on that same joint set** so they are comparable at all; a
   detector's rate over its own, larger coverage set is a different quantity and
   lives in the evaluation rows, not here.

3. **Agreement vs. accuracy.** Neither detector is gold. Nothing in this module
   returns precision, recall, F1 or AUPRC — ``analysis.detector_scores`` refuses
   those separately, because they need human labels that do not exist.

THE UNIT OF ANALYSIS IS THE CONSTRAINT, NOT THE PAIR
----------------------------------------------------
``configs/analysis/statistics.yaml`` sets ``independent_unit: constraint`` and
``pair_level_independence_assumption: FORBIDDEN``. So a pooled κ or raw
agreement computed over pairs is a **point estimate only**: its textbook
standard error assumes independent units and would be too narrow, because pairs
(A,B) and (A,C) share response A. :func:`per_constraint_agreement` yields one
value per constraint for ``analysis.bootstrap.cluster_bootstrap``, which is the
only interval this project will report for these quantities.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from ..schemas.enums import DetectorId, ResponseLabel, Verdict
from ..utils.ids import pair_id

#: The two verdicts that count as a decision. NOT_APPLICABLE is not one.
DECIDED: frozenset[Verdict] = frozenset({Verdict.VIOLATION, Verdict.SATISFIED})


@dataclass(frozen=True, slots=True)
class PairVerdicts:
    """Every detector's verdict on one pair. ``None`` = that detector was not asked."""

    pair_id: str
    constraint_id: str
    constraint_class: str
    verdicts: Mapping[str, Verdict | None] = field(default_factory=dict)

    def decided(self, detector: str) -> bool:
        return self.verdicts.get(detector) in DECIDED


def d0_pair_verdicts(
    constraint: Any, canon: Sequence[Any], kb: Any, registry: Any
) -> dict[str, Verdict]:
    """D0's verdict for each pair it is ASKED about — the one definition.

    ``analysis.evaluate.constraint_rows`` calls this too, so the question "which
    pairs was D0 consulted on" has a single answer in this project rather than
    two that happen to agree today.

    **Only pairs where both responses are ``ANSWER``.** A ``NEGATED`` response
    names no cluster ("not Canberra" picks out no member of the answer space),
    and D0's predicates are set-theoretic over definite answers. Returning
    nothing for such a pair is deliberate: see distinction 1 in the module
    docstring.

    An empty dict means D0 had no registered predicate for this constraint, or
    fewer than two definite answers — both are "not asked", not "undecided".
    """
    if kb is None or registry is None or not registry.has(constraint.formal_predicate):
        return {}
    pred = registry.get(constraint.formal_predicate)
    definite = [x for x in canon if x.label is ResponseLabel.ANSWER]
    return {
        pair_id(x.probe_id, y.probe_id): pred.check_pair(constraint, x, y, kb).verdict
        for x, y in combinations(definite, 2)
    }


def pair_table(
    constraint: Any,
    canon: Sequence[Any],
    *,
    d0_kb: Any | None = None,
    d0_registry: Any | None = None,
    d3_verdicts: Mapping[str, Verdict] | None = None,
) -> list[PairVerdicts]:
    """One row per pair of one constraint's responses, every detector aligned.

    D1 is always present: it is asked about every pair and answers
    ``NOT_APPLICABLE`` where a response makes no claim. D0 and D3 are ``None``
    wherever they were not asked — D0 by its ANSWER-only domain, D3 because a
    pair whose response renders no claim is never sent to the judge and so never
    reaches the archive.
    """
    from ..detectors.d1.exact_match import check_all_pairs

    d0 = d0_pair_verdicts(constraint, canon, d0_kb, d0_registry)
    d3 = dict(d3_verdicts or {})
    rows: list[PairVerdicts] = []
    for r in check_all_pairs(canon):
        rows.append(
            PairVerdicts(
                pair_id=r.pair_id,
                constraint_id=constraint.constraint_id,
                constraint_class=constraint.constraint_class.value,
                verdicts={
                    DetectorId.D0.value: d0.get(r.pair_id),
                    DetectorId.D1.value: r.verdict,
                    DetectorId.D3.value: d3.get(r.pair_id),
                },
            )
        )
    return rows


@dataclass(frozen=True, slots=True)
class Concordance:
    """Pairwise concordance between two detectors over a set of pairs."""

    detector_a: str
    detector_b: str
    n_pairs: int
    n_a_not_asked: int
    n_b_not_asked: int
    n_a_undecided: int
    n_b_undecided: int
    n_joint: int
    n_agree: int
    both_violation: int
    both_satisfied: int
    a_only_violation: int
    b_only_violation: int
    kappa: float | None
    kappa_note: str

    @property
    def raw_agreement(self) -> float | None:
        """Fraction of JOINTLY DECIDED pairs the two detectors label alike."""
        return (self.n_agree / self.n_joint) if self.n_joint else None

    @property
    def a_violation_rate(self) -> float | None:
        """A's contradiction rate ON THE JOINT SET — comparable with b's."""
        if not self.n_joint:
            return None
        return (self.both_violation + self.a_only_violation) / self.n_joint

    @property
    def b_violation_rate(self) -> float | None:
        if not self.n_joint:
            return None
        return (self.both_violation + self.b_only_violation) / self.n_joint


def cohens_kappa(
    both_violation: int, a_only: int, b_only: int, both_satisfied: int
) -> tuple[float | None, str]:
    """Chance-corrected agreement on the 2x2, with an explicit refusal.

    Returns ``(None, reason)`` rather than a number whenever κ is undefined or
    uninterpretable:

    * **no jointly decided pairs** — nothing to correct;
    * **either detector assigned ONE label to every pair.** κ is then
      identically 0 however much the two actually agree, so the number carries
      no information and reads as "no agreement".

    That second case is worth stating as algebra, because it is not the usual
    "both are constant" guard and it bites in practice. Let ``a`` be constant
    SATISFIED, so ``a_viol = 0``. Then::

        p_expected = 0 * b_viol + 1 * (1 - b_viol) = 1 - b_viol
        p_observed = both_satisfied / n = (n - b_only) / n = 1 - b_viol

    The two are equal for **every** value of ``b_viol``, so κ = 0 identically —
    even where raw agreement is 0.99. A real run hit exactly this: D1 returned
    SATISFIED on all 84 pairs while D3 called 28 of them contradictory, and the
    formula produced ``3.1e-16``, which rounds to a reported 0.0000 and would
    have been read as two detectors agreeing no better than chance when they
    in fact agreed on 64% of pairs.

    When κ is withheld, **raw agreement and the directional breakdown are the
    informative quantities** — they are always defined. The note travels into
    the report so a missing κ is never mistaken for zero agreement.
    """
    n = both_violation + a_only + b_only + both_satisfied
    if n == 0:
        return None, "no jointly decided pairs"
    p_observed = (both_violation + both_satisfied) / n
    a_viol = (both_violation + a_only) / n
    b_viol = (both_violation + b_only) / n
    constant = [
        name for name, rate in (("a", a_viol), ("b", b_viol)) if rate in (0.0, 1.0)
    ]
    if constant:
        which = " and ".join(constant)
        label = "VIOLATION" if (a_viol or b_viol) == 1.0 else "a single label"
        return None, (
            f"detector {which} assigned {label} to every one of the {n} jointly "
            "decided pairs, so kappa is identically 0 regardless of the other "
            "detector and carries no information; read raw_agreement and the "
            "directional breakdown instead"
        )
    p_expected = a_viol * b_viol + (1 - a_viol) * (1 - b_viol)
    if p_expected >= 1.0:  # pragma: no cover - unreachable once marginals vary
        return None, "expected agreement is 1.0; kappa is undefined (0/0)"
    return (p_observed - p_expected) / (1 - p_expected), "ok"


def concordance(
    rows: Sequence[PairVerdicts], detector_a: str, detector_b: str
) -> Concordance:
    """Compare two detectors pair-by-pair over ``rows``."""
    both_v = both_s = a_only = b_only = 0
    a_not_asked = b_not_asked = a_undecided = b_undecided = 0
    for r in rows:
        va, vb = r.verdicts.get(detector_a), r.verdicts.get(detector_b)
        if va is None:
            a_not_asked += 1
        elif va not in DECIDED:
            a_undecided += 1
        if vb is None:
            b_not_asked += 1
        elif vb not in DECIDED:
            b_undecided += 1
        if va not in DECIDED or vb not in DECIDED:
            continue
        if va is Verdict.VIOLATION and vb is Verdict.VIOLATION:
            both_v += 1
        elif va is Verdict.SATISFIED and vb is Verdict.SATISFIED:
            both_s += 1
        elif va is Verdict.VIOLATION:
            a_only += 1
        else:
            b_only += 1
    kappa, note = cohens_kappa(both_v, a_only, b_only, both_s)
    return Concordance(
        detector_a=detector_a, detector_b=detector_b, n_pairs=len(rows),
        n_a_not_asked=a_not_asked, n_b_not_asked=b_not_asked,
        n_a_undecided=a_undecided, n_b_undecided=b_undecided,
        n_joint=both_v + both_s + a_only + b_only,
        n_agree=both_v + both_s,
        both_violation=both_v, both_satisfied=both_s,
        a_only_violation=a_only, b_only_violation=b_only,
        kappa=kappa, kappa_note=note,
    )


def per_constraint_agreement(
    rows: Sequence[PairVerdicts], detector_a: str, detector_b: str
) -> tuple[list[str], list[float | None]]:
    """Raw agreement per CONSTRAINT, ready for ``cluster_bootstrap``.

    Returns ``(constraint_ids, values)`` in a stable order. A constraint with no
    jointly decided pair contributes ``None`` — never 0.0, which would read as
    total disagreement. Q6's rule: an undefined cell is resampled as a cluster
    that contributes nothing, widening the interval rather than biasing it.
    """
    by_constraint: dict[str, list[PairVerdicts]] = {}
    for r in rows:
        by_constraint.setdefault(r.constraint_id, []).append(r)
    cids = sorted(by_constraint)
    return cids, [
        concordance(by_constraint[c], detector_a, detector_b).raw_agreement for c in cids
    ]
