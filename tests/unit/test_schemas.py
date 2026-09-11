"""Schema invariants: the proposal's records, enforced at load time."""

import datetime as dt

import pytest

from semintegrity.schemas.constraint import Constraint, TemporalValidity
from semintegrity.schemas.enums import ConstraintClass, Domain, ResponseLabel
from semintegrity.schemas.probe import (
    EQUIVALENCE_KEY_FIELDS,
    Probe,
    assert_distinct_surfaces,
    assert_mutually_equivalent,
)
from semintegrity.schemas.response import (
    REQUIRED_PROVENANCE_FIELDS,
    Provenance,
    pair_is_evaluable,
)
from tests.fixtures.responses import canon
from tests.fixtures.synthetic_benchmark import make_constraint


# --- constraint ------------------------------------------------------------
def test_constraint_round_trips_the_proposal_field_name():
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    assert c.to_record()["class"] == "C1"


def test_all_seventeen_proposal_fields_are_present():
    proposal_fields = {
        "constraint_id", "family_id", "schema_id", "domain", "constraint_class",
        "formal_predicate", "constraint_text", "entities", "entity_qids",
        "entity_sitelinks", "gold_proposition", "gold_source", "gold_source_url",
        "gold_source_date", "temporal_validity", "ambiguity_notes",
        "prerequisite_atomic_facts",
    }
    assert proposal_fields <= set(Constraint.model_fields)
    assert len(proposal_fields) == 17


def test_unknown_fields_are_rejected():
    d = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1).to_record()
    d["typo_field"] = 1
    with pytest.raises(ValueError, match="typo_field"):
        Constraint.model_validate(d)


def test_c4_requires_temporal_validity():
    d = make_constraint(ConstraintClass.C4, Domain.HISTORY, 1).to_record()
    d["temporal_validity"] = None
    with pytest.raises(ValueError, match="temporal_validity"):
        Constraint.model_validate(d)


def test_temporal_validity_rejects_reversed_interval():
    with pytest.raises(ValueError, match="precedes start"):
        TemporalValidity(start=dt.date(2000, 1, 1), end=dt.date(1990, 1, 1))


def test_temporal_validity_distinguishes_open_from_unknown_end():
    assert TemporalValidity(end=None, end_unknown=False).end_unknown is False
    assert TemporalValidity(end=None, end_unknown=True).end_unknown is True
    with pytest.raises(ValueError, match="end_unknown"):
        TemporalValidity(end=dt.date(2000, 1, 1), end_unknown=True)


def test_median_sitelinks():
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1, sitelinks=(300, 100))
    assert c.median_sitelinks == 200.0


def test_constraint_class_is_not_ordered():
    """Guards against class ever being modelled as ordinal or continuous."""
    with pytest.raises(TypeError):
        _ = ConstraintClass.C1 < ConstraintClass.C4  # type: ignore[operator]


# --- probe -----------------------------------------------------------------
def _probe(pid: str, **over):
    base = dict(
        constraint_id=pid.rsplit("-P", 1)[0],
        probe_id=pid,
        logical_form="capital_of(Australia)=?x",
        subject="Australia",
        predicate="capital_of",
        object="",
        time_scope="",
        quantifier="none",
        polarity="affirmative",
        answer_type="entity",
        syntax="declarative",
        register="formal",
        directionality="direct",
        factor_cell_index=0,
        probe_text="The capital of Australia is",
        expected_answer="Canberra",
    )
    return Probe(**{**base, **over})


def test_polarity_is_outside_the_equivalence_key():
    """Q21: recorded behaviour, awaiting researcher approval."""
    assert "polarity" not in EQUIVALENCE_KEY_FIELDS
    a = _probe("K-C1-GEO-01-P01")
    b = _probe("K-C1-GEO-01-P02", polarity="negated", factor_cell_index=1)
    assert a.is_equivalent_to(b)


def test_differing_logical_form_breaks_equivalence():
    a = _probe("K-C1-GEO-01-P01")
    b = _probe("K-C1-GEO-01-P02", logical_form="largest_city_of(Australia)=?x", factor_cell_index=1)
    assert not a.is_equivalent_to(b)
    with pytest.raises(ValueError, match="not mutually equivalent"):
        assert_mutually_equivalent([a, b])


def test_duplicate_factor_cells_are_rejected():
    a = _probe("K-C1-GEO-01-P01")
    b = _probe("K-C1-GEO-01-P02")  # identical surface factors
    with pytest.raises(ValueError, match="same factor cell"):
        assert_distinct_surfaces([a, b])


def test_cloze_requires_a_blank():
    with pytest.raises(ValueError, match="___"):
        _probe("K-C1-GEO-01-P01", syntax="cloze")
    _probe("K-C1-GEO-01-P01", syntax="cloze", probe_text="The capital of Australia is ___.")


def test_boolean_probe_expects_yes_or_no():
    with pytest.raises(ValueError, match="YES or NO"):
        _probe("K-C1-GEO-01-P01", answer_type="boolean", expected_answer="Canberra")
    _probe("K-C1-GEO-01-P01", answer_type="boolean", expected_answer="YES")


def test_probe_must_belong_to_its_constraint():
    with pytest.raises(ValueError):
        _probe("K-C1-GEO-01-P01", constraint_id="K-C4-HIS-02")


# --- response --------------------------------------------------------------
def test_provenance_matches_the_proposal_list_exactly():
    """Same 22 fields as the proposal; the class groups them for readability,
    while REQUIRED_PROVENANCE_FIELDS and the config preserve the proposal order."""
    assert set(Provenance.model_fields) == set(REQUIRED_PROVENANCE_FIELDS)
    assert len(Provenance.model_fields) == len(REQUIRED_PROVENANCE_FIELDS) == 22
    assert all(f.is_required() for f in Provenance.model_fields.values()), (
        "no provenance field may have a default — a missing value must be supplied, not inferred"
    )


def test_greedy_decoding_admits_only_sample_index_zero():
    fields = dict(
        model_id="m", hf_revision_hash="a" * 40, tokenizer_hash="t", chat_template_hash="c",
        transformers_version="4.44.0", vllm_version="0.5.0", torch_version="2.4.0",
        cuda_version="12.1", gpu_model="A100", dtype="bfloat16", quantisation="none",
        temperature=0.0, top_p=1.0, top_k=-1, repetition_penalty=1.0, max_new_tokens=24,
        stop_sequences=["\n\n"], seed=1, rendered_prompt="p", batch_size=8,
        timestamp=dt.datetime(2026, 9, 11, tzinfo=dt.timezone.utc),
    )
    Provenance(**fields, sample_index=0)
    with pytest.raises(ValueError, match="sample_index 0"):
        Provenance(**fields, sample_index=1)


def test_canonical_response_label_answer_coherence():
    with pytest.raises(ValueError, match="requires a canonical_answer"):
        canon("K-C1-GEO-01-P01", None)
    with pytest.raises(ValueError, match="must not carry a canonical_answer"):
        canon("K-C1-GEO-01-P01", "Canberra", label=ResponseLabel.ABSTAIN)
    with pytest.raises(ValueError, match="at least two"):
        canon("K-C1-GEO-01-P01", None, label=ResponseLabel.AMBIGUOUS, candidates=["Canberra"])


def test_pair_evaluability_requires_both_answers():
    a = canon("K-C1-GEO-01-P01", "Canberra")
    b = canon("K-C1-GEO-01-P02", "Sydney")
    absent = canon("K-C1-GEO-01-P03", None, label=ResponseLabel.ABSTAIN)
    assert pair_is_evaluable(a, b)
    assert not pair_is_evaluable(a, absent)
    assert not pair_is_evaluable(absent, absent)


def test_raw_response_is_immutable():
    from semintegrity.schemas.response import RawResponse

    r = RawResponse(
        response_id="R-" + "a" * 12, run_id="run", experiment_id="exp",
        config_snapshot_sha256="0" * 64, constraint_id="K-C1-GEO-01",
        probe_id="K-C1-GEO-01-P01", tier="primary", track="A",
        semantic_instruction_id="trackA.v1", raw_text="Canberra",
        provenance=Provenance(
            model_id="m", hf_revision_hash="a" * 40, tokenizer_hash="t", chat_template_hash="c",
            transformers_version="4.44.0", vllm_version="0.5.0", torch_version="2.4.0",
            cuda_version="12.1", gpu_model="A100", dtype="bfloat16", quantisation="none",
            temperature=0.0, top_p=1.0, top_k=-1, repetition_penalty=1.0, max_new_tokens=24,
            stop_sequences=[], seed=1, rendered_prompt="p", batch_size=1, sample_index=0,
            timestamp=dt.datetime(2026, 9, 11, tzinfo=dt.timezone.utc),
        ),
    )
    with pytest.raises(ValueError):
        r.raw_text = "Sydney"  # type: ignore[misc]
    assert r.resume_key() == ("exp", "m", "K-C1-GEO-01-P01", 0)
