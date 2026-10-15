# ADR-0023 — Redesign without human validation

**Kind:** METHODOLOGY (supersedes parts of the preregistered design)

**Status:** **PARTIALLY APPROVED BY RESEARCHER, 2026-10-15.** Explicitly
approved that day, in the researcher's own words: proceed with D2 NLI scoring
(**D6**); report S4 as a secondary sensitivity analysis alongside the unchanged
K=8 primary results and keep the CANON threshold at 95% (**D9**, and the CANON
retention in **D1**); treat D0AUDIT-A strictly as formal/synthetic unit testing,
not human validation (**D3**). D2's measured outcome is recorded in **D6a**,
which corrects D6's rationale.

The remainder is **PROPOSED**: **D1** (the full go/no-go revision), **D2**
(PROBE-C), **D4** (the NONDEGEN resolution), **D5** (removing IAA), **D7**
(withdrawing detector-accuracy claims) and **D8** (Mistral's disposition). Of
these, **D5 and D7 follow necessarily** from the researcher's founding decision
that the project requires no human annotation — with no annotators there is no
agreement to measure and no gold to score against — but they are listed as
proposed because they were not separately confirmed.
**Date:** 2026-10-15
**Authorised by:** researcher decision of 2026-10-15, with professor's permission,
to redesign so that the project requires no human annotation or validation.
**Supersedes parts of:** the §4.12 go/no-go criteria
(`configs/inference/pilot.yaml`), §4.9 human validation, the detector-accuracy
clauses of §4.8, and ADR-0007's stated purposes.
**Relates to:** ADR-0005 (immutable results), ADR-0008 (open-weight judge),
ADR-0010 (cluster interaction), ADR-0017 (answer-type allocation),
ADR-0024 (D4 distribution construction), Q31, Q32.
**Evidence base:** `docs/AUDIT_2026-10-15_no_human_validation.md`.

---

## 1. Context

The design made human annotation load-bearing in four places. The audit
established that **no human-annotation code was ever written** —
`src/semintegrity/annotation/` and `src/semintegrity/knowledge_screen/` contain
only `__init__.py`. The dependency is entirely in specifications, so this ADR
supersedes text rather than deleting implementations.

It also established two things that change what a labelless design can claim,
and both are measured rather than assumed. They are stated here because they
constrain every decision below:

1. **D0 and D1 are substantially the same detector.** All 24 registered
   `s_c*_0*` predicates — the only ones any of the 120 test constraints select —
   route their pairwise verdict through `C1MutualExclusion.check_pair`, which
   reduces to `a.canonical_answer == b.canonical_answer` and never reads the
   `kb` argument on that path. Measured D0-vs-D1 pair agreement is **1.0000**
   (κ 1.0000) for three models and 0.9995 for OLMo-2.
2. **D3 concordance is descriptive, not validation.** D1-vs-D3 agreement is
   0.9914–0.9957. phi-4 is an independent mechanism, but the task it is given —
   compare two rendered claims differing only in the answer slot — largely
   recovers answer-identity.

**Consequence: cross-detector agreement cannot substitute for validation.** The
detectors do not independently triangulate contradiction detection. What they
establish is narrower and still worth stating: canonicalisation and claim
rendering are faithful, checked by one genuinely independent model.

---

## 2. Decisions

### D1 — The §4.12 go/no-go criteria are revised

| id | old | new |
|---|---|---|
| GT | ≥95% have unambiguous, sourceable ground truth | **RETAINED**, machine-checked via the evidence ladder |
| **PROBE** | ≥90% of probes survive **human** semantic-equivalence validation | **SUPERSEDED** → `PROBE-C` (D2 below) |
| CANON | Stage 0 canonicalises ≥95% of valid responses | **RETAINED AND FROZEN**; unchanged |
| **D0AUDIT** | every predicate passes its three-instance schema audit | **RESPECIFIED** → `D0AUDIT-A` (D3 below) |
| **NONDEGEN** | D2 and D3 produce non-degenerate predictions | **RESOLVED** to the `pilot.yaml` reading (D4 below) |
| **IAA** | inter-annotator agreement is acceptable | **REMOVED** (D5 below) |
| ABSTAIN | no class with a dominant abstention rate | **RETAINED**, computable now |

### D2 — PROBE becomes PROBE-C: equivalence by construction, audited by machine

Probes are *generated* from an authored `logical_form` plus a factor cell, and
`benchmark/loader.py` already makes identical surfaces a **hard** failure. The
claim therefore becomes:

> Probes are semantically equivalent **by construction**. Surface distinctness,
> factor-cell coverage and the absence of machine-detectable probe pathologies
> are verified. No human judged their equivalence.

`PROBE-C` passes when: every probe's `logical_form` matches its constraint's
schema; no two probes of a constraint share a surface; the factor lattice is
fully covered; and zero probes trip the pathology checks of §3.1.

**What is lost, stated plainly:** this audits the *generator*, not the generated
meaning. A systematically mis-specified `logical_form` would pass. "Validated"
is no longer available as a word; "constructed and machine-audited" is.

### D3 — D0AUDIT becomes D0AUDIT-A: analytic cases, not hand-checked instances

`detectors/d0/audit.py` requires human-supplied expected verdicts ("An audit
case with no human-supplied verdict is rejected, not defaulted"). Replaced by
cases whose expected verdict follows **deductively** from the predicate's
declared `formal_statement` against a constructed KB fixture — a unit test, not
an annotation.

**This is strictly weaker than the original and must be reported as such.** It
establishes that a predicate implements its own stated formalisation. It cannot
establish that the formalisation captures the constraint, which is what a human
auditor was for. Given §1.1, it is weaker again: it audits one shared
implementation reached by 24 names.

**RESIDUAL UNCERTAINTY FOR THE RESEARCHER.** Whether deductive case construction
counts as "human validation" for the professor's purposes is a boundary only the
researcher can set. If it does count, `D0AUDIT` is removed outright and D0's
correctness rests on code review alone.

### D4 — NONDEGEN resolves to the preregistered reading

`configs/inference/pilot.yaml` (the §4.12 gate, "fixed IN ADVANCE") defines it
as a label-distribution property. `configs/models/_judge.yaml` describes it as
"dev-split judge-vs-human agreement". **The `pilot.yaml` reading governs**,
because it is the preregistered artefact and the `_judge.yaml` line is a
verification note rather than a gate definition. `_judge.yaml` must be amended
to match.

Under that reading **D3 satisfies NONDEGEN on measured data**: 1,017 : 1,308 for
Qwen2.5-3B, and comparable splits for Qwen2.5-7B, Qwen2.5-14B and OLMo-2-7B.
D2's half is addressed by D6.

### D5 — IAA is removed, and nothing replaces it

With no annotators there is no agreement to measure. It is **not** replaced by
inter-detector agreement: §1.1 shows D0 and D1 share their pairwise
implementation, so their concordance is near-tautological. The reportable
replacement is narrower — D1-vs-D3 concordance as evidence that canonicalisation
and rendering are faithful, with D0-vs-D1 reported **only** as a redundancy
check and never as corroboration.

### D6 — D2 is RETAINED, as a continuous score with no thresholded verdict

The threshold cannot be calibrated without labels, and `d2_nli.yaml` forbids a
bare 0.5 precisely to stop one being invented. Three options were weighed:
invent a threshold (**rejected** — arbitrary, and leaks nothing because it
answers to nothing), remove D2, or change its estimand.

**Decision: change the estimand.** D2 reports a bidirectional contradiction
*score* per pair. It contributes **no verdict and no contradiction count**, and
therefore enters no PSCR, no H1 contrast and no agreement table. What is
reported is **rank concordance** between D2's score and the D0/D1/D3 partitions:
does a soft semantic signal order pairs the way the symbolic rule does, and
where does it not?

**Why retain it at all, given §1.1.** D0, D1 and D3 all reduce to comparing
answer slots. **D2 is the only detector in the stack whose mechanism is not
answer-identity** — an NLI model scores the full rendered claims. The
near-perfect D0/D1/D3 concordance is therefore an argument *for* D2, not against
it: D2 is the only instrument that could disagree for an interesting reason.

**Two constraints on this decision.**
* `checkpoint_selection.status` is `EMPIRICAL_NOT_ASSUMED` with `selected: null`.
  Selecting among checkpoints without dev labels is not possible, so **one
  checkpoint is fixed a priori and pinned by revision, and no checkpoint
  comparison is performed or claimed.** Declaring this removes the leakage
  concern: there is nothing to tune.
* **D2 requires one GPU run** (NLI scoring over ~2,000–2,800 pairs per model).
  If the researcher declines that cost, the fallback is **removal**, documented,
  not a substitute.

A rank-concordance statistic must **not** be routed through
`analysis.detector_scores`, whose `require_human_gold` guard stays in force. It
needs its own, differently named function so that concordance can never be
printed under an accuracy heading.

### D6a — MEASURED 2026-10-15: D6's RATIONALE WAS WRONG

D6 retained D2 on the argument that "D2 is the only detector in the stack whose
mechanism is not answer-identity". **The measurement refutes that.**

`scripts/detectors/run_d2_nli.py`, five models, jobs 15160/15162-15165
*(cluster, pasted)*:

| model | scored | rank concordance vs D1 | vs D3 |
|---|---|---|---|
| Qwen2.5-3B | 2,325 | **1.0000** (1.0000, 1.0000) | 0.9989 |
| Qwen2.5-7B | 2,058 | **1.0000** (1.0000, 1.0000) | 0.9959 |
| Qwen2.5-14B | 2,771 | **1.0000** (1.0000, 1.0000) | 0.9973 |
| OLMo-2-7B | 2,205 | **1.0000** (1.0000, 1.0000) | 0.9986 |
| Mistral-7B | 1,050 | **1.0000** (1.0000, 1.0000) | no D3 archive |

**Perfect rank separation in all five models**, and the divergence file shows
why there is no overlap to speak of: the lowest-scoring D1-VIOLATION pair scores
**0.6957** and the highest-scoring D1-SATISFIED pair scores **0.0096**. A gap of
0.686 with nothing in between. The scores are bimodal, not graded.

**The mechanism, and it is structural.** `d2/templates.render_claim` builds each
claim from the constraint's `gold_proposition` with the response's canonical
answer substituted in. So for a pair of responses:

* **different answers** -> two claims differing in exactly one slot, which an
  NLI model finds trivially contradictory;
* **the same answer** -> two claims that are **byte-identical strings**, and an
  NLI model given (X, X) returns entailment with near-certainty, hence 0.0096.

D2 is therefore not performing semantic judgement on this benchmark. It is
detecting whether two strings differ in one slot, which is answer-identity
reached by a 435M-parameter route.

**The general finding, which is stronger than §1.1's.** §1.1 said D0 and D1 are
non-independent because they **share an implementation**. D6a shows something
wider: **every detector downstream of `render_claim` is non-independent, because
they all consume claims rendered from the same canonical answers.** The
rendering step destroys independence before any detector sees anything. Shared
input construction, not shared code.

**Consequence: no pair of D0/D1/D2/D3 provides independent corroboration, by
construction.** The dissertation's validation argument must not rest on
cross-detector agreement anywhere, and §4.8.2's anticipated detector-
disagreement result does not exist in any form.

**What D2 still establishes, narrowly.** An independent 435M NLI model, with no
access to the answer space or the knowledge base, separates the two classes of
rendered claim perfectly. That is further evidence that **canonicalisation and
claim rendering are faithful** — the same claim D1-vs-D3 supported, now from a
second mechanism. It is not accuracy and not corroboration of contradiction
detection.

**D2 is RETAINED and REPORTED as this negative result.** It is not deleted: the
finding that the stack collapses onto answer-identity is worth more than the
confirmation D6 hoped for, and it could only be established by running D2.

### D7 — Detector accuracy claims are withdrawn permanently

Precision, recall, F1 and AUPRC against gold are removed from the design, not
deferred. `analysis.detector_scores.require_human_gold` stays as an active
guard. `VerificationStatus.HUMAN_VALIDATED` becomes **unreachable by design** and
must be documented as permanently unused so no future code aspires to it.

### D8 — Mistral-7B-Instruct-v0.3: CANON-FAIL retained, reported in full

Measured, five models, 960 responses each:

| model | INVALID | CANON | outside space | Q31 entity/date | bool buried | polar, neither |
|---|---|---|---|---|---|---|
| Qwen2.5-3B | 13 | 0.9865 | 13 | 0 | 0 | 0 |
| Qwen2.5-7B | 8 | 0.9917 | 7 | 0 | 0 | 1 |
| Qwen2.5-14B | 9 | 0.9906 | 6 | 3 | 0 | 0 |
| OLMo-2-7B | 26 | 0.9729 | 16 | 4 | 1 | 5 |
| **Mistral-7B-v0.3** | **355** | **0.6302** | **13** | **71** | **27** | **244** |

**Q31 is settled by arithmetic.** Recovering **every** one of the 71 entity/date
fall-through cases yields a CANON ceiling of **0.7042**, still far below the
frozen ≥0.95 gate. **No entity/date fall-through rule can rescue Mistral.** Q31
therefore stops being the decision that determines Mistral's inclusion and
reverts to a question about what Stage 0 ought to mean. The ceiling is an
**upper bound, not a correction**: the canonicaliser and the gate are unchanged.

**Q31's characterisation of the failure was wrong and is corrected here.** Q31
says Mistral "answers polar probes by naming an answer-space member instead of
YES/NO". That is **71 + 27 = 98 of 355 (27.6%)**. The dominant mode is
`POLAR_NO_YESNO_NO_SPACE_MEMBER` — **244 of 355 (68.7%)** — a polar probe
answered with neither a yes/no nor an answer-space member.

**The sharpest result: Mistral's failure is format compliance, not knowledge.**
Its out-of-space count is **13 — identical to Qwen2.5-3B's 13**, the
best-canonicalising model. 342 of its 355 INVALIDs (96.3%) are polar-format
failures. "Mistral is less self-consistent" and "Mistral will not answer polar
probes in the required form" are different claims, and only the second is
supported.

**How Mistral is reported.** Its 960 raw responses and all existing figures stay
**immutable and unaltered** (ADR-0005). Its PSCR, H1 and per-class values remain
**NOT REPORTABLE** as model properties. It appears in its own section as a
**measurement-instrument finding** with the decomposition above. It is neither
deleted nor silently dropped from any table; every table that omits it says why.

**The cost, stated.** The reportable set becomes Qwen2.5 (three scales) and
OLMo-2-7B. **Cross-family generalisation therefore rests on two families, not
three**, and "no cross-family difference is detectable" rests on a single
OLMo-2-vs-Qwen comparison. This is a material weakening and belongs in the
limitations, not in a footnote.

**Is a replacement model justified? NOT REQUIRED, RECOMMENDED IF FEASIBLE —
researcher's decision.** A third family would restore the cross-family claim and
is cheap in GPU time (the measured D3 runs took 3.5–4.5 minutes). The binding
constraint is **disk quota — 1000 G hard, ~948 G already used by other users of
the shared account** — so staging new weights is the real cost, not compute. Any
candidate must sit outside {qwen, mistral, gemma, llama} *and* outside phi (the
judge's family). `ibm-granite/granite-3.1-8b-instruct` is already named in
`_judge.yaml` as an acceptable independent lineage. **Nothing is replaced or
erased either way.**

### D9 — The ground-truth sensitivity analysis is respecified

The intended analysis — re-run H1_primary on the 48 EVIDENCE_VERIFIED test
constraints — **cannot be run as specified.** Verified from
`data/benchmark/test/constraints.jsonl`:

| | C1 | C2 | C3 | C4 |
|---|---|---|---|---|
| EVIDENCE_VERIFIED | 16 | 16 | 16 | **0** |
| DRAFT | 14 | 14 | 14 | 30 |

**There are no EVIDENCE_VERIFIED C4 constraints**, and `history` is absent from
the subset entirely (biology, geography, public_office, science_technology, 12
each). So:

* H1_primary is `C1+C2 vs C3+C4`; with C4 empty, arm B would be **C3 alone** — a
  different contrast under the same name.
* The **chance balance is destroyed**. On the full benchmark both arms sit at
  0.5556 (gap 0.0000); on the 48 they are **0.5417 vs 0.5000, gap +0.0417**.
  `statistics.yaml` states that design balance, not covariate adjustment, is
  what protects the confirmatory contrast, so the protection is gone.

**Running H1_primary on the 48 and reporting it as confirming H1 would be
invalid.** Three analyses replace it:

* **S1 (primary sensitivity).** Within each of C1, C2 and C3, the difference in
  mean PSCR between EVIDENCE_VERIFIED and DRAFT constraints, cluster-bootstrapped
  over constraints. This estimates the association between verification status
  and PSCR **while holding class and answer-type composition fixed**, which is
  the actual question. **C4 cannot be assessed at all** and that is reported.
* **S2.** Per-class PSCR restricted to EVIDENCE_VERIFIED, placed beside the
  full-benchmark per-class values. Descriptive; no contrast.
* **S3.** The `C1+C2 vs C3` contrast on the 48, labelled a **different contrast**
  from H1_primary, with the +0.0417 chance gap stated. Note the gap's direction:
  chance alone pushes arm A's PSCR **up** relative to arm B, i.e. toward a
  *positive* estimate, so it works **against** the negative sign observed on the
  full benchmark. A negative estimate here is therefore **conservative**.

---

## 3. What becomes impossible to claim

Removed from the narrative, not weakened:

* detector precision, recall, F1, AUPRC — any detector accuracy against gold
* inter-annotator agreement, Krippendorff α, adjudication
* "the probes are semantically equivalent" **as a validated finding**
* D0's measured error rate
* that any detector is correct where detectors disagree
* human-validated ground truth, for any constraint
* D0-vs-D1 agreement as independent corroboration
* H1_primary on the EVIDENCE_VERIFIED subset

## 4. What survives intact

CANON and its gate verdict; H1_primary and H1_planned on the full 120; the
four-class profile; the scale comparisons; C3-at-chance; the analytic
chance-balance derivation (C1/C4 = 0.611, C2/C3 = 0.500, both H1 arms 0.5556);
reproducibility; D3 coverage and label distributions; D1-vs-D3 concordance; the
INVALID decomposition.

## 5. Alternatives considered and rejected

* **Lower the CANON gate or amend the canonicaliser** so Mistral passes.
  Rejected: forbidden by the researcher, and D8 shows it would not work — the
  ceiling is 0.7042.
* **Invent a D2 threshold.** Rejected (D6): arbitrary, and forbidden by
  `d2_nli.yaml`.
* **Use cross-detector agreement as the validation substitute.** Rejected (§1.1):
  D0 and D1 share their implementation.
* **Treat D1-vs-D3 concordance as accuracy.** Rejected: neither is gold, and
  both may share the bias induced by rendering claims from canonical answers.
* **Drop Mistral from the study.** Rejected: ADR-0005, and its decomposition is
  itself a result.
* **Retain `HUMAN_VALIDATED` as a future rung.** Rejected: an unreachable status
  invites a later claim to it.

## 6. Consequences

* The dissertation's validation argument becomes: analytic construction +
  controlled cases + one independent-mechanism concordance check +
  reproducibility + explicit sensitivity analysis. It is **weaker than human
  validation and must say so**.
* `configs/inference/pilot.yaml` and `configs/models/_judge.yaml` must be edited
  to agree with D1 and D4.
* Three documents need updating: `PROJECT_STATUS.md`, `docs/RESULTS_STATUS.md`,
  `docs/AUDIT_2026-10-15_no_human_validation.md`.
* D2 (D6) and D4 (ADR-0024) each need one GPU run, or explicit removal.
* The P04 probe-pathology concern is a **HYPOTHESIS, not an explanation**: all 3
  Qwen2.5-14B and all 4 OLMo-2 Q31 cases are P04, but Mistral's 71 span P02–P08.
  It requires the construction-level audit of D2/`PROBE-C`, and must not be
  presented as the cause of Mistral's failure.
