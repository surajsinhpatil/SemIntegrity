#!/bin/bash
#SBATCH --job-name=semint-envtest
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=00:10:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
# --- PARTITION AND GPU REQUEST DELIBERATELY OMITTED ------------------------
# Fill in after scripts/cluster/probe_cluster.sh reports real partition names.
# Submitting with a guessed partition name is how jobs sit in the queue
# forever, so this template refuses to guess.
#   #SBATCH --partition=<from probe>
#   #SBATCH --gres=gpu:1

source slurm/templates/_common.sh
job_provenance

echo "--- step 1: interpreter and package import ---"
python3 - <<'PY'
import importlib, sys
print("python", sys.version)
for m in ["semintegrity", "yaml", "pydantic", "numpy", "pandas"]:
    try:
        mod = importlib.import_module(m)
        print(f"  OK      {m} {getattr(mod, '__version__', '')}")
    except Exception as e:
        print(f"  MISSING {m}: {e}")
PY

echo "--- step 2: torch / GPU visibility ---"
python3 - <<'PY'
try:
    import torch
    print("torch", torch.__version__, "cuda", torch.version.cuda)
    print("gpu count:", torch.cuda.device_count())
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        print(f"  [{i}] {p.name}  {p.total_memory/2**30:.1f} GiB  sm_{p.major}{p.minor}")
    print("bf16 supported:", torch.cuda.is_bf16_supported() if torch.cuda.is_available() else "n/a")
except Exception as e:
    print("torch unavailable:", e)
PY

echo "--- step 3: project config loads and unit tests pass ---"
python3 -m pytest -q tests/unit || echo "UNIT TESTS FAILED"
echo "env test complete"
