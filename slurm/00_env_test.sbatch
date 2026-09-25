#!/bin/bash
#SBATCH --job-name=semint-envtest
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=00:15:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#
# Step 0 of the escalation. Verifies the environment on a REAL compute node.
# Downloads nothing, loads no model.
#
# Partition and GPU are NOT hard-coded — pass them on the command line, which
# overrides any #SBATCH directive:
#
#   sbatch --partition=<from probe> --gres=gpu:1 slurm/00_env_test.sbatch

source "${SLURM_SUBMIT_DIR:-$PWD}/slurm/templates/_common.sh"
job_provenance

echo "--- 1. interpreter and package imports ---"
python3 - <<'PY'
import importlib, sys
print("python", sys.version.split()[0])
for m in ["semintegrity", "yaml", "pydantic", "numpy", "pandas", "transformers", "vllm", "torch"]:
    try:
        mod = importlib.import_module(m)
        print(f"  OK      {m:16s} {getattr(mod, '__version__', '')}")
    except Exception as e:
        print(f"  MISSING {m:16s} {type(e).__name__}")
PY

echo
echo "--- 2. GPU visibility and bf16 support ---"
# This step GATES everything downstream. §4.6 requires bf16 uniformly for every
# evaluated model, so a node that cannot do bf16 is not a node this study can
# use. Printing the problem and exiting 0 would let a broken stack through.
python3 - <<'PY' || { echo "GPU/bf16 CHECK FAILED — do not submit inference jobs"; exit 1; }
import sys
try:
    import torch
except ImportError as exc:
    sys.exit(f"torch is not installed: {exc}")

print("torch", torch.__version__, "| built for CUDA", torch.version.cuda)

built = (torch.version.cuda or "").split(".")[0]
if built and built != "12":
    sys.exit(
        f"WRONG CUDA BUILD: torch was built for CUDA {torch.version.cuda}, but this "
        "cluster's driver is 570.158.01 (CUDA 12.8) and cannot run it. "
        "Fix: bash scripts/cluster/fix_torch_cuda.sh"
    )

if not torch.cuda.is_available():
    sys.exit("torch.cuda.is_available() is False — no usable GPU in this allocation")

n = torch.cuda.device_count()
print("gpu count:", n)
for i in range(n):
    props = torch.cuda.get_device_properties(i)
    print(f"  [{i}] {props.name}  {props.total_memory / 2**30:.1f} GiB  sm_{props.major}{props.minor}")

if not torch.cuda.is_bf16_supported():
    sys.exit("bf16 is NOT supported — §4.6 requires it for every evaluated model")
print("bf16 supported: yes  (§4.6 requires it for every evaluated model)")

# Prove a real bf16 kernel runs, not just that the capability flag is set.
x = torch.randn(512, 512, dtype=torch.bfloat16, device="cuda")
checksum = (x @ x).float().sum().item()
print(f"bf16 matmul on device: OK (checksum {checksum:.1f})")
PY

echo
echo "--- 3. project config loads and unit tests pass ---"
python3 -m pytest -q -m "not gpu and not network" || echo "UNIT TESTS FAILED"

echo
echo "--- 4. weight cache location and free space ---"
echo "HF_HOME=${HF_HOME}"
df -h "${HF_HOME%/*}" | tail -1
echo "env test complete"
