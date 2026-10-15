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
# Caches split in TWO, and the split matters.
#
# DURABLE artefacts stay in work_dir. These tools default to $HOME/.cache, which
# on this SHARED lab account is outside work_dir and breaks the first rule in
# configs/cluster/cluster.yaml:shared_account_rules (job 11968 wrote one there).
export XDG_CACHE_HOME="${SEMINT_ROOT}/.cache"
mkdir -p "$XDG_CACHE_HOME"

# JIT CACHES GO NODE-LOCAL. NEVER ON NFS.
#
# Triton and Inductor cache *compiled shared objects* -- e.g.
# triton/<hash>/cuda_utils.cpython-311-x86_64-linux-gnu.so -- which are dlopen'd
# during CUDA initialisation. On NFS that is unsafe: no reliable locking, and
# mmap semantics that differ from local disk.
#
# This is not theoretical. Pointing these at ${SEMINT_ROOT}/.cache cost five
# failed jobs on 2026-09-26 (12081, 12089, 12090, 12092, 12093). The pattern was
# exact: the runs that CREATED the cache succeeded, and every run that READ it
# died with SIGSEGV in EngineCore before parallel_state init, on four different
# nodes, with no Python-level error. Moving the caches aside fixed it on the
# first attempt.
#
# The cost of node-local is one torch.compile per job, ~16 s out of ~74 s. The
# compile cache is a derived build artefact, not a reproducibility artefact --
# the things that must be archived are the weights (HF_HOME), the lock file and
# the outputs, all of which stay on NFS.
SEMINT_JIT_ROOT="${SLURM_TMPDIR:-/tmp}/semint-jit-${SLURM_JOB_ID:-$$}"
export VLLM_CACHE_ROOT="${SEMINT_JIT_ROOT}/vllm"
export TORCHINDUCTOR_CACHE_DIR="${SEMINT_JIT_ROOT}/torchinductor"
export TRITON_CACHE_DIR="${SEMINT_JIT_ROOT}/triton"
mkdir -p "$VLLM_CACHE_ROOT" "$TORCHINDUCTOR_CACHE_DIR" "$TRITON_CACHE_DIR"
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
# Parse glibc without a pipe. `ldd --version | head -1` makes ldd die of SIGPIPE,
# which `set -o pipefail` turns into a fatal 141 (observed 2026-09-25).
glibc_version() {
  local raw line ver
  raw="$(ldd --version 2>/dev/null || true)"
  line="${raw%%$'\n'*}"
  ver="${line##* }"
  case "$ver" in
    [0-9]*.[0-9]*) printf '%s' "$ver" ;;
    *)             printf 'unknown'   ;;
  esac
}

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
  # glibc decides which vLLM wheels can be installed at all (ADR-0015), and a
  # compute node need not match the login node. Record it on every job so the
  # question is answered by an artefact, never inferred.
  # No `| head -1` here: head closes the pipe, ldd dies of SIGPIPE, and under the
  # `set -o pipefail` at the top of this file that would abort the job. It cost
  # one failed run to learn. Slice the string in the shell instead.
  echo "glibc         : $(glibc_version)"
  echo "os            : $(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}" || echo unknown)"
  echo "start_utc     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_commit    : $(git -C "$SEMINT_ROOT" rev-parse HEAD 2>/dev/null || echo 'not-a-git-repo')"
  echo "git_dirty     : $(git -C "$SEMINT_ROOT" status --porcelain 2>/dev/null | wc -l) files"
  # NEVER let provenance capture kill the job. csis.mn1 ships an nvidia-smi
  # WRAPPER that prints "GPU ACCESS RESTRICTED" and exits non-zero even inside a
  # Slurm job holding a real allocation. Unguarded, `cmd -v x && x` returns that
  # non-zero status, `set -e` aborts, and job 14962 died in 2 s having produced
  # nothing but a provenance block. Recording the GPU is diagnostics; failing to
  # record it must never be fatal.
  if command -v nvidia-smi >/dev/null; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader \
      || echo "nvidia-smi present but refused (site wrapper or restricted node)"
  fi
  python3 -c 'import sys; print("python        :", sys.version.split()[0])' 2>/dev/null || true
  echo "==============================================================="
}

on_exit() {
  local code=$?
  # Node-local JIT scratch is per-job and worthless afterwards; leaving it
  # behind fills /tmp on a shared node.
  if [[ -n "${SEMINT_JIT_ROOT:-}" && "${SEMINT_JIT_ROOT}" == */semint-jit-* ]]; then
    rm -rf "${SEMINT_JIT_ROOT}" 2>/dev/null || true
  fi
  echo "=== job exit: ${code} at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  exit "$code"
}
trap on_exit EXIT
