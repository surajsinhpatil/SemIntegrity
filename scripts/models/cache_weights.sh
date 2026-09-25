#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Download one model's weights to the project-local HuggingFace cache.
#
# LOGIN NODE ONLY. Compute nodes have no DNS (verified 2026-09-25), so every
# weight must be here before any job starts. §4.13: "Model weights are cached
# once from a non-GPU session rather than downloaded inside paid GPU time."
#
#   bash scripts/models/cache_weights.sh qwen25-3b
#   bash scripts/models/cache_weights.sh qwen25-3b --check     # size only
#
# Downloads at the EXACT pinned revision from configs/models/<name>.yaml.
# Refuses to run if the revision is unpinned, because "which weights produced
# this result" must be answerable.
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL="${1:-}"
CHECK_ONLY=0
[[ "${2:-}" == "--check" ]] && CHECK_ONLY=1

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!!  %s\033[0m\n' "$*" >&2; }

[[ -n "$MODEL" ]] || {
  echo "usage: $0 <model-short-name> [--check]" >&2
  echo "available:" >&2
  for f in "$ROOT"/configs/models/*.yaml; do
    b="$(basename "$f" .yaml)"; [[ "$b" == _* ]] || echo "  $b" >&2
  done
  exit 2
}

CFG="${ROOT}/configs/models/${MODEL}.yaml"
[[ -f "$CFG" ]] || { warn "no config: ${CFG}"; exit 2; }

if [[ -n "${SLURM_JOB_ID:-}" ]]; then
  warn "Running inside Slurm job ${SLURM_JOB_ID}. Compute nodes have no network."
  warn "Run this on the login node."
  exit 2
fi

export HF_HOME="${ROOT}/hf_cache"
mkdir -p "$HF_HOME"

say "Caching ${MODEL}"
python - "$CFG" "$HF_HOME" "$CHECK_ONLY" <<'PY'
import os, re, sys, yaml
cfg_path, hf_home, check_only = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
cfg = yaml.safe_load(open(cfg_path))
model_id, revision, gated = cfg["model_id"], cfg.get("revision"), cfg.get("gated_on_hf", False)

print(f"  model     : {model_id}")
print(f"  revision  : {revision}")
print(f"  gated     : {gated}")
print(f"  cache     : {hf_home}")

if not revision or not re.fullmatch(r"[0-9a-f]{40}", str(revision)):
    sys.exit(
        f"\nREFUSING: {model_id} has no pinned 40-hex revision (got {revision!r}).\n"
        "§4.5 requires pinned open-weight revisions so that 'which weights produced\n"
        "this result' is answerable. Run: python scripts/models/pin_revisions.py --write"
    )

token = os.environ.get("HF_TOKEN")
if gated and not token:
    print("\n  NOTE: this model is GATED. Accept its licence on huggingface.co with your\n"
          "  own account, create a read token, then `export HF_TOKEN=...` before re-running.\n"
          "  The token is read from the environment and never written to any file.")

from huggingface_hub import snapshot_download
from huggingface_hub.utils import GatedRepoError

try:
    info_files = None
    if check_only:
        from huggingface_hub import HfApi
        files = HfApi().model_info(model_id, revision=revision, files_metadata=True, token=token).siblings
        total = sum(f.size or 0 for f in files)
        print(f"\n  {len(files)} files, {total / 2**30:.1f} GiB")
        sys.exit(0)

    path = snapshot_download(
        model_id, revision=revision, token=token,
        allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt", "*.py"],
    )
    print(f"\n  downloaded to: {path}")
except GatedRepoError:
    sys.exit(f"\nGATED: accept the licence for {model_id} on huggingface.co, then set HF_TOKEN.")
PY

if [[ $CHECK_ONLY -eq 0 ]]; then
  say "Cache size"
  du -sh "$HF_HOME"
  say "Quota after download"
  quota -s 2>/dev/null | tail -2 || df -h "$ROOT" | tail -1
fi
