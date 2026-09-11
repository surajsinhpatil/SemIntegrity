# Human judgement budget

Exact item-by-item breakdown of every task requiring a human. Generated from the
frozen design counts; recomputed by `scripts/analysis/human_budget.py` whenever a
count changes.

> **Correction to an earlier figure.** I previously reported "~4,500 human
> judgements". That was an undercount. It omitted the development set (added by
> the Q1 decision on 2026-09-11), probe re-validation after rewrites, the Phase 3
> pilot annotation batch, the Track B extraction spot-check, ground-truth
> corroboration and the D0 schema audit. The correct figure is **≈ 5,721**.

---

## A. Probe semantic-equivalence validation (§4.4.5)

Human validation is the **certification step** — NLI is explicitly not permitted
to certify the equivalence that NLI-based detection then depends on.

| # | Task | Items | Annotators | Reps | Judgements |
|---|---|---:|---:|---:|---:|
| A1 | Primary tier, test set (120 × 8 probes) | 960 | 2 | 1 | **1,920** |
| A2 | Development set (24 × 8 probes) — ADR-0007 | 192 | 2 | 1 | **384** |
| A3 | Saturation tier (24 × 42 additional probes) | 1,008 | 1 | 1 | **1,008** |
| A4 | Re-validation of rewritten probes (≤10% discard) | 217 | 2 / 1 | 1 | **333** |
| | **Subtotal A** | | | | **3,645** |

A4 assumes the §4.12 gate is just met (≥ 90% survival): 96 primary + 20 dev
rewrites at 2 annotators (232), plus 101 saturation rewrites at 1 (101).

---

## B. Blinded pair annotation (§4.9)

| # | Task | Items | Annotators | Reps | Judgements |
|---|---|---:|---:|---:|---:|
| B1 | Sample A — representative | 400 pairs | 2 | 1 | **800** |
| B2 | Sample B — enriched | 300 pairs | 2 | 1 | **600** |
| B3 | Phase 3 pilot batch (IAA gate) | 100 pairs | 2 | 1 | **200** |
| B4 | Adjudication of disagreements | ~160 pairs | 1 | 1 | **160** |
| | **Subtotal B** | | | | **1,760** |

* B3 size is **not specified in the proposal** — 100 pairs is my proposal, enough
  for a usable Krippendorff's α at the gate. Needs your sign-off (Q11 companion).
* B4 assumes 15–30% disagreement across the 800 A+B pairs (range 105–210) plus
  the pilot. This is the one line that cannot be known until the data exists.
* Each pair carries **five labels**: relation, correctness of A, correctness of B,
  response status, and a failure-taxonomy reason where contradictory. One
  "judgement" here means one complete pair form, not one label.

---

## C. Ground truth, predicates and extraction

| # | Task | Items | People | Reps | Judgements |
|---|---|---:|---:|---:|---:|
| C1 | Ground-truth verification + second source (§4.3) | 144 constraints | 1 | 1 | **144** |
| C2 | D0 three-instance schema audit (§4.8.2) | 24 schemas × 3 | 1 | 1 | **72** |
| C3 | Track B extraction spot-check (Q15) | 100 responses | 1 | 1 | **100** |
| | **Subtotal C** | | | | **316** |

C1 covers 120 test + 24 dev constraints. Each requires Wikidata resolution **plus**
an independent corroborating source for historical and temporal facts.

---

## Total

| Block | Judgements |
|---|---:|
| A — probe validation | 3,645 |
| B — pair annotation | 1,760 |
| C — ground truth, predicates, extraction | 316 |
| **Total** | **5,721** |

---

## Time estimate

**Rates below are assumptions, not measurements.** They are replaced with
measured rates after the Phase 3 pilot, which is the first point at which real
per-item timings exist.

| Task | Judgements | Assumed rate | Hours |
|---|---:|---|---:|
| A1–A4 probe equivalence | 3,645 | 30 s | 30.4 |
| B1–B3 pair annotation | 1,600 | 90 s | 40.0 |
| B4 adjudication | 160 | 120 s | 5.3 |
| C1 ground truth (2 sources) | 144 | 15 min | 36.0 |
| C2 D0 audit instance | 72 | 10 min | 12.0 |
| C3 Track B spot-check | 100 | 60 s | 1.7 |
| **Total** | **5,721** | | **≈ 125 h** |

### Split by person

| Person | Tasks | Hours |
|---|---|---:|
| **Second annotator** | A1, A2, A4 (primary+dev share), B1, B2, B3 | **≈ 31** |
| **Researcher** | everything else, incl. all of A3, B4, C1–C3 | **≈ 94** |

The second annotator's ~31 hours is the number to quote when recruiting. It is
the figure that makes Q9 actionable: it is a real commitment, but a bounded one.

### What this confirms

§4.13 says the binding resource is "authoring and annotation effort, not GPU
time". The arithmetic agrees: ~125 human hours against an inference load of
~21,750 short generations, which is a few GPU-hours on the cluster.

---

## Not counted here

* **Constraint authoring itself** (writing 144 constraints and their schemas).
  This is creative work, not judgement, and the proposal does not size it.
  Realistically it dominates C1.
* **Probe authoring** (960 + 192 + 1,008 surface realisations). Generated from
  the formal representation and factor cells, then human-checked — the checking
  is counted in A, the generation is automated.
* **Preregistration writing, analysis interpretation and paper writing.**
