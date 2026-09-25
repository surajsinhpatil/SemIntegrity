# ADR-0013 — vLLM 0.19.1 is the single inference stack

**Kind:** METHODOLOGY

**Status:** ACCEPTED — researcher instruction, 2026-09-25
**Date:** 2026-09-25
**Supersedes:** ADR-0012

## Context
ADR-0012 proposed abandoning vLLM for `transformers` on the grounds that no
vLLM build can run on this cluster's CUDA 12.8 driver (570.158.01). The
researcher rejected that proposal and directed that **vLLM remain the sole
inference backend**, with the methodology otherwise unchanged.

ADR-0012's evidence was correct but incomplete. Its two failed attempts
(`vllm` 0.30.0, then 0.26.0 with `torch==2.11.0+cu128`) both genuinely link
`libcudart.so.13`. Its generalisation — "every published wheel from 0.22
onward" — understated the range and, more importantly, stopped the search at
0.22 instead of continuing downward.

Reading the `DT_NEEDED` strings directly out of the published manylinux wheels
gives the real boundary:

| vLLM | torch pin | CUDA runtime linked |
|---|---|---|
| 0.15.0 | 2.9.1 | **12** |
| 0.17.0 – 0.19.1 | 2.10.0 | **12** |
| 0.20.2 – 0.26.0 | 2.11.0 | 13 |
| 0.27.0 – 0.30.0 | 2.13.0 | 13 |

A vLLM wheel's `torch` pin does **not** track its own CUDA linkage: 0.20.2
through 0.26.0 pin a torch for which a cu128 build exists, while their own
extensions still require CUDA 13. That is why pinning torch to cu128 fixed
torch and not vLLM.

## Decision
Pin **vLLM 0.19.1** as the single inference stack for every evaluated model.

0.19.1 is the newest CUDA 12 release that does not also require
`transformers<5`. Releases 0.17.0–0.19.0 do, which would force the installed
`transformers` 5.x down to 4.x and change chat-template rendering — and the
chat template is recorded per response as `chat_template_hash`, so that is not
a free change. 0.19.1 admits `transformers>=5.5.1`, leaving it untouched.

The resulting stack:

| Component | Version |
|---|---|
| Python | 3.11 |
| torch | 2.10.0+cu128 |
| torchvision | 0.25.0+cu128 |
| torchaudio | 2.10.0+cu128 |
| vLLM | 0.19.1 |
| transformers | 5.x (unchanged) |

## Consequences
- **torch moves 2.11.0 → 2.10.0.** vLLM 0.19.1 pins it. torch 2.10.0+cu128
  supports A100 (sm80) and bf16; both are re-verified on a GPU node rather than
  assumed.
- `TransformersBackend` stays in the codebase behind the `Backend` protocol but
  is **not selected**. `backend: vllm` is set in
  `configs/models/_defaults.yaml`, and the code-level fallback in `smoke.py` and
  `run_pilot.py` is `vllm`, so an absent config key cannot silently select
  another engine.
- §4.13 ("a single inference stack") is satisfied by vLLM, as originally
  designed. No decoding, prompt, probe, or detector definition changes.
- The wheel is `manylinux_2_31`; the install script gates on glibc ≥ 2.31
  rather than discovering this mid-install.

## Verification
`scripts/cluster/fix_torch_cuda.sh` refuses to finish unless, in order: torch
reports CUDA 12.x; `import vllm` succeeds; and a scan of every `.so` under the
installed `vllm` package finds no `libcudart.so.13` reference.
