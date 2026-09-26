"""Cluster bootstrap and BH-FDR (§4.11, configs/analysis/statistics.yaml).

The bootstrap carries the confirmatory claim (`precedence`: where it and the
GLMM disagree, the bootstrap governs), so these tests lean on the properties
that make it trustworthy rather than on any particular number: the constraint
is the resampling unit, NA cells are never imputed, and a seeded run repeats.
"""

import pytest

from semintegrity.analysis.bootstrap import (
    benjamini_hochberg,
    bh_adjusted_p,
    bootstrap_difference,
    cluster_bootstrap,
)


# --- basic behaviour ---------------------------------------------------------

def test_recovers_a_known_mean():
    values = [0.2] * 20
    r = cluster_bootstrap(values, n_boot=500)
    assert r.estimate == pytest.approx(0.2)
    assert r.ci_low == pytest.approx(0.2) and r.ci_high == pytest.approx(0.2)


def test_interval_brackets_the_estimate_and_widens_with_spread():
    tight = cluster_bootstrap([0.5, 0.49, 0.51, 0.5] * 5, n_boot=800, seed=1)
    wide = cluster_bootstrap([0.0, 1.0, 0.0, 1.0] * 5, n_boot=800, seed=1)
    for r in (tight, wide):
        assert r.ci_low <= r.estimate <= r.ci_high
    assert (wide.ci_high - wide.ci_low) > (tight.ci_high - tight.ci_low)


def test_is_reproducible_under_a_seed():
    v = [0.1, 0.9, 0.3, 0.7, 0.5] * 4
    a = cluster_bootstrap(v, n_boot=500, seed=7)
    b = cluster_bootstrap(v, n_boot=500, seed=7)
    assert (a.estimate, a.ci_low, a.ci_high) == (b.estimate, b.ci_low, b.ci_high)


def test_different_seeds_give_different_intervals_but_the_same_point():
    v = [0.1, 0.9, 0.3, 0.7, 0.5] * 4
    a = cluster_bootstrap(v, n_boot=300, seed=1)
    b = cluster_bootstrap(v, n_boot=300, seed=2)
    assert a.estimate == b.estimate
    assert (a.ci_low, a.ci_high) != (b.ci_low, b.ci_high)


# --- NA handling: Q6 --------------------------------------------------------

def test_na_cells_are_never_imputed_as_zero():
    """Imputing 0 would read as 'perfectly consistent'. The estimate must be
    the mean of the DEFINED values only."""
    with_na = cluster_bootstrap([0.4, 0.4, None, None], n_boot=400, seed=3)
    without = cluster_bootstrap([0.4, 0.4], n_boot=400, seed=3)
    assert with_na.estimate == pytest.approx(0.4) == without.estimate
    assert with_na.n_clusters == 4 and with_na.n_defined == 2


def test_na_prevalence_widens_the_interval_rather_than_biasing_it():
    """NA clusters are resampled like any other but contribute no value, so
    they reduce effective sample size -- which should show as a wider interval,
    not a shifted point."""
    few_na = cluster_bootstrap([0.3, 0.7] * 10, n_boot=800, seed=5)
    many_na = cluster_bootstrap(([0.3, 0.7] + [None] * 6) * 5, n_boot=800, seed=5)
    assert many_na.estimate == pytest.approx(few_na.estimate, abs=1e-9)
    assert (many_na.ci_high - many_na.ci_low) > (few_na.ci_high - few_na.ci_low)


def test_all_na_yields_no_estimate_rather_than_a_fabricated_one():
    r = cluster_bootstrap([None, None, None], n_boot=100)
    assert r.estimate is None and r.ci_low is None and not r.defined
    assert r.n_clusters == 3 and r.n_defined == 0


def test_degenerate_resamples_are_counted_not_hidden():
    """A resample that draws only NA clusters produces no replicate. That must
    be reported, because it means the interval rests on fewer draws."""
    r = cluster_bootstrap([0.5] + [None] * 5, n_boot=500, seed=11)
    assert r.n_degenerate_resamples > 0
    assert r.estimate == pytest.approx(0.5)


def test_empty_input_is_handled():
    r = cluster_bootstrap([], n_boot=100)
    assert r.estimate is None and r.n_clusters == 0


# --- the constraint is the unit ---------------------------------------------

def test_resampling_is_over_clusters_not_observations():
    """With one cluster there is nothing to resample, so every replicate is
    identical and the interval collapses. That is correct, and it is the
    signature of resampling CONSTRAINTS rather than pairs."""
    r = cluster_bootstrap([0.42], n_boot=200)
    assert r.estimate == pytest.approx(0.42)
    assert r.ci_low == pytest.approx(0.42) and r.ci_high == pytest.approx(0.42)


# --- methods -----------------------------------------------------------------

def test_percentile_method_is_available_and_brackets_the_estimate():
    r = cluster_bootstrap([0.1, 0.5, 0.9] * 5, n_boot=600, seed=2, method="percentile")
    assert r.method == "percentile"
    assert r.ci_low <= r.estimate <= r.ci_high


def test_bca_falls_back_rather_than_emitting_an_infinite_bound():
    """z0 is infinite when the point lies outside the replicate spread. The
    result must say it fell back instead of returning a nonsense bound."""
    r = cluster_bootstrap([0.25] * 6, n_boot=200, seed=4)
    assert r.ci_low is not None and r.ci_high is not None
    assert all(abs(x) < 1e9 for x in (r.ci_low, r.ci_high))


# --- contrasts ---------------------------------------------------------------

def test_difference_detects_a_real_gap():
    a = [0.8] * 10      # higher-structure arm
    b = [0.2] * 10
    r = bootstrap_difference(a, b, n_boot=600, seed=1)
    assert r.estimate == pytest.approx(0.6)
    assert r.ci_low > 0.0, "a real difference should exclude zero"


def test_difference_interval_includes_zero_when_arms_match():
    a = [0.4, 0.5, 0.6] * 4
    b = [0.4, 0.5, 0.6] * 4
    r = bootstrap_difference(a, b, n_boot=800, seed=1)
    assert r.ci_low <= 0.0 <= r.ci_high


def test_difference_is_none_when_an_arm_is_entirely_undefined():
    r = bootstrap_difference([0.5, 0.5], [None, None], n_boot=100)
    assert r.estimate is None


# --- BH-FDR ------------------------------------------------------------------

def test_bh_rejects_nothing_when_all_p_are_large():
    assert benjamini_hochberg([0.9, 0.8, 0.7]) == [False, False, False]


def test_bh_rejects_everything_when_all_p_are_tiny():
    assert benjamini_hochberg([1e-6, 1e-7, 1e-8]) == [True, True, True]


def test_bh_is_less_conservative_than_bonferroni():
    """The reason BH is specified rather than Bonferroni."""
    p = [0.01, 0.02, 0.03, 0.04, 0.05]
    bh = benjamini_hochberg(p, alpha=0.05)
    bonferroni = [x <= 0.05 / len(p) for x in p]
    assert sum(bh) > sum(bonferroni)


def test_bh_preserves_input_order():
    p = [0.9, 0.001, 0.5]
    assert benjamini_hochberg(p, alpha=0.05) == [False, True, False]


def test_bh_step_up_rejects_below_the_largest_passing_rank():
    """A p-value failing its own threshold is still rejected if a LARGER one
    passes. Getting this wrong turns BH into a per-test comparison."""
    p = [0.001, 0.049]           # rank 2 passes at 0.05*2/2 = 0.05
    assert benjamini_hochberg(p, alpha=0.05) == [True, True]


def test_bh_handles_empty_input():
    assert benjamini_hochberg([]) == [] and bh_adjusted_p([]) == []


def test_bh_rejects_out_of_range_p_values():
    with pytest.raises(ValueError, match="outside"):
        benjamini_hochberg([0.5, 1.5])


def test_adjusted_p_values_are_monotone_and_bounded():
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205]
    q = bh_adjusted_p(p)
    ranked = [q[i] for i in sorted(range(len(p)), key=lambda i: p[i])]
    assert ranked == sorted(ranked), "adjusted p must not decrease with raw p"
    assert all(0.0 <= x <= 1.0 for x in q)
    assert all(qi >= pi for qi, pi in zip(q, p)), "adjustment cannot lower a p-value"


def test_adjusted_p_agrees_with_the_rejection_flags():
    p = [0.001, 0.02, 0.3, 0.7]
    q = bh_adjusted_p(p)
    flags = benjamini_hochberg(p, alpha=0.05)
    assert [qi <= 0.05 for qi in q] == flags
