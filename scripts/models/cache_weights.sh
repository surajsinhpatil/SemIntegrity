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

# The D3 judges live nested in _judge.yaml (they are not roster models, and a
# roster file would break the readiness audit's model count). Address them as
# `judge:primary_judge`. JUDGE_ROLE is read by the python block below.
#
# D2's NLI checkpoint is addressed as `detector:d2`. It lives in
# configs/detectors/d2_nli.yaml, not the model roster, for the same reason the
# judge does not: adding it to configs/models/ would break the readiness
# audit's model count. Its keys differ from a model config's
# (`checkpoint_selection.selected` / `.revision` rather than `model_id` /
# `revision`), so DETECTOR_KEY tells the python blocks below to normalise.
JUDGE_ROLE=""
DETECTOR_KEY=""
if [[ "$MODEL" == judge:* ]]; then
  JUDGE_ROLE="${MODEL#judge:}"
  CFG="${ROOT}/configs/models/_judge.yaml"
elif [[ "$MODEL" == detector:* ]]; then
  DET="${MODEL#detector:}"
  case "$DET" in
    d2) CFG="${ROOT}/configs/detectors/d2_nli.yaml"; DETECTOR_KEY="checkpoint_selection" ;;
    *)  warn "unknown detector ${DET}; known: d2"; exit 2 ;;
  esac
else
  CFG="${ROOT}/configs/models/${MODEL}.yaml"
fi
[[ -f "$CFG" ]] || { warn "no config: ${CFG}"; exit 2; }

if [[ -n "${SLURM_JOB_ID:-}" ]]; then
  warn "Running inside Slurm job ${SLURM_JOB_ID}. Compute nodes have no network."
  warn "Run this on the login node."
  exit 2
fi

export HF_HOME="${ROOT}/hf_cache"
mkdir -p "$HF_HOME"

# --- download on a SHARED LOGIN NODE, politely and within its memory ---------
# Staging qwen25-14b aborted on 2026-10-15 with
#     memory allocation of 66713827 bytes failed
#     note: run with `RUST_BACKTRACE=1` ...  Aborted (core dumped)
# That is the Rust `hf_xet` transfer backend, not a quota problem: the default
# fetches up to 8 shards CONCURRENTLY and each buffers in memory. Eight 4 GB
# shards at once exhausted the login node, which is shared with everyone.
# The 3B and 7B happened to be small enough to survive it; the 14B was not.
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"   # plain HTTP, no Rust allocator
export HF_HUB_ENABLE_HF_TRANSFER=0                      # no parallel-chunk accelerator
# Serial-ish downloads are slower but bounded, and kinder to a shared machine.
HF_MAX_WORKERS="${HF_MAX_WORKERS:-2}"

# --- free space BEFORE downloading, not after -------------------------------
# Jobs 13032/13033 (2026-10-08) died at preflight 2 with "no weight shards
# found": the cache held config.json and tokenizer_config.json but ZERO
# .safetensors. A download that runs out of space fails exactly that way --
# the small JSON files land, the multi-GB shards do not, and nothing says so
# because the old `du`/`quota` report ran only AFTER the attempt.
NEED_GB="$(JUDGE_ROLE="$JUDGE_ROLE" DETECTOR_KEY="$DETECTOR_KEY" python - "$CFG" <<'PY2'
import os, sys, yaml
cfg_path = sys.argv[1]
cfg = yaml.safe_load(open(cfg_path))
role = os.environ.get("JUDGE_ROLE", "")
if role:
    cfg = cfg.get(role, {})
detector_key = os.environ.get("DETECTOR_KEY", "")
if detector_key:
    block = cfg.get(detector_key) or {}
    cfg = {"weights_bf16_gb_estimate": block.get("weights_gb_estimate", 4)}
est = cfg.get("weights_bf16_gb_estimate")
# 30% margin: the HF cache stores a blob plus a snapshot symlink, and the
# estimate is the bf16 weight total, not the whole repo.
print(int(est * 1.3) if est else 0)
PY2
)"
# TWO limits, and on this cluster the SMALLER one is the user QUOTA, not the
# filesystem. Observed 2026-10-14: df reported 15T free on /nfs_home while
# `quota` showed 955G used of a 1000G hard limit -- about 45G of real headroom.
# A df-only check is blind to that and would wave through a download destined
# to fail, which is precisely how qwen25-7b/14b ended up with 0 weight shards.
DEV="$( { df -P "$HF_HOME" 2>/dev/null | awk 'NR==2 {print $1}'; } || true )"
DF_GB="$( { df -P -k "$HF_HOME" 2>/dev/null | awk 'NR==2 {printf "%d", $4/1048576}'; } || true )"
# `quota` prints 1K blocks: used=$2, soft=$3, hard=$4. -w keeps the filesystem
# on one line; some builds wrap it otherwise and the fields shift.
QUOTA_GB="$( { quota -w 2>/dev/null | awk -v d="$DEV" '$1==d && $4+0>0 {printf "%d", ($4-$2)/1048576; exit}'; } || true )"
AVAIL_GB="$DF_GB"
if [[ -n "$QUOTA_GB" ]]; then
  echo "  filesystem free: ${DF_GB:-?} GiB"
  echo "  quota headroom : ${QUOTA_GB} GiB  (the binding limit)"
  if [[ -z "$AVAIL_GB" ]] || (( QUOTA_GB < AVAIL_GB )); then
    AVAIL_GB="$QUOTA_GB"
  fi
fi
if [[ -n "$AVAIL_GB" && "$NEED_GB" -gt 0 ]]; then
  echo "  need (est+30%): ${NEED_GB} GiB"
  echo "  available     : ${AVAIL_GB} GiB"
  if (( AVAIL_GB < NEED_GB )); then
    warn "NOT ENOUGH SPACE for ${MODEL}: need ~${NEED_GB} GiB, have ${AVAIL_GB} GiB."
    warn "A download that runs out of space leaves the JSON files and silently"
    warn "drops every weight shard. Check what is using the quota, then evict:"
    warn "  quota -s"
    warn "  du -sh ${HF_HOME}/hub/models--*"
    warn "  du -sh \$HOME/* 2>/dev/null | sort -h | tail -15"
    warn "The quota is per USER across /nfs_home, not per project directory."
    exit 3
  fi
else
  warn "could not determine free space or size estimate; proceeding unchecked"
fi

say "Caching ${MODEL}"
HF_MAX_WORKERS="$HF_MAX_WORKERS" JUDGE_ROLE="$JUDGE_ROLE" DETECTOR_KEY="$DETECTOR_KEY" python - "$CFG" "$HF_HOME" "$CHECK_ONLY" <<'PY'
import os, re, sys, yaml
cfg_path, hf_home, check_only = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
cfg = yaml.safe_load(open(cfg_path))
role = os.environ.get("JUDGE_ROLE", "")
if role:
    if role not in cfg:
        sys.exit(f"no judge role {role!r} in {cfg_path}")
    cfg = cfg[role]

def _normalise(cfg, detector_key):
    """A detector config states its checkpoint under a different set of keys."""
    if not detector_key:
        return cfg
    block = cfg.get(detector_key) or {}
    if not block.get("selected"):
        sys.exit(f"{detector_key}.selected is empty in {cfg_path}")
    return {
        "model_id": block["selected"],
        "revision": block.get("revision"),
        "gated_on_hf": block.get("gated_on_hf", False),
        # A 435M fp32 classifier is ~1.8 GB; 4 GB with the cache's blob +
        # snapshot overhead is a safe floor for the quota preflight.
        "weights_bf16_gb_estimate": block.get("weights_gb_estimate", 4),
    }

cfg = _normalise(cfg, os.environ.get("DETECTOR_KEY", ""))
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
        # Bounded concurrency: see the HF_MAX_WORKERS note in the shell above.
        # snapshot_download RESUMES, so a re-run after a crash continues rather
        # than restarting the multi-GB shards.
        max_workers=int(os.environ.get("HF_MAX_WORKERS", "2")),
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

  # --- VERIFY, so that "staged successfully" is a checked claim -------------
  # This is the same offline check the Slurm preflight runs. Without it this
  # script could report success having fetched only metadata, which is exactly
  # what happened before jobs 13032/13033 burned two queue slots and 8 hours.
  # Exit status propagates: a half-populated cache fails HERE, on the login
  # node, where it is free to fix.
  say "Verifying the cache is usable offline"
  if ! python "${ROOT}/scripts/models/verify_cache.py" "$MODEL"; then
    warn "STAGING INCOMPLETE for ${MODEL} — do NOT submit a job."
    warn "Re-run this script; if it fails again, check space and quota."
    exit 4
  fi
  say "${MODEL} is staged AND verified usable offline"
fi
