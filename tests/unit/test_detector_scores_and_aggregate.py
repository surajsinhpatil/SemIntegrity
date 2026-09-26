"""Detector scoring interfaces (§4.10) and aggregation (§4.11, ADR-0009).

The detector-scoring tests are mostly about REFUSAL: none of these numbers can
be reported yet, because the gold standard is human annotation and none exists.
The interface is written now so the analysis is fixed before the labels arrive
rather than shaped by them.
"""

import pytest

from semintegrity.analysis.aggregate import (
    CLASS_IS_CATEGORICAL,
    binomial_cells,
    by_class,
    by_domain,
    group_by,
    pair_factor_cell,
)
from semintegrity.analysis.detector_scores import (
    GoldStandardMissing,
    average_precision,
    confusion_matrix,
    require_human_gold,
    score_detector,
)
from semintegrity.analysis.metrics import ConstraintMetrics


def _row(cid, cls, domain, pscr):
    return ConstraintMetrics(
        constraint_id=cid, constraint_class=cls, domain=domain,
        n_responses=8, n_answer=8, n_negated=0, n_abstain=0, n_invalid=0, n_other=0,
        n_pairs=28, n_evaluable_pairs=28,
        n_contradictory_pairs=round((pscr or 0) * 28),
        pscr=pscr, pcs=1.0, truth_accuracy=1.0, abstention_rate=0.0, coverage=1.0,
    )


# --- gold standard refusal ---------------------------------------------------

def test_scoring_against_anything_but_human_gold_is_refused():
    """Scoring against another detector measures AGREEMENT, not accuracy."""
    with pytest.raises(GoldStandardMissing, match="not human annotation"):
        score_detector("D2", [True], [True], gold_source="d1_output")
    with pytest.raises(GoldStandardMissing):
        require_human_gold("model_consensus")


@pytest.mark.parametrize("source", ["human_adjudicated", "human_consensus"])
def test_adjudicated_human_gold_is_accepted(source):
    require_human_gold(source)   # must not raise


# --- confusion matrix --------------------------------------------------------

def test_confusion_matrix_counts():
    cm = confusion_matrix([True, True, False, False], [True, False, True, False])
    assert (cm.tp, cm.fp, cm.fn, cm.tn) == (1, 1, 1, 1)
    assert cm.n == 4
    assert cm.precision == 0.5 and cm.recall == 0.5 and cm.f1 == 0.5


def test_perfect_detector():
    cm = confusion_matrix([True, False, True], [True, False, True])
    assert cm.precision == 1.0 and cm.recall == 1.0 and cm.f1 == 1.0


def test_precision_is_none_not_zero_when_nothing_is_predicted_positive():
    """0/0 is undefined. A 0.0 would say 'every prediction was wrong' when no
    prediction was made."""
    cm = confusion_matrix([False, False], [True, False])
    assert cm.precision is None
    assert cm.recall == 0.0          # there WAS a positive to find, and it was missed
    assert cm.f1 is None


def test_recall_is_none_when_the_gold_set_has_no_positives():
    cm = confusion_matrix([True, False], [False, False])
    assert cm.recall is None and cm.precision == 0.0


def test_mismatched_lengths_are_rejected():
    with pytest.raises(ValueError, match="2 predictions vs 3"):
        confusion_matrix([True, False], [True, False, True])


# --- AUPRC and Q7 ------------------------------------------------------------

def test_auprc_is_refused_for_binary_detectors():
    """Q7: D0 and D1 have a single operating point. An AUPRC would interpolate
    between two points and mean nothing."""
    for detector in ("D0", "D1"):
        s = score_detector(detector, [True, False], [True, False],
                           gold_source="human_adjudicated", scores=[0.9, 0.1])
        assert s.auprc is None
        assert "single operating point" in s.auprc_note


def test_auprc_is_computed_for_scored_detectors():
    s = score_detector("D2", [True, True, False, False], [True, False, True, False],
                       gold_source="human_adjudicated", scores=[0.9, 0.8, 0.4, 0.1])
    assert s.auprc is not None and 0.0 <= s.auprc <= 1.0


def test_auprc_is_none_when_scores_are_absent():
    s = score_detector("D3", [True], [True], gold_source="human_adjudicated")
    assert s.auprc is None and "no continuous scores" in s.auprc_note


def test_perfect_ranking_gives_auprc_one():
    assert average_precision([0.9, 0.8, 0.2, 0.1],
                             [True, True, False, False]) == pytest.approx(1.0)


def test_auprc_is_none_without_positives():
    assert average_precision([0.9, 0.1], [False, False]) is None


def test_worst_ranking_scores_below_perfect():
    good = average_precision([0.9, 0.8, 0.2, 0.1], [True, True, False, False])
    bad = average_precision([0.9, 0.8, 0.2, 0.1], [False, False, True, True])
    assert bad < good


# --- aggregation -------------------------------------------------------------

def test_by_class_averages_over_constraints():
    rows = [_row("a", "C1", "geography", 0.2), _row("b", "C1", "science", 0.4),
            _row("c", "C2", "geography", 0.6)]
    agg = by_class(rows)
    assert agg["C1"].mean == pytest.approx(0.3) and agg["C1"].n_constraints == 2
    assert agg["C2"].mean == pytest.approx(0.6)


def test_undefined_constraints_are_excluded_and_counted():
    """An aggregate must arrive with the number of cells it could not use."""
    rows = [_row("a", "C1", "geography", 0.4), _row("b", "C1", "science", None)]
    agg = by_class(rows)["C1"]
    assert agg.mean == pytest.approx(0.4)
    assert agg.n_constraints == 2 and agg.n_defined == 1 and agg.n_undefined == 1
    assert agg.undefined_rate == pytest.approx(0.5)


def test_an_all_undefined_group_has_no_mean():
    agg = by_class([_row("a", "C3", "geography", None)])["C3"]
    assert agg.mean is None and not agg.defined


def test_by_domain_and_arbitrary_grouping():
    rows = [_row("a", "C1", "geography", 0.2), _row("b", "C2", "geography", 0.4),
            _row("c", "C1", "science", 0.9)]
    assert by_domain(rows)["geography"].mean == pytest.approx(0.3)
    agg = group_by(rows, lambda r: r.domain, lambda r: r.coverage)
    assert agg["science"].mean == pytest.approx(1.0)


def test_classes_are_documented_as_categorical():
    assert "CATEGORICAL" in CLASS_IS_CATEGORICAL and "never a trend" in CLASS_IS_CATEGORICAL


# --- pair-factor cells (ADR-0009) -------------------------------------------

@pytest.mark.parametrize(
    ("a", "b", "cell"),
    [
        ("affirmative", "affirmative", "aff-aff"),
        ("affirmative", "negated", "aff-neg"),
        ("negated", "affirmative", "aff-neg"),      # unordered
        ("negated", "negated", "neg-neg"),
        ("declarative", "cloze", "clz-dec"),
        ("direct", "reverse", "dir-rev"),
    ],
)
def test_pair_factor_cells_are_unordered(a, b, cell):
    """A pair is unordered, so (aff, neg) and (neg, aff) are ONE cell. Treating
    them separately would split one cell's evidence in two."""
    assert pair_factor_cell(a, b) == cell
    assert pair_factor_cell(b, a) == cell


def test_unknown_factor_levels_are_rejected():
    with pytest.raises(ValueError, match="unknown factor level"):
        pair_factor_cell("affirmative", "subjunctive")


def test_binomial_cells_count_contradictions_over_evaluable_pairs():
    pairs = [
        {"level_a": "affirmative", "level_b": "affirmative", "is_contradiction": True},
        {"level_a": "affirmative", "level_b": "affirmative", "is_contradiction": False},
        {"level_a": "affirmative", "level_b": "negated", "is_contradiction": True},
    ]
    cells = {c.cell: c for c in
             binomial_cells("K-C1-GEO-01", "C1", "geography", pairs, "polarity")}
    assert cells["aff-aff"].contradictions == 1 and cells["aff-aff"].denominator == 2
    assert cells["aff-aff"].rate == pytest.approx(0.5)
    assert cells["aff-neg"].denominator == 1


def test_cells_with_no_evaluable_pairs_contribute_no_row():
    """statistics.yaml: "Cells with zero evaluable pairs contribute no row."
    A zero-denominator row would either crash the fit or be silently imputed."""
    cells = binomial_cells("K-C1-GEO-01", "C1", "geography", [], "polarity")
    assert cells == []


def test_every_cell_has_a_positive_denominator():
    pairs = [{"level_a": "direct", "level_b": "reverse", "is_contradiction": False}]
    for cell in binomial_cells("K-C1-GEO-01", "C1", "geography", pairs, "direction"):
        assert cell.denominator > 0
        assert cell.contradictions <= cell.denominator
