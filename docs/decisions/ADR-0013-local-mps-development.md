# ADR-0013 — Apple MPS as a development device, never for final results

**Kind:** METHODOLOGY

**Status:** PROPOSED — AWAITING RESEARCHER APPROVAL
**Date:** 2026-09-25

## Context
Cluster access is intermittent. The researcher's MacBook Air M4 has 16 GB
unified memory (11.8 GiB usable by MPS) and 44 GB free disk.

Measured on the machine, not assumed: **bf16 works on MPS for every operation a
transformer generation path uses** — matmul, softmax, layer_norm, gelu, silu,
scaled_dot_product_attention, topk, cumsum. So §4.6's bf16 requirement is
satisfiable locally.

What does *not* fit is everything else. Only Qwen2.5-3B (6.2 GB) runs in 16 GB;
Mistral-7B (14.5), Llama-3.1-8B (16), Gemma-2-9B (18.5), Qwen2.5-14B (29.5) and
Llama-3.3-70B (141) do not. Quantising them to fit is forbidden by §4.6:
*"Quantisation is not used selectively, because it would be confounded with model
family."*

## Decision (proposed)
MPS is supported as a **development and pilot** device. `TransformersBackend`
takes a `device` argument; `auto` prefers CUDA inside a Slurm allocation, then
MPS, then refuses CPU.

**Results produced on MPS must never appear in the final study.** Every number
reported in the paper comes from one uniform hardware configuration — the
cluster's A100 80GB — for all seven models.

## Why final results must be re-run
Merging runs from different machines is *technically* trivial: results are
append-only JSONL keyed by
`(experiment_id, model_id, probe_id, sample_index)`, so concatenation is enough.

But it would be methodologically wrong. Different kernels give different
numerics, and inconsistency is the dependent variable. If Qwen2.5-3B ran on
MPS while 7B and 14B ran on CUDA, the **within-family scale axis (§4.5) would be
confounded with hardware** — the one comparison it exists to make. The same
applies to the cross-family comparison.

This is detectable rather than silent: `gpu_model` is one of §4.6's required
provenance fields and MPS runs record `apple-mps:<chip>`. Detectable is enough
to catch a mistake; it is not enough to license one.

## Consequences
* The 12-constraint pilot, Stage 0, D0, D1, D2 and every analysis step can run
  on the laptop. Infrastructure failure never blocks the project completely.
* Phase 6 remains cluster-only, all seven models on identical hardware.
* CPU generation is refused outright: bf16 behaviour differs from both CUDA and
  MPS, and it would be unusably slow.
* MPS calls `torch.mps.synchronize()` before timing, since the queue is
  asynchronous and would otherwise measure submission rather than execution.
* An analysis-time guard should refuse `apple-mps:*` provenance in final result
  sets, in the same way `assert_no_stub_responses` refuses stub output. Not yet
  implemented — noted here so it is not forgotten.
