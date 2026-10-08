"""The five authoring gates closed on 2026-10-07.

Each gate is tested twice: once that it **fires** on a violating input, and once
that the real pilot still passes. A gate that cannot fail is the same defect as
a gate that does not exist, which is the pattern these five were introduced to
close.

Two of them — cross-split ids and dev/test disjointness — were already
implemented and unit-tested before this pass, but nothing in the production path
called them. So the tests that matter most here assert that the ``validate``
CLI, which Slurm uses as its preflight gate, actually invokes them.
"""

from __future__ import annotations

import pytest
import yaml

from semintegrity.benchmark import validate as validate_cli
from semintegrity.benchmark.design_validator import BenchmarkDesignValidator
from semintegrity.benchmark.loader import (
    REQUIRED_FACTOR_CELLS,
    check_distinct_probe_texts,
    check_factor_cell_completeness,
    check_probe_sets,
    load_split,
)
from semintegrity.benchmark.pilot_builder import build
from semintegrity.schemas.enums import VerificationStatus
from semintegrity.schemas.probe import assert_distinct_surfaces
from semintegrity.utils.paths import data_path


@pytest.fixture(scope="module")
def pilot():
    return load_split(data_path("benchmark") / "pilot")


@pytest.fixture(scope="module")
def one_group(pilot):
    constraints, probes = pilot
    cid = constraints[0].constraint_id
    return [p for p in probes if p.constraint_id == cid]


# --- A. factor-cell completeness -----------------------------------------
def test_required_factor_cells_is_the_adr0003_crossing():
    assert len(REQUIRED_FACTOR_CELLS) == 8
    assert ("affirmative", "formal", "direct") in REQUIRED_FACTOR_CELLS
    assert ("negated", "colloquial", "reverse") in REQUIRED_FACTOR_CELLS


def test_pilot_is_factor_cell_complete(pilot):
    constraints, probes = pilot
    for c in constraints:
        group = [p for p in probes if p.constraint_id == c.constraint_id]
        assert check_factor_cell_completeness(group) == [], c.constraint_id


def test_completeness_catches_what_distinctness_cannot(one_group):
    """The precise gap: 8 probes, all 4-tuples distinct, a required cell missing.

    Duplicating one (polarity, register, directionality) cell under a different
    syntax keeps every surface_key unique, so ``assert_distinct_surfaces``
    passes — and the exact class-level balance ADR-0003 guarantees is broken
    anyway.
    """
    victim, donor = one_group[0], one_group[1]
    # Give `donor`'s cell to `victim`, but under a different syntax.
    other_syntax = next(
        s for s in ("declarative", "interrogative", "cloze") if s != donor.syntax.value
    )
    clashing = victim.model_copy(
        update={
            "polarity": donor.polarity,
            "register": donor.register,
            "directionality": donor.directionality,
            "syntax": other_syntax,
        }
    )
    group = [clashing, *one_group[1:]]

    assert_distinct_surfaces(group)  # must NOT raise — this is the blind spot

    problems = check_factor_cell_completeness(group)
    assert problems, "completeness gate failed to fire"
    assert any("missing" in p for p in problems)
    assert any("appears 2 times" in p for p in problems)


def test_completeness_runs_from_check_probe_sets(pilot, one_group):
    constraints, _ = pilot
    c = next(c for c in constraints if c.constraint_id == one_group[0].constraint_id)
    swapped = one_group[0].model_copy(
        update={
            "polarity": one_group[1].polarity,
            "register": one_group[1].register,
            "directionality": one_group[1].directionality,
            "syntax": "cloze" if one_group[1].syntax.value != "cloze" else "declarative",
        }
    )
    problems = check_probe_sets([c], [swapped, *one_group[1:]], k=8)
    assert any("factor cell" in p for p in problems), problems


# --- B. duplicate probe text ----------------------------------------------
def test_pilot_has_no_duplicate_probe_text(pilot):
    constraints, probes = pilot
    for c in constraints:
        group = [p for p in probes if p.constraint_id == c.constraint_id]
        assert check_distinct_probe_texts(group) == [], c.constraint_id


def test_duplicate_text_is_detected(one_group):
    dup = one_group[1].model_copy(update={"probe_text": one_group[0].probe_text})
    problems = check_distinct_probe_texts([one_group[0], dup, *one_group[2:]])
    assert problems
    assert "identical text" in problems[0]


def test_duplicate_text_is_a_hard_failure_not_a_warning(pilot, one_group):
    """It must reach the list `check_probe_sets` returns, which the CLI exits on."""
    constraints, _ = pilot
    c = next(c for c in constraints if c.constraint_id == one_group[0].constraint_id)
    dup = one_group[1].model_copy(update={"probe_text": one_group[0].probe_text})
    problems = check_probe_sets([c], [one_group[0], dup, *one_group[2:]], k=8)
    assert any("identical text" in p for p in problems), problems


def test_builder_still_produces_distinct_texts():
    """Variant A must not have collided two probes of one constraint."""
    candidates = yaml.safe_load(
        (data_path("benchmark") / "pilot" / "candidates.yaml").read_text(encoding="utf-8")
    )
    result = build(candidates)
    assert [w for w in result.warnings if "identical text" in w] == []


# --- C. second-source corroboration ---------------------------------------
def _needs_corroboration(constraints):
    return next(c for c in constraints if c.answer_type.value == "date")


def test_policy_is_read_from_the_config_not_restated():
    """The rule must take its policy from design.yaml, not carry its own copy."""
    gt = BenchmarkDesignValidator().cfg["ground_truth"]
    assert gt["second_source_required"] is True
    assert set(gt["corroboration_required_for"]) == {"history", "temporal_facts"}


def test_draft_without_corroboration_is_a_warning(pilot):
    constraints, _ = pilot
    report = BenchmarkDesignValidator().validate(constraints, split=constraints[0].split)
    rule = next(r for r in report.results if r.rule == "corroboration")
    assert not rule.passed
    assert rule.severity == "warning"
    assert report.ok, "a DRAFT without a second source must not block the preflight"
    assert any("C4" in o for o in rule.offenders)


def test_promotion_without_corroboration_is_an_error(pilot):
    constraints, _ = pilot
    target = _needs_corroboration(constraints)
    promoted = target.model_copy(
        update={"verification_status": VerificationStatus.EVIDENCE_VERIFIED}
    )
    others = [c for c in constraints if c.constraint_id != target.constraint_id]
    report = BenchmarkDesignValidator().validate([*others, promoted], split=target.split)
    rule = next(r for r in report.results if r.rule == "corroboration")
    assert not rule.passed
    assert rule.severity == "error"
    assert not report.ok
    assert any(target.constraint_id in o for o in rule.offenders)


def test_a_plain_gold_source_is_no_longer_accepted_as_corroboration(pilot):
    """§4.3's second source needs provenance a GoldSource does not carry.

    Superseded 2026-10-07: `corroborating_sources` is typed
    `list[CorroboratingSource]`, which additionally requires a provider, a
    frozen snapshot, a content hash and the exact fact supported. A bare
    name/url/date is not corroboration.
    """
    from pydantic import ValidationError

    from semintegrity.schemas.constraint import Constraint, GoldSource

    constraints, _ = pilot
    target = next(c for c in constraints if c.answer_type.value == "date")
    bare = GoldSource(
        name="Some Reference Work",
        url="https://ref.example.test/x",
        retrieved="2026-10-07",
    )
    with pytest.raises(ValidationError):
        Constraint.model_validate(
            {**target.to_record(), "corroborating_sources": [bare.model_dump(mode="json")]}
        )


def test_corroboration_is_unsatisfied_until_a_source_is_actually_recorded(pilot):
    """A DRAFT without a second source warns; it does not pass and does not block.

    ADR-0019 approved a provider list, so the rule no longer reports "policy not
    configured" — it reports the thing that is actually missing. The severity
    ladder is unchanged: a warning while DRAFT, an error at promotion.
    """
    constraints, _ = pilot
    report = BenchmarkDesignValidator().validate(constraints, split=constraints[0].split)
    rule = next(r for r in report.results if r.rule == "corroboration")
    assert not rule.passed
    assert rule.severity == "warning"  # DRAFT may warn
    assert "lack a valid second source" in rule.message
    assert "not yet configured" not in rule.message
    assert report.ok, "a DRAFT without a usable second source must not block preflight"


def test_non_temporal_constraints_need_no_second_source(pilot):
    """The requirement must not be widened beyond §4.3."""
    constraints, _ = pilot
    entity = next(c for c in constraints if c.answer_type.value == "entity")
    assert entity.corroborating_sources == []
    report = BenchmarkDesignValidator().validate([entity], split=entity.split)
    rule = next(r for r in report.results if r.rule == "corroboration")
    assert rule.passed, "an entity constraint was asked for corroboration it does not need"


# --- D + E. the cross-split gates run from the CLI ------------------------
def test_cli_invokes_both_cross_split_gates(capsys):
    """The gap these closed was 'implemented but never called'.

    So the assertion is about the production entry point, not the functions.
    """
    rc = validate_cli.main(["--split", "pilot", "--k", "8"])
    out = capsys.readouterr().out
    assert "cross-split rules over" in out
    assert "cross_split_ids" in out
    assert "dev_test_disjoint" in out
    assert rc == 0


def test_cli_reports_disjointness_as_vacuous_when_a_split_is_absent(capsys, monkeypatch):
    """A check that cannot discriminate must say VACUOUS, never PASS.

    Driven by a stubbed split load rather than by the repository's data state: the
    test split now exists on disk (authoring began 2026-10-07), so the live
    condition this used to rely on is gone, while the behaviour it pins is not.
    """
    from tests.fixtures.synthetic_benchmark import dev_set

    monkeypatch.setattr(validate_cli, "_load_all_splits", lambda: (dev_set(), ["dev=6"]))
    validate_cli.main(["--split", "pilot", "--k", "8"])
    out = capsys.readouterr().out
    assert "[VACUOUS] dev_test_disjoint" in out
    assert "NOT a pass" in out


def test_cli_reports_a_real_disjointness_verdict_once_both_splits_exist(capsys):
    """And with both splits on disk it must stop hedging and decide."""
    validate_cli.main(["--split", "pilot", "--k", "8"])
    out = capsys.readouterr().out
    assert "dev_test_disjoint" in out
    assert "[VACUOUS] dev_test_disjoint" not in out, (
        "a test split exists on disk, so the check can discriminate and must report "
        "a real verdict"
    )


def test_cli_still_exits_zero_on_the_real_pilot(capsys):
    assert validate_cli.main(["--split", "pilot", "--k", "8", "--strict-lattice"]) == 0
    out = capsys.readouterr().out
    assert "all 8 factor cells present exactly once" in out
    assert "no duplicate probe text" in out


def test_split_disjointness_still_catches_a_leak():
    from tests.fixtures.synthetic_benchmark import dev_set, full_benchmark

    v = BenchmarkDesignValidator()
    test = full_benchmark()
    leaked = dev_set()[0].model_copy(
        update={"entity_qids": test[0].entity_qids, "entities": test[0].entities,
                "entity_sitelinks": test[0].entity_sitelinks}
    )
    rule = v.validate_split_disjointness([*test, leaked])
    assert not rule.passed
    assert any("entity set" in o for o in rule.offenders)
