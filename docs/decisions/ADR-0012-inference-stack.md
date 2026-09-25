# ADR-0012 — transformers, not vLLM, as the inference stack

**Kind:** METHODOLOGY

**Status:** REJECTED by the researcher, 2026-09-25 — superseded by ADR-0013
**Date:** 2026-09-25

> **Rejected.** The researcher directed that vLLM remain the sole inference
> backend. The claim below that "every published wheel from 0.22 onward" links
> CUDA 13 is also factually wrong in one direction that matters: the search
> stopped at 0.22 and never went lower. vLLM **0.19.1** links `libcudart.so.12`
> and runs on this driver. See ADR-0013.

## Context
§4.13 requires "a single inference stack, since mixing frameworks across models
would introduce an uncontrolled variable". It names no specific engine; earlier
configs assumed vLLM.

**vLLM cannot run on this cluster.** Every published wheel from 0.22 onward links
the CUDA 13 runtime:

```
ImportError: libcudart.so.13: cannot open shared object file
```

The BITS CSIS driver is **570.158.01 = CUDA 12.8**. CUDA 13 needs a 580+ driver.
Two attempts failed:

1. `pip install vllm` → 0.30.0, which pins `torch==2.13.0` whose default PyPI
   wheel is cu130. On the GPU node: *"The NVIDIA driver on your system is too
   old (found version 12080)."*
2. Pinning torch to `2.11.0+cu128` and vLLM to 0.26.0 (the last release pinning
   that torch) fixed torch but not vLLM: its own compiled extension still links
   `libcudart.so.13`.

The driver is administered by the cluster staff and is not ours to change.

Meanwhile the 2026-09-25 GPU environment test confirms the alternative works:

```
torch 2.11.0+cu128 | built for CUDA 12.8
[0] NVIDIA A100 80GB PCIe  79.3 GiB  sm_80
bf16 supported: yes
bf16 matmul on device: OK
```

## Decision (proposed)
Use **HuggingFace `transformers`** as the single inference stack for every
evaluated model. `TransformersBackend` sits behind the existing `Backend`
protocol, so `VLLMBackend` remains available if a CUDA 12 build appears, and the
choice is one config key (`backend:` in `configs/models/_defaults.yaml`).

## Why the workload suits it
* Track A caps generations at **24 new tokens** (§4.4.3). vLLM's advantage is
  continuous batching over long sequences, which this study never exercises.
* Every model up to 14B fits on **one A100 80GB** in bf16 with room for KV cache.
* D4's teacher-forced candidate scoring (§4.8.6) reads log-probabilities
  directly, which is simpler through `transformers` than through a serving engine.
* Total load is ~21,750 short generations — small, as §4.13 itself notes.

## Consequences
* **§4.13's requirement is still met**: one stack, held constant across all
  models. The requirement was never "vLLM".
* **Provenance stays honest.** The `vllm_version` field (§4.6) records
  `"unavailable"` rather than being dropped, so the record shows which engine
  actually ran.
* **The 70B ceiling run is the real cost.** Llama-3.3-70B at ~141 GB needs
  `device_map="auto"` across 2 A100s, and generation will be materially slower
  than vLLM. At ~1,000 short generations for that model it should remain
  tractable, but it must be timed at Phase 6 rather than assumed.
* **Throughput is lower throughout.** Irrelevant at this scale; it would matter
  if the probe budget grew by an order of magnitude.
* Batch generation uses **left padding**, without which shorter prompts in a
  batch generate from pad tokens instead of their own text.

## Alternatives rejected
* **Build vLLM from source against CUDA 12.8** — possible, but a long compile on
  a shared login node, and a bespoke build undermines the reproducibility that
  pinned wheels provide.
* **Ask the admins to upgrade the driver** — affects every user of a shared
  cluster for one project's convenience.
* **vLLM ≤ 0.21** — declares no CUDA-13 dependencies and might link CUDA 12, but
  it is far behind, and Gemma-2 soft-capping support (§4.6, ADR-0006) is exactly
  the kind of thing an old release gets wrong. Worth revisiting only if
  transformers proves inadequate.
