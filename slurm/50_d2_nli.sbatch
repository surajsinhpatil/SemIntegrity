#!/bin/bash
#SBATCH --job-name=semint-d2
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=00:45:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#
# D2 — NLI contradiction SCORING (§4.8.4, ADR-0023 D6), one model per job.
#
#   MODEL=qwen25-3b sbatch --partition=gpu-short --exclude=csis.mn1,csis.cn2 \
#       --gres=gpu:1 slurm/50_d2_nli.sbatch
#
# D2 PRODUCES NO VERDICT. Its per-class threshold was calibrated on
# human-labelled dev data that does not exist; ADR-0023 D6 changed the estimand
# to a continuous score. The driver never calls check_pair, which still raises.
#
# The scorer is MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli,
# ~435M params in fp32 (~1.8 GB) — far smaller than the evaluated models. Stage
# it from the LOGIN node first:
#   bash scripts/models/cache_weights.sh detector:d2
#
# --time=00:45:00: up to 3,360 pairs x 2 directions = 6,720 forward passes of a
# 435M classifier at batch 32. Minutes, not hours; 45 min is headroom that still
# backfills. --mem=64G is the floor proven by five primary runs (see
# slurm/30_primary_one_model.sbatch); do NOT lower it on MaxRSS reasoning.

source "${SLURM_SUBMIT_DIR:-$PWD}/slurm/templates/_common.sh"
job_provenance

MODEL="${MODEL:-}"
if [[ -z "${MODEL}" ]]; then
  echo "ABORT: set MODEL (the EVALUATED model whose responses are scored)." >&2
  exit 2
fi

RAW="${RAW:-results/raw/primary_trackA/${MODEL}.jsonl}"
if [[ ! -s "${RAW}" ]]; then
  echo "ABORT: ${RAW} does not exist or is empty." >&2
  exit 2
fi
N_RAW="$(wc -l < "${RAW}")"
if [[ "${N_RAW}" -lt 960 ]]; then
  echo "ABORT: ${RAW} holds ${N_RAW} records, not 960." >&2
  exit 2
fi

echo "--- preflight 0/2: GPU is usable AND not already occupied ---"
# ConstrainDevices=no on this cluster: a co-tenant can hold the card Slurm
# assigned us and CUDA then fails at context creation. Same guard as D3.
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free --format=csv \
  2>/dev/null || echo "nvidia-smi unavailable"
python3 - <<'GPUCHECK' || exit 9
import sys
try:
    import torch
    if torch.cuda.device_count() < 1:
        sys.exit("torch reports 0 CUDA devices")
    free, total = torch.cuda.mem_get_info(0)
    gib = 1024 ** 3
    print(f"  memory free : {free / gib:.1f} GiB of {total / gib:.1f} GiB")
    # D2 is a 435M classifier, so the 80% floor the generative jobs need is
    # unnecessary here. 10% of an 80 GB card is ~8 GB, ample for fp32 + batch 32.
    if free / total < 0.10:
        sys.exit(f"ABORT: only {100 * free / total:.0f}% of the GPU is free")
except Exception as exc:
    sys.exit(f"CUDA INIT FAILED: {type(exc).__name__}: {exc}")
print("  GPU OK")
GPUCHECK

echo
echo "--- preflight: HOST memory (job 15158 died on a 16 MiB CPU allocation) ---"
# Slurm granting --mem=64G does not mean the node has it free: GrpTRES mem is
# per-ACCOUNT and shared, and this cluster does not fence co-tenants tightly.
# Reported, not gated: the scorers now load shards straight onto the GPU via
# device_map, so host RAM should barely be touched. If this number is small and
# a load still fails, the node is the problem, not the code.
echo "  SLURM_MEM_PER_NODE=${SLURM_MEM_PER_NODE:-unset} MB"
# NOT `free -g | head -2`: head exits early, free gets SIGPIPE, and
# `set -o pipefail` turns that into a fatal 141 — the trap _common.sh records
# and tests/unit/test_shell_scripts.py enforces. free -g output is short anyway.
free -g 2>/dev/null || echo "  free(1) unavailable"
awk '/MemAvailable/ {printf "  MemAvailable: %.1f GiB\n", $2/1048576}' /proc/meminfo 2>/dev/null || true

echo
echo "--- preflight 1/3: the NLI checkpoint is cached offline ---"
# Compute nodes have no network. Without this the job would try to download and
# fail deep inside transformers rather than here, with a clear message.
python3 scripts/models/verify_cache.py "detector:d2" || {
  echo "ABORT: D2's NLI checkpoint is not in the offline cache at HF_HOME=${HF_HOME}." >&2
  echo "       Stage it from the LOGIN node (~0.88 GB):" >&2
  echo "         bash scripts/models/cache_weights.sh detector:d2" >&2
  exit 4
}

echo
echo "--- preflight 2/3: count pairs, load nothing ---"
# Catches a bad raw file, an unresolvable split or a config/code disagreement
# about the pinned revision in seconds, before any weights load.
python3 scripts/detectors/run_d2_nli.py --raw "${RAW}" --dry-run || exit 5

echo
echo "--- D2: scoring ${MODEL} ---"
python3 scripts/detectors/run_d2_nli.py --raw "${RAW}" || exit 7

echo
echo "--- archive ---"
ls -la results/detectors/d2/raw 2>/dev/null | tail -5
echo "d2 complete for ${MODEL}"
