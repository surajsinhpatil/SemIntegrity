# Results status — what is measured, what is pending

**Updated 2026-09-26.**

One table per quantity the paper will report, with an explicit state. The point
of this file is that **nothing here can be mistaken for a result that does not
exist**. Every row is `MEASURED`, `DIAGNOSTIC`, `PENDING` or `BLOCKED`, and the
rules are:

| state | meaning |
|---|---|
| **MEASURED** | computed from real model output under the frozen pipeline; reportable |
| **DIAGNOSTIC** | computed from real output, but pipeline-validation only — **not** a finding about any model |
| **PENDING** | the code exists and is tested; the data does not |
| **BLOCKED** | cannot proceed without a decision or human annotation |

No row may move to MEASURED while the CANON go/no-go gate is failing.

---

## 1. Infrastructure — MEASURED

| quantity | value | evidence |
|---|---|---|
| Inference stack | vLLM 0.11.2 · torch 2.9.0+cu128 · transformers 4.57.6 · Python 3.11.16 | ADR-0015; `requirements/lock/cluster-gpu.txt` |
| CUDA linkage | `libcudart.so.12` only, 0 references to `.13` | scan of the installed package, job log |
| Host | Rocky Linux 8.10, glibc 2.28, A100 80 GB, driver 570.158.01 | job provenance blocks |
| bf16 | supported; a real bf16 matmul executed on device | job 11966 |
| Offline resolution | model resolved from the frozen cache with `HF_HUB_OFFLINE=1` | jobs 11968/11969/12094/12095 |
| Model revision | `aa8e72537993ba99e69dfaafa59ed015b17504d1` | recorded on every response |
| Provenance completeness | 22/22 fields | `_provenance.yaml` + schema test |

## 2. Reproducibility — MEASURED

| quantity | value | evidence |
|---|---|---|
| Run-to-run agreement | **96/96 raw responses byte-identical** | jobs 11969 → 12095, `compare_runs.py` |
| Across nodes / days | cn4 (Sep 25) → cn1 (Sep 26), environment rebuilt between | provenance blocks |
| Stage 0 label agreement | 96/96 | `compare_runs.py` |
| Chat-template hash | `cd8e9439…` identical under transformers 4.57.6 and 5.0.0 | measured on Mac and cluster |

This is **partial** evidence for §4.6's determinism requirement — a component of
the preregistered check in `determinism_check.yaml`, which spans 100 prompts,
two batch compositions and every model. It is not that whole check.

## 3. Pilot — DIAGNOSTIC, not results

One model, one detector pair, no human gold, and a **failing gate**. These
numbers validate the pipeline. They are **not** findings about Qwen2.5-3B and
must not be reported as such.

| quantity | value | state |
|---|---|---|
| Canonicalisation rate | 93.75% (90/96) | **FAILS** the ≥95% CANON gate |
| Stage 0 labels | ANSWER 68 · NEGATED 4 · ABSTAIN 18 · INVALID 6 | DIAGNOSTIC |
| D1 coverage | 0.551 | DIAGNOSTIC |
| D1 mean PSCR | 0.300 | DIAGNOSTIC |
| D0 coverage | 0.485 | DIAGNOSTIC |
| D0 mean PSCR | 0.209 | DIAGNOSTIC |
| D0 set-level | SATISFIED 7 · VIOLATION 5 | DIAGNOSTIC |
| Truth accuracy | 0.767 | DIAGNOSTIC |
| Abstention rate | 0.188 | DIAGNOSTIC |

**Perfect-model artifact: 0.643 → 0.000.** Before the Q21 polarity mapping, a
model answering every probe correctly scored PSCR 0.643 and the per-constraint
ordering was inverted. That is now 0.000 on all twelve constraints and guarded
by a permanent test. **Any number produced before canonicaliser v1.1 is
uninterpretable.**

**D0 and D1 disagree on real output** (0.209 vs 0.300) while agreeing exactly on
a perfect model. Detector disagreement is a reportable result under §4.8.2 — but
not from one model on twelve constraints.

## 4. Detectors

| detector | implementation | can it run? | can it be reported? |
|---|---|---|---|
| **D0** symbolic | ✅ complete, tested | ✅ runs against the frozen KB | DIAGNOSTIC only |
| **D1** exact match | ✅ complete, tested | ✅ | DIAGNOSTIC only |
| **D2** NLI | ✅ complete, tested | ❌ **no checkpoint chosen** (`EMPIRICAL_NOT_ASSUMED`) and **no calibrated thresholds** | **BLOCKED** |
| **D3** judge | ✅ complete, tested | ⚠️ judge decided (phi-4, pinned) — never executed | **PENDING** |
| **D4** distributional | ✅ complete, tested | ❌ **Q5 unresolved** (ADR-0016) | **BLOCKED** |

D2's threshold and D4's distribution mapping are **refused in code**, not merely
undone: both raise rather than fall back to a default, so neither can produce a
number by accident.

## 5. Metrics and statistics — PENDING (code done, data absent)

| component | implementation | data |
|---|---|---|
| PSCR, PCS, Consistency@K, AOCR | ✅ tested against the proposal's three worked examples | pilot only |
| Truth accuracy, abstention, D0/D1 coverage | ✅ tested | pilot only |
| Recovery@k | ✅ tested (rarefaction, seeded) | not run |
| Cluster bootstrap (BCa, constraint-level) | ✅ tested | not run |
| BH-FDR + adjusted q-values | ✅ tested | not run |
| Per-class / per-domain aggregation | ✅ tested | pilot only |
| Pair-factor binomial cells (ADR-0009) | ✅ tested | not run |
| Detector P/R/F1/AUPRC | ✅ interface tested | **BLOCKED — no human gold** |
| Beta-binomial mixed model (PyMC) | ❌ not implemented | not run |
| Knowledge-screen analysis | ❌ not implemented | not run |

## 6. NOT STARTED

- **Human validation.** Sample A (~400 representative pairs) and Sample B (~300
  enriched) are unauthored. No annotators, no adjudication, no Krippendorff α,
  no confusion matrices, no detector precision/recall against gold.
- **The 120-constraint benchmark.** Only the 12-constraint pilot exists.
- **Six of seven models.** Only Qwen2.5-3B has been loaded.
- **Preregistration.** Not submitted.

## 7. What blocks what

```
CANON gate (93.75%)
  └── blocks: any pilot number becoming a RESULT
        └── cause: 4 polar-cloze probes + 2 others, all cloze
              └── needs: a probe-wording decision (touches ADR-0003)

human validation (not started)
  └── blocks: D2 checkpoint selection, D2 thresholds,
              all detector P/R/F1/AUPRC, the IAA go/no-go criterion

Q5 (ADR-0016)
  └── blocks: D4 only. Nothing depends on D4.

120-constraint benchmark (unauthored)
  └── blocks: the full run, every confirmatory contrast, the GLMM
        └── §4.13: authoring is the binding resource, not GPU time
```

## 8. Standing prohibitions

Never report, because they do not exist:

- human annotations, inter-annotator agreement, Krippendorff α, adjudication
- detector precision, recall, F1 or AUPRC against human gold
- full-benchmark PSCR, cross-model comparisons, scaling trends
- statistical significance of any contrast
- D4 divergences (Q5 unresolved)
- any pilot number as a finding about Qwen2.5-3B

A number's presence in a log is not a licence to publish it.
