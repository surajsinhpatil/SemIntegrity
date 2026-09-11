#!/usr/bin/env bash
# Sourced by every script that does heavy work.
# Aborts if it is running outside a Slurm allocation, so that a mistyped
# command cannot start model inference on the login node.
#
#   source "$(dirname "$0")/../_guard_login_node.sh"
#   require_slurm_allocation
require_slurm_allocation() {
  if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    cat >&2 <<'MSG'
REFUSING TO RUN: no SLURM_JOB_ID in the environment.

This script performs GPU- or CPU-heavy work and must be submitted through
Slurm. The login node is for editing, git, job submission and status checks
only (see configs/cluster/cluster.yaml -> hard_rules).

  sbatch slurm/<the matching job script>

To override for a genuine interactive allocation, obtain one first:
  srun --partition=<gpu-partition> --gres=gpu:1 --pty bash
MSG
    exit 99
  fi
}
