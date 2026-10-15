# Phase 1 audit — redesigning SemIntegrity without human validation

**Date:** 2026-10-15. **Scope:** repository state of record, verified against
files on disk rather than against prior summaries.

> **PHASE 2 COMPLETE.** The redesign this audit recommended is now recorded in
> **ADR-0023** (human-validation-free design) and **ADR-0024** (D4 temperature),
> with the methodology in `docs/METHODOLOGY_REVISED.md`. Where later measurement
> contradicted an audit recommendation, the audit text is struck through and
> points at what superseded it — see §5 item 10 and §4d.

**What this audit could not inspect.** `results/` is gitignored and exists only
on the cluster, and ADR-0010 forbids asserting a cluster fact from this
environment. Every figure below marked *(cluster, pasted)* comes from output the
researcher pasted into the session. Three things are therefore **UNKNOWN** and
are listed in §7 with the exact commands to resolve them: Mistral's raw Stage 0
outputs, whether a Mistral D3 archive exists, and the current on-disk state of
`results/analysis/`.

---

## 1. What is implemented, executed and measured

### 1.1 Implemented and locally verified

Local validation, executed 2026-10-15: **1,155 passed / 1 skipped**, `ruff`
clean over `src scripts tests`, `mypy` 13 errors (the unchanged baseline).

| area | state |
|---|---|
| Benchmark construction | 132 constraints (120 test + 12 dev) + 12 frozen pilot; 1,056 probes; lattice; coverage matrix Revision 6; 20/20 axis-5 universes |
| Stage 0 canonicalisation | v1.1 with the Q21 polarity mapping; **FROZEN** 2026-10-07 |
| D0 symbolic | predicate registry, freeze manifest, 24 schema registrations, three-instance audit harness |
| D1 exact match | complete; polarity-aware; symmetric |
| D2 NLI | complete, **refuses** to emit a verdict without a calibrated per-class threshold (`ThresholdNotCalibrated`), and refuses a bare 0.5 |
| D3 judge | complete; chat-template rendering fixed 2026-10-15 (Q32); archive-integrity guards |
| D4 distributional | complete **except** the Q5 mapping parameter; refuses without it |
| Metrics | PSCR, PCS, Consistency@K, AOCR, Recovery@k, truth accuracy, abstention, D0/D1 coverage |
| Statistics | cluster bootstrap (BCa), paired cluster bootstrap, bootstrap difference, BH-FDR, ADR-0009 binomial cells |
| Analysis | `analysis.evaluate` (shared row builder + §4.11 contrasts), `evaluate_primary.py`, `detector_agreement` + driver (new, 2026-10-15) |
| Knowledge base | frozen Wikidata cache, 8-provider corroboration fetcher and store, witness rule |
| Inference | `run_experiment` driver, vLLM / transformers / stub backends, chat-template rendering with hash logging |

**Two package directories are empty stubs holding only `__init__.py`:**
`src/semintegrity/annotation/` and `src/semintegrity/knowledge_screen/`.

This is a materially good finding for the redesign: **no human-annotation
infrastructure was ever built.** There is no annotation tool, schema, adjudication
flow or IAA computation to remove. The human dependency lives entirely in
*specifications* — config criteria, ADR text and docstrings — not in code that
must be rewritten.

### 1.2 Executed and measured *(cluster, pasted)*

| quantity | value |
|---|---|
| Primary run | 5 models x 960 probes = **4,800 responses**, Track A, seed 20250058, temperature 0.0 |
| CANON | Qwen 7B 99.17 · 14B 99.06 · 3B 98.65 · OLMo-2 97.29 = **PASS**; **Mistral 63.02 = FAIL** |
| H1_primary (C1+C2 vs C3+C4) | negative with a 95% CI excluding 0 in **all five** models |
| Scale (Qwen) | 3B→7B **+0.042** (0.006, 0.079); 7B→14B **−0.019** (−0.062, 0.023) |
| Per-class PSCR | C3 **at chance** (0.50) in every model at every scale; C1 and C4 far below chance |
| D3 | 4 models, **9,359 judgements**, parse-failure **0.0**, one shared template hash |
| Reproducibility | 96/96 raw responses byte-identical across nodes and days |

### 1.3 Verified directly from repository data (not from a summary)

Read out of `data/benchmark/*/constraints.jsonl` and `probes.jsonl`:

| fact | value |
|---|---|
| test constraints | 120 — **72 DRAFT**, 48 EVIDENCE_VERIFIED |
| dev constraints | 12 — **9 DRAFT**, 3 EVIDENCE_VERIFIED |
| **total DRAFT** | **81 of 132** — the previously reported figure is **CONFIRMED** |
| constraints with any corroborating source | **3 of 120** test (two with 2 sources, one with 1) |
| `human_validated_at` set | **0** — nothing is falsely marked |
| class balance | C1/C2/C3/C4 = 30/30/30/30 |
| answer-type allocation | C1 and C4 = 10 entity / 10 boolean / 10 date each; **C2 and C3 = 30 boolean each** |
| **probe validation status** | **all 1,056 probes are `draft`. Zero validated.** |

**The answer-type crosstab confirms the chance-balance claim analytically.** With
C1/C4 mixed (chance = (10·⅔ + 10·⅔ + 10·½)/30 = **0.611**) and C2/C3 all boolean
(**0.500**), both H1 arms sit at (0.611·30 + 0.500·30)/60 = **0.5556**. The
confirmatory contrast is chance-balanced *by construction*, exactly as
`statistics.yaml` asserts. This result survives the redesign untouched.

---

## 2. What is incomplete, blocked or only proposed

| item | state |
|---|---|
| **Probe validation** | **never exercised.** All 1,056 probes `draft` |
| Ground-truth corroboration | 81/132 DRAFT; 3 constraints have any second source |
| D2 | **BLOCKED** — no checkpoint selected (`EMPIRICAL_NOT_ASSUMED`), no thresholds |
| D4 | **BLOCKED** — Q5 / ADR-0016 `T` unresolved |
| Mistral D3 | **UNKNOWN** — not established by any artefact seen here |
| Beta-binomial fit | data-prep done; **FIT not implemented**; ADR-0004 PROPOSED; `pymc` absent |
| Knowledge screen | **not implemented** (empty module) |
| Preregistration | not submitted |
| Open ADRs | 0004 PROPOSED · 0006 PROPOSED · 0014 PROPOSED · **0016 OPEN** |
| Open questions | Q5, Q7, Q8, Q9, Q11, Q28, Q30, Q31 open; Q29 and Q32 resolved |

---

## 3. Design decisions that MUST be superseded

The seven preregistered go/no-go criteria in `configs/inference/pilot.yaml`
(§4.12, "fixed IN ADVANCE") are the load-bearing human dependency.

| id | criterion | human? | disposition |
|---|---|---|---|
| GT | ≥95% have unambiguous, sourceable ground truth | evidential | **SURVIVES** — machine-checkable via the evidence ladder |
| **PROBE** | ≥90% of probes survive **human** semantic-equivalence validation | **YES, explicitly** | **MUST BE SUPERSEDED** |
| CANON | Stage 0 canonicalises ≥95% of valid responses | no | **SURVIVES** — already PASS |
| **D0AUDIT** | every D0 predicate passes its three-instance schema audit | **YES — see below** | **MUST BE RESPECIFIED** |
| **NONDEGEN** | D2 and D3 produce non-degenerate predictions | **AMBIGUOUS** | **CONFLICT — must be resolved** |
| **IAA** | inter-annotator agreement is acceptable | **YES, irreducibly** | **MUST BE REMOVED** |
| ABSTAIN | no class with a dominant abstention rate | no | **SURVIVES** — computable now |

### 3.1 D0AUDIT is human, and the criterion text does not say so

`src/semintegrity/detectors/d0/audit.py` states it outright:

> "The expected verdicts are human judgements and are never generated here. An
> audit case with no human-supplied verdict is rejected, not defaulted."

So **three** criteria depend on a human, not two. This is only visible by reading
the harness, which is why §2 of the brief insisted on inspecting implementations
rather than names.

### 3.2 NONDEGEN is defined two different ways, and they disagree

| source | definition | satisfiable without humans? |
|---|---|---|
| `configs/inference/pilot.yaml` (the **preregistered** §4.12 gate) | "D2 and D3 produce non-degenerate predictions (not all-contradiction, not all-compatible)" | **YES** — a label-distribution property |
| `configs/models/_judge.yaml` | "dev-split **judge-vs-human** agreement must be non-degenerate (pilot criterion NONDEGEN)" | **NO** |

Under the preregistered reading, **D3 already satisfies NONDEGEN** on measured
data (1,017 CONTRADICTION : 1,308 COMPATIBLE for Qwen2.5-3B, and comparable
splits for the other three). Under the `_judge.yaml` reading it is unsatisfiable.

**This is a methodology decision and is recorded here rather than taken.** My
recommendation is the `pilot.yaml` reading, because it is the preregistered
artefact and `_judge.yaml`'s sentence is a verification note rather than a gate
definition — but the researcher decides, and either way the two files must be
made to agree.

### 3.3 Other specifications that must be superseded

* **§4.9 human validation plan** — Sample A (~400 representative pairs) and
  Sample B (~300 enriched), annotators, adjudication, Krippendorff α. Unauthored;
  must be formally withdrawn, not left dangling.
* **Detector precision / recall / F1 / AUPRC against gold** — specified
  throughout §4.8. `analysis.detector_scores.require_human_gold` already refuses
  these in code. The *guard stays*; what changes is that the design must stop
  treating the refusal as temporary.
* **ADR-0007 (development set)** — its stated purposes include D2 calibration on
  dev human labels and D0 predicate correction. The dev split's role must be
  redefined, not silently repurposed.
* **`VerificationStatus.HUMAN_VALIDATED`** — the enum rung exists and is now
  unreachable by design. It must be explicitly retired or documented as
  permanently unused, so no future code can aspire to it.

---

## 4. Which existing outputs remain valid

### 4.1 Valid unchanged — no recomputation needed

* **All 4,800 raw responses.** Immutable under ADR-0005; nothing about them
  depended on labels.
* **Stage 0 / CANON rates and the gate verdict.** CANON was always a
  machine-only criterion.
* **D1 PSCR, the four-class profile, H1_primary, and the scale comparisons.** D1
  needs no reference labels, and the chance-balance that protects the
  confirmatory contrast is a property of the authored design (§1.3), not of any
  annotation.
* **D3 archives for four models.** Measured judge output. They were never
  accuracy estimates.
* **Reproducibility evidence** — byte-identical reruns, config hashes, pinned
  revisions, template hashes.
* **The chance-balance derivation** in §1.3, which is analytic.

### 4.2 Valid but requiring re-labelling, not recomputation

Every row currently marked "DIAGNOSTIC pending human validation" is still
DIAGNOSTIC, but **the reason changes** from "awaiting annotation" to "no
reference labels exist by design". That is a documentation change with
consequences for what may be claimed, and it must not be mistaken for a
promotion.

### 4.3 Invalid and already quarantined

The untemplated D3 archive
(`Qwen__Qwen2.5-3B-Instruct.jsonl.untemplated-prefix`, 99.14% parse failure,
Q32) stays excluded. `scripts/analysis/detector_agreement.py` refuses by
inspection any archive lacking `judge_chat_template_hash`.

### 4.4 Unestablished, and now permanently so

**D0's error rate.** D0's correctness was to be established by the human
three-instance audit and by D0-vs-human disagreement on the test split
(`detectors/d0/registry.py` records both). Without humans, D0's agreement with
the formal intent of its own predicates can be demonstrated only on
analytically-specified cases — which is weaker, and must be stated as weaker.

---

## 4a. THE CENTRAL FINDING — D0 and D1 are not independent detectors

**Measured detector concordance** *(cluster, pasted, 2026-10-15)*, pair-level on
jointly decided pairs, intervals clustered over constraints:

| model | D0 vs D1 | D0 vs D3 | D1 vs D3 |
|---|---|---|---|
| Qwen2.5-3B | **1.0000** (κ 1.0000) | 0.9995 | 0.9957 |
| Qwen2.5-7B | **1.0000** (κ 1.0000) | 0.9984 | 0.9917 |
| Qwen2.5-14B | **1.0000** (κ 1.0000) | 0.9992 | 0.9931 |
| OLMo-2-7B | 0.9995 (κ 0.9989) | 0.9990 | 0.9914 |

### Why D0 vs D1 = 1.0000 is near-tautological, not corroboration

Reading the implementations rather than the names, as §6 of the brief required:

* `C1MutualExclusion.check_pair` reduces to **`a.canonical_answer ==
  b.canonical_answer` → SATISFIED, else VIOLATION**, after returning
  NOT_APPLICABLE for a `None` answer or an answer outside the closed space. Its
  `kb` argument is accepted and **never read** on the pairwise path.
* `_SchemaExclusion.check_pair` — the base of **all 24** registered
  `s_c*_0*` predicates — **delegates straight to `C1MutualExclusion`**.
* `_SchemaAnchor.check_pair` tries `C4IntervalPrecedence` first and **falls back
  to `C1MutualExclusion`** when the anchor cannot apply.
* All 120 test constraints use an `s_c*_0*` predicate (24 predicates x 5 each).

D1's rule for non-NEGATED pairs is the same answer-identity comparison. So on
the pairs where both are asked, **D0 and D1 can only differ in three ways**: a
NEGATED response (D0 is not asked), an answer outside the closed space, or
`C4IntervalPrecedence` firing on a pair whose answers *agree*. The last is the
only genuine source of verdict disagreement, and OLMo-2's single discordant pair
in 1,971 is plausibly it.

**Consequence: cross-detector agreement cannot be the validation substitute for
D0/D1.** They are not two detectors that happen to agree; for this benchmark
they are substantially **one detector reached by two code paths**. The brief
warned that detectors "may share systematic biases"; here they share
*implementation*, which is the strongest form of that problem. Reporting
D0 vs D1 = 1.0000 as mutual corroboration would be a serious error.

### This REVERSES a claim currently in RESULTS_STATUS.md

§3 of that document says: "D0 and D1 disagree on real output (0.209 vs 0.300)
while agreeing exactly on a perfect model. Detector disagreement is a reportable
result under §4.8.2."

Those pilot figures are each detector's PSCR **on its own coverage set**. The
pair-level measurement now shows the verdicts agree essentially perfectly, so
**the 0.209 vs 0.300 gap was a COVERAGE difference, not a verdict
disagreement** — precisely the conflation `analysis.detector_agreement` was
written to prevent, now demonstrated on real data. The §4.8.2 "detector
disagreement" result, as the proposal anticipated it, **does not exist**. What
exists is a coverage difference, which is a different and weaker claim.

### D1 vs D3 is the only informative concordance — and it is a low bar

phi-4 is a genuinely independent mechanism, so 0.9914-0.9957 is real evidence
that the pipeline's canonicalisation and claim rendering are faithful. But the
task D3 is given is to compare two rendered claims differing only in the answer
slot, which largely **recovers answer-identity**. It establishes that phi-4 can
see that "the capital is Canberra" and "the capital is Sydney" conflict. That is
worth reporting and must not be oversold as validating contradiction detection.

### Two registered predicates are placeholders — currently harmless

`c2_conjunction` and `c3_functional_uniqueness` are registered at
`v0.1-placeholder` with a `formal_statement` beginning "PLACEHOLDER". **No test
constraint selects either** (verified: all 120 use `s_c*_0*`), so no reported
verdict comes from one. They remain reachable by a future constraint and should
be either completed or unregistered.

---

## 4b. Mistral D3 — NOT RUN, established by artefact

`ls results/detectors/d3/raw/` *(cluster, pasted)* lists four archives
(Qwen 3B/7B/14B, OLMo-2) plus the quarantined `.untemplated-prefix`. **There is
no Mistral archive and no Mistral summary.** The brief's caution was correct:
only four of five D3 runs exist.

---

## 4c. Stage 0 INVALID decomposition — MEASURED, five models

`scripts/analysis/classify_invalid.py` *(cluster, pasted, 2026-10-15)*. Stage 0
recomputed, nothing relabelled, canonicaliser unchanged.

| model | INVALID | CANON | outside space | Q31 entity/date | bool buried | polar, neither |
|---|---|---|---|---|---|---|
| Qwen2.5-3B | 13 | 0.9865 | 13 | 0 | 0 | 0 |
| Qwen2.5-7B | 8 | 0.9917 | 7 | 0 | 0 | 1 |
| Qwen2.5-14B | 9 | 0.9906 | 6 | 3 | 0 | 0 |
| OLMo-2-7B | 26 | 0.9729 | 16 | 4 | 1 | 5 |
| **Mistral-7B-v0.3** | **355** | **0.6302** | **13** | **71** | **27** | **244** |

**Q31 is settled by arithmetic.** Recovering every one of Mistral's 71
entity/date cases gives a CANON ceiling of **0.7042** — an **upper bound, not a
correction** — still far below the frozen >=0.95 gate. No entity/date
fall-through rule can rescue Mistral, so Q31 no longer decides its inclusion.

**Q31's characterisation was wrong.** It describes Mistral as answering polar
probes by naming an answer-space member: that is 98 of 355 (27.6%). The
dominant mode is **244 of 355 (68.7%)** answered with neither a yes/no nor a
space member.

**Mistral's failure is format compliance, not knowledge.** Its out-of-space
count is **13 — identical to Qwen2.5-3B's**, the best-canonicalising model.
342 of 355 (96.3%) are polar-format failures.

**An earlier conflation, corrected.** A `YES`/`NO` candidate on a *boolean*
constraint (`answer_space == ['YES','NO']`) is the canonicaliser's **deliberate
anti-bypass guard**, not the Q31 entity/date question. The taxonomy now splits
them and a test pins that they never pool. The split was a clean repartition:
Mistral 58+40 -> 71+27, OLMo-2 5 -> 4+1.

**P04 is a HYPOTHESIS, not an explanation.** All 3 Qwen2.5-14B and all 4 OLMo-2
Q31 cases are P04 — an affirmative cloze whose stem embeds the gold answer —
but **Mistral's 71 span P02-P08**. So P04 does not explain Mistral's failure. It
remains a candidate probe pathology requiring the `PROBE-C` construction audit
(ADR-0023 D2), and it matters because all 1,056 probes are `draft` and the human
PROBE criterion was never exercised.

---

## 4d. The EVIDENCE_VERIFIED subset cannot carry H1 — verified from repository data

| | C1 | C2 | C3 | C4 |
|---|---|---|---|---|
| EVIDENCE_VERIFIED | 16 | 16 | 16 | **0** |
| DRAFT | 14 | 14 | 14 | 30 |

**There are no EVIDENCE_VERIFIED C4 constraints**, and `history` is absent from
the 48 (biology, geography, public_office, science_technology, 12 each).

H1_primary is `C1+C2 vs C3+C4`. With C4 empty, arm B is **C3 alone** — a
different contrast under the same name. And the chance balance is destroyed:
both arms sit at 0.5556 on the full benchmark (gap 0.0000) but at **0.5417 vs
0.5000 (gap +0.0417)** on the 48. `statistics.yaml` states that design balance,
not adjustment, is what protects the contrast.

**The audit's own §5 item 10 recommendation was therefore wrong as written** and
is superseded by ADR-0023 D9, which replaces it with S1/S2/S3. Running
H1_primary on the 48 and reporting it as confirming H1 would have been invalid.

---

## 5. Minimum defensible redesign

Ordered by dependency. Items marked **[decision]** are methodology and are
recorded for the researcher, not taken unilaterally.

1. **ADR-0023** superseding the human-dependent design: PROBE, IAA, D0AUDIT, the
   NONDEGEN conflict, §4.9, and the detector-accuracy claims. Links back to
   ADR-0007 and ADR-0008.
2. **Replace PROBE with construction-based evidence.** The probes are *generated*
   from an authored `logical_form` plus a factor cell, and `benchmark/loader.py`
   already makes identical surfaces a **hard** failure ("identical surfaces
   inflate apparent agreement"). The defensible claim becomes "semantically
   equivalent **by construction**, with surface distinctness and factor-cell
   coverage machine-verified" — not "validated". Its limits must be stated: this
   checks the generator, not the generated meaning.
3. **Respecify D0AUDIT as controlled-case evaluation.** Reuse `d0/audit.py` with
   cases whose expected verdict follows **deductively from the predicate's
   `formal_statement`** against a hand-constructed KB fixture. This is a unit
   test, not annotation — but it is also strictly weaker than the original audit
   and must be labelled as such. **[decision: does deductive case construction
   count as "human validation" for the professor's purposes?]**
4. **Remove IAA.** It cannot be replaced by inter-detector agreement, because
   §4a shows D0 and D1 share their pairwise implementation. The usable
   replacement is **narrower**: report D1-vs-D3 concordance as evidence that
   canonicalisation and claim rendering are faithful, state explicitly that D0
   and D1 are not independent, and make no corroboration claim from D0 vs D1.
5. **Resolve NONDEGEN** per §3.2. **[decision]**
6. **D2 — my recommendation is to change its estimand, not to invent a
   threshold.** Any threshold chosen without labels is arbitrary, and
   `d2_nli.yaml` forbids 0.5 precisely to stop that. The defensible move is to
   report D2 as a **continuous score** with no thresholded verdict, so it enters
   rank-based agreement analyses but contributes no contradiction count. The
   alternative is removing D2 from the comparison. **Inventing a threshold is
   the one option I would argue against.** **[decision]**
7. **D4 — resolvable without humans.** ADR-0016 already narrows Q5 to the
   one-parameter family `p_i = softmax_i(mean_token_logprob_i / T)`. Fix `T = 1`
   as a prespecified choice plus a sensitivity analysis over `T`, and keep D4
   exploratory. It must not become a contradiction detector. **[decision on the
   value of `T`]**
8. **Mistral.** Retain CANON-FAIL. Report separately, plus a labelled sensitivity
   analysis. Requires cluster inspection first (§7).
9. **Evidence stays as it is.** Removing human validation does **not** remove
   §4.3. 81/132 remain DRAFT.
10. **~~Re-run the confirmatory contrast on the 48 EVIDENCE_VERIFIED
    constraints.~~ WITHDRAWN — see §4d.** The subset holds **zero C4**
    constraints, so H1_primary cannot be computed on it and the chance balance
    that protects the contrast is destroyed (+0.0417). Superseded by ADR-0023
    D9's S1/S2/S3, of which **S1 — the within-class EVIDENCE_VERIFIED vs DRAFT
    difference for C1/C2/C3 — is the usable form**, because it holds class and
    answer-type composition fixed. C4's ground truth cannot be
    sensitivity-tested at all.

---

## 6. Claims that become impossible

These must be removed from the narrative, not weakened:

* detector precision, recall, F1 or AUPRC — any detector accuracy against gold
* inter-annotator agreement, Krippendorff α, adjudication
* "the probes are semantically equivalent" **as a validated finding** (available
  only as a construction property)
* D0's measured error rate
* that any detector is *correct* where detectors disagree
* human-validated ground truth, for any constraint

Claims that survive intact: CANON, H1_primary, the four-class profile, the scale
comparisons, C3-at-chance, reproducibility, D3 coverage and label distributions,
and inter-detector concordance — each within its stated scope.

---

## 7. What I cannot determine from here — exact commands

**(a) Is there a Mistral D3 archive?**

```bash
ls -la results/detectors/d3/raw/ && python -c "
import json,glob
for f in sorted(glob.glob('results/detectors/d3/raw/*.summary.json')):
    d=json.load(open(f)); print(d['model_id'], d['n_judgements'], d['parse_failure_rate'])"
```

**(b) Mistral's Stage 0 failure — defect or model behaviour?**

```bash
python scripts/analysis/inspect_stage0.py --raw results/raw/primary_trackA/mistral7b-v03.jsonl 2>&1 | tail -60
```

`inspect_stage0.py` recomputes Stage 0 rather than trusting stored labels and
ends with a factor cross-tab. Q31 reports INVALID concentrating at 51.6% of
cloze and 58.8% of interrogative probes but **0.6% of declarative** — a pattern
that a parser bug would not spare declaratives, which is evidence for model
behaviour over evaluator defect. The cross-tab decides it.

**(c) What analysis artefacts currently exist?**

```bash
ls -laR results/analysis/ 2>&1 | head -40
```
