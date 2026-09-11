# SemIntegrity — progress summary

**Surajsinh Patil · M.E. Computer Science, BITS Pilani · 11 September 2026**
Topic P13 · Theme E — Evaluation & Standards

---

## Position

The methodology is frozen per proposal v2. Infrastructure, literature
verification and a **single-model pilot path** are complete. Following the
advice to start with one model before expanding, the pilot has been scoped to
**one model (Qwen2.5-3B-Instruct)** rather than the proposal's three.

Nothing has been run on GPU yet. No experimental result, human annotation or
model output exists, and none is claimed.

---

## Completed

### Phase 0 — literature verification: **12 of 12 resolved**

Every work in Appendix A.3 checked against ACL Anthology, OpenReview, PMLR and
arXiv. **7 verified as cited · 4 venue corrections · 1 downgraded to preprint.**

| Correction | Cited as | Actually |
|---|---|---|
| Mündler et al. (self-contradiction) | 2023 | **ICLR 2024** (2023 is the preprint) |
| Berglund et al. (Reversal Curse) | 2023 | **ICLR 2024** (2023 is the preprint) |
| ConCoRD | "2022" | **EMNLP 2022** |
| REPAIR / "Aligning with Logic" | unstated | **ICML 2025** |
| ChaosBench-Logic | unstated | **preprint only** — no peer-reviewed venue |

Three findings affect what the paper may claim:

1. **The D4 precedent holds, but the construction differs.** Tsujimura et al.
   (ACL 2026) do use Jensen–Shannon divergence — verified from the paper's own
   text, not a summary. But they compare a *prior* against a *posterior*
   scenario using sampled selection frequencies, explicitly *"rather than
   computing log probabilities over a pre-defined answer set"* — which is
   exactly what D4 does over K paraphrases. The precedent is real; the method is
   distinct, and related work should say so.
2. **The scale claim is confirmed.** "Belief consistency does not improve solely
   with model size scaling." The decision to state no scaling-law hypothesis is
   well founded.
3. **Flip-Flop Consistency is a mitigation method**, not a measurement study —
   it introduces an unsupervised training objective. It sits closer to ConCoRD
   than to ParaRel in the narrative.

### Phase 1 — representation infrastructure

Constraint / probe / response schemas · benchmark design validator · Wikidata
client with a frozen offline cache · D0 predicate framework with a freeze policy
and three-instance audit harness · probe factor generator.

### One-model pilot stack

Chat-template rendering with system-role merging · 22-field provenance capture ·
vLLM backend · resumable runner · Stage 0 canonicaliser · D1 detector · three
CLI entry points · three Slurm scripts.

**All 9 model revisions pinned to real, Hub-verified commit SHAs** (7 evaluated
models + 2 judges). No hash was written by hand.

---

## Verification

```
pytest -q                206 passed
ruff check               clean
coverage                 ~90%
scripts/demo_pipeline.py full workflow end to end, no GPU
```

Two bugs the tests caught before any GPU time was spent:

* **the resume key never resolved** — `model_id` lives inside the provenance
  block, so every resumed cluster job would have crashed on re-submission;
* a commit SHA written into documentation by hand diverged from the real one
  after 12 characters. A test now fails the suite on any SHA in the docs that
  matches no pinned config.

---

## Design decisions resolved

| Question | Resolution |
|---|---|
| Dev/test split vs the 60/60 confirmatory arms | separate 24-constraint dev set, disjoint from the 120 |
| D3 judge (must be outside all 4 evaluated families) | open-weight **Phi-4**, cross-checked by **OLMo-2** — removes API cost and version drift |
| Probe factors: 24 cells but K=8 | 2×2×2 within constraint + syntax rotation → **exactly 10 per cell per class** |
| Probe-level covariates on a constraint-level model | disaggregated binomial cells — a preregistered deviation |

**Two methodology questions remain open and are flagged, not decided:** whether
`polarity` belongs inside the probe equivalence key (Q21), and which D0 verdict —
pairwise or set-level — the paper reports as "D0" (Q22). Both are implemented
behind a single named switch so the decision can still go either way.

---

## Immediate next step

**One read-only cluster probe.** It submits no job, downloads nothing, and
resolves 14 of the 16 remaining unknowns: partitions, GPUs, VRAM, CUDA, quota,
network reachability. Everything downstream is prepared and waiting on it.

Then: cache one ungated 6 GB model → environment test → smoke test → pilot.

**Qwen2.5-3B-Instruct was chosen as the single model because it is the only
evaluated model that is not gated on Hugging Face** — it needs no licence
acceptance, so it removes the longest external dependency from the critical path.

---

## Honest limits

* No experiment has run. No GPU time has been used.
* The 120-constraint benchmark is not authored; the 12 pilot constraints are not
  yet drafted and will be presented for approval before being treated as data.
* Human annotation (~5,721 judgements, ≈125 hours, ≈31 of them a second
  annotator's) has not begun and a second annotator is not yet identified.
* Phase 0 verified the 12 *cited* works. The systematic sweep for *unknown*
  prior work is outstanding, so **no novelty claim is made**.
