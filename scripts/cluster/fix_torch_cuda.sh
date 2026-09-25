#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Install the torch/vLLM stack that actually runs on this cluster's CUDA 12.8
# driver, keeping vLLM as the sole inference backend (§4.13).
#
# WHY THIS VERSION SET  (ADR-0015)
# --------------------------------
# TWO constraints must be satisfied at once, and they nearly exclude each other.
#
#   1. CUDA. The driver here is 570.158.01 = CUDA 12.8; CUDA 13 needs 580+.
#   2. glibc. The host is Rocky Linux 8.10, which provides glibc 2.28.
#
# Reading every published x86_64 wheel tag together with the DT_NEEDED strings
# of its compiled extensions gives both dimensions:
#
#   vllm 0.1.4 - 0.11.2    manylinux1        glibc 2.5    libcudart.so.12   OK
#   vllm 0.12.0 - 0.19.1   manylinux_2_31    glibc 2.31   libcudart.so.12   no (glibc)
#   vllm 0.20.0 - 0.20.2   manylinux_2_35    glibc 2.35   libcudart.so.13   no (both)
#   vllm 0.21.0            manylinux_2_24    glibc 2.24   libcudart.so.13   no (CUDA)
#   vllm 0.22.0 - 0.30.0   manylinux_2_28    glibc 2.28   libcudart.so.13   no (CUDA)
#
# Every CUDA-12 release from 0.12.0 on needs glibc 2.31; the first release built
# for 2.28 is already CUDA-13. The ONLY overlap is the manylinux1 line, so
# 0.11.2 is the newest usable release. ADR-0013's 0.19.1 pin is unexecutable
# here: correct about CUDA, but it never checked glibc.
#
# Two traps, both of which have misled this project already:
#   * A wheel's torch pin does NOT track its own CUDA linkage. 0.20.0-0.26.0 pin
#     torch==2.11.0, for which a cu128 build exists, yet still need CUDA 13.
#   * Neither does the dependency metadata. 0.20.0 and 0.21.0 declare no cu13
#     dependency and link libcudart.so.13 anyway. Only the binary is
#     authoritative.
#
# The cost is transformers 5.x -> 4.x, which vllm 0.11.2 requires. That was
# measured before being accepted: for Qwen2.5-3B at the pinned revision,
# transformers 4.57.6 and 5.0.0 produce a byte-identical rendered prompt and the
# same chat_template_hash (the hash is taken over the template string shipped in
# the model repo, so the library version cannot change it). Per-model
# confirmation is still required via scripts/models/audit_chat_templates.py.
#
# LOGIN NODE ONLY (needs the network).
#
#   bash scripts/cluster/fix_torch_cuda.sh
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CU_INDEX="https://download.pytorch.org/whl/cu128"

TORCH_VERSION="2.9.0"
TORCHVISION_VERSION="0.24.0"
TORCHAUDIO_VERSION="2.9.0"
VLLM_VERSION="0.11.2"
REQUIRED_GLIBC="2.14"      # vllm 0.11.2 ships manylinux1 wheels; max GLIBC symbol is 2.14

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

say "Checking glibc (vllm ${VLLM_VERSION} ships manylinux1 wheels)"
# Do NOT write `ldd --version | head -1`, and do NOT compare with `sort -V | head -1`.
# `head` closes the pipe after the line it wants, the writer upstream dies of
# SIGPIPE, and under `set -o pipefail` that becomes a fatal exit 141. This script
# failed exactly that way on its first real run (2026-09-25, exit 141 right after
# the "Checking glibc" banner). Read the output once, then slice and compare in
# the shell, so there is no pipe to break.
GLIBC_RAW="$(ldd --version 2>/dev/null || true)"
GLIBC_LINE="${GLIBC_RAW%%$'\n'*}"        # e.g. "ldd (GNU libc) 2.28"
GLIBC="${GLIBC_LINE##* }"                # e.g. "2.28"
case "$GLIBC" in
  [0-9]*.[0-9]*) : ;;
  *) warn "could not parse a glibc version from: ${GLIBC_LINE:-<no output from ldd>}"
     warn "STOP. Determine the host's glibc before installing anything."
     exit 4 ;;
esac

_ver_major() { printf '%s' "${1%%.*}"; }
_ver_minor() { local r="${1#*.}"; printf '%s' "${r%%.*}"; }

echo "  glibc ${GLIBC}, need >= ${REQUIRED_GLIBC}"
if [ "$(_ver_major "$GLIBC")" -lt "$(_ver_major "$REQUIRED_GLIBC")" ] ||
   { [ "$(_ver_major "$GLIBC")" -eq "$(_ver_major "$REQUIRED_GLIBC")" ] &&
     [ "$(_ver_minor "$GLIBC")" -lt "$(_ver_minor "$REQUIRED_GLIBC")" ]; }; then
  warn "glibc ${GLIBC} is older than ${REQUIRED_GLIBC}: the vllm ${VLLM_VERSION} wheel will not install."
  warn "STOP. Do not build from source on the login node. Report this and re-plan."
  exit 4
fi
echo "  OK"

say "Removing the CUDA-13 stack"
# vllm 0.26.0 is the ROOT of the CUDA-13 contamination on this host. Audited
# 2026-09-25: it pulled nvidia-cutlass-dsl (shared with flashinfer-python,
# quack-kernels and tokenspeed-mla, all vllm 0.26.0 dependencies), which dragged
# in the cu13 chain; nvidia-cudnn-cu13 and nvidia-nccl-cu13 are left as orphans
# with no remaining dependents. Removing vllm alone would strand them, and a
# stray libcudart.so.13 on the path is exactly what the final scan exists to
# catch. The nvidia-*-cu12 packages belong to torch and MUST survive.
python -m pip uninstall -y vllm torch torchvision torchaudio 2>/dev/null || true
python -m pip uninstall -y \
  flashinfer-python quack-kernels tokenspeed-mla \
  nvidia-cutlass-dsl nvidia-cutlass-dsl-libs-base nvidia-cutlass-dsl-libs-core \
  nvidia-cutlass-dsl-libs-cu12 nvidia-cutlass-dsl-libs-cu13 \
  nvidia-cudnn-cu13 nvidia-nccl-cu13 nvidia-cusparselt-cu13 nvidia-nvshmem-cu13 \
  nvidia-cublas nvidia-cuda-runtime nvidia-cuda-cupti nvidia-cuda-nvrtc \
  nvidia-cuda-nvcc nvidia-cuda-crt nvidia-cuda-cccl nvidia-cuda-nvdisasm \
  nvidia-cufft nvidia-cufile nvidia-curand nvidia-cusolver nvidia-cusparse \
  nvidia-nvjitlink nvidia-nvtx nvidia-nvvm \
  2>/dev/null || true

say "Confirming no CUDA-13 runtime package survived the purge"
python - <<'PY'
import importlib.metadata as md
left = sorted(
    d.metadata["Name"]
    for d in md.distributions()
    if (d.metadata["Name"] or "").lower().endswith("-cu13")
    or (d.metadata["Name"] or "").lower() in {
        "nvidia-cublas", "nvidia-cuda-runtime", "nvidia-cuda-nvcc", "nvidia-cutlass-dsl",
    }
)
print("  surviving CUDA-13 packages:", left or "none")
if left:
    print("  (not fatal here: the post-install .so scan is the real gate)")
PY

say "Installing torch ${TORCH_VERSION}+cu128 from ${CU_INDEX}"
python -m pip install --index-url "$CU_INDEX" \
  "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" "torchaudio==${TORCHAUDIO_VERSION}"

say "Repairing any nvidia package whose files the purge clobbered"
# Several nvidia wheels install into the SAME directory: nvidia-cusparselt-cu12
# and nvidia-cusparselt-cu13 both write site-packages/nvidia/cusparselt/lib/.
# Uninstalling the cu13 one deletes the shared directory contents, taking the
# cu12 .so with it while leaving cu12's METADATA intact. pip then sees cu12 as
# "already installed" at a satisfying version and skips it, so torch ends up
# with a recorded dependency that has no files:
#
#   ImportError: libcusparseLt.so.0: cannot open shared object file
#
# Observed 2026-09-25: exactly one package (nvidia-cusparselt-cu12 0.7.1) was
# hit, because the others happened to need a version bump and were genuinely
# reinstalled. Which packages collide depends on the versions present, so this
# detects rather than hard-codes: compare each nvidia package's RECORD against
# the filesystem and force-reinstall only what is actually missing.
REPAIR_LIST="${TMPDIR}/nvidia-repair.txt"
python - "$REPAIR_LIST" <<'PY'
import importlib.metadata as md, pathlib, sys
out = pathlib.Path(sys.argv[1])
broken = {}
for d in md.distributions():
    name = d.metadata["Name"] or ""
    if not name.lower().startswith("nvidia-"):
        continue
    for f in (d.files or []):
        if ".so" in str(f) and not pathlib.Path(d.locate_file(f)).exists():
            broken[name] = d.version
            break
for n, v in sorted(broken.items()):
    print(f"  MISSING FILES: {n}=={v}")
out.write_text("\n".join(f"{n}=={v}" for n, v in sorted(broken.items())))
print(f"  {len(broken)} package(s) need repair")
PY
if [ -s "$REPAIR_LIST" ]; then
  # shellcheck disable=SC2046
  python -m pip install --force-reinstall --no-deps $(tr '\n' ' ' < "$REPAIR_LIST")
else
  echo "  nothing to repair"
fi

say "Verifying the CUDA build BEFORE installing vLLM"
python - <<'PY'
import sys
try:
    import torch
except ImportError as exc:
    # A missing libXXX.so.N here means a shared CUDA library is absent, not that
    # torch is uninstalled. The repair step above should have caught it; if this
    # still fires, the library belongs to a package whose RECORD also lost the
    # entry, so re-run with an explicit reinstall of that nvidia-* package.
    sys.exit(
        f"\ntorch is installed but cannot import: {exc}\n"
        "This is a MISSING SHARED LIBRARY, not a CUDA-version problem.\n"
        "Identify the owning package and force-reinstall it, e.g.\n"
        "  python -m pip install --force-reinstall --no-deps nvidia-<lib>-cu12==<version>"
    )
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

say "Verifying torch was not silently replaced, and the versions landed in range"
python - <<'PY'
import sys, torch, importlib.metadata as md
cuda = torch.version.cuda or ""
print(f"  torch {torch.__version__}  (cuda {cuda})")
if not cuda.startswith("12"):
    sys.exit(f"\nvLLM pulled a different torch: CUDA {cuda!r}. Pin a lower vLLM and re-run.")

# vllm 0.11.2 requires transformers<5, so pip downgrades 5.x on install. ADR-0015
# accepts that, having measured it as a no-op for chat-template rendering — but
# only WITHIN the declared range. Landing outside it is a different change.
tf = md.version("transformers")
major, minor = (int(x) for x in tf.split(".")[:2])
if not (major == 4 and minor >= 56):
    sys.exit(
        f"\ntransformers {tf} is outside the range ADR-0015 pins (>=4.56,<5).\n"
        "vllm 0.11.2 requires transformers<5; a version outside the tested range\n"
        "has not been checked for chat-template equivalence."
    )
print(f"  transformers {tf}  (ADR-0015 range >=4.56,<5)")
print(f"  vllm  {md.version('vllm')}  (metadata; import is checked next)")
print("  OK")
PY

# `import vllm` runs platform detection, which probes CUDA. On THIS login node
# GPU access is blocked and such a probe BLOCKS rather than returning False —
# the same hazard that once hung the test suite. So the import is attempted with
# a hard timeout here and is NOT the authoritative gate: a timeout means "cannot
# be determined on the login node", which is different from "vLLM is broken".
# The authoritative import check is slurm/00_env_test.sbatch section 2b, which
# runs inside an allocation and exits non-zero if the import fails.
say "Attempting the vLLM import (best-effort on a login node; 180s cap)"
if timeout 180 python -c "import vllm, sys; print('  import vllm OK  version', vllm.__version__)"; then
  :
else
  rc=$?
  if [ "$rc" -eq 124 ]; then
    warn "import vllm timed out after 180s — expected on a GPU-blocked login node."
    warn "NOT treated as a failure. It is verified for real on a GPU node by"
    warn "  sbatch --partition=gpu-short --gres=gpu:1 slurm/00_env_test.sbatch"
  else
    warn "import vllm FAILED (exit ${rc}) for a reason other than a timeout."
    warn "Read the traceback above before continuing; the .so scan follows."
  fi
fi

say "Confirming no CUDA-13 runtime is linked anywhere in the vLLM install"
# THIS is the authoritative login-node gate, and it never imports vllm:
# find_spec locates the package without executing it, so it cannot block on the
# CUDA probe. On 2026-09-25 this same scan reported {'13': 198} for vllm 0.26.0.
python - <<'PY'
import collections, importlib.util, pathlib, re, sys
spec = importlib.util.find_spec("vllm")
if spec is None or not spec.origin:
    sys.exit("  FAIL — vllm is not installed at all.")
root = pathlib.Path(spec.origin).parent
pat = re.compile(rb"libcudart\.so\.(\d+)")
counts, bad, n = collections.Counter(), [], 0
for so in root.rglob("*.so"):
    n += 1
    try:
        hits = {m.decode() for m in pat.findall(so.read_bytes())}
    except OSError:
        continue
    for h in hits:
        counts[h] += 1
    if "13" in hits:
        bad.append(so.relative_to(root))
print(f"  scanned {n} shared objects; libcudart references {dict(counts) or 'none'}")
if bad:
    print("  CUDA 13 references found in:", *[f"    {b}" for b in bad[:10]], sep="\n")
    sys.exit("  FAIL — this build cannot run on a CUDA 12.8 driver.")
if not n:
    sys.exit("  FAIL — no shared objects found under the vllm package; install looks broken.")
print("  OK — none need libcudart.so.13")
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
