#!/usr/bin/env bash
# Common preamble sourced by every SemIntegrity Slurm job.
# Keeps environment activation, provenance capture and failure handling in one
# place so that no single job script can quietly diverge.
set -euo pipefail

: "${SEMINT_ROOT:?SEMINT_ROOT must be set (the repository root on the cluster)}"
cd "$SEMINT_ROOT"

# --- caches stay inside the working directory (never in $HOME, never shared) --
export HF_HOME="${SEMINT_ROOT}/hf_cache"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"     # compute nodes run OFFLINE by default
export TRANSFORMERS_OFFLINE="${HF_HUB_OFFLINE}"
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export PYTHONPATH="${SEMINT_ROOT}/src:${PYTHONPATH:-}"
export PYTHONHASHSEED=0

# --- environment activation -------------------------------------------------
# UNRESOLVED until the cluster probe reports the module system. Set
# SEMINT_ENV_ACTIVATE to the correct command in configs/cluster/cluster.yaml
# and export it from the submit script.
if [[ -n "${SEMINT_ENV_ACTIVATE:-}" ]]; then
  # shellcheck disable=SC1090
  source "${SEMINT_ENV_ACTIVATE}"
else
  echo "WARNING: SEMINT_ENV_ACTIVATE is unset; relying on the inherited environment" >&2
fi

# --- provenance -------------------------------------------------------------
job_provenance() {
  echo "=== SemIntegrity job provenance ==============================="
  echo "job_id        : ${SLURM_JOB_ID:-none}"
  echo "array_task    : ${SLURM_ARRAY_TASK_ID:-none}"
  echo "node          : ${SLURMD_NODENAME:-$(hostname)}"
  echo "partition     : ${SLURM_JOB_PARTITION:-none}"
  echo "cpus_per_task : ${SLURM_CPUS_PER_TASK:-unset}"
  echo "gpus          : ${SLURM_GPUS_ON_NODE:-${CUDA_VISIBLE_DEVICES:-none}}"
  echo "start_utc     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_commit    : $(git -C "$SEMINT_ROOT" rev-parse HEAD 2>/dev/null || echo 'not-a-git-repo')"
  echo "git_dirty     : $(git -C "$SEMINT_ROOT" status --porcelain 2>/dev/null | wc -l) files"
  command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
  python3 -c 'import sys; print("python        :", sys.version.split()[0])' 2>/dev/null || true
  echo "==============================================================="
}

on_exit() {
  local code=$?
  echo "=== job exit: ${code} at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  exit "$code"
}
trap on_exit EXIT
