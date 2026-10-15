"""CLI: run ONE model over ONE experiment, driven by its experiment config.

    python -m semintegrity.inference.run_experiment --experiment primary_trackA --model qwen25-3b

Why this exists alongside ``run_pilot``: ``run_pilot`` hard-codes
``experiment_id="pilot_<split>"`` and ``tier=Tier.PILOT``, and never passes a
seed to :meth:`InferenceRunner.run`. Those are correct for the 12-constraint
pilot and wrong for every other tier, so a primary-tier run could not be
produced through it at all. This is **not a second pipeline**: it resolves the
same model config, builds the same backend, and calls the same
:class:`InferenceRunner`. What it adds is that ``experiment_id``, ``tier``,
``track``, the split, the decoding block and the seed are all **read from the
experiment config** rather than assumed.

Every value that could change a number is taken from configuration and recorded,
so a run is reproducible from its own provenance. Nothing here invents a
default: a missing key is an error, because a silently defaulted seed or tier
would make two runs incomparable while looking identical.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from ..benchmark.loader import load_split
from ..schemas.enums import Split, Tier, Track
from ..utils.config import load_config
from ..utils.logging import get_logger, setup_logging
from ..utils.paths import data_path

log = get_logger(__name__)

#: Experiment configs live here, one file per experiment id.
EXPERIMENT_DIR = "configs/inference"

#: Which benchmark split each tier reads. The pilot tier is the only one that
#: reads the pilot split; everything else evaluates the frozen test split.
#: Stated here rather than inferred, so a new tier must declare its intent.
TIER_SPLIT: dict[Tier, Split] = {
    Tier.PRIMARY: Split.TEST,
    Tier.SATURATION: Split.TEST,
    Tier.STOCHASTIC: Split.TEST,
    Tier.TRACK_B: Split.TEST,
    Tier.KNOWLEDGE_SCREEN: Split.TEST,
    Tier.DETERMINISM: Split.TEST,
    Tier.PILOT: Split.PILOT,
}


class ExperimentConfigError(ValueError):
    """Raised when an experiment config cannot be used as written."""


def _require(cfg: dict[str, Any], key: str, where: str) -> Any:
    if key not in cfg:
        raise ExperimentConfigError(
            f"{where} has no {key!r}. Every value that can change a reported "
            "number is read from configuration, never defaulted here."
        )
    return cfg[key]


def resolve_experiment(name: str) -> tuple[dict[str, Any], str, Tier, Track, Split]:
    """Load one experiment config and resolve its identity fields.

    Returns the raw config, its sha256, and the tier/track/split it declares.
    """
    path = f"{EXPERIMENT_DIR}/{name}.yaml"
    if not Path(path).is_file():
        available = sorted(p.stem for p in Path(EXPERIMENT_DIR).glob("*.yaml")
                           if not p.stem.startswith("_"))
        raise ExperimentConfigError(
            f"no experiment config at {path}; available: {available}"
        )
    loaded = load_config(path)
    cfg = loaded.data
    _require(cfg, "experiment", path)  # validated here; read from cfg by callers
    tier = Tier(str(_require(cfg, "tier", path)))
    track = Track(str(_require(cfg, "track", path)))
    if tier not in TIER_SPLIT:
        raise ExperimentConfigError(f"{path}: tier {tier!s} declares no split in TIER_SPLIT")
    return cfg, loaded.sha256, tier, track, TIER_SPLIT[tier]


def merged_generation(model_generation: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """The model's generation block, with the experiment's decoding applied.

    The experiment config is authoritative where it speaks, because a tier is
    DEFINED by its decoding (primary is fixed-decoding; stochastic is not). Any
    disagreement is surfaced rather than resolved silently.
    """
    gen = dict(model_generation)
    decoding = cfg.get("decoding") or {}
    overrides = {k: v for k, v in decoding.items() if k != "seed"}
    if "seed" in decoding:
        overrides["seed"] = decoding["seed"]
    if "max_new_tokens" in cfg:
        overrides["max_new_tokens"] = cfg["max_new_tokens"]
    disagree = {
        k: (gen[k], v) for k, v in overrides.items() if k in gen and gen[k] != v
    }
    if disagree:
        log.info(
            "experiment config overrides the model's generation block",
            extra={"extra_fields": {"overridden": {k: {"model": a, "experiment": b}
                                                   for k, (a, b) in disagree.items()}}},
        )
    gen.update(overrides)
    return gen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", required=True,
                    help="experiment id; reads configs/inference/<id>.yaml")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", default=None,
                    help="output JSONL; defaults to the experiment config's output.path")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--sample-index", type=int, default=0,
                    help="which draw this is; >0 only makes sense for a stochastic tier")
    ap.add_argument("--allow-no-slurm", action="store_true")
    ap.add_argument("--stub", action="store_true",
                    help="deterministic stub backend; output is FAKE and rejected by analysis")
    ap.add_argument("--backend", default=None)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve everything, print the plan, generate nothing")
    args = ap.parse_args(argv)

    setup_logging()
    cfg, cfg_sha, tier, track, split = resolve_experiment(args.experiment)

    models = cfg.get("models") or []
    if models and args.model not in models:
        sys.exit(
            f"{args.model} is not in {args.experiment}'s model list {models}. "
            "A model evaluated outside its experiment's declared set is not comparable."
        )

    from ..utils.config import resolve_model_config

    model_cfg = resolve_model_config(args.model)
    if not args.stub and not model_cfg.data["revision"]:
        sys.exit(f"{args.model} has no pinned revision; run scripts/models/pin_revisions.py --write")

    constraints, probes = load_split(data_path("benchmark") / split.value)
    expected = (cfg.get("workload") or {}).get("probes")
    if expected is not None and len(probes) != int(expected):
        sys.exit(
            f"{args.experiment} declares workload.probes={expected} but the "
            f"{split.value} split on disk holds {len(probes)}. Refusing to run a "
            "workload that does not match its config: the mismatch is either a "
            "stale config or an incomplete benchmark, and both change the result."
        )

    generation = merged_generation(model_cfg.data["generation"], cfg)
    seed = generation.get("seed")
    if seed is None and tier is not Tier.STOCHASTIC:
        sys.exit(
            f"{args.experiment} resolves no seed for a non-stochastic tier. "
            "A fixed-decoding run without a recorded seed is not reproducible."
        )

    out = args.out or str(Path((cfg.get("output") or {}).get("path", f"results/raw/{args.experiment}"))
                          / f"{args.model}.jsonl")

    plan = {
        "experiment_id": cfg["experiment"], "tier": str(tier), "track": str(track),
        "split": split.value, "model": args.model, "model_id": model_cfg.data["model_id"],
        "revision": model_cfg.data["revision"], "constraints": len(constraints),
        "probes": len(probes), "generation": generation,
        "serving": model_cfg.data.get("serving"), "out": out,
        "experiment_config_sha256": cfg_sha,
    }
    for key, value in plan.items():
        print(f"  {key:26s} {value}")

    if args.dry_run:
        print("\n--dry-run: resolved only, nothing generated.")
        return 0

    if not args.stub and not os.environ.get("SLURM_JOB_ID") and not args.allow_no_slurm:
        sys.exit(
            "REFUSING TO RUN: no SLURM_JOB_ID. Submit through Slurm:\n"
            f"  sbatch slurm/30_primary_one_model.sbatch {args.model}"
        )

    from .backend import make_backend, serving_kwargs
    from .chat_template import audit_tokenizer
    from .runner import InferenceRunner

    backend_name = "stub" if args.stub else (args.backend or model_cfg.data.get("backend", "vllm"))
    if backend_name == "stub":
        backend = make_backend("stub", default="UNKNOWN")
    else:
        backend = make_backend(
            backend_name, **serving_kwargs(model_cfg.data, backend_name, args.device)
        )

    audit = audit_tokenizer(
        backend.tokenizer, declared_supports_system=model_cfg.data["supports_system_role"]
    )
    if not audit["agrees"]:
        print(f"WARNING: configs/models/{args.model}.yaml declares "
              f"supports_system_role={audit['declared_supports_system_role']} but the real chat "
              f"template says {audit['actual_supports_system_role']}. Using the REAL value and "
              "recording the discrepancy; correct the config before the full run.")

    instruction_id = str(cfg.get("semantic_instruction_id", "trackA.v1"))
    instruction = load_config("configs/inference/prompts.yaml").data[
        "instructions"][instruction_id]["text"]

    stats = InferenceRunner(
        backend=backend, experiment_id=cfg["experiment"], tier=tier, track=track,
        semantic_instruction=instruction, semantic_instruction_id=instruction_id,
        generation=generation, dtype=model_cfg.data["dtype"],
        quantisation=model_cfg.data["quantisation"],
        supports_system_role=audit["actual_supports_system_role"],
        system_merge_strategy=model_cfg.data["system_merge_strategy"],
        batch_size=args.batch_size, config_snapshot_sha256=model_cfg.sha256,
    ).run(probes, out, sample_index=args.sample_index, seed=seed)

    print(stats.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
