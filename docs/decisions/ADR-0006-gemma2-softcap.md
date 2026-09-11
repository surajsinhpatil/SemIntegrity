# ADR-0006 — Gemma-2 soft-capping preflight gate

**Kind:** METHODOLOGY

**Status:** PROPOSED — AWAITING RESEARCHER APPROVAL — see Q13
**Date:** 2026-09-11

## Context
§4.6 records that Gemma-2 uses attention logit soft-capping and sliding-window
attention, and that some FlashAttention-2 / vLLM builds have silently produced
degraded output without soft-capping support. Silent degradation is
indistinguishable from genuine model inconsistency, so an undetected failure
would not break the study — it would produce a plausible but wrong result for
one of the four model families.

The proposal requires a "known-good reference" but does not define one.

## Decision (proposed)
`scripts/models/gemma2_softcap_check.py` must pass before any Gemma-2 result is
admitted to the study:

1. **Version assertion** — record the vLLM/transformers/FlashAttention versions
   and assert the serving stack reports soft-capping enabled.
2. **Reference comparison** — generate a fixed prompt set under the production
   vLLM path **and** under HuggingFace `transformers` with eager attention (slow
   but correct), and require agreement at the canonical-answer level.
3. **Archive** both output sets and the version matrix under
   `results/manifests/gemma2_preflight/`.

`configs/models/gemma2-9b.yaml` carries `blocked_until_preflight_passes: true`;
the inference runner refuses to run Gemma-2 while `preflight_status: NOT_RUN`.

## Consequences
One extra job before the main run, and a slow eager-attention reference pass.
Cheap relative to the alternative, which is a wrong per-family result that no
downstream analysis could detect.
