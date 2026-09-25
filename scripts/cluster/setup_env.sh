#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build the SemIntegrity Python environment on the BITS CSIS cluster.
#
# LOGIN NODE ONLY — it needs the internet, and compute nodes have none
# (verified 2026-09-25: DNS does not resolve there).
#
#   bash scripts/cluster/setup_env.sh            # base env (no torch, no vllm)
#   bash scripts/cluster/setup_env.sh --gpu      # base + torch + vLLM (~10 GB)
#
# Shared-account discipline: EVERYTHING lands inside this project directory.
# conda packages, pip cache, HuggingFace cache and temporary files are all
# redirected away from /nfs_home/users/yashsinha, which several students share.
#
# Idempotent: safe to re-run. It will not rebuild an environment that exists.
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_PREFIX="${ROOT}/.conda-env"
PY_VERSION="3.11"

WITH_GPU=0
[[ "${1:-}" == "--gpu" ]] && WITH_GPU=1

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!!  %s\033[0m\n' "$*" >&2; }

# Conda's and Lmod's hook scripts are not `set -u` safe. This cluster ships
# etc/conda/deactivate.d/unset_pythonpath.sh, which reads $CONDA_OLD_PYTHONPATH
# with no default and aborts the whole script under `set -u`. It exists because
# the cluster exports a global PYTHONPATH for Intel oneAPI.
#
# So: relax nounset around third-party hooks only, and restore it immediately.
# The alternative — dropping `set -u` for the whole script — would lose the
# protection everywhere else.
nounset_off() { set +u; }
nounset_on()  { set -u; }

# --- refuse to run inside a compute allocation -----------------------------
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
  warn "This is running inside Slurm job ${SLURM_JOB_ID}."
  warn "Compute nodes have NO internet, so package installation will fail."
  warn "Run this on the login node instead."
  exit 2
fi

say "Project root: ${ROOT}"
df -h "${ROOT}" | tail -1

# --- keep every cache inside the project ------------------------------------
export CONDA_PKGS_DIRS="${ROOT}/.conda-pkgs"
export PIP_CACHE_DIR="${ROOT}/.pip-cache"
export HF_HOME="${ROOT}/hf_cache"
export TMPDIR="${ROOT}/.tmp"
export XDG_CACHE_HOME="${ROOT}/.cache"
mkdir -p "$CONDA_PKGS_DIRS" "$PIP_CACHE_DIR" "$HF_HOME" "$TMPDIR" "$XDG_CACHE_HOME"
say "Caches redirected into the project (shared account is left untouched)"
printf '  CONDA_PKGS_DIRS=%s\n  PIP_CACHE_DIR=%s\n  HF_HOME=%s\n  TMPDIR=%s\n' \
  "$CONDA_PKGS_DIRS" "$PIP_CACHE_DIR" "$HF_HOME" "$TMPDIR"

# --- conda ------------------------------------------------------------------
say "Loading miniconda module"
nounset_off
module load miniconda/default 2>/dev/null || warn "module load failed; trying conda on PATH"
nounset_on
command -v conda >/dev/null || { warn "conda not found; run 'module avail' and adjust"; exit 3; }
conda --version

CONDA_BASE="$(conda info --base)"
nounset_off
# shellcheck disable=SC1091
source "${CONDA_BASE}/etc/profile.d/conda.sh"
# Leave any environment that is already active, so `conda activate` below does
# not have to run a deactivate hook mid-script.
while [[ -n "${CONDA_PREFIX:-}" ]]; do conda deactivate || break; done
nounset_on

if [[ -d "$ENV_PREFIX" ]]; then
  say "Environment already exists at ${ENV_PREFIX} — reusing it"
else
  say "Creating Python ${PY_VERSION} environment at ${ENV_PREFIX}"
  # 3.11 deliberately: the system python is 3.6.8 (far too old) and the default
  # module is 3.13.7 (ahead of what vLLM supports). pyproject pins >=3.10,<3.12.
  nounset_off
  conda create -y -p "$ENV_PREFIX" "python=${PY_VERSION}" pip
  nounset_on
fi

nounset_off
conda activate "$ENV_PREFIX"
nounset_on
[[ "${CONDA_PREFIX:-}" == "$ENV_PREFIX" ]] || {
  warn "expected CONDA_PREFIX=${ENV_PREFIX} but got ${CONDA_PREFIX:-<unset>}"
  exit 4
}
say "Active interpreter"
python -VV
which python

# --- project package --------------------------------------------------------
say "Installing SemIntegrity (login-node dependencies: no torch, no vllm)"
python -m pip install --upgrade pip setuptools wheel
# [dev] pulls [analysis] transitively, which brings scipy. The design
# validator's entity-familiarity check (§4.3) needs it and now FAILS CLOSED
# without it, so a dev environment missing scipy cannot silently under-test.
python -m pip install -e "${ROOT}[dev]"

say "Confirming the analysis stack is present"
python - <<'PY'
import importlib, sys
missing = []
for m in ("scipy", "sklearn", "matplotlib", "krippendorff", "statsmodels"):
    try:
        mod = importlib.import_module(m)
        print(f"  OK      {m:14s} {getattr(mod, '__version__', '?')}")
    except ImportError:
        print(f"  MISSING {m}")
        missing.append(m)
if missing:
    sys.exit(f"analysis dependencies missing: {missing}")
PY

if [[ $WITH_GPU -eq 1 ]]; then
  say "Installing torch + vLLM (large — expect ~10 GB and several minutes)"
  # The driver is 570.158.01 / CUDA 12.8, which runs cu12x wheels. vLLM pins its
  # own torch, so torch is NOT installed separately: letting pip resolve it
  # avoids a version conflict that would surface only at model-load time.
  python -m pip install vllm
  say "Recording the resolved versions"
  python - <<'PY'
import importlib
for m in ("torch", "vllm", "transformers", "tokenizers"):
    try:
        mod = importlib.import_module(m)
        print(f"  {m:14s} {getattr(mod, '__version__', '?')}")
    except Exception as e:
        print(f"  {m:14s} MISSING ({type(e).__name__})")
PY
fi

# --- lock file --------------------------------------------------------------
say "Freezing the exact environment"
mkdir -p "${ROOT}/requirements/lock"
LOCK="${ROOT}/requirements/lock/cluster-$([[ $WITH_GPU -eq 1 ]] && echo gpu || echo login).txt"
{
  echo "# SemIntegrity locked environment"
  echo "# host      : $(hostname -f)"
  echo "# generated : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# python    : $(python -V 2>&1)"
  echo "# prefix    : ${ENV_PREFIX}"
  python -m pip freeze
} > "$LOCK"
say "Lock file written: ${LOCK#"${ROOT}/"} ($(wc -l < "$LOCK") lines)"

# --- verify -----------------------------------------------------------------
say "Running the test suite"
cd "$ROOT"
python -m pytest -q -m "not gpu and not network" || warn "TESTS FAILED — do not submit jobs yet"

cat <<EOF

$(printf '=%.0s' {1..70})
Environment ready.

Activate it in any future shell with:

  module load miniconda/default
  source \$(conda info --base)/etc/profile.d/conda.sh
  conda activate ${ENV_PREFIX}

Slurm jobs pick it up automatically via:

  export SEMINT_ENV_ACTIVATE=${ENV_PREFIX}

$(printf '=%.0s' {1..70})
EOF
