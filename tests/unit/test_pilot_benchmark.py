"""The pilot benchmark must conform to the schema, the factor design and the
verification ladder. These tests run against the REAL records on disk.
"""

from collections import Counter
from itertools import product

import pytest
import yaml

from semintegrity.benchmark.design_validator import BenchmarkDesignValidator
from semintegrity.benchmark.loader import check_probe_sets, is_frozen, load_split
from semintegrity.benchmark.pilot_builder import K_PILOT, answer_type_by_class, build
from semintegrity.detectors.d0.registry import default_registry
from semintegrity.probes.factor_design import CELL_ORDER
from semintegrity.probes.surface import realised_factors
from semintegrity.schemas.enums import (
    ConstraintClass,
    Directionality,
    Polarity,
    Register,
    Split,
    Syntax,
    VerificationStatus,
)
from semintegrity.utils.paths import data_path

PILOT = data_path("benchmark") / "pilot"
pytestmark = pytest.mark.skipif(
    not (PILOT / "constraints.jsonl").is_file(),
    reason="pilot benchmark not built; run scripts/benchmark/build_pilot.py",
)


@pytest.fixture(scope="module")
def pilot():
    return load_split(PILOT)


@pytest.fixture(scope="module")
def candidates():
    return yaml.safe_load((PILOT / "candidates.yaml").read_text(encoding="utf-8"))


# --- size and structure ----------------------------------------------------
def test_twelve_constraints_three_per_class(pilot):
    constraints, _ = pilot
    assert len(constraints) == 12
    assert Counter(c.constraint_class for c in constraints) == {
        ConstraintClass.C1: 3, ConstraintClass.C2: 3,
        ConstraintClass.C3: 3, ConstraintClass.C4: 3,
    }


def test_three_complete_families_one_domain_each(pilot):
    constraints, _ = pilot
    by_family: dict[str, list] = {}
    for c in constraints:
        by_family.setdefault(c.family_id, []).append(c)
    assert len(by_family) == 3
    for fam, members in by_family.items():
        assert len(members) == 4, fam
        assert {m.constraint_class.value for m in members} == {"C1", "C2", "C3", "C4"}
        assert len({m.domain for m in members}) == 1, f"{fam} spans domains"


def test_every_constraint_is_in_the_pilot_split(pilot):
    constraints, probes = pilot
    assert all(c.split is Split.PILOT for c in constraints)
    assert all(p.tier.value == "pilot" for p in probes)


# --- probes and factor design ----------------------------------------------
def test_ninety_six_probes_eight_per_constraint(pilot):
    constraints, probes = pilot
    assert len(probes) == len(constraints) * K_PILOT == 96
    assert Counter(p.constraint_id for p in probes) == {
        c.constraint_id: K_PILOT for c in constraints
    }


def test_probe_sets_pass_the_structural_checks(pilot):
    constraints, probes = pilot
    assert check_probe_sets(constraints, probes, k=K_PILOT) == []


def test_every_constraint_covers_the_full_2x2x2_lattice(pilot):
    """ADR-0003: (polarity x register x direction) appears exactly once each."""
    _, probes = pilot
    by_cid: dict[str, list] = {}
    for p in probes:
        by_cid.setdefault(p.constraint_id, []).append(p)
    for cid, group in by_cid.items():
        triples = {(p.polarity, p.register, p.directionality) for p in group}
        assert len(triples) == len(CELL_ORDER) == 8, cid
        assert Counter(p.polarity for p in group) == {
            Polarity.AFFIRMATIVE: 4, Polarity.NEGATED: 4
        }, cid
        assert Counter(p.register for p in group) == {
            Register.FORMAL: 4, Register.COLLOQUIAL: 4
        }, cid
        assert Counter(p.directionality for p in group) == {
            Directionality.DIRECT: 4, Directionality.REVERSE: 4
        }, cid


def test_syntax_splits_three_three_two_within_each_constraint(pilot):
    """8 is not divisible by 3; balance is a class-level property (ADR-0003)."""
    _, probes = pilot
    by_cid: dict[str, list] = {}
    for p in probes:
        by_cid.setdefault(p.constraint_id, []).append(p)
    for cid, group in by_cid.items():
        assert sorted(Counter(p.syntax for p in group).values(), reverse=True) == [3, 3, 2], cid


def test_all_twenty_four_factor_cells_appear_across_the_pilot(pilot):
    _, probes = pilot
    seen = {(p.syntax, p.polarity, p.register, p.directionality) for p in probes}
    assert len(seen) == 24 == len(list(product(Syntax, Polarity, Register, Directionality)))


def test_no_two_probes_of_a_constraint_share_text(pilot):
    """Identical surfaces would inflate apparent agreement."""
    _, probes = pilot
    by_cid: dict[str, list] = {}
    for p in probes:
        by_cid.setdefault(p.constraint_id, []).append(p)
    for cid, group in by_cid.items():
        texts = [" ".join(p.probe_text.lower().split()) for p in group]
        assert len(set(texts)) == len(texts), f"{cid} has duplicate probe text"


def test_cloze_probes_carry_a_blank(pilot):
    _, probes = pilot
    assert all("___" in p.probe_text for p in probes if p.syntax is Syntax.CLOZE)


def test_every_factor_is_actually_realised_in_every_constraint(candidates):
    """A factor that never changes the text is a constant wearing a factor's name."""
    unrealised = {}
    for family in candidates["families"]:
        for spec in family["constraints"]:
            flags = realised_factors(
                slots=spec["surface"],
                answer_type=__import__(
                    "semintegrity.schemas.enums", fromlist=["AnswerType"]
                ).AnswerType(spec["answer_type"]),
                gold_answer=str(spec["gold_answer"]),
            )
            if not all(flags.values()):
                unrealised[spec["constraint_id"]] = flags
    assert not unrealised, f"factors recorded but not varied: {unrealised}"


def test_expected_answers_are_in_a_recognisable_space(pilot):
    constraints, probes = pilot
    by_cid = {c.constraint_id: c for c in constraints}
    for p in probes:
        c = by_cid[p.constraint_id]
        allowed = set(c.answer_space) | {"YES", "NO"}
        assert p.expected_answer in allowed, f"{p.probe_id}: {p.expected_answer}"


# --- verification ladder (integrity rules) ---------------------------------
def test_nothing_claims_human_validation(pilot):
    """Integrity rule 2: no constraint may claim a human validated it."""
    constraints, _ = pilot
    for c in constraints:
        assert c.verification_status is not VerificationStatus.HUMAN_VALIDATED, c.constraint_id
        assert c.verification_status is not VerificationStatus.FROZEN, c.constraint_id
        assert c.human_validated_by is None
        assert c.human_validated_at is None


def test_the_pilot_split_is_not_frozen():
    """Integrity rule 3: nothing is frozen until it has passed the process."""
    assert not is_frozen(PILOT)


def test_evidence_verified_constraints_have_passing_evidence(pilot):
    constraints, _ = pilot
    for c in constraints:
        if c.verification_status is VerificationStatus.EVIDENCE_VERIFIED:
            assert any(e.supports_gold for e in c.evidence), c.constraint_id


def test_every_constraint_carries_traceable_evidence_or_is_draft(pilot):
    """Integrity rule 5: evidence, or an explicit unverified-draft label."""
    constraints, _ = pilot
    for c in constraints:
        if c.verification_status is VerificationStatus.DRAFT:
            continue
        assert c.evidence, f"{c.constraint_id} claims {c.verification_status.value} with no evidence"
        for e in c.evidence:
            assert e.url and e.comparison and e.retrieved_at


def test_no_synthetic_fixture_content_in_the_pilot(pilot):
    """Integrity rule 6: test fixtures are never benchmark data."""
    from tests.fixtures.synthetic_benchmark import SYNTHETIC_MARKER

    constraints, probes = pilot
    blob = " ".join(
        [c.model_dump_json() for c in constraints] + [p.model_dump_json() for p in probes]
    )
    assert SYNTHETIC_MARKER not in blob


# --- validators ------------------------------------------------------------
def test_design_validator_passes_on_the_pilot(pilot):
    constraints, _ = pilot
    report = BenchmarkDesignValidator().validate(
        constraints, split=Split.PILOT, known_predicates=default_registry().names()
    )
    assert report.ok, str(report)


def test_every_predicate_resolves(pilot):
    constraints, _ = pilot
    registry = default_registry()
    assert all(registry.has(c.formal_predicate) for c in constraints)


def test_sitelinks_are_populated(pilot):
    """Entity familiarity is the §4.3 covariate; a zero here means it was never fetched."""
    constraints, _ = pilot
    missing = [c.constraint_id for c in constraints if all(s == 0 for s in c.entity_sitelinks)]
    assert not missing, f"sitelinks unfetched for {missing}"


# --- known limitations, asserted so they cannot be forgotten ---------------
def test_class_is_currently_confounded_with_answer_type(pilot):
    """A KNOWN limitation of this 12-item pilot, asserted so it stays visible.

    If this ever fails, the confound has been fixed and the note in
    PILOT_BENCHMARK_PREVIEW.md should be updated.
    """
    constraints, _ = pilot
    mapping = answer_type_by_class(constraints)
    assert all(len(v) == 1 for v in mapping.values()), (
        "class and answer type are no longer perfectly correlated — update the "
        "limitation note in docs/PILOT_BENCHMARK_PREVIEW.md"
    )


def test_builder_is_deterministic(candidates):
    """The same candidates must produce the same probes, byte for byte."""
    a = build(candidates, fetch_evidence=False)
    b = build(candidates, fetch_evidence=False)
    assert [p.probe_text for p in a.probes] == [p.probe_text for p in b.probes]
    assert [p.probe_id for p in a.probes] == [p.probe_id for p in b.probes]


# --- inspection tooling is read-only ---------------------------------------
def test_inspection_commands_do_not_modify_the_benchmark(tmp_path):
    """Integrity: inspection must never write to the benchmark records."""
    import hashlib
    import subprocess
    import sys as _sys

    from semintegrity.utils.paths import project_root

    files = [*sorted(PILOT.glob("*.jsonl")), PILOT / "candidates.yaml"]
    before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}

    for argv in (
        ["scripts/benchmark/inspect_pilot.py", "--compact"],
        ["scripts/benchmark/inspect_pilot.py", "--constraint", "K-C1-GEO-01"],
        ["scripts/benchmark/show_pilot.py"],
    ):
        proc = subprocess.run(
            [_sys.executable, *argv], cwd=project_root(), capture_output=True, text=True
        )
        assert proc.returncode == 0, f"{argv} failed: {proc.stderr[-400:]}"

    after = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    assert before == after, "an inspection command modified the benchmark records"


def test_examples_doc_matches_the_records():
    """docs/PILOT_EXAMPLES.md is generated; it must not drift from the data."""
    from semintegrity.utils.paths import p as _p

    doc = _p("docs/PILOT_EXAMPLES.md")
    assert doc.is_file(), "run scripts/benchmark/make_examples_doc.py"
    text = doc.read_text(encoding="utf-8")

    constraints, probes = load_split(PILOT)
    assert f"**{len(constraints)} constraints · {len(probes)} probes" in text

    by_cid = {c.constraint_id: c for c in constraints}
    for cid in ("K-C1-GEO-01", "K-C3-SCI-01", "K-C4-POL-01"):
        assert f"`{cid}`" in text
        # every one of that constraint's probe texts must appear verbatim
        for pr in (x for x in probes if x.constraint_id == cid):
            assert pr.probe_text.replace("|", "\\|") in text, f"{pr.probe_id} missing from the doc"
        assert by_cid[cid].gold_answer in text


def test_examples_doc_states_the_draft_status():
    """The doc must not read as though anything is verified."""
    from semintegrity.utils.paths import p as _p

    text = _p("docs/PILOT_EXAMPLES.md").read_text(encoding="utf-8")
    assert "all DRAFT" in text
    assert "Not human-reviewed" in text
    assert "Not frozen" in text
