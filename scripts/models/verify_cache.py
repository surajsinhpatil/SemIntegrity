#!/usr/bin/env python3
"""Verify a model's weights are usable from the LOCAL cache, with no network.

    python scripts/models/verify_cache.py qwen25-3b

Why this exists rather than ``cache_weights.sh --check``: that path calls
``HfApi().model_info()``, which is a request to huggingface.co. It answers "how
big is this repo upstream", not "can this node load it offline" — and on a
compute node with ``HF_HUB_OFFLINE=1`` and no route to the internet it cannot
answer at all.

This script forces ``HF_HUB_OFFLINE=1`` and ``local_files_only=True`` before
touching the hub, so it is structurally incapable of downloading anything. If
the weights are not cached it says so and exits non-zero; it never fetches.

Exit status: 0 if the pinned revision is fully present locally, 1 otherwise.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Set BEFORE huggingface_hub is imported: the library reads these at import time.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

#: Files a vLLM load actually needs. Weights may be sharded or a single file.
REQUIRED = ("config.json", "tokenizer_config.json")
WEIGHT_SUFFIXES = (".safetensors", ".bin")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    name = sys.argv[1]

    cfg_path = ROOT / "configs" / "models" / f"{name}.yaml"
    if not cfg_path.is_file():
        print(f"no such model config: {cfg_path}", file=sys.stderr)
        return 1
    cfg = yaml.safe_load(cfg_path.read_text())
    model_id = cfg["model_id"]
    revision = str(cfg.get("revision") or "")

    hf_home = os.environ.get("HF_HOME", "")
    print("=" * 78)
    print(f"LOCAL CACHE CHECK — {name}")
    print("=" * 78)
    print(f"  model_id      : {model_id}")
    print(f"  revision      : {revision or '<UNPINNED>'}")
    print(f"  HF_HOME       : {hf_home or '<unset — the cache will not be where jobs expect it>'}")
    print(f"  HF_HUB_OFFLINE: {os.environ['HF_HUB_OFFLINE']}  (forced by this script)")

    if len(revision) != 40:
        print("\n  REFUSING: §4.5 requires a pinned 40-hex revision. "
              "'Which weights produced this result' must be answerable.")
        return 1
    if not hf_home:
        print("\n  WARNING: HF_HOME is unset in this shell. slurm/templates/_common.sh")
        print("  sets it to ${work_dir}/hf_cache inside a job, so a check run on the")
        print("  login node without it may look at a different cache than the job will.")

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        print(f"\n  huggingface_hub not importable: {exc}")
        return 1

    try:
        path = Path(
            snapshot_download(model_id, revision=revision, local_files_only=True)
        )
    except Exception as exc:
        print(f"\n  NOT USABLE OFFLINE: {type(exc).__name__}")
        print(f"  {exc}")
        print("\n  The pinned revision is not fully present in this cache.")
        print("  Populate it from a NON-GPU session (never inside paid GPU time):")
        print(f"      bash scripts/models/cache_weights.sh {name}")
        return 1

    print(f"\n  resolved to   : {path}")
    files = sorted(p for p in path.rglob("*") if p.is_file() or p.is_symlink())
    weights = [p for p in files if p.suffix in WEIGHT_SUFFIXES]
    missing = [r for r in REQUIRED if not (path / r).exists()]

    total = 0
    for p in weights:
        try:
            total += p.stat().st_size  # follows symlinks into the blob store
        except OSError:
            print(f"  BROKEN LINK   : {p.name}")
            missing.append(p.name)

    print(f"  files         : {len(files)}")
    print(f"  weight shards : {len(weights)}  ({total / 2**30:.2f} GiB)")
    for r in REQUIRED:
        print(f"  {r:22s}: {'present' if (path / r).exists() else 'MISSING'}")

    if missing or not weights:
        print(f"\n  INCOMPLETE: {missing or 'no weight shards found'}")
        print("  Do not spend a GPU on this. Re-cache from a non-GPU session.")
        return 1

    print("\n  USABLE OFFLINE — the pinned revision is fully cached locally.")
    print("  Nothing was downloaded: HF_HUB_OFFLINE=1 and local_files_only=True.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
