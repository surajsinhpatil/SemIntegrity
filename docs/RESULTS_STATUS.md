# Results status — what is measured, what is pending

**Updated 2026-10-15.**

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
| Canonicalisation rate | **100.00% (96/96)** — run3, post-rewrite | **PASSES** the ≥95% CANON gate |
| Stage 0 labels | ANSWER 68 · NEGATED 4 · ABSTAIN 18 · INVALID 6 | DIAGNOSTIC |
| D1 coverage | 0.551 | DIAGNOSTIC |
| D1 mean PSCR | 0.300 | DIAGNOSTIC |
| D0 coverage | 0.485 | DIAGNOSTIC |
| D0 mean PSCR | 0.209 | DIAGNOSTIC |
| D0 set-level | SATISFIED 7 · VIOLATION 5 | DIAGNOSTIC |
| Truth accuracy | 0.767 | DIAGNOSTIC |
| Abstention rate | 0.188 | DIAGNOSTIC |

### CANON — FROZEN 2026-10-07

| | before the rewrite | **run3, after Variant A** |
|---|---|---|
| INVALID | 6 / 96 | **0 / 96** |
| canonicalisation rate | 93.75% | **100.00%** |
| gate (≥95%, unchanged) | FAIL | **PASS** |
| previous six INVALIDs | — | all six resolved |
| new INVALIDs | — | none |

**Frozen. The canonicaliser, the ≥95% threshold and the Variant A cloze wording
are not to be modified on the strength of this result.** The threshold was never
touched: `scripts/analysis/evaluate_cloze_rewrite.py` reads it out of
`configs/inference/pilot.yaml` rather than carrying its own copy.

**Provenance, stated precisely.** These figures were produced by the researcher
on the cluster from `results/raw/pilot/qwen25-3b-run3.jsonl` and **reported into
the session in prose**; the evaluator output itself was not pasted here, and
ADR-0010 means no cluster fact is asserted from this environment. The durable
evidence is the run3 JSONL and its report under `results/`, which
`.gitignore` keeps out of the repository. Anyone re-deriving this figure should
re-run the evaluator against that JSONL.

**What this does and does not establish.** It establishes that Stage 0
canonicalises every response in a 96-probe single-model run — the preregistered
CANON criterion. It establishes nothing about PSCR, detector agreement, or any
property of Qwen2.5-3B: one model, twelve constraints, no human gold. Those rows
remain DIAGNOSTIC below.

**Superseded figures, retained with their labels.** The 93.75% / 6-INVALID
figure is the pre-rewrite observed result and stays the correct citation for the
*pre-rewrite* pipeline. The **94.79% / 5-INVALID** figure in
`docs/Q21_polarity_mapping_spec.md` §7 remains a **simulation** under an
entity/date fall-through rule that was never adopted, is labelled as such there,
and is now doubly superseded — it must not be quoted as an observed result.

**A consequence for an open question.** With 0 INVALID there are no polar
probes left whose reply names an answer-space member, so the entity/date
fall-through question (HANDOFF decision 2) has **no live instance in this
dataset**. It stays OPEN and undecided; it is simply no longer exercised by the
pilot, which removes the evidence this run might otherwise have supplied.

**Perfect-model artifact: 0.643 → 0.000.** Before the Q21 polarity mapping, a
model answering every probe correctly scored PSCR 0.643 and the per-constraint
ordering was inverted. That is now 0.000 on all twelve constraints and guarded
by a permanent test. **Any number produced before canonicaliser v1.1 is
uninterpretable.**

**D0 and D1 disagree on real output** (0.209 vs 0.300) while agreeing exactly on
a perfect model. Detector disagreement is a reportable result under §4.8.2 — but
not from one model on twelve constraints.

## 3b. PRIMARY RUN — MEASURED 2026-10-15

The frozen 120 test constraints x K=8 = **960 probes x 5 models = 4,800
responses**, Track A, fixed decoding (seed 20250058, temperature 0.0), vLLM
0.11.2. Every run completed with 960/960 records.

### Stage 0 / CANON gate

| model | family | canonicalisation | CANON (>=95%) |
|---|---|---|---|
| Qwen2.5-7B-Instruct | qwen | 99.17% | PASS |
| Qwen2.5-14B-Instruct | qwen | 99.06% | PASS |
| Qwen2.5-3B-Instruct | qwen | 98.65% | PASS |
| OLMo-2-1124-7B-Instruct | olmo | 97.29% | PASS |
| **Mistral-7B-Instruct-v0.3** | mistral | **63.02%** | **FAIL** |

**Mistral's scores are NOT reportable.** Its failure is structural — it answers
polar probes by naming an answer-space member instead of YES/NO (51.6% of cloze,
58.8% of interrogative, 0.6% of declarative). See Q31. OLMo-2 passing at 97.3%
establishes that the gate is not Qwen-specific.

### H1_primary — the confirmatory contrast (C1+C2 vs C3+C4)

Cluster bootstrap over constraints, BCa, 10,000 replicates, seed 20250058.
Negative = C1+C2 contradict LESS than C3+C4.

| model | estimate | 95% CI | excludes 0 |
|---|---|---|---|
| Qwen2.5-7B | -0.182 | (-0.249, -0.116) | YES |
| Qwen2.5-14B | -0.171 | (-0.253, -0.090) | YES |
| Qwen2.5-3B | -0.094 | (-0.154, -0.032) | YES |
| OLMo-2-7B | -0.090 | (-0.157, -0.019) | YES |
| *Mistral-7B* | *-0.116* | *(-0.211, -0.019)* | *not reportable* |

**Negative with an interval excluding zero in every model, across three
families and a 4.7x scale range.** The contrast is chance-balanced by
construction (design.yaml: C1+C2 = C3+C4 = 0.556, gap 0.000), so it is not an
artefact of answer-space cardinality.

### Scale: helps to 7B, then saturates

Paired cluster bootstrap over the identical 120 constraints.

| comparison | estimate | 95% CI | excludes 0 |
|---|---|---|---|
| 3B vs 7B | +0.042 | (0.006, 0.079) | YES — 7B more consistent |
| 7B vs 14B | -0.019 | (-0.062, 0.023) | no |
| 3B vs 14B | -0.061 | (-0.104, -0.018) | YES |
| 7B vs OLMo-2-7B | -0.017 | (-0.062, 0.029) | no |
| 14B vs OLMo-2-7B | -0.036 | (-0.089, 0.016) | no |

Within Qwen, consistency improves 3B -> 7B and then stops. **No cross-family
difference is detectable at this sample size.**

### C3 sits at chance everywhere

Per-class PSCR against the class's chance rate (C1/C4 = 0.611, C2/C3 = 0.500):

| class | 3B | 7B | 14B | OLMo-2 | chance |
|---|---|---|---|---|---|
| C1 | 0.351 | 0.299 | 0.295 | 0.310 | 0.611 |
| C2 | 0.445 | 0.324 | 0.301 | 0.440 | 0.500 |
| **C3** | **0.550** | **0.511** | **0.503** | **0.506** | **0.500** |
| C4 | 0.432 | 0.476 | 0.434 | 0.423 | 0.611 |

C1 and C4 are far below chance in every model. **C3 is at chance in every model
at every scale** — only the 3B's interval excludes 0.500, and on the wrong side
(above it). Scale improves C2 markedly within Qwen and does not move C3.

### Scope — what these numbers are NOT

* **Only D0 and D1 ran for these figures.** D2 uncalibrated, D4 blocked on Q5.
  D3 has since executed for **one model of five** (qwen25-3b, job 15140) and is
  reported in §4a below; nothing in this section incorporates it.
* **81 of 132 constraints are DRAFT**, lacking an independent second source
  (§4.3). The ground truth is provisional to that extent.
* **No human validation.** No detector precision/recall/F1/AUPRC exists.
* **BH-FDR is not applied** to the 10-pair model-comparison family: a bootstrap
  interval yields no p-value, and inventing one would fabricate a test. Three
  of ten pairs exclude zero; multiplicity is unaddressed and must be stated.

## 4. Detectors

| detector | implementation | can it run? | can it be reported? |
|---|---|---|---|
| **D0** symbolic | ✅ complete, tested | ✅ runs against the frozen KB | DIAGNOSTIC only |
| **D1** exact match | ✅ complete, tested | ✅ | DIAGNOSTIC only |
| **D2** NLI | ✅ complete, tested | ✅ **scored for 5 of 5 models** (jobs 15160/15162-15165) | **score only, NO verdict** — see §4c |
| **D3** judge | ✅ complete, tested | ✅ **executed for 4 of 5 models** (Mistral excluded, see below) | DIAGNOSTIC only — see §4a |
| **D4** distributional | ✅ complete, tested | ✅ **run for 1 of 5 models** (qwen25-3b, job 15168) | EXPLORATORY only — see §4d |

**D2's threshold remains refused in code.** ADR-0023 D6 changed its estimand to
a continuous score; it did not calibrate a threshold. `D2Detector.check_pair`
still raises `ThresholdNotCalibrated`, and the driver never calls it. D4's
distribution mapping is no longer refused — ADR-0024 resolved it to a frozen
`T = 1` — but `builder` is still a required argument with no default, so no JSD
can be produced without the choice being explicit at the call site.

**Mistral-7B D3 was NOT run, by decision.** Its CANON failure (0.6302) makes its
consistency metrics non-reportable regardless, and 2,310 of its 3,360 pairs
render no claim, so a judge run would have scored a small, unrepresentative
remainder at no benefit. Recorded as an exclusion, not an omission.

**D4 was run for ONE model, by decision.** See §4d: the other four would need
~74 GB of sequential re-staging against 19 GB of quota headroom, with the phi-4
judge evicted to fit the 7B and 14B, for an exploratory analysis that no primary
or secondary metric depends on.

**Consequence of running human validation LAST (professor-approved 2026-10-08).**
D2 is calibrated on dev-split human labels, so with human validation deferred to
the end **D2 cannot run in the technical-evaluation phase at all**. That is a
sequencing consequence, not a defect: the technical evaluation reports D0, D1 and
(once a judge run exists) D3, and D2 joins after the human study. Nothing about
D2 is relaxed to make it runnable earlier.

## 4a. D3 judge — DIAGNOSTIC, four of five models

**Jobs 15140-15143, 2026-10-15, all COMPLETED 0:0, 3.5-4.5 min each on csis.cn1.**
Judge `microsoft/phi-4` @ `2db69c1c3e91a05d2c64a3185acfbaf36f744e25`,
single-shot, no ensembling, no set-level verdict. **9,359 judgements total.**

| model | judgements | coverage | parse_failure | empty output | CONTRADICTION | COMPATIBLE |
|---|---|---|---|---|---|---|
| Qwen2.5-3B | 2,325 | 0.6920 | **0.0** | 0 | 1,017 | 1,308 |
| Qwen2.5-7B | 2,058 | 0.6125 | **0.0** | 0 | 813 | 1,245 |
| Qwen2.5-14B | 2,771 | 0.8247 | **0.0** | 0 | 980 | 1,791 |
| OLMo-2-7B | 2,205 | 0.6562 | **0.0** | 0 | 927 | 1,278 |

**Zero parse failures and zero empty outputs across all 9,359.** All four
archives carry the identical chat-template hash
`fe4120415a3858b873955c92ce3a103a95bc97c2cb00b72e62659aaf0f891ee5`, so they were
rendered alike and are comparable. **UNCLEAR was never returned.**

Mistral-7B-v0.3 is not judged yet and is last by design: it fails CANON at
63.02%, so most of its responses are INVALID, most pairs are unjudgeable, and its
scores are not reportable regardless.

### This supersedes an earlier run that must never be cited

Job 15127 produced 2,325 judgements at a **99.14% parse failure rate** because
the prompt was not rendered through phi-4's chat template (Q32) — phi-4 ran as a
completion model. Its archive is retained as
`Qwen__Qwen2.5-3B-Instruct.jsonl.untemplated-prefix` as evidence of the defect.
**No number from it is reportable**, and `scripts/analysis/detector_agreement.py`
refuses by inspection any archive lacking a `judge_chat_template_hash`.

### Coverage is a property of the MODEL, not of the judge

Coverage is the fraction of the 3,360 possible pairs where **both** responses
make a claim, so it is set by abstention and canonicalisation before the judge
sees anything. It is **not monotone in scale**: 7B has the *lowest* coverage of
the four (0.6125, below 3B's 0.6920) while 14B has much the highest (0.8247).
With CANON at 98.65-99.17% for all three Qwen models, INVALID cannot account for
this — it is abstention, which this project holds as a dimension **separate**
from consistency.

### A CONFOUND that must not be reported as a finding

D3's contradiction rate over the pairs it judged falls monotonically across the
Qwen scale, which *looks* like consistency continuing to improve past 7B:

| model | D3 contradiction rate | unweighted mean of the four per-class D1 PSCR values |
|---|---|---|
| Qwen2.5-3B | 0.4374 | 0.4445 |
| Qwen2.5-7B | 0.3950 | 0.4025 |
| Qwen2.5-14B | **0.3537** | 0.3833 |
| OLMo-2-7B | 0.4204 | 0.4198 |

**This table may not be used to claim anything.** Two reasons:

1. **The denominators differ by model.** 14B's rate is computed over 2,771
   judgeable pairs and 7B's over 2,058 — different sets, differently composed.
   The confirmatory 7B-vs-14B result (-0.019, CI (-0.062, 0.023), §3b) is a
   *paired* comparison over the identical 120 constraints. A cross-model
   comparison of per-model rates on per-model coverage sets is not the same
   quantity and cannot contradict it.
2. **The D1 column is not overall PSCR.** It is the unweighted mean of four
   per-class means, shown only because the orderings coincide. The
   constraint-level PSCR is a different average.

The orderings agreeing is **not** detector agreement either — identical
marginals are compatible with disagreement on every pair. The §4.8.2 result is
per-pair concordance restricted to pairs both detectors decided, which is what
`detector_agreement.py` computes and what has **not yet been run**.

### What this row is NOT

* **Not a finding about any model.** No human gold; 81 of 132 constraints still
  DRAFT. Pipeline validation, on the same footing as §3.
* **Not detector precision, recall, F1 or AUPRC.** Those need human gold;
  `analysis.detector_scores` refuses them and the agreement driver cannot reach
  that module (pinned by test).
* **Not NONDEGEN passing.** `_judge.yaml` defines NONDEGEN as *judge-vs-human*
  agreement on the dev split. A 43.7%/56.3% label split clears the
  all-one-label failure mode — necessary, not sufficient. NONDEGEN stays
  **BLOCKED on human validation**.

## 4b. Ground-truth sensitivity — MEASURED 2026-10-15, four models

`scripts/analysis/run_sensitivity.py` *(cluster, pasted)*. CPU only. Artefacts at
`results/analysis/sensitivity/*.sensitivity.json`. ADR-0023 D9, Q33.

**H1_primary was NOT computed on the verified subset and cannot be:** there are
no EVIDENCE_VERIFIED C4 constraints, so arm B would be C3 alone and the chance
balance that protects the contrast is destroyed (gap 0.0000 -> +0.0417).

### S1 — within-class EVIDENCE_VERIFIED minus DRAFT, the primary sensitivity

| model | C2 | C3 |
|---|---|---|
| Qwen2.5-3B | +0.0009 (-0.1010, +0.1063) | -0.0153 (-0.0666, +0.0295) |
| Qwen2.5-7B | -0.0685 (-0.2105, +0.0759) | +0.0599 (-0.0188, +0.1371) |
| Qwen2.5-14B | -0.0036 (-0.1513, +0.1474) | +0.0045 (-0.1128, +0.1353) |
| OLMo-2-7B | +0.0323 (-0.0794, +0.1430) | -0.0149 (-0.0925, +0.0904) |

**All eight intervals include zero, and the signs are mixed.** No association
between verification status and PSCR is detectable in the two classes where the
comparison is defensible.

**C1 is reported with NO estimate** — its verified subset holds no `date`
constraints while its draft subset is 10/14 `date` (chance gap -0.0595), so a
difference there is a difference between answer-type mixtures. **C4 is not
assessable at all**, having no verified constraint.

**What this does and does not license.** It is the strongest available answer to
"are the results an artefact of provisional ground truth?" — and it is a bound,
not an exclusion. **n is 16 vs 14 per class, so the intervals are wide**: C2 for
the 7B spans -0.21 to +0.08. Absence of a detectable effect at this sample size
is not evidence of no effect, and the claim must be stated as "no systematic
association detected", never as "verification status does not matter".

### S3 — the arm contrast on the verified subset. NOT H1_primary.

| model | estimate | 95% CI | excludes 0 |
|---|---|---|---|
| Qwen2.5-3B | -0.1741 | (-0.2539, -0.0996) | YES |
| Qwen2.5-7B | -0.2856 | (-0.3804, -0.1892) | YES |
| Qwen2.5-14B | -0.2109 | (-0.3542, -0.0716) | YES |
| OLMo-2-7B | -0.1324 | (-0.2160, -0.0510) | YES |

This is `C1+C2 vs C3` on 48 constraints — **a different contrast from
H1_primary** (`C1+C2 vs C3+C4` on 120) and it must never be reported as
confirming it. What it shows is **direction**: the negative sign reproduces on
the machine-verified subset in all four models, **while the restriction's
+0.0417 chance gap pushes the estimate toward positive**. The bias works against
the observed sign, so a negative estimate here is conservative.

Magnitudes are larger than H1_primary's (-0.090 to -0.182) because the contrast
differs — C3 alone rather than C3+C4 — not because the effect grew.

### S4 — probe-exclusion sensitivity (secondary; K=8 remains primary)

Paired difference in PSCR with and without the 43 `PROBE-C` probes, across 27
affected constraints. Exclusion is on probe TEXT, never on a response.

| model | paired estimate | 95% CI | excludes 0 |
|---|---|---|---|
| Qwen2.5-3B | -0.0030 | (-0.0087, +0.0034) | no |
| Qwen2.5-7B | -0.0022 | (-0.0047, -0.0001) | **YES** |
| Qwen2.5-14B | +0.0066 | (-0.0006, +0.0145) | no |
| OLMo-2-7B | +0.0052 | (-0.0018, +0.0139) | no |

**This answers Q33: the flagged probes have no material effect.** Magnitudes are
0.002-0.007, **one to two orders of magnitude below H1_primary's 0.090-0.182**,
and the signs are mixed. One of four intervals excludes zero at an estimate of
-0.0022; with four comparisons, mixed signs and no multiplicity correction
applied, that is consistent with noise and is **not** reported as an effect.

K=8 stays primary. No probe was rewritten, discarded or reordered.

## 4c. D2 NLI — MEASURED 2026-10-15, five models. A NEGATIVE result.

Jobs 15160/15162/15163/15164/15165, all COMPLETED 0:0, 1:23-3:12 each on
csis.cn1. Checkpoint `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli`
@ `b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7`, fp32, `contradiction_index: 2`
verified against the loaded checkpoint at run time.

**D2 produced NO verdicts and NO contradiction counts.** Its threshold is
WITHDRAWN (ADR-0023 D6); `check_pair` still raises.

| model | scored | no claim | rank concordance vs D1 | vs D3 |
|---|---|---|---|---|
| Qwen2.5-3B | 2,325 | 1,035 | **1.0000** (1.0000, 1.0000) | 0.9989 |
| Qwen2.5-7B | 2,058 | 1,302 | **1.0000** (1.0000, 1.0000) | 0.9959 |
| Qwen2.5-14B | 2,771 | 589 | **1.0000** (1.0000, 1.0000) | 0.9973 |
| OLMo-2-7B | 2,205 | 1,155 | **1.0000** (1.0000, 1.0000) | 0.9986 |
| Mistral-7B | 1,050 | 2,310 | **1.0000** (1.0000, 1.0000) | n/a (no D3 archive) |

Lowest-scoring D1-VIOLATION pair **0.6957**; highest-scoring D1-SATISFIED pair
**0.0096**. A 0.686 gap with nothing between: the scores are bimodal.

**This is ADR-0023 D6a and it refutes D6's own rationale.** D2 was retained as
"the only detector whose mechanism is not answer-identity". It is not.
`render_claim` substitutes the canonical answer into the gold proposition, so a
pair with different answers yields two claims differing in one slot, and a pair
with the same answer yields two **byte-identical strings** — which is why the
compatible side sits at 0.0096.

**The general finding: no pair of D0/D1/D2/D3 provides independent
corroboration, by construction.** They all consume claims rendered from the same
canonical answers, so independence is destroyed upstream of every detector. This
is wider than the D0/D1 case, which was shared *code*; this is shared *input
construction*. §4.8.2's anticipated detector-disagreement result does not exist
in any form, and the validation argument must not rest on cross-detector
agreement anywhere.

**What D2 does establish, narrowly:** an independent 435M NLI model with no
access to the answer space or the knowledge base separates the two classes of
rendered claim perfectly — further evidence that canonicalisation and claim
rendering are faithful. Not accuracy, not corroboration of contradiction
detection.

Mistral is scored (1,050 pairs) and its scores remain **NOT REPORTABLE** as
model properties; 2,310 of its pairs render no claim, consistent with its 63.02%
CANON rate.

## 4d. D4 distributional — MEASURED 2026-10-15, ONE model. EXPLORATORY.

Job 15168, COMPLETED 0:0, 00:02:59 on csis.cn1. Qwen2.5-3B only.

| quantity | value |
|---|---|
| constraints analysed | 120 / 120 |
| primary temperature | **1.0** (frozen, ADR-0024) |
| mean pairwise JSD at T=1 | **0.1513** |
| band reused one scoring run | **true** — no extra inference |
| is a contradiction detector | **false** |
| exposes a verdict | **false** |
| contributes to PSCR | **false** |

The band on `K-C1-BIO-11` (candidates `Felis catus / silvestris / chaus`, 8
probes) behaves exactly as ADR-0024 predicts — lower `T` sharpens the
distributions and raises the divergence:

| T | role | mean pairwise JSD |
|---|---|---|
| 0.5 | exploratory | 0.1881 |
| **1.0** | **PRIMARY** | 0.0908 |
| 2.0 | exploratory | 0.0320 |
| 4.0 | exploratory | 0.0090 |

**JSD is not zero, so paraphrase does induce different candidate
distributions** — D4 is measuring something. But the magnitude spans a **21x
range across the band**, so "mean JSD = 0.1513" is close to meaningless without
its `T` and is **not reportable as a standalone number**.

### Ordering stability across the band — MEASURED, and it is partial

Spearman rank correlation of the 120 per-constraint JSD values against the
preregistered `T = 1`, computed from the stored log-probabilities with no
additional inference (120/120 constraints defined at every `T`):

| T | Spearman rho vs T=1 |
|---|---|
| 0.5 | **0.9727** |
| 1.0 | 1.0000 (by construction) |
| 2.0 | **0.8854** |
| 4.0 | **0.6488** |

**The ordering is stable in a neighbourhood of `T = 1` and degrades as `T`
rises.** The degradation is explained by the mechanism rather than being a
defect: higher `T` flattens the softmax toward uniform, so every distribution
converges and the divergence collapses (mean JSD 0.0090 at `T = 4` against
0.1881 at `T = 0.5`). Once the values are all near zero, their ordering is
dominated by numerical noise.

**What D4 may therefore claim, precisely:**

* a qualitative statement about **which constraints are most distributionally
  unstable** is supported for `T` in [0.5, 2], where rho >= 0.885;
* it is **NOT** supported if robustness across the whole preregistered band is
  required, because rho falls to 0.649 at `T = 4`;
* **no claim about JSD magnitude** is available at any `T`.

**The band is NOT narrowed after the fact.** ADR-0024 preregistered
`T in {0.5, 1, 2, 4}` and all four values are reported. Dropping `T = 4` now
because it is inconvenient would be a researcher degree of freedom exercised
after seeing the result, so it is not done — the full band is stated, together
with the reason the high end is degenerate, and the reader judges. Any future
preregistration should bound the band by the flattening argument *in advance*.

**Scope, unchanged:** EXPLORATORY; not a contradiction detector; absolute JSD is
NOT comparable across constraints (dissimilar candidate spaces, §4.8.6) nor
across temperatures (ADR-0024); one model of five.

**D4 was deliberately NOT run on the other four models.** It needs each model
re-staged (the evaluated weights were evicted after the primary runs to stay
under the 1000 G per-user quota), ~74 GB more of sequential download against
19 GB of headroom, with the phi-4 judge evicted to fit the 7B and 14B. Nothing
depends on D4, so the cost was judged not worth it. Recorded as a decision, not
an omission.

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
| Beta-binomial mixed model (PyMC) | ⚠️ **data-prep done** (`aggregate.binomial_cells`, tested); FIT not implemented | not run |
| Knowledge-screen analysis | ❌ not implemented | not run |

## 6. NOT STARTED

- **Human validation.** Sample A (~400 representative pairs) and Sample B (~300
  enriched) are unauthored. No annotators, no adjudication, no Krippendorff α,
  no confusion matrices, no detector precision/recall against gold.
- ~~**The 120-constraint benchmark.**~~ **DONE 2026-10-08.** 132/132 authored
  (120 test + 12 dev), 1,056 probes, **313/313 evidence checks passed**, every
  lattice rule PASS, 20/20 axis-5 universes frozen. Coverage matrix Revision 6.
  **81 of 132 are DRAFT** pending an independent second source (§4.3), so the
  structure is complete and the ground truth is provisional to that extent.
- **Six of seven models.** Only Qwen2.5-3B has been loaded.
- **Preregistration.** Not submitted.

## 7. What blocks what

```
CANON gate — PASS, FROZEN 2026-10-07 (0/96 INVALID = 100.00%)
  └── no longer blocks anything. Variant A resolved all six; no new INVALIDs.
        └── the remaining go/no-go criteria are untouched by this:
              PROBE (human probe validation), D0AUDIT, NONDEGEN (D2/D3),
              IAA (needs annotators), ABSTAIN. CANON was one of seven.

human validation (not started)
  └── blocks: D2 checkpoint selection, D2 thresholds,
              all detector P/R/F1/AUPRC, the IAA go/no-go criterion

Q5 (ADR-0016)
  └── blocks: D4 only. Nothing depends on D4.

120-constraint benchmark — COMPLETE 2026-10-08 (132/132, Revision 6)
  └── no longer blocks anything structural. The primary run is ready to submit.
  └── 81/132 still DRAFT (no second source). This does NOT block inference:
        nothing in inference, the detectors or the analysis reads
        verification_status. It DOES mean a final result must state how much of
        the benchmark was provisional when it was measured.

ADR-0004 (PyMC backend) — PROPOSED, not approved
  └── blocks: the beta-binomial SECONDARY model only. The confirmatory
        cluster-bootstrap analysis is primary, implemented and tested.
  └── also needs `pip install -r requirements/analysis.in` (pymc is absent)

GPU run (not executed)
  └── blocks: every MEASURED row below the infrastructure section
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
