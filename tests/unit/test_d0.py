"""D0 framework: predicates, registry freeze policy and the three-instance audit."""

import datetime as dt

import pytest

from semintegrity.detectors.d0.audit import (
    MIN_AUDIT_INSTANCES,
    AuditCase,
    SchemaAuditFailure,
    audit_all,
    audit_predicate,
)
from semintegrity.detectors.d0.base import D0Predicate, D0Result
from semintegrity.detectors.d0.registry import (
    PredicateFrozenError,
    PredicateRegistry,
)
from semintegrity.kb.adapter import StaticKB
from semintegrity.schemas.constraint import TemporalValidity
from semintegrity.schemas.enums import ConstraintClass, Domain, ResponseLabel, Verdict
from tests.fixtures.responses import canon
from tests.fixtures.synthetic_benchmark import make_constraint


@pytest.fixture
def kb():
    return StaticKB()


@pytest.fixture
def registry():
    r = PredicateRegistry()
    r.autodiscover()
    return r


@pytest.fixture
def c1(registry):
    return registry.get("c1_mutual_exclusion")


@pytest.fixture
def c1_constraint():
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    return c.model_copy(update={"formal_predicate": "c1_mutual_exclusion"})


# --- C1 reference predicate ------------------------------------------------
def test_same_answer_is_satisfied(c1, c1_constraint, kb):
    space = c1_constraint.answer_space
    a = canon("K-C1-GEO-01-P01", space[0])
    b = canon("K-C1-GEO-01-P02", space[0])
    assert c1.check_pair(c1_constraint, a, b, kb).verdict is Verdict.SATISFIED


def test_different_answers_violate(c1, c1_constraint, kb):
    space = c1_constraint.answer_space
    a = canon("K-C1-GEO-01-P01", space[0])
    b = canon("K-C1-GEO-01-P02", space[1])
    r = c1.check_pair(c1_constraint, a, b, kb)
    assert r.verdict is Verdict.VIOLATION
    assert r.conflicting_pairs == (("K-C1-GEO-01-P01", "K-C1-GEO-01-P02"),)
    assert r.is_covered


def test_answer_outside_the_closed_space_is_not_a_contradiction(c1, c1_constraint, kb):
    """A Stage 0 bug must surface as NOT_APPLICABLE, never as model inconsistency."""
    a = canon("K-C1-GEO-01-P01", c1_constraint.answer_space[0])
    b = canon("K-C1-GEO-01-P02", "SomethingNotInTheSpace")
    r = c1.check_pair(c1_constraint, a, b, kb)
    assert r.verdict is Verdict.NOT_APPLICABLE
    assert "canonicalisation bug" in r.reason
    assert not r.is_covered


def test_abstentions_are_skipped_not_counted(c1, c1_constraint, kb):
    space = c1_constraint.answer_space
    responses = [
        canon("K-C1-GEO-01-P01", space[0]),
        canon("K-C1-GEO-01-P02", None, label=ResponseLabel.ABSTAIN),
        canon("K-C1-GEO-01-P03", space[0]),
    ]
    r = c1.check_set(c1_constraint, responses, kb)
    assert r.verdict is Verdict.SATISFIED
    assert r.skipped_probe_ids == ("K-C1-GEO-01-P02",)


def test_fewer_than_two_answers_is_not_applicable(c1, c1_constraint, kb):
    """Feeds the D0 coverage metric and the PSCR zero-denominator policy (Q6)."""
    responses = [
        canon("K-C1-GEO-01-P01", c1_constraint.answer_space[0]),
        canon("K-C1-GEO-01-P02", None, label=ResponseLabel.ABSTAIN),
    ]
    r = c1.check_set(c1_constraint, responses, kb)
    assert r.verdict is Verdict.NOT_APPLICABLE
    assert not r.is_covered


def test_set_level_reports_every_conflicting_pair(c1, c1_constraint, kb):
    space = c1_constraint.answer_space
    responses = [
        canon("K-C1-GEO-01-P01", space[0]),
        canon("K-C1-GEO-01-P02", space[1]),
        canon("K-C1-GEO-01-P03", space[2]),
    ]
    r = c1.check_set(c1_constraint, responses, kb)
    assert r.verdict is Verdict.VIOLATION
    assert len(r.conflicting_pairs) == 3  # C(3,2), all mutually exclusive


# --- C4 reference predicate ------------------------------------------------
@pytest.fixture
def c4_constraint():
    c = make_constraint(ConstraintClass.C4, Domain.HISTORY, 1)
    return c.model_copy(
        update={
            "formal_predicate": "c4_interval_precedence",
            "answer_type": "date",
            "answer_space": ["1901", "1927", "1850"],
            "gold_answer": "1927",
            "temporal_validity": TemporalValidity(start=dt.date(1901, 1, 1)),
        }
    )


def test_date_before_the_anchor_violates(registry, c4_constraint, kb):
    c4 = registry.get("c4_interval_precedence")
    a = canon("K-C4-HIS-01-P01", "1850")
    b = canon("K-C4-HIS-01-P02", "1850")
    r = c4.check_pair(c4_constraint, a, b, kb)
    assert r.verdict is Verdict.VIOLATION
    assert "precede the establishment anchor" in r.reason


def test_matching_valid_dates_satisfy(registry, c4_constraint, kb):
    c4 = registry.get("c4_interval_precedence")
    a = canon("K-C4-HIS-01-P01", "1927")
    b = canon("K-C4-HIS-01-P02", "1927")
    assert c4.check_pair(c4_constraint, a, b, kb).verdict is Verdict.SATISFIED


def test_differing_valid_dates_violate(registry, c4_constraint, kb):
    c4 = registry.get("c4_interval_precedence")
    a = canon("K-C4-HIS-01-P01", "1927")
    b = canon("K-C4-HIS-01-P02", "1901")
    assert c4.check_pair(c4_constraint, a, b, kb).verdict is Verdict.VIOLATION


def test_unparseable_date_is_not_applicable(registry, c4_constraint, kb):
    c4 = registry.get("c4_interval_precedence")
    a = canon("K-C4-HIS-01-P01", "not a date")
    b = canon("K-C4-HIS-01-P02", "1927")
    assert c4.check_pair(c4_constraint, a, b, kb).verdict is Verdict.NOT_APPLICABLE


# --- registry --------------------------------------------------------------
def test_duplicate_registration_is_rejected(registry, c1):
    with pytest.raises(ValueError, match="already registered"):
        registry.register(c1)


def test_unknown_predicate_names_are_listed(registry):
    with pytest.raises(KeyError, match="c1_mutual_exclusion"):
        registry.get("no_such_predicate")


# --- freeze policy (§4.8.2) ------------------------------------------------
def test_freeze_manifest_detects_modification(registry, tmp_path):
    path = tmp_path / "d0_freeze.json"
    registry.write_freeze_manifest(path, note="test freeze")
    assert registry.verify_freeze(path) == []
    registry.assert_frozen(path)  # must not raise

    class Sneaky(D0Predicate):
        predicate_name = "c1_mutual_exclusion"
        schema_id = "S-C1-00"
        formal_statement = "altered after the freeze"
        version = "2.0"

        def check_pair(self, constraint, a, b, kb):  # pragma: no cover
            return D0Result(Verdict.SATISFIED, self.predicate_name, self.schema_id)

    registry._by_name["c1_mutual_exclusion"] = Sneaky()
    problems = registry.verify_freeze(path)
    assert any("MODIFIED after freeze" in p for p in problems)
    with pytest.raises(PredicateFrozenError, match="TEST split"):
        registry.assert_frozen(path)


def test_freeze_manifest_is_never_overwritten(registry, tmp_path):
    from semintegrity.utils.io import ImmutabilityError

    path = tmp_path / "d0_freeze.json"
    registry.write_freeze_manifest(path)
    with pytest.raises(ImmutabilityError):
        registry.write_freeze_manifest(path)


def test_added_and_removed_predicates_are_reported(registry, tmp_path):
    path = tmp_path / "f.json"
    registry.write_freeze_manifest(path)
    del registry._by_name["c4_interval_precedence"]
    assert any("removed after freeze" in p for p in registry.verify_freeze(path))


# --- three-instance audit (§4.8.2 step 10) ---------------------------------
def _case(cid, c1_constraint, answers, expected, checked_by="researcher"):
    return AuditCase(
        case_id=cid,
        constraint=c1_constraint,
        responses=[canon(f"K-C1-GEO-01-P{i:02d}", a) for i, a in enumerate(answers, start=1)],
        expected_verdict=expected,
        checked_by=checked_by,
        checked_at=dt.date(2026, 9, 11),
    )


def test_audit_passes_with_three_correct_cases(c1, c1_constraint, kb):
    sp = c1_constraint.answer_space
    cases = [
        _case("a1", c1_constraint, [sp[0], sp[0]], Verdict.SATISFIED),
        _case("a2", c1_constraint, [sp[0], sp[1]], Verdict.VIOLATION),
        _case("a3", c1_constraint, [sp[1], sp[1]], Verdict.SATISFIED),
    ]
    result = audit_predicate(c1, cases, kb)
    assert result.passed and "PASS" in result.summary


def test_audit_fails_when_the_predicate_disagrees_with_the_human(c1, c1_constraint, kb):
    sp = c1_constraint.answer_space
    cases = [
        _case("a1", c1_constraint, [sp[0], sp[0]], Verdict.SATISFIED),
        _case("a2", c1_constraint, [sp[0], sp[1]], Verdict.SATISFIED),  # human says compatible
        _case("a3", c1_constraint, [sp[1], sp[1]], Verdict.SATISFIED),
    ]
    result = audit_predicate(c1, cases, kb)
    assert not result.passed
    assert [o.passed for o in result.outcomes] == [True, False, True]


def test_fewer_than_three_cases_fails_the_gate(c1, c1_constraint, kb):
    sp = c1_constraint.answer_space
    cases = [_case("a1", c1_constraint, [sp[0], sp[0]], Verdict.SATISFIED)]
    result = audit_predicate(c1, cases, kb)
    assert not result.passed
    assert str(MIN_AUDIT_INSTANCES) in result.summary


def test_audit_case_requires_a_named_human_checker(c1_constraint):
    with pytest.raises(ValueError, match="checked_by is required"):
        _case("a1", c1_constraint, ["x", "x"], Verdict.SATISFIED, checked_by="  ")


def test_audit_all_blocks_when_a_predicate_has_no_cases(registry, c1, c1_constraint, kb, tmp_path):
    sp = c1_constraint.answer_space
    cases = {
        "c1_mutual_exclusion": [
            _case("a1", c1_constraint, [sp[0], sp[0]], Verdict.SATISFIED),
            _case("a2", c1_constraint, [sp[0], sp[1]], Verdict.VIOLATION),
            _case("a3", c1_constraint, [sp[1], sp[1]], Verdict.SATISFIED),
        ]
    }
    with pytest.raises(SchemaAuditFailure, match="no audit cases"):
        audit_all(list(registry), cases, kb, out_path=tmp_path / "audit.jsonl")
    # the passing predicate's result is still recorded before the gate fires
    assert (tmp_path / "audit.jsonl").exists()


def test_audit_case_must_reference_its_own_predicate(c1, c1_constraint, kb):
    wrong = c1_constraint.model_copy(update={"formal_predicate": "something_else"})
    with pytest.raises(ValueError, match="references predicate"):
        audit_predicate(c1, [_case("a1", wrong, ["x", "x"], Verdict.SATISFIED)], kb)
