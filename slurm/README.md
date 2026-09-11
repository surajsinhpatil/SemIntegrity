# Slurm infrastructure

## Rule
The login node is for editing, git, lightweight commands, job status and
`sbatch`. **All CPU-heavy and GPU-heavy computation goes through Slurm.**
`scripts/_guard_login_node.sh` enforces this for shell entry points.

## Why the templates have no `--partition`
Partition names, GPU gres strings and QoS are cluster-specific. Guessing them
produces jobs that queue forever or are rejected. Run

```bash
bash scripts/cluster/probe_cluster.sh
```

record the real values in `configs/cluster/cluster.yaml`, then
`scripts/slurm/render_jobs.py` materialises `slurm/*.sbatch` from these
templates with the correct directives filled in.

## Escalation order — never skip a step
| # | Job | Gate |
|---|---|---|
| 0 | `00_env_test.sbatch` | interpreter, imports, GPU visible, unit tests pass |
| 1 | `10_smoke_inference.sbatch` | one small model, 8 prompts, provenance written |
| 2 | model-loading validation for **every** model incl. 70B | weights load in bf16, chat template hash recorded |
| 3 | Gemma-2 soft-capping preflight | output matches a known-good reference |
| 4 | pilot (`configs/inference/pilot.yaml`) | Phase 3 go/no-go criteria |
| 5 | full inference | only after all of the above |

## Checkpointing and resume
Every inference job writes JSONL incrementally with `fsync`, keyed by
`(experiment_id, model_id, probe_id, sample_index)`. Re-submitting the same job
skips completed keys and appends the remainder. Results are never rewritten in
place, so a walltime kill costs at most the in-flight batch.
