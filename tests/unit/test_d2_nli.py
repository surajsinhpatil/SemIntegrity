"""D2 — NLI contradiction detection (§4.8.4, configs/detectors/d2_nli.yaml).

The scorer is injected, so these tests exercise D2's actual logic -- claim
rendering, bidirectional aggregation, threshold discipline, coverage -- without
a GPU or a checkpoint. What is tested is what D2 decides, not what an NLI model
happens to predict.
"""

import datetime as dt

import pytest

from semintegrity.detectors.d2.nli import (
    D2Detector,
    ThresholdNotCalibrated,
    coverage,
)
from semintegrity.detectors.d2.templates import (
    NEGATION_PREFIX,
    ClaimRenderingError,
    negate,
    render_claim,
)
from semintegrity.schemas.enums import AnswerType, ConstraintClass, Domain, ResponseLabel, Verdict
from semintegrity.schemas.response import CanonicalResponse
from tests.fixtures.synthetic_benchmark import make_constraint


def _constraint(answer_type=AnswerType.ENTITY, space=None, gold="Canberra",
                proposition="The capital city of Australia is Canberra."):
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    return c.model_copy(update={
        "answer_type": answer_type,
        "answer_space": space or ["Canberra", "Sydney", "Melbourne"],
        "gold_answer": gold,
        "gold_proposition": proposition,
    })


def _resp(probe_n: int, answer: str | None, label=ResponseLabel.ANSWER) -> CanonicalResponse:
    return CanonicalResponse(
        response_id=f"R-{probe_n:012x}", constraint_id="K-C1-GEO-01",
        probe_id=f"K-C1-GEO-01-P0{probe_n}", label=label, canonical_answer=answer,
        matched_alias=answer, candidates_found=[answer] if answer else [],
        canonicaliser_version="1.1", canonicaliser_sha256="0" * 64,
        canonicalised_at=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc),
    )


class FixedScorer:
    """Returns a score looked up by (premise, hypothesis), else a default."""

    name = "fixed-test-scorer"

    def __init__(self, table=None, default=0.01):
        self.table = table or {}
        self.default = default
        self.calls: list[tuple[str, str]] = []

    def contradiction_probability(self, premise: str, hypothesis: str) -> float:
        self.calls.append((premise, hypothesis))
        return self.table.get((premise, hypothesis), self.default)


# --- claim rendering ---------------------------------------------------------

def test_entity_answer_renders_the_response_into_the_proposition():
    c = _constraint()
    assert render_claim(c, _resp(1, "Sydney")) == "The capital city of Australia is Sydney."
    assert render_claim(c, _resp(2, "Canberra")) == "The capital city of Australia is Canberra."


def test_negated_response_renders_as_the_negation():
    c = _constraint()
    claim = render_claim(c, _resp(1, "Canberra", ResponseLabel.NEGATED))
    assert claim.startswith(NEGATION_PREFIX)
    assert "Canberra" in claim


def test_boolean_branches_on_answer_type_not_on_substrings():
    """K-C3-GEO-01 reads '...and of no other sovereign state'. A substring test
    for 'NO' would corrupt it, so boolean must key on answer_type."""
    prop = "Canberra is the capital of Australia and of no other sovereign state."
    c = _constraint(AnswerType.BOOLEAN, ["YES", "NO"], "NO", prop)
    assert render_claim(c, _resp(1, "YES")) == prop
    assert render_claim(c, _resp(2, "NO")) == negate(prop)


def test_non_answer_labels_render_no_claim():
    """ABSTAIN and INVALID assert nothing; inventing a proposition for them
    would put words in the model's mouth."""
    c = _constraint()
    for label in (ResponseLabel.ABSTAIN, ResponseLabel.INVALID):
        assert render_claim(c, _resp(1, None, label)) is None


def test_missing_gold_answer_in_proposition_fails_loudly():
    """Silently rendering the wrong claim is worse than no D2 verdict."""
    c = _constraint(proposition="Australia has a capital city.")
    with pytest.raises(ClaimRenderingError, match="does not occur"):
        render_claim(c, _resp(1, "Sydney"))


# --- bidirectional scoring ---------------------------------------------------

def test_scoring_is_bidirectional_and_takes_the_max():
    """NLI is asymmetric; d2_nli.yaml specifies max over both directions."""
    c = _constraint()
    a, b = _resp(1, "Canberra"), _resp(2, "Sydney")
    ca = "The capital city of Australia is Canberra."
    cb = "The capital city of Australia is Sydney."
    scorer = FixedScorer({(ca, cb): 0.30, (cb, ca): 0.90})
    s = D2Detector(scorer).score_pair(c, a, b)
    assert (s.p_forward, s.p_backward) == (0.30, 0.90)
    assert s.contradiction_probability == 0.90
    assert len(scorer.calls) == 2, "both orderings must be scored"


def test_unevaluable_pair_is_scored_as_none_not_zero():
    """A pair D2 cannot read is NOT a pair with no contradiction."""
    c = _constraint()
    s = D2Detector(FixedScorer()).score_pair(c, _resp(1, "Canberra"),
                                             _resp(2, None, ResponseLabel.ABSTAIN))
    assert not s.evaluable
    assert s.contradiction_probability is None


# --- threshold discipline ----------------------------------------------------

def test_verdicts_require_calibrated_thresholds():
    """d2_nli.yaml: calibrated per_class, and a bare 0.5 is never used."""
    c = _constraint()
    d2 = D2Detector(FixedScorer())
    with pytest.raises(ThresholdNotCalibrated, match="calibrate_d2"):
        d2.check_pair(c, _resp(1, "Canberra"), _resp(2, "Sydney"))


def test_scoring_works_without_thresholds_because_calibration_needs_it():
    """Calibration consumes scores and produces thresholds, so scoring cannot
    require them -- otherwise D2 could never be calibrated at all."""
    c = _constraint()
    s = D2Detector(FixedScorer(default=0.42)).score_pair(c, _resp(1, "Canberra"),
                                                         _resp(2, "Sydney"))
    assert s.contradiction_probability == 0.42


def test_a_bare_half_threshold_is_rejected():
    with pytest.raises(ValueError, match="forbids"):
        D2Detector(FixedScorer(), thresholds={"C1": 0.5})


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5])
def test_out_of_range_thresholds_are_rejected(bad):
    with pytest.raises(ValueError, match="must be in"):
        D2Detector(FixedScorer(), thresholds={"C1": bad})


def test_thresholds_are_per_class_not_global():
    c = _constraint()
    d2 = D2Detector(FixedScorer(), thresholds={"C2": 0.8})
    with pytest.raises(ThresholdNotCalibrated, match="class C1"):
        d2.check_pair(c, _resp(1, "Canberra"), _resp(2, "Sydney"))


# --- verdicts ----------------------------------------------------------------

def test_positive_contradiction_case():
    c = _constraint()
    a, b = _resp(1, "Canberra"), _resp(2, "Sydney")
    ca = "The capital city of Australia is Canberra."
    cb = "The capital city of Australia is Sydney."
    d2 = D2Detector(FixedScorer({(ca, cb): 0.95, (cb, ca): 0.93}), thresholds={"C1": 0.7})
    r = d2.check_pair(c, a, b)
    assert r.verdict is Verdict.VIOLATION and r.is_contradiction
    assert r.score == 0.95 and r.threshold == 0.7


def test_negative_contradiction_case():
    c = _constraint()
    a, b = _resp(1, "Canberra"), _resp(2, "Canberra")
    d2 = D2Detector(FixedScorer(default=0.02), thresholds={"C1": 0.7})
    r = d2.check_pair(c, a, b)
    assert r.verdict is Verdict.SATISFIED and not r.is_contradiction


def test_threshold_boundary_is_inclusive_and_explicit():
    """At exactly the threshold the pair counts as a contradiction. Stated in a
    test because a boundary left to chance is a silent methodology choice."""
    c = _constraint()
    d2 = D2Detector(FixedScorer(default=0.70), thresholds={"C1": 0.70})
    assert d2.check_pair(c, _resp(1, "Canberra"), _resp(2, "Sydney")).verdict is Verdict.VIOLATION


def test_unevaluable_pair_is_not_applicable_never_satisfied():
    """An unreadable pair must not be counted as 'no contradiction found'."""
    c = _constraint()
    d2 = D2Detector(FixedScorer(), thresholds={"C1": 0.7})
    r = d2.check_pair(c, _resp(1, "Canberra"), _resp(2, None, ResponseLabel.ABSTAIN))
    assert r.verdict is Verdict.NOT_APPLICABLE
    assert r.score is None


def test_coverage_counts_only_pairs_d2_could_read():
    c = _constraint()
    d2 = D2Detector(FixedScorer(), thresholds={"C1": 0.7})
    responses = [_resp(1, "Canberra"), _resp(2, "Sydney"),
                 _resp(3, None, ResponseLabel.ABSTAIN), _resp(4, None, ResponseLabel.INVALID)]
    results = d2.check_all_pairs(c, responses)
    assert len(results) == 6          # C(4,2)
    assert coverage(results) == pytest.approx(1 / 6)   # only the Canberra/Sydney pair
    assert coverage([]) == 0.0


def test_a_perfectly_consistent_set_yields_no_violations():
    """The D2 counterpart of the perfect-model invariant."""
    c = _constraint()
    d2 = D2Detector(FixedScorer(default=0.01), thresholds={"C1": 0.7})
    results = d2.check_all_pairs(c, [_resp(i, "Canberra") for i in range(1, 6)])
    assert results and not any(r.is_contradiction for r in results)


def test_real_scorer_requires_an_explicit_checkpoint():
    """The checkpoint is EMPIRICAL_NOT_ASSUMED; a default would decide it."""
    from semintegrity.detectors.d2.nli import HuggingFaceNLIScorer

    with pytest.raises(ValueError, match="EMPIRICAL_NOT_ASSUMED"):
        HuggingFaceNLIScorer("")
