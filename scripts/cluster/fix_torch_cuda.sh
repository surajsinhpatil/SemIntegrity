#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Install the torch/vLLM stack that actually runs on this cluster's CUDA 12.8
# driver, keeping vLLM as the sole inference backend (§4.13).
#
# WHY THIS VERSION PAIR
# ---------------------
# The driver here is 570.158.01 = CUDA 12.8. CUDA 13 needs a 580+ driver.
#
# The trap: vLLM's PyPI metadata is NOT a reliable CUDA signal. vLLM 0.20.2
# through 0.26.0 all pin torch==2.11.0 (a CUDA 12 torch is available for that
# version), yet their own compiled extensions link libcudart.so.13 /
# libnvrtc.so.13. Pinning torch to cu128 therefore fixes torch and leaves vLLM
# still importing a CUDA 13 runtime that does not exist here. That is the
# `ImportError: libcudart.so.13` seen on this cluster with vllm 0.30.0, and it
# is why the earlier 0.26.0 pin in this script did not work either.
#
# Verified by reading the DT_NEEDED strings out of the published wheels:
#
#   vllm <= 0.19.1   ->  libcudart.so.12   COMPATIBLE
#   vllm >= 0.20.2   ->  libcudart.so.13   INCOMPATIBLE (needs driver 580+)
#
# Among the CUDA 12 line, 0.19.1 is the only usable release: 0.17.0-0.19.0
# require transformers<5, which would force a downgrade from the installed
# transformers 5.x and change chat-template behaviour (logged per response as
# chat_template_hash, so it is not a free change). vllm 0.19.1 allows
# transformers >= 5.5.1, so transformers is left untouched.
#
# The cost is torch 2.11.0 -> 2.10.0, which vllm 0.19.1 pins. torch
# 2.10.0+cu128 supports A100 (sm80) and bf16 exactly as 2.11.0 did.
#
# LOGIN NODE ONLY (needs the network).
#
#   bash scripts/cluster/fix_torch_cuda.sh
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CU_INDEX="https://download.pytorch.org/whl/cu128"

TORCH_VERSION="2.10.0"
TORCHVISION_VERSION="0.25.0"
TORCHAUDIO_VERSION="2.10.0"
VLLM_VERSION="0.19.1"
REQUIRED_GLIBC="2.31"      # vllm 0.19.1 ships manylinux_2_31 wheels

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
for m in ("torch", "vllm", "transformers"):
    try:
        mod = importlib.import_module(m)
        cu = getattr(getattr(mod, "version", None), "cuda", None)
        print(f"  {m:13s} {getattr(mod, '__version__', '?')}" + (f"  (cuda {cu})" if cu else ""))
    except Exception as exc:
        print(f"  {m:13s} NOT IMPORTABLE ({type(exc).__name__}: {str(exc)[:60]})")
PY

say "Checking glibc (vllm ${VLLM_VERSION} ships manylinux_2_31 wheels)"
GLIBC="$(ldd --version | head -1 | grep -oE '[0-9]+\.[0-9]+$')"
echo "  glibc ${GLIBC}, need >= ${REQUIRED_GLIBC}"
if [ "$(printf '%s\n%s\n' "$REQUIRED_GLIBC" "$GLIBC" | sort -V | head -1)" != "$REQUIRED_GLIBC" ]; then
  warn "glibc ${GLIBC} is older than ${REQUIRED_GLIBC}: the vllm ${VLLM_VERSION} wheel will not install."
  warn "STOP. Do not build from source on the login node. Report this and re-plan."
  exit 4
fi
echo "  OK"

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
if (cuda.split(".")[0] if cuda else "") != "12":
    sys.exit(
        f"\nWRONG BUILD: torch reports CUDA {cuda!r}, expected 12.x.\n"
        "The driver here is 570.158.01 (CUDA 12.8) and cannot run a CUDA 13 build."
    )
print("  OK — matches the 12.8 driver")
PY

# A constraints file stops any transitive dependency from swapping the cu128
# torch back out for a default-index (CUDA 13) build.
CONSTRAINTS="${TMPDIR}/cuda12-constraints.txt"
{
  echo "torch==${TORCH_VERSION}"
  echo "torchvision==${TORCHVISION_VERSION}"
  echo "torchaudio==${TORCHAUDIO_VERSION}"
} > "$CONSTRAINTS"

say "Installing vLLM ${VLLM_VERSION} under constraints"
python -m pip install "vllm==${VLLM_VERSION}" \
  --constraint "$CONSTRAINTS" \
  --extra-index-url "$CU_INDEX"

say "Verifying torch was not silently replaced, and vLLM actually imports"
python - <<'PY'
import sys, torch
cuda = torch.version.cuda or ""
print(f"  torch {torch.__version__}  (cuda {cuda})")
if not cuda.startswith("12"):
    sys.exit(f"\nvLLM pulled a different torch: CUDA {cuda!r}. Pin a lower vLLM and re-run.")
import vllm
print(f"  vllm  {vllm.__version__}   <- imported, so no libcudart.so.13")
import transformers
print(f"  transformers {transformers.__version__}")
print("  OK")
PY

say "Confirming no CUDA-13 runtime is linked anywhere in the vLLM install"
python - <<'PY'
import pathlib, re, sys, vllm
root = pathlib.Path(vllm.__file__).parent
pat = re.compile(rb"libcudart\.so\.(\d+)")
bad = []
for so in root.rglob("*.so"):
    try:
        hit = {m.decode() for m in pat.findall(so.read_bytes())}
    except OSError:
        continue
    if "13" in hit:
        bad.append(so.relative_to(root))
if bad:
    print("  CUDA 13 references found in:", *[f"    {b}" for b in bad[:10]], sep="\n")
    sys.exit("  FAIL — this build cannot run on a CUDA 12.8 driver.")
print(f"  OK — scanned {sum(1 for _ in root.rglob('*.so'))} shared objects, none need libcudart.so.13")
PY

say "Freezing the environment"
LOCK="${ROOT}/requirements/lock/cluster-gpu.txt"
mkdir -p "$(dirname "$LOCK")"
{
  echo "# SemIntegrity locked GPU environment"
  echo "# host      : $(hostname -f)"
  echo "# generated : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# driver    : 570.158.01 (CUDA 12.8) -> cu128 wheels required"
  echo "# backend   : vLLM ${VLLM_VERSION} (last release linking libcudart.so.12)"
  echo "# python    : $(python -V 2>&1)"
  python -m pip freeze
} > "$LOCK"
say "Lock file rewritten: ${LOCK#"${ROOT}/"} ($(wc -l < "$LOCK") lines)"

cat <<'EOF'

======================================================================
Stack reinstalled for CUDA 12.8 with vLLM as the inference backend.

bf16 and real GPU use can only be confirmed on a GPU node:

  sbatch --partition=gpu-short --gres=gpu:1 --cpus-per-task=8 --mem=64G slurm/00_env_test.sbatch

======================================================================
EOF
