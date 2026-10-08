# Benchmark accounting

**Confirmed by the researcher 2026-10-06 (decision A7).** One place for the
constraint and probe counts, so that "120" never has to be guessed at again.

The proposal and ADR-0007 are both authoritative and they do not disagree; the
proposal simply does not say where the pilot constraints go, and ADR-0007
decides it.

---

## What the proposal fixes

* **Appendix A.1** — *"Increased to 30 per class, **120 total**."*
* **§4.3** — *"Size. 120 constraints: 30 per class, balanced across 5 domains
  ... giving 6 constraints per domain per class."*
* **§4.4.2** — *"K = 8 probes per constraint, **960 probes in total**, C(8,2) =
  28 pairs per constraint."*
* **§4.11** — the confirmatory contrast is *"C1+C2 versus C3+C4 (60 constraints
  per arm)"*, and *"the collapsed contrast carries the confirmatory claim, which
  is what makes 120 constraints statistically adequate"*.
* **§4.12** — Phase 1 *"author 12 pilot constraints (3 per class)"*; Phase 5
  *"Author the 120-constraint benchmark"*. Two distinct authoring tasks.
* **§5.6** — *"a frozen development/test split so that NLI thresholds, judge
  prompts and extraction rules are tuned only on development data"*. No size is
  given, and nothing is said about where the pilot constraints land.

## What ADR-0007 decides

The 120 **are the test set**. A separate development set of 24 (6 per class) is
authored, disjoint from the 120; the 12 pilot constraints are absorbed into it,
and 12 further dev constraints are authored to reach 24.

**Why the alternative is closed, independently of preference.** §5.6 restricts
tuning to development data, and the canonicaliser's Q21 polarity mapping — v1.1,
in production — was *derived from pilot output*
(`docs/Q21_polarity_mapping_spec.md` §7 recomputes the 96 responses and sets the
mapping from them). The 12 pilot constraints are already tuning data. Placing
them in the test set would retrospectively breach §5.6.

---

## Constraints

| | count | state |
|---|---|---|
| Existing pilot constraints (→ dev) | **12** | authored, `verification_status: DRAFT`, two byte-identical runs complete |
| New **test** constraints (the 120) | **120** | **not authored** |
| New **dev** constraints, to reach ADR-0007's 24 | **12** | **not authored** |
| **At freeze** | **144** | 120 test + 24 dev |
| **Newly authored** | **132** | 120 + 12 |

The 120 is unchanged from §4.3 and Appendix A.1. What ADR-0007 changes is the
*authoring bill*: none of the existing 12 can be one of the 120, so 120 must be
written rather than 108.

## Primary-tier probes (K = 8, Track A)

| | count | state |
|---|---|---|
| Test | 120 × 8 = **960** | all new |
| Dev, existing | **96** | the pilot run; 28 of them rewritten under RW-001 |
| Dev, new | 12 × 8 = **96** | not authored |
| Dev total | 24 × 8 = **192** | |
| **At freeze** | **1,152** | 960 + 192 |
| **Newly authored** | **1,056** | 960 test + 96 new dev |

The 960 matches §4.4.2 and `configs/inference/primary.yaml` (`probes: 960`).

**The existing 96 probes stay pilot/dev material.** They are not part of the 960,
they were generated at K=8 against the pilot's 12 constraints, and the 28
rewritten ones carry new surface text with unchanged formal representations
(`docs/PROBE_REWRITE_LOG.md`). The distinction matters because the recorded pilot
responses correspond to those probe ids, and ADR-0005 makes the responses
immutable.

## Other tiers, for completeness

Derived from the same constraints rather than authored separately, except where
noted. Itemised in Q18.

| tier | basis | probes |
|---|---|---|
| Saturation (§4.4.4) | 24 of the 120 at K = 50 | **1,008 additional**, authored |
| Track B (§4.4.3) | 20-constraint subset, free-form | 160, same probes under a different instruction |
| Stochastic | 20 × 8 × 3 samples | no new probes |
| Knowledge screen (§4.11) | ~2.5 prerequisite facts × 120 | ~300, from the constraint records |
| Determinism check (§4.6) | 100 prompts × 2 batch compositions | no new probes |

Q18's total of ≈21,750 generations across 7 models is consistent with §4.13's
"roughly 19,000" as an order-of-magnitude figure.

---

## The two splits must not share ids

The id grammar (`K-<class>-<domain>-<nn>`) carries no split field, and
`design_validator.validate()` filters to one split before checking
`unique_ids` — so a test constraint and a pilot/dev constraint could share an id,
pass both validations, and merge in any analysis that joins on `constraint_id`.

**Allocation:** test constraints and families take cell index **11..16**;
01..10 stays with pilot/dev. Numbering test 01..06 would re-mint all 12 existing
pilot ids. Renumbering the pilot instead was rejected: its probe ids appear in
the two byte-identical pilot result files, which ADR-0005 makes immutable.

Checked by `BenchmarkDesignValidator.validate_global_id_uniqueness`, which the
readiness audit runs. While only the pilot split exists on disk the check reports
**BLOCKED**, not PASS, because it cannot yet discriminate.

## One clause of ADR-0007 needs reading with ADR-0017

ADR-0007 says dev constraints "reuse the **same schemas** but **different entity
instantiations**". Under ADR-0017 answer type is fixed by schema axis, while the
12 pilot constraints have it fixed by class — so they are not instances of the 24
test schemas. They remain valid development and tuning material; it is the 12
**new** dev constraints that instantiate the 24 schemas, with entity sets
disjoint from the test set.
