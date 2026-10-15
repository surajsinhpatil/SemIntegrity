"""S1/S2/S3 ground-truth sensitivity analyses (ADR-0023 D9).

81 of 132 constraints are DRAFT, so these analyses are the primary defence of
the confirmatory results once human validation is removed. The thing they must
never do is produce a number that reads as "H1 confirmed on verified data" when
the verified subset cannot support that contrast.

The real benchmark is used where the point is a fact about it; synthetic
constraints are used where the point is the logic.
"""

from __future__ import annotations

import pytest

from semintegrity.analysis.sensitivity import (
    CONFOUNDED_ANSWER_TYPE,
    NOT_ASSESSABLE_NO_OVERLAP,
    chance_pscr,
    confound_report,
    s1_within_class,
    s2_verified_only_profile,
    s3_restricted_contrast,
)
from semintegrity.benchmark.loader import load_split
from semintegrity.schemas.enums import ConstraintClass, Domain
from semintegrity.utils.paths import data_path
from tests.fixtures.synthetic_benchmark import make_constraint

TEST_SPLIT = data_path("benchmark") / "test"
needs_split = pytest.mark.skipif(
    not (TEST_SPLIT / "constraints.jsonl").is_file(), reason="test split not built"
)


@pytest.fixture(scope="module")
def frozen_constraints():
    cons, _ = load_split(TEST_SPLIT)
    return cons


# --- the analytic quantity the whole design rests on ---------------------

def test_chance_pscr_is_one_minus_one_over_cardinality():
    """Two independent draws from a space of size m agree with probability 1/m."""
    c2 = make_constraint(ConstraintClass.C2, Domain.GEOGRAPHY, 1)
    assert chance_pscr(c2.model_copy(update={"answer_space": ["YES", "NO"]})) == 0.5
    three = c2.model_copy(update={"answer_space": ["a", "b", "c"]})
    assert chance_pscr(three) == pytest.approx(2 / 3)


def test_an_empty_answer_space_raises_rather_than_dividing_by_zero():
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    with pytest.raises(ValueError, match="empty answer space"):
        chance_pscr(c.model_copy(update={"answer_space": []}))


# --- facts about the FROZEN benchmark ------------------------------------

@needs_split
def test_c4_has_no_verified_constraint_so_h1_cannot_be_restricted(frozen_constraints):
    """The finding that invalidated the originally planned sensitivity analysis."""
    report = confound_report(frozen_constraints)
    assert report["C4"].n_verified == 0
    assert report["C4"].verdict == NOT_ASSESSABLE_NO_OVERLAP
    assert "cannot be sensitivity-tested" in " ".join(report["C4"].notes)


@needs_split
def test_c1_is_confounded_by_answer_type_and_c2_c3_are_not(frozen_constraints):
    """C1's verified subset holds no dates; its draft subset is mostly dates."""
    report = confound_report(frozen_constraints)

    assert report["C1"].verdict == CONFOUNDED_ANSWER_TYPE
    assert "date" not in report["C1"].answer_types_verified
    assert report["C1"].answer_types_draft["date"] == 10
    assert report["C1"].chance_gap == pytest.approx(-0.0595, abs=5e-4)

    for klass in ("C2", "C3"):
        cf = report[klass]
        assert cf.comparable, f"{klass} should be comparable: {cf.notes}"
        assert cf.chance_gap == pytest.approx(0.0, abs=1e-12)
        assert set(cf.answer_types_verified) == {"boolean"}
        assert set(cf.answer_types_draft) == {"boolean"}


@needs_split
def test_history_is_a_residual_confound_in_every_class(frozen_constraints):
    """All 24 history constraints are DRAFT, so it is absent from every
    verified subset. Reported, never adjusted for."""
    report = confound_report(frozen_constraints)
    for klass in ("C1", "C2", "C3"):
        cf = report[klass]
        assert "history" in cf.domains_missing_from_verified
        assert any("RESIDUAL CONFOUND" in n for n in cf.notes)


@needs_split
def test_sitelinks_do_not_show_a_systematic_prominence_confound(frozen_constraints):
    """A priori worry: constraints may be verifiable BECAUSE their entities are
    prominent. The medians move in opposite directions across classes, so the
    data does not support that concern."""
    report = confound_report(frozen_constraints)
    diffs = [
        report[k].median_sitelinks_verified - report[k].median_sitelinks_draft
        for k in ("C1", "C2", "C3")
    ]
    assert any(d > 0 for d in diffs) and any(d < 0 for d in diffs), (
        "a one-directional shift would indicate a prominence confound"
    )


# --- S1 refuses rather than estimating a confounded cell -----------------

def _rows(spec):
    """spec: list of (cid, class, status, pscr)."""
    return [
        {"constraint_id": cid, "class": k, "verification_status": s, "pscr": v}
        for cid, k, s, v in spec
    ]


def _cons(spec):
    """spec: list of (cid, class, status, answer_space)."""
    out = []
    for cid, k, s, space in spec:
        c = make_constraint(getattr(ConstraintClass, k), Domain.GEOGRAPHY, 1)
        out.append(c.model_copy(update={
            "constraint_id": cid, "verification_status": s,
            "answer_space": list(space),
        }))
    return out


def test_s1_refuses_a_confounded_class_but_still_reports_both_means():
    """"We could not estimate this" and "we did not look" are different claims."""
    cons = _cons([
        ("K-C1-GEO-01", "C1", "EVIDENCE_VERIFIED", ["YES", "NO"]),
        ("K-C1-GEO-02", "C1", "EVIDENCE_VERIFIED", ["YES", "NO"]),
        ("K-C1-GEO-03", "C1", "DRAFT", ["a", "b", "c"]),
        ("K-C1-GEO-04", "C1", "DRAFT", ["a", "b", "c"]),
    ])
    rows = _rows([
        ("K-C1-GEO-01", "C1", "EVIDENCE_VERIFIED", 0.20),
        ("K-C1-GEO-02", "C1", "EVIDENCE_VERIFIED", 0.30),
        ("K-C1-GEO-03", "C1", "DRAFT", 0.60),
        ("K-C1-GEO-04", "C1", "DRAFT", 0.70),
    ])
    out = s1_within_class(rows, cons, n_boot=200, seed=1)["C1"]
    assert out["comparability"] == CONFOUNDED_ANSWER_TYPE
    assert out["estimate"] is None
    assert "refusal" in out
    assert out["mean_verified"] == pytest.approx(0.25)
    assert out["mean_draft"] == pytest.approx(0.65)


def test_s1_estimates_a_comparable_class():
    cons = _cons([
        (f"K-C2-GEO-{i:02d}", "C2",
         "EVIDENCE_VERIFIED" if i <= 4 else "DRAFT", ["YES", "NO"])
        for i in range(1, 9)
    ])
    rows = _rows([
        (f"K-C2-GEO-{i:02d}", "C2",
         "EVIDENCE_VERIFIED" if i <= 4 else "DRAFT",
         0.3 if i <= 4 else 0.5)
        for i in range(1, 9)
    ])
    out = s1_within_class(rows, cons, n_boot=400, seed=1)["C2"]
    assert out["comparable"] is True
    assert out["estimate"] == pytest.approx(-0.2)
    assert out["unit"] == "constraint"
    assert "refusal" not in out


def test_s1_refuses_a_class_with_no_overlap():
    cons = _cons([("K-C4-GEO-01", "C4", "DRAFT", ["a", "b", "c"])])
    rows = _rows([("K-C4-GEO-01", "C4", "DRAFT", 0.5)])
    out = s1_within_class(rows, cons, n_boot=100, seed=1)["C4"]
    assert out["comparability"] == NOT_ASSESSABLE_NO_OVERLAP
    assert out["estimate"] is None


def test_s1_carries_undefined_pscr_without_imputing_zero():
    """Q6: an undefined cell contributes nothing; it is never read as 0.0."""
    cons = _cons([
        (f"K-C2-GEO-{i:02d}", "C2",
         "EVIDENCE_VERIFIED" if i <= 3 else "DRAFT", ["YES", "NO"])
        for i in range(1, 7)
    ])
    rows = _rows([
        ("K-C2-GEO-01", "C2", "EVIDENCE_VERIFIED", 0.4),
        ("K-C2-GEO-02", "C2", "EVIDENCE_VERIFIED", None),
        ("K-C2-GEO-03", "C2", "EVIDENCE_VERIFIED", 0.4),
        ("K-C2-GEO-04", "C2", "DRAFT", 0.6),
        ("K-C2-GEO-05", "C2", "DRAFT", 0.6),
        ("K-C2-GEO-06", "C2", "DRAFT", None),
    ])
    out = s1_within_class(rows, cons, n_boot=200, seed=1)["C2"]
    assert out["n_verified"] == 3 and out["n_verified_defined"] == 2
    assert out["mean_verified"] == pytest.approx(0.4)
    assert out["estimate"] == pytest.approx(-0.2)


# --- S3 must never be mistaken for H1_primary ----------------------------

@needs_split
def test_s3_on_the_real_benchmark_refuses_the_h1_primary_name(frozen_constraints):
    rows = [
        {"constraint_id": c.constraint_id, "class": c.constraint_class.value,
         "verification_status": str(c.verification_status), "pscr": 0.4}
        for c in frozen_constraints
    ]
    out = s3_restricted_contrast(rows, frozen_constraints, n_boot=200, seed=1)
    assert out["is_h1_primary"] is False
    assert out["classes_dropped"] == ["C4"]
    assert "DIFFERENT contrast from H1_primary" in out["warning"]
    assert "H1_primary" not in out["name"]


@needs_split
def test_s3_reports_the_chance_gap_and_its_direction(frozen_constraints):
    rows = [
        {"constraint_id": c.constraint_id, "class": c.constraint_class.value,
         "verification_status": str(c.verification_status), "pscr": 0.4}
        for c in frozen_constraints
    ]
    out = s3_restricted_contrast(rows, frozen_constraints, n_boot=200, seed=1)
    assert out["chance_gap"] == pytest.approx(0.0417, abs=5e-4)
    note = out["chance_balance_note"]
    assert "positive" in note
    assert "AGAINST" in note, "the gap opposes the observed negative sign"


@needs_split
def test_s2_is_descriptive_and_says_so(frozen_constraints):
    rows = [
        {"constraint_id": c.constraint_id, "class": c.constraint_class.value,
         "verification_status": str(c.verification_status), "pscr": 0.4}
        for c in frozen_constraints
    ]
    out = s2_verified_only_profile(rows, n_boot=200, seed=1)
    assert out["C4"]["n_constraints"] == 0
    assert out["C4"]["estimate"] is None
    for klass in ("C1", "C2", "C3"):
        assert out[klass]["n_constraints"] == 16
        assert "NOT a contrast" in out[klass]["note"]


# --- S4: probe-exclusion sensitivity (Q33) -------------------------------

def test_s4_plan_quantifies_what_exclusion_costs_the_design():
    """The plan must be inspectable BEFORE any estimate is produced."""
    from semintegrity.analysis.sensitivity import s4_probe_exclusion_plan

    class _P:
        def __init__(self, pid): self.probe_id = pid

    probes = {
        "K-C1-GEO-11": [_P(f"K-C1-GEO-11-P{i:02d}") for i in range(1, 9)],
        "K-C1-GEO-12": [_P(f"K-C1-GEO-12-P{i:02d}") for i in range(1, 9)],
    }
    plan = s4_probe_exclusion_plan(
        probes, ["K-C1-GEO-11-P04", "K-C1-GEO-11-P07"]
    )
    assert plan["n_probes"] == 16
    assert plan["n_excluded"] == 2
    assert plan["n_constraints_affected"] == 1
    a = plan["affected"]["K-C1-GEO-11"]
    assert (a["k_before"], a["k_after"]) == (8, 6)
    assert (a["pairs_before"], a["pairs_after"]) == (28, 15)
    assert a["factor_cells_dropped"] == ["04", "07"]
    assert plan["pairs_lost"] == 13
    assert plan["exclusion_is_response_independent"] is True
    assert "K=8 remains the primary" in plan["primary_design_unchanged"]
    assert "ADR-0003" in plan["cost"]


@needs_split
def test_s4_plan_on_the_real_43_flagged_probes(frozen_constraints):
    """Measured: what Q33's exclusion would actually cost."""
    from semintegrity.analysis.sensitivity import s4_probe_exclusion_plan
    from semintegrity.probes.pathology import audit

    _, probe_list = load_split(TEST_SPLIT)
    by: dict[str, list] = {}
    for p in probe_list:
        by.setdefault(p.constraint_id, []).append(p)
    findings, _ = audit(frozen_constraints, by)
    plan = s4_probe_exclusion_plan(by, [f.probe_id for f in findings])

    assert plan["n_excluded"] == 43
    assert plan["n_constraints_affected"] == 27
    assert plan["min_k_after"] == 6, "no constraint drops below K=6"
    # 11 constraints lose 1 probe (28->21, -7) and 16 lose 2 (28->15, -13)
    assert plan["pairs_lost"] == 11 * 7 + 16 * 13
    assert plan["excluded_share"] == pytest.approx(43 / 960)


def test_s4_is_paired_and_refuses_mismatched_constraints():
    from semintegrity.analysis.sensitivity import s4_probe_exclusion

    full = _rows([("K-C1-GEO-01", "C1", "DRAFT", 0.4)])
    excl = _rows([("K-C1-GEO-02", "C1", "DRAFT", 0.3)])
    with pytest.raises(ValueError, match="PAIRED"):
        s4_probe_exclusion(full, excl, n_boot=50, seed=1)


def test_s4_is_secondary_and_says_which_figure_is_primary():
    from semintegrity.analysis.sensitivity import s4_probe_exclusion

    full = _rows([(f"K-C1-GEO-{i:02d}", "C1", "DRAFT", 0.5) for i in range(1, 9)])
    excl = _rows([(f"K-C1-GEO-{i:02d}", "C1", "DRAFT", 0.4) for i in range(1, 9)])
    out = s4_probe_exclusion(full, excl, n_boot=400, seed=1)
    assert out["is_primary"] is False
    assert out["paired"] is True
    assert out["estimate"] == pytest.approx(0.1)
    assert out["unit"] == "constraint"
    assert "K=8 is the PRIMARY design" in out["interpretation_limit"]
    assert "does not establish which figure is correct" in out["interpretation_limit"]
