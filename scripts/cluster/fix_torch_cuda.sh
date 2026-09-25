#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Reinstall the torch/vLLM stack against CUDA 12.8.
#
# WHY: `pip install vllm` resolves to the newest release, and vLLM >= 0.27
# pins torch==2.13.0, whose default PyPI wheel is built for CUDA 13.0. CUDA 13
# requires a 580+ driver. This cluster runs 570.158.01 (CUDA 12.8), so torch
# loads but cannot use the GPU:
#
#   "The NVIDIA driver on your system is too old (found version 12080)"
#
# The last vLLM line pinning torch==2.11.0 is 0.26.0, and torch 2.11.0+cu128
# exists on the PyTorch cu128 index — as do torchvision 0.26.0+cu128 and
# torchaudio 2.11.0+cu128. That combination matches the driver.
#
# LOGIN NODE ONLY (needs the network).
#
#   bash scripts/cluster/fix_torch_cuda.sh
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CU_INDEX="https://download.pytorch.org/whl/cu128"

TORCH_VERSION="2.11.0"
TORCHVISION_VERSION="0.26.0"
TORCHAUDIO_VERSION="2.11.0"
VLLM_VERSION="0.26.0"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!!  %s\033[0m\n' "$*" >&2; }

[[ -z "${SLURM_JOB_ID:-}" ]] || { warn "login node only — compute nodes have no network"; exit 2; }
[[ -n "${CONDA_PREFIX:-}" ]] || { warn "activate the environment first:
  module load miniconda/default
  source \$(conda info --base)/etc/profile.d/conda.sh
  conda activate ${ROOT}/.conda-env"; exit 3; }

export PIP_CACHE_DIR="${ROOT}/.pip-cache"
export TMPDIR="${ROOT}/.tmp"
mkdir -p "$PIP_CACHE_DIR" "$TMPDIR"

say "Current stack"
python - <<'PY'
import importlib
for m in ("torch", "vllm"):
    try:
        mod = importlib.import_module(m)
        cu = getattr(getattr(mod, "version", None), "cuda", None)
        print(f"  {m:8s} {getattr(mod, '__version__', '?')}" + (f"  (cuda {cu})" if cu else ""))
    except Exception:
        print(f"  {m:8s} not installed")
PY

say "Removing the CUDA-13 stack"
python -m pip uninstall -y vllm torch torchvision torchaudio 2>/dev/null || true

say "Installing torch ${TORCH_VERSION}+cu128 from ${CU_INDEX}"
python -m pip install --index-url "$CU_INDEX" \
  "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" "torchaudio==${TORCHAUDIO_VERSION}"

say "Verifying the CUDA build BEFORE installing vLLM"
python - <<'PY'
import sys, torch
cuda = torch.version.cuda or ""
print(f"  torch {torch.__version__}  built for CUDA {cuda}")
major = cuda.split(".")[0] if cuda else ""
if major != "12":
    sys.exit(
        f"\nWRONG BUILD: torch reports CUDA {cuda!r}, expected 12.x.\n"
        "The driver here is 570.158.01 (CUDA 12.8) and cannot run a CUDA 13 build."
    )
print("  OK — matches the 12.8 driver")
PY

say "Installing vLLM ${VLLM_VERSION} (pins torch==${TORCH_VERSION}, so the cu128 build is kept)"
python -m pip install "vllm==${VLLM_VERSION}"

say "Verifying torch was not silently replaced"
python - <<'PY'
import sys, torch, vllm
cuda = torch.version.cuda or ""
print(f"  torch {torch.__version__}  (cuda {cuda})")
print(f"  vllm  {vllm.__version__}")
if not cuda.startswith("12"):
    sys.exit(
        f"\nvLLM pulled a different torch: CUDA {cuda!r}.\n"
        "Pin a lower vLLM version and re-run."
    )
print("  OK")
PY

say "Freezing the environment"
LOCK="${ROOT}/requirements/lock/cluster-gpu.txt"
{
  echo "# SemIntegrity locked GPU environment"
  echo "# host      : $(hostname -f)"
  echo "# generated : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# driver    : 570.158.01 (CUDA 12.8) -> cu128 wheels required"
  echo "# python    : $(python -V 2>&1)"
  python -m pip freeze
} > "$LOCK"
say "Lock file rewritten: ${LOCK#"${ROOT}/"} ($(wc -l < "$LOCK") lines)"

cat <<'EOF'

======================================================================
Stack reinstalled for CUDA 12.8.

bf16 and real GPU use can only be confirmed on a GPU node. Re-run the
environment test:

  sbatch --partition=gpu-short --gres=gpu:1 --cpus-per-task=8 --mem=64G slurm/00_env_test.sbatch

======================================================================
EOF
