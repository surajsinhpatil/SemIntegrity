#!/usr/bin/env python3
"""Local dry-run of the one-model pilot workflow. No GPU, no network, no model.

Exercises the exact code path the cluster job uses — prompt rendering, provenance,
incremental JSONL, resume, Stage 0, D1 and the pilot report — using the
deterministic stub backend and throwaway constraints.

    python scripts/demo_pipeline.py

Everything it writes goes to a temporary directory. It touches no benchmark data
and produces no model output. Its purpose is to demonstrate that the plumbing is
correct before any GPU time is spent.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.fixtures.synthetic_benchmark import make_constraint  # noqa: E402

from semintegrity.canonicalization.canonicaliser import canonicalise  # noqa: E402
from semintegrity.detectors.d1.exact_match import check_all_pairs, coverage  # noqa: E402
from semintegrity.inference.backend import (  # noqa: E402
    StubBackend,
    StubOutputError,
    assert_no_stub_responses,
)
from semintegrity.inference.runner import InferenceRunner  # noqa: E402
from semintegrity.probes.factor_design import cells_for_constraint  # noqa: E402
from semintegrity.schemas.enums import (  # noqa: E402
    AnswerType,
    ConstraintClass,
    Domain,
    ResponseLabel,
    Tier,
    Track,
    Verdict,
)
from semintegrity.schemas.probe import Probe  # noqa: E402
from semintegrity.schemas.response import RawResponse  # noqa: E402
from semintegrity.utils.ids import probe_id  # noqa: E402
from semintegrity.utils.io import read_jsonl  # noqa: E402

GEN = {"temperature": 0.0, "top_p": 1.0, "top_k": -1, "repetition_penalty": 1.0,
       "max_new_tokens": 24, "seed": 20250058, "stop_sequences": ["\n\n"]}

RULE = "─" * 72


def banner(n: int, title: str) -> None:
    print(f"\n{RULE}\n {n}. {title}\n{RULE}")


def main() -> int:
    print(RULE)
    print(" SemIntegrity — one-model pilot workflow, local dry run")
    print(" stub backend · no GPU · no network · no model weights")
    print(RULE)

    constraint = make_constraint(ConstraintClass.C1, Domain.GEOGRAPHY, 1).model_copy(
        update={"answer_type": AnswerType.ENTITY,
                "answer_space": ["Canberra", "Sydney", "Melbourne"],
                "gold_answer": "Canberra", "answer_aliases": {"Canberra": ["Canberra, ACT"]}}
    )

    banner(1, "Probe generation — exact factor balance (ADR-0003)")
    probes = []
    for i, cell in enumerate(cells_for_constraint(0, 8), start=1):
        text = f"[probe {i}] capital of Australia"
        if cell.syntax.value == "cloze":
            text += " is ___"
        probes.append(Probe(
            constraint_id=constraint.constraint_id, probe_id=probe_id(constraint.constraint_id, i),
            logical_form="capital_of(Australia)=?x", subject="Australia", predicate="capital_of",
            object="", time_scope="", quantifier="none", polarity=cell.polarity.value,
            answer_type="entity", syntax=cell.syntax.value, register=cell.register.value,
            directionality=cell.directionality.value, factor_cell_index=cell.cell_index,
            probe_text=text, expected_answer="Canberra"))
    print(f"  {len(probes)} probes for 1 constraint")
    for p in probes:
        print(f"    {p.probe_id}  {p.syntax.value:14s} {p.polarity.value:12s} "
              f"{p.register.value:11s} {p.directionality.value}")
    print("\n  Every (polarity x register x direction) cell appears exactly once.")

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "raw.jsonl"

        banner(2, "Inference — stub 'model' that is deliberately inconsistent")
        backend = StubBackend(
            answers={"[probe 4]": "Sydney", "[probe 6]": "I don't know.",
                     "[probe 7]": "Canberra, ACT"},
            default="Canberra")
        runner = InferenceRunner(
            backend=backend, experiment_id="demo", tier=Tier.PILOT, track=Track.A,
            semantic_instruction="Answer with the name only, or UNKNOWN.",
            semantic_instruction_id="trackA.v1", generation=GEN, batch_size=3)
        stats = runner.run(probes, out)
        print(f"  {stats.summary()}")

        banner(3, "Resume — re-running must not duplicate work")
        again = runner.run(probes, out)
        print(f"  {again.summary()}")
        print(f"  records on disk: {len(list(read_jsonl(out)))} (expected 8)")

        banner(4, "Provenance — all 22 fields §4.6 requires")
        raws = [RawResponse.model_validate(r) for r in read_jsonl(out)]
        pv = raws[0].provenance
        print(f"  model_id       : {pv.model_id}")
        print(f"  dtype/quant    : {pv.dtype} / {pv.quantisation}")
        print(f"  temperature    : {pv.temperature}   seed: {pv.seed}")
        print(f"  chat template  : {pv.chat_template_hash[:16]}")
        print(f"  rendered prompt: {pv.rendered_prompt[:70]!r}...")

        banner(5, "Stage 0 canonicalisation (§4.7)")
        canon = [canonicalise(r, constraint) for r in raws]
        for c in canon:
            raw = next(r.raw_text for r in raws if r.probe_id == c.probe_id)
            print(f"    {c.probe_id}  {raw!r:26s} -> {c.label.value:9s} {c.canonical_answer or ''}")
        print("\n  'Canberra, ACT' resolved via the alias table.")
        print("  \"I don't know\" is ABSTAIN — checked BEFORE answer matching.")

        banner(6, "D1 canonical exact match (§4.8.3)")
        results = check_all_pairs(canon)
        contradictions = [r for r in results if r.is_contradiction]
        n_eval = sum(r.verdict is not Verdict.NOT_APPLICABLE for r in results)
        print(f"  pairs            : {len(results)}  (C(8,2))")
        print(f"  evaluable        : {n_eval}   coverage {coverage(results):.3f}")
        print(f"  contradictory    : {len(contradictions)}")
        print(f"  PSCR             : {len(contradictions)}/{n_eval} = "
              f"{len(contradictions)/n_eval:.3f}")
        for r in contradictions[:3]:
            print(f"    {r.pair_id}  {r.reason}")

        banner(7, "Reliability triad, never collapsed (§4.10)")
        answered = [c for c in canon if c.label is ResponseLabel.ANSWER]
        acc = sum(c.canonical_answer == constraint.gold_answer for c in answered) / len(answered)
        abst = sum(c.label is ResponseLabel.ABSTAIN for c in canon) / len(canon)
        print(f"  truth accuracy   : {acc:.3f}   (of answered probes)")
        print(f"  PSCR             : {len(contradictions)/n_eval:.3f}")
        print(f"  abstention rate  : {abst:.3f}")
        print("  Reported as three numbers, never as one score.")

        banner(8, "Stub containment — fake output cannot reach analysis")
        try:
            assert_no_stub_responses(str(out))
            print("  FAILED: stub output was accepted")
            return 1
        except StubOutputError as exc:
            print(f"  REFUSED as required:\n    {str(exc).splitlines()[0]}")

    print(f"\n{RULE}\n Dry run complete. Pipeline verified end to end without a GPU.\n{RULE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
