"""The design validator must accept a lattice-valid benchmark and localise breaks."""

import pytest

from semintegrity.benchmark.design_validator import BenchmarkDesignValidator, DesignViolation
from semintegrity.schemas.enums import ConstraintClass, Domain, Split
from tests.fixtures.synthetic_benchmark import dev_set, full_benchmark, make_constraint


@pytest.fixture(scope="module")
def validator():
    return BenchmarkDesignValidator()


@pytest.fixture(scope="module")
def benchmark():
    return full_benchmark()


def test_lattice_valid_benchmark_passes_every_rule(validator, benchmark):
    report = validator.validate(benchmark, strict_schema_crossing=True)
    assert report.ok, str(report)
    report.raise_if_failed()  # must not raise


def test_fixture_realises_the_adr0002_lattice(benchmark):
    assert len(benchmark) == 120
    assert len({c.family_id for c in benchmark}) == 30
    for cls in ConstraintClass:
        assert sum(c.constraint_class is cls for c in benchmark) == 30
    for dom in Domain:
        for cls in ConstraintClass:
            assert sum(c.domain is dom and c.constraint_class is cls for c in benchmark) == 6


def test_missing_constraint_breaks_count_and_balance(validator, benchmark):
    report = validator.validate(benchmark[:-1])
    failed = {r.rule for r in report.errors}
    assert "total_count" in failed
    assert "class_balance" in failed or "domain_class_balance" in failed


def test_duplicate_id_is_localised(validator, benchmark):
    report = validator.validate([*benchmark, benchmark[0]])
    rule = next(r for r in report.results if r.rule == "unique_ids")
    assert not rule.passed
    assert benchmark[0].constraint_id in rule.offenders


def test_family_spanning_two_domains_is_caught(validator):
    a = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1, family_index=1)
    b = make_constraint(ConstraintClass.C2, Domain.HISTORY, 1, family_index=1)
    # b's family_id encodes HISTORY, so force the collision the rule looks for
    b = b.model_copy(update={"family_id": a.family_id})
    report = validator.validate([a, b], split=Split.TEST)
    rule = next(r for r in report.results if r.rule == "family_domain_fixed")
    assert not rule.passed


def test_missing_scipy_fails_closed(validator, benchmark, monkeypatch):
    """A validity check that cannot run must NOT report success.

    Regression test for a real bug: the check returned passed=True when scipy
    was absent, so on the cluster — where the analysis actually runs — a
    benchmark confounded between class and entity familiarity would have passed
    validation in silence.
    """
    import builtins

    real_import = builtins.__import__

    def no_scipy(name, *args, **kwargs):
        if name.startswith("scipy"):
            raise ImportError("simulated: scipy not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_scipy)
    rule = next(
        r for r in validator.validate(benchmark).results if r.rule == "sitelink_matching"
    )
    assert not rule.passed, "a check that could not run must never report PASS"
    assert rule.severity == "error"
    assert "COULD NOT RUN" in rule.message


def test_sitelink_confound_is_detected(validator):
    """C3/C4 built from far less familiar entities must trip the matching test."""
    pytest.importorskip("scipy")
    cs = []
    for dom in Domain:
        for i in range(1, 7):
            for cls in ConstraintClass:
                low = cls in (ConstraintClass.C3, ConstraintClass.C4)
                cs.append(
                    make_constraint(
                        cls, dom, i, family_index=i, schema_index=i,
                        sitelinks=(3, 2) if low else (400, 380),
                    )
                )
    rule = next(r for r in validator.validate(cs).results if r.rule == "sitelink_matching")
    assert not rule.passed, "a gross familiarity confound must fail the matching test"
    assert "p=" in rule.message


def test_matched_sitelinks_pass(validator, benchmark):
    pytest.importorskip("scipy")
    rule = next(r for r in validator.validate(benchmark).results if r.rule == "sitelink_matching")
    assert rule.passed


def test_unregistered_predicate_is_reported(validator, benchmark):
    report = validator.validate(benchmark, known_predicates={"only_this_one"})
    rule = next(r for r in report.results if r.rule == "predicate_registered")
    assert not rule.passed and len(rule.offenders) > 0


def test_dev_test_disjointness(validator, benchmark):
    assert validator.validate_split_disjointness([*benchmark, *dev_set()]).passed
    leaked = benchmark[0].model_copy(update={"split": Split.DEV})
    result = validator.validate_split_disjointness([*benchmark, leaked])
    assert not result.passed
    assert any("entity set" in o for o in result.offenders)


def test_raise_if_failed_surfaces_all_errors(validator, benchmark):
    with pytest.raises(DesignViolation) as exc:
        validator.validate(benchmark[:50]).raise_if_failed()
    assert "design rule(s) violated" in str(exc.value)


# --- cross-split id uniqueness --------------------------------------------
# `validate()` filters to one split before checking `unique_ids`, and the id
# grammar carries no split field, so a TEST and a PILOT/DEV constraint can share
# an id, pass both per-split validations, and merge in any join on
# `constraint_id`. These tests pin the gap and its fix.
def test_cross_split_ids_pass_when_splits_are_numbered_apart(validator, benchmark):
    rule = validator.validate_global_id_uniqueness([*benchmark, *dev_set()])
    assert rule.passed, str(rule)
    assert rule.rule == "cross_split_ids"


def test_cross_split_id_reuse_is_caught(validator, benchmark):
    collider = benchmark[0].model_copy(update={"split": Split.PILOT})
    rule = validator.validate_global_id_uniqueness([*benchmark, collider])
    assert not rule.passed
    assert any(benchmark[0].constraint_id in o for o in rule.offenders)
    assert "test" in rule.offenders[0] and "pilot" in rule.offenders[0]


def test_per_split_validation_cannot_see_a_cross_split_collision(validator, benchmark):
    """Why the separate check is necessary rather than merely tidy."""
    collider = benchmark[0].model_copy(update={"split": Split.PILOT})
    both = [*benchmark, collider]
    test_report = validator.validate(both, split=Split.TEST)
    dev_report = validator.validate(both, split=Split.PILOT)
    assert next(r for r in test_report.results if r.rule == "unique_ids").passed
    assert next(r for r in dev_report.results if r.rule == "unique_ids").passed
    assert not validator.validate_global_id_uniqueness(both).passed


def test_unique_ids_still_catches_within_split_duplicates(validator, benchmark):
    report = validator.validate([*benchmark, benchmark[0]], split=Split.TEST)
    rule = next(r for r in report.results if r.rule == "unique_ids")
    assert not rule.passed
    assert "within this split" in rule.message
