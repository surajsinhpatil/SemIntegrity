# Environment specification

Two-layer scheme, because exact pins depend on the cluster's CUDA/driver pair,
which is not known until `scripts/cluster/probe_cluster.sh` has been run.

| Layer | Files | Meaning |
|---|---|---|
| **Declared** | `*.in` | Human-authored constraints (ranges). Edited by hand. |
| **Locked** | `lock/*.txt` | `pip freeze` output captured **on the target node**. Exact, reproducible, committed. |

Never hand-edit a lock file. Regenerate it:

```bash
bash scripts/env/freeze_lock.sh <env-name>   # writes requirements/lock/<env-name>.txt
```

## Environments

| Name | Node | Purpose |
|---|---|---|
| `login` | cluster login node / laptop | authoring, KB queries, analysis prep, Slurm submission. **No torch.** |
| `gpu`   | Slurm GPU node | vLLM + transformers inference, NLI (D2), logprob scoring (D4) |
| `analysis` | login node or laptop | statistics, GLMM, figures |

> **Rule:** `login` intentionally has no `torch`, so that a mis-typed command
> cannot start model inference on the login node.

## CUDA / vLLM pairing — UNRESOLVED

`torch` and `vllm` versions must match the cluster CUDA toolkit. `vllm` also
gates Gemma-2 correctness (attention logit soft-capping — see
`docs/decisions/ADR-0006-gemma2-softcap.md`). **Do not pin these until the
cluster probe has reported `nvidia-smi` driver version and available modules.**
