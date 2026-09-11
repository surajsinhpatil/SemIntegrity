"""Stage 0 canonicalisation (§4.7) and D1 (§4.8.3)."""

import datetime as dt

import pytest

from semintegrity.canonicalization.canonicaliser import (
    canonicalise,
    canonicaliser_hash,
    classify,
    normalise,
)
from semintegrity.detectors.d1.exact_match import check_all_pairs, check_pair, coverage
from semintegrity.schemas.enums import AnswerType, ConstraintClass, Domain, ResponseLabel, Verdict
from semintegrity.schemas.response import Provenance, RawResponse
from tests.fixtures.responses import canon
from tests.fixtures.synthetic_benchmark import make_constraint


@pytest.fixture
def constraint():
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    return c.model_copy(
        update={
            "answer_type": AnswerType.ENTITY,
            "answer_space": ["Canberra", "Sydney", "Melbourne"],
            "gold_answer": "Canberra",
            "answer_aliases": {"Canberra": ["Canberra, ACT", "the ACT capital"]},
        }
    )


def _raw(text: str, *, probe="K-C1-GEO-01-P01", timed_out=False) -> RawResponse:
    return RawResponse(
        response_id="R-" + "a" * 12, run_id="r", experiment_id="e",
        config_snapshot_sha256="0" * 64, constraint_id=probe.rsplit("-P", 1)[0],
        probe_id=probe, tier="pilot", track="A", semantic_instruction_id="trackA.v1",
        raw_text=text, timed_out=timed_out, retry_index=1 if timed_out else 0,
        provenance=Provenance(
            model_id="m", hf_revision_hash="a" * 40, tokenizer_hash="t", chat_template_hash="c",
            transformers_version="5.0.0", vllm_version="0.5.0", torch_version="2.4.0",
            cuda_version="12.1", gpu_model="A100", dtype="bfloat16", quantisation="none",
            temperature=0.0, top_p=1.0, top_k=-1, repetition_penalty=1.0, max_new_tokens=24,
            stop_sequences=[], seed=1, rendered_prompt="p", batch_size=1, sample_index=0,
            timestamp=dt.datetime(2026, 9, 11, tzinfo=dt.timezone.utc),
        ),
    )


# --- the §4.7 mapping table ------------------------------------------------
@pytest.mark.parametrize(
    "text,expected_label,expected_answer",
    [
        ("Canberra", ResponseLabel.ANSWER, "Canberra"),
        ("  canberra.  ", ResponseLabel.ANSWER, "Canberra"),
        ("Canberra, ACT", ResponseLabel.ANSWER, "Canberra"),      # alias table
        ("the ACT capital", ResponseLabel.ANSWER, "Canberra"),    # alias table
        ("Sydney", ResponseLabel.ANSWER, "Sydney"),
        ("UNKNOWN", ResponseLabel.ABSTAIN, None),
        ("I don't know.", ResponseLabel.ABSTAIN, None),
        ("As an AI, I cannot verify this.", ResponseLabel.ABSTAIN, None),
        ("", ResponseLabel.INVALID, None),
        ("   ", ResponseLabel.INVALID, None),
        ("Reykjavik", ResponseLabel.INVALID, None),               # outside the closed space
        ("Canberra or Sydney", ResponseLabel.AMBIGUOUS, None),
    ],
)
def test_stage0_mapping(constraint, text, expected_label, expected_answer):
    result = classify(_raw(text), constraint)
    assert result.label is expected_label
    assert result.canonical_answer == expected_answer


def test_timeout_becomes_failed_after_one_retry(constraint):
    assert classify(_raw("", timed_out=True), constraint).label is ResponseLabel.FAILED


def test_abstention_is_checked_before_answer_matching(constraint):
    """'I don't know, but possibly Sydney' is an abstention, not an answer.

    Matching first would silently convert refusals into confident answers and
    deflate the abstention rate §4.7 treats as a first-class outcome.
    """
    result = classify(_raw("I don't know, but possibly Sydney."), constraint)
    assert result.label is ResponseLabel.ABSTAIN
    assert result.canonical_answer is None


def test_ambiguous_records_every_candidate(constraint):
    result = classify(_raw("Either Canberra or Melbourne."), constraint)
    assert result.label is ResponseLabel.AMBIGUOUS
    assert set(result.candidates_found) == {"Canberra", "Melbourne"}


def test_substring_collisions_do_not_match(constraint):
    """'Sydneyish' must not match 'Sydney' — word boundaries are enforced."""
    assert classify(_raw("Sydneyish"), constraint).label is ResponseLabel.INVALID


def test_boolean_answers(constraint):
    c = constraint.model_copy(
        update={"answer_type": AnswerType.BOOLEAN, "answer_space": ["YES", "NO"],
                "gold_answer": "YES", "answer_aliases": {}}
    )
    assert classify(_raw("Yes"), c).canonical_answer == "YES"
    assert classify(_raw("no"), c).canonical_answer == "NO"
    assert classify(_raw("True"), c).canonical_answer == "YES"
    assert classify(_raw("Yes and no"), c).label is ResponseLabel.AMBIGUOUS


def test_date_answers(constraint):
    c = constraint.model_copy(
        update={"answer_type": AnswerType.DATE, "answer_space": ["1901", "1927", "1788"],
                "gold_answer": "1927", "answer_aliases": {}}
    )
    assert classify(_raw("1927"), c).canonical_answer == "1927"
    assert classify(_raw("It was 1927-05-09."), c).canonical_answer == "1927"
    assert classify(_raw("1066"), c).label is ResponseLabel.INVALID


def test_canonicalise_stamps_a_freeze_hash(constraint):
    cr = canonicalise(_raw("Canberra"), constraint)
    assert cr.canonicaliser_sha256 == canonicaliser_hash()
    assert len(cr.canonicaliser_sha256) == 64
    assert cr.response_id == "R-" + "a" * 12  # traceable to its source


def test_mismatched_constraint_is_rejected(constraint):
    other = make_constraint(ConstraintClass.C2, Domain.HISTORY, 1)
    with pytest.raises(ValueError, match="belongs to"):
        classify(_raw("Canberra"), other)


def test_normalise_strips_accents_and_punctuation():
    assert normalise("Kraków, Poland!") == "krakow poland"


# --- D1 ---------------------------------------------------------------------
def test_d1_flags_differing_answers():
    a = canon("K-C1-GEO-01-P01", "Canberra")
    b = canon("K-C1-GEO-01-P02", "Sydney")
    r = check_pair(a, b)
    assert r.is_contradiction and r.pair_id == "K-C1-GEO-01-P01xP02"


def test_d1_accepts_matching_answers():
    a = canon("K-C1-GEO-01-P01", "Canberra")
    b = canon("K-C1-GEO-01-P02", "Canberra")
    assert check_pair(a, b).verdict is Verdict.SATISFIED


def test_d1_marks_non_evaluable_pairs():
    a = canon("K-C1-GEO-01-P01", "Canberra")
    b = canon("K-C1-GEO-01-P02", None, label=ResponseLabel.ABSTAIN)
    r = check_pair(a, b)
    assert r.verdict is Verdict.NOT_APPLICABLE and "ABSTAIN" in r.reason


def test_d1_coverage_shrinks_with_abstention():
    """§4.8.3: D1's coverage shrinkage is the reportable result."""
    full = [canon(f"K-C1-GEO-01-P0{i}", "Canberra") for i in range(1, 5)]
    assert coverage(check_all_pairs(full)) == 1.0

    partial = full[:2] + [
        canon(f"K-C1-GEO-01-P0{i}", None, label=ResponseLabel.ABSTAIN) for i in (3, 4)
    ]
    assert coverage(check_all_pairs(partial)) == pytest.approx(1 / 6)
    assert coverage([]) == 0.0
