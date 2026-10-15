"""Decomposing Stage 0 INVALIDs (§7.6).

Mistral's 63.02% CANON rate is one number covering at least two different
events, and the test cases below are taken from the REAL pasted diagnostic of
`results/raw/primary_trackA/mistral7b-v03.jsonl` so that the taxonomy is pinned
against observed output rather than invented output.

These tests assert CLASSIFICATION ONLY. None of them asserts that a reply
should have been labelled ANSWER, and none licenses a canonicaliser change:
Stage 0 and the >=95% threshold are FROZEN.
"""

from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import sys

import pytest

from semintegrity.analysis.invalid_taxonomy import (
    CATEGORIES,
    EMPTY,
    NON_POLAR_NO_SPACE_MEMBER,
    POLAR_BOOLEAN_YESNO_BURIED,
    POLAR_ENTITY_DATE_MEMBER,
    POLAR_NO_YESNO_NO_SPACE_MEMBER,
    categorise,
    decompose,
)
from semintegrity.benchmark.loader import load_split
from semintegrity.schemas.enums import (
    AnswerType,
    ConstraintClass,
    Domain,
    Polarity,
)
from semintegrity.schemas.probe import Probe
from semintegrity.schemas.response import Provenance, RawResponse
from semintegrity.utils.paths import data_path, project_root
from tests.fixtures.synthetic_benchmark import make_constraint


def _constraint(space, gold, answer_type=AnswerType.DATE):
    """`model_copy` does NOT coerce, so answer_type must be the enum itself.

    Production constraints arrive through the validating loader; a plain string
    here would silently fail every `is AnswerType.X` comparison in the code
    under test and make this suite pass for the wrong reason.
    """
    c = make_constraint(ConstraintClass.C4, Domain.SCIENCE_TECHNOLOGY, 16)
    assert isinstance(answer_type, AnswerType)
    return c.model_copy(update={
        "answer_space": list(space), "gold_answer": gold,
        "answer_type": answer_type,
        "gold_proposition": f"The year it ended is {gold}.",
    })


def _probe(c, expected, *, polarity=Polarity.AFFIRMATIVE, idx=1):
    return Probe(
        probe_id=f"{c.constraint_id}-P0{idx}", constraint_id=c.constraint_id,
        probe_text="The year it ended is ___.", expected_answer=expected,
        answer_type=c.answer_type, polarity=polarity,
        syntax="cloze", directionality="direct", factor_cell_index=idx,
        logical_form="ended(apollo) = y", subject="apollo_program",
        predicate="ended", object=str(expected), quantifier="none",
        generated_at=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc),
    )


def _raw(c, p, text):
    return RawResponse(
        response_id="R-" + "c" * 12, run_id="r", experiment_id="tax",
        config_snapshot_sha256="0" * 64, constraint_id=c.constraint_id,
        probe_id=p.probe_id, tier="primary", track="A",
        semantic_instruction_id="trackA.v1", raw_text=text, timed_out=False,
        retry_index=0,
        provenance=Provenance(
            model_id="mistralai/Mistral-7B-Instruct-v0.3", hf_revision_hash="a" * 40,
            tokenizer_hash="t", chat_template_hash="c",
            transformers_version="4.57.6", vllm_version="0.11.2",
            torch_version="2.9.0", cuda_version="12.8", gpu_model="A100",
            dtype="bfloat16", quantisation="none", temperature=0.0, top_p=1.0,
            top_k=-1, repetition_penalty=1.0, max_new_tokens=24, stop_sequences=[],
            seed=1, rendered_prompt="p", batch_size=1, sample_index=0,
            timestamp=dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc),
        ),
    )


# --- observed Mistral cases ----------------------------------------------

def test_non_polar_answer_outside_the_closed_space_is_model_error():
    """K-C4-SCI-16-P01: asked the Apollo end year, said ' 1975'.

    1975 is not in ['1972','1961','1981']. INVALID is CORRECT, and this is a
    finding about the model, not about Stage 0.
    """
    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "1972")
    case = categorise(_raw(c, p, " 1975"), c, p)
    assert case is not None, "Stage 0 must still call this INVALID"
    assert case.category == NON_POLAR_NO_SPACE_MEMBER
    assert case.candidates == ()
    assert case.polar is False


def test_polar_probe_on_a_DATE_constraint_answered_with_a_member_is_q31():
    """K-C1-HIS-16-P04 / K-C1-BIO-16-P04 shape: a polar cloze whose stem embeds
    the gold answer, completed with that answer instead of TRUE/FALSE.

    Observed in Qwen2.5-14B and OLMo-2 as well as Mistral, so the phenomenon is
    not Mistral-specific.
    """
    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "YES", idx=4)
    case = categorise(_raw(c, p, " 1972"), c, p)
    assert case is not None
    assert case.category == POLAR_ENTITY_DATE_MEMBER
    assert "1972" in case.candidates
    assert case.has_negation is False


def test_a_buried_YESNO_on_a_BOOLEAN_constraint_is_NOT_q31():
    """K-C1-SCI-12-P05 shape: candidates=['YES'] on a boolean constraint.

    The canonicaliser refuses answer-space matching here ON PURPOSE -- matching
    a buried 'yes' would bypass the polarity inversion and reintroduce the very
    artifact the Q21 mapping removed. Pooling these with the entity/date cases
    would misread a deliberate guard as an open question.
    """
    c = _constraint(["YES", "NO"], "YES", answer_type=AnswerType.BOOLEAN)
    p = _probe(c, "NO", polarity=Polarity.NEGATED, idx=5)
    case = categorise(_raw(c, p, " It is not yes."), c, p)
    assert case is not None
    assert case.category == POLAR_BOOLEAN_YESNO_BURIED
    assert case.category != POLAR_ENTITY_DATE_MEMBER
    assert case.has_negation is True


def test_a_negation_marker_with_a_space_member_is_counted_separately():
    """K-C4-SCI-16-P07: said ' 1972 is NOT the year the Apollo program ended.'

    A negation marker and an answer-space member co-occur with no LEADING
    yes/no. Counted as its own category because it bounds what the frozen
    first-token rule forgoes. This is NOT an assertion that the reply was a
    determinate answer, and NOT a licence to change Stage 0.
    """
    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "NO", polarity=Polarity.NEGATED, idx=7)
    case = categorise(
        _raw(c, p, " 1972 is NOT the year the Apollo program ended."), c, p
    )
    assert case is not None
    assert case.category == POLAR_ENTITY_DATE_MEMBER
    assert case.has_negation is True
    assert "1972" in case.candidates


def test_polar_probe_with_neither_yesno_nor_member():
    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "YES", idx=2)
    case = categorise(_raw(c, p, " Decimeter"), c, p)
    assert case is not None
    assert case.category == POLAR_NO_YESNO_NO_SPACE_MEMBER


def test_empty_reply():
    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "1972")
    case = categorise(_raw(c, p, "   "), c, p)
    assert case is not None
    assert case.category == EMPTY


# --- the module must not reclassify valid responses -----------------------

def test_a_valid_answer_is_not_a_case_at_all():
    """Only INVALIDs are categorised; everything else returns None."""
    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "1972")
    assert categorise(_raw(c, p, "1972"), c, p) is None


def test_a_leading_yes_on_a_polar_probe_is_not_a_case():
    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "YES", idx=4)
    assert categorise(_raw(c, p, "yes"), c, p) is None


# --- the summary separates the two kinds of failure ----------------------

def test_decompose_separates_model_error_from_fallthrough():
    c = _constraint(["1972", "1961", "1981"], "1972")
    non_polar = _probe(c, "1972", idx=1)
    polar = _probe(c, "YES", idx=4)
    raws = [
        _raw(c, non_polar, " 1975"),      # model error, correctly INVALID
        _raw(c, polar, " 1972"),          # fall-through
        _raw(c, non_polar, "1972"),       # valid, not a case
    ]
    cases, summary = decompose(
        raws, {c.constraint_id: c},
        {non_polar.probe_id: non_polar, polar.probe_id: polar},
    )
    assert len(cases) == 2
    assert summary["n_responses"] == 3
    assert summary["n_invalid"] == 2
    assert summary["n_correctly_invalid_model_error"] == 1
    assert summary["n_q31_entity_date_fallthrough"] == 1
    assert summary["q31_share_of_invalid"] == 0.5
    assert summary["n_boolean_yesno_buried"] == 0
    assert summary["n_unclassified"] == 0
    assert set(summary["counts"]) == set(CATEGORIES)


def test_an_unclassified_invalid_is_surfaced_not_swallowed():
    """A non-empty OTHER count means the taxonomy is incomplete."""
    from semintegrity.analysis.invalid_taxonomy import decompose as d

    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "1972")
    _, summary = d([_raw(c, p, " 1975")], {c.constraint_id: c}, {p.probe_id: p})
    assert "n_unclassified" in summary, "OTHER must always be reported"


def test_the_summary_states_that_stage0_stays_frozen():
    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "1972")
    _, summary = decompose([_raw(c, p, " 1975")], {c.constraint_id: c}, {p.probe_id: p})
    assert "FROZEN" in summary["interpretation"]


@pytest.mark.parametrize("category", CATEGORIES)
def test_every_category_is_reported_even_at_zero(category):
    """A missing key and a zero count must not look alike."""
    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "1972")
    _, summary = decompose([_raw(c, p, " 1975")], {c.constraint_id: c}, {p.probe_id: p})
    assert category in summary["counts"]


def test_the_recovery_ceiling_is_reported_as_an_upper_bound():
    """The arithmetic that settles Q31 without touching the canonicaliser.

    If recovering EVERY Q31 case still leaves a run below the >=0.95 gate, then
    no entity/date fall-through rule can rescue it, and the question stops being
    the one that decides whether the model is in the study.
    """
    c = _constraint(["1972", "1961", "1981"], "1972")
    non_polar = _probe(c, "1972", idx=1)
    polar = _probe(c, "YES", idx=4)
    raws = (
        [_raw(c, non_polar, " 1975")] * 3        # model error, unrecoverable
        + [_raw(c, polar, " 1972")]              # one Q31 case
        + [_raw(c, non_polar, "1972")] * 6       # valid
    )
    _, summary = decompose(
        raws, {c.constraint_id: c},
        {non_polar.probe_id: non_polar, polar.probe_id: polar},
    )
    assert summary["n_invalid"] == 4
    assert summary["canonicalisation_rate"] == pytest.approx(0.6)
    # recovering the single Q31 case lifts 0.6 -> 0.7, still under 0.95
    assert summary["ceiling_if_every_q31_case_were_recovered"] == pytest.approx(0.7)
    assert summary["ceiling_if_every_q31_case_were_recovered"] < 0.95
    assert "UPPER BOUND" in summary["interpretation"]


# --- the driver's main(), end to end -------------------------------------
#
# The module's summary keys were renamed and the driver's print block was not,
# so `classify_invalid.py` crashed on the cluster AFTER printing its table and
# BEFORE writing its JSON -- a silent stale-output failure that cost a round
# trip. main() had no test. It does now: a rename must break a test here rather
# than a run there.

_TEST_SPLIT = data_path("benchmark") / "test"


def _load_classifier():
    path = project_root() / "scripts" / "analysis" / "classify_invalid.py"
    spec = _ilu.spec_from_file_location("classify_invalid", path)
    mod = _ilu.module_from_spec(spec)
    sys.modules["classify_invalid"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(
    not (_TEST_SPLIT / "constraints.jsonl").is_file(), reason="test split not built"
)
def test_classify_invalid_main_runs_and_writes_a_report(tmp_path, capsys):
    import json as _json

    mod = _load_classifier()
    _, probe_list = load_split(_TEST_SPLIT)
    by_constraint: dict[str, list] = {}
    for probe in probe_list:
        by_constraint.setdefault(probe.constraint_id, []).append(probe)
    cids = sorted(by_constraint)[:2]

    raw_path = tmp_path / "raw.jsonl"
    with raw_path.open("w") as fh:
        for cid in cids:
            for probe in by_constraint[cid]:
                # A reply that cannot be in any closed answer space, so every
                # response is INVALID and every print path is exercised.
                fh.write(
                    _raw_for(cid, probe, "zzz unparseable zzz").model_dump_json() + "\n"
                )

    out = tmp_path / "out"
    rc = mod.main(["--raw", str(raw_path), "--split", "test",
                   "--out-dir", str(out), "--examples", "1"])
    assert rc == 0

    written = list(out.glob("*.invalid.json"))
    assert len(written) == 1, "the JSON report must actually be written"
    report = _json.loads(written[0].read_text())
    for key in (
        "n_q31_entity_date_fallthrough", "q31_share_of_invalid",
        "n_boolean_yesno_buried", "n_correctly_invalid_model_error",
        "n_negation_marker_present", "canonicalisation_rate",
        "ceiling_if_every_q31_case_were_recovered", "counts", "cases",
    ):
        assert key in report, f"the driver's report lost {key}"

    printed = capsys.readouterr().out
    assert "Q31 entity/date fall-through" in printed
    assert "boolean yes/no buried" in printed
    assert "FROZEN" in printed
    assert "ceiling if EVERY Q31 case were recovered" in printed


def _raw_for(cid, probe, text):
    return RawResponse(
        response_id="R-" + "d" * 12, run_id="r", experiment_id="tax",
        config_snapshot_sha256="0" * 64, constraint_id=cid,
        probe_id=probe.probe_id, tier="primary", track="A",
        semantic_instruction_id="trackA.v1", raw_text=text, timed_out=False,
        retry_index=0,
        provenance=Provenance(
            model_id="mistralai/Mistral-7B-Instruct-v0.3", hf_revision_hash="a" * 40,
            tokenizer_hash="t", chat_template_hash="c",
            transformers_version="4.57.6", vllm_version="0.11.2",
            torch_version="2.9.0", cuda_version="12.8", gpu_model="A100",
            dtype="bfloat16", quantisation="none", temperature=0.0, top_p=1.0,
            top_k=-1, repetition_penalty=1.0, max_new_tokens=24, stop_sequences=[],
            seed=1, rendered_prompt="p", batch_size=1, sample_index=0,
            timestamp=dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc),
        ),
    )


def test_every_summary_key_the_driver_prints_exists_in_the_module():
    """Pins the module/driver contract that actually broke.

    Greps the driver for `summary['...']` and `report[...]` subscripts and
    asserts each key is produced by `decompose`, so a rename cannot pass lint,
    pass the unit tests, and still fail at runtime.
    """
    import re as _re

    c = _constraint(["1972", "1961", "1981"], "1972")
    p = _probe(c, "1972")
    _, summary = decompose(
        [_raw(c, p, " 1975")], {c.constraint_id: c}, {p.probe_id: p}
    )
    src = (project_root() / "scripts" / "analysis" / "classify_invalid.py").read_text()
    used = set(_re.findall(r"summary\[[\"']([^\"']+)[\"']\]", src))
    assert used, "the grep found nothing; this test would pass vacuously"
    missing = sorted(used - set(summary))
    assert not missing, f"the driver reads summary keys that decompose() does not emit: {missing}"
