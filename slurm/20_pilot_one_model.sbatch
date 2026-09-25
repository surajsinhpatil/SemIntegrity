#!/bin/bash
#SBATCH --job-name=semint-pilot1
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#
# Step 2: the ONE-MODEL pilot — 12 pilot constraints x 8 probes (K=8, the
# design primary) on a single model, then Stage 0 and D1. The reduced-scope
# pilot the professor
# advised: the proposal's Phase 3 uses 3 models, and this runs the first one.
#
#   sbatch --partition=<from probe> --gres=gpu:1 slurm/20_pilot_one_model.sbatch
#
# PRECONDITIONS (the script checks them and exits rather than burning GPU time):
#   * 00_env_test and 10_smoke_inference have passed
#   * data/benchmark/pilot/{constraints,probes}.jsonl exist and validate
#   * the model revision is pinned

source "${SLURM_SUBMIT_DIR:-$PWD}/slurm/templates/_common.sh"
job_provenance

MODEL="${MODEL:-qwen25-3b}"
PILOT_DIR="data/benchmark/pilot"

if [[ ! -f "${PILOT_DIR}/constraints.jsonl" ]]; then
  echo "ABORT: ${PILOT_DIR}/constraints.jsonl does not exist." >&2
  echo "The pilot constraints must be authored and approved before this runs." >&2
  exit 2
fi

echo "--- preflight: validate the pilot benchmark ---"
python3 -m semintegrity.benchmark.validate --split pilot || exit 3

echo
echo "--- inference: ${MODEL} ---"
OUT="results/raw/pilot/${MODEL}.jsonl"
python3 -m semintegrity.inference.run_pilot \
  --model "${MODEL}" \
  --split pilot \
  --out "${OUT}" || exit 4

echo
echo "--- Stage 0 + D1 ---"
python3 -m semintegrity.analysis.pilot_report \
  --raw "${OUT}" \
  --split pilot \
  --out "results/analysis/pilot_${MODEL}.json"

echo "pilot complete"
