"""CLI: run one model over one benchmark split.

    python -m semintegrity.inference.run_pilot --model qwen25-3b --split pilot --out results/raw/pilot/qwen25-3b.jsonl

Resumable and append-only. Refuses to run outside a Slurm allocation.
"""

from __future__ import annotations

import argparse
import os
import sys

from ..benchmark.loader import load_split
from ..schemas.enums import Split, Tier, Track
from ..utils.config import load_config, resolve_model_config
from ..utils.logging import setup_logging
from ..utils.paths import data_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--split", default="pilot", choices=[s.value for s in Split])
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--allow-no-slurm", action="store_true")
    ap.add_argument("--stub", action="store_true",
                    help="deterministic stub backend; output is FAKE and rejected by analysis")
    ap.add_argument("--backend", default=None, help="override configs/models/_defaults.yaml")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    args = ap.parse_args(argv)

    setup_logging()
    if not args.stub and not os.environ.get("SLURM_JOB_ID") and not args.allow_no_slurm:
        sys.exit(
            "REFUSING TO RUN: no SLURM_JOB_ID. Submit through Slurm:\n"
            "  sbatch --partition=<p> --gres=gpu:1 slurm/20_pilot_one_model.sbatch"
        )

    cfg = resolve_model_config(args.model)
    if not args.stub and not cfg.data["revision"]:
        sys.exit(f"{args.model} has no pinned revision; run scripts/models/pin_revisions.py --write")

    constraints, probes = load_split(data_path("benchmark") / args.split)
    print(f"{len(constraints)} constraints, {len(probes)} probes -> {cfg.data['model_id']}")

    instruction = load_config("configs/inference/prompts.yaml").data["instructions"]["trackA.v1"]["text"]

    from .backend import make_backend

    backend_name = "stub" if args.stub else (args.backend or cfg.data.get("backend", "vllm"))
    if backend_name == "stub":
        backend = make_backend("stub", default="UNKNOWN")
    else:
        backend = make_backend(
            backend_name,
            model_id=cfg.data["model_id"], revision=cfg.data["revision"],
            dtype=cfg.data["dtype"], max_model_len=cfg.data["serving"]["max_model_len"],
            seed=cfg.data["generation"]["seed"],
            **({"device": args.device} if backend_name == "transformers" else {}),
        )

    from .chat_template import audit_tokenizer
    from .runner import InferenceRunner

    audit = audit_tokenizer(backend.tokenizer,
                            declared_supports_system=cfg.data["supports_system_role"])
    if not audit["agrees"]:
        print(f"WARNING: configs/models/{args.model}.yaml declares "
              f"supports_system_role={audit['declared_supports_system_role']} but the real chat "
              f"template says {audit['actual_supports_system_role']}. Using the REAL value and "
              "recording the discrepancy; correct the config before the full run.")

    stats = InferenceRunner(
        backend=backend, experiment_id=f"pilot_{args.split}", tier=Tier.PILOT, track=Track.A,
        semantic_instruction=instruction, semantic_instruction_id="trackA.v1",
        generation=cfg.data["generation"], dtype=cfg.data["dtype"],
        quantisation=cfg.data["quantisation"],
        supports_system_role=audit["actual_supports_system_role"],
        system_merge_strategy=cfg.data["system_merge_strategy"],
        batch_size=args.batch_size, config_snapshot_sha256=cfg.sha256,
    ).run(probes, args.out)

    print(stats.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
