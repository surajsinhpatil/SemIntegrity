#!/usr/bin/env bash
# Common preamble sourced by every SemIntegrity Slurm job.
# Keeps environment activation, provenance capture and failure handling in one
# place so that no single job script can quietly diverge.
set -euo pipefail

# Default to the directory the job was submitted from. Requiring an explicit
# export meant a forgotten variable burned a GPU allocation to print an error.
SEMINT_ROOT="${SEMINT_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}"
export SEMINT_ROOT
[[ -f "${SEMINT_ROOT}/configs/project.yaml" ]] || {
  echo "SEMINT_ROOT=${SEMINT_ROOT} is not the project root (no configs/project.yaml)" >&2
  exit 1
}
cd "$SEMINT_ROOT"

# The conda environment lives inside the project by default.
if [[ -z "${SEMINT_ENV_ACTIVATE:-}" && -d "${SEMINT_ROOT}/.conda-env" ]]; then
  export SEMINT_ENV_ACTIVATE="${SEMINT_ROOT}/.conda-env"
fi

# --- caches stay inside the working directory (never in $HOME, never shared) --
export HF_HOME="${SEMINT_ROOT}/hf_cache"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"     # compute nodes run OFFLINE by default
export TRANSFORMERS_OFFLINE="${HF_HUB_OFFLINE}"
export TOKENIZERS_PARALLELISM=false
# Cap every BLAS backend, not just OpenMP. Compute nodes have 128 cores, and
# numpy/scipy otherwise spawn one thread per core at import — slow at best,
# stalled at worst. Bound by what Slurm actually allocated.
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export OPENBLAS_NUM_THREADS="${OMP_NUM_THREADS}"
export MKL_NUM_THREADS="${OMP_NUM_THREADS}"
export NUMEXPR_NUM_THREADS="${OMP_NUM_THREADS}"
export VECLIB_MAXIMUM_THREADS="${OMP_NUM_THREADS}"
export PYTHONPATH="${SEMINT_ROOT}/src:${PYTHONPATH:-}"
export PYTHONHASHSEED=0

# --- environment activation -------------------------------------------------
# UNRESOLVED until the cluster probe reports the module system. Set
# SEMINT_ENV_ACTIVATE to the correct command in configs/cluster/cluster.yaml
# and export it from the submit script.
# SEMINT_ENV_ACTIVATE may be either a conda PREFIX or a script to source.
# Conda's hook scripts are not `set -u` safe — this cluster's
# deactivate.d/unset_pythonpath.sh reads an unset variable and would abort the
# job — so nounset is relaxed around them and restored straight after.
if [[ -n "${SEMINT_ENV_ACTIVATE:-}" ]]; then
  set +u
  if [[ -d "${SEMINT_ENV_ACTIVATE}" ]]; then
    module load miniconda/default 2>/dev/null || true
    # shellcheck disable=SC1091
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "${SEMINT_ENV_ACTIVATE}"
  else
    # shellcheck disable=SC1090
    source "${SEMINT_ENV_ACTIVATE}"
  fi
  set -u
  echo "environment    : ${CONDA_PREFIX:-${SEMINT_ENV_ACTIVATE}}"
  echo "python         : $(command -v python3)"
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
  echo "gpus_on_node  : ${SLURM_GPUS_ON_NODE:-unset}"
  # ConstrainDevices=no on this cluster: cgroups do NOT fence GPUs between jobs,
  # so the only record of which devices are ours is this variable. Log it.
  echo "CUDA_VISIBLE_DEVICES = ${CUDA_VISIBLE_DEVICES:-unset}"
  # glibc decides whether the ADR-0013 vLLM 0.19.1 wheel (manylinux_2_31) can
  # be installed at all, and compute nodes need not match the login node. Record
  # it on every job so the question is answered by an artefact, never inferred.
  echo "glibc         : $(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+$' || echo unknown)"
  echo "os            : $(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}" || echo unknown)"
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
