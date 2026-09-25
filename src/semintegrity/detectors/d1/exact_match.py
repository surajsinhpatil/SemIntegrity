"""D1 — canonical exact match (proposal §4.8.3).

Applied **after** Stage 0, which is what makes it a legitimate floor rather than
a strawman: comparing raw strings across a yes/no probe and an entity probe would
flag every such pair by construction (§4.7).

Its coverage shrinks as constraint structure becomes more demanding, and that
shrinkage is itself the reportable result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from ...schemas.enums import DetectorId, ResponseLabel, Verdict
from ...schemas.response import CanonicalResponse, pair_is_evaluable
from ...utils.ids import pair_id


@dataclass(frozen=True, slots=True)
class D1Result:
    pair_id: str
    probe_a: str
    probe_b: str
    verdict: Verdict
    detector: str = DetectorId.D1.value
    reason: str = ""

    @property
    def is_contradiction(self) -> bool:
        return self.verdict is Verdict.VIOLATION


def _negated(r: CanonicalResponse) -> bool:
    return r.label is ResponseLabel.NEGATED


def check_pair(a: CanonicalResponse, b: CanonicalResponse) -> D1Result:
    """Two canonical answers contradict iff they cannot both be true.

    With the Q21 polarity mapping a response is either a definite answer or the
    NEGATION of one ("the capital is not Canberra"). The rule generalises
    "differ = contradict" to cover that, and is symmetric — PSCR counts
    unordered pairs, so an asymmetric rule would make the metric depend on
    iteration order:

    ============  ============  ==========================
    a             b             contradiction?
    ============  ============  ==========================
    ANSWER(x)     ANSWER(y)     iff x != y
    ANSWER(x)     NEGATED(y)    iff x == y
    NEGATED(x)    NEGATED(y)    never — jointly satisfiable
    ============  ============  ==========================

    Two negations never conflict: "not Canberra" and "not Sydney" are both true
    if the answer is Melbourne. Nor does NEGATED(x) conflict with ANSWER(y!=x),
    which is the case that makes the closed answer space matter — a negation
    rules out one member, not all the others.
    """
    pid = pair_id(a.probe_id, b.probe_id)
    if not pair_is_evaluable(a, b):
        return D1Result(
            pid, a.probe_id, b.probe_id, Verdict.NOT_APPLICABLE,
            reason=f"not evaluable: {a.label.value} / {b.label.value}",
        )

    na, nb = _negated(a), _negated(b)
    if na and nb:
        return D1Result(
            pid, a.probe_id, b.probe_id, Verdict.SATISFIED,
            reason=f"not {a.canonical_answer!r} and not {b.canonical_answer!r} "
                   "are jointly satisfiable",
        )
    if na or nb:
        definite, negation = (b, a) if na else (a, b)
        if definite.canonical_answer == negation.canonical_answer:
            return D1Result(
                pid, a.probe_id, b.probe_id, Verdict.VIOLATION,
                reason=f"{definite.canonical_answer!r} contradicts "
                       f"not {negation.canonical_answer!r}",
            )
        return D1Result(
            pid, a.probe_id, b.probe_id, Verdict.SATISFIED,
            reason=f"{definite.canonical_answer!r} is consistent with "
                   f"not {negation.canonical_answer!r}",
        )
    if a.canonical_answer == b.canonical_answer:
        return D1Result(
            pid, a.probe_id, b.probe_id, Verdict.SATISFIED,
            reason=f"both {a.canonical_answer!r}",
        )
    return D1Result(
        pid, a.probe_id, b.probe_id, Verdict.VIOLATION,
        reason=f"{a.canonical_answer!r} != {b.canonical_answer!r}",
    )


def check_all_pairs(responses: Sequence[CanonicalResponse]) -> list[D1Result]:
    """Every pair of a constraint's responses, in canonical pair order."""
    return [check_pair(a, b) for a, b in combinations(responses, 2)]


def coverage(results: Sequence[D1Result]) -> float:
    """Fraction of pairs D1 could evaluate — the §4.8.3 reportable quantity."""
    if not results:
        return 0.0
    return sum(r.verdict is not Verdict.NOT_APPLICABLE for r in results) / len(results)
