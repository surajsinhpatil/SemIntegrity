# ADR-0015 — vLLM 0.11.2 is the single inference stack (glibc 2.28 constraint)

**Kind:** METHODOLOGY

**Status:** ACCEPTED — researcher decision, 2026-09-25
**Date:** 2026-09-25
**Supersedes:** ADR-0013 (which superseded ADR-0012)

## Context

ADR-0013 pinned vLLM **0.19.1** as the newest release linking `libcudart.so.12`.
That finding was correct and still is. What it did not check was the host's
C library.

The cluster was reachable again on 2026-09-25 and reports:

```
Rocky Linux 8.10 (Green Obsidian)   kernel 4.18
ldd (GNU libc) 2.28
Python 3.11.16 · torch 2.11.0+cu128 · transformers 5.17.0 · vllm 0.26.0
```

**glibc 2.28 makes ADR-0013 unexecutable.** The vLLM 0.19.1 wheel is
`manylinux_2_31` and requires glibc ≥ 2.31; pip will not select it on this host.
This is not a preference, it is a hard packaging constraint.

Worse, the two requirements appeared mutually exclusive across the modern
release line. Reading every published `x86_64` wheel tag together with the
`DT_NEEDED` strings of the compiled extensions gives both dimensions at once:

| vLLM | wheel tag | min glibc | CUDA runtime linked | usable here |
|---|---|---|---|---|
| 0.1.4 – 0.11.2 | `manylinux1` | 2.5 | **12** | **YES** |
| 0.12.0 – 0.19.1 | `manylinux_2_31` | 2.31 | 12 | no — glibc |
| 0.20.0 – 0.20.2 | `manylinux_2_35` | 2.35 | 13 | no — both |
| 0.21.0 | `manylinux_2_24` | 2.24 | 13 | no — CUDA |
| 0.22.0 – 0.30.0 | `manylinux_2_28` | 2.28 | 13 | no — CUDA |

Every CUDA-12 release from 0.12.0 onward is `manylinux_2_31`; the first
`manylinux_2_28` release is 0.22.0, which is already CUDA-13. The only overlap
is the **`manylinux1` line, 0.11.2 and below**.

Two traps this table closes, both of which have already misled this project
once:

* **A wheel's torch pin does not track its own CUDA linkage.** 0.20.0–0.26.0
  pin `torch==2.11.0`, for which a cu128 build exists, yet their extensions
  still require CUDA 13. Pinning torch to cu128 fixes torch and not vLLM.
* **Neither does the dependency metadata.** 0.20.0 and 0.21.0 declare no `cu13`
  dependency at all, yet both link `libcudart.so.13`. Only the binary is
  authoritative. ADR-0012 reasoned from metadata and reached the wrong
  conclusion; ADR-0013 reasoned from binaries but stopped before checking glibc.

## Decision

Pin **vLLM 0.11.2** as the single inference stack for every evaluated model.

| Component | Version | Why |
|---|---|---|
| Python | 3.11.16 | already installed; 0.11.2 admits `>=3.10,<3.14` |
| torch | 2.9.0+cu128 | pinned by vLLM 0.11.2; `manylinux_2_28` wheel exists for cp311 |
| torchvision | 0.24.0+cu128 | companion |
| torchaudio | 2.9.0+cu128 | companion |
| vLLM | **0.11.2** | last `manylinux1` release; links `libcudart.so.12` |
| transformers | `>=4.56,<5` | required by vLLM 0.11.2 |

### Verification performed before deciding

Read directly out of the published wheel, not inferred:

```
vllm 0.11.2  vllm/vllm_flash_attn/_vllm_fa2_C.abi3.so
  DT_NEEDED       : libtorch.so, libcudart.so.12, libtorch_cpu.so,
                    libtorch_cuda.so, libc10_cuda.so, libc10.so, ...
  max GLIBC symbol: 2.14           (host provides 2.28)
```

And on the installed-but-unusable package, on the cluster itself:

```
vllm 0.26.0 : 16 shared objects scanned, libcudart references {'13': 198}
```

## Consequences

* **transformers drops 5.17.0 → 4.x.** ADR-0013 rejected the 0.17.0–0.19.0 line
  partly for this reason, on the grounds that chat-template rendering is
  recorded per response as `chat_template_hash`. That objection was **measured
  and does not hold**:

  | field | transformers 5.0.0 | transformers 4.57.6 |
  |---|---|---|
  | `chat_template_sha256` | `cd8e9439…` | `cd8e9439…` |
  | rendered prompt sha256 | `bc824e05…` | `bc824e05…` |
  | rendered length / tokens | 503 / 104 | 503 / 104 |

  Byte-identical for Qwen2.5-3B at the pinned revision. Structurally this is
  expected: `chat_template_hash` is taken over `tokenizer.chat_template`, a
  string that ships in the model repository and is fixed by the pinned
  revision, so the library version cannot change it.

  **Scope of that claim:** Qwen2.5-3B only, one prompt. Gemma-2 and
  Mistral-v0.3 take the `prepend_to_first_user` path and are not covered.
  `scripts/models/audit_chat_templates.py` must be run per model and its
  `chat_template_hash` recorded before that model's results are admitted.

* **§4.13 is satisfied.** One inference stack, held constant across all seven
  models. Zero cluster results exist at the time of this decision, so
  transformers 4.x is constant from the first generation onward rather than
  changed mid-study. The `transformers_version` provenance field records it.

* **Gemma-2 remains gated.** Gemma-2 landed in vLLM 0.5.1 and soft-capping in
  the attention path settled well before 0.11.x, but ADR-0006 refuses to assume
  this, and 0.11.2 being an older release raises rather than lowers the residual
  risk. `blocked_until_preflight_passes: true` stays set; the preflight gate is
  what converts that risk into a detected failure instead of a plausible wrong
  number for one model family.

* **Llama-3.3-70B at tensor_parallel_size=2 is unaffected.** vLLM has supported
  tensor parallelism since 0.1.x and Llama-3.3 is architecturally Llama-3.1.

* **Quota, not disk, is the binding storage limit.** The account reports 713 G
  used against a 1000 G hard limit — roughly 286 G of headroom, shared with
  other students. All seven models in bf16 are ≈244 G, so models MUST be staged
  one at a time and evicted. Caching all seven at once would crowd out labmates
  and risk hitting the hard limit mid-run.

* **`requirements/lock/cluster-gpu.txt` is stale.** It was generated at
  2026-09-25T12:25:54Z, before vLLM 0.26.0 was installed, so it does not
  describe the environment being repaired and is not a restore point for it.
  It is rewritten at the end of `scripts/cluster/fix_torch_cuda.sh`.

## Alternatives rejected

* **Singularity container** (`singularity/4.4.0` is available) — would carry its
  own glibc and permit any CUDA-12 vLLM with transformers 5.x, with a pinned
  image digest giving stronger reproducibility. Rejected for now: it adds
  10–20 G to an already tight shared quota, requires the image to be staged for
  compute nodes that have no network, and introduces a second artifact to
  reproduce. **It remains the designated fallback** if the Gemma-2 preflight
  fails under 0.11.2 — it can be applied to that model family alone without
  redoing anything else.
* **Building vLLM from source against CUDA 12.8** — a long compile on a shared
  login node, and a bespoke build undermines the reproducibility that pinned
  wheels provide.
* **Asking the admins to upgrade the driver or the OS** — affects every user of
  a shared cluster for one project's convenience.
* **transformers, not vLLM** — this is ADR-0012, already rejected by the
  researcher. vLLM remains the inference backend.

## Verification gate

`scripts/cluster/fix_torch_cuda.sh` refuses to finish unless, in order:
glibc satisfies the wheel tag; torch reports CUDA 12.x both before and after the
vLLM install; `import vllm` succeeds; and a scan of every `.so` under the
installed `vllm` package finds no `libcudart.so.13` reference.
