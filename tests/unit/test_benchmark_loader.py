"""Benchmark persistence, structural checks and the freeze."""

import pytest

from semintegrity.benchmark.loader import (
    BenchmarkFrozenError,
    check_probe_sets,
    content_hash,
    freeze,
    is_frozen,
    load_split,
    save_constraints,
    save_probes,
    verify_freeze,
)
from semintegrity.probes.factor_design import cells_for_constraint
from semintegrity.schemas.enums import ConstraintClass, Domain, Split
from semintegrity.schemas.probe import Probe
from semintegrity.utils.ids import probe_id
from tests.fixtures.synthetic_benchmark import make_constraint


def _probes_for(constraint, k=8, constraint_index=0, break_equivalence=False):
    out = []
    for i, cell in enumerate(cells_for_constraint(constraint_index, k), start=1):
        text = f"probe {i} for {constraint.constraint_id}"
        if cell.syntax.value == "cloze":
            text += " ___"
        out.append(
            Probe(
                constraint_id=constraint.constraint_id,
                probe_id=probe_id(constraint.constraint_id, i),
                logical_form=f"lf({constraint.constraint_id})" + (f"-{i}" if break_equivalence else ""),
                subject="S", predicate="P", object="", time_scope="",
                quantifier="none", polarity=cell.polarity.value,
                answer_type="entity", syntax=cell.syntax.value,
                register=cell.register.value, directionality=cell.directionality.value,
                factor_cell_index=cell.cell_index, probe_text=text,
                expected_answer=constraint.gold_answer,
            )
        )
    return out


@pytest.fixture
def split_dir(tmp_path):
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1, split=Split.PILOT)
    save_constraints(tmp_path / "constraints.jsonl", [c])
    save_probes(tmp_path / "probes.jsonl", _probes_for(c))
    return tmp_path


def test_round_trip(split_dir):
    constraints, probes = load_split(split_dir)
    assert len(constraints) == 1 and len(probes) == 8
    assert constraints[0].constraint_id == "K-C1-GEO-01"


def test_structural_checks_pass_on_a_well_formed_set(split_dir):
    constraints, probes = load_split(split_dir)
    assert check_probe_sets(constraints, probes, k=8) == []


def test_wrong_probe_count_is_reported(split_dir):
    constraints, probes = load_split(split_dir)
    problems = check_probe_sets(constraints, probes[:-1], k=8)
    assert any("7 probes, expected 8" in p for p in problems)


def test_non_equivalent_probes_are_reported(tmp_path):
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1, split=Split.PILOT)
    probes = _probes_for(c, break_equivalence=True)
    problems = check_probe_sets([c], probes, k=8)
    assert any("not mutually equivalent" in p for p in problems)


def test_orphan_probes_are_reported(split_dir):
    constraints, probes = load_split(split_dir)
    problems = check_probe_sets([], probes, k=8)
    assert any("not in this split" in p for p in problems)


def test_malformed_line_raises_with_its_line_number(tmp_path):
    (tmp_path / "constraints.jsonl").write_text('{"constraint_id": "nope"}\n')
    with pytest.raises(ValueError, match=r"constraints.jsonl:1"):
        load_split(tmp_path)


# --- freeze ----------------------------------------------------------------
def test_freeze_writes_a_manifest_and_detects_no_drift(split_dir):
    assert not is_frozen(split_dir)
    freeze(split_dir, split=Split.PILOT, k=8, note="phase 1 pilot")
    assert is_frozen(split_dir)
    assert verify_freeze(split_dir) == []


def test_writing_to_a_frozen_split_is_refused(split_dir):
    freeze(split_dir, split=Split.PILOT, k=8)
    c = make_constraint(ConstraintClass.C2, Domain.HISTORY, 1, split=Split.PILOT)
    with pytest.raises(BenchmarkFrozenError, match="is frozen"):
        save_constraints(split_dir / "constraints.jsonl", [c])


def test_content_change_after_freeze_is_detected(split_dir):
    freeze(split_dir, split=Split.PILOT, k=8)
    path = split_dir / "constraints.jsonl"
    path.write_text(path.read_text().replace("AnsX", "AnsQ"))
    problems = verify_freeze(split_dir)
    assert any("CONTENT CHANGED" in p for p in problems)


def test_freeze_refuses_a_structurally_broken_benchmark(tmp_path):
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1, split=Split.PILOT)
    save_constraints(tmp_path / "constraints.jsonl", [c])
    save_probes(tmp_path / "probes.jsonl", _probes_for(c)[:5])
    with pytest.raises(BenchmarkFrozenError, match="structural problems"):
        freeze(tmp_path, split=Split.PILOT, k=8)


def test_content_hash_is_order_independent(split_dir):
    constraints, probes = load_split(split_dir)
    assert content_hash(constraints, probes) == content_hash(
        constraints, list(reversed(probes))
    )
