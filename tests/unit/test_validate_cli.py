"""The `benchmark.validate` CLI is the preflight gate a Slurm job runs before
spending an A100 allocation (`slurm/20_pilot_one_model.sbatch` gates on its exit
code). It had no tests at all, which is how a fail-open path survived in it.

Every test here asserts an EXIT CODE, not printed text: the exit code is the
only thing the gate actually reads.
"""

import pytest

from semintegrity.benchmark import validate as validate_cli
from semintegrity.benchmark.loader import save_constraints, save_probes
from semintegrity.probes.factor_design import cells_for_constraint
from semintegrity.schemas.enums import ConstraintClass, Domain, Split
from semintegrity.schemas.probe import Probe
from semintegrity.utils.ids import probe_id
from semintegrity.utils.paths import data_path
from tests.fixtures.synthetic_benchmark import make_constraint

PILOT = data_path("benchmark") / "pilot"
pytestmark = pytest.mark.skipif(
    not (PILOT / "constraints.jsonl").is_file(),
    reason="pilot benchmark not built; run scripts/benchmark/build_pilot.py",
)


def _probes_for(constraint, k=8):
    out = []
    for i, cell in enumerate(cells_for_constraint(0, k), start=1):
        text = f"probe {i} for {constraint.constraint_id}"
        if cell.syntax.value == "cloze":
            text += " ___"
        out.append(
            Probe(
                constraint_id=constraint.constraint_id,
                probe_id=probe_id(constraint.constraint_id, i),
                logical_form=f"lf({constraint.constraint_id})",
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
def synthetic_split(tmp_path, monkeypatch):
    """A structurally valid split whose predicate is NOT in the D0 registry.

    `make_constraint` emits `c1_synthetic_00`; the registry holds only the four
    real predicates. That is exactly the shape of a `formal_predicate` typo.
    """
    directory = tmp_path / "pilot"
    directory.mkdir()
    constraint = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1, split=Split.PILOT)
    save_constraints(directory / "constraints.jsonl", [constraint])
    save_probes(directory / "probes.jsonl", _probes_for(constraint))
    monkeypatch.setattr(validate_cli, "data_path", lambda _key: tmp_path)
    return directory


def test_the_real_pilot_passes_at_k_eight():
    assert validate_cli.main(["--split", "pilot", "--k", "8"]) == 0


def test_the_real_pilot_fails_at_k_five():
    """K=5 was written into configs/inference/pilot.yaml at one point while the
    authored benchmark held 96 probes = 12 x 8. The gate must catch that drift
    rather than let a job run against a K the benchmark does not have.
    """
    assert validate_cli.main(["--split", "pilot", "--k", "5"]) != 0


def test_a_missing_split_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_cli, "data_path", lambda _key: tmp_path)
    assert validate_cli.main(["--split", "pilot"]) == 2


def test_unregistered_predicate_is_a_warning_by_default(synthetic_split):
    """Documents the CURRENT policy, so that changing it is a deliberate act.

    An unregistered predicate may be a legitimate D0 coverage gap (§4.8.1 makes
    coverage a result in its own right), so the default stays non-fatal.
    """
    assert validate_cli.main(["--split", "pilot"]) == 0


def test_strict_d0_turns_an_unregistered_predicate_into_a_failure(synthetic_split):
    """The fail-open that mattered: without this, a `formal_predicate` typo
    passes preflight, burns the allocation, and is then reported as a D0
    coverage gap rather than as the bug it is.
    """
    assert validate_cli.main(["--split", "pilot", "--strict-d0"]) == 1


def test_strict_d0_does_not_fire_when_every_predicate_resolves():
    """A guard that always fires is as useless as one that never does."""
    assert validate_cli.main(["--split", "pilot", "--k", "8", "--strict-d0"]) == 0
