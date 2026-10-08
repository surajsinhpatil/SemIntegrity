# ADR-0007 — A separate development set, disjoint from the 120

**Kind:** METHODOLOGY

**Status:** APPROVED BY RESEARCHER 2026-09-11 · resolves Q1
**Date:** 2026-09-11

## Context
§5.6 requires "a frozen development/test split so that NLI thresholds, judge
prompts and extraction rules are tuned only on development data". §4.11 rests
the confirmatory claim on "C1+C2 versus C3+C4 (60 constraints per arm)" over the
120-constraint benchmark. Carving dev out of the 120 would leave ~48 per arm and
weaken the very sample-size argument Appendix A.1 used to reject n = 15 per class.

## Decision
The **120 constraints are the test set**. A **separate development set of 24
constraints (6 per class)** is authored, disjoint from the 120:

* the 12 Phase-1 pilot constraints (3 per class) are absorbed into it;
* 12 further constraints are authored to reach 6 per class;
* dev constraints reuse the **same schemas** but **different entity
  instantiations**, so tuning transfers without leaking test content;
* disjointness (no shared entity set, gold proposition or probe surface form) is
  enforced by `design_validator.py` before freeze.

Dev is used for: D2 checkpoint selection and per-class threshold calibration,
D3 prompt tuning, Track B extraction rules, D0 predicate correction (§4.8.2),
and canonicaliser alias tuning.

## Consequences
* The confirmatory arms remain exactly **60/60**, as preregistered.
* ~12 extra constraints and 192 dev probes of authoring cost.
* Per-class D2 threshold calibration gets 6 dev constraints × 28 pairs × models
  of human-labelled data per class — thin but workable, where 3 would not be.
* Dev probes need human equivalence validation too, adding to the Q9 load.
* Every tuned artefact is hashed and frozen before the test set is touched, and
  the freeze manifest makes that claim checkable rather than asserted.

## Amendment 2026-10-06 — the "same schemas" clause, read with ADR-0017

Confirmed unchanged in substance by researcher decision A7; one clause needs
qualifying.

ADR-0017 makes `answer_type` a property of the schema **axis**, while the 12
Phase-1 pilot constraints have it fixed by **class** (C1 `entity`, C2/C3
`boolean`, C4 `date`). The pilot constraints are therefore **not** instances of
the 24 test schemas, and "dev constraints reuse the same schemas but different
entity instantiations" cannot hold literally for them.

* The 12 pilot constraints remain valid development and tuning material. They
  are what the canonicaliser's Q21 polarity mapping was derived from, which is
  also why §5.6 bars them from the test set — see `docs/BENCHMARK_ACCOUNTING.md`.
* The **12 new** dev constraints are the ones that instantiate the 24 test
  schemas, with entity sets disjoint from the test set. The disjointness rule is
  unchanged and still enforced by
  `design_validator.validate_split_disjointness`.
* Per-class D2 threshold calibration still has 6 dev constraints per class, as
  this ADR requires; what changes is only which of them share a schema with the
  test set.

## Amendment 2026-10-07 — the 12 new development cells, adopted

Approved by the researcher. The three new dev families are:

| family | domain | axis | answer type | schemas |
|---|---|---|---|---|
| `F-HIS-02` | history | 2 | `boolean` | `S-C1-02` … `S-C4-02` |
| `F-BIO-03` | biology | 3 | `entity` | `S-C1-03` … `S-C4-03` |
| `F-SCI-04` | science_technology | 4 | `date` | `S-C1-04` … `S-C4-04` |

3 families × 4 classes = 12, which with the pilot's three axis-1 families brings
dev to the 24 this ADR requires, 6 per class. All five domains are covered, and
all three answer types appear among the new cells. Cell indices 02–04 keep dev
inside 01..10 and clear of the test split's 11..16.

The 12 existing pilot constraints **remain separate development data**: they are
what the Q21 polarity mapping was tuned on, which is why §5.6 bars them from the
test set, and their answer types follow class rather than axis because they
predate ADR-0017.

### Accepted limitation — axes 5 and 6 have no new-dev coverage

**This is a limitation of the calibration design, not a defect to be fixed
later.** D2's per-class thresholds, D2's checkpoint selection, D3's prompt
tuning and D0's dev-split predicate corrections are all calibrated on dev — and
dev contains no extremal-uniqueness (axis 5) or interval-boundary (axis 6)
schema. Those tuned artefacts are nonetheless applied to the 40 test
constraints built on axes 5 and 6.

Widening dev to cover all six axes would require more than the 24 constraints
this ADR fixes, so the gap follows from the approved design. It is recorded here,
in `docs/AUTHORING_PLAN.md` §2.2 and in the limitations, to be **reported** rather
than silently corrected.
