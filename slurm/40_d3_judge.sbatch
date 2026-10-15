#!/bin/bash
#SBATCH --job-name=semint-d3
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#
# D3 — the pairwise LLM judge (§4.8.5), ONE evaluated model per job.
#
#   MODEL=qwen25-3b sbatch --partition=gpu-short --exclude=csis.mn1,csis.cn2 \
#       --gres=gpu:1 slurm/40_d3_judge.sbatch
#
# The judge is microsoft/phi-4 (14B, ~29 GB), NOT one of the evaluated models.
# It must be staged first, from the LOGIN node:
#   bash scripts/models/cache_weights.sh judge:primary_judge
#
# WORKLOAD: C(8,2)=28 pairs x 120 constraints = up to 3,360 judgements per
# evaluated model, minus pairs where either response makes no claim (an ABSTAIN
# has nothing to judge). The driver batches generation and RESUMES from its
# archive, so a walltime kill costs only the unfinished tail.
#
# --time=02:00:00 rather than longer: a shorter reservation backfills into gaps
# a long one cannot, which matters on an account whose cpu=64 ceiling is shared.
# Resume makes an underestimate cheap; over-reserving is not.
#
# --mem=64G is the value proven by five completed primary runs. Do not lower it
# on MaxRSS reasoning -- see the note in slurm/30_primary_one_model.sbatch.

source "${SLURM_SUBMIT_DIR:-$PWD}/slurm/templates/_common.sh"
job_provenance

MODEL="${MODEL:-}"
JUDGE="${JUDGE:-primary_judge}"
if [[ -z "${MODEL}" ]]; then
  echo "ABORT: set MODEL (the EVALUATED model whose responses are judged)." >&2
  echo "  e.g. MODEL=qwen25-3b sbatch ... slurm/40_d3_judge.sbatch" >&2
  exit 2
fi

# LIMIT/OUT_DIR exist for ONE purpose: a cheap smoke test on real phi-4 before
# committing five models to a judging run. Job 15127 produced a 99.1% parse
# failure rate because the prompt was never rendered through the judge's chat
# template (Q32), and --dry-run cannot catch that -- it generates nothing. A
# two-constraint run does, in about a minute.
#
#   LIMIT=2 OUT_DIR=results/detectors/d3/smoke MODEL=qwen25-3b sbatch ...
#
# OUT_DIR keeps smoke output OUT of the reportable archive. Never set LIMIT for
# a reporting run: coverage from a truncated set is not comparable across models.
LIMIT="${LIMIT:-}"
OUT_DIR="${OUT_DIR:-results/detectors/d3/raw}"
EXTRA=()
if [[ -n "${LIMIT}" ]]; then
  EXTRA+=(--limit-constraints "${LIMIT}")
  echo "*** SMOKE TEST: ${LIMIT} constraint(s) only -> ${OUT_DIR}. NOT REPORTABLE. ***"
fi

RAW="${RAW:-results/raw/primary_trackA/${MODEL}.jsonl}"
if [[ ! -s "${RAW}" ]]; then
  echo "ABORT: ${RAW} does not exist or is empty. Run the primary job first." >&2
  exit 2
fi
N_RAW="$(wc -l < "${RAW}")"
if [[ "${N_RAW}" -lt 960 ]]; then
  echo "ABORT: ${RAW} holds ${N_RAW} records, not 960. Judging a truncated run" >&2
  echo "       produces coverage figures that cannot be compared across models." >&2
  exit 2
fi

echo "--- preflight 0/3: GPU is usable AND not already occupied ---"
# Same guard as the primary job. ConstrainDevices=no on this cluster, so a
# co-tenant can hold the card Slurm assigned us and CUDA then fails at context
# creation with "cudaGetDeviceCount()... Error 2: out of memory".
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free --format=csv \
  2>/dev/null || echo "nvidia-smi unavailable"
python3 - <<'GPUCHECK' || exit 9
import sys
try:
    import torch
    n = torch.cuda.device_count()
    if n < 1:
        sys.exit("torch reports 0 CUDA devices")
    free, total = torch.cuda.mem_get_info(0)
    gib = 1024 ** 3
    print(f"  memory free : {free / gib:.1f} GiB of {total / gib:.1f} GiB")
    if free / total < 0.80:
        sys.exit(
            f"ABORT: only {100 * free / total:.0f}% of the GPU is free; the judge "
            "needs ~90% (gpu_memory_utilization=0.90). Another job holds this "
            "card (ConstrainDevices=no). Resubmit or target an idle node."
        )
except Exception as exc:
    sys.exit(f"CUDA INIT FAILED: {type(exc).__name__}: {exc}")
print("  GPU OK")
GPUCHECK

echo
echo "--- preflight 1/3: the JUDGE's weights are cached offline ---"
python3 scripts/models/verify_cache.py "judge:${JUDGE}" || {
  echo "ABORT: judge ${JUDGE} is not in the offline cache at HF_HOME=${HF_HOME}." >&2
  echo "       Stage it from the LOGIN node:" >&2
  echo "         bash scripts/models/cache_weights.sh judge:${JUDGE}" >&2
  exit 4
}

echo
echo "--- preflight 2/3: build every prompt, generate nothing ---"
# Catches a bad prompt template, an unpinned judge or a lineage collision in
# seconds, before the 14B is loaded.
python3 scripts/analysis/run_d3_judge.py \
  --raw "${RAW}" --judge "${JUDGE}" --out-dir "${OUT_DIR}" ${EXTRA[@]+"${EXTRA[@]}"} --dry-run || exit 5

echo
echo "--- D3: judging ${MODEL} with ${JUDGE} ---"
python3 scripts/analysis/run_d3_judge.py \
  --raw "${RAW}" --judge "${JUDGE}" --out-dir "${OUT_DIR}" ${EXTRA[@]+"${EXTRA[@]}"} || exit 7

echo
ARCHIVE="${OUT_DIR}"
echo "--- archive ---"
ls -la "${ARCHIVE}" 2>/dev/null | tail -5
echo "d3 complete for ${MODEL}"
