"""D4 — distributional instability (§4.8.6). EXPLORATORY, never a detector.

The first test group is the important one: `d4_distributional.yaml` sets
`IS_A_CONTRADICTION_DETECTOR: false` and says it is "enforced by tests". These
are those tests. They check the ABSENCE of a verdict interface, so D4 output
cannot be handed to code that expects a detector.
"""

import math

import pytest

from semintegrity.detectors.d4 import distributional as d4
from semintegrity.detectors.d4.distributional import (
    D4Distributional,
    SoftmaxOverMeanLogprob,
    jensen_shannon_divergence,
)


class FlatScorer:
    name = "flat-test-scorer"

    def __init__(self, table):
        self.table = table

    def mean_token_logprobs(self, prompt, candidates):
        return list(self.table[prompt])


# --- D4 IS NOT A DETECTOR ----------------------------------------------------

def test_module_declares_it_is_not_a_contradiction_detector():
    assert d4.IS_A_CONTRADICTION_DETECTOR is False


def test_config_and_module_agree_that_d4_is_not_a_detector():
    import yaml

    from semintegrity.utils.paths import p

    cfg = yaml.safe_load(p("configs/detectors/d4_distributional.yaml").read_text())
    assert cfg["IS_A_CONTRADICTION_DETECTOR"] is False
    assert cfg["IS_A_CONTRADICTION_DETECTOR"] is d4.IS_A_CONTRADICTION_DETECTOR


@pytest.mark.parametrize("forbidden", ["check_pair", "check_all_pairs", "check_set", "verdict"])
def test_d4_exposes_no_verdict_interface(forbidden):
    """The enforcement the config asks for: D4 must not be callable as a
    detector even by mistake."""
    assert not hasattr(D4Distributional, forbidden), (
        f"D4Distributional exposes {forbidden!r}; §4.8.6 forbids it being used "
        "as a contradiction detector"
    )


def test_results_carry_an_interpretation_limit():
    """Every record states the limit, so a number cannot travel without it."""
    an = D4Distributional(
        FlatScorer({"p1": [-1.0, -2.0], "p2": [-1.0, -2.0]}),
        SoftmaxOverMeanLogprob(temperature=1.0),
    ).analyse("K-C1-GEO-01", {"P01": "p1", "P02": "p2"}, ["Canberra", "Sydney"])
    assert "EXPLORATORY" in an.interpretation_limit
    assert "NOT evidence of a contradiction" in an.interpretation_limit


# --- Q5: the distribution mapping is NOT chosen here -------------------------

def test_builder_has_no_default():
    """Q5 is unresolved and the mapping is a preregistered quantity; a default
    would settle it by import."""
    import inspect

    params = inspect.signature(D4Distributional.__init__).parameters
    assert params["builder"].default is inspect.Parameter.empty


def test_temperature_must_be_stated_and_positive():
    import inspect

    assert inspect.signature(SoftmaxOverMeanLogprob).parameters[
        "temperature"].default is inspect.Parameter.empty
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError, match="temperature"):
            SoftmaxOverMeanLogprob(temperature=bad)


def test_temperature_changes_jsd_which_is_why_it_is_preregistered():
    """The concrete reason Q5 matters: the same log-probabilities give
    different divergences under different T, so the choice is not cosmetic."""
    lp_a, lp_b = [-1.0, -3.0], [-3.0, -1.0]
    jsds = []
    for t in (0.5, 1.0, 4.0):
        builder = SoftmaxOverMeanLogprob(temperature=t)
        jsds.append(jensen_shannon_divergence(
            builder.to_distribution(lp_a), builder.to_distribution(lp_b)))
    assert len({round(v, 6) for v in jsds}) == 3, "T must materially change JSD"
    assert jsds[0] > jsds[-1], "lower temperature sharpens, raising divergence"


# --- the softmax mapping -----------------------------------------------------

def test_distribution_sums_to_one_and_is_ordered_by_logprob():
    d = SoftmaxOverMeanLogprob(temperature=1.0).to_distribution([-1.0, -2.0, -5.0])
    assert math.isclose(sum(d), 1.0)
    assert d[0] > d[1] > d[2]


def test_distribution_is_numerically_stable_for_extreme_logprobs():
    d = SoftmaxOverMeanLogprob(temperature=1.0).to_distribution([-1000.0, -1001.0])
    assert math.isclose(sum(d), 1.0) and all(math.isfinite(x) for x in d)


def test_empty_candidate_set_is_rejected():
    with pytest.raises(ValueError, match="empty candidate set"):
        SoftmaxOverMeanLogprob(temperature=1.0).to_distribution([])


# --- JSD ---------------------------------------------------------------------

def test_identical_distributions_have_zero_divergence():
    assert jensen_shannon_divergence([0.5, 0.5], [0.5, 0.5]) == pytest.approx(0.0, abs=1e-12)


def test_disjoint_distributions_have_maximal_divergence_of_one():
    """Base 2, so the maximum is exactly 1."""
    assert jensen_shannon_divergence([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)


def test_jsd_is_symmetric():
    p, q = [0.7, 0.2, 0.1], [0.1, 0.3, 0.6]
    assert jensen_shannon_divergence(p, q) == pytest.approx(jensen_shannon_divergence(q, p))


def test_jsd_is_bounded_in_zero_one():
    for p, q in ([[0.9, 0.1], [0.1, 0.9]], [[0.5, 0.5], [0.4, 0.6]], [[1.0, 0.0], [1.0, 0.0]]):
        assert 0.0 <= jensen_shannon_divergence(p, q) <= 1.0


@pytest.mark.parametrize(
    ("p", "q", "match"),
    [
        ([0.5, 0.5], [1.0], "different supports"),
        ([0.5, 0.4], [0.5, 0.5], "sums to"),
        ([1.5, -0.5], [0.5, 0.5], "negative"),
        ([], [], "empty"),
    ],
)
def test_malformed_distributions_are_rejected(p, q, match):
    with pytest.raises(ValueError, match=match):
        jensen_shannon_divergence(p, q)


# --- aggregation -------------------------------------------------------------

def test_identical_probes_give_zero_mean_pairwise_jsd():
    """The D4 analogue of the perfect-model invariant: a model whose candidate
    distribution does not move across probes has no distributional instability."""
    scorer = FlatScorer({f"p{i}": [-0.5, -2.0, -4.0] for i in range(1, 5)})
    an = D4Distributional(scorer, SoftmaxOverMeanLogprob(temperature=1.0)).analyse(
        "K-C1-GEO-01", {f"P0{i}": f"p{i}" for i in range(1, 5)},
        ["Canberra", "Sydney", "Melbourne"],
    )
    assert an.n_probes == 4
    assert len(an.pairwise) == 6
    assert an.mean_pairwise_jsd == pytest.approx(0.0, abs=1e-12)


def test_divergent_probes_are_detected_as_instability():
    scorer = FlatScorer({"p1": [-0.1, -9.0], "p2": [-9.0, -0.1]})
    an = D4Distributional(scorer, SoftmaxOverMeanLogprob(temperature=1.0)).analyse(
        "K-C1-GEO-01", {"P01": "p1", "P02": "p2"}, ["Canberra", "Sydney"])
    assert an.mean_pairwise_jsd > 0.9
    assert an.max_pairwise_jsd == an.mean_pairwise_jsd    # single pair


def test_a_single_probe_yields_no_pairwise_value_rather_than_zero():
    """Undefined is not zero: one probe has no pair to compare."""
    an = D4Distributional(
        FlatScorer({"p1": [-1.0, -2.0]}), SoftmaxOverMeanLogprob(temperature=1.0)
    ).analyse("K-C1-GEO-01", {"P01": "p1"}, ["Canberra", "Sydney"])
    assert an.mean_pairwise_jsd is None and an.max_pairwise_jsd is None


def test_top_candidate_can_agree_while_distributions_differ():
    """The config's own disclaimer, made concrete: a large JSD does not imply
    the model would answer differently."""
    scorer = FlatScorer({"p1": [-0.1, -1.0], "p2": [-0.1, -8.0]})
    d4d = D4Distributional(scorer, SoftmaxOverMeanLogprob(temperature=1.0))
    a = d4d.distribution_for("P01", "p1", ["Canberra", "Sydney"])
    b = d4d.distribution_for("P02", "p2", ["Canberra", "Sydney"])
    assert a.top_candidate == b.top_candidate == "Canberra"
    assert jensen_shannon_divergence(a.probabilities, b.probabilities) > 0.05


def test_empty_candidate_set_is_a_scope_error():
    """§4.8.6 is Track A only, because it needs a defined candidate set."""
    with pytest.raises(ValueError, match="closed candidate set"):
        D4Distributional(
            FlatScorer({"p1": []}), SoftmaxOverMeanLogprob(temperature=1.0)
        ).distribution_for("P01", "p1", [])


def test_scorer_returning_the_wrong_number_of_scores_is_rejected():
    with pytest.raises(ValueError, match="returned 2 scores for 3"):
        D4Distributional(
            FlatScorer({"p1": [-1.0, -2.0]}), SoftmaxOverMeanLogprob(temperature=1.0)
        ).distribution_for("P01", "p1", ["a", "b", "c"])
