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

source slurm/templates/_common.sh
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
python3 - <<'PY'
try:
    import torch
    print("torch", torch.__version__, "| cuda", torch.version.cuda)
    n = torch.cuda.device_count()
    print("gpu count:", n)
    for i in range(n):
        p = torch.cuda.get_device_properties(i)
        print(f"  [{i}] {p.name}  {p.total_memory/2**30:.1f} GiB  sm_{p.major}{p.minor}")
    print("bf16 supported:", torch.cuda.is_bf16_supported() if torch.cuda.is_available() else "n/a")
    print("  (bf16 is REQUIRED — §4.6 uses it uniformly for every evaluated model)")
except Exception as e:
    print("torch unavailable:", e)
PY

echo
echo "--- 3. project config loads and unit tests pass ---"
python3 -m pytest -q -m "not gpu and not network" || echo "UNIT TESTS FAILED"

echo
echo "--- 4. weight cache location and free space ---"
echo "HF_HOME=${HF_HOME}"
df -h "${HF_HOME%/*}" | tail -1
echo "env test complete"
