"""One-model smoke test (Phase 3 escalation step 1).

The smallest real inference that exercises every part of the path a full run
uses: config resolution, weight loading at a pinned revision, the model's own
chat template, generation, complete provenance, incremental JSONL, resume, then
Stage 0 and D1.

    python -m semintegrity.inference.smoke --model qwen25-3b --out results/raw/_smoke/run.jsonl

Refuses to run on a login node: constructing a vLLM backend outside a Slurm
allocation is exactly the mistake the cluster rules forbid.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ..schemas.enums import Tier, Track
from ..utils.config import load_config, resolve_model_config
from ..utils.logging import get_logger, setup_logging

log = get_logger(__name__)

#: Fixed, content-free probes. They exercise the *path*, not the benchmark, and
#: deliberately use no benchmark content so the smoke test can run before any
#: constraint is authored.
SMOKE_PROMPTS: tuple[str, ...] = (
    "What is the capital of France?",
    "Is Paris the capital of France?",
    "The capital of France is ___.",
    "What is the capital of Japan?",
    "Is Tokyo the capital of Japan?",
    "What is the chemical symbol for gold?",
    "In which year did the Apollo 11 Moon landing occur?",
    "What is the largest planet in the Solar System?",
)


def _require_allocation(force: bool) -> None:
    if os.environ.get("SLURM_JOB_ID") or force:
        return
    sys.exit(
        "REFUSING TO RUN: no SLURM_JOB_ID in the environment.\n\n"
        "This loads model weights onto a GPU and must be submitted through Slurm.\n"
        "  sbatch slurm/10_smoke_inference.sbatch\n\n"
        "Pass --allow-no-slurm only inside a genuine interactive allocation (srun --pty)."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen25-3b", help="short name from configs/models/")
    parser.add_argument("--n-prompts", type=int, default=len(SMOKE_PROMPTS))
    parser.add_argument("--out", required=True, help="JSONL output path (append-only)")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--allow-no-slurm", action="store_true")
    parser.add_argument(
        "--stub", action="store_true",
        help="use the deterministic stub backend (pipeline test only; output is NOT model output)",
    )
    parser.add_argument("--backend", default=None, help="override configs/models/_defaults.yaml")
    args = parser.parse_args(argv)

    setup_logging()
    if not args.stub:
        _require_allocation(args.allow_no_slurm)

    cfg = resolve_model_config(args.model)
    prompts_cfg = load_config("configs/inference/prompts.yaml").data
    instruction = prompts_cfg["instructions"]["trackA.v1"]["text"]

    print("=" * 70)
    print(f"SemIntegrity smoke test — {cfg.data['model_id']}")
    print(f"  revision   : {cfg.data['revision'] or 'UNPINNED'}")
    print(f"  dtype      : {cfg.data['dtype']}  quantisation: {cfg.data['quantisation']}")
    print(f"  system role: {cfg.data['supports_system_role']}"
          f"  merge: {cfg.data['system_merge_strategy']}")
    from .backend import make_backend

    backend_name = "stub" if args.stub else (args.backend or cfg.data.get("backend", "transformers"))
    print(f"  backend    : {'STUB (fake output)' if args.stub else backend_name}")
    print("=" * 70)

    if backend_name == "stub":
        backend = make_backend("stub", default="Paris")
    else:
        backend = make_backend(
            backend_name,
            model_id=cfg.data["model_id"],
            revision=cfg.data["revision"],
            dtype=cfg.data["dtype"],
            max_model_len=cfg.data["serving"]["max_model_len"],
            seed=cfg.data["generation"]["seed"],
        )

    # Verify the declared system-role support against the real chat template.
    from .chat_template import audit_tokenizer

    audit = audit_tokenizer(
        backend.tokenizer, declared_supports_system=cfg.data["supports_system_role"]
    )
    print(f"\nchat template hash : {audit['chat_template_hash'][:16]}")
    print(f"system role declared={audit['declared_supports_system_role']} "
          f"actual={audit['actual_supports_system_role']} "
          f"agrees={'YES' if audit['agrees'] else 'NO — config must be corrected'}")

    probes = _smoke_probes(args.n_prompts)
    from .runner import InferenceRunner

    runner = InferenceRunner(
        backend=backend,
        experiment_id="smoke",
        tier=Tier.PILOT,
        track=Track.A,
        semantic_instruction=instruction,
        semantic_instruction_id="trackA.v1",
        generation=cfg.data["generation"],
        dtype=cfg.data["dtype"],
        quantisation=cfg.data["quantisation"],
        supports_system_role=audit["actual_supports_system_role"],
        system_merge_strategy=cfg.data["system_merge_strategy"],
        batch_size=args.batch_size,
        config_snapshot_sha256=cfg.sha256,
    )
    stats = runner.run(probes, args.out)

    print(f"\n{stats.summary()}")
    print(f"written to: {args.out}")

    from ..utils.io import read_jsonl

    records = list(read_jsonl(args.out))
    print(f"\n--- responses ({len(records)}) ---")
    for rec in records:
        print(f"  {rec['probe_id']:24s} -> {rec['raw_text']!r}")

    print("\n--- provenance completeness ---")
    from ..schemas.response import REQUIRED_PROVENANCE_FIELDS

    prov = records[0]["provenance"]
    missing = [f for f in REQUIRED_PROVENANCE_FIELDS if f not in prov or prov[f] in (None, "")]
    print(f"  {len(REQUIRED_PROVENANCE_FIELDS) - len(missing)}/{len(REQUIRED_PROVENANCE_FIELDS)}"
          f" fields populated" + (f"; MISSING {missing}" if missing else ""))
    print(f"  rendered_prompt (first 200 chars):\n    {prov['rendered_prompt'][:200]!r}")

    manifest = Path(args.out).with_suffix(".manifest.json")
    if not manifest.exists():
        manifest.write_text(json.dumps({
            "experiment_id": "smoke",
            "model_short_name": args.model,
            "model_id": cfg.data["model_id"],
            "revision": cfg.data["revision"],
            "config_sha256": cfg.sha256,
            "chat_template_audit": {k: v for k, v in audit.items() if k != "rendered_sample"},
            "n_responses": len(records),
            "stub_backend": bool(args.stub),
        }, indent=2))
        print(f"\nmanifest: {manifest}")

    if args.stub:
        print("\nWARNING: --stub was used. This output is FAKE and is rejected by analysis.")
    return 0 if not missing else 1


def _smoke_probes(n: int):
    from ..probes.factor_design import cells_for_constraint
    from ..schemas.probe import Probe
    from ..utils.ids import probe_id

    cid = "K-C1-GEO-99"  # reserved smoke id; never a benchmark constraint
    out = []
    for i, (text, cell) in enumerate(
        zip(SMOKE_PROMPTS[:n], cells_for_constraint(0, max(n, 1)), strict=False), start=1
    ):
        surface = text if cell.syntax.value != "cloze" else (
            text if "___" in text else text.rstrip("?.") + " ___"
        )
        out.append(
            Probe(
                constraint_id=cid, probe_id=probe_id(cid, i),
                logical_form=f"smoke_{i}", subject="smoke", predicate="smoke",
                object="", time_scope="", quantifier="none",
                polarity=cell.polarity.value, answer_type="entity",
                syntax=cell.syntax.value, register=cell.register.value,
                directionality=cell.directionality.value, factor_cell_index=cell.cell_index,
                probe_text=surface, expected_answer="smoke",
            )
        )
    return out


if __name__ == "__main__":
    raise SystemExit(main())
