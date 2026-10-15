#!/bin/bash
#SBATCH --job-name=semint-primary
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=01:30:00
#
# 01:30 not 06:00. Job 13023 ran all 960 primary probes on a 3B in 00:01:47, so
# a 7B/14B is minutes, not hours. A 6-hour reservation cannot backfill into the
# gaps a 90-minute one fits, and on a saturated account that cost us priority
# for no benefit. Raise it only if a real run approaches the limit.
#SBATCH --cpus-per-task=4
#
# 4 not 8. GrpTRES cpu=64 is an AGGREGATE account limit and job 14958 sat at
# (AssocGrpCpuLimit) behind ~80 co-tenant array jobs. If those leave only a
# handful of CPUs free, an 8-CPU request never schedules while a 4-CPU one does.
# Offline batch inference of a <=14B model is GPU-bound; TOKENIZERS_PARALLELISM
# is already false, decoding is greedy (temperature 0.0), so CPU count cannot
# change a generated token -- only how fast it arrives.
#SBATCH --mem=64G
#
# --mem=64G. MEASURED, with one earlier theory of mine CORRECTED.
#
# What the completed runs actually show (2026-10-15):
#     15060 mistral7b-v03  MaxRSS 3.18 GiB   MaxVMSize 98.3 GiB   COMPLETED
#     15061 qwen25-7b      MaxRSS 4.16 GiB   MaxVMSize 39.6 GiB   COMPLETED
#     13023 qwen25-3b      MaxRSS 2.64 GiB   MaxVMSize 30.5 GiB   COMPLETED
#
# NOTE THE FIRST ROW: 98.3 GiB of VIRTUAL memory completed under a 64G request.
# So --mem does NOT cap VSZ on this cluster. An earlier comment here claimed it
# did, and used that to explain why --mem=32G broke job 14935. THAT WAS WRONG.
# The real cause was GPU contention (ConstrainDevices=no, a co-tenant holding
# the card) -- confirmed when 15060/15061 ran clean on csis.cn4, the very node
# that had failed twice, as soon as its neighbour left.
#
# RSS is the binding quantity and it is only 3-4 GiB. 64G is therefore generous
# headroom, kept because it is the documented plan (configs/cluster/cluster.yaml
# resource_plan) and three models have now completed under it. It is NOT lowered
# to chase scheduling, because the scheduling constraint here is the account's
# cpu=64 cap, not memory.
#
# CONSEQUENCE, accepted deliberately: GrpTRES mem=128G is an AGGREGATE limit over
# the shared `faculty` account, so two 64G jobs consume the entire pool. RUN ONE
# MODEL AT A TIME. Correctness first; concurrency is not worth a failed run.
#
# Still NOT a benchmark parameter: dtype=bfloat16, max_model_len=2048,
# gpu_memory_utilization=0.90, tensor_parallel_size and the decoding block
# (temperature 0.0, top_p 1.0, seed 20250058, max_new_tokens 24) are untouched.
#
# PRIMARY RUN, ONE MODEL — the frozen 120 test constraints x 8 probes = 960
# probes, Track A, fixed decoding (configs/inference/primary.yaml).
#
#   # 1 GPU (every model except the 70B):
#   MODEL=qwen25-3b sbatch --partition=<p> --gres=gpu:1 slurm/30_primary_one_model.sbatch
#
#   # 2 GPUs (llama33-70b only — tensor_parallel_size=2):
#   MODEL=llama33-70b sbatch --partition=<p> --gres=gpu:2 --time=24:00:00 \
#       slurm/30_primary_one_model.sbatch
#
# ONE MODEL PER JOB, DELIBERATELY. The readiness audit records 244 GB of weights
# against 286 GB of SHARED headroom, so the seven models do not coexist on disk:
# stage one, run it, evict it, stage the next. A job that assumes all seven are
# present will fail at load, not at submit.
#
# PRECONDITIONS, checked here rather than discovered on the GPU:
#   * 00_env_test and 10_smoke_inference have passed
#   * data/benchmark/test/{constraints,probes}.jsonl exist and validate at K=8
#   * the model revision is pinned and its weights are in the offline cache
#   * --gres matches the model's tensor_parallel_size

source "${SLURM_SUBMIT_DIR:-$PWD}/slurm/templates/_common.sh"
job_provenance

MODEL="${MODEL:-}"
EXPERIMENT="${EXPERIMENT:-primary}"
if [[ -z "${MODEL}" ]]; then
  echo "ABORT: set MODEL. e.g. MODEL=qwen25-3b sbatch ... slurm/30_primary_one_model.sbatch" >&2
  exit 2
fi

# The default output path is STABLE on purpose: the runner resumes on
# (experiment_id, model_id, probe_id, sample_index), so a job killed by walltime
# picks up where it stopped. The cost, learned on the pilot (job 12081), is that
# a DELIBERATE re-run against a complete file silently generates nothing. A fresh
# run therefore says so explicitly:
#   OUT=results/raw/primary_trackA/qwen25-3b-rerun2.jsonl MODEL=qwen25-3b sbatch ...
OUT="${OUT:-results/raw/primary_trackA/${MODEL}.jsonl}"

if [[ ! -f data/benchmark/test/constraints.jsonl ]]; then
  echo "ABORT: data/benchmark/test/constraints.jsonl does not exist." >&2
  exit 2
fi

echo "--- preflight 0/4: GPU is usable AND not already occupied ---"
# WHY THIS EXISTS. Jobs 14935 and 14956 both died ~30-48 s in with
#     torch._C._cuda_init()
#     RuntimeError: cudaGetDeviceCount()... Error 2: out of memory
# at MODULE IMPORT time (vllm/v1/attention/backends/flash_attn.py evaluates
# get_flash_attn_version() in a class body), before a single weight is read.
# Identical at --mem=32G and --mem=64G, so it is NOT our memory request.
#
# This cluster sets ConstrainDevices=no: cgroups do NOT fence GPUs between jobs
# (see slurm/templates/_common.sh). A co-tenant process filling the card makes
# CUDA context creation fail exactly this way. So before spending the run, prove
# a context can be created AND record what the card looked like -- a failure log
# that does not say how full the GPU was cannot be diagnosed afterwards.
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,compute_mode \
           --format=csv 2>/dev/null || echo "nvidia-smi unavailable"
# Host memory too: a node squeezed by co-tenants produces a similar CUDA
# failure, and the two are indistinguishable afterwards unless both are logged.
echo "--- node host memory (co-tenants share it; our cgroup cap is --mem) ---"
{ free -g 2>/dev/null | awk 'NR<=2'; } || echo "  (free unavailable)"
echo "--- processes already on this GPU (ConstrainDevices=no, so these are NOT ours) ---"
nvidia-smi --query-compute-apps=pid,used_memory --format=csv 2>/dev/null \
  || echo "  (could not list compute apps)"

python3 - <<'GPUCHECK' || exit 9
import sys
try:
    import torch
except Exception as exc:                      # pragma: no cover - env problem
    sys.exit(f"torch not importable: {type(exc).__name__}: {exc}")
try:
    n = torch.cuda.device_count()
    if n < 1:
        sys.exit("torch reports 0 CUDA devices")
    free, total = torch.cuda.mem_get_info(0)
    gib = 1024 ** 3
    print(f"  devices        : {n}")
    print(f"  device 0       : {torch.cuda.get_device_name(0)}")
    print(f"  memory free    : {free / gib:.1f} GiB of {total / gib:.1f} GiB")
    # gpu_memory_utilization is 0.90, so vLLM will try to reserve ~90% of TOTAL.
    # If a co-tenant already holds the card, that reservation cannot succeed and
    # the run dies minutes later with a less obvious error. Refuse here instead.
    if free / total < 0.80:
        sys.exit(
            f"ABORT: only {free / gib:.1f} GiB of {total / gib:.1f} GiB is free "
            f"({100 * free / total:.0f}%). gpu_memory_utilization=0.90 needs ~90%. "
            "Another job is on this GPU (ConstrainDevices=no). This is CONTENTION, "
            "not a configuration error -- resubmit, or target an idle node."
        )
except Exception as exc:
    sys.exit(
        f"CUDA INIT FAILED: {type(exc).__name__}: {exc}\n"
        "  This is the 14935/14956 failure. It is NOT the memory request -- it "
        "reproduced identically at 32G and 64G. Most likely a co-tenant process "
        "holds the allocated GPU (ConstrainDevices=no on this cluster). Check the "
        "nvidia-smi output above, then resubmit or target an idle node."
    )
print("  GPU OK and substantially free")
GPUCHECK

echo
echo "--- preflight 1/4: validate the TEST benchmark at K=8 ---"
# --strict-lattice because this is the frozen 120: a run against an incomplete
# or unbalanced benchmark produces numbers that cannot be reported.
python3 -m semintegrity.benchmark.validate --split test --k 8 --strict-lattice || exit 3

echo
echo "--- preflight 2/4: offline weight cache ---"
# OFFLINE check only. cache_weights.sh --check hits the network and must never
# run on a compute node (configs/cluster: compute nodes have no internet).
python3 scripts/models/verify_cache.py "${MODEL}" || {
  echo "ABORT: ${MODEL} weights are not in the offline cache at HF_HOME=${HF_HOME}." >&2
  echo "       Stage them from the LOGIN node first, then resubmit." >&2
  exit 4
}

echo
echo "--- preflight 3/4: resolve the run without generating ---"
python3 -m semintegrity.inference.run_experiment \
  --experiment "${EXPERIMENT}" --model "${MODEL}" --dry-run || exit 5

# tensor_parallel_size must match the GPUs Slurm actually gave us. vLLM would
# otherwise either hang or silently run on one device, and a 70B run on one A100
# is an OOM, not a result.
TP="$(python3 -c "
from semintegrity.utils.config import resolve_model_config
print(resolve_model_config('${MODEL}').data['serving']['tensor_parallel_size'])
")"
GPUS="${SLURM_GPUS_ON_NODE:-$(( $(echo "${CUDA_VISIBLE_DEVICES:-}" | tr ',' '\n' | grep -c . ) ))}"
echo "tensor_parallel_size=${TP}  gpus_visible=${GPUS}"
if [[ "${GPUS}" != "unset" && -n "${GPUS}" && "${TP}" -gt "${GPUS}" ]]; then
  echo "ABORT: ${MODEL} needs tensor_parallel_size=${TP} but only ${GPUS} GPU(s) are visible." >&2
  echo "       Resubmit with --gres=gpu:${TP}." >&2
  exit 6
fi

echo
echo "--- inference: ${MODEL} over 960 primary probes ---"
echo "output: ${OUT}"
if [[ -s "${OUT}" ]]; then
  echo "NOTE: ${OUT} already has $(wc -l < "${OUT}") record(s); the runner will"
  echo "      RESUME and skip probes already present. Set OUT=<new path> for a"
  echo "      genuinely fresh run."
fi
python3 -m semintegrity.inference.run_experiment \
  --experiment "${EXPERIMENT}" \
  --model "${MODEL}" \
  --out "${OUT}" || exit 7

echo
echo "--- record count ---"
# A short run is a FAILED run, not a partial result. Say so here rather than
# letting analysis average over a truncated dataset.
N="$(wc -l < "${OUT}")"
echo "${N} record(s) in ${OUT}"
if [[ "${N}" -lt 960 ]]; then
  echo "WARNING: fewer than 960 records. The run is INCOMPLETE — resubmit to resume." >&2
  echo "         Do NOT run analysis on a truncated dataset." >&2
  exit 8
fi

echo "primary run complete for ${MODEL}: ${N}/960"
