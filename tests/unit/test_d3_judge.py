"""D3 — pairwise LLM judge (§4.8.5, configs/detectors/d3_llm_judge.yaml).

The generator is injected, so the protocol is tested without 29 GB of weights.
Most of these cover malformed and ambiguous output, because that is where a
judge-based detector quietly turns into noise.
"""

import datetime as dt
import json

import pytest

from semintegrity.detectors.d3.judge import (
    VALID_LABELS,
    D3Judge,
    coverage,
    parse_failure_rate,
    parse_judgement,
)
from semintegrity.schemas.enums import ConstraintClass, Domain, ResponseLabel, Verdict
from semintegrity.schemas.response import CanonicalResponse
from semintegrity.utils.paths import p
from tests.fixtures.synthetic_benchmark import make_constraint

PROMPT = p("configs/detectors/d3_prompt.txt").read_text(encoding="utf-8")


def _constraint():
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    return c.model_copy(update={
        "answer_space": ["Canberra", "Sydney", "Melbourne"], "gold_answer": "Canberra",
        "gold_proposition": "The capital city of Australia is Canberra.",
        "constraint_text": "A country has exactly one capital city.",
    })


def _resp(n: int, answer: str | None, label=ResponseLabel.ANSWER) -> CanonicalResponse:
    return CanonicalResponse(
        response_id=f"R-{n:012x}", constraint_id="K-C1-GEO-01",
        probe_id=f"K-C1-GEO-01-P0{n}", label=label, canonical_answer=answer,
        matched_alias=answer, candidates_found=[answer] if answer else [],
        canonicaliser_version="1.1", canonicaliser_sha256="0" * 64,
        canonicalised_at=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc),
    )


class ScriptedJudge:
    name = "scripted-test-judge"

    def __init__(self, reply):
        self.reply = reply
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply(prompt) if callable(self.reply) else self.reply


def _ok(label="CONTRADICTION", confidence=0.9, **kw):
    return json.dumps({"label": label, "confidence": confidence,
                       "conflicting_span_a": kw.get("a", "Canberra"),
                       "conflicting_span_b": kw.get("b", "Sydney"),
                       "reason": "different cities"})


# --- the shipped prompt ------------------------------------------------------

def test_prompt_file_has_the_required_placeholders_and_labels():
    for placeholder in ("{constraint_text}", "{claim_a}", "{claim_b}"):
        assert placeholder in PROMPT
    for label in VALID_LABELS:
        assert label in PROMPT


def test_prompt_tells_the_judge_not_to_decide_which_is_correct():
    """Two statements can contradict while both are wrong. A judge that rules on
    factual correctness measures accuracy, not consistency."""
    # Normalise whitespace: the prompt is line-wrapped, and a semantic
    # assertion should not depend on where the wrap falls.
    flat = " ".join(PROMPT.lower().split())
    assert "do not judge which one is factually correct" in flat
    assert "both be wrong" in flat or "both are wrong" in flat


# --- parsing: the well-formed case ------------------------------------------

def test_parses_a_well_formed_judgement():
    obj, err = parse_judgement(_ok())
    assert err is None and obj["label"] == "CONTRADICTION"


def test_parses_json_embedded_in_prose():
    """Extraction is generous; validation is not."""
    obj, err = parse_judgement("Sure! Here is my answer:\n" + _ok() + "\nHope that helps.")
    assert err is None and obj["label"] == "CONTRADICTION"


# --- parsing: malformed output ----------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "no JSON object found"),
        ("I think they contradict.", "no JSON object found"),
        ("{not json at all}", "invalid JSON"),
        ('{"confidence": 0.9}', "missing 'label'"),
        ('{"label": "MAYBE", "confidence": 0.9}', "not one of"),
        ('{"label": "CONTRADICTION"}', "missing 'confidence'"),
        ('{"label": "CONTRADICTION", "confidence": "high"}', "not a number"),
        ('{"label": "CONTRADICTION", "confidence": 1.5}', "outside [0, 1]"),
        ('{"label": "CONTRADICTION", "confidence": -0.2}', "outside [0, 1]"),
        ('{"label": "CONTRADICTION", "confidence": true}', "not a number"),
    ],
)
def test_malformed_output_reports_a_reason_and_never_raises(text, expected):
    """Losing a malformed judgement to an exception loses the evidence that the
    judge is misbehaving."""
    _, err = parse_judgement(text)
    assert err is not None and expected in err


def test_unparseable_output_is_distinguishable_from_unclear():
    """Three different states that must not collapse into one another:
    a real verdict, an honest UNCLEAR, and a broken reply."""
    c = _constraint()
    a, b = _resp(1, "Canberra"), _resp(2, "Sydney")

    broken = D3Judge(ScriptedJudge("total gibberish"), PROMPT).judge_pair(c, a, b)
    unclear = D3Judge(ScriptedJudge(_ok("UNCLEAR", 0.4)), PROMPT).judge_pair(c, a, b)
    real = D3Judge(ScriptedJudge(_ok("CONTRADICTION")), PROMPT).judge_pair(c, a, b)

    assert broken.label is None and broken.parse_error and not broken.parsed
    assert unclear.label == "UNCLEAR" and unclear.parsed and unclear.parse_error is None
    assert real.label == "CONTRADICTION" and real.parsed
    # Both non-verdicts are NOT_APPLICABLE for coverage, but remain separable.
    assert broken.verdict is unclear.verdict is Verdict.NOT_APPLICABLE
    assert real.verdict is Verdict.VIOLATION


def test_parse_failure_rate_is_reported():
    c = _constraint()
    good = D3Judge(ScriptedJudge(_ok()), PROMPT).judge_pair(c, _resp(1, "Canberra"),
                                                            _resp(2, "Sydney"))
    bad = D3Judge(ScriptedJudge("nope"), PROMPT).judge_pair(c, _resp(1, "Canberra"),
                                                            _resp(2, "Sydney"))
    assert parse_failure_rate([good, bad]) == 0.5
    assert parse_failure_rate([]) == 0.0


# --- A/B randomisation -------------------------------------------------------

def test_ab_order_is_randomised_and_recorded():
    c = _constraint()
    responses = [_resp(i, "Canberra" if i % 2 else "Sydney") for i in range(1, 9)]
    js = D3Judge(ScriptedJudge(_ok()), PROMPT, seed=1).judge_all_pairs(c, responses)
    orders = {j.presented_swapped for j in js}
    assert orders == {True, False}, "A/B order must actually vary, not merely be claimed"


def test_ab_randomisation_is_reproducible_under_a_seed():
    c = _constraint()
    responses = [_resp(i, "Canberra" if i % 2 else "Sydney") for i in range(1, 7)]
    runs = [
        [j.presented_swapped
         for j in D3Judge(ScriptedJudge(_ok()), PROMPT, seed=7).judge_all_pairs(c, responses)]
        for _ in range(2)
    ]
    assert runs[0] == runs[1]


def test_swapped_presentation_swaps_the_spans_back():
    """The verdict is reported in the CALLER's orientation whatever the judge
    saw; otherwise a position-effect analysis would compare mislabelled spans."""
    c = _constraint()
    a, b = _resp(1, "Canberra"), _resp(2, "Sydney")
    judge = D3Judge(ScriptedJudge(_ok(a="FIRST-SHOWN", b="SECOND-SHOWN")), PROMPT, seed=0)
    j = judge.judge_pair(c, a, b)
    if j.presented_swapped:
        assert (j.conflicting_span_a, j.conflicting_span_b) == ("SECOND-SHOWN", "FIRST-SHOWN")
    else:
        assert (j.conflicting_span_a, j.conflicting_span_b) == ("FIRST-SHOWN", "SECOND-SHOWN")


# --- archiving ---------------------------------------------------------------

def test_raw_output_and_prompt_are_archived():
    """`archive_raw_judgements: true`. A parsing change must be re-runnable
    against what the judge actually said."""
    c = _constraint()
    raw = _ok()
    j = D3Judge(ScriptedJudge(raw), PROMPT).judge_pair(c, _resp(1, "Canberra"),
                                                       _resp(2, "Sydney"))
    assert j.raw_output == raw
    assert "The capital city of Australia is" in j.prompt
    assert j.judge == "scripted-test-judge"


# --- skipping ----------------------------------------------------------------

def test_pairs_without_a_claim_are_skipped_not_judged():
    """"Nothing to judge" must not become "the judge was unsure"."""
    c = _constraint()
    assert D3Judge(ScriptedJudge(_ok()), PROMPT).judge_pair(
        c, _resp(1, "Canberra"), _resp(2, None, ResponseLabel.ABSTAIN)
    ) is None


def test_coverage_denominator_is_all_pairs_not_just_judged_ones():
    c = _constraint()
    responses = [_resp(1, "Canberra"), _resp(2, "Sydney"),
                 _resp(3, None, ResponseLabel.ABSTAIN)]
    js = D3Judge(ScriptedJudge(_ok()), PROMPT).judge_all_pairs(c, responses)
    assert len(js) == 1                      # only the Canberra/Sydney pair is judgeable
    assert coverage(js, n_pairs=3) == pytest.approx(1 / 3)
    assert coverage([], n_pairs=0) == 0.0


def test_a_consistent_set_yields_no_contradictions():
    c = _constraint()
    js = D3Judge(ScriptedJudge(_ok("COMPATIBLE", 0.95)), PROMPT).judge_all_pairs(
        c, [_resp(i, "Canberra") for i in range(1, 5)]
    )
    assert js and not any(j.is_contradiction for j in js)
    assert all(j.verdict is Verdict.SATISFIED for j in js)


def test_prompt_template_is_validated_at_construction():
    with pytest.raises(ValueError, match="claim_a"):
        D3Judge(ScriptedJudge(_ok()), "a template with no placeholders")
