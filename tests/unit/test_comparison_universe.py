"""Comparison universes for extremal (axis-5) constraints.

A superlative is not a proposition until the set it ranges over is fixed: "the
highest summit" is true of Everest, Kilimanjaro or Ben Nevis depending on
whether the universe is the world, Africa or Scotland. Recording the answer
space does not fix it. So for extremal schemas the universe is part of the
frozen ground truth, and a record cannot claim EVIDENCE_VERIFIED or above
without one.

These tests pin that the requirement fires, that it fires for the right schemas
only, and that prose is not accepted in its place.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from semintegrity.benchmark.design_validator import BenchmarkDesignValidator
from semintegrity.schemas.constraint import (
    EXTREMAL_SCHEMA_INDICES,
    ComparisonUniverse,
    Constraint,
    Evidence,
    RankedSource,
    UniverseMember,
)
from semintegrity.schemas.enums import (
    AnswerType,
    ConstraintClass,
    Domain,
    Split,
    VerificationStatus,
)
from tests.fixtures.synthetic_benchmark import make_constraint

EXTREMAL_INDEX = 5
PROMOTED = (
    VerificationStatus.EVIDENCE_VERIFIED,
    VerificationStatus.HUMAN_VALIDATED,
    VerificationStatus.FROZEN,
)


def _extremal(**overrides) -> Constraint:
    """A structurally valid, factually fictional axis-5 constraint.

    Forced to an ENTITY answer so that the gold answer IS the asserted extremal
    bearer. Under the approved allocation axis 5 is boolean, which collides with
    ADR-0018's self-consistency check — see
    ``test_axis5_boolean_allocation_cannot_carry_an_enumerated_universe``. These
    model-level tests exercise ``ComparisonUniverse`` itself, so they use the
    shape the check was written for rather than the shape the allocation
    produces; mixing the two would let them pass by building a member labelled
    "YES".
    """
    base = make_constraint(
        ConstraintClass.C1, Domain.GEOGRAPHY, 15, family_index=15, schema_index=EXTREMAL_INDEX
    )
    forced = {
        "answer_type": AnswerType.ENTITY,
        "answer_space": ["Highest-Peak", "Second-Peak", "Third-Peak"],
        "gold_answer": "Highest-Peak",
    }
    return base.model_copy(update={**forced, **overrides})


#: The synthetic constraint's own first entity QID — the universe must assert a
#: bearer that is one of the constraint's entities.
BEARER_QID = "Q9000015"


def _enumerated(bearer_label: str = "Highest-Peak", **overrides) -> ComparisonUniverse:
    kwargs = dict(
        universe="summits wholly within the synthetic test region",
        membership_rule="P31/P279* Q8502 (mountain) AND P30 Q-SYNTHETIC",
        measure="elevation (P2044)",
        direction="max",
        argmax_qid=BEARER_QID,
        argmax_label=bearer_label,
        frozen_at=dt.date(2026, 10, 7),
        members=[
            UniverseMember(label=bearer_label, qid=BEARER_QID, measure_value="5895 metre"),
            UniverseMember(label="Runner-up", qid="Q9000016", measure_value="5199 metre"),
            UniverseMember(label="Third", qid="Q9000017", measure_value="4550 metre"),
        ],
    )
    kwargs.update(overrides)
    return ComparisonUniverse(**kwargs)


def _ranked(rank: int = 1, **overrides) -> ComparisonUniverse:
    kwargs = dict(
        universe="naturally occurring chemical elements",
        membership_rule="Wikidata P31 Q11344 with a natural-occurrence qualifier",
        measure="atomic number (P1086)",
        direction="max",
        argmax_qid=BEARER_QID,
        argmax_label="Heaviest-Element",
        frozen_at=dt.date(2026, 10, 7),
        ranked_source=RankedSource(
            name="Wikidata SPARQL",
            url="https://query.wikidata.org/",
            retrieved=dt.date(2026, 10, 7),
            snapshot="wikidata_cache/sparql/d4/d4e1438f.json",
            query="SELECT ?e ?z WHERE { ?e wdt:P1086 ?z } ORDER BY DESC(?z)",
            rank_of_argmax=rank,
        ),
    )
    kwargs.update(overrides)
    return ComparisonUniverse(**kwargs)


def _evidence() -> Evidence:
    return Evidence(
        source="wikidata",
        query="Q9000015 P2044",
        url="https://www.wikidata.org/wiki/Q9000015",
        retrieved_at=dt.date(2026, 10, 7),
        observed_value="5895 metre",
        supports_gold=True,
        comparison="observed elevation matches the recorded gold measure",
    )


# --- the constant is pinned to the matrix ---------------------------------
def test_extremal_indices_match_the_approved_matrix():
    """Axis 5 is 'Extremal uniqueness' in the Revision 3 matrix."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from propose_coverage_matrix import AXES

    extremal = [a.index for a in AXES if "Extremal" in a.name]
    assert extremal == sorted(EXTREMAL_SCHEMA_INDICES) == [EXTREMAL_INDEX]


# --- 1. a valid explicit comparison set ------------------------------------
def test_valid_enumerated_set_permits_promotion():
    c = _extremal()
    promoted = Constraint.model_validate(
        {
            **c.to_record(),
            "comparison_universe": _enumerated().model_dump(mode="json"),
            "evidence": [_evidence().model_dump(mode="json")],
            "verification_status": VerificationStatus.EVIDENCE_VERIFIED.value,
        }
    )
    assert promoted.comparison_universe is not None
    assert len(promoted.comparison_universe.members) == 3
    assert promoted.comparison_universe.ranked_source is None


# --- 2. a valid ranked source ---------------------------------------------
def test_valid_ranked_source_permits_promotion():
    c = _extremal()
    promoted = Constraint.model_validate(
        {
            **c.to_record(),
            "comparison_universe": _ranked().model_dump(mode="json"),
            "evidence": [_evidence().model_dump(mode="json")],
            "verification_status": VerificationStatus.EVIDENCE_VERIFIED.value,
        }
    )
    assert promoted.comparison_universe.ranked_source.rank_of_argmax == 1
    assert promoted.comparison_universe.members == []


def test_ranked_source_records_a_frozen_snapshot_not_a_live_endpoint():
    """ADR-0011: evidence resolves from the frozen cache, never the network."""
    assert _ranked().ranked_source.snapshot
    with pytest.raises(ValidationError):
        RankedSource(
            name="Wikidata SPARQL",
            url="https://query.wikidata.org/",
            retrieved=dt.date(2026, 10, 7),
            snapshot="",  # a live query with nothing frozen behind it
            rank_of_argmax=1,
        )


# --- 3. a missing comparison universe fails -------------------------------
@pytest.mark.parametrize("status", [s.value for s in PROMOTED])
def test_promotion_without_a_universe_is_refused(status):
    c = _extremal()
    record = {**c.to_record(), "verification_status": status,
              "evidence": [_evidence().model_dump(mode="json")]}
    if status != VerificationStatus.EVIDENCE_VERIFIED.value:
        record["human_validated_by"] = "A. Researcher"
        record["human_validated_at"] = "2026-10-07"
    with pytest.raises(ValidationError, match="comparison_universe"):
        Constraint.model_validate(record)


def test_draft_without_a_universe_is_permitted():
    """Authoring a draft before the universe is fixed is normal."""
    c = _extremal()
    assert c.verification_status is VerificationStatus.DRAFT
    assert c.comparison_universe is None


def test_draft_without_a_universe_is_surfaced_as_a_warning():
    report = BenchmarkDesignValidator().validate([_extremal()], split=Split.TEST)
    rule = next(r for r in report.results if r.rule == "comparison_universe")
    assert not rule.passed
    assert rule.severity == "warning"
    assert any("S-C1-05" in o for o in rule.offenders)


def test_universe_present_passes_the_validator_rule():
    c = _extremal()
    with_universe = c.model_copy(update={"comparison_universe": _enumerated()})
    report = BenchmarkDesignValidator().validate([with_universe], split=Split.TEST)
    rule = next(r for r in report.results if r.rule == "comparison_universe")
    assert rule.passed, rule.message
    assert "enumerated" in rule.message


# --- 4. non-axis-5 constraints are unaffected -----------------------------
@pytest.mark.parametrize("schema_index", [1, 2, 3, 4, 6])
def test_other_schemas_need_no_universe(schema_index):
    base = make_constraint(
        ConstraintClass.C1, Domain.BIOLOGY, 11, family_index=11, schema_index=schema_index
    )
    promoted = Constraint.model_validate(
        {
            **base.to_record(),
            "evidence": [_evidence().model_dump(mode="json")],
            "verification_status": VerificationStatus.EVIDENCE_VERIFIED.value,
        }
    )
    assert promoted.comparison_universe is None


def test_the_rule_does_not_apply_where_no_extremal_schema_exists():
    base = make_constraint(
        ConstraintClass.C1, Domain.BIOLOGY, 11, family_index=11, schema_index=3
    )
    report = BenchmarkDesignValidator().validate([base], split=Split.TEST)
    rule = next(r for r in report.results if r.rule == "comparison_universe")
    assert rule.passed
    assert rule.severity == "info"
    assert "does not apply" in rule.message


@pytest.mark.parametrize("cls", list(ConstraintClass))
def test_every_class_of_the_extremal_axis_is_covered(cls):
    """All four of S-C1-05 .. S-C4-05 are extremal, not just C1."""
    base = make_constraint(
        cls, Domain.HISTORY, 15, family_index=15, schema_index=EXTREMAL_INDEX
    ).model_copy(update={"answer_type": AnswerType.ENTITY,
                         "answer_space": ["A-Peak", "B-Peak"],
                         "gold_answer": "A-Peak"})
    record = {**base.to_record(), "evidence": [_evidence().model_dump(mode="json")],
              "verification_status": VerificationStatus.EVIDENCE_VERIFIED.value}
    with pytest.raises(ValidationError, match="comparison_universe"):
        Constraint.model_validate(record)


# --- 5. malformed universes fail ------------------------------------------
def test_neither_basis_is_refused():
    with pytest.raises(ValidationError, match="needs a basis"):
        ComparisonUniverse(
            universe="summits", membership_rule="rule", measure="elevation",
            direction="max", argmax_qid=BEARER_QID, argmax_label="A",
            frozen_at=dt.date(2026, 10, 7),
        )


def test_both_bases_at_once_is_refused():
    with pytest.raises(ValidationError, match="not both"):
        ComparisonUniverse(
            universe="summits", membership_rule="rule", measure="elevation",
            direction="max", argmax_qid="Q1", argmax_label="A",
            frozen_at=dt.date(2026, 10, 7),
            members=[
                UniverseMember(label="A", qid="Q1", measure_value="2 m"),
                UniverseMember(label="B", qid="Q2", measure_value="1 m"),
            ],
            ranked_source=_ranked().ranked_source,
        )


def test_a_single_member_set_is_refused():
    with pytest.raises(ValidationError, match="at least 2 members"):
        ComparisonUniverse(
            universe="summits", membership_rule="rule", measure="elevation",
            direction="max", argmax_qid="Q1", argmax_label="A",
            frozen_at=dt.date(2026, 10, 7),
            members=[UniverseMember(label="A", qid="Q1", measure_value="2 m")],
        )


def test_duplicate_qids_are_refused():
    with pytest.raises(ValidationError, match="duplicate QIDs"):
        ComparisonUniverse(
            universe="summits", membership_rule="rule", measure="elevation",
            direction="max", argmax_qid="Q1", argmax_label="A",
            frozen_at=dt.date(2026, 10, 7),
            members=[
                UniverseMember(label="A", qid="Q1", measure_value="2 m"),
                UniverseMember(label="B", qid="Q1", measure_value="1 m"),
            ],
        )


@pytest.mark.parametrize("field", ["universe", "membership_rule", "measure"])
def test_empty_descriptive_fields_are_refused(field):
    kwargs = {
        "universe": "summits", "membership_rule": "rule", "measure": "elevation",
        "direction": "max", "argmax_qid": "Q1", "argmax_label": "A",
        "frozen_at": dt.date(2026, 10, 7),
        "members": [
            UniverseMember(label="A", qid="Q1", measure_value="2 m"),
            UniverseMember(label="B", qid="Q2", measure_value="1 m"),
        ],
    }
    kwargs[field] = ""
    with pytest.raises(ValidationError):
        ComparisonUniverse(**kwargs)


def test_malformed_member_qid_is_refused():
    with pytest.raises(ValidationError):
        UniverseMember(label="A", qid="NOT-A-QID", measure_value="2 m")


def test_rank_of_argmax_must_be_positive():
    with pytest.raises(ValidationError):
        RankedSource(
            name="n", url="u", retrieved=dt.date(2026, 10, 7),
            snapshot="s", rank_of_argmax=0,
        )


def test_unknown_field_on_a_universe_is_refused():
    """extra='forbid': a typo must not become a silently ignored universe."""
    with pytest.raises(ValidationError):
        ComparisonUniverse.model_validate(
            {
                "universe": "summits", "membership_rule": "rule", "measure": "elevation",
                "direction": "max", "argmax_qid": "Q1", "argmax_label": "A",
                "frozen_at": "2026-10-07",
                "members": [
                    {"label": "A", "qid": "Q1", "measure_value": "2 m"},
                    {"label": "B", "qid": "Q2", "measure_value": "1 m"},
                ],
                "comparison_set": "typo for members",
            }
        )


def test_universe_must_belong_to_this_constraint():
    """The asserted bearer must be one of the constraint's own entities.

    Replaces the superseded gold-answer check: that compared the wrong object,
    because axis 5 is boolean and the gold answer is YES/NO.
    """
    c = _extremal()
    foreign = _enumerated(
        argmax_qid="Q7777777",
        members=[
            UniverseMember(label="Elsewhere", qid="Q7777777", measure_value="9000 m"),
            UniverseMember(label="Other", qid="Q7777778", measure_value="1 m"),
        ],
        argmax_label="Elsewhere",
    )
    with pytest.raises(ValidationError, match="not among the constraint's entities"):
        Constraint.model_validate(
            {**c.to_record(), "comparison_universe": foreign.model_dump(mode="json")}
        )


# --- 6. prose is NOT a substitute -----------------------------------------
def test_ambiguity_notes_is_not_accepted_as_a_substitute():
    """The whole reason Option 1 was chosen over Option 2."""
    c = _extremal()
    record = {
        **c.to_record(),
        "ambiguity_notes": (
            "COMPARISON SET: summits wholly within Africa, per Wikidata P30 Q15, "
            "frozen 2026-10-07. Members: Kilimanjaro, Mount Kenya, Ras Dashen."
        ),
        "evidence": [_evidence().model_dump(mode="json")],
        "verification_status": VerificationStatus.EVIDENCE_VERIFIED.value,
    }
    with pytest.raises(ValidationError, match="comparison_universe"):
        Constraint.model_validate(record)


# --- round-trip -----------------------------------------------------------
def test_universe_round_trips_through_the_record():
    c = _extremal()
    with_universe = Constraint.model_validate(
        {**c.to_record(), "comparison_universe": _enumerated().model_dump(mode="json")}
    )
    again = Constraint.model_validate(with_universe.to_record())
    assert again.comparison_universe == with_universe.comparison_universe


def test_existing_records_without_the_field_still_load():
    """The 12 pilot constraints predate the field and must be unaffected."""
    from semintegrity.benchmark.loader import load_split
    from semintegrity.utils.paths import data_path

    constraints, _ = load_split(data_path("benchmark") / "pilot")
    assert len(constraints) == 12
    assert all(c.comparison_universe is None for c in constraints)


# --- ADR-0018 amendment 2026-10-07: the asserted extremal bearer ---------
# Axis 5 is BOOLEAN under ADR-0017 Option B, so gold_answer is YES/NO and is not
# the bearer of anything. The universe records the asserted extremum explicitly.
def _boolean_extremal() -> Constraint:
    """An axis-5 constraint exactly as the approved allocation produces it."""
    c = make_constraint(
        ConstraintClass.C1, Domain.GEOGRAPHY, 15, family_index=15, schema_index=EXTREMAL_INDEX
    )
    assert c.answer_type.value == "boolean"
    assert c.gold_answer in ("YES", "NO")
    assert BEARER_QID in c.entity_qids
    return c


def test_case1_enumerated_universe_with_gold_yes_passes():
    """Case 1: gold YES · argmax in members · correct argmax measure -> PASS."""
    c = _boolean_extremal()
    attached = Constraint.model_validate(
        {**c.to_record(), "comparison_universe": _enumerated().model_dump(mode="json")}
    )
    assert attached.gold_answer == "YES"
    assert attached.comparison_universe.argmax_qid == BEARER_QID
    assert attached.comparison_universe.argmax_label == "Highest-Peak"
    assert attached.comparison_universe.direction == "max"


def test_case2_enumerated_universe_with_gold_no_passes():
    """Case 2: gold NO, bearer still explicit -> PASS.

    A negative superlative claim ("X is NOT the highest") is still about a
    universe and an asserted bearer; the truth value is orthogonal, which is what
    answer-type independence means.
    """
    c = _boolean_extremal().model_copy(update={"gold_answer": "NO"})
    attached = Constraint.model_validate(
        {**c.to_record(), "comparison_universe": _enumerated().model_dump(mode="json")}
    )
    assert attached.gold_answer == "NO"
    assert attached.comparison_universe.argmax_qid == BEARER_QID


def test_case3_missing_argmax_qid_fails():
    """Case 3: argmax_qid absent -> FAIL."""
    payload = _enumerated().model_dump(mode="json")
    del payload["argmax_qid"]
    with pytest.raises(ValidationError, match="argmax_qid"):
        ComparisonUniverse.model_validate(payload)


def test_case3b_missing_argmax_label_or_direction_fails():
    for field in ("argmax_label", "direction"):
        payload = _enumerated().model_dump(mode="json")
        del payload[field]
        with pytest.raises(ValidationError, match=field):
            ComparisonUniverse.model_validate(payload)


def test_case4_argmax_not_in_members_fails():
    """Case 4: argmax_qid not among members -> FAIL."""
    with pytest.raises(ValidationError, match="not among the enumerated members"):
        _enumerated(argmax_qid="Q9999999")


def test_case5_argmax_label_inconsistent_with_its_member_fails():
    """Case 5: argmax_label does not match the selected member -> FAIL."""
    with pytest.raises(ValidationError, match="does not match member"):
        _enumerated(argmax_label="Not-That-Peak")


def test_case6_bearer_that_is_not_the_extremum_fails():
    """Case 6: the asserted bearer is not extremal by the recorded measures."""
    with pytest.raises(ValidationError, match="is not the extremum of the recorded measures"):
        _enumerated(
            argmax_qid="Q9000016",
            argmax_label="Runner-up",   # records 5199 m against the bearer's 5895 m
        )


def test_case6_direction_min_is_honoured():
    """The same check, inverted: with direction=min the smallest must be asserted."""
    ok = _enumerated(direction="min", argmax_qid="Q9000017", argmax_label="Third")
    assert ok.direction == "min"
    with pytest.raises(ValidationError, match="is not the extremum of the recorded measures"):
        _enumerated(direction="min")  # asserts the 5895 m member as the minimum


def test_case6_is_skipped_when_measures_are_not_numeric():
    """Not machine-checkable -> not checked, rather than passed silently."""
    universe = _enumerated(
        members=[
            UniverseMember(label="Highest-Peak", qid=BEARER_QID, measure_value="very tall"),
            UniverseMember(label="Runner-up", qid="Q9000016", measure_value="tall"),
        ]
    )
    assert universe.argmax_qid == BEARER_QID


def test_case7_valid_ranked_source_passes():
    """Case 7: a ranked source with the bearer at rank 1 -> PASS."""
    c = _boolean_extremal()
    attached = Constraint.model_validate(
        {**c.to_record(), "comparison_universe": _ranked().model_dump(mode="json")}
    )
    assert attached.comparison_universe.ranked_source.rank_of_argmax == 1
    assert attached.comparison_universe.members == []


def test_case8_ranked_source_with_inconsistent_rank_fails():
    """Case 8: the asserted bearer does not head the ordering -> FAIL."""
    with pytest.raises(ValidationError, match="an extremal claim requires rank 1"):
        _ranked(rank=4)


@pytest.mark.parametrize("schema_index", [1, 2, 3, 4, 6])
def test_case9_non_axis5_constraints_are_unaffected(schema_index):
    """Case 9: nothing outside axis 5 gains a requirement."""
    base = make_constraint(
        ConstraintClass.C1, Domain.BIOLOGY, 11, family_index=11, schema_index=schema_index
    )
    promoted = Constraint.model_validate(
        {**base.to_record(), "evidence": [_evidence().model_dump(mode="json")],
         "verification_status": VerificationStatus.EVIDENCE_VERIFIED.value}
    )
    assert promoted.comparison_universe is None


def test_case10_pilot_is_unaffected():
    """Case 10: the 12 pilot constraints still load, with no universe."""
    from semintegrity.benchmark.loader import load_split
    from semintegrity.utils.paths import data_path

    constraints, probes = load_split(data_path("benchmark") / "pilot")
    assert len(constraints) == 12
    assert len(probes) == 96
    assert all(c.comparison_universe is None for c in constraints)


@pytest.mark.parametrize("boolean_word", ["YES", "NO", "yes", "no", " Yes "])
def test_case11_a_universe_cannot_contain_a_boolean_truth_value(boolean_word):
    """Case 11: no test may pass by enumerating "YES" as a member.

    This is the exact failure mode the earlier gold-answer check permitted: a
    member labelled "YES" satisfied it while recording nonsense.
    """
    with pytest.raises(ValidationError, match="boolean truth value"):
        _enumerated(
            argmax_label=boolean_word,
            members=[
                UniverseMember(label=boolean_word, qid=BEARER_QID, measure_value="5895 m"),
                UniverseMember(label="Runner-up", qid="Q9000016", measure_value="5199 m"),
            ],
        )


def test_case11b_a_boolean_member_is_refused_even_when_not_the_bearer():
    with pytest.raises(ValidationError, match="boolean truth value"):
        _enumerated(
            members=[
                UniverseMember(label="Highest-Peak", qid=BEARER_QID, measure_value="5895 m"),
                UniverseMember(label="NO", qid="Q9000016", measure_value="5199 m"),
            ]
        )


def test_promotion_of_a_boolean_extremal_now_works_end_to_end():
    """The blocker this amendment resolves, asserted positively."""
    c = _boolean_extremal()
    promoted = Constraint.model_validate(
        {
            **c.to_record(),
            "comparison_universe": _enumerated().model_dump(mode="json"),
            "evidence": [_evidence().model_dump(mode="json")],
            "verification_status": VerificationStatus.EVIDENCE_VERIFIED.value,
        }
    )
    assert promoted.verification_status is VerificationStatus.EVIDENCE_VERIFIED
    assert promoted.answer_type.value == "boolean"
    assert promoted.comparison_universe.argmax_label == "Highest-Peak"


def test_both_representations_remain_valid_for_a_boolean_extremal():
    """Enumerated and ranked-source universes are both still permitted."""
    c = _boolean_extremal()
    for universe in (_enumerated(), _ranked()):
        attached = Constraint.model_validate(
            {**c.to_record(), "comparison_universe": universe.model_dump(mode="json")}
        )
        assert attached.comparison_universe is not None


# ===========================================================================
# The authoring path (added 2026-10-07). ADR-0018 defined the universe long
# before the builder could carry one from a candidates document, so axis-5
# cells were unauthorable through the production path. These tests pin the
# passthrough: read as given, validated by the schema, never synthesised.
# ===========================================================================
def _axis5_spec(**overrides) -> dict:
    spec = {
        "constraint_id": "K-C1-GEO-15",
        "schema_id": "S-C1-05",
        "class": "C1",
        "formal_predicate": "s_c1_05",
        "constraint_text": "The highest summit wholly within Africa is Kilimanjaro.",
        "logical_form": "argmax(elevation, summits_in_africa) = Kilimanjaro",
        "gold_proposition": "Kilimanjaro is the highest summit wholly within Africa.",
        "answer_type": "boolean",
        "answer_space": ["YES", "NO"],
        "gold_answer": "YES",
        "entities": [{"label": "Kilimanjaro", "qid": "Q7296"},
                     {"label": "Mount Kenya", "qid": "Q3757"}],
        "surface": {
            "claim_formal": "Kilimanjaro is the highest summit wholly within Africa",
            "claim_colloquial": "Kilimanjaro is Africa's highest mountain",
            "claim_reverse_formal": "the highest summit wholly within Africa is Kilimanjaro",
            "claim_reverse_colloquial": "Africa's highest mountain is Kilimanjaro",
        },
        "comparison_universe": {
            "universe": "summits wholly within Africa",
            "membership_rule": "Wikidata P31/P279* Q8502 (mountain) AND P30 Q15 (Africa)",
            "measure": "elevation above sea level (P2044)",
            "direction": "max",
            "argmax_qid": "Q7296",
            "argmax_label": "Kilimanjaro",
            "frozen_at": "2026-10-07",
            "members": [
                {"label": "Kilimanjaro", "qid": "Q7296", "measure_value": "5895 metre"},
                {"label": "Mount Kenya", "qid": "Q3757", "measure_value": "5199 metre"},
            ],
        },
    }
    spec.update(overrides)
    return spec


def _build_one(spec: dict):
    from semintegrity.benchmark.pilot_builder import build
    from semintegrity.schemas.enums import Split, Tier

    return build(
        {"families": [{"family_id": "F-GEO-15", "domain": "geography",
                       "theme": "the highest summit of a continent",
                       "constraints": [spec]}]},
        split=Split.TEST, tier=Tier.PRIMARY,
    )


def test_the_builder_carries_a_comparison_universe_through_intact():
    result = _build_one(_axis5_spec())
    assert len(result.constraints) == 1
    cu = result.constraints[0].comparison_universe
    assert cu is not None, "ADR-0018's universe must survive the authoring path"
    assert cu.direction == "max"
    assert cu.argmax_qid == "Q7296"
    assert cu.argmax_label == "Kilimanjaro"
    assert cu.universe == "summits wholly within Africa"
    assert cu.measure == "elevation above sea level (P2044)"
    assert [m.qid for m in cu.members] == ["Q7296", "Q3757"]
    assert [m.measure_value for m in cu.members] == ["5895 metre", "5199 metre"]
    assert cu.frozen_at.isoformat() == "2026-10-07"
    assert len(result.probes) == 8


def test_the_builder_synthesises_nothing_when_the_key_is_absent():
    """An absent universe must stay absent so the gates can still see it."""
    spec = _axis5_spec()
    del spec["comparison_universe"]
    result = _build_one(spec)
    assert result.constraints[0].comparison_universe is None


def test_an_axis5_cell_cannot_be_promoted_without_a_universe():
    """The gate ADR-0018 exists for still fires through the authoring path."""
    from semintegrity.schemas.enums import VerificationStatus

    spec = _axis5_spec()
    del spec["comparison_universe"]
    c = _build_one(spec).constraints[0]
    # Promotion also needs evidence, so supply one: the point under test is the
    # universe rule, not the evidence rule, and a test that passes for the wrong
    # reason is worse than no test.
    evidence = [{
        "source": "wikidata", "query": "Q7296 P2044",
        "url": "https://www.wikidata.org/wiki/Q7296",
        "retrieved_at": "2026-10-07", "observed_value": "5895",
        "supports_gold": True, "comparison": "exact match",
    }]
    with pytest.raises(ValidationError, match="requires a `comparison_universe`"):
        Constraint.model_validate({
            **c.to_record(),
            "evidence": evidence,
            "verification_status": VerificationStatus.EVIDENCE_VERIFIED.value,
        })


def test_a_universe_whose_argmax_is_not_the_extremum_is_refused_at_authoring():
    """A fabricated extremum is caught by the recorded measures themselves."""
    spec = _axis5_spec()
    spec["comparison_universe"]["members"][1]["measure_value"] = "8849 metre"
    with pytest.raises(ValidationError, match="not the extremum of the recorded measures"):
        _build_one(spec)


def test_a_universe_about_another_entity_is_refused_at_authoring():
    spec = _axis5_spec()
    spec["entities"] = [{"label": "Mount Kenya", "qid": "Q3757"}]
    with pytest.raises(ValidationError, match="not among the constraint's entities"):
        _build_one(spec)
