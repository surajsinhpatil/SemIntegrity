"""Cluster bootstrap and multiplicity control (§4.11, configs/analysis/statistics.yaml).

**The constraint is the independent unit**, and `pair_level_independence_assumption`
is FORBIDDEN: pairs (A,B) and (A,C) share response A, so with K=8 the effective
information is nearer 8 responses than 28 pairs. Resampling pairs would shrink
intervals by pretending to information that is not there. Every function here
resamples CONSTRAINTS with replacement, carrying each constraint's pairs with it.

`precedence` in the config: where the bootstrap and the GLMM disagree on a
quantity both can estimate, **the bootstrap governs** and the discrepancy is
reported. So this module carries the confirmatory claim and must be the
conservative one.

NA cells (PSCR undefined for want of evaluable pairs) are carried through as
MISSING and never imputed as 0 — Q6's rule. A resample containing only NA cells
yields no estimate rather than a fabricated one.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """A point estimate with a bootstrap interval, and the counts behind it."""

    estimate: float | None
    ci_low: float | None
    ci_high: float | None
    n_clusters: int
    n_defined: int
    n_boot: int
    ci_level: float
    method: str
    n_degenerate_resamples: int = 0

    @property
    def defined(self) -> bool:
        return self.estimate is not None


def _mean_defined(values: Sequence[float | None]) -> float | None:
    """Mean over the DEFINED values. None if there are none."""
    defined = [v for v in values if v is not None]
    if not defined:
        return None
    return sum(defined) / len(defined)


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile; q in [0, 1]."""
    if not sorted_values:
        raise ValueError("no values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[int(pos)]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation).

    Hand-rolled so the confirmatory path does not depend on scipy being
    installed — the same absent-dependency trap that once made a validity check
    fail open in this project.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be in (0,1), got {p}")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def cluster_bootstrap(
    cluster_values: Sequence[float | None],
    *,
    statistic: Callable[[Sequence[float | None]], float | None] = _mean_defined,
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
    method: str = "BCa",
) -> BootstrapResult:
    """Bootstrap over CONSTRAINTS, the independent unit (§4.11).

    `cluster_values` is one value per constraint, `None` where undefined. NA
    cells are resampled like any other cluster but contribute nothing to the
    statistic, so their prevalence widens the interval instead of biasing it.

    `method` is "BCa" (default, as configured) or "percentile". BCa corrects for
    bias and skew, which matters because PSCR is a bounded proportion whose
    sampling distribution is skewed near 0 and 1.
    """
    n = len(cluster_values)
    n_defined = sum(v is not None for v in cluster_values)
    point = statistic(cluster_values)
    if point is None or n == 0:
        return BootstrapResult(None, None, None, n, n_defined, n_boot, ci, method)

    rng = random.Random(seed)
    replicates: list[float] = []
    degenerate = 0
    for _ in range(n_boot):
        sample = [cluster_values[rng.randrange(n)] for _ in range(n)]
        value = statistic(sample)
        if value is None:
            degenerate += 1      # every cluster in this resample was NA
            continue
        replicates.append(value)

    if not replicates:
        return BootstrapResult(point, None, None, n, n_defined, n_boot, ci, method,
                               degenerate)
    replicates.sort()
    alpha = (1 - ci) / 2

    if method == "percentile":
        lo, hi = _percentile(replicates, alpha), _percentile(replicates, 1 - alpha)
        return BootstrapResult(point, lo, hi, n, n_defined, n_boot, ci, method, degenerate)

    # --- BCa ---------------------------------------------------------------
    n_below = sum(r < point for r in replicates)
    if n_below in (0, len(replicates)):
        # The point estimate lies outside the replicate spread; z0 is infinite.
        # Fall back to percentile rather than emit an interval from an infinity.
        lo, hi = _percentile(replicates, alpha), _percentile(replicates, 1 - alpha)
        return BootstrapResult(point, lo, hi, n, n_defined, n_boot, ci,
                               "percentile (BCa degenerate)", degenerate)
    z0 = _norm_ppf(n_below / len(replicates))

    # Acceleration by jackknife over clusters.
    jack = []
    for i in range(n):
        left_out = [v for j, v in enumerate(cluster_values) if j != i]
        value = statistic(left_out)
        if value is not None:
            jack.append(value)
    if len(jack) < 2:
        lo, hi = _percentile(replicates, alpha), _percentile(replicates, 1 - alpha)
        return BootstrapResult(point, lo, hi, n, n_defined, n_boot, ci,
                               "percentile (jackknife degenerate)", degenerate)
    jbar = sum(jack) / len(jack)
    num = sum((jbar - v) ** 3 for v in jack)
    den = 6.0 * (sum((jbar - v) ** 2 for v in jack) ** 1.5)
    a = num / den if den != 0 else 0.0

    def _adjust(z_alpha: float) -> float:
        denom = 1 - a * (z0 + z_alpha)
        if denom == 0:
            return 0.5
        return _norm_cdf(z0 + (z0 + z_alpha) / denom)

    q_lo = min(max(_adjust(_norm_ppf(alpha)), 0.0), 1.0)
    q_hi = min(max(_adjust(_norm_ppf(1 - alpha)), 0.0), 1.0)
    lo, hi = _percentile(replicates, q_lo), _percentile(replicates, q_hi)
    if lo > hi:  # pragma: no cover - guards a pathological adjustment
        lo, hi = hi, lo
    return BootstrapResult(point, lo, hi, n, n_defined, n_boot, ci, method, degenerate)


def bootstrap_difference(
    a_values: Sequence[float | None],
    b_values: Sequence[float | None],
    *,
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
) -> BootstrapResult:
    """Difference in means between two INDEPENDENT sets of constraints.

    For the §4.11 contrasts (C1+C2 vs C3+C4; C4 vs C1-C3 pooled), whose arms are
    disjoint constraint sets, so each arm is resampled separately.
    """
    pa, pb = _mean_defined(a_values), _mean_defined(b_values)
    n_total = len(a_values) + len(b_values)
    n_def = sum(v is not None for v in a_values) + sum(v is not None for v in b_values)
    if pa is None or pb is None:
        return BootstrapResult(None, None, None, n_total, n_def, n_boot, ci, "percentile")

    rng = random.Random(seed)
    reps: list[float] = []
    degenerate = 0
    for _ in range(n_boot):
        ra = [a_values[rng.randrange(len(a_values))] for _ in range(len(a_values))]
        rb = [b_values[rng.randrange(len(b_values))] for _ in range(len(b_values))]
        ma, mb = _mean_defined(ra), _mean_defined(rb)
        if ma is None or mb is None:
            degenerate += 1
            continue
        reps.append(ma - mb)
    if not reps:
        return BootstrapResult(pa - pb, None, None, n_total, n_def, n_boot, ci,
                               "percentile", degenerate)
    reps.sort()
    alpha = (1 - ci) / 2
    return BootstrapResult(
        pa - pb, _percentile(reps, alpha), _percentile(reps, 1 - alpha),
        n_total, n_def, n_boot, ci, "percentile", degenerate,
    )


def paired_cluster_bootstrap(
    a_values: Sequence[float | None],
    b_values: Sequence[float | None],
    *,
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 20250058,
) -> BootstrapResult:
    """Difference between two measurements of the SAME constraints.

    Used for MODEL comparisons, where every model is evaluated on the identical
    120 constraints. :func:`bootstrap_difference` is wrong here: it resamples
    each arm independently, which discards the pairing and inflates the interval
    because between-constraint variance — much the larger component — enters
    twice instead of cancelling.

    So one constraint INDEX is resampled and used for both arms, which is the
    §4.11 framework unchanged (``independent_unit: constraint``,
    ``resample: constraints_with_replacement``) applied to a paired contrast.

    ``a_values[i]`` and ``b_values[i]`` must describe the same constraint. A
    cluster where EITHER arm is undefined contributes to neither mean, so an
    NA in one model does not silently shift the other's.
    """
    if len(a_values) != len(b_values):
        raise ValueError(
            f"paired bootstrap needs aligned arms, got {len(a_values)} and "
            f"{len(b_values)}; the i-th value of each must be the same constraint"
        )
    n = len(a_values)
    pairs = [
        (a, b) for a, b in zip(a_values, b_values, strict=True)
        if a is not None and b is not None
    ]
    point = (
        sum(a - b for a, b in pairs) / len(pairs) if pairs else None
    )
    if point is None or n == 0:
        return BootstrapResult(None, None, None, n, len(pairs), n_boot, ci, "percentile")

    rng = random.Random(seed)
    reps: list[float] = []
    degenerate = 0
    for _ in range(n_boot):
        drawn = [
            (a_values[i], b_values[i])
            for i in (rng.randrange(n) for _ in range(n))
        ]
        usable = [(a, b) for a, b in drawn if a is not None and b is not None]
        if not usable:
            degenerate += 1
            continue
        reps.append(sum(a - b for a, b in usable) / len(usable))
    if not reps:
        return BootstrapResult(point, None, None, n, len(pairs), n_boot, ci,
                               "percentile", degenerate)
    reps.sort()
    alpha = (1 - ci) / 2
    return BootstrapResult(
        point, _percentile(reps, alpha), _percentile(reps, 1 - alpha),
        n, len(pairs), n_boot, ci, "percentile", degenerate,
    )


# --- multiplicity ------------------------------------------------------------

def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> list[bool]:
    """BH-FDR. Returns per-hypothesis rejection flags in the INPUT order.

    `multiplicity` in the config applies this to everything OUTSIDE the
    pre-specified confirmatory contrasts, which are exempt.
    """
    n = len(p_values)
    if n == 0:
        return []
    for p in p_values:
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"p-value {p} outside [0, 1]")
    order = sorted(range(n), key=lambda i: p_values[i])
    reject = [False] * n
    max_k = -1
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= alpha * rank / n:
            max_k = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= max_k:
            reject[idx] = True
    return reject


def bh_adjusted_p(p_values: Sequence[float]) -> list[float]:
    """BH-adjusted p-values (q-values), monotone, in the INPUT order."""
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    adjusted = [0.0] * n
    prev = 1.0
    for rank in range(n, 0, -1):
        idx = order[rank - 1]
        q = min(prev, p_values[idx] * n / rank)
        adjusted[idx] = min(1.0, q)
        prev = adjusted[idx]
    return adjusted
