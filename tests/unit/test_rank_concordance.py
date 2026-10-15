"""D2's rank concordance against a detector partition (ADR-0023 D6).

D2 reports a continuous score and no verdict, because its per-class threshold
was calibrated on human-labelled dev data that does not exist. What remains
answerable is whether the score ORDERS pairs the way another detector
PARTITIONS them.

The hazards these tests exist to prevent:
  * the statistic being read as accuracy -- the reference is a detector;
  * 0.5 being returned for "undefined", when 0.5 already means "no ordering
    relationship";
  * pairs the reference never decided being folded into one side;
  * a pair-level interval, which statistics.yaml forbids.
"""

from __future__ import annotations

import pytest

from semintegrity.analysis.rank_concordance import (
    MIN_PER_SIDE,
    ScoredPair,
    disagreement_examples,
    per_constraint_concordance,
    rank_concordance,
    report,
)
from semintegrity.schemas.enums import Verdict

V, S, NA = Verdict.VIOLATION, Verdict.SATISFIED, Verdict.NOT_APPLICABLE


def _p(i, score, verdict, cid="K-C1-GEO-01"):
    return ScoredPair(pair_id=f"{cid}-P01xP{i:02d}", constraint_id=cid,
                      score=score, reference_verdict=verdict)


# --- the statistic -------------------------------------------------------

def test_perfect_separation_is_one():
    pairs = [_p(1, 0.9, V), _p(2, 0.8, V), _p(3, 0.2, S), _p(4, 0.1, S)]
    c = rank_concordance(pairs)
    assert c.estimate == 1.0
    assert c.n_violation == 2 and c.n_satisfied == 2


def test_perfectly_inverted_separation_is_zero():
    """A score that orders pairs exactly backwards. Not 0.5."""
    pairs = [_p(1, 0.1, V), _p(2, 0.2, V), _p(3, 0.8, S), _p(4, 0.9, S)]
    assert rank_concordance(pairs).estimate == 0.0


def test_all_ties_is_one_half_and_the_ties_are_counted():
    pairs = [_p(1, 0.5, V), _p(2, 0.5, V), _p(3, 0.5, S), _p(4, 0.5, S)]
    c = rank_concordance(pairs)
    assert c.estimate == 0.5
    assert c.n_ties == 4, "every cross-pair comparison is a tie"


def test_ties_are_credited_one_half():
    pairs = [_p(1, 0.6, V), _p(2, 0.4, V), _p(3, 0.4, S), _p(4, 0.2, S)]
    # comparisons: .6>.4 win, .6>.2 win, .4==.4 tie, .4>.2 win -> (3 + 0.5)/4
    assert rank_concordance(pairs).estimate == pytest.approx(3.5 / 4)


# --- undefined must not look like 0.5 -----------------------------------

def test_a_one_sided_partition_is_undefined_not_one_half():
    """0.5 already means 'no ordering relationship'. Undefined must differ."""
    pairs = [_p(1, 0.9, V), _p(2, 0.8, V), _p(3, 0.7, V)]
    c = rank_concordance(pairs)
    assert c.estimate is None, "must not be 0.5"
    assert c.defined is False
    assert "NOT 0.5" in c.refusal
    assert str(MIN_PER_SIDE) in c.refusal


def test_one_pair_per_side_is_refused():
    pairs = [_p(1, 0.9, V), _p(2, 0.1, S)]
    assert rank_concordance(pairs).estimate is None


# --- "not decided" is not "compatible" ----------------------------------

def test_undecided_pairs_are_excluded_and_counted_not_folded_in():
    pairs = [
        _p(1, 0.9, V), _p(2, 0.8, V),
        _p(3, 0.2, S), _p(4, 0.1, S),
        _p(5, 0.99, NA),     # reference reached no decision
        _p(6, 0.98, None),   # reference was never asked
    ]
    c = rank_concordance(pairs)
    assert c.n_excluded_undecided == 2
    assert c.n_violation == 2 and c.n_satisfied == 2
    assert c.estimate == 1.0, "the excluded high scores must not perturb it"


def test_a_non_finite_score_raises_rather_than_propagating():
    pairs = [_p(1, float("nan"), V), _p(2, 0.8, V), _p(3, 0.2, S), _p(4, 0.1, S)]
    with pytest.raises(ValueError, match="non-finite"):
        rank_concordance(pairs)


# --- this is not accuracy -----------------------------------------------

def test_the_result_declares_that_it_is_not_accuracy():
    pairs = [_p(1, 0.9, V), _p(2, 0.8, V), _p(3, 0.2, S), _p(4, 0.1, S)]
    assert rank_concordance(pairs).is_accuracy is False


def test_the_module_does_not_import_the_gold_scoring_module():
    """detector_scores guards precision/recall/F1/AUPRC behind
    require_human_gold. A concordance figure must never be reachable through it."""
    import ast

    from semintegrity.utils.paths import project_root

    path = project_root() / "src" / "semintegrity" / "analysis" / "rank_concordance.py"
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("detector_scores" in m for m in imported)
    for forbidden in ("average_precision", "confusion_matrix", "score_detector"):
        assert forbidden not in imported


def test_the_report_states_its_interpretation_limit():
    pairs = [_p(1, 0.9, V), _p(2, 0.8, V), _p(3, 0.2, S), _p(4, 0.1, S)]
    out = report({"D1": pairs}, n_boot=100, seed=1)
    assert out["is_accuracy"] is False
    assert out["reference_is_ground_truth"] is False
    assert "does not mean either is" in out["interpretation_limit"]
    assert out["references"]["D1"]["clustered"]["unit"] == "constraint"


# --- the clustered unit --------------------------------------------------

def test_per_constraint_values_are_one_per_constraint():
    pairs = (
        [_p(i, 0.9, V, "K-C1-GEO-01") for i in (1, 2)]
        + [_p(i, 0.1, S, "K-C1-GEO-01") for i in (3, 4)]
        + [_p(i, 0.1, V, "K-C2-GEO-01") for i in (1, 2)]
        + [_p(i, 0.9, S, "K-C2-GEO-01") for i in (3, 4)]
    )
    cids, values = per_constraint_concordance(pairs)
    assert cids == ["K-C1-GEO-01", "K-C2-GEO-01"]
    assert values == [1.0, 0.0]


def test_a_one_sided_constraint_contributes_none_not_one_half():
    pairs = (
        [_p(i, 0.9, V, "K-C1-GEO-01") for i in (1, 2)]
        + [_p(i, 0.1, S, "K-C1-GEO-01") for i in (3, 4)]
        + [_p(i, 0.5, V, "K-C2-GEO-01") for i in (1, 2, 3)]   # one-sided
    )
    _, values = per_constraint_concordance(pairs)
    assert values == [1.0, None]


def test_the_clustered_interval_resamples_constraints():
    from semintegrity.analysis.bootstrap import cluster_bootstrap

    pairs = []
    for k in range(1, 9):
        cid = f"K-C1-GEO-{k:02d}"
        hi, lo = (0.9, 0.1) if k % 2 == 0 else (0.1, 0.9)
        pairs += [_p(1, hi, V, cid), _p(2, hi, V, cid),
                  _p(3, lo, S, cid), _p(4, lo, S, cid)]
    _, values = per_constraint_concordance(pairs)
    res = cluster_bootstrap(values, n_boot=200, seed=1)
    assert res.n_clusters == 8
    assert res.estimate == pytest.approx(0.5)


# --- the interesting part: where they diverge ----------------------------

def test_disagreement_examples_attach_no_verdict():
    pairs = [_p(1, 0.05, V), _p(2, 0.9, V), _p(3, 0.95, S), _p(4, 0.1, S)]
    ex = disagreement_examples(pairs, limit=1)
    assert ex["reference_violation_lowest_score"][0]["score"] == 0.05
    assert ex["reference_satisfied_highest_score"][0]["score"] == 0.95
    for rows in ex.values():
        for row in rows:
            assert "error" not in row and "correct" not in row
