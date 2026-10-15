"""D0AUDIT-A — analytic audit cases (ADR-0023 D3).

The preregistered `D0AUDIT` criterion required three HAND-CHECKED instances per
predicate with a human-supplied `expected_verdict`. `D0AUDIT-A` replaces the
human verdict with one that follows DEDUCTIVELY from the predicate's own
declared `formal_statement`.

WHAT THESE TESTS ESTABLISH: that a predicate implements the formalisation it
declares. A software-correctness check.

WHAT THEY DO NOT ESTABLISH, and it must be said in the dissertation:
  * NOT detector validity — a predicate whose `formal_statement` is itself wrong
    passes its own analytic audit perfectly;
  * NOT human validation — nobody judged any instance;
  * NOT 28 independent formalisations — see the coverage test at the end.
"""

from __future__ import annotations

import datetime as dt

import pytest

from semintegrity.detectors.d0.audit import (
    AnalyticAuditCase,
    mechanism_coverage,
    run_analytic_audit,
)
from semintegrity.detectors.d0.registry import default_registry
from semintegrity.schemas.enums import (
    AnswerType,
    ConstraintClass,
    Domain,
    ResponseLabel,
    Verdict,
)
from semintegrity.schemas.response import CanonicalResponse
from tests.fixtures.synthetic_benchmark import make_constraint


class _FixtureKB:
    """A constructed knowledge base. Returns nothing it was not given.

    Deliberately minimal: a predicate that needs more than this protocol is
    doing authoring work inside a predicate, which `d0/base.py` says is where
    it must not be.
    """

    def __init__(self, claims=None, intervals=None):
        self._claims = claims or {}
        self._intervals = intervals or {}

    def entity_label(self, qid): return f"label({qid})"
    def sitelinks(self, qid): return 100
    def claim_values(self, qid, property_id): return list(self._claims.get((qid, property_id), []))
    def claim_interval(self, qid, property_id, value_qid):
        return self._intervals.get((qid, property_id, value_qid), (None, None))


def _constraint(space, gold, *, klass=ConstraintClass.C1, at=AnswerType.ENTITY):
    c = make_constraint(klass, Domain.GEOGRAPHY, 1)
    return c.model_copy(update={
        "answer_space": list(space), "gold_answer": gold, "answer_type": at,
    })


def _resp(n, answer, label=ResponseLabel.ANSWER, cid="K-C1-GEO-01"):
    return CanonicalResponse(
        response_id=f"R-{n:012x}", constraint_id=cid, probe_id=f"{cid}-P0{n}",
        label=label, canonical_answer=answer, matched_alias=answer,
        candidates_found=[answer] if answer else [],
        canonicaliser_version="1.1", canonicaliser_sha256="0" * 64,
        canonicalised_at=dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc),
    )


# --- the mechanism all 28 names route through ---------------------------

def _mutual_exclusion_cases(pred):
    """Three cases derived from `c1_mutual_exclusion`'s own formal statement."""
    c = _constraint(["Canberra", "Sydney", "Melbourne"], "Canberra")
    stmt = pred.formal_statement
    return [
        AnalyticAuditCase(
            case_id="EXCL-differ",
            constraint=c,
            responses=[_resp(1, "Canberra"), _resp(2, "Sydney")],
            expected_verdict=Verdict.VIOLATION,
            derivation=(
                "The statement asserts the answer space members are mutually "
                "exclusive. 'Canberra' and 'Sydney' are distinct members, so they "
                "cannot both hold and the pair VIOLATES."
            ),
            derived_from=stmt,
        ),
        AnalyticAuditCase(
            case_id="EXCL-agree",
            constraint=c,
            responses=[_resp(1, "Canberra"), _resp(2, "Canberra")],
            expected_verdict=Verdict.SATISFIED,
            derivation=(
                "Mutual exclusion is violated only by DISTINCT members. One "
                "member asserted twice is jointly satisfiable, so SATISFIED."
            ),
            derived_from=stmt,
        ),
        AnalyticAuditCase(
            case_id="EXCL-outside-space",
            constraint=c,
            responses=[_resp(1, "Canberra"), _resp(2, "Brisbane")],
            expected_verdict=Verdict.NOT_APPLICABLE,
            derivation=(
                "The statement is about members OF the closed space. 'Brisbane' "
                "is not one, so the formalisation does not apply and the verdict "
                "must be NOT_APPLICABLE rather than a contradiction -- a "
                "canonicalisation bug must not be reported as model "
                "inconsistency."
            ),
            derived_from=stmt,
        ),
    ]


def test_c1_mutual_exclusion_implements_its_declared_statement():
    pred = default_registry().get("c1_mutual_exclusion")
    result = run_analytic_audit(pred, _mutual_exclusion_cases(pred), _FixtureKB())
    assert result.passed, result.summary
    assert len(result.outcomes) >= 3


def test_a_schema_predicate_delegating_to_it_behaves_identically():
    """`_SchemaExclusion` covers 20 of the 28 names."""
    reg = default_registry()
    pred = reg.get("s_c1_01")
    cases = [
        AnalyticAuditCase(
            case_id=c.case_id, constraint=c.constraint, responses=c.responses,
            expected_verdict=c.expected_verdict, derivation=c.derivation,
            derived_from=pred.formal_statement,
        )
        for c in _mutual_exclusion_cases(reg.get("c1_mutual_exclusion"))
    ]
    result = run_analytic_audit(pred, cases, _FixtureKB())
    assert result.passed, result.summary


# --- the drift guard, which is what makes a literal verdict safe --------

def test_a_case_derived_from_a_stale_formal_statement_is_REFUSED():
    """A stale derivation is not evidence either way, so it raises rather than
    failing -- a failed case would read as a defect in the predicate."""
    pred = default_registry().get("c1_mutual_exclusion")
    case = _mutual_exclusion_cases(pred)[0]
    stale = AnalyticAuditCase(
        case_id=case.case_id, constraint=case.constraint,
        responses=case.responses, expected_verdict=case.expected_verdict,
        derivation=case.derivation,
        derived_from="some OTHER formalisation this predicate does not declare",
    )
    with pytest.raises(ValueError, match="no longer declares"):
        run_analytic_audit(pred, [stale], _FixtureKB())


def test_a_case_without_a_derivation_is_rejected():
    c = _constraint(["Canberra", "Sydney"], "Canberra")
    with pytest.raises(ValueError, match="derivation.*required"):
        AnalyticAuditCase(
            case_id="x", constraint=c,
            responses=[_resp(1, "Canberra"), _resp(2, "Sydney")],
            expected_verdict=Verdict.VIOLATION,
            derivation="   ", derived_from="something",
        )


def test_a_case_without_derived_from_is_rejected():
    c = _constraint(["Canberra", "Sydney"], "Canberra")
    with pytest.raises(ValueError, match="derived_from"):
        AnalyticAuditCase(
            case_id="x", constraint=c,
            responses=[_resp(1, "Canberra"), _resp(2, "Sydney")],
            expected_verdict=Verdict.VIOLATION,
            derivation="because", derived_from="",
        )


def test_the_expected_verdict_must_be_a_literal_Verdict():
    c = _constraint(["Canberra", "Sydney"], "Canberra")
    with pytest.raises(TypeError, match="must be a Verdict"):
        AnalyticAuditCase(
            case_id="x", constraint=c,
            responses=[_resp(1, "Canberra"), _resp(2, "Sydney")],
            expected_verdict="VIOLATION",   # type: ignore[arg-type]
            derivation="because", derived_from="something",
        )


def test_a_non_pairwise_case_is_rejected():
    pred = default_registry().get("c1_mutual_exclusion")
    c = _constraint(["Canberra", "Sydney"], "Canberra")
    case = AnalyticAuditCase(
        case_id="x", constraint=c, responses=[_resp(1, "Canberra")],
        expected_verdict=Verdict.VIOLATION, derivation="because",
        derived_from=pred.formal_statement,
    )
    with pytest.raises(ValueError, match="exactly 2 responses"):
        run_analytic_audit(pred, [case], _FixtureKB())


# --- the honest coverage denominator ------------------------------------

def test_28_predicate_names_are_only_5_pairwise_implementations():
    """The claim D0AUDIT-A is allowed to make, and the one it is not.

    Auditing every NAME does not audit 28 independent formalisations. This is
    the same fact that makes D0-vs-D1 agreement near-tautological (ADR-0023
    §1.1), and it must appear in the dissertation's limitations.
    """
    cov = mechanism_coverage(default_registry())
    assert cov["n_registered_predicates"] == 28
    assert cov["n_distinct_pairwise_implementations"] == 5
    impls = cov["predicates_by_implementation"]
    assert len(impls["_SchemaExclusion.check_pair"]) == 20
    assert len(impls["_SchemaAnchor.check_pair"]) == 4
    assert "audits those implementations, not that many" in cov["coverage_caveat"]


def test_the_two_placeholder_predicates_are_named_and_unused():
    """`c2_conjunction` and `c3_functional_uniqueness` are registered at
    v0.1-placeholder. No test constraint selects either, so no reported verdict
    comes from one -- but they remain reachable and must be surfaced."""
    from semintegrity.benchmark.loader import load_split
    from semintegrity.utils.paths import data_path

    cov = mechanism_coverage(default_registry())
    assert set(cov["placeholder_predicates"]) == {
        "c2_conjunction", "c3_functional_uniqueness"
    }

    split = data_path("benchmark") / "test"
    if (split / "constraints.jsonl").is_file():
        cons, _ = load_split(split)
        used = {c.formal_predicate for c in cons}
        assert not used & set(cov["placeholder_predicates"]), (
            "a placeholder predicate must never produce a reported verdict"
        )
