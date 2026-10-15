"""The D3 driver's record-then-replay batching.

`D3Judge.judge_pair` generates ONE prompt at a time. With 28 pairs per
constraint and 120 constraints that is 3,360 sequential generations per model,
which wastes almost all of a GPU. `scripts/analysis/run_d3_judge.py` therefore
runs the judge twice over the same seeded RNG — once to record prompts, once to
replay real completions — so the generation itself can be batched.

That trick is only safe if `D3Judge` reproduces its prompts exactly under the
same seed. These tests pin that invariant, and pin that the replay REFUSES
rather than silently pairing a completion with the wrong prompt.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys

import pytest

from semintegrity.detectors.d3.judge import D3Judge
from semintegrity.schemas.enums import ConstraintClass, Domain, ResponseLabel
from semintegrity.schemas.response import CanonicalResponse
from semintegrity.utils.paths import p, project_root
from tests.fixtures.synthetic_benchmark import make_constraint

PROMPT = p("configs/detectors/d3_prompt.txt").read_text(encoding="utf-8")


def _load_driver():
    path = project_root() / "scripts" / "analysis" / "run_d3_judge.py"
    spec = importlib.util.spec_from_file_location("run_d3_judge", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_d3_judge"] = mod
    spec.loader.exec_module(mod)
    return mod


def _constraint():
    c = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1)
    return c.model_copy(update={
        "answer_space": ["Canberra", "Sydney", "Melbourne"], "gold_answer": "Canberra",
        "gold_proposition": "The capital city of Australia is Canberra.",
        "constraint_text": "A country has exactly one capital city.",
    })


def _resp(n: int, answer: str) -> CanonicalResponse:
    return CanonicalResponse(
        response_id=f"R-{n:012x}", constraint_id="K-C1-GEO-01",
        probe_id=f"K-C1-GEO-01-P0{n}", label=ResponseLabel.ANSWER,
        canonical_answer=answer, matched_alias=answer, candidates_found=[answer],
        canonicaliser_version="1.1", canonicaliser_sha256="0" * 64,
        canonicalised_at=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc),
    )


RESPONSES = [_resp(1, "Canberra"), _resp(2, "Sydney"), _resp(3, "Canberra")]


def test_recording_pass_captures_one_prompt_per_judgeable_pair():
    mod = _load_driver()
    rec = mod._Recorder("judge")
    out = D3Judge(generator=rec, prompt_template=PROMPT).judge_all_pairs(
        _constraint(), RESPONSES
    )
    assert len(out) == 3, "C(3,2) judgeable pairs"
    assert len(rec.prompts) == 3


def test_the_judge_reproduces_its_prompts_under_the_same_seed():
    """The whole batching scheme rests on this."""
    mod = _load_driver()
    first, second = mod._Recorder("j"), mod._Recorder("j")
    D3Judge(generator=first, prompt_template=PROMPT).judge_all_pairs(_constraint(), RESPONSES)
    D3Judge(generator=second, prompt_template=PROMPT).judge_all_pairs(_constraint(), RESPONSES)
    assert first.prompts == second.prompts


def test_replay_returns_completions_in_recorded_order():
    mod = _load_driver()
    rec = mod._Recorder("j")
    D3Judge(generator=rec, prompt_template=PROMPT).judge_all_pairs(_constraint(), RESPONSES)
    completions = [
        '{"label": "CONTRADICTION", "confidence": 0.9, "reason": "a"}',
        '{"label": "COMPATIBLE", "confidence": 0.8, "reason": "b"}',
        '{"label": "UNCLEAR", "confidence": 0.5, "reason": "c"}',
    ]
    replay = mod._Replayer("j", rec.prompts, completions)
    out = D3Judge(generator=replay, prompt_template=PROMPT).judge_all_pairs(
        _constraint(), RESPONSES
    )
    assert [j.label for j in out] == ["CONTRADICTION", "COMPATIBLE", "UNCLEAR"]
    assert all(j.parse_error is None for j in out)


def test_replay_refuses_a_prompt_that_does_not_match_the_recording():
    """A silent mismatch would attach a judgement to the wrong pair."""
    mod = _load_driver()
    replay = mod._Replayer("j", ["a prompt that will never be built"], ["{}"])
    with pytest.raises(RuntimeError, match="differs from the recorded one"):
        D3Judge(generator=replay, prompt_template=PROMPT).judge_all_pairs(
            _constraint(), RESPONSES
        )


def test_replay_refuses_to_run_past_the_end_of_the_recording():
    mod = _load_driver()
    rec = mod._Recorder("j")
    D3Judge(generator=rec, prompt_template=PROMPT).judge_all_pairs(_constraint(), RESPONSES)
    short = mod._Replayer("j", rec.prompts[:1], ["{}"])
    with pytest.raises(RuntimeError, match="only 1 were recorded"):
        D3Judge(generator=short, prompt_template=PROMPT).judge_all_pairs(
            _constraint(), RESPONSES
        )


def test_pairs_with_no_claim_are_skipped_not_judged():
    """An ABSTAIN has nothing to judge; it must not consume a generation."""
    mod = _load_driver()
    abstain = CanonicalResponse(
        response_id="R-00000000000f", constraint_id="K-C1-GEO-01",
        probe_id="K-C1-GEO-01-P09", label=ResponseLabel.ABSTAIN,
        canonical_answer=None, matched_alias=None, candidates_found=[],
        canonicaliser_version="1.1", canonicaliser_sha256="0" * 64,
        canonicalised_at=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc),
    )
    rec = mod._Recorder("j")
    out = D3Judge(generator=rec, prompt_template=PROMPT).judge_all_pairs(
        _constraint(), [_resp(1, "Canberra"), abstain]
    )
    assert out == []
    assert rec.prompts == [], "a non-judgeable pair must not reach the generator"


# --- archived row -> real D3Judgement (regression for job 15127) ---------
def test_archived_row_rebuilds_a_judgement_with_a_working_verdict():
    """`coverage` reads `j.verdict`, a PROPERTY derived from `label`.

    The driver originally fabricated objects with `type("J", (), row)()`, which
    have no such property. Job 15127 generated and archived all 2,325
    judgements and then died on the final summary line with
    `AttributeError: 'J' object has no attribute 'verdict'`.
    """
    mod = _load_driver()
    from semintegrity.detectors.d3.judge import coverage, parse_failure_rate
    from semintegrity.schemas.enums import Verdict

    rows = [
        {"pair_id": "p1", "probe_a": "a", "probe_b": "b", "presented_swapped": False,
         "label": "CONTRADICTION", "confidence": 0.9, "conflicting_span_a": None,
         "conflicting_span_b": None, "reason": "", "raw_output": "{}",
         "parse_error": None, "judge_model_id": "microsoft/phi-4"},
        {"pair_id": "p2", "probe_a": "a", "probe_b": "c", "presented_swapped": True,
         "label": "COMPATIBLE", "confidence": 0.8, "conflicting_span_a": None,
         "conflicting_span_b": None, "reason": "", "raw_output": "{}",
         "parse_error": None, "judge_model_id": "microsoft/phi-4"},
        {"pair_id": "p3", "probe_a": "b", "probe_b": "c", "presented_swapped": False,
         "label": None, "confidence": None, "conflicting_span_a": None,
         "conflicting_span_b": None, "reason": "", "raw_output": "not json",
         "parse_error": "boom", "judge_model_id": "microsoft/phi-4"},
    ]
    js = [mod._judgement_from_row(r) for r in rows]
    assert [j.verdict for j in js] == [
        Verdict.VIOLATION, Verdict.SATISFIED, Verdict.NOT_APPLICABLE
    ]
    # two of three decided, over four possible pairs
    assert coverage(js, 4) == pytest.approx(0.5)
    assert parse_failure_rate(js) == pytest.approx(1 / 3)


def test_summary_is_still_produced_when_every_pair_is_already_archived():
    """Resume must not skip the report.

    An earlier version returned early on an empty prompt list, so a summary
    that had failed to write could never be regenerated — exactly the state
    job 15127 left behind.
    """
    src = (project_root() / "scripts" / "analysis" / "run_d3_judge.py").read_text()
    early = src.index("all pairs already judged")
    summary = src.index('"coverage": coverage(')
    assert early < summary, "the no-op path must fall through to the summary"


def test_resume_counts_only_judgeable_pairs():
    """A constraint holding an abstention must still be able to reach 'done'.

    `_all_done` originally built ALL C(n,2) pair ids, but a pair where either
    response renders no claim is never judged and never archived — so any
    constraint with one abstention looked permanently pending. On the first
    real resume that was 85 of 120 constraints, and it would have reloaded a
    14B to re-judge work already on disk.
    """
    mod = _load_driver()
    from semintegrity.utils.ids import pair_id

    abstain = CanonicalResponse(
        response_id="R-00000000000f", constraint_id="K-C1-GEO-01",
        probe_id="K-C1-GEO-01-P09", label=ResponseLabel.ABSTAIN,
        canonical_answer=None, matched_alias=None, candidates_found=[],
        canonicaliser_version="1.1", canonicaliser_sha256="0" * 64,
        canonicalised_at=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc),
    )
    a, b = _resp(1, "Canberra"), _resp(2, "Sydney")
    responses = [a, b, abstain]
    # only the (a, b) pair is judgeable; the two abstain pairs never archive
    done = {pair_id(a.probe_id, b.probe_id)}
    assert mod._all_done(_constraint(), responses, done) is True


def test_resume_is_not_done_when_a_judgeable_pair_is_missing():
    mod = _load_driver()
    assert mod._all_done(_constraint(), RESPONSES, set()) is False


def test_summary_only_mode_can_never_load_a_model():
    """Rebuilding a report must not be able to start a 14B on a login node."""
    src = (project_root() / "scripts" / "analysis" / "run_d3_judge.py").read_text()
    branch = src.index("--summary-only: skipping")
    generate = src.index("completions, template_hash = _generate(")
    assert branch < generate, "the summary-only branch must precede any generation"
    assert "prompts, completions = [], []" in src


# --- §4.6 chat templating -------------------------------------------------
#
# Job 15127 judged 2,325 pairs for qwen25-3b and its archive contains rows with
# `raw_output: ''` and `parse_error: "no JSON object found in judge output"`,
# plus parsed rows whose output begins `- [Response]: {...}`. Both are the
# signature of an instruction-tuned model handed a BARE prompt: phi-4 ran as a
# completion model, continuing the document instead of answering. §4.6 requires
# each model's own official chat template, and the inference runner has always
# applied one; this driver did not. These tests pin the fix.


class _FakeBackend:
    """Records exactly what reached the backend, with a real chat template."""

    def __init__(self) -> None:
        from semintegrity.inference.backend import _StubTokenizer

        self.tokenizer = _StubTokenizer()
        self.seen: list[str] = []
        self.kwargs: dict = {}

    def generate(self, prompts, **kwargs):
        from semintegrity.inference.backend import Generation

        self.seen.extend(prompts)
        self.kwargs = kwargs
        return [Generation(text="{}", finish_reason="stop", n_generated_tokens=1)
                for _ in prompts]


def _generate_against_fake(monkeypatch, decoding):
    import semintegrity.inference.backend as backend_mod

    mod = _load_driver()
    fake = _FakeBackend()
    monkeypatch.setattr(backend_mod, "make_backend", lambda *a, **k: fake)
    monkeypatch.setenv("SLURM_JOB_ID", "99999")
    args = type("A", (), {"stub": False, "allow_no_slurm": False, "batch_size": 8})()
    jcfg = {"model_id": "microsoft/phi-4", "revision": "a" * 40, "serving": {}}
    completions, template_hash = mod._generate(["JUDGE THIS"], jcfg, decoding, args)
    return fake, completions, template_hash


def test_the_judge_prompt_is_rendered_through_the_chat_template(monkeypatch):
    """A bare prompt makes phi-4 a completion model. This is the 15127 defect."""
    fake, _, template_hash = _generate_against_fake(monkeypatch, {})

    assert len(fake.seen) == 1
    sent = fake.seen[0]
    assert sent != "JUDGE THIS", "the prompt reached the backend untemplated"
    assert "<|user|>" in sent and "<|assistant|>" in sent
    # The FROZEN prompt text survives byte-for-byte inside the rendered turn.
    assert "JUDGE THIS" in sent
    assert len(template_hash) == 64


def test_the_frozen_prompt_goes_in_as_exactly_one_user_turn(monkeypatch):
    """Splitting it into a system turn would change the frozen delivery."""
    fake, _, _ = _generate_against_fake(monkeypatch, {})
    assert fake.seen[0].count("<|user|>") == 1
    assert "<|system|>" not in fake.seen[0]


def test_decoding_comes_from_the_judge_config_not_from_literals(monkeypatch):
    """The configured seed was previously dropped, leaving a run unreproducible."""
    decoding = {"temperature": 0.0, "top_p": 1.0, "seed": 20250058, "max_new_tokens": 256}
    fake, _, _ = _generate_against_fake(monkeypatch, decoding)
    assert fake.kwargs["seed"] == 20250058
    assert fake.kwargs["max_new_tokens"] == 256
    assert fake.kwargs["temperature"] == 0.0


def test_the_configured_judge_decoding_block_actually_pins_a_seed():
    """If _judge.yaml stopped pinning one, the test above would pass vacuously."""
    from semintegrity.utils.config import load_config

    decoding = load_config("configs/models/_judge.yaml").data["protocol"]["decoding"]
    assert decoding["seed"] == 20250058
    assert decoding["temperature"] == 0.0


def test_a_pre_fix_archive_is_refused_rather_than_resumed(tmp_path):
    """Untemplated judgements are evidence about the harness, not the judge."""
    mod = _load_driver()
    archive = tmp_path / "a.jsonl"
    rows = [{"pair_id": "K-C1-GEO-01-P01xP02", "raw_output": ""}]
    with pytest.raises(SystemExit) as exc:
        mod._check_archive_rendering(archive, rows, allow=False)
    assert "REFUSING TO RESUME" in str(exc.value)
    assert "chat template" in str(exc.value)


def test_a_pre_fix_archive_may_still_be_summarised_to_quantify_it(tmp_path, capsys):
    """--summary-only generates nothing, so measuring the damage is allowed."""
    mod = _load_driver()
    rows = [{"pair_id": "K-C1-GEO-01-P01xP02", "raw_output": ""}]
    mod._check_archive_rendering(tmp_path / "a.jsonl", rows, allow=True)
    assert "WARNING" in capsys.readouterr().out


def test_a_templated_archive_resumes_normally(tmp_path):
    mod = _load_driver()
    rows = [{"pair_id": "x", mod.TEMPLATE_FIELD: "b" * 64}]
    mod._check_archive_rendering(tmp_path / "a.jsonl", rows, allow=False)  # no raise
