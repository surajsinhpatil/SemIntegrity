# ADR-0017 — Answer type is fixed by schema axis, not by class

**Kind:** METHODOLOGY

**Status:** APPROVED BY RESEARCHER 2026-10-06 · **AMENDED 2026-10-07** · resolves Q23
**Date:** 2026-10-06 · amended 2026-10-07

> **Read the amendment at the end of this file first.** The Decision section
> below states the ORIGINAL axis-only rule, which was found to be incompatible
> with the approved probe generator. The operative rule is
> answer type ← **(axis, class)**.

## Context

§4.3 asks that families "hold nuisance variation **approximately constant**
across classes — same domain, comparable entity familiarity, **comparable answer
type**, comparable lexical complexity — while the structural requirement
changes".

Three facts bound how much that sentence can carry, and they are recorded here
because the decision is easy to over-read in either direction:

* `answer_type` is **not** one of §4.3's 17 per-constraint fields. It appears in
  §4.4.1 as part of the formal **probe** representation. The constraint-level
  field in `schemas/constraint.py` is marked `DERIVED` and exists because §4.7
  requires a closed answer space.
* §4.7 positively expects answer type to vary *within* a constraint: "the
  directionality probe factor mixes 'Is A the X of B?' (yes/no) with 'What is the
  X of B?' (an entity)". ADR-0003 records the same thing.
* §4.4.2 reserves the phrase "balanced exactly across classes" for the four
  probe transformation factors, which do not include answer type.

So §4.3 asks for comparability within a family. It does **not** require answer
type to be crossed with class, and the words are "approximately" and
"comparable", not "identical". This ADR adopts one reading; it does not claim
the proposal compels it.

The 12 Phase-1 pilot constraints make answer type a perfect function of class —
C1 `entity` (m=3), C2 `boolean` (m=2), C3 `boolean` (m=2), C4 `date` (m=3) —
which is not "approximately constant across classes" on any reading.

## Decision

**Answer type is a property of the schema axis**, so all four class variants
within a family share one answer type, and every class receives the same
answer-type mix. Under ADR-0002's lattice each axis contributes exactly one
constraint to every (class, domain) cell, so this is automatic rather than
something authoring must be careful about.

**Two axes are `date`** (axes 4 and 6), two are `entity` (1 and 3) and two are
`boolean` (2 and 5), giving **10 / 10 / 10 per class**.

**Answer-space cardinality is retained as a covariate** in §4.11's
beta-binomial mixed model.

## Why

Chance agreement between two independent draws from a closed answer space of
size *m* is 1/*m*, so the chance "contradiction" rate is 1 − 1/*m*: **0.667 at
m = 3 and 0.500 at m = 2**. A 2-option class therefore looks *more
self-consistent* than a 3-option class before any model behaviour is involved.

| allocation | C1 | C2 | C3 | C4 | confirmatory C1+C2 vs C3+C4 | planned C4 vs C1–C3 |
|---|---|---|---|---|---|---|
| class-tied (the pilot) | 0.667 | 0.500 | 0.500 | 0.667 | 0.583 vs 0.583 — balanced | 0.667 vs 0.556 — **0.111 artefact** |
| **axis-fixed (adopted)** | **0.611** | **0.611** | **0.611** | **0.611** | balanced | balanced |

The class-tied arrangement happens to be balanced across the *confirmatory*
arms, because each arm holds one 3-option and one 2-option class. It is not
balanced for the descriptive four-class profile, which carries a spread of
0.167, nor for the planned C4-versus-pooled contrast. §4.11 presents the
four-class profile as descriptive, but H1 makes a per-class claim, so that is
where the artefact would have done its damage.

The covariate is kept as well as the balance, not instead of it: §4.11 states
that "a bootstrap on a difference in means cannot deliver covariate
adjustment", and the cluster bootstrap carries the confirmatory claim. Balance
protects the bootstrap; the covariate protects the model-based analyses.

## Cost, accepted explicitly

**D0's structural coverage on C4 falls.** `c4_interval_precedence` — the one
predicate that decides something closed-space mutual exclusion cannot, namely a
single response dated before `temporal_validity.start` — needs a parseable date
answer. Class-level answer-type balance forces C4 to hold no more date
constraints than C1, so:

| | C4 constraints with a date answer | D0 structural coverage on C4 |
|---|---|---|
| class-tied | 30 / 30 | 30 / 30 |
| one date axis | 5 / 30 | 5 / 30 |
| **two date axes (adopted)** | **10 / 30** | **10 / 30** |
| three date axes | 15 / 30 | 15 / 30 |

Two axes was chosen as the point where C4 keeps a third of its structural
coverage without pushing temporal content into half the C1–C3 constraints.
There is no free optimum here and the trade is recorded rather than smoothed
over.

**Which axes carry which type is an engineering choice inside this decision**,
taken on authorability: axis 4 (event precedence) renders most naturally as a
date, and axis 5 (extremal uniqueness) renders naturally as a yes/no
verification, so those two swapped rather than axis 1 or 3 being forced into an
unnatural type. Reversible without touching this ADR.

## Consequences

* **Authoring.** Each axis must render in one answer type across all four
  classes. The awkward cells are a `date`-typed C1/C2 and a `boolean`-typed C4;
  `docs/BENCHMARK_COVERAGE_MATRIX.md` §5 records the three predicted to resist.
* **Probe generation.** Unchanged. Directionality already mixes probe answer
  types within every constraint, and Stage 0 reconciles them (§4.7).
* **Detectors.** D0 as above. D1 and D4 both read `answer_space`, so their
  baselines shift with cardinality too — which is the reason the covariate is
  retained rather than the balance being treated as sufficient.
* **Statistics.** `configs/analysis/statistics.yaml` carries
  `answer_space_cardinality` as a secondary-model covariate.
* **Human annotation.** Unchanged in volume; annotators judge probe
  equivalence, not answer type.
* **ADR-0007.** Its clause that dev constraints "reuse the **same schemas** but
  different entity instantiations" cannot hold literally for the 12 pilot
  constraints, whose answer types follow class rather than axis. They remain
  valid development and tuning material; the 12 *new* dev constraints are the
  ones that instantiate the 24 test schemas. Recorded in ADR-0007 and in
  `docs/BENCHMARK_ACCOUNTING.md`.
* **The pilot's own numbers are unaffected.** They are DIAGNOSTIC either way,
  and this ADR changes nothing about how they were produced.

---

# Amendment 2026-10-07 — answer type is a function of (axis, class)

**Approved by the researcher.** This is an amendment to ADR-0017 **only**. It
changes nothing in ADR-0002 (the lattice), ADR-0003 (probe factors), the CANON
result or threshold, the Revision 3/4 coverage matrix's cell allocation, or the
132-cell allocation.

## 1. The rule

| class | answer type |
|---|---|
| **C1** | per axis — the approved axis-fixed allocation (1 entity · 2 boolean · 3 entity · 4 date · 5 boolean · 6 date) |
| **C2** | **`boolean`, every axis** |
| **C3** | **`boolean`, every axis** |
| **C4** | per axis — the approved axis-fixed allocation |

Executable in `configs/benchmark/design.yaml` under `lattice.answer_type`
(`fixed_by: axis_and_class`), read by
`design_validator.answer_type_for_cell` and enforced by the
`answer_type_allocation` rule. The rule is read from the config, never restated
in code.

## 2. Why

The original axis-only allocation is **incompatible with the already-approved
probe generator**. `probes.surface.realise` routes a probe by answer type:

```python
open_answer = answer_type in (AnswerType.ENTITY, AnswerType.DATE)
if open_answer and direct and affirmative:
    return _realise_open(...)   # requires subject / relation / object
return _realise_verify(...)     # accepts an author-written claim
```

`_realise_open` renders `"The {relation} of {subject} is ___"`, which
presupposes a **single binary subject-relation-object**. A C2 conjunction and a
C3 universal do not have one — `surface.py`'s own docstring says so: *"a
conjunction or a universal cannot be reassembled from parts, so the author
writes the claim and it is embedded in a frame"* — and that author-claim path is
reachable only from `_realise_verify`.

Under the axis-only rule, C2 and C3 on axes 1, 3, 4 and 6 acquired `entity` or
`date` answer types, so their direct+affirmative cells routed to
`_realise_open` and could not be generated. Forcing the conjunction into the
`relation` slot produced, measurably:

```
C2  P01  The city that is both the capital and located in the Federal District of Brazil is
C3  P01  The sovereign state of which it is the capital of Brasília is
C3  P03  The country it's the capital of of Brasília is ___.
```

Two of the eight probes per affected constraint would have been discarded at
§4.4.5 human validation, breaking ADR-0003's requirement that each constraint
carry all 8 factor cells exactly once.

## 3. Measured scope

| | constraints |
|---|---|
| C2/C3 on an open axis — **no single binary relation exists** | **44** (40 test, 4 dev) |
| C4 on an open axis — uses the existing relation representation | **22** |
| Unaffected (C1 anywhere; C2/C3/C4 on boolean axes 2 and 5) | **66** |

By axis: 1 → 10, 3 → 12, 4 → 12, 6 → 10. By class: C2 22, C3 22. 66 of 132 new
constraints were affected in total.

## 4. Why Option A was rejected

Option A was to extend the generator with an author-claim *open* form (an
authored `open_stem` slot, or a frame such as `"Which city satisfies: <claim>?
___"`). Rejected: it introduces a **new probe-generation surface after** the
probe methodology and the CANON evidence were established. The CANON result
(0/96, frozen 2026-10-07) and ADR-0003's balance guarantees were obtained on the
existing surface forms, and a new form would sit outside the evidence that
licenses them.

## 5. Why Option C was rejected

Option C was to revert to the pilot's class-tied allocation. Rejected: it
unnecessarily reintroduces the class-tied answer-type confounding ADR-0017 was
created to address, at a **0.167** descriptive spread, when Option B achieves
the same generator compatibility at **0.111**.

## 6. Why Option B is accepted

* the existing generator remains valid and **unmodified**;
* the factor lattice is unchanged — all 8 cells generate for every constraint;
* **K = 8** is unchanged;
* the **confirmatory class comparison remains balanced**;
* answer-type distribution is treated as **descriptive/covariate** information,
  not a primary experimental factor.

## 7. The resulting distribution, and its statistical status

Per class, over the 120 test constraints:

| class | `entity` | `boolean` | `date` | chance-PSCR |
|---|---|---|---|---|
| C1 | 10 | 10 | 10 | 0.611 |
| C2 | 0 | 30 | 0 | 0.500 |
| C3 | 0 | 30 | 0 | 0.500 |
| C4 | 10 | 10 | 10 | 0.611 |

Chance-PSCR is 1 − 1/*m* for a closed answer space of size *m*: the
contradiction rate two independent draws produce before any model behaviour is
involved.

Three claims, kept distinct:

* **Confirmatory class balance — preserved exactly.** C1+C2 = 0.556 and
  C3+C4 = 0.556, gap **0.000**. §4.11 rests the confirmatory claim on that
  contrast and on nothing else, so the claim is unaffected.
* **Descriptive answer-type distribution — a 0.111 spread.** The four-class
  descriptive profile is no longer artefact-free: C1 and C4 sit at 0.611, C2 and
  C3 at 0.500. Against 0.000 under the original axis-only rule and 0.167 under a
  fully class-tied one. §4.11 presents the four-class profile as descriptive; H1
  makes a per-class claim, so this must be **reported**, and it belongs in
  §4.14's limitations.
* **Answer type as a covariate.** `answer_space_cardinality` remains a covariate
  in the secondary beta-binomial model (`configs/analysis/statistics.yaml`). It
  is not a factor and no contrast is defined over it. §4.11 notes a bootstrap
  cannot deliver covariate adjustment, which is why the *balance* of the
  confirmatory arms, not the covariate, is what protects the claim.

The planned C4-versus-pooled contrast carries a 0.074 gap, between the 0.000 of
the original rule and the 0.111 of a class-tied one.

## 8. Scope of this amendment

This amends **ADR-0017 only**. Unchanged: ADR-0002, ADR-0003, ADR-0007,
ADR-0018, CANON and its threshold, the canonicaliser, Variant A, K = 8, the
probe factor lattice and syntax rotation, the coverage matrix's **cell**
allocation (proved identical: the same 120 constraint ids, families, schemas and
domains), the 132-cell manifest, D0's scope, Q5/ADR-0016 and Q22.

Two consequences are recorded rather than absorbed:

* **D0's `ANCHOR` reach narrows from 8 schemas to 4** — `S-C1-04`, `S-C4-04`,
  `S-C1-06`, `S-C4-06`. C2 and C3 are boolean on every axis, so a temporal
  anchor could never apply to them; the four registrations that previously
  claimed it have had their `formal_statement` corrected, because a predicate
  claiming a check it cannot run is the failure mode
  `configs/detectors/d0_symbolic.yaml` names. No detection logic was added or
  removed.
* **The corroboration rule gained a temporal-axis trigger.** Axes 4 and 6 are
  temporal by construction, so a C2 or C3 on one of them is a temporal fact
  whatever its answer type. Without that trigger this amendment would have
  silently narrowed §4.3's corroboration requirement by moving those constraints
  off `date`. The policy in `design.yaml` is unchanged; only its
  operationalisation was widened to hold the same set of facts in scope.
  Verified: **81 constraints required a second source before the amendment and
  81 do after.**
