"""The 24 per-schema D0 registrations (decision A5, 2026-10-06).

The point of these tests is that the *limits* are pinned as firmly as the
behaviour. A predicate whose name promises structure it does not check is the
failure mode `configs/detectors/d0_symbolic.yaml` names: "a faulty predicate is
confidently wrong across every instance of its schema". So every C2 and C3
registration must say in words what it does not formalise, and these tests fail
if that text goes missing.
"""

from __future__ import annotations

import datetime as dt

import pytest

from semintegrity.detectors.d0.base import KnowledgeBase
from semintegrity.detectors.d0.registry import PredicateRegistry
from semintegrity.schemas.enums import Verdict

ANCHOR_AXES = (4, 6)  # the two `date` axes approved under A4
ALL_SCHEMAS = [f"s_c{c}_{a:02d}" for a in range(1, 7) for c in (1, 2, 3, 4)]


class _NullKB(KnowledgeBase):
    def value_of(self, qid: str, prop: str):  # pragma: no cover - unused
        return None

    def creation_date(self, qid: str):  # pragma: no cover - unused
        return None


@pytest.fixture(scope="module")
def registry() -> PredicateRegistry:
    r = PredicateRegistry()
    r.autodiscover()
    return r


def test_all_24_schemas_are_registered(registry):
    names = set(registry.names())
    assert len(ALL_SCHEMAS) == 24
    missing = [n for n in ALL_SCHEMAS if n not in names]
    assert missing == []


def test_the_four_pilot_predicates_are_untouched(registry):
    """The 12 pilot/dev constraints still resolve."""
    for legacy in (
        "c1_mutual_exclusion",
        "c2_conjunction",
        "c3_functional_uniqueness",
        "c4_interval_precedence",
    ):
        assert registry.has(legacy)


@pytest.mark.parametrize("name", ALL_SCHEMAS)
def test_each_registration_declares_its_identity(registry, name):
    p = registry.get(name)
    assert p.schema_id == name.upper().replace("_", "-")
    assert p.version
    assert p.formal_statement


@pytest.mark.parametrize("name", ALL_SCHEMAS)
def test_every_registration_states_the_exclusion_basis(registry, name):
    assert "mutual exclusion" in registry.get(name).formal_statement


@pytest.mark.parametrize("name", ALL_SCHEMAS)
def test_anchor_is_claimed_only_where_the_answer_is_a_date(registry, name):
    """ADR-0017 as amended: ANCHOR needs a DATE answer, so it follows (axis, class).

    C2 and C3 are boolean on every axis, so a temporal anchor could never apply
    to them — their canonical answers are YES/NO and never parse as dates.
    Claiming it would be a formal statement the predicate cannot honour, which is
    the failure mode `configs/detectors/d0_symbolic.yaml` names.
    """
    cls, axis = name.split("_")[1].upper(), int(name.rsplit("_", 1)[1])
    statement = registry.get(name).formal_statement
    claims_anchor = "temporal anchor precedence" in statement
    expected = axis in ANCHOR_AXES and cls in ("C1", "C4")
    assert claims_anchor is expected, name
    if not claims_anchor:
        assert "NOT_APPLICABLE" in statement


def test_exactly_four_schemas_claim_the_anchor(registry):
    claiming = [
        p.predicate_name for p in registry
        if p.predicate_name.startswith("s_c")
        and "temporal anchor precedence" in p.formal_statement
    ]
    assert sorted(claiming) == ["s_c1_04", "s_c1_06", "s_c4_04", "s_c4_06"]


@pytest.mark.parametrize("name", [n for n in ALL_SCHEMAS if n.startswith(("s_c2", "s_c3"))])
def test_c2_and_c3_declare_what_they_do_not_formalise(registry, name):
    """§4.8.2: the audit record must carry the limit, not just the verdict."""
    statement = registry.get(name).formal_statement
    assert "Does NOT" in statement
    if name.startswith("s_c2"):
        assert "conjuncts" in statement
    else:
        assert "quantifier" in statement


def test_source_hashes_are_distinct(registry):
    """The freeze manifest (§4.8.2) is only meaningful if each predicate hashes
    its own source. A dynamically generated class would fall back to ``repr``."""
    hashes = {p.predicate_name: p.describe()["source_sha256"] for p in registry}
    assert len(set(hashes.values())) == len(hashes)


def test_no_new_detection_logic_was_invented(registry):
    """Every per-schema predicate must delegate, not decide.

    A5 approved honest coverage, not new semantics. If a registration grows its
    own ``check_pair``, that is new detection logic and this fails.
    """
    from semintegrity.detectors.d0.predicates.schema_registrations import (
        _SchemaAnchor,
        _SchemaExclusion,
    )

    for name in ALL_SCHEMAS:
        cls = type(registry.get(name))
        assert "check_pair" not in cls.__dict__, f"{name} defines its own check_pair"
        assert issubclass(cls, _SchemaAnchor | _SchemaExclusion)


# --- behaviour, through the real pilot records ----------------------------
def _responses(constraint, a_answer, b_answer):
    from semintegrity.schemas.response import CanonicalResponse

    def one(i, answer):
        return CanonicalResponse(
            response_id=f"R-00000000000{i}",
            constraint_id=constraint.constraint_id,
            probe_id=f"{constraint.constraint_id}-P0{i}",
            label="ANSWER",
            canonical_answer=answer,
            matched_alias=answer,
            candidates_found=[answer],
            canonicaliser_version="1.1",
            canonicaliser_sha256="0" * 64,
            canonicalised_at=dt.datetime(2026, 10, 6, tzinfo=dt.timezone.utc),
            notes="synthetic, for a predicate unit test",
        )

    return one(1, a_answer), one(2, b_answer)


@pytest.fixture(scope="module")
def date_constraint():
    import yaml

    from semintegrity.benchmark.pilot_builder import build
    from semintegrity.utils.paths import data_path

    candidates = yaml.safe_load(
        (data_path("benchmark") / "pilot" / "candidates.yaml").read_text(encoding="utf-8")
    )
    for c in build(candidates).constraints:
        if c.answer_type.value == "date" and c.temporal_validity:
            return c
    pytest.skip("no dated pilot constraint available")


def test_exclusion_agrees_and_disagrees(registry, date_constraint):
    p = registry.get("s_c1_01")
    gold = date_constraint.gold_answer
    other = next(a for a in date_constraint.answer_space if a != gold)
    a, b = _responses(date_constraint, gold, gold)
    assert p.check_pair(date_constraint, a, b, _NullKB()).verdict is Verdict.SATISFIED
    a, b = _responses(date_constraint, gold, other)
    result = p.check_pair(date_constraint, a, b, _NullKB())
    assert result.verdict is Verdict.VIOLATION
    assert result.predicate == "s_c1_01"
    assert result.schema_id == "S-C1-01"


def test_anchor_fires_on_agreeing_responses_that_precede_the_anchor(
    registry, date_constraint
):
    """The behaviour EXCL cannot reach: both answers agree, both are too early."""
    anchor = date_constraint.temporal_validity.start
    assert anchor is not None
    early = str(anchor.year - 10)
    constraint = date_constraint.model_copy(
        update={"answer_space": [*date_constraint.answer_space, early]}
    )
    a, b = _responses(constraint, early, early)

    excl = registry.get("s_c1_01").check_pair(constraint, a, b, _NullKB())
    assert excl.verdict is Verdict.SATISFIED  # agreement is all EXCL can see

    anchored = registry.get("s_c1_06").check_pair(constraint, a, b, _NullKB())
    assert anchored.verdict is Verdict.VIOLATION
    assert anchored.predicate == "s_c1_06"
    assert "precede" in anchored.reason


def test_anchor_falls_back_to_exclusion_when_it_cannot_apply(registry):
    """A boolean-answer constraint has no parseable date, so ANCHOR must not
    swallow the pair — the exclusion verdict has to stand."""
    import yaml

    from semintegrity.benchmark.pilot_builder import build
    from semintegrity.utils.paths import data_path

    candidates = yaml.safe_load(
        (data_path("benchmark") / "pilot" / "candidates.yaml").read_text(encoding="utf-8")
    )
    boolean = next(
        c for c in build(candidates).constraints if c.answer_type.value == "boolean"
    )
    a, b = _responses(boolean, "YES", "NO")
    result = registry.get("s_c1_06").check_pair(boolean, a, b, _NullKB())
    assert result.verdict is Verdict.VIOLATION
    assert result.predicate == "s_c1_06"


def test_freeze_manifest_round_trips_every_registration(registry, tmp_path):
    path = registry.write_freeze_manifest(tmp_path / "d0_freeze.json", note="unit test")
    assert registry.verify_freeze(path) == []
    manifest = __import__("json").loads(path.read_text())
    assert manifest["n_predicates"] == len(registry)
    for name in ALL_SCHEMAS:
        assert name in manifest["predicates"]
    assert dt.datetime.fromisoformat(manifest["frozen_at"])
