# ADR-0007 — A separate development set, disjoint from the 120

**Status:** ACCEPTED (researcher, 2026-09-11) · resolves Q1
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
