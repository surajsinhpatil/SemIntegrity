"""Per-pair detector concordance (§4.8.2).

The distinctions these tests exist to defend are the ones a detector-agreement
number is easiest to get wrong:

* a detector that was never ASKED about a pair is not a detector that could not
  DECIDE it -- D0 is asked only about ANSWER/ANSWER pairs, D1 and D3 also take
  NEGATED;
* two detectors with the IDENTICAL contradiction rate can differ on every pair,
  so concordance is never inferred from marginals;
* kappa is undefined when one label covers everything, and a number emitted
  there would be read as disagreement.
"""

from __future__ import annotations

import datetime as dt

from semintegrity.analysis.detector_agreement import (
    Concordance,
    PairVerdicts,
    cohens_kappa,
    concordance,
    pair_table,
    per_constraint_agreement,
)
from semintegrity.schemas.enums import ConstraintClass, Domain, ResponseLabel, Verdict
from semintegrity.schemas.response import CanonicalResponse
from tests.fixtures.synthetic_benchmark import make_constraint

D0, D1, D3 = "D0", "D1", "D3"


def _constraint():
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    return c.model_copy(update={
        "answer_space": ["Canberra", "Sydney", "Melbourne"], "gold_answer": "Canberra",
        "gold_proposition": "The capital city of Australia is Canberra.",
    })


def _resp(n: int, answer: str, label: ResponseLabel = ResponseLabel.ANSWER):
    return CanonicalResponse(
        response_id=f"R-{n:012x}", constraint_id="K-C1-GEO-01",
        probe_id=f"K-C1-GEO-01-P0{n}", label=label,
        canonical_answer=answer, matched_alias=answer, candidates_found=[answer],
        canonicaliser_version="1.1", canonicaliser_sha256="0" * 64,
        canonicalised_at=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc),
    )


def _row(pid: str, va, vb, vc=None, cid="K-C1-GEO-01") -> PairVerdicts:
    return PairVerdicts(pair_id=pid, constraint_id=cid, constraint_class="C1",
                        verdicts={D0: va, D1: vb, D3: vc})


# --- the distinction that is easiest to lose ------------------------------

def test_not_asked_and_undecided_are_counted_separately():
    rows = [
        _row("p1", None, Verdict.VIOLATION),            # D0 never asked
        _row("p2", Verdict.NOT_APPLICABLE, Verdict.VIOLATION),  # asked, no decision
    ]
    c = concordance(rows, D0, D1)
    assert c.n_a_not_asked == 1
    assert c.n_a_undecided == 1
    assert c.n_joint == 0, "neither pair is jointly decided"
    assert c.raw_agreement is None, "undefined, not zero"


def test_d0_is_not_asked_about_pairs_holding_a_negation():
    """D1 and D3 take NEGATED; D0's predicates are over definite answers only."""
    canon = [
        _resp(1, "Canberra"),
        _resp(2, "Sydney", ResponseLabel.NEGATED),
        _resp(3, "Canberra"),
    ]
    rows = pair_table(_constraint(), canon)   # no kb/registry: D0 asked about nothing
    assert len(rows) == 3
    assert all(r.verdicts[D0] is None for r in rows)
    # D1 still answers every pair.
    assert all(r.verdicts[D1] is not None for r in rows)


def test_d3_is_none_where_the_judge_never_saw_the_pair():
    canon = [_resp(1, "Canberra"), _resp(2, "Sydney"), _resp(3, "Canberra")]
    judged = {"K-C1-GEO-01-P01xP02": Verdict.VIOLATION}
    rows = pair_table(_constraint(), canon, d3_verdicts=judged)
    got = {r.pair_id: r.verdicts[D3] for r in rows}
    assert got["K-C1-GEO-01-P01xP02"] is Verdict.VIOLATION
    assert got["K-C1-GEO-01-P01xP03"] is None
    assert got["K-C1-GEO-01-P02xP03"] is None


# --- marginals are not agreement -----------------------------------------

def test_identical_rates_with_total_disagreement():
    """The trap: D3 and D1 both call half the pairs contradictory, and differ
    on every one. A report built from marginals would call this perfect."""
    rows = [
        _row("p1", Verdict.VIOLATION, Verdict.SATISFIED),
        _row("p2", Verdict.SATISFIED, Verdict.VIOLATION),
    ]
    c = concordance(rows, D0, D1)
    assert c.a_violation_rate == 0.5
    assert c.b_violation_rate == 0.5, "identical marginals"
    assert c.raw_agreement == 0.0, "and yet they agree on nothing"
    assert c.kappa == -1.0


def test_perfect_agreement_scores_one():
    rows = [
        _row("p1", Verdict.VIOLATION, Verdict.VIOLATION),
        _row("p2", Verdict.SATISFIED, Verdict.SATISFIED),
    ]
    c = concordance(rows, D0, D1)
    assert c.raw_agreement == 1.0
    assert c.kappa == 1.0


def test_the_disagreement_breakdown_says_which_detector_is_liberal():
    rows = [
        _row("p1", Verdict.VIOLATION, Verdict.SATISFIED),
        _row("p2", Verdict.VIOLATION, Verdict.SATISFIED),
        _row("p3", Verdict.SATISFIED, Verdict.SATISFIED),
    ]
    c = concordance(rows, D0, D1)
    assert (c.a_only_violation, c.b_only_violation) == (2, 0)
    assert c.a_violation_rate == 2 / 3, "D0 called two of three contradictory"
    assert c.b_violation_rate == 0.0, "D1 called none"


# --- kappa refuses rather than misleads ----------------------------------

def test_kappa_is_none_when_one_label_covers_everything():
    """A 99%-SATISFIED set can show kappa~0 while the detectors agree on 99% of
    pairs. Emitting a number here invites exactly that misreading."""
    k, note = cohens_kappa(both_violation=0, a_only=0, b_only=0, both_satisfied=50)
    assert k is None
    assert "identically 0" in note


def test_kappa_is_withheld_when_only_ONE_detector_is_constant():
    """The case that is easy to miss, and that a real run produced.

    With `a` constant SATISFIED, p_expected = 1 - b_viol = p_observed for EVERY
    b_viol, so kappa is identically 0 however much the two agree. Here they
    agree on 2/3 of pairs and the raw formula returns ~3e-16, which would be
    reported as 0.0000 and read as chance-level agreement.
    """
    k, note = cohens_kappa(both_violation=0, a_only=0, b_only=28, both_satisfied=56)
    assert k is None, "a constant detector makes kappa uninformative, not zero"
    assert "identically 0" in note
    assert "raw_agreement" in note, "the note must point at what IS defined"

    # And the agreement it withholds kappa for is substantial, not chance.
    rows = (
        [_row(f"v{i}", Verdict.SATISFIED, Verdict.VIOLATION) for i in range(28)]
        + [_row(f"s{i}", Verdict.SATISFIED, Verdict.SATISFIED) for i in range(56)]
    )
    c = concordance(rows, D0, D1)
    assert c.raw_agreement == 56 / 84
    assert c.kappa is None


def test_kappa_is_none_with_no_jointly_decided_pairs():
    k, note = cohens_kappa(0, 0, 0, 0)
    assert k is None
    assert note == "no jointly decided pairs"


def test_a_missing_kappa_carries_its_reason_into_the_report():
    rows = [_row("p1", Verdict.SATISFIED, Verdict.SATISFIED)]
    c = concordance(rows, D0, D1)
    assert c.kappa is None
    assert c.kappa_note != "ok"
    assert c.raw_agreement == 1.0, "agreement is still perfectly well defined"


# --- the clustered unit --------------------------------------------------

def test_per_constraint_agreement_is_one_value_per_constraint():
    rows = [
        _row("a1", Verdict.VIOLATION, Verdict.VIOLATION, cid="K-C1-GEO-01"),
        _row("a2", Verdict.VIOLATION, Verdict.SATISFIED, cid="K-C1-GEO-01"),
        _row("b1", Verdict.SATISFIED, Verdict.SATISFIED, cid="K-C2-GEO-01"),
    ]
    cids, values = per_constraint_agreement(rows, D0, D1)
    assert cids == ["K-C1-GEO-01", "K-C2-GEO-01"]
    assert values == [0.5, 1.0]


def test_a_constraint_with_no_joint_decision_contributes_none_not_zero():
    """Q6: an undefined cell widens the interval; a zero would bias it."""
    rows = [
        _row("a1", Verdict.VIOLATION, Verdict.VIOLATION, cid="K-C1-GEO-01"),
        _row("b1", None, Verdict.VIOLATION, cid="K-C2-GEO-01"),
    ]
    cids, values = per_constraint_agreement(rows, D0, D1)
    assert values == [1.0, None]


def test_per_constraint_values_feed_the_cluster_bootstrap():
    """The only interval this project reports for agreement resamples
    CONSTRAINTS, because statistics.yaml forbids pair-level independence."""
    from semintegrity.analysis.bootstrap import cluster_bootstrap

    rows = []
    for i in range(1, 9):
        cid = f"K-C1-GEO-0{i}"
        agree = i % 2 == 0
        rows.append(_row(f"{cid}-P01xP02", Verdict.VIOLATION,
                         Verdict.VIOLATION if agree else Verdict.SATISFIED, cid=cid))
    _, values = per_constraint_agreement(rows, D0, D1)
    res = cluster_bootstrap(values, n_boot=200, seed=1)
    assert res.n_clusters == 8
    assert res.estimate == 0.5
    assert res.ci_low is not None and res.ci_high is not None


# --- nothing here pretends to be accuracy --------------------------------

def test_the_module_exposes_no_accuracy_metric():
    import semintegrity.analysis.detector_agreement as mod

    names = dir(mod)
    for forbidden in ("precision", "recall", "f1", "auprc", "average_precision"):
        assert not any(forbidden in n.lower() for n in names), (
            f"{forbidden} needs human gold; detector_scores refuses it separately"
        )


def test_concordance_is_frozen():
    rows = [_row("p1", Verdict.VIOLATION, Verdict.VIOLATION)]
    c = concordance(rows, D0, D1)
    assert isinstance(c, Concordance)
    try:
        c.n_agree = 99  # type: ignore[misc]
    except (AttributeError, TypeError):
        return
    raise AssertionError("a computed concordance must not be mutable")
