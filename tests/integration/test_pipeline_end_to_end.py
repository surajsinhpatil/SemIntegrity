"""End-to-end pipeline on the stub backend: probes -> generation -> Stage 0 -> D1.

Proves the plumbing before a single GPU-hour is spent, and proves the stub's
containment: fake output must never be admissible to analysis.
"""

import pytest

from semintegrity.canonicalization.canonicaliser import canonicalise
from semintegrity.detectors.d1.exact_match import check_all_pairs, coverage
from semintegrity.inference.backend import (
    StubBackend,
    StubOutputError,
    assert_no_stub_responses,
)
from semintegrity.inference.runner import InferenceRunner
from semintegrity.probes.factor_design import cells_for_constraint
from semintegrity.schemas.constraint import Constraint
from semintegrity.schemas.enums import (
    AnswerType,
    ConstraintClass,
    Domain,
    ResponseLabel,
    Tier,
    Track,
)
from semintegrity.schemas.probe import Probe
from semintegrity.schemas.response import RawResponse
from semintegrity.utils.ids import probe_id
from semintegrity.utils.io import read_jsonl
from tests.fixtures.synthetic_benchmark import make_constraint

GENERATION = {
    "temperature": 0.0, "top_p": 1.0, "top_k": -1, "repetition_penalty": 1.0,
    "max_new_tokens": 24, "seed": 20250058, "stop_sequences": ["\n\n"],
}


@pytest.fixture
def constraint() -> Constraint:
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    return c.model_copy(
        update={
            "answer_type": AnswerType.ENTITY,
            "answer_space": ["Canberra", "Sydney", "Melbourne"],
            "gold_answer": "Canberra",
        }
    )


@pytest.fixture
def probes(constraint) -> list[Probe]:
    out = []
    for i, cell in enumerate(cells_for_constraint(0, 8), start=1):
        text = f"Q{i}: capital of Australia"
        if cell.syntax.value == "cloze":
            text += " is ___"
        out.append(
            Probe(
                constraint_id=constraint.constraint_id,
                probe_id=probe_id(constraint.constraint_id, i),
                logical_form="capital_of(Australia)=?x", subject="Australia",
                predicate="capital_of", object="", time_scope="", quantifier="none",
                polarity=cell.polarity.value, answer_type="entity",
                syntax=cell.syntax.value, register=cell.register.value,
                directionality=cell.directionality.value, factor_cell_index=cell.cell_index,
                probe_text=text, expected_answer="Canberra",
            )
        )
    return out


def _runner(backend) -> InferenceRunner:
    return InferenceRunner(
        backend=backend, experiment_id="pilot_test", tier=Tier.PILOT, track=Track.A,
        semantic_instruction="Answer with the name only.", semantic_instruction_id="trackA.v1",
        generation=GENERATION, batch_size=3,
    )


def test_full_pipeline(tmp_path, constraint, probes):
    # An inconsistent "model": most probes say Canberra, Q4 says Sydney, Q6 abstains.
    backend = StubBackend(
        answers={"Q4:": "Sydney", "Q6:": "I don't know."}, default="Canberra"
    )
    out = tmp_path / "raw.jsonl"

    stats = _runner(backend).run(probes, out)
    assert stats.generated == 8 and stats.skipped_existing == 0

    raws = [RawResponse.model_validate(r) for r in read_jsonl(out)]
    assert len(raws) == 8

    # Every one of the 22 provenance fields is populated.
    p = raws[0].provenance
    assert p.rendered_prompt and p.chat_template_hash and p.tokenizer_hash
    assert p.temperature == 0.0 and p.dtype == "bfloat16" and p.quantisation == "none"

    # Stage 0.
    by_probe = {p.probe_id: p for p in probes}
    canon = [canonicalise(r, constraint, by_probe[r.probe_id]) for r in raws]
    labels = [c.label for c in canon]
    assert labels.count(ResponseLabel.ANSWER) == 7
    assert labels.count(ResponseLabel.ABSTAIN) == 1

    # D1 over C(8,2) = 28 pairs.
    results = check_all_pairs(canon)
    assert len(results) == 28
    # The abstaining probe removes 7 pairs from the evaluable set.
    assert coverage(results) == pytest.approx(21 / 28)
    # Q4 (Sydney) contradicts each of the 6 other answering probes.
    assert sum(r.is_contradiction for r in results) == 6


def test_resume_skips_completed_work(tmp_path, probes):
    backend = StubBackend(default="Canberra")
    out = tmp_path / "raw.jsonl"

    first = _runner(backend).run(probes[:3], out)
    assert first.generated == 3

    second = _runner(backend).run(probes, out)
    assert second.skipped_existing == 3
    assert second.generated == 5
    assert len(list(read_jsonl(out))) == 8, "resume must not duplicate work"

    third = _runner(backend).run(probes, out)
    assert third.generated == 0 and third.skipped_existing == 8


def test_backend_failure_is_retried_once_then_recorded(tmp_path, probes):
    class Flaky:
        model_id, revision = "stub://flaky", "stub://none"
        tokenizer = StubBackend().tokenizer

        def generate(self, prompts, **kw):
            raise RuntimeError("simulated GPU OOM")

    stats = _runner(Flaky()).run(probes[:2], tmp_path / "raw.jsonl")
    assert stats.retried == 1 and stats.timed_out == 2

    raws = [RawResponse.model_validate(r) for r in read_jsonl(tmp_path / "raw.jsonl")]
    assert all(r.timed_out and r.retry_index == 1 for r in raws)

    # §4.7: a timeout, after its one retry, is FAILED.
    from semintegrity.canonicalization.canonicaliser import classify
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    probe = next(p for p in probes if p.probe_id == raws[0].probe_id)
    assert classify(raws[0], c, probe).label is ResponseLabel.FAILED


def test_stub_output_is_refused_by_analysis(tmp_path, probes):
    out = tmp_path / "raw.jsonl"
    _runner(StubBackend(default="Canberra")).run(probes[:2], out)
    with pytest.raises(StubOutputError, match="stub backend"):
        assert_no_stub_responses(str(out))


def test_rendered_prompt_carries_the_semantic_instruction(tmp_path, probes):
    out = tmp_path / "raw.jsonl"
    _runner(StubBackend(default="Canberra")).run(probes[:1], out)
    raw = RawResponse.model_validate(next(iter(read_jsonl(out))))
    assert "Answer with the name only." in raw.provenance.rendered_prompt
    assert probes[0].probe_text in raw.provenance.rendered_prompt
