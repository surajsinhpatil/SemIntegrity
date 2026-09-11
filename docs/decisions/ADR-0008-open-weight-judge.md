# ADR-0008 — Open-weight D3 judge

**Kind:** METHODOLOGY

**Status:** APPROVED BY RESEARCHER 2026-09-11 · resolves Q3
**Date:** 2026-09-11

## Context
§4.8.5 requires a judge "external to every evaluated model", version-pinned,
with "a strong open-weight judge on a stratified subset as a reproducibility
check". No model was named. Appendix A.1 implied a closed API judge, having
migrated the reproducibility concern from the evaluated set onto the judge.

## Decision
**`microsoft/phi-4` (14B, bf16) as the primary judge**, with
**`allenai/OLMo-2-1124-13B-Instruct`** on a stratified 15% subset as the
cross-family reproducibility check. Both pinned to exact revisions before any
judging run.

## Rationale
* **Externality.** Phi (Microsoft) and OLMo (AI2) are independent lineages; the
  seven evaluated models span Llama, Mistral, Qwen and Gemma.
* **Reproducibility.** Appendix A.1 removed the closed model from the evaluated
  set specifically to eliminate API version drift and deprecation risk. Choosing
  an open-weight judge removes it from the detection stack too, rather than
  relocating it there. The judge becomes re-runnable from pinned weights years
  later.
* **Cost.** ~23,520 judgements move from an API budget line (~14M in / 3.5M out
  tokens) to roughly 2–4 GPU-hours on the existing allocation.
* **Fit.** 14B in bf16 fits one 40 GB GPU — the same class of resource the
  evaluated models already need.

## The lineage contamination trap
"Different organisation" is **not** the externality test; shared lineage is.
Several strong open-weight judges are disqualified because they are built on an
evaluated family's base model — `DeepSeek-R1-Distill-Qwen-*` (Qwen base),
`DeepSeek-R1-Distill-Llama-*` and `Llama-*-Nemotron-*` (Llama base). Command-R
is excluded separately for its non-commercial licence, which conflicts with the
§5.6 release plan. Recorded in `configs/models/_judge.yaml:disqualified`.

## Consequences
* **The reproducibility check changes meaning.** §4.8.5 paired a closed primary
  with an open-weight check. With an open-weight primary, the second judge is a
  **cross-family agreement** check instead. The paper must describe it that way.
* **Judge ceiling.** A 14B judge is weaker than a frontier model, so D3's
  measured precision/recall against human gold may be lower than the proposal
  anticipated. This is a *finding about D3 as deployed*, not a flaw — §4.8.5
  already frames D3 as a baseline (after Mündler et al.), and RQ4 asks how
  reliable these detectors are, not how reliable the best possible judge is.
  The limitation is stated explicitly in the write-up.
* The family-affinity check (§4.8.5) is still run: an open-weight judge has no
  Qwen lineage, but the point is to measure that rather than assume it.
* If Phi-4 proves degenerate on the dev split (pilot criterion `NONDEGEN`),
  fall back to IBM Granite 3.x or a larger OLMo-2 — recorded as alternatives.
