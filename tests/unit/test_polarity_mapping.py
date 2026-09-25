"""The Q21 polarity mapping in PRODUCTION Stage 0, across every answer type.

Covers affirmative and negated polar probes for entity, date and boolean
constraints. The double-negation rows are the ones worth having: "Is it false
that the capital is Canberra?" answered "NO" means the capital IS Canberra, and
getting that backwards would silently invert a quarter of the benchmark.
"""

import datetime as dt

import pytest

from semintegrity.canonicalization.canonicaliser import canonicalise, classify, parse_yes_no
from semintegrity.detectors.d1.exact_match import check_pair
from semintegrity.schemas.enums import (
    AnswerType,
    ConstraintClass,
    Domain,
    ResponseLabel,
    Verdict,
)
from semintegrity.schemas.probe import Probe
from semintegrity.schemas.response import Provenance, RawResponse
from tests.fixtures.synthetic_benchmark import make_constraint

CID = "K-C1-GEO-01"


def _constraint(answer_type: AnswerType, space, gold):
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    return c.model_copy(update={
        "answer_type": answer_type, "answer_space": space,
        "gold_answer": gold, "answer_aliases": {},
    })


def _probe(polarity: str, expected: str, n: int = 1) -> Probe:
    return Probe(
        constraint_id=CID, probe_id=f"{CID}-P0{n}", logical_form="lf",
        subject="S", predicate="P", object="", time_scope="", quantifier="none",
        polarity=polarity, answer_type="entity", syntax="interrogative",
        register="formal", directionality="reverse", factor_cell_index=n,
        probe_text="probe", expected_answer=expected,
    )


def _raw(text: str, n: int = 1) -> RawResponse:
    return RawResponse(
        response_id="R-" + "c" * 12, run_id="r", experiment_id="e",
        config_snapshot_sha256="0" * 64, constraint_id=CID, probe_id=f"{CID}-P0{n}",
        tier="pilot", track="A", semantic_instruction_id="trackA.v1",
        raw_text=text, timed_out=False, retry_index=0,
        provenance=Provenance(
            model_id="m", hf_revision_hash="a" * 40, tokenizer_hash="t",
            chat_template_hash="c", transformers_version="4.57.6", vllm_version="0.11.2",
            torch_version="2.9.0", cuda_version="12.8", gpu_model="A100",
            dtype="bfloat16", quantisation="none", temperature=0.0, top_p=1.0,
            top_k=-1, repetition_penalty=1.0, max_new_tokens=24, stop_sequences=[],
            seed=1, rendered_prompt="p", batch_size=1, sample_index=0,
            timestamp=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc),
        ),
    )


ENTITY = (AnswerType.ENTITY, ["Canberra", "Sydney", "Melbourne"], "Canberra")
DATE = (AnswerType.DATE, ["1927", "1901", "1913"], "1927")


@pytest.mark.parametrize("answer_type,space,gold", [ENTITY, DATE], ids=["entity", "date"])
@pytest.mark.parametrize(
    "polarity,said,expected_label",
    [
        ("affirmative", "YES", ResponseLabel.ANSWER),
        ("affirmative", "NO", ResponseLabel.NEGATED),
        ("negated", "YES", ResponseLabel.NEGATED),
        ("negated", "NO", ResponseLabel.ANSWER),   # double negation
    ],
)
def test_entity_and_date_polar_probes(answer_type, space, gold, polarity, said, expected_label):
    c = _constraint(answer_type, space, gold)
    expected = "YES" if polarity == "affirmative" else "NO"
    res = classify(_raw(said), c, _probe(polarity, expected))
    assert res.label is expected_label
    # Either way the canonical answer is the candidate the probe named; the
    # label says whether the model affirmed or denied it.
    assert res.canonical_answer == gold


@pytest.mark.parametrize(
    "polarity,said,holds",
    [
        ("affirmative", "YES", "YES"),
        ("affirmative", "NO", "NO"),
        ("negated", "YES", "NO"),
        ("negated", "NO", "YES"),   # double negation
    ],
)
def test_boolean_polar_probes_normalise_to_whether_the_proposition_holds(polarity, said, holds):
    """Boolean constraints are NOT exempt -- this is where every probe is polar."""
    c = _constraint(AnswerType.BOOLEAN, ["YES", "NO"], "YES")
    expected = "YES" if polarity == "affirmative" else "NO"
    res = classify(_raw(said), c, _probe(polarity, expected))
    assert res.label is ResponseLabel.ANSWER
    assert res.canonical_answer == holds


def test_affirmative_yes_and_negated_no_agree():
    """The pair that used to be scored as a contradiction on every constraint."""
    c = _constraint(AnswerType.BOOLEAN, ["YES", "NO"], "YES")
    a = canonicalise(_raw("YES", 1), c, _probe("affirmative", "YES", 1))
    b = canonicalise(_raw("NO", 2), c, _probe("negated", "NO", 2))
    assert a.canonical_answer == b.canonical_answer == "YES"
    assert check_pair(a, b).verdict is Verdict.SATISFIED


def test_negation_contradicts_the_definite_answer_it_denies():
    c = _constraint(*ENTITY)
    yes = canonicalise(_raw("YES", 1), c, _probe("affirmative", "YES", 1))
    no = canonicalise(_raw("NO", 2), c, _probe("affirmative", "YES", 2))
    assert yes.label is ResponseLabel.ANSWER
    assert no.label is ResponseLabel.NEGATED
    assert check_pair(yes, no).verdict is Verdict.VIOLATION


def test_negation_is_compatible_with_a_different_member():
    """'not Canberra' and 'Sydney' are jointly satisfiable."""
    c = _constraint(*ENTITY)
    negated = canonicalise(_raw("NO", 1), c, _probe("affirmative", "YES", 1))
    sydney = canonicalise(_raw("Sydney", 2), c, _probe("affirmative", "Canberra", 2))
    assert negated.label is ResponseLabel.NEGATED
    assert sydney.label is ResponseLabel.ANSWER
    assert check_pair(negated, sydney).verdict is Verdict.SATISFIED


def test_two_negations_never_contradict():
    c = _constraint(*ENTITY)
    a = canonicalise(_raw("NO", 1), c, _probe("affirmative", "YES", 1))
    b = canonicalise(_raw("no", 2), c, _probe("affirmative", "YES", 2))
    assert check_pair(a, b).verdict is Verdict.SATISFIED


def test_abstention_still_wins_over_the_polarity_mapping():
    """Order matters: a refusal that happens to start with a hedge is not a YES."""
    c = _constraint(*ENTITY)
    res = classify(_raw("I don't know"), c, _probe("affirmative", "YES"))
    assert res.label is ResponseLabel.ABSTAIN


@pytest.mark.parametrize("text", ["The answer is yes", "Probably", "Canberra maybe"])
def test_non_polar_text_on_a_polar_probe_does_not_become_a_boolean(text):
    """Strict parsing: a yes buried in a sentence must not be promoted to YES.

    Inferring a polar answer the model did not commit to would manufacture data,
    which is worse than recording an INVALID.
    """
    c = _constraint(AnswerType.BOOLEAN, ["YES", "NO"], "YES")
    res = classify(_raw(text), c, _probe("affirmative", "YES"))
    assert res.label is not ResponseLabel.ANSWER or res.canonical_answer != "YES"


@pytest.mark.parametrize(
    "text,expected",
    [("yes", True), ("YES", True), ("Yes.", True), ("true", True),
     ("no", False), ("NO", False), ("No,", False), ("false", False),
     ("", None), ("Canberra", None), ("The answer is yes", None)],
)
def test_parse_yes_no_is_strict(text, expected):
    assert parse_yes_no(text) is expected


def test_open_probe_is_unaffected_by_the_mapping():
    """Case 2 of the spec: an open probe still matches the answer space."""
    c = _constraint(*ENTITY)
    res = classify(_raw("Sydney"), c, _probe("affirmative", "Canberra"))
    assert res.label is ResponseLabel.ANSWER
    assert res.canonical_answer == "Sydney"


def test_probe_must_match_the_response():
    """Canonicalising against the wrong probe would silently mis-map polarity."""
    c = _constraint(*ENTITY)
    with pytest.raises(ValueError, match="does not match"):
        classify(_raw("yes", 1), c, _probe("affirmative", "YES", 2))
