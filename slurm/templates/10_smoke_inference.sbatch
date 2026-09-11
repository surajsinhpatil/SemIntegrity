#!/bin/bash
#SBATCH --job-name=semint-smoke
#SBATCH --output=slurm/logs/%x-%j.out
#SBATCH --error=slurm/logs/%x-%j.err
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
# #SBATCH --partition=<from probe>
# #SBATCH --gres=gpu:1
#
# Smallest possible real inference: ONE model (qwen25-3b, the cheapest), a
# handful of prompts, full provenance logging. This must pass before any
# larger job is submitted.
#
#   MODEL=qwen25-3b sbatch slurm/templates/10_smoke_inference.sbatch

source slurm/templates/_common.sh
job_provenance

MODEL="${MODEL:-qwen25-3b}"
echo "smoke model: ${MODEL}"

python3 -m semintegrity.inference.smoke \
  --model "${MODEL}" \
  --n-prompts 8 \
  --out "results/raw/_smoke/${MODEL}-${SLURM_JOB_ID}.jsonl"
