"""Metric definitions (§4.10). `configs/analysis/metrics.yaml` names this file:
its three worked examples are marked "regression-tested in
tests/unit/test_metrics.py", and they are, below.

The rest enforces the three rules the module is built around: denominators are
explicit, undefined is not zero, and neither ABSTAIN nor INVALID may become a
contradiction.
"""

import datetime as dt
from dataclasses import dataclass
from itertools import combinations

import pytest
import yaml

from semintegrity.analysis.metrics import (
    AOCR_LABEL,
    abstention_rate,
    aocr,
    consistency_at_k,
    constraint_metrics,
    detector_coverage,
    expected_pairs,
    pcs,
    pscr,
    recovery_at_k,
    truth_accuracy,
)
from semintegrity.schemas.enums import ResponseLabel, Verdict
from semintegrity.schemas.response import CanonicalResponse
from semintegrity.utils.paths import p


@dataclass(frozen=True)
class FakePair:
    probe_a: str
    probe_b: str
    verdict: Verdict


def _resp(n: int, answer: str | None, label=ResponseLabel.ANSWER) -> CanonicalResponse:
    return CanonicalResponse(
        response_id=f"R-{n:012x}", constraint_id="K-C1-GEO-01",
        probe_id=f"K-C1-GEO-01-P{n:02d}", label=label, canonical_answer=answer,
        matched_alias=answer, candidates_found=[answer] if answer else [],
        canonicaliser_version="1.1", canonicaliser_sha256="0" * 64,
        canonicalised_at=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc),
    )


def _pairs_from_answers(answers: list[str | None]) -> tuple[list, list[FakePair]]:
    """Build responses and the D1-style verdicts they imply."""
    responses = [
        _resp(i, a, ResponseLabel.ANSWER if a else ResponseLabel.ABSTAIN)
        for i, a in enumerate(answers, start=1)
    ]
    results = []
    for a, b in combinations(responses, 2):
        if a.canonical_answer is None or b.canonical_answer is None:
            v = Verdict.NOT_APPLICABLE
        elif a.canonical_answer == b.canonical_answer:
            v = Verdict.SATISFIED
        else:
            v = Verdict.VIOLATION
        results.append(FakePair(a.probe_id, b.probe_id, v))
    return responses, results


# --- the worked examples from metrics.yaml ----------------------------------

@pytest.mark.parametrize(
    ("description", "answers", "want_pscr", "want_pcs"),
    [
        ("4/4 split, K=8", ["A"] * 4 + ["B"] * 4, 0.5714, 0.50),
        ("7 agree + 1 outlier", ["A"] * 7 + ["B"], 0.25, 0.875),
        ("8 distinct answers", [f"A{i}" for i in range(8)], 1.00, 0.125),
    ],
)
def test_worked_examples_from_the_proposal(description, answers, want_pscr, want_pcs):
    responses, results = _pairs_from_answers(answers)
    assert len(results) == 28, "K=8 must give 28 pairs"
    assert pscr(results) == pytest.approx(want_pscr, abs=5e-5), description
    assert pcs(responses, k=8) == pytest.approx(want_pcs), description


def test_the_worked_examples_in_the_config_match_this_file():
    """The config claims these are regression-tested here. Keep that true."""
    cfg = yaml.safe_load(p("configs/analysis/metrics.yaml").read_text(encoding="utf-8"))
    examples = cfg["pcs"]["worked_examples_from_proposal"]
    assert len(examples) == 3
    expected = {(0.5714, 0.50), (0.25, 0.875), (1.00, 0.125)}
    assert {(e["pscr"], e["pcs"]) for e in examples} == expected


def test_k_equals_eight_gives_twenty_eight_pairs():
    assert expected_pairs(8) == 28


# --- undefined is not zero ---------------------------------------------------

def test_pscr_is_none_not_zero_when_nothing_is_evaluable():
    """Q6: NA cells are carried as missing and never imputed. A 0.0 would read
    as 'perfectly consistent', the opposite of 'we could not tell'."""
    _, results = _pairs_from_answers([None] * 4)
    assert pscr(results) is None
    assert pscr([]) is None


def test_pcs_is_none_when_nothing_was_answered():
    responses, _ = _pairs_from_answers([None] * 4)
    assert pcs(responses, k=8) is None


@pytest.mark.parametrize("fn", [consistency_at_k, aocr])
def test_aggregates_are_none_when_every_constraint_is_undefined(fn):
    assert fn([None, None]) is None
    assert fn([]) is None


def test_undefined_constraints_leave_both_numerator_and_denominator():
    """Two of four defined, one clean: 1/2, not 1/4."""
    assert consistency_at_k([0.0, 0.5, None, None]) == pytest.approx(0.5)
    assert aocr([0.0, 0.5, None, None]) == pytest.approx(0.5)


# --- ABSTAIN and INVALID are never contradictions ---------------------------

@pytest.mark.parametrize("label", [ResponseLabel.ABSTAIN, ResponseLabel.INVALID])
def test_non_answers_never_become_contradictions(label):
    """They leave the numerator AND the denominator."""
    # The responses are built for clarity about what the verdicts represent;
    # the metric reads the verdicts.
    _ = [_resp(1, "A"), _resp(2, "A"), _resp(3, None, label)]
    results = [
        FakePair("K-C1-GEO-01-P01", "K-C1-GEO-01-P02", Verdict.SATISFIED),
        FakePair("K-C1-GEO-01-P01", "K-C1-GEO-01-P03", Verdict.NOT_APPLICABLE),
        FakePair("K-C1-GEO-01-P02", "K-C1-GEO-01-P03", Verdict.NOT_APPLICABLE),
    ]
    assert pscr(results) == 0.0          # the one evaluable pair agrees
    assert detector_coverage(results) == pytest.approx(1 / 3)


def test_a_model_that_abstains_everywhere_is_not_scored_as_consistent():
    """The failure mode the reliability triad exists to prevent."""
    responses, results = _pairs_from_answers([None] * 8)
    assert pscr(results) is None, "must be undefined, not 0.0"
    assert abstention_rate(responses) == 1.0


# --- truth accuracy ----------------------------------------------------------

def test_truth_accuracy_counts_negated_as_answered_and_wrong():
    """"the capital is not Canberra", when it is, is a WRONG answer -- not a
    non-answer. Folding it into abstention would flatter the model."""
    responses = [
        _resp(1, "Canberra"),
        _resp(2, "Canberra", ResponseLabel.NEGATED),
        _resp(3, None, ResponseLabel.ABSTAIN),
    ]
    assert truth_accuracy(responses, "Canberra") == pytest.approx(0.5)  # 1 of 2 answered


def test_truth_accuracy_is_none_when_nothing_was_answered():
    assert truth_accuracy([_resp(1, None, ResponseLabel.ABSTAIN)], "Canberra") is None


def test_truth_accuracy_and_pscr_are_independent():
    """A model can be perfectly consistent and perfectly wrong. Keeping these
    separate is what §4.10's triad is for."""
    responses, results = _pairs_from_answers(["Sydney"] * 8)
    assert pscr(results) == 0.0
    assert truth_accuracy(responses, "Canberra") == 0.0


# --- PCS denominator ---------------------------------------------------------

def test_pcs_denominator_is_k_not_the_answered_count():
    """Otherwise a model could raise its PCS by abstaining more."""
    responses = [_resp(1, "A"), _resp(2, "A")] + [
        _resp(i, None, ResponseLabel.ABSTAIN) for i in range(3, 9)
    ]
    assert pcs(responses, k=8) == pytest.approx(2 / 8)
    assert pcs(responses) == pytest.approx(2 / 8)   # len(responses) == 8 here


def test_pcs_ignores_negated_because_it_names_no_cluster():
    responses = [_resp(1, "A"), _resp(2, "A"), _resp(3, "A", ResponseLabel.NEGATED)]
    assert pcs(responses, k=3) == pytest.approx(2 / 3)


# --- abstention / coverage ---------------------------------------------------

def test_abstention_denominator_includes_invalid():
    responses = [_resp(1, "A"), _resp(2, None, ResponseLabel.ABSTAIN),
                 _resp(3, None, ResponseLabel.INVALID), _resp(4, "A")]
    assert abstention_rate(responses) == pytest.approx(0.25)


def test_coverage_is_none_for_no_pairs_not_zero():
    assert detector_coverage([]) is None


# --- AOCR --------------------------------------------------------------------

def test_aocr_is_the_complement_of_consistency_at_k():
    values = [0.0, 0.1, 0.0, 0.5]
    assert aocr(values) + consistency_at_k(values) == pytest.approx(1.0)


def test_aocr_carries_its_k_dependence_label():
    assert "K-DEPENDENT" in AOCR_LABEL and "saturates" in AOCR_LABEL


# --- recovery@k --------------------------------------------------------------

def test_recovery_at_k_rises_with_k():
    _, results = _pairs_from_answers(["A"] * 7 + ["B"])
    ids = [f"K-C1-GEO-01-P{i:02d}" for i in range(1, 9)]
    r2 = recovery_at_k(results, ids, 2, draws=4000, seed=1)
    r4 = recovery_at_k(results, ids, 4, draws=4000, seed=1)
    r8 = recovery_at_k(results, ids, 8, draws=4000, seed=1)
    assert r2 < r4 < r8
    assert r8 == pytest.approx(1.0), "the full budget must always find it"


def test_recovery_at_k_is_zero_when_there_is_nothing_to_recover():
    _, results = _pairs_from_answers(["A"] * 8)
    assert recovery_at_k(results, [f"K-C1-GEO-01-P{i:02d}" for i in range(1, 9)], 4) == 0.0


def test_recovery_at_k_is_none_for_impossible_budgets():
    _, results = _pairs_from_answers(["A"] * 4)
    ids = [f"K-C1-GEO-01-P{i:02d}" for i in range(1, 5)]
    assert recovery_at_k(results, ids, 1) is None       # a pair needs 2
    assert recovery_at_k(results, ids, 99) is None      # more than exist


def test_recovery_at_k_is_reproducible_under_a_seed():
    _, results = _pairs_from_answers(["A"] * 6 + ["B", "C"])
    ids = [f"K-C1-GEO-01-P{i:02d}" for i in range(1, 9)]
    a = recovery_at_k(results, ids, 3, draws=500, seed=42)
    b = recovery_at_k(results, ids, 3, draws=500, seed=42)
    assert a == b


# --- the bundle --------------------------------------------------------------

def test_constraint_metrics_reconciles_its_denominators():
    responses, results = _pairs_from_answers(["A"] * 6 + [None, None])
    m = constraint_metrics("K-C1-GEO-01", "C1", "geography", responses, results, "A", k=8)
    assert m.n_responses == 8
    assert m.n_answer == 6 and m.n_abstain == 2
    assert m.n_pairs == 28
    assert m.n_evaluable_pairs == 15        # C(6,2)
    assert m.n_contradictory_pairs == 0
    assert m.pscr == 0.0 and m.pscr_defined
    assert m.pcs == pytest.approx(6 / 8)
    assert m.abstention_rate == pytest.approx(0.25)


def test_constraint_metrics_rejects_inconsistent_counts():
    """The reconciliation is a real check, not decoration."""
    from semintegrity.analysis.metrics import ConstraintMetrics

    bad = ConstraintMetrics(
        constraint_id="X", constraint_class="C1", domain="geography",
        n_responses=8, n_answer=6, n_negated=0, n_abstain=1, n_invalid=0, n_other=0,
        n_pairs=28, n_evaluable_pairs=15, n_contradictory_pairs=0,
        pscr=0.0, pcs=0.75, truth_accuracy=1.0, abstention_rate=0.125, coverage=0.5,
    )
    with pytest.raises(ValueError, match="labels sum to 7"):
        bad.check_denominators()


def test_a_perfectly_consistent_synthetic_model():
    responses, results = _pairs_from_answers(["Canberra"] * 8)
    m = constraint_metrics("K-C1-GEO-01", "C1", "geography", responses, results,
                           "Canberra", k=8)
    assert m.pscr == 0.0
    assert m.pcs == 1.0
    assert m.truth_accuracy == 1.0
    assert m.abstention_rate == 0.0
    assert m.coverage == 1.0


def test_a_deliberately_contradictory_synthetic_model_is_detected():
    responses, results = _pairs_from_answers(["Canberra"] * 4 + ["Sydney"] * 4)
    m = constraint_metrics("K-C1-GEO-01", "C1", "geography", responses, results,
                           "Canberra", k=8)
    assert m.n_contradictory_pairs == 16
    assert m.pscr == pytest.approx(16 / 28)
    assert m.pcs == pytest.approx(0.5)
    assert m.truth_accuracy == pytest.approx(0.5)
