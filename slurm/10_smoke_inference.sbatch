#!/bin/bash
#SBATCH --job-name=semint-smoke
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=00:40:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#
# Step 1: the smallest REAL inference. ONE model, 8 prompts, full provenance.
# Must pass before any larger job is submitted.
#
#   sbatch --partition=<from probe> --gres=gpu:1 slurm/10_smoke_inference.sbatch
#
# Model defaults to qwen25-3b: the smallest evaluated model AND the only one
# that is not gated on Hugging Face, so it needs no licence acceptance.
#   MODEL=qwen25-7b sbatch ... slurm/10_smoke_inference.sbatch

source slurm/templates/_common.sh
job_provenance

MODEL="${MODEL:-qwen25-3b}"
OUT="results/raw/_smoke/${MODEL}-${SLURM_JOB_ID}.jsonl"
echo "model: ${MODEL}"
echo "out  : ${OUT}"

python3 -m semintegrity.inference.smoke \
  --model "${MODEL}" \
  --n-prompts 8 \
  --batch-size 4 \
  --out "${OUT}"

echo
echo "--- smoke test finished; inspect ${OUT} ---"
