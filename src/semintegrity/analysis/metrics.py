"""Metric definitions (§4.10, `configs/analysis/metrics.yaml`).

Detector-agnostic: every function takes pair verdicts, so D0, D1, D2 and D3 are
scored by identical code and their numbers are commensurable. That is the whole
point of the detector comparison — a metric implemented twice would compare
implementations as much as detectors.

Three rules run through all of it.

**Denominators are explicit and carried on the record.** `ConstraintMetrics`
reports `n_pairs`, `n_evaluable_pairs` and `n_contradictory_pairs` beside every
rate, so a reader can reconstruct any figure and see what it was divided by.
A rate whose denominator is invisible cannot be audited.

**Undefined is not zero.** A constraint with no evaluable pairs has PSCR `None`,
never `0.0`. Q6 requires NA cells be carried through the bootstrap as missing
and never imputed, and a 0.0 would read as "perfectly consistent" — the exact
opposite of "we could not tell".

**ABSTAIN and INVALID are never contradictions.** They are not evaluable, so
they leave the numerator *and* the denominator. A model that refuses everything
must not thereby score as consistent, which is why abstention is reported
alongside PSCR as part of the reliability triad rather than folded into it.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Protocol

from ..schemas.enums import ResponseLabel, Verdict
from ..schemas.response import CanonicalResponse


class PairVerdict(Protocol):
    """The slice of a detector result the metrics need."""

    probe_a: str
    probe_b: str
    verdict: Verdict


def _evaluable(results: Sequence[PairVerdict]) -> list[PairVerdict]:
    return [r for r in results if r.verdict is not Verdict.NOT_APPLICABLE]


# --- primary and key secondary ----------------------------------------------

def pscr(results: Sequence[PairVerdict]) -> float | None:
    """PRIMARY ENDPOINT — contradictory pairs / evaluable pairs.

    Returns None when nothing is evaluable. Never 0.0: "no contradictions were
    found" and "no comparison could be made" are different claims, and Q6
    requires the second be carried as missing.
    """
    ev = _evaluable(results)
    if not ev:
        return None
    return sum(r.verdict is Verdict.VIOLATION for r in ev) / len(ev)


def pcs(responses: Sequence[CanonicalResponse], k: int | None = None) -> float | None:
    """KEY SECONDARY — largest canonical-answer cluster / K.

    The denominator is K, the number of probes ASKED, not the number answered.
    Dividing by the answered count would let a model raise its PCS by abstaining
    more, which inverts the metric's meaning.

    NEGATED is excluded from clustering: "not Canberra" names no cluster, it
    rules one out. Counting it as its own cluster would invent an answer.
    """
    denominator = k if k is not None else len(responses)
    if denominator <= 0:
        return None
    clusters = Counter(
        r.canonical_answer for r in responses if r.label is ResponseLabel.ANSWER
    )
    if not clusters:
        return None
    return max(clusters.values()) / denominator


# --- secondary --------------------------------------------------------------

def consistency_at_k(pscr_values: Sequence[float | None]) -> float | None:
    """Proportion of constraints with NO contradiction among their K probes.

    Constraints with undefined PSCR are excluded from both numerator and
    denominator, and the caller should report how many were dropped —
    `metrics.yaml` requires the NA count be reported alongside.
    """
    defined = [v for v in pscr_values if v is not None]
    if not defined:
        return None
    return sum(v == 0.0 for v in defined) / len(defined)


def aocr(pscr_values: Sequence[float | None]) -> float | None:
    """Proportion of constraints with >= 1 contradiction detected.

    MUST be labelled K-dependent wherever reported. `metrics.yaml` demotes this
    to secondary-descriptive because AOCR ~ 1-(1-PSCR)^C(K,2) saturates near 1
    and measures the detector more than the model. It is the complement of
    Consistency@K over the same defined subset.
    """
    defined = [v for v in pscr_values if v is not None]
    if not defined:
        return None
    return sum(v > 0.0 for v in defined) / len(defined)


#: Attached wherever AOCR is reported, per `MUST_BE_LABELLED_K_DEPENDENT`.
AOCR_LABEL = (
    "K-DEPENDENT: AOCR ~ 1-(1-PSCR)^C(K,2). It saturates near 1.0 as K grows and "
    "measures the detector as much as the model; not comparable across K."
)


def truth_accuracy(
    responses: Sequence[CanonicalResponse], gold_answer: str
) -> float | None:
    """Correct answers / answers given. A SEPARATE reliability dimension.

    NEGATED counts in the denominator and never the numerator: asserting "the
    capital is not Canberra" when it is Canberra is a wrong answer, not a
    non-answer. Folding it into abstention would flatter the model.
    """
    answered = [r for r in responses
                if r.label in (ResponseLabel.ANSWER, ResponseLabel.NEGATED)]
    if not answered:
        return None
    correct = sum(
        r.label is ResponseLabel.ANSWER and r.canonical_answer == gold_answer
        for r in answered
    )
    return correct / len(answered)


def abstention_rate(responses: Sequence[CanonicalResponse]) -> float | None:
    """ABSTAIN / all responses. A SEPARATE reliability dimension.

    Denominator is every response, including INVALID: the question is how often
    the model declined, out of how often it was asked.
    """
    if not responses:
        return None
    return sum(r.label is ResponseLabel.ABSTAIN for r in responses) / len(responses)


def detector_coverage(results: Sequence[PairVerdict]) -> float | None:
    """Evaluable pairs / all pairs. A RESULT, never a diagnostic (§4.8.1)."""
    if not results:
        return None
    return len(_evaluable(results)) / len(results)


# --- recovery@k --------------------------------------------------------------

def recovery_at_k(
    results: Sequence[PairVerdict],
    probe_ids: Sequence[str],
    k: int,
    *,
    draws: int = 1000,
    seed: int = 20250058,
) -> float | None:
    """Probability that a random k-probe subset surfaces >= 1 contradiction.

    Rarefaction-style subsampling, as `metrics.yaml` specifies. The reference
    budget (50 on the saturation subset, 8 elsewhere) is the CALLER's to supply;
    this returns the raw detection probability at k so the caller can form the
    ratio against whichever reference applies.

    Framing, from the config: a REFERENCE, never ground truth and never a proven
    asymptote.
    """
    if k < 2 or k > len(probe_ids):
        return None
    violating = {
        frozenset((r.probe_a, r.probe_b))
        for r in results if r.verdict is Verdict.VIOLATION
    }
    if not violating:
        return 0.0
    rng = random.Random(seed)
    ids = list(probe_ids)
    hits = 0
    for _ in range(draws):
        subset = set(rng.sample(ids, k))
        if any(pair <= subset for pair in violating):
            hits += 1
    return hits / draws


# --- per-constraint bundle ---------------------------------------------------

@dataclass(frozen=True, slots=True)
class ConstraintMetrics:
    """Every metric for one constraint x model, with its denominators."""

    constraint_id: str
    constraint_class: str
    domain: str
    n_responses: int
    n_answer: int
    n_negated: int
    n_abstain: int
    n_invalid: int
    n_other: int
    n_pairs: int
    n_evaluable_pairs: int
    n_contradictory_pairs: int
    pscr: float | None
    pcs: float | None
    truth_accuracy: float | None
    abstention_rate: float | None
    coverage: float | None

    @property
    def pscr_defined(self) -> bool:
        return self.pscr is not None

    def check_denominators(self) -> None:
        """The counts must reconcile. Cheap, and catches a filter drifting."""
        total = (self.n_answer + self.n_negated + self.n_abstain
                 + self.n_invalid + self.n_other)
        if total != self.n_responses:
            raise ValueError(
                f"{self.constraint_id}: labels sum to {total}, "
                f"n_responses is {self.n_responses}"
            )
        if self.n_contradictory_pairs > self.n_evaluable_pairs:
            raise ValueError(
                f"{self.constraint_id}: {self.n_contradictory_pairs} contradictions "
                f"among {self.n_evaluable_pairs} evaluable pairs"
            )
        if self.n_evaluable_pairs > self.n_pairs:
            raise ValueError(
                f"{self.constraint_id}: {self.n_evaluable_pairs} evaluable of "
                f"{self.n_pairs} pairs"
            )


def constraint_metrics(
    constraint_id: str,
    constraint_class: str,
    domain: str,
    responses: Sequence[CanonicalResponse],
    results: Sequence[PairVerdict],
    gold_answer: str,
    *,
    k: int | None = None,
) -> ConstraintMetrics:
    """Bundle every metric for one constraint, with reconciled denominators."""
    labels = Counter(r.label for r in responses)
    known = (ResponseLabel.ANSWER, ResponseLabel.NEGATED,
             ResponseLabel.ABSTAIN, ResponseLabel.INVALID)
    ev = _evaluable(results)
    m = ConstraintMetrics(
        constraint_id=constraint_id, constraint_class=constraint_class, domain=domain,
        n_responses=len(responses),
        n_answer=labels[ResponseLabel.ANSWER],
        n_negated=labels[ResponseLabel.NEGATED],
        n_abstain=labels[ResponseLabel.ABSTAIN],
        n_invalid=labels[ResponseLabel.INVALID],
        n_other=sum(v for lbl, v in labels.items() if lbl not in known),
        n_pairs=len(results),
        n_evaluable_pairs=len(ev),
        n_contradictory_pairs=sum(r.verdict is Verdict.VIOLATION for r in ev),
        pscr=pscr(results),
        pcs=pcs(responses, k),
        truth_accuracy=truth_accuracy(responses, gold_answer),
        abstention_rate=abstention_rate(responses),
        coverage=detector_coverage(results),
    )
    m.check_denominators()
    return m


def expected_pairs(k: int) -> int:
    """C(k, 2) — the pair count a complete K-probe constraint must produce."""
    return len(list(combinations(range(k), 2)))
