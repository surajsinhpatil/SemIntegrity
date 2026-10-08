"""The deterministic authoring manifest must match the approved allocation.

The manifest is what authoring will be driven from, so "did we author exactly
the approved cells?" has to be a diff rather than a judgement. These tests pin
it to the Revision 3 matrix, to ADR-0007's dev set and to the accounting in
`docs/AUTHORING_PLAN.md`.

The manifest deliberately holds the allocation ONLY — no entities, QIDs, gold
answers or sources — and a test asserts that, so a half-authored dataset can
never be mistaken for the plan.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from propose_authoring_plan import build_manifest  # noqa: E402

MANIFEST_PATH = REPO / "data" / "benchmark" / "authoring_manifest.json"


@pytest.fixture(scope="module")
def manifest():
    return build_manifest()


@pytest.fixture(scope="module")
def rows(manifest):
    return manifest["constraints"]


def test_on_disk_manifest_matches_the_generator():
    """Regenerate rather than edit: a hand-edited manifest is a silent fork."""
    assert MANIFEST_PATH.is_file(), f"run: propose_authoring_plan.py --manifest {MANIFEST_PATH}"
    on_disk = json.loads(MANIFEST_PATH.read_text())
    assert on_disk == build_manifest(), "manifest on disk has drifted from the generator"


# --- accounting, exactly as docs/AUTHORING_PLAN.md states it --------------
def test_total_is_132(rows):
    assert len(rows) == 132


def test_split_totals(rows):
    counts = Counter(r["split"] for r in rows)
    assert counts == {"test": 120, "dev": 12}


def test_class_totals_for_new_constraints(rows):
    assert Counter(r["class"] for r in rows) == {"C1": 33, "C2": 33, "C3": 33, "C4": 33}


@pytest.mark.parametrize("split,per_class", [("test", 30), ("dev", 3)])
def test_class_totals_per_split(rows, split, per_class):
    counts = Counter(r["class"] for r in rows if r["split"] == split)
    assert counts == {"C1": per_class, "C2": per_class, "C3": per_class, "C4": per_class}


def test_freeze_totals(manifest):
    t = manifest["totals"]
    assert t["existing_pilot_constraints_separate"] == 12
    assert t["existing_pilot_probes_separate"] == 96
    assert t["constraints_at_freeze"] == 144
    assert t["planned_probes"] == 1056
    assert t["primary_probes_at_freeze"] == 1152


def test_every_constraint_expects_eight_probes(rows):
    assert {r["probes_expected"] for r in rows} == {8}
    assert sum(r["probes_expected"] for r in rows) == 1056


# --- the test allocation is the matrix, cell for cell --------------------
def test_test_cells_are_exactly_the_matrix():
    from propose_coverage_matrix import allocate

    expected = {c.constraint_id for c in allocate()}
    on_plan = {r["constraint_id"] for r in build_manifest()["constraints"] if r["split"] == "test"}
    assert on_plan == expected
    assert len(expected) == 120


def test_test_lattice_balance(rows):
    test = [r for r in rows if r["split"] == "test"]
    assert len({r["family_id"] for r in test}) == 30
    assert len({r["schema_id"] for r in test}) == 24
    for domain in {r["domain"] for r in test}:
        for cls in ("C1", "C2", "C3", "C4"):
            n = sum(1 for r in test if r["domain"] == domain and r["class"] == cls)
            assert n == 6, (domain, cls, n)


def test_each_test_schema_has_five_instances(rows):
    """ADR-0002: 6 schemas x 5 instances per class."""
    test = [r for r in rows if r["split"] == "test"]
    counts = Counter(r["schema_id"] for r in test)
    assert set(counts.values()) == {5}
    assert sorted(r["instance_index"] for r in test if r["schema_id"] == "S-C1-01") == [
        1, 2, 3, 4, 5
    ]


def test_dev_uses_the_three_approved_families(rows):
    dev = [r for r in rows if r["split"] == "dev"]
    assert {(r["axis"], r["domain"]) for r in dev} == {
        (2, "history"),
        (3, "biology"),
        (4, "science_technology"),
    }
    assert {r["family_id"] for r in dev} == {"F-HIS-02", "F-BIO-03", "F-SCI-04"}
    assert {r["instance_index"] for r in dev} == {1}


# --- answer type follows ADR-0017 ----------------------------------------
# --- ADR-0017 as AMENDED 2026-10-07: answer type <- (axis, class) --------
# Regression tests 1-4 and 7 of the amendment brief. C2 and C3 are boolean on
# every axis because a conjunction and a universal have no single binary
# subject-relation-object, which the approved probe generator requires for a
# direct+affirmative probe of an entity/date-answered constraint.
def test_c2_is_boolean_on_every_axis_including_formerly_open_ones(rows):
    """Case 1: C2 on an axis whose old rule gave ENTITY/DATE is now BOOLEAN."""
    c2 = [r for r in rows if r["class"] == "C2"]
    assert {r["answer_type"] for r in c2} == {"boolean"}
    formerly_open = [r for r in c2 if r["axis"] in (1, 3, 4, 6)]
    assert formerly_open, "no C2 on a formerly open axis — the test would be vacuous"
    assert all(r["answer_type"] == "boolean" for r in formerly_open)


def test_c3_is_boolean_on_every_axis_including_formerly_open_ones(rows):
    """Case 2: C3 on an axis whose old rule gave ENTITY/DATE is now BOOLEAN."""
    c3 = [r for r in rows if r["class"] == "C3"]
    assert {r["answer_type"] for r in c3} == {"boolean"}
    formerly_open = [r for r in c3 if r["axis"] in (1, 3, 4, 6)]
    assert formerly_open
    assert all(r["answer_type"] == "boolean" for r in formerly_open)


@pytest.mark.parametrize(
    "axis,expected", [(1, "entity"), (2, "boolean"), (3, "entity"),
                      (4, "date"), (5, "boolean"), (6, "date")]
)
def test_c1_retains_the_axis_fixed_allocation(rows, axis, expected):
    """Case 3: C1 keeps its approved axis-specific type."""
    got = {r["answer_type"] for r in rows if r["class"] == "C1" and r["axis"] == axis}
    assert got == {expected}, (axis, got)


@pytest.mark.parametrize(
    "axis,expected", [(1, "entity"), (2, "boolean"), (3, "entity"),
                      (4, "date"), (5, "boolean"), (6, "date")]
)
def test_c4_retains_the_axis_fixed_allocation(rows, axis, expected):
    """Case 4: C4 keeps its approved axis-specific type."""
    got = {r["answer_type"] for r in rows if r["class"] == "C4" and r["axis"] == axis}
    assert got == {expected}, (axis, got)


def test_two_date_axes(rows):
    """Date answers survive only on C1/C4 of the two date axes."""
    assert {r["axis"] for r in rows if r["answer_type"] == "date"} == {4, 6}
    assert {r["class"] for r in rows if r["answer_type"] == "date"} == {"C1", "C4"}


def test_answer_type_is_a_function_of_axis_and_class(rows):
    by_cell: dict[tuple[int, str], set[str]] = {}
    for r in rows:
        by_cell.setdefault((r["axis"], r["class"]), set()).add(r["answer_type"])
    assert all(len(v) == 1 for v in by_cell.values()), by_cell


def test_no_allocation_exists_outside_the_approved_rule(rows):
    """Case 7: every row matches the rule read from design.yaml."""
    from semintegrity.benchmark.design_validator import answer_type_for_cell
    from semintegrity.schemas.enums import ConstraintClass

    for r in rows:
        expected = answer_type_for_cell(r["schema_id"], ConstraintClass(r["class"]))
        assert r["answer_type"] == expected, r["constraint_id"]


def test_confirmatory_arms_stay_balanced(rows):
    """The amendment's whole justification: C1+C2 vs C3+C4 remains artefact-free."""
    from statistics import mean

    card = {"entity": 3, "boolean": 2, "date": 3}
    test = [r for r in rows if r["split"] == "test"]
    per = {
        c: mean(1 - 1 / card[r["answer_type"]] for r in test if r["class"] == c)
        for c in ("C1", "C2", "C3", "C4")
    }
    assert mean([per["C1"], per["C2"]]) == pytest.approx(mean([per["C3"], per["C4"]]))
    assert per["C1"] == pytest.approx(per["C4"])
    assert per["C2"] == pytest.approx(per["C3"])
    # The descriptive spread the amendment explicitly accepts.
    assert max(per.values()) - min(per.values()) == pytest.approx(0.111, abs=5e-4)


# --- per-row policy flags ------------------------------------------------
def test_comparison_universe_required_exactly_on_axis_five(rows):
    needing = [r for r in rows if r["comparison_universe_required"]]
    assert {r["axis"] for r in needing} == {5}
    assert len(needing) == 20  # 4 classes x 5 domains, test only
    assert all(r["split"] == "test" for r in needing)


def test_corroboration_flag_matches_the_implemented_rule(rows):
    """Must mirror design_validator._corroboration, which reads design.yaml.

    The temporal AXIS is a trigger as well as the answer type. Without it the
    answer-type amendment would have narrowed §4.3 by moving C2/C3 on axes 4 and
    6 off `date`.
    """
    for r in rows:
        expected = (
            r["domain"] == "history"
            or r["answer_type"] == "date"
            or r["class"] == "C4"
            or r["axis"] in (4, 6)
        )
        assert r["corroboration_required"] is expected, r["constraint_id"]


def test_the_amendment_did_not_narrow_corroboration(rows):
    """81 constraints needed a second source before the amendment, and after."""
    assert sum(r["corroboration_required"] for r in rows) == 81


def test_every_row_carries_an_evidence_policy(rows):
    for r in rows:
        policy = r["evidence_policy"]
        assert policy["baseline"]
        assert policy["axis_specific"]
        assert isinstance(policy["special_handling"], bool)
        if policy["special_handling"]:
            assert policy["special_handling_note"]


def test_axes_needing_special_evidence_handling(rows):
    special = {r["axis"] for r in rows if r["evidence_policy"]["special_handling"]}
    assert special == {2, 3, 4, 5, 6}


def test_every_row_maps_to_a_registered_d0_predicate(rows):
    from semintegrity.detectors.d0.registry import PredicateRegistry

    reg = PredicateRegistry()
    reg.autodiscover()
    for r in rows:
        assert reg.has(r["d0_predicate"]), r["constraint_id"]


def test_c2_and_c3_carry_their_structural_limit(rows):
    for r in rows:
        if r["class"] in ("C2", "C3"):
            assert r["d0_structural_limit"] == "N/A-struct", r["constraint_id"]
        else:
            assert r["d0_structural_limit"] is None, r["constraint_id"]


# --- ids cannot collide --------------------------------------------------
def test_ids_are_unique_and_clear_of_the_pilot(rows):
    from semintegrity.benchmark.loader import load_split
    from semintegrity.utils.paths import data_path

    planned = [r["constraint_id"] for r in rows]
    assert len(set(planned)) == len(planned) == 132

    pilot, _ = load_split(data_path("benchmark") / "pilot")
    pilot_ids = {c.constraint_id for c in pilot}
    assert not (set(planned) & pilot_ids)
    assert len(set(planned) | pilot_ids) == 144


def test_index_ranges_keep_the_splits_apart(rows):
    def span(subset):
        return {int(r["constraint_id"].rsplit("-", 1)[1]) for r in subset}

    assert span([r for r in rows if r["split"] == "test"]) == {11, 12, 13, 14, 15, 16}
    assert span([r for r in rows if r["split"] == "dev"]) == {2, 3, 4}


# --- the manifest is a plan, not a dataset -------------------------------
def test_manifest_holds_no_ground_truth(rows):
    """No entity, QID, gold answer or source may appear in the manifest.

    If authoring ever starts writing content here, the plan and the dataset have
    merged and the diff that proves 'we authored exactly the approved cells'
    stops being possible.
    """
    forbidden = {
        "entities", "entity_qids", "entity_sitelinks", "gold_answer", "gold_proposition",
        "answer_space", "gold_source", "gold_source_url", "evidence", "comparison_universe",
        "constraint_text", "temporal_validity", "corroborating_sources",
    }
    for r in rows:
        assert not (forbidden & set(r)), sorted(forbidden & set(r))
        assert r["authoring_status"] == "NOT_AUTHORED"


def test_manifest_names_its_authoritative_sources(manifest):
    src = manifest["authoritative_sources"]
    assert "BENCHMARK_COVERAGE_MATRIX" in src["which_cells"]
    assert "Revision 3" in src["which_cells"]
    assert "AUTHORING_PLAN" in src["accounting"]
