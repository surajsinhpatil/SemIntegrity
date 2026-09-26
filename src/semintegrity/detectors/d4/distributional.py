"""D4 — distributional instability over candidate answers (§4.8.6). EXPLORATORY.

**D4 IS NOT A CONTRADICTION DETECTOR.** `configs/detectors/d4_distributional.yaml`
sets `IS_A_CONTRADICTION_DETECTOR: false` and says it is "enforced by tests".
This module therefore exposes **no** `check_pair`, no `verdict`, and no
`is_contradiction` anywhere, so D4 output cannot be fed to code expecting a
detector. `tests/unit/test_d4_distributional.py` asserts that absence.

The disclaimer the config carries, restated because it is the whole reason for
the restriction: two distributions can differ substantially while agreeing on
the top answer, and can be nearly identical while straddling a decision
boundary. A JSD is not evidence of a contradiction.

WHAT IS IMPLEMENTED
-------------------
Everything §4.8.6 specifies unambiguously:

* teacher-forced scoring of the constraint's closed candidate set;
* length normalisation to **per-token** log-probability;
* Jensen-Shannon divergence between two candidate distributions;
* `mean_pairwise_JSD_within_constraint` aggregation;
* the scope limits — Track A only, cross-constraint absolute comparison
  forbidden.

WHAT IS DELIBERATELY NOT IMPLEMENTED
------------------------------------
The mapping from per-token log-probabilities to a probability distribution.
Per-token means do not sum to 1, so a mapping is required, and **Q5 records it
as unresolved**. The repository narrows it to a one-parameter family:

    p_i = softmax_i(mean_token_logprob_i / T)

§4.8.6 requires length normalisation, which rules out renormalising
`exp(sum logprob)`. `T = 1` is the "no temperature" reading. But **JSD
magnitudes are not comparable across choices of T**, and Q5 states the mapping
must be preregistered. Choosing T here would settle a preregistered quantity by
import, so `DistributionBuilder` is a required argument with **no default**.

`SoftmaxOverMeanLogprob` is provided as the named candidate, but nothing
constructs it implicitly: a caller must choose it and state its temperature.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Protocol

#: Mirrors the config key. Any code that reads this and still builds a verdict
#: is doing something the specification forbids.
IS_A_CONTRADICTION_DETECTOR = False


class DistributionUnresolved(RuntimeError):
    """A distribution was requested without the Q5 mapping being chosen."""


class CandidateScorer(Protocol):
    """Teacher-forced per-token log-probability for each candidate answer."""

    name: str

    def mean_token_logprobs(self, prompt: str, candidates: Sequence[str]) -> list[float]:
        """Mean per-token log-probability of each candidate, given the prompt."""
        ...


class DistributionBuilder(Protocol):
    """Maps per-token log-probabilities to a probability distribution (Q5)."""

    name: str

    def to_distribution(self, mean_logprobs: Sequence[float]) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class SoftmaxOverMeanLogprob:
    """`p_i = softmax_i(mean_token_logprob_i / T)` — the candidate in Q5.

    Not a default anywhere. `temperature` must be stated explicitly because it
    is a preregistered quantity: JSD magnitudes are not comparable across
    values of it.
    """

    temperature: float

    def __post_init__(self) -> None:
        if not self.temperature > 0:
            raise ValueError(f"temperature must be > 0, got {self.temperature}")

    @property
    def name(self) -> str:
        return f"softmax_over_mean_logprob(T={self.temperature})"

    def to_distribution(self, mean_logprobs: Sequence[float]) -> list[float]:
        if not mean_logprobs:
            raise ValueError("cannot build a distribution over an empty candidate set")
        scaled = [x / self.temperature for x in mean_logprobs]
        top = max(scaled)
        exps = [math.exp(x - top) for x in scaled]  # shift for numerical stability
        total = sum(exps)
        return [e / total for e in exps]


def jensen_shannon_divergence(p: Sequence[float], q: Sequence[float], *, base: float = 2.0) -> float:
    """JSD between two distributions over the SAME ordered candidate set.

    Base 2, so the value lies in [0, 1] and 1 means disjoint support. Returns a
    divergence, not a distance: it is not the square root.
    """
    if len(p) != len(q):
        raise ValueError(f"distributions have different supports: {len(p)} vs {len(q)}")
    if not p:
        raise ValueError("empty distribution")
    for name, d in (("p", p), ("q", q)):
        if any(x < 0 for x in d):
            raise ValueError(f"{name} has a negative probability")
        if not math.isclose(sum(d), 1.0, abs_tol=1e-6):
            raise ValueError(f"{name} sums to {sum(d)}, not 1")

    def _kl(a: Sequence[float], m: Sequence[float]) -> float:
        return sum(
            ai * math.log(ai / mi, base)
            for ai, mi in zip(a, m, strict=True)
            if ai > 0 and mi > 0
        )

    m = [(pi + qi) / 2 for pi, qi in zip(p, q, strict=True)]
    return max(0.0, 0.5 * _kl(p, m) + 0.5 * _kl(q, m))


@dataclass(frozen=True, slots=True)
class D4ProbeDistribution:
    """One probe's distribution over the constraint's candidate set."""

    probe_id: str
    candidates: tuple[str, ...]
    mean_logprobs: tuple[float, ...]
    probabilities: tuple[float, ...]
    scorer: str
    builder: str

    @property
    def top_candidate(self) -> str:
        return self.candidates[max(range(len(self.probabilities)),
                                   key=self.probabilities.__getitem__)]


@dataclass(frozen=True, slots=True)
class D4Analysis:
    """Mean pairwise JSD within one constraint. EXPLORATORY, never a verdict."""

    constraint_id: str
    n_probes: int
    mean_pairwise_jsd: float | None
    max_pairwise_jsd: float | None
    pairwise: tuple[tuple[str, str, float], ...]
    builder: str
    scorer: str
    #: Carried on every record so a reader cannot mistake this for a detector.
    interpretation_limit: str = (
        "EXPLORATORY. Two distributions can differ substantially while agreeing "
        "on the top answer, and can be nearly identical while straddling a "
        "decision boundary. Absolute JSD is NOT comparable across constraints "
        "(dissimilar candidate spaces) and is NOT evidence of a contradiction."
    )


@dataclass
class D4Distributional:
    """Teacher-forced candidate distributions and their divergence (§4.8.6)."""

    scorer: CandidateScorer
    #: Q5. No default: choosing one would settle a preregistered quantity.
    builder: DistributionBuilder

    def distribution_for(
        self, probe_id: str, prompt: str, candidates: Sequence[str]
    ) -> D4ProbeDistribution:
        if not candidates:
            raise ValueError(f"{probe_id}: D4 needs a closed candidate set (§4.8.6 scope limit)")
        logprobs = self.scorer.mean_token_logprobs(prompt, candidates)
        if len(logprobs) != len(candidates):
            raise ValueError(
                f"{probe_id}: scorer returned {len(logprobs)} scores for "
                f"{len(candidates)} candidates"
            )
        probs = self.builder.to_distribution(logprobs)
        return D4ProbeDistribution(
            probe_id=probe_id, candidates=tuple(candidates),
            mean_logprobs=tuple(logprobs), probabilities=tuple(probs),
            scorer=self.scorer.name, builder=self.builder.name,
        )

    def analyse(
        self, constraint_id: str, prompts: Mapping[str, str], candidates: Sequence[str]
    ) -> D4Analysis:
        """`mean_pairwise_JSD_within_constraint` over the given probes."""
        dists = [self.distribution_for(pid, prompt, candidates)
                 for pid, prompt in prompts.items()]
        pairs = [
            (a.probe_id, b.probe_id,
             jensen_shannon_divergence(a.probabilities, b.probabilities))
            for a, b in combinations(dists, 2)
        ]
        values = [v for _, _, v in pairs]
        return D4Analysis(
            constraint_id=constraint_id, n_probes=len(dists),
            mean_pairwise_jsd=(sum(values) / len(values)) if values else None,
            max_pairwise_jsd=max(values) if values else None,
            pairwise=tuple(pairs), builder=self.builder.name, scorer=self.scorer.name,
        )
