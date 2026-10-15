# Revised methodology — SemIntegrity without human validation

**Date:** 2026-10-15. **Status:** PROPOSED — awaiting researcher approval.
**Governing decisions:** ADR-0023 (redesign), ADR-0024 (D4 temperature).
**Evidence:** `docs/AUDIT_2026-10-15_no_human_validation.md`.

This document states what the project asks, what it measures, what it can
conclude, and what it cannot. It replaces the human-validation-dependent parts of
the proposal's §4.8–§4.12. **The benchmark, the four constraint classes, K=8, the
factor lattice, the constraint ids and the canonicalisation rules are unchanged.**

---

## 1. Research questions

**RQ1 (confirmatory).** Does an LLM's pairwise self-consistency differ between
lower-structure constraint classes (C1 entity, C2 Boolean) and higher-structure
classes (C3 relational/quantified, C4 temporal), measured over semantically
equivalent probes of the same constraint?

**RQ2 (confirmatory).** Does self-consistency improve with model scale within a
family?

**RQ3 (descriptive).** What is the four-class self-inconsistency *profile*, and
how does each class compare with the chance rate implied by its answer-space
cardinality?

**RQ4 (descriptive, measurement).** Do detectors of different mechanism agree at
the pair level, and where they are asked different questions, how much of an
apparent disagreement is **coverage** rather than verdict?

**RQ5 (descriptive, measurement).** How do response-level failures to
canonicalise distribute across causes, and what does that reveal about the
instrument and about instruction-following?

**RQ6 (sensitivity).** Are the confirmatory results sensitive to the provisional
state of the benchmark's ground truth?

**Withdrawn.** Every question of the form "how accurate is detector X" is removed
(ADR-0023 D7). No reference labels exist, so no accuracy is estimable.

---

## 2. Hypotheses and estimands

| id | hypothesis | estimand | unit | status |
|---|---|---|---|---|
| **H1_primary** | C1+C2 differ from C3+C4 in PSCR | difference in mean constraint-level PSCR between arms | constraint | **PRESPECIFIED** |
| **H1_planned** | C4 differs from C1–C3 pooled | as above | constraint | **PRESPECIFIED** |
| **H2_scale** | PSCR differs across Qwen2.5 3B/7B/14B | paired difference over the identical 120 constraints | constraint | **PRESPECIFIED** |
| **H3_family** | PSCR differs between families | difference, Qwen vs OLMo-2 | constraint | **PRESPECIFIED, now underpowered — see §6** |
| **S1** | PSCR is associated with verification status | within-class EVIDENCE_VERIFIED − DRAFT difference, for C1/C2/C3 | constraint | **NEW (ADR-0023 D9)** |
| **E1** | detectors of different mechanism order pairs alike | rank concordance of D2's score with the D0/D1/D3 partitions | pair, clustered | **EXPLORATORY** |
| **E2** | paraphrase induces distributional instability | mean pairwise JSD within a constraint at `T = 1` | constraint | **EXPLORATORY** |

**The independent unit is the constraint, always.** `statistics.yaml` sets
`pair_level_independence_assumption: FORBIDDEN`: pairs (A,B) and (A,C) share
response A, so with K=8 the effective information is nearer 8 responses than 28
pairs. Every interval resamples constraints with replacement, carrying each
constraint's pairs. Pooled pair-level figures are **point estimates only**.

**PSCR is undefined, never zero, where a constraint has no evaluable pair.** An
undefined cell is resampled as a cluster contributing nothing, widening the
interval rather than biasing it (Q6).

---

## 3. What replaces human validation

Five sources of evidence. Together they are **weaker than human validation**, and
the dissertation says so in these words.

### 3.1 Analytic construction

Properties true by construction and verifiable by reading the design, not by
measuring output:

* **Chance balance.** C1 and C4 are 10 entity / 10 boolean / 10 date; C2 and C3
  are 30 boolean each. Chance PSCR is therefore 0.611 / 0.500 / 0.500 / 0.611, and
  **both H1 arms sit at 0.5556, gap 0.0000.** The confirmatory contrast is
  chance-balanced *by construction*, which is what protects it —
  `statistics.yaml`: "design balance (ADR-0017), not adjustment".
* **Probe equivalence by construction** (`PROBE-C`, ADR-0023 D2): probes are
  generated from an authored `logical_form` plus a factor cell; identical
  surfaces are a hard load failure. **This audits the generator, not the
  generated meaning.**
* **The perfect-model invariant.** A model answering every probe correctly scores
  PSCR 0.000 on every constraint, pinned by a permanent test. Any metric change
  that breaks it is rejected.

### 3.2 Controlled cases with analytically known outcomes

`D0AUDIT-A` (ADR-0023 D3): each predicate is exercised against constructed KB
fixtures whose expected verdict follows **deductively** from the predicate's
declared `formal_statement`. Reported as a unit test, not an audit.

**Limit, stated twice because it matters:** this shows a predicate implements its
own stated formalisation. It cannot show the formalisation captures the
constraint. And since all 24 registered predicates delegate to one shared
pairwise implementation, it audits one mechanism reached by 24 names.

### 3.3 Cross-detector concordance — narrowly scoped

Measured pair-level agreement on jointly decided pairs, clustered over
constraints:

| model | D0 vs D1 | D0 vs D3 | D1 vs D3 |
|---|---|---|---|
| Qwen2.5-3B | 1.0000 | 0.9995 | 0.9957 |
| Qwen2.5-7B | 1.0000 | 0.9984 | 0.9917 |
| Qwen2.5-14B | 1.0000 | 0.9992 | 0.9931 |
| OLMo-2-7B | 0.9995 | 0.9990 | 0.9914 |

**D0 vs D1 is a redundancy check, not corroboration.** All 24 predicates the
benchmark uses route through `C1MutualExclusion.check_pair`, which is
answer-identity and never reads the KB on that path.

**D1 vs D3 is the one informative concordance**, phi-4 being an independent
mechanism. It supports exactly one claim: **canonicalisation and claim rendering
are faithful.** It is not accuracy — neither detector is gold, and both may share
the bias induced by rendering claims from canonical answers.

**This is also a finding in its own right (RQ4).** The proposal's anticipated
"D0 vs D1 disagreement" result does **not exist**. The pilot's apparent
disagreement (PSCR 0.209 vs 0.300) was a **coverage** difference; at pair level
the verdicts agree essentially perfectly.

### 3.4 Reproducibility and artefact integrity

96/96 raw responses byte-identical across nodes and days; pinned model revisions;
config and chat-template hashes on every response; content-addressed ids; append-only
archives; a D3 archive that refuses to mix chat-template renderings (Q32).

### 3.5 Sensitivity analysis

§5 below. This is the primary defence of the confirmatory results, replacing the
assurance that human-validated ground truth would have provided.

---

## 4. Detectors under the revised design

| detector | mechanism | reports | status |
|---|---|---|---|
| **D0** symbolic | answer-identity over the closed space, via `C1MutualExclusion` | verdict, coverage | RUN. **Not independent of D1** |
| **D1** exact match | answer-identity, polarity-aware | verdict, coverage, **PSCR — the primary metric** | RUN |
| **D2** NLI | bidirectional NLI over full rendered claims | **continuous score only; no verdict, no count** | RUN, 5 of 5 models. **Not independent — see ADR-0023 D6a** |
| **D3** judge | phi-4 pairwise, chat-templated, single-shot | verdict, coverage, label distribution | RUN, 4 of 5 models |
| **D4** distributional | teacher-forced per-token logprob → softmax at `T=1` | mean pairwise JSD. **EXPLORATORY, not a detector** | RUN, 1 of 5 models by decision (ADR-0024) |

**D2 was expected to carry RQ4 and did not — MEASURED, see ADR-0023 D6a.** The
hope was that D2, scoring full rendered claims, would be the one instrument whose
mechanism is not answer-identity. Its rank concordance with D1 is **1.0000 in all
five models**, because `render_claim` hands it claims that differ in one slot or
are byte-identical. **No pair of D0/D1/D2/D3 is independent**, because they share
their input construction rather than merely their code. RQ4's answer is therefore
a negative one, and it is reported as such.

**D3 coverage is a property of the model, not of the judge** — the share of pairs
where both responses make a claim: 0.6125 (7B) to 0.8247 (14B), non-monotone in
scale. Coverage and contradiction rate are reported **separately, never pooled**.

---

## 5. The ground-truth sensitivity analysis (RQ6)

**H1_primary cannot be computed on the EVIDENCE_VERIFIED subset.** Verified from
the benchmark data: EVIDENCE_VERIFIED is C1 16 / C2 16 / C3 16 / **C4 0**, and
`history` is absent. Arm B would be C3 alone, and the chance gap moves from
0.0000 to **+0.0417**, destroying the balance that protects the contrast.

| id | analysis | why |
|---|---|---|
| **S1** | within-class EVIDENCE_VERIFIED − DRAFT difference in mean PSCR, for C1, C2, C3; cluster bootstrap | holds class and answer-type composition fixed, so it estimates the association with verification status rather than with class. **C4 is not assessable and this is reported.** |
| **S2** | per-class PSCR restricted to EVIDENCE_VERIFIED, beside the full-benchmark values | descriptive, no contrast |
| **S3** | `C1+C2 vs C3` on the 48, labelled a **different contrast** | the +0.0417 chance gap pushes arm A up, i.e. toward a *positive* estimate, so it works **against** the observed negative sign. A negative estimate here is **conservative**. |

Further sensitivity analyses, all prespecified: eligibility rule (pairs requiring
ANSWER only, vs ANSWER-or-NEGATED as implemented); abstention handling;
Mistral's inclusion; and the restriction to D3's judgeable subset.

---

## 6. Limitations

Ordered by severity.

1. **No reference labels exist.** No detector accuracy is estimable. Every
   detector figure is a measurement of the detector, not of its correctness.
2. **D0 and D1 are not independent.** Their agreement is near-tautological; the
   detector stack provides less triangulation than the design assumed.
3. **Probe equivalence is constructed, not validated.** All 1,056 probes carry
   `validation_status: draft`; no human judged any of them. A systematically
   mis-specified `logical_form` would pass every machine check.
4. **Ground truth is provisional for 81 of 132 constraints**, and the verified
   subset **excludes C4 entirely**, so C4's ground truth cannot be
   sensitivity-tested at all.
5. **Cross-family generalisation rests on two families.** With Mistral not
   reportable, H3_family is a single OLMo-2-vs-Qwen comparison.
6. **D0's error rate is unestablished and now permanently so.**
7. **Multiplicity is unaddressed for the 10-pair model family.** A bootstrap
   interval yields no p-value; three of ten pairs exclude zero; BH-FDR is not
   applied and this is stated rather than patched.
8. **Scale results are within one family at three sizes.** No causal claim about
   parameter count is available.
9. **One probe set, one track, fixed decoding.** Track B and stochastic decoding
   are unexercised.
10. **43 of 960 probes carry a structural pathology (Q33).** The `PROBE-C`
    audit flags 43 polar-cloze probes whose own text contains the gold answer,
    confined to factor cells 04/06/07 — and cells 04 and 07 are exactly those
    observed failing across three model families. This plausibly depresses
    canonicalisation for **every** model. It does **not** explain Mistral's
    failure (its 71 cases span P02–P08). Whether to add a sensitivity analysis
    excluding them is an open design decision; no probe has been changed.

---

## 7. Reporting rules

* **Response-level, pair-level, constraint-level and model-level quantities are
  never pooled or interchanged.** Each figure names its unit.
* **Coverage, abstention and contradiction rate are reported separately.**
* **A bootstrap interval is not a test.** "Excludes zero" is written as exactly
  that, never as a p-value or as significance.
* **Agreement is never called accuracy.**
* Every table omitting Mistral says why.
* Empirical observations, analytic results, assumptions, hypotheses and
  limitations are labelled distinctly.
* Figures from superseded runs retain their labels and are never cited as
  current — specifically job 15127's D3 archive (99.14% parse failure, Q32) and
  any pre-canonicaliser-v1.1 number.
