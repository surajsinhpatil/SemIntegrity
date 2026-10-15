#!/bin/bash
#SBATCH --job-name=semint-d4
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#
# D4 — EXPLORATORY distributional analysis (§4.8.6, ADR-0024), one model per job.
#
#   MODEL=qwen25-3b sbatch --partition=gpu-short --exclude=csis.mn1,csis.cn2 \
#       --gres=gpu:1 slurm/60_d4_distributional.sbatch
#
# D4 IS NOT A CONTRADICTION DETECTOR. It measures distributional instability
# under paraphrase and exposes no verdict.
#
# It re-loads the EVALUATED model (already cached from the primary run — no new
# staging) and scores each candidate teacher-forced. Workload per model:
# 960 probes x |answer_space| (2 or 3) forward passes, one per candidate, each
# over prompt + candidate. ~2,400 short forward passes for a 3B; the 14B is
# proportionally slower. --time=02:00:00 covers the largest; resume makes an
# underestimate cheap.
#
# T = 1 is FROZEN as primary (ADR-0024). The sensitivity band {0.5,1,2,4} is
# computed from the SAME stored log-probabilities and costs NO extra inference.

source "${SLURM_SUBMIT_DIR:-$PWD}/slurm/templates/_common.sh"
job_provenance

MODEL="${MODEL:-}"
if [[ -z "${MODEL}" ]]; then
  echo "ABORT: set MODEL." >&2
  exit 2
fi
CFG="configs/models/${MODEL}.yaml"
if [[ ! -s "${CFG}" ]]; then
  echo "ABORT: no model config at ${CFG}" >&2
  exit 2
fi
RAW="${RAW:-results/raw/primary_trackA/${MODEL}.jsonl}"
if [[ ! -s "${RAW}" ]]; then
  echo "ABORT: ${RAW} does not exist or is empty." >&2
  exit 2
fi

echo "--- preflight 0/3: GPU is usable AND not already occupied ---"
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
    if free / total < 0.80:
        sys.exit(
            f"ABORT: only {100 * free / total:.0f}% of the GPU is free; D4 loads a "
            "full evaluated model. Another job holds this card "
            "(ConstrainDevices=no). Resubmit or target an idle node."
        )
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

# GATE, unlike D2's report-only version. Measured 2026-10-15 on gpu-short:
#   cn1 20.2 GB free · cn3 1.0 GB free · cn4 27.0 GB free   (of 240 GB each)
# Slurm granting --mem=64G does not make that memory physically available —
# GrpTRES mem is per-ACCOUNT and shared across ~9 students. D2's job 15158 died
# on cn1 with a failed 16 MiB CPU allocation for exactly this reason.
#
# D4 loads a FULL evaluated model (3B-14B). device_map keeps the model off the
# host, but each safetensors shard is still read through host buffers, and the
# measured floor from D2's successful run is MaxRSS 2.4 GB for a 435M model.
# 10 GiB is a conservative floor that would have refused cn3 outright.
# Override with D4_MIN_AVAIL_GIB if a run is deliberately tried on less.
MIN_AVAIL_GIB="${D4_MIN_AVAIL_GIB:-10}"
AVAIL_GIB="$(awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null || echo 0)"
if [[ "${AVAIL_GIB}" -lt "${MIN_AVAIL_GIB}" ]]; then
  echo "ABORT: only ${AVAIL_GIB} GiB of host memory is available on $(hostname -s);" >&2
  echo "       D4 needs at least ${MIN_AVAIL_GIB} GiB to stream weight shards." >&2
  echo "       This is a co-tenant problem, not a config problem: resubmit, or" >&2
  echo "       target a node with free memory (sinfo -N -p gpu-short -o '%n %t %e')." >&2
  exit 10
fi
echo "  host memory gate: ${AVAIL_GIB} GiB available >= ${MIN_AVAIL_GIB} GiB required"

echo
echo "--- preflight 1/3: the EVALUATED model's weights are cached offline ---"
python3 scripts/models/verify_cache.py "${MODEL}" || {
  echo "ABORT: ${MODEL} is not in the offline cache at HF_HOME=${HF_HOME}." >&2
  echo "       This is EXPECTED, not a bug: the evaluated models were EVICTED" >&2
  echo "       after the primary runs to stay under the 1000 G per-user quota" >&2
  echo "       (stage one, run it, evict it). D4 needs the model back." >&2
  echo "       From the LOGIN node:" >&2
  echo "         bash scripts/models/cache_weights.sh ${MODEL}" >&2
  echo "       Check headroom FIRST (quota -s): a 7B needs ~20 G and the 14B" >&2
  echo "       ~39 G with margin. If headroom is short, evict the phi-4 judge" >&2
  echo "       (~29 G) -- D3 is complete for every reportable model." >&2
  exit 4
}

echo
echo "--- preflight 2/3: count the workload, load nothing ---"
python3 scripts/analysis/run_d4.py --raw "${RAW}" --model-config "${CFG}" --dry-run || exit 5

echo
echo "--- D4: analysing ${MODEL} ---"
python3 scripts/analysis/run_d4.py --raw "${RAW}" --model-config "${CFG}" || exit 7

echo
echo "--- archive ---"
ls -la results/detectors/d4/raw 2>/dev/null | tail -5
echo "d4 complete for ${MODEL}"
